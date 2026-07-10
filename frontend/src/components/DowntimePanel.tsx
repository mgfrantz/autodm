import { useCallback, useEffect, useState } from 'react'
import { getDowntimeActivities, resolveDowntime } from '../stores/api'
import type { DowntimeResolveOptions } from '../stores/api'
import type { DowntimeActivity, DowntimeResolveResult, StoryEntry } from '../types'

/* ------------------------------------------------------------------ *
 * Downtime panel — DnD 5e between-adventures activities (PHB ch.8 +
 * XGE ch.2). The third stretch of an adventurer's life — after combat
 * and exploration and socialising — is what they do *between* jobs:
 * carouse, pull heists, gamble, brawl for coin, research lore, craft,
 * train, or simply rest. Each activity spends or earns gold, and some
 * ease exhaustion (Relaxation, Religion) or grant a proficiency when
 * Training completes.
 *
 * This panel is a UI over the tested backend API
 * (`/api/game/{id}/downtime`). It picks an activity, collects the
 * activity-specific parameters, and resolves it; results narrate into
 * the DM story bubble.
 * ------------------------------------------------------------------ */

interface DowntimePanelProps {
  gameId: number
  gold: number
  onChanged?: () => void | Promise<void>
  onNarration?: (entry: StoryEntry) => void
}

type Tier = 'lower' | 'middle' | 'upper'

const ACTIVITY_ICON: Record<string, string> = {
  carousing: '🍷',
  crime: '🗝️',
  gambling: '🎲',
  pit_fighting: '🥊',
  research: '📜',
  relaxation: '🛌',
  crafting: '🔨',
  profession: '🛠️',
  work: '⛏️',
  training: '📖',
  religion: '🕯️',
}

