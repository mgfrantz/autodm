import { useMemo } from 'react'
import type { GameEvent } from '../types'
import {
  damageSummary,
  damageTypeColor,
  hpBarData,
} from '../utils/gameEvents'

/* ------------------------------------------------------------------ *
 * DamageCard — inline game-event card showing direct damage applied
 * to a combatant (DM function calling Phase 2: combat resolution).
 *
 * Renders the target, damage amount + type, and an HP bar. Colour-coded
 * by damage type. Shows a death indicator at 0 HP. Dismissible.
 * ------------------------------------------------------------------ */

interface DamageCardProps {
  event: GameEvent
  onDismiss?: () => void
}

export default function DamageCard({ event, onDismiss }: DamageCardProps) {
  const d = event.data
  const dmgType = d.damage_type ?? 'slashing'
  const amount = d.amount ?? 0

  const summary = useMemo(
    () => damageSummary(d.target, amount, d.damage_type,
      d.target_remaining_hp, d.target_max_hp),
    [d.target, amount, d.damage_type, d.target_remaining_hp, d.target_max_hp],
  )
  const dmgColors = useMemo(() => damageTypeColor(dmgType), [dmgType])
  const hp = useMemo(
    () => hpBarData(d.target_remaining_hp, d.target_max_hp),
    [d.target_remaining_hp, d.target_max_hp],
  )

  return (
    <div
      className={`rounded-lg border ${dmgColors.border} ${dmgColors.bg} p-3 mt-2 animate-scale-in`}
      role="status"
      aria-label={summary}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className={`text-sm font-bold ${dmgColors.text} flex items-center gap-1.5`}>
          <span aria-hidden>💥</span>
          {d.target ?? 'Unknown'} takes {amount} {dmgType} damage
        </span>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="text-parchment-500 hover:text-parchment-200 text-xs px-1.5 py-0.5 rounded transition-colors"
            aria-label="Dismiss damage result"
            title="Dismiss"
          >
            ✕
          </button>
        )}
      </div>

      {/* HP bar */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-parchment-400 min-w-fit">HP</span>
        <div className="flex-1 h-2.5 rounded-full bg-parchment-800/60 overflow-hidden animate-shake" role="progressbar" aria-valuenow={hp.percentage} aria-valuemin={0} aria-valuemax={100}>
          <div className={`h-full ${hp.color} rounded-full transition-all duration-300`} style={{ width: `${hp.percentage}%` }} />
        </div>
        <span className={`text-xs font-mono min-w-fit ${hp.isDead ? 'text-blood-300' : 'text-parchment-300'}`}>
          {hp.label}
        </span>
      </div>

      {hp.isDead && (
        <div className="text-xs font-bold text-blood-300 mt-1">☠️ Defeated!</div>
      )}
    </div>
  )
}
