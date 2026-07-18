import { useMemo } from 'react'
import type { GameEvent } from '../types'
import { useDiceTumbleRolls } from '../hooks/useDiceTumble'
import {
  formatRollResult,
  formatAdvantage,
  getSuccessLabel,
  getRollColor,
  isCriticalHit,
  isCriticalMiss,
  inferSides,
  summarizeEvent,
} from '../utils/gameEvents'

/* ------------------------------------------------------------------ *
 * DiceRollCard — inline game-event card showing a real dice roll
 * (DM function calling Phase 1: dice rolling).
 *
 * Renders the roll label, die faces, modifier breakdown, total, DC,
 * and pass/fail — colour-coded by outcome. Supports advantage/
 * disadvantage (shows both rolls). Dismissible.
 *
 * UI polish: when `animate` is true, the raw die value(s) tumble through
 * random faces for ~480ms before settling on the true result. Opt-in so
 * tests render the final value deterministically.
 * ------------------------------------------------------------------ */

interface DiceRollCardProps {
  event: GameEvent
  onDismiss?: () => void
  /** Enable the dice-tumble flourish (opt-in; defaults to the settled value). */
  animate?: boolean
}

export default function DiceRollCard({ event, onDismiss, animate = false }: DiceRollCardProps) {
  const data = event.data
  const rolls = data.rolls ?? []
  const modifier = data.modifier ?? 0
  const total = data.total ?? 0
  const dc = data.dc
  const success = data.success
  const advantage = data.advantage ?? false
  const disadvantage = data.disadvantage ?? false

  const sides = useMemo(() => inferSides(event), [event])
  // Crit/advantage logic always uses the REAL rolls so labels are correct.
  const critHit = useMemo(() => isCriticalHit(rolls, sides), [rolls, sides])
  const critMiss = useMemo(() => isCriticalMiss(rolls, sides), [rolls, sides])
  const colors = useMemo(
    () => getRollColor(success, critHit, critMiss),
    [success, critHit, critMiss],
  )
  const advInfo = useMemo(
    () => formatAdvantage(rolls, advantage, disadvantage),
    [rolls, advantage, disadvantage],
  )
  const summary = useMemo(() => summarizeEvent(event), [event])
  const successLabel = getSuccessLabel(success, dc)

  // Dice-tumble flourish: displayed digits flicker, then settle to the truth.
  const { rolls: displayRolls, isTumbling } = useDiceTumbleRolls(rolls, { sides, animate })
  // Keep the breakdown arithmetically consistent while tumbling, but always
  // settle on the stored total.
  const displayTotal = isTumbling
    ? displayRolls.reduce((a, b) => a + b, 0) + modifier
    : total
  const rollStr = formatRollResult(displayRolls, modifier, displayTotal)

  const showAdvantage = (advantage || disadvantage) && rolls.length >= 2
  const critLabel = critHit ? '✦ CRITICAL!' : critMiss ? '✦ CRITICAL FAIL!' : ''

  return (
    <div
      className={`rounded-lg border ${colors.border} ${colors.bg} p-3 mt-2 animate-scale-in`}
      role="status"
      aria-label={summary}
    >
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className="text-sm font-bold text-parchment-100 flex items-center gap-1.5">
          <span aria-hidden className={isTumbling ? 'inline-block animate-chevron-down' : ''}>🎲</span>
          {event.label}
        </span>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="text-parchment-500 hover:text-parchment-200 text-xs px-1.5 py-0.5 rounded transition-colors"
            aria-label="Dismiss dice roll"
            title="Dismiss"
          >
            ✕
          </button>
        )}
      </div>

      {/* Roll result */}
      <div className="flex items-baseline gap-2 flex-wrap">
        {showAdvantage ? (
          <span className={`text-lg font-mono font-bold ${colors.text}`}>
            {displayRolls.map((r, i) => (
              <span key={i} className={i === advInfo.struckIndex ? 'line-through opacity-50' : ''}>
                {i > 0 ? ' / ' : ''}{r}
              </span>
            ))}
            {modifier !== 0 && (
              <span className="text-sm opacity-80">
                {' '}{modifier > 0 ? '+' : '−'}{Math.abs(modifier)}
              </span>
            )}
            {' = '}
            <span className="text-xl">{displayTotal}</span>
          </span>
        ) : (
          <span className={`text-lg font-mono font-bold ${colors.text}`}>
            {rollStr}
          </span>
        )}
      </div>

      {/* DC + success label */}
      {(dc !== null && dc !== undefined) && (
        <div className={`text-sm font-semibold mt-1 ${colors.text}`}>
          DC {dc} → {successLabel}
        </div>
      )}

      {/* Advantage/disadvantage tag */}
      {showAdvantage && (
        <div className="text-xs text-parchment-400 mt-0.5">
          {advantage ? '▲ Advantage' : '▼ Disadvantage'}
        </div>
      )}

      {/* Critical label */}
      {critLabel && (
        <div className={`text-sm font-bold mt-1 ${critHit ? 'text-amber-300' : 'text-blood-300'}`}>
          {critLabel}
        </div>
      )}
    </div>
  )
}
