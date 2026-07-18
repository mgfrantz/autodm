import { useMemo } from 'react'
import type { GameEvent } from '../types'
import {
  concentrationColor,
  concentrationIcon,
  concentrationSummary,
} from '../utils/gameEvents'

/* ------------------------------------------------------------------ *
 * ConcentrationCard — inline game-event card showing a concentration
 * state change (DM function calling Phase 3.5: concentration tracking).
 *
 * Renders the spell name + 🧠 icon, the operation (started / broken /
 * ended / check_passed / check_failed), and — for concentration checks —
 * the Con-save breakdown (damage taken, DC, roll total). Colour-coded by
 * operation (started=indigo, broken=red, ended=stone, check_passed=green,
 * check_failed=amber). Failed operations render a muted card with the
 * reason. Dismissible.
 * ------------------------------------------------------------------ */

interface ConcentrationCardProps {
  event: GameEvent
  onDismiss?: () => void
}

export default function ConcentrationCard({ event, onDismiss }: ConcentrationCardProps) {
  const d = event.data
  const success = d.success ?? true
  const operation = (d.operation ?? 'ended').toLowerCase()
  const spellName = d.spell_name ?? 'spell'
  const reason = d.reason
  const damageTaken = d.damage_taken
  const concDc = d.concentration_dc
  const rollTotal = d.roll_total
  const isCheck = operation === 'check_passed' || operation === 'check_failed'

  const summary = useMemo(
    () => concentrationSummary(
      d.operation, d.spell_name, d.reason, d.damage_taken,
      d.concentration_dc, d.roll_total, d.success, d.message,
    ),
    [d.operation, d.spell_name, d.reason, d.damage_taken,
      d.concentration_dc, d.roll_total, d.success, d.message],
  )
  const colors = useMemo(() => concentrationColor(operation), [operation])
  const icon = useMemo(() => concentrationIcon(operation), [operation])

  // Operation badge (verb + glyph).
  const opBadge = useMemo(() => {
    switch (operation) {
      case 'started':       return { glyph: '✨', label: 'Concentration Started', tone: 'text-indigo-300' }
      case 'broken':        return { glyph: '💥', label: 'Concentration Broken', tone: 'text-rose-300' }
      case 'ended':         return { glyph: '🛑', label: 'Concentration Ended', tone: 'text-stone-300' }
      case 'check_passed':  return { glyph: '✅', label: 'Concentration Held', tone: 'text-emerald-300' }
      case 'check_failed':  return { glyph: '⚠️', label: 'Concentration Lost', tone: 'text-amber-300' }
      default:              return { glyph: '🧠', label: operation, tone: 'text-parchment-300' }
    }
  }, [operation])

  // Failed operation → muted card.
  if (!success) {
    return (
      <div
        className="rounded-lg border border-parchment-700/40 bg-parchment-900/20 p-3 mt-2 animate-scale-in opacity-80"
        role="status"
        aria-label={summary}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold text-parchment-300 flex items-center gap-1.5">
            <span aria-hidden>{icon}</span>
            {spellName}
            <span className="text-parchment-500 font-normal">— concentration event failed</span>
          </span>
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              className="text-parchment-500 hover:text-parchment-200 text-xs px-1.5 py-0.5 rounded transition-colors"
              aria-label="Dismiss concentration event"
              title="Dismiss"
            >
              ✕
            </button>
          )}
        </div>
        {d.message && (
          <div className="text-xs text-parchment-400 mt-1 italic">{d.message}</div>
        )}
      </div>
    )
  }

  return (
    <div
      className={`rounded-lg border ${colors.border} ${colors.bg} p-3 mt-2 animate-scale-in`}
      role="status"
      aria-label={summary}
    >
      {/* Header: icon + spell name + operation badge */}
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className={`text-sm font-bold ${colors.text} flex items-center gap-1.5`}>
          <span aria-hidden>{icon}</span>
          {spellName}
        </span>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="text-parchment-500 hover:text-parchment-200 text-xs px-1.5 py-0.5 rounded transition-colors"
            aria-label="Dismiss concentration event"
            title="Dismiss"
          >
            ✕
          </button>
        )}
      </div>

      {/* Operation badge */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`text-sm font-semibold ${opBadge.tone} flex items-center gap-1`}>
          <span aria-hidden>{opBadge.glyph}</span>
          {opBadge.label}
        </span>
      </div>

      {/* Concentration check breakdown (damage → DC → roll) */}
      {isCheck && (
        <div className="flex items-center gap-2 flex-wrap mt-1.5">
          {damageTaken !== null && damageTaken !== undefined && (
            <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-rose-900/40 text-rose-300">
              💢 {damageTaken} dmg
            </span>
          )}
          {concDc !== null && concDc !== undefined && (
            <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-parchment-800/60 text-parchment-300">
              DC {concDc}
            </span>
          )}
          {rollTotal !== null && rollTotal !== undefined && (
            <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${
              operation === 'check_passed'
                ? 'bg-emerald-900/40 text-emerald-300'
                : 'bg-amber-900/40 text-amber-300'
            }`}>
              🎲 Con save {rollTotal}
            </span>
          )}
        </div>
      )}

      {/* Reason text */}
      {reason && !isCheck && (
        <div className="text-xs text-parchment-400 mt-1.5 leading-relaxed italic">
          {reason}
        </div>
      )}
      {reason && isCheck && (
        <div className="text-xs text-parchment-400 mt-1 leading-relaxed italic">
          {reason}
        </div>
      )}
    </div>
  )
}
