import { useCallback, useEffect, useMemo, useState } from 'react'
import { listQuests, updateQuestStatus } from '../stores/api'
import type { Quest, QuestStatus, StoryEntry } from '../types'

/* ------------------------------------------------------------------ *
 * Quest Log panel — tracks quests the DM auto-detects from narration.
 *
 * The backend runs a DSPy quest-detection signature after every DM
 * narration, extracting quests offered / completed / failed and the
 * important information revealed. This panel is a read-mostly UI over
 * `/api/game/{id}/quests`: it lists those quests, groups them by
 * status, and lets the player manually adjust a quest's status (e.g.
 * mark a detected quest complete, or reopen one the DM wrongly closed).
 *
 * Status changes narrate into the DM story bubble and refresh state.
 * ------------------------------------------------------------------ */

interface QuestLogPanelProps {
  gameId: number
  onNarration?: (entry: StoryEntry) => void
  onChanged?: () => void | Promise<void>
}

type FilterKey = 'all' | QuestStatus

const FILTERS: { key: FilterKey; label: string; icon: string }[] = [
  { key: 'all', label: 'All', icon: '📜' },
  { key: 'active', label: 'Active', icon: '⚔️' },
  { key: 'completed', label: 'Completed', icon: '✅' },
  { key: 'failed', label: 'Failed', icon: '💀' },
]

const STATUS_STYLES: Record<QuestStatus, string> = {
  active: 'border-arcane-600/50 bg-arcane-900/20',
  completed: 'border-green-600/40 bg-green-900/20',
  failed: 'border-blood-600/40 bg-blood-900/20',
}

const STATUS_BADGE: Record<QuestStatus, string> = {
  active: 'bg-arcane-900/60 text-arcane-300',
  completed: 'bg-green-900/60 text-green-300',
  failed: 'bg-blood-900/60 text-blood-300',
}