export default function DowntimePanel({ gameId, gold, onChanged, onNarration }: DowntimePanelProps) {
  const [activities, setActivities] = useState<DowntimeActivity[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<DowntimeResolveResult | null>(null)

  // Selected activity + its contextual parameters.
  const [selected, setSelected] = useState<string | null>(null)
  const [tier, setTier] = useState<Tier>('middle')
  const [workweeks, setWorkweeks] = useState(1)
  const [days, setDays] = useState(5)
  const [wager, setWager] = useState(50)
  const [games, setGames] = useState(3)
  const [itemValue, setItemValue] = useState(50)
  const [hasProficiency, setHasProficiency] = useState(true)
  const [target, setTarget] = useState('')
  const [targetKind, setTargetKind] = useState<'tool' | 'language'>('tool')

  const refresh = useCallback(async () => {
    try {
      const data = await getDowntimeActivities(gameId)
      setActivities(data)
      setError(null)
    } catch {
      setError('Failed to load downtime activities.')
    } finally {
      setLoading(false)
    }
  }, [gameId])

  useEffect(() => {
    setLoading(true)
    refresh()
  }, [refresh])

  const selectedActivity = activities.find((a) => a.id === selected) || null

  const showFlash = (r: DowntimeResolveResult | null) => {
    setResult(r)
    if (r) window.setTimeout(() => setResult(null), 6000)
  }

  const resolve = async () => {
    if (!selected) return
    setBusy(true)
    setError(null)
    try {
      // Build the request payload from the selected activity + params.
      const payload: DowntimeResolveOptions = { activity: selected }
      switch (selected) {
        case 'carousing':
          payload.tier = tier
          payload.workweeks = workweeks
          break
        case 'gambling':
          payload.wager = wager
          payload.games = games
          break
        case 'crime':
        case 'pit_fighting':
          // Use character-derived defaults (Dex/Str + proficiency).
          break
        case 'research':
          payload.workweeks = workweeks
          break
        case 'relaxation':
          payload.days = days
          break
        case 'crafting':
          payload.item_value = itemValue
          payload.days = days
          payload.has_proficiency = hasProficiency
          break
        case 'profession':
        case 'work':
          payload.workweeks = workweeks
          break
        case 'training':
          if (!target.trim()) {
            setError('Enter a tool or language id to train (e.g. "elvish", "brewers_supplies").')
            setBusy(false)
            return
          }
          payload.target = target.trim()
          payload.target_kind = targetKind
          payload.days = days
          break
        case 'religion':
          break
      }
      const res = await resolveDowntime(gameId, payload)
      showFlash(res)
      // Narrate into the DM story bubble.
      if (onNarration) {
        const lines = [res.narration]
        if (res.complication) lines.push(`Complication: ${res.complication}`)
        onNarration({
          role: 'system',
          content: lines.join(' '),
          timestamp: new Date().toISOString(),
        })
      }
      if (onChanged) await onChanged()
    } catch (err: unknown) {
      const msg =
        (err as { response?: { status?: number; data?: { detail?: string } } })?.response?.data?.detail ||
        'Could not resolve the downtime activity.'
      setError(msg)
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return <div className="text-parchment-400 animate-pulse text-center py-8">Gathering downtime options…</div>
  }

  if (error && activities.length === 0) {
    return <div className="text-blood-500 text-sm text-center py-8">{error}</div>
  }

  return (
    <div className="space-y-4">
      {/* Purse readout */}
      <div className="rounded-lg p-3 border bg-gold-900/20 border-gold-700/40 flex items-center justify-between">
        <span className="text-xs font-semibold text-gold-300 uppercase tracking-wide">Purse</span>
        <span className="text-lg font-bold font-fantasy text-gold-300">🪙 {gold} gp</span>
      </div>

      {/* Activity picker */}
      <div>
        <h3 className="text-xs text-parchment-500 font-semibold uppercase tracking-wide mb-2">
          Choose an Activity
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {activities.map((a) => (
            <button
              key={a.id}
              onClick={() => {
                setSelected(a.id)
                setError(null)
                showFlash(null)
                // Sensible defaults per activity.
                if (a.id === 'relaxation') setDays(5)
                else if (a.id === 'training') setDays(250)
                else if (a.id === 'crafting') setDays(10)
              }}
              className={`text-left rounded-lg p-3 border transition ${
                selected === a.id
                  ? 'bg-arcane-900/40 border-arcane-600'
                  : 'bg-parchment-900/50 border-parchment-700/40 hover:border-parchment-600'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg">{ACTIVITY_ICON[a.id] || '✦'}</span>
                <span className="font-semibold text-parchment-200">{a.name}</span>
                <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded ${
                  a.source === 'PHB' ? 'bg-leaf-900/50 text-leaf-300' : 'bg-arcane-900/50 text-arcane-300'
                }`}>
                  {a.source}
                </span>
              </div>
              <div className="text-xs text-parchment-500 leading-snug">{a.description}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Contextual parameters for the selected activity */}
      {selectedActivity && (
        <div className="bg-parchment-900/60 rounded-lg p-3 space-y-3 animate-fade-in">
          <h3 className="text-xs text-parchment-500 font-semibold uppercase tracking-wide">
            {selectedActivity.name} — Parameters
          </h3>

          {(selected === 'carousing') && (
            <div className="grid grid-cols-2 gap-2">
              <label className="text-xs text-parchment-400">
                Tier
                <select
                  value={tier}
                  onChange={(e) => setTier(e.target.value as Tier)}
                  disabled={busy}
                  className="block w-full mt-1 bg-parchment-900 border border-parchment-700 rounded px-2 py-1 text-parchment-200"
                >
                  <option value="lower">Lower (10 gp/wk)</option>
                  <option value="middle">Middle (50 gp/wk)</option>
                  <option value="upper">Upper (250 gp/wk)</option>
                </select>
              </label>
              <label className="text-xs text-parchment-400">
                Workweeks
                <input
                  type="number" min={1} max={10} value={workweeks}
                  onChange={(e) => setWorkweeks(Math.max(1, Number(e.target.value)))}
                  disabled={busy}
                  className="block w-full mt-1 bg-parchment-900 border border-parchment-700 rounded px-2 py-1 text-parchment-200"
                />
              </label>
            </div>
          )}

          {(['crime', 'pit_fighting', 'profession', 'work', 'religion'].includes(selectedActivity.id)) && (
            <p className="text-xs text-parchment-500">
              Uses your character's relevant modifier + proficiency. {selectedActivity.id === 'crime' && 'Payout scales with the heist checks; casing failure means no take.'}
              {selectedActivity.id === 'pit_fighting' && 'Purse: 0/50/150/500 gp for 0–3 successes.'}
              {selectedActivity.id === 'profession' && 'Requires a tool proficiency for the comfortable tier; else falls back to modest work.'}
            </p>
          )}

          {(['gambling'].includes(selectedActivity.id)) && (
            <div className="grid grid-cols-2 gap-2">
              <label className="text-xs text-parchment-400">
                Wager (gp)
                <input
                  type="number" min={0} max={gold} value={wager}
                  onChange={(e) => setWager(Math.max(0, Number(e.target.value)))}
                  disabled={busy}
                  className="block w-full mt-1 bg-parchment-900 border border-parchment-700 rounded px-2 py-1 text-parchment-200"
                />
              </label>
              <label className="text-xs text-parchment-400">
                Games
                <input
                  type="number" min={1} max={10} value={games}
                  onChange={(e) => setGames(Math.max(1, Number(e.target.value)))}
                  disabled={busy}
                  className="block w-full mt-1 bg-parchment-900 border border-parchment-700 rounded px-2 py-1 text-parchment-200"
                />
              </label>
            </div>
          )}

          {(['research'].includes(selectedActivity.id)) && (
            <label className="text-xs text-parchment-400 block">
              Workweeks (25 gp each)
              <input
                type="number" min={1} max={10} value={workweeks}
                onChange={(e) => setWorkweeks(Math.max(1, Number(e.target.value)))}
                disabled={busy}
                className="block w-full mt-1 bg-parchment-900 border border-parchment-700 rounded px-2 py-1 text-parchment-200"
              />
            </label>
          )}

          {(['relaxation', 'crafting'].includes(selectedActivity.id)) && (
            <label className="text-xs text-parchment-400 block">
              Days
              <input
                type="number" min={1} max={250} value={days}
                onChange={(e) => setDays(Math.max(1, Number(e.target.value)))}
                disabled={busy}
                className="block w-full mt-1 bg-parchment-900 border border-parchment-700 rounded px-2 py-1 text-parchment-200"
              />
            </label>
          )}

          {selected === 'crafting' && (
            <div className="grid grid-cols-2 gap-2">
              <label className="text-xs text-parchment-400">
                Item value (gp)
                <input
                  type="number" min={1} max={10000} value={itemValue}
                  onChange={(e) => setItemValue(Math.max(1, Number(e.target.value)))}
                  disabled={busy}
                  className="block w-full mt-1 bg-parchment-900 border border-parchment-700 rounded px-2 py-1 text-parchment-200"
                />
              </label>
              <label className="text-xs text-parchment-400 flex items-end pb-1">
                <input
                  type="checkbox" checked={hasProficiency}
                  onChange={(e) => setHasProficiency(e.target.checked)}
                  disabled={busy}
                  className="mr-2 accent-gold-500"
                />
                Has tool proficiency
              </label>
            </div>
          )}

          {selected === 'training' && (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <label className="text-xs text-parchment-400">
                  Target id
                  <input
                    type="text" value={target} placeholder="elvish / brewers_supplies"
                    onChange={(e) => setTarget(e.target.value)}
                    disabled={busy}
                    className="block w-full mt-1 bg-parchment-900 border border-parchment-700 rounded px-2 py-1 text-parchment-200"
                  />
                </label>
                <label className="text-xs text-parchment-400">
                  Kind
                  <select
                    value={targetKind}
                    onChange={(e) => setTargetKind(e.target.value as 'tool' | 'language')}
                    disabled={busy}
                    className="block w-full mt-1 bg-parchment-900 border border-parchment-700 rounded px-2 py-1 text-parchment-200"
                  >
                    <option value="tool">Tool</option>
                    <option value="language">Language</option>
                  </select>
                </label>
              </div>
              <label className="text-xs text-parchment-400 block">
                Days this period (250 to complete · 1 gp/day)
                <input
                  type="number" min={1} max={250} value={days}
                  onChange={(e) => setDays(Math.max(1, Number(e.target.value)))}
                  disabled={busy}
                  className="block w-full mt-1 bg-parchment-900 border border-parchment-700 rounded px-2 py-1 text-parchment-200"
                />
              </label>
            </div>
          )}

          <button
            className="btn-primary text-sm w-full"
            onClick={resolve}
            disabled={busy}
          >
            {busy ? 'Resolving…' : `▶ Resolve ${selectedActivity.name}`}
          </button>
        </div>
      )}

      {/* Error / result flash */}
      {error && (
        <div className="text-blood-400 text-sm bg-blood-900/30 border border-blood-700/50 rounded p-2">
          {error}
        </div>
      )}

      {result && (
        <div className={`rounded-lg p-3 border text-sm animate-fade-in ${
          result.gold_delta > 0
            ? 'bg-leaf-900/40 border-leaf-700 text-leaf-200'
            : result.gold_delta < 0
            ? 'bg-amber-900/30 border-amber-700 text-amber-200'
            : 'bg-arcane-900/40 border-arcane-700 text-parchment-200'
        }`}>
          <div className="font-semibold mb-1">
            {result.gold_delta > 0 ? '💰 ' : result.gold_delta < 0 ? '🪙 ' : '✦ '}
            {result.narration}
          </div>
          {result.complication && (
            <div className="text-xs text-blood-300 mt-1">⚠️ {result.complication}</div>
          )}
          <div className="text-xs text-parchment-400 mt-1">
            Purse now: <span className="font-semibold text-gold-300">{result.character_gold} gp</span>
            {result.exhaustion !== null && <> · Exhaustion: {result.exhaustion}/6</>}
            {result.proficiency_granted && <> · ✦ Granted: {result.proficiency_granted}</>}
          </div>
        </div>
      )}
    </div>
  )
}
