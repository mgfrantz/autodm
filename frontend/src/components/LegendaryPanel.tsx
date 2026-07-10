import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getEncounterLegendary,
  useLegendaryAction,
  getLairState,
  fireLairAction,
  listLegendaryCreatures,
} from '../stores/api'
import type {
  LegendaryCombatantView,
  LegendaryCreaturePreset,
  LairStateResponse,
  StoryEntry,
} from '../types'

/* ------------------------------------------------------------------ *
 * Legendary Actions & Lair Actions panel — DnD 5e boss-monster combat
 * (Monster Manual p. 11). The defining trait of a legendary creature
 * (a dragon, lich, beholder) is that it can act *off-turn*: it spends a
 * limited pool of legendary actions at the end of other creatures' turns,
 * and — in its lair — triggers environmental hazards on initiative 20.
 *
 * This panel surfaces both during combat: each legendary creature's
 * action budget (remaining/max) with per-action use buttons (attack-kind
 * actions let you pick a target), and a lair-action console that fires
 * the rotating initiative-20 hazard. Moves narrate into the DM story
 * bubble. It also browses the registry of ready-to-drop legendary bosses.
 * ------------------------------------------------------------------ */

interface LegendaryPanelProps {
  gameId: number
  onNarration?: (entry: StoryEntry) => void
  onChanged?: () => void | Promise<void>
}

const KIND_ICON: Record<string, string> = {
  attack: '⚔️',
  detect: '👁️',
  move: '🏃',
  utility: '✦',
  save: '🌀',
}