/** Human-readable relative-ish timestamp (date portion only). */
function formatDate(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function QuestLogPanel({ gameId, onNarration, onChanged }: QuestLogPanelProps) {
  const [quests, setQuests] = useState<Quest[]>([])
  const [filter, setFilter] = useState<FilterKey>('all')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [flash, setFlash] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<number | null>(null)

  const refresh = useCallback(async () => {
    setRefreshing(true)
    setError(null)
    try {
      const res = await listQuests(gameId)
      // Stable ordering: active first, then completed, then failed;
      // within each, newest created first.
      const rank: Record<QuestStatus, number> = { active: 0, completed: 1, failed: 2 }
      const sorted = [...res.quests].sort((a, b) => {
        if (rank[a.status] !== rank[b.status]) return rank[a.status] - rank[b.status]
        return (b.created_at || '').localeCompare(a.created_at || '')
      })
      setQuests(sorted)
    } catch {
      setError('Could not load the quest log.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [gameId])

  useEffect(() => {
    setLoading(true)
    refresh()
  }, [refresh])

  const counts = useMemo(() => {
    const c = { all: quests.length, active: 0, completed: 0, failed: 0 }
    for (const q of quests) c[q.status] += 1
    return c
  }, [quests])

  const visible = useMemo(
    () => (filter === 'all' ? quests : quests.filter((q) => q.status === filter)),
    [quests, filter],
  )

  const showFlash = (msg: string) => {
    setFlash(msg)
    window.setTimeout(() => setFlash(null), 5000)
  }

  const handleStatus = async (quest: Quest, status: QuestStatus) => {
    if (quest.status === status) return
    setBusyId(quest.id)
    setError(null)
    try {
      const updated = await updateQuestStatus(gameId, quest.id, status)
      setQuests((prev) =>
        prev
          .map((q) => (q.id === updated.id ? updated : q))
          .sort((a, b) => {
            const rank: Record<QuestStatus, number> = {
              active: 0,
              completed: 1,
              failed: 2,
            }
            if (rank[a.status] !== rank[b.status]) return rank[a.status] - rank[b.status]
            return (b.created_at || '').localeCompare(a.created_at || '')
          }),
      )
      const verb =
        status === 'completed'
          ? 'completed'
          : status === 'failed'
            ? 'failed'
            : 'reopened'
      showFlash(`📜 "${updated.title}" marked ${verb}.`)
      if (onNarration) {
        onNarration({
          role: 'system',
          content: `📜 Quest ${verb}: ${updated.title}.`,
          timestamp: new Date().toISOString(),
        })
      }
      onChanged?.()
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Could not update that quest.'
      setError(detail)
    } finally {
      setBusyId(null)
    }
  }

  if (loading) {
    return (
      <div className="text-parchment-400 animate-pulse text-center py-8">
        Consulting the quest log…
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Filter tabs + counts */}
      <div className="flex flex-wrap items-center gap-2">
        {FILTERS.map((f) => {
          const active = filter === f.key
          const count = counts[f.key as keyof typeof counts] ?? 0
          return (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                active
                  ? 'border-arcane-500/70 bg-arcane-900/50 text-parchment-100'
                  : 'border-parchment-700/40 bg-parchment-900/40 text-parchment-400 hover:text-parchment-200'
              }`}
            >
              {f.icon} {f.label}{' '}
              <span className="opacity-70">({count})</span>
            </button>
          )
        })}
        <button
          onClick={refresh}
          disabled={refreshing}
          className="ml-auto text-xs px-3 py-1.5 rounded-full border border-parchment-700/40 bg-parchment-900/40 text-parchment-400 hover:text-parchment-200 disabled:opacity-40"
          title="Re-read the quest log"
        >
          {refreshing ? 'Refreshing…' : '↻ Refresh'}
        </button>
      </div>

      {/* Error / flash */}
      {error && (
        <div className="text-blood-400 text-sm bg-blood-900/30 border border-blood-700/50 rounded p-2">
          {error}
        </div>
      )}
      {flash && (
        <div className="rounded-lg p-3 border text-sm bg-arcane-900/40 border-arcane-700 text-parchment-200 animate-fade-in">
          {flash}
        </div>
      )}

      {/* Empty state */}
      {quests.length === 0 && (
        <div className="rounded-lg p-3 border bg-parchment-900/30 border-parchment-700/40 text-sm text-parchment-300">
          📜 <span className="font-semibold">No quests yet.</span> As you adventure, the DM
          automatically detects quests from the story and they'll appear here — including who
          offered them, your objective, and any reward hints.
        </div>
      )}

      {/* Filtered-empty state (quests exist, but none match the filter) */}
      {quests.length > 0 && visible.length === 0 && (
        <div className="rounded-lg p-3 border bg-parchment-900/30 border-parchment-700/40 text-sm text-parchment-400 text-center">
          No {filter} quests.
        </div>
      )}

      {/* Quest cards */}
      <div className="space-y-2.5">
        {visible.map((q) => {
          const isOpen = expanded === q.id
          return (
            <div
              key={q.id}
              className={`rounded-lg p-3 border space-y-2 ${STATUS_STYLES[q.status]}`}
            >
              <button
                className="w-full text-left"
                onClick={() => setExpanded((e) => (e === q.id ? null : q.id))}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-fantasy text-lg text-parchment-100">
                        {q.title}
                      </span>
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide ${STATUS_BADGE[q.status]}`}
                      >
                        {q.status}
                      </span>
                    </div>
                    {q.giver && (
                      <div className="text-[11px] text-parchment-500 mt-0.5">
                        from {q.giver}
                      </div>
                    )}
                  </div>
                  <span className="text-parchment-500 text-sm shrink-0">
                    {isOpen ? '▾' : '▸'}
                  </span>
                </div>
              </button>

              {/* Objective line (always visible — it's the at-a-glance summary) */}
              {q.objective && (
                <div className="text-sm text-parchment-200">
                  <span className="text-[10px] uppercase tracking-wide text-parchment-500">
                    Objective:{' '}
                  </span>
                  {q.objective}
                </div>
              )}

              {isOpen && (
                <div className="space-y-2 animate-fade-in">
                  {q.description && (
                    <p className="text-sm text-parchment-300 leading-snug">{q.description}</p>
                  )}
                  {q.reward_hint && (
                    <div className="text-sm text-gold-300">
                      <span className="text-[10px] uppercase tracking-wide text-gold-500/80">
                        Reward:{' '}
                      </span>
                      {q.reward_hint}
                    </div>
                  )}
                  {(q.created_at || q.updated_at) && (
                    <div className="text-[11px] text-parchment-600">
                      {q.created_at && <>offered {formatDate(q.created_at)}</>}
                      {q.created_at && q.updated_at && q.created_at !== q.updated_at && (
                        <> · updated {formatDate(q.updated_at)}</>
                      )}
                    </div>
                  )}

                  {/* Status controls */}
                  <div className="flex flex-wrap gap-2 pt-1">
                    {q.status !== 'completed' && (
                      <button
                        className="btn-primary text-xs px-3 py-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
                        onClick={() => handleStatus(q, 'completed')}
                        disabled={busyId === q.id}
                      >
                        ✅ Mark Complete
                      </button>
                    )}
                    {q.status !== 'failed' && (
                      <button
                        className="text-xs px-3 py-1.5 rounded border border-blood-700/50 bg-blood-900/30 text-blood-300 hover:bg-blood-900/50 disabled:opacity-40 disabled:cursor-not-allowed"
                        onClick={() => handleStatus(q, 'failed')}
                        disabled={busyId === q.id}
                      >
                        💀 Mark Failed
                      </button>
                    )}
                    {q.status !== 'active' && (
                      <button
                        className="text-xs px-3 py-1.5 rounded border border-arcane-700/50 bg-arcane-900/30 text-arcane-300 hover:bg-arcane-900/50 disabled:opacity-40 disabled:cursor-not-allowed"
                        onClick={() => handleStatus(q, 'active')}
                        disabled={busyId === q.id}
                      >
                        ↩ Reopen
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
