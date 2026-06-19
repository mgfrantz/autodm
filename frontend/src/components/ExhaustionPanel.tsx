import { useCallback, useEffect, useState } from 'react'
import { getExhaustion, modifyExhaustion } from '../stores/api'
import type { ExhaustionModifyResult, ExhaustionStatus, StoryEntry } from '../types'

/**
 * Build a one-line, story-log-worthy narration of an exhaustion change, or
 * ``null`` when nothing worth narrating happened (a no-op set).
 *
 * Surfacing this in the DM bubble (via ``onNarration``) means a hazard the
 * player triggers from this panel reads like a world event, not just a silent
 * stat change — matching how rest outcomes are already logged.
 */
function exhaustionNarration(result: ExhaustionModifyResult): string | null {
  if (result.died) {
    return `☠️ Exhaustion reaches level ${result.after}. The character collapses, lifeless — death by exhaustion.`
  }
  if (!result.changed) return null
  if (result.after > result.before) {
    return `🥵 Exhaustion worsens — level ${result.before} → ${result.after}.`
  }
  return `✨ Exhaustion eases — level ${result.before} → ${result.after}.`
}

/* ------------------------------------------------------------------ *
 * Exhaustion is a DnD 5e special state — a stacking 0–6 affliction
 * (6 = death) driven by hazards such as extreme heat/cold, starvation,
 * forced marches, and certain monster abilities. Unlike the 14
 * conditions, it has *levels* and recovers by one level per long rest.
 *
 * This panel is a thin UI over the existing, already-tested backend
 * exhaustion API (`/api/game/{id}/exhaustion`). It is out-of-combat only
 * (combat exhaustion is tracked per-combatant via the combat tracker).
 * ------------------------------------------------------------------ */

const MAX_LEVEL = 6

/** All six PHB levels, with a severity tone for the pip row + the headline. */
const LEVEL_INFO: { level: number; title: string; tone: 'leaf' | 'gold' | 'amber' | 'blood' }[] = [
  { level: 1, title: 'Disadvantage on ability checks', tone: 'gold' },
  { level: 2, title: 'Speed halved', tone: 'gold' },
  { level: 3, title: 'Disadvantage on attack rolls & saving throws', tone: 'amber' },
  { level: 4, title: 'Hit-point maximum halved', tone: 'amber' },
  { level: 5, title: 'Speed reduced to 0', tone: 'blood' },
  { level: 6, title: 'Death', tone: 'blood' },
]

const TONE_TEXT: Record<string, string> = {
  leaf: 'text-leaf-300',
  gold: 'text-gold-300',
  amber: 'text-amber-300',
  blood: 'text-blood-400',
}

const TONE_PIP: Record<string, string> = {
  leaf: 'bg-leaf-500',
  gold: 'bg-gold-500',
  amber: 'bg-amber-500',
  blood: 'bg-blood-500',
}

/** Severity band for the *current* level (drives header accent + pip fill). */
function levelTone(level: number): 'leaf' | 'gold' | 'amber' | 'blood' {
  if (level <= 0) return 'leaf'
  if (level <= 2) return 'gold'
  if (level <= 4) return 'amber'
  return 'blood'
}

interface ExhaustionPanelProps {
  gameId: number
  onChanged?: () => void | Promise<void>
  /** Narrate an exhaustion change into the DM story bubble. Called with a
   *  system story entry only when the level actually changed (or the
   *  character died); no-op sets are not narrated. */
  onNarration?: (entry: StoryEntry) => void
}