export default function LegendaryPanel({ gameId, onNarration, onChanged }: LegendaryPanelProps) {
  const [bosses, setBosses] = useState<LegendaryCombatantView[]>([])
  const [lair, setLair] = useState<LairStateResponse | null>(null)
  const [registry, setRegistry] = useState<LegendaryCreaturePreset[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [flash, setFlash] = useState<string | null>(null)
  // Per-boss target picker (combatant id → selected target id).
  const [targets, setTargets] = useState<Record<string, string>>({})
  // Registry detail view (creature id → expanded).
  const [expanded, setExpanded] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setBusy(true)
    try {
      const [enc, lairState] = await Promise.all([
        getEncounterLegendary(gameId).catch(() => null),
        getLairState(gameId).catch(() => null),
      ])
      setBosses(enc?.legendary_creatures ?? [])
      setLair(lairState)
      setError(null)
    } catch {
      setError('Could not load the legendary/lair state.')
    } finally {
      setBusy(false)
      setLoading(false)
    }
  }, [gameId])

  useEffect(() => {
    setLoading(true)
    refresh()
    // Load the registry once (it is game-independent).
    listLegendaryCreatures()
      .then(setRegistry)
      .catch(() => setRegistry([]))
  }, [refresh])

  // Default target = the player combatant, so attack actions have a target.
  useEffect(() => {
    setTargets((prev) => {
      const next = { ...prev }
      for (const b of bosses) {
        if (!next[b.combatant_id]) next[b.combatant_id] = 'player'
      }
      return next
    })
  }, [bosses])

  const showFlash = (msg: string | null) => {
    setFlash(msg)
    if (msg) window.setTimeout(() => setFlash(null), 6000)
  }

  const handleUse = async (boss: LegendaryCombatantView, actionId: string) => {
    const action = boss.legendary_actions.find((a) => a.id === actionId)
    const needsTarget = action?.kind === 'attack' && !!action?.attack
    const targetId = needsTarget ? targets[boss.combatant_id] || 'player' : undefined
    setBusy(true)
    setError(null)
    try {
      const res = await useLegendaryAction(gameId, boss.combatant_id, actionId, targetId)
      showFlash(res.description)
      if (onNarration) {
        onNarration({ role: 'system', content: res.description, timestamp: new Date().toISOString() })
      }
      await refresh()
      if (onChanged) await onChanged()
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Could not use that legendary action.'
      setError(detail)
    } finally {
      setBusy(false)
    }
  }

  const handleFireLair = async () => {
    setBusy(true)
    setError(null)
    try {
      const res = await fireLairAction(gameId)
      showFlash(res.description)
      if (onNarration) {
        onNarration({ role: 'system', content: res.description, timestamp: new Date().toISOString() })
      }
      await refresh()
      if (onChanged) await onChanged()
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Could not fire the lair action.'
      setError(detail)
    } finally {
      setBusy(false)
    }
  }

  // Enemy + player combatant ids for the target picker. We only know the boss
  // ids from `bosses`; the player is always targetable as 'player'.
  const allTargetIds = useMemo(() => ['player', ...bosses.map((b) => b.combatant_id)], [bosses])

  if (loading) {
    return (
      <div className="text-parchment-400 animate-pulse text-center py-8">
        Sensing the legendary threat…
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Not-in-combat / no boss banner */}
      {bosses.length === 0 && (
        <div className="rounded-lg p-3 border bg-arcane-900/20 border-arcane-700/40 text-sm text-parchment-300">
          🐉 <span className="font-semibold">No legendary creature in this fight.</span> Start
          combat with a legendary boss (pass <code className="text-arcane-300">is_legendary</code>{' '}
          + <code className="text-arcane-300">legendary_actions</code> on an enemy, or use a
          registry preset below) to manage its off-turn actions and lair hazards here.
        </div>
      )}

      {/* Boss cards */}
      {bosses.map((boss) => {
        const pct = boss.budget_max > 0 ? (boss.budget_remaining / boss.budget_max) * 100 : 0
        return (
          <div
            key={boss.combatant_id}
            className="rounded-lg p-3 border bg-blood-900/20 border-blood-700/40 space-y-3"
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="font-fantasy text-lg text-blood-300">{boss.name}</div>
                <div className="text-[11px] text-parchment-500 uppercase tracking-wide">
                  Legendary Creature
                </div>
              </div>
              <div className="text-right">
                <div className="text-2xl font-fantasy text-gold-300">
                  {boss.budget_remaining}
                  <span className="text-sm text-parchment-500">/{boss.budget_max}</span>
                </div>
                <div className="text-[10px] text-parchment-500 uppercase">actions left</div>
              </div>
            </div>

            {/* Action budget bar */}
            <div className="h-2 rounded-full bg-parchment-900/70 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-blood-500 to-gold-400 transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>

            {/* Action buttons */}
            <div className="space-y-2">
              {boss.legendary_actions.map((a) => {
                const affordable = boss.budget_remaining >= a.cost
                const needsTarget = a.kind === 'attack' && !!a.attack
                return (
                  <div
                    key={a.id}
                    className="rounded-lg p-2.5 border bg-parchment-900/50 border-parchment-700/40"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-base">{KIND_ICON[a.kind] || '✦'}</span>
                          <span className="font-semibold text-parchment-200">{a.name}</span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-arcane-900/60 text-arcane-300">
                            cost {a.cost}
                          </span>
                          {a.condition && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-blood-900/60 text-blood-300">
                              inflicts {a.condition}
                            </span>
                          )}
                        </div>
                        {a.description && (
                          <div className="text-xs text-parchment-500 mt-1 leading-snug">
                            {a.description}
                          </div>
                        )}
                      </div>
                    </div>
                    {needsTarget && (
                      <label className="block mt-2 text-[11px] text-parchment-400">
                        Target
                        <select
                          value={targets[boss.combatant_id] || 'player'}
                          onChange={(e) =>
                            setTargets((t) => ({ ...t, [boss.combatant_id]: e.target.value }))
                          }
                          disabled={busy || !affordable}
                          className="block w-full mt-1 bg-parchment-900 border border-parchment-700 rounded px-2 py-1 text-parchment-200"
                        >
                          {allTargetIds.map((id) => (
                            <option key={id} value={id}>
                              {id === 'player' ? 'Player' : id}
                            </option>
                          ))}
                        </select>
                      </label>
                    )}
                    <button
                      className="btn-primary text-xs w-full mt-2"
                      onClick={() => handleUse(boss, a.id)}
                      disabled={busy || !affordable}
                    >
                      {affordable
                        ? `▶ Use ${a.name} (${a.cost})`
                        : `Need ${a.cost} action${a.cost > 1 ? 's' : ''}`}
                    </button>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}

      {/* Lair action console */}
      {lair?.has_lair && (
        <div className="rounded-lg p-3 border bg-arcane-900/30 border-arcane-600/50 space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-xs text-arcane-300 font-semibold uppercase tracking-wide">
              🏰 Lair Actions
            </h3>
            <span className="text-[10px] text-parchment-500">
              initiative {lair.initiative_count} · round {lair.round_number}
              {lair.lair_last_fired_round === lair.round_number && ' · fired'}
            </span>
          </div>
          <div className="space-y-1.5">
            {lair.lair_actions.map((a) => (
              <div
                key={a.id}
                className="rounded p-2 border bg-parchment-900/40 border-parchment-700/30"
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm">{KIND_ICON[a.kind] || '✦'}</span>
                  <span className="font-semibold text-parchment-200 text-sm">{a.name}</span>
                  {a.save_dc ? (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-blood-900/60 text-blood-300">
                      DC {a.save_dc} {a.save_ability?.toUpperCase()}
                    </span>
                  ) : null}
                  {a.damage ? (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-blood-900/60 text-blood-300">
                      {a.damage} {a.damage_type}
                    </span>
                  ) : null}
                </div>
                {a.description && (
                  <div className="text-xs text-parchment-500 mt-1 leading-snug">{a.description}</div>
                )}
              </div>
            ))}
          </div>
          <button
            className="btn-primary text-sm w-full"
            onClick={handleFireLair}
            disabled={busy || lair.lair_last_fired_round === lair.round_number}
          >
            {lair.lair_last_fired_round === lair.round_number
              ? '⚠ Already fired this round'
              : '🌀 Fire lair action (initiative 20)'}
          </button>
        </div>
      )}

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

      {/* Registry browser */}
      <div>
        <h3 className="text-xs text-parchment-500 font-semibold uppercase tracking-wide mb-2">
          Legendary Bestiary ({registry.length})
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {registry.map((c) => (
            <div key={c.id} className="rounded-lg p-2.5 border bg-parchment-900/50 border-parchment-700/40">
              <button
                className="w-full text-left"
                onClick={() => setExpanded((e) => (e === c.id ? null : c.id))}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-parchment-200">{c.name}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-gold-900/50 text-gold-300">
                    CR {c.cr}
                  </span>
                </div>
                <div className="text-[11px] text-parchment-500 mt-0.5">
                  HP {c.max_hp} · AC {c.armor_class} · {c.legendary_budget_max} legendary actions
                  {c.lair_actions.length > 0 && ` · ${c.lair_actions.length} lair actions`}
                </div>
              </button>
              {expanded === c.id && (
                <div className="mt-2 space-y-1.5 animate-fade-in">
                  <div className="text-[11px] text-parchment-400">{c.notes}</div>
                  <div className="text-[11px] font-semibold text-arcane-300 uppercase">
                    Legendary Actions
                  </div>
                  {c.legendary_actions.map((a) => (
                    <div key={a.id} className="text-[11px] text-parchment-400">
                      <span className="text-parchment-200">
                        {KIND_ICON[a.kind] || '✦'} {a.name}
                      </span>{' '}
                      <span className="text-arcane-300">(cost {a.cost})</span>
                      {a.description && <> — {a.description}</>}
                    </div>
                  ))}
                  {c.lair_actions.length > 0 && (
                    <>
                      <div className="text-[11px] font-semibold text-arcane-300 uppercase mt-1">
                        Lair Actions
                      </div>
                      {c.lair_actions.map((a) => (
                        <div key={a.id} className="text-[11px] text-parchment-400">
                          <span className="text-parchment-200">{a.name}</span>
                          {a.description && <> — {a.description}</>}
                        </div>
                      ))}
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