export default function ExhaustionPanel({ gameId, onChanged, onNarration }: ExhaustionPanelProps) {
  const [status, setStatus] = useState<ExhaustionStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [setLevel, setSetLevel] = useState<number>(1)
  const [flash, setFlash] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const data = await getExhaustion(gameId)
      setStatus(data)
      setError(null)
    } catch {
      setError('Failed to load exhaustion status.')
    } finally {
      setLoading(false)
    }
  }, [gameId])

  useEffect(() => {
    setLoading(true)
    refresh()
  }, [refresh])

  const showFlash = (msg: string) => {
    setFlash(msg)
    window.setTimeout(() => setFlash(null), 3500)
  }

  const apply = async (mode: 'set' | 'add' | 'reduce', levels: number) => {
    setBusy(true)
    setError(null)
    try {
      const result = await modifyExhaustion(gameId, mode, levels)
      setStatus(result)
      if (result.died) {
        showFlash(`💀 ${result.character_id ? '' : ''}${result.before} → ${result.after}: the character succumbs to exhaustion and dies.`)
      } else if (result.changed) {
        showFlash(`Exhaustion ${result.before} → ${result.after}.`)
      } else {
        showFlash('No change — already at that level.')
      }
      // Surface the change in the DM story bubble (only when meaningful).
      const line = exhaustionNarration(result)
      if (line && onNarration) {
        onNarration({ role: 'system', content: line, timestamp: new Date().toISOString() })
      }
      if (onChanged) await onChanged()
    } catch {
      setError('Could not modify exhaustion (it cannot be changed mid-combat).')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return <div className="text-parchment-400 animate-pulse text-center py-8">Assessing exhaustion…</div>
  }

  if (error && !status) {
    return <div className="text-blood-500 text-sm text-center py-8">{error}</div>
  }

  if (!status) return null

  const level = status.exhaustion
  const tone = levelTone(level)
  const dead = status.dead || level >= MAX_LEVEL

  return (
    <div className="space-y-4">
      {/* In-combat guard — exhaustion changes go through the combat tracker. */}
      {status.in_combat && (
        <div className="bg-blood-900/40 border border-blood-700 rounded-lg p-3 text-sm text-blood-300">
          ⚔️ You are in combat. Exhaustion changes during a fight are handled per-combatant
          (e.g. a monster ability forces a level). Resolve combat first, then adjust here.
        </div>
      )}

      {/* Current level + pip meter */}
      <div className={`rounded-lg p-4 border ${
        dead
          ? 'bg-blood-900/50 border-blood-600'
          : tone === 'leaf'
          ? 'bg-leaf-900/30 border-leaf-700/40'
          : tone === 'gold'
          ? 'bg-gold-900/30 border-gold-700/40'
          : tone === 'amber'
          ? 'bg-amber-900/30 border-amber-700/40'
          : 'bg-blood-900/30 border-blood-600/50'
      }`}>
        <div className="flex items-baseline justify-between mb-2">
          <span className="text-parchment-500 text-sm font-semibold uppercase tracking-wide">
            Current Level
          </span>
          <span className={`text-3xl font-bold font-fantasy ${dead ? 'text-blood-300' : TONE_TEXT[tone]}`}>
            {level}
            <span className="text-parchment-600 text-base font-normal"> / {MAX_LEVEL}</span>
          </span>
        </div>

        {/* Six severity pips */}
        <div className="flex gap-1.5 mb-3">
          {LEVEL_INFO.map((info) => {
            const filled = level >= info.level
            return (
              <div
                key={info.level}
                title={`Level ${info.level}: ${info.title}`}
                className={`flex-1 h-2.5 rounded-full transition-all ${
                  filled ? TONE_PIP[info.tone] : 'bg-parchment-800/70'
                }`}
              />
            )
          })}
        </div>

        <div className={`text-sm ${dead ? 'text-blood-200' : 'text-parchment-200'}`}>
          {dead ? (
            <span className="font-semibold">☠️ The character is dead from exhaustion (level 6).</span>
          ) : level === 0 ? (
            <span className="text-leaf-300">The character is well-rested — no exhaustion.</span>
          ) : (
            status.description
          )}
        </div>
      </div>

      {/* Cumulative active effects */}
      <div className="bg-parchment-900/60 rounded-lg p-3">
        <h3 className="text-xs text-parchment-500 font-semibold uppercase tracking-wide mb-2">
          Cumulative Effects
        </h3>
        {level === 0 ? (
          <p className="text-sm text-parchment-400">None — healthy and unimpaired.</p>
        ) : (
          <ul className="space-y-1.5">
            {LEVEL_INFO.slice(0, level).map((info) => (
              <li key={info.level} className="flex items-start gap-2 text-sm">
                <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${TONE_PIP[info.tone]}`} />
                <span className="text-parchment-200">
                  <span className="text-parchment-500 mr-1">Lv {info.level}.</span>
                  {info.title}
                </span>
              </li>
            ))}
          </ul>
        )}
        {/* Derived mechanical flags */}
        {(level > 0 && !dead) && (
          <div className="flex flex-wrap gap-1.5 mt-3 pt-2 border-t border-parchment-800/60">
            {status.disadvantage_ability_checks && (
              <span className="text-xs bg-amber-900/40 text-amber-300 border border-amber-700/40 px-2 py-0.5 rounded">⚠️ Disadv: ability checks</span>
            )}
            {status.disadvantage_attack_rolls && (
              <span className="text-xs bg-amber-900/40 text-amber-300 border border-amber-700/40 px-2 py-0.5 rounded">⚠️ Disadv: attacks</span>
            )}
            {status.disadvantage_saving_throws && (
              <span className="text-xs bg-amber-900/40 text-amber-300 border border-amber-700/40 px-2 py-0.5 rounded">⚠️ Disadv: saves</span>
            )}
            {status.max_hp_halved && (
              <span className="text-xs bg-blood-900/40 text-blood-300 border border-blood-700/40 px-2 py-0.5 rounded">💔 Max HP halved</span>
            )}
            <span className={`text-xs px-2 py-0.5 rounded border ${
              status.speed_divisor === 0
                ? 'bg-blood-900/40 text-blood-300 border-blood-700/40'
                : status.speed_divisor === 2
                ? 'bg-amber-900/40 text-amber-300 border-amber-700/40'
                : 'bg-leaf-900/40 text-leaf-300 border-leaf-700/40'
            }`}>
              🏃 {status.speed_divisor === 0 ? 'Speed 0' : status.speed_divisor === 2 ? 'Speed halved' : 'Full speed'}
            </span>
          </div>
        )}
      </div>

      {/* Recovery note */}
      <p className="text-xs text-parchment-600 leading-relaxed">
        💤 A <span className="text-parchment-400">long rest</span> reduces exhaustion by one level
        (provided the character has had food and drink). Level 6 is fatal and cannot be recovered
        from by resting alone — it requires magic such as <span className="text-arcane-300">Greater Restoration</span>.
      </p>

      {/* Result flash */}
      {flash && (
        <div className="bg-arcane-900/40 border border-arcane-700 rounded-lg p-3 text-sm text-parchment-200 animate-fade-in">
          {flash}
        </div>
      )}
      {error && (
        <div className="text-blood-500 text-sm">{error}</div>
      )}

      {/* Controls — hazards add levels; recovery reduces them. */}
      <div className="bg-parchment-900/60 rounded-lg p-3">
        <h3 className="text-xs text-parchment-500 font-semibold uppercase tracking-wide mb-2">
          Adjust Exhaustion
        </h3>
        <p className="text-xs text-parchment-600 mb-3">
          Hazards (extreme weather, starvation, forced marches) add levels; rest or magic removes them.
        </p>
        <div className="grid grid-cols-2 gap-2 mb-2">
          <button
            className="btn-primary text-sm"
            onClick={() => apply('add', 1)}
            disabled={busy || status.in_combat || dead}
            title="A hazard takes effect (add one level)"
          >
            🔥 Gain a level (+1)
          </button>
          <button
            className="btn-primary text-sm bg-leaf-700 hover:bg-leaf-600"
            onClick={() => apply('reduce', 1)}
            disabled={busy || status.in_combat || level <= 0}
            title="Recover one level (e.g. Greater Restoration)"
          >
            ✨ Recover a level (−1)
          </button>
        </div>
        <div className="flex gap-2 items-center">
          <label className="text-xs text-parchment-500 shrink-0">Set to</label>
          <select
            className="input-field text-sm py-1 px-2 flex-1"
            value={setLevel}
            onChange={(e) => setSetLevel(Number(e.target.value))}
            disabled={busy || status.in_combat}
          >
            {[0, 1, 2, 3, 4, 5, 6].map((n) => (
              <option key={n} value={n}>
                Level {n}{n === 0 ? ' — none' : n === 6 ? ' — death' : ''}
              </option>
            ))}
          </select>
          <button
            className="btn-primary text-sm px-4 shrink-0"
            onClick={() => apply('set', setLevel)}
            disabled={busy || status.in_combat}
            title="Set exhaustion to an absolute level"
          >
            Apply
          </button>
        </div>
      </div>
    </div>
  )
}
