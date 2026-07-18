import { useMemo } from 'react'
import type { GameEvent } from '../types'
import { useDiceTumble } from '../hooks/useDiceTumble'
import {
  attackSummary,
  damageTypeColor,
  hpBarData,
} from '../utils/gameEvents'

/* ------------------------------------------------------------------ *
 * AttackCard — inline game-event card showing a combat attack result
 * (DM function calling Phase 2: combat resolution).
 *
 * Renders the attacker→target flow, to-hit roll vs AC, hit/miss/crit
 * outcome, damage amount + type, and the target's HP bar. Colour-coded
 * by outcome (crit = gold, hit = green, miss = red). Dismissible.
 *
 * UI polish: when `animate` is true, the to-hit total tumbles like a
 * rolling d20, and the HP bar shakes when damage lands.
 * ------------------------------------------------------------------ */

interface AttackCardProps {
  event: GameEvent
  onDismiss?: () => void
  /** Enable the dice-tumble flourish on the to-hit total (opt-in). */
  animate?: boolean
}

export default function AttackCard({ event, onDismiss, animate = false }: AttackCardProps) {
  const d = event.data
  const hit = d.hit ?? false
  const critical = d.critical ?? false
  const criticalMiss = d.critical_miss ?? false
  const dmgType = d.damage_type ?? 'slashing'

  const summary = useMemo(
    () => attackSummary(d.attacker, d.target, d.attack_total, d.ac,
      hit, critical, criticalMiss, d.damage, d.damage_type),
    [d.attacker, d.target, d.attack_total, d.ac, hit, critical, criticalMiss, d.damage, d.damage_type],
  )
  const dmgColors = useMemo(() => damageTypeColor(dmgType), [dmgType])
  const hp = useMemo(
    () => hpBarData(d.target_remaining_hp, d.target_max_hp),
    [d.target_remaining_hp, d.target_max_hp],
  )

  // Dice-tumble flourish on the to-hit total (settles to the real value).
  const { value: displayTotal } = useDiceTumble(d.attack_total ?? 0, { sides: 20, animate })

  // Determine border/bg colour by outcome
  let borderColor = 'border-parchment-700/50'
  let bgColor = 'bg-parchment-900/30'
  let textColor = 'text-parchment-200'
  if (critical) {
    borderColor = 'border-amber-500/60'; bgColor = 'bg-amber-900/30'; textColor = 'text-amber-200'
  } else if (hit) {
    borderColor = 'border-emerald-600/50'; bgColor = 'bg-emerald-900/30'; textColor = 'text-emerald-200'
  } else {
    borderColor = 'border-blood-600/50'; bgColor = 'bg-blood-900/30'; textColor = 'text-blood-200'
  }

  // Shake the HP bar only when the attack actually dealt damage.
  const hpShake = hit && (d.damage ?? 0) > 0 ? 'animate-shake' : ''

  return (
    <div
      className={`rounded-lg border ${borderColor} ${bgColor} p-3 mt-2 animate-scale-in`}
      role="status"
      aria-label={summary}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className={`text-sm font-bold ${textColor} flex items-center gap-1.5`}>
          <span aria-hidden>⚔️</span>
          {d.attacker ?? 'Unknown'} → {d.target ?? 'Unknown'}
        </span>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="text-parchment-500 hover:text-parchment-200 text-xs px-1.5 py-0.5 rounded transition-colors"
            aria-label="Dismiss attack result"
            title="Dismiss"
          >
            ✕
          </button>
        )}
      </div>

      {/* Outcome badge */}
      <div className="flex items-center gap-2 flex-wrap mb-2">
        {critical && (
          <span className="text-sm font-bold text-amber-300">✦ CRITICAL HIT!</span>
        )}
        {criticalMiss && (
          <span className="text-sm font-bold text-blood-300">✦ CRITICAL MISS!</span>
        )}
        {!critical && !criticalMiss && (
          <span className={`text-sm font-bold ${hit ? 'text-emerald-300' : 'text-blood-300'}`}>
            {hit ? '✅ HIT' : '❌ MISS'}
          </span>
        )}
        <span className={`text-sm font-mono ${textColor}`}>
          {displayTotal} vs AC {d.ac ?? '?'}
        </span>
      </div>

      {/* Damage breakdown (only on hit) */}
      {hit && d.damage !== undefined && (
        <div className={`text-sm mb-2 ${dmgColors.text}`}>
          💥 {d.damage} {dmgType} damage
        </div>
      )}

      {/* HP bar */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-parchment-400 min-w-fit">{d.target ?? 'Target'} HP</span>
        <div className={`flex-1 h-2.5 rounded-full bg-parchment-800/60 overflow-hidden ${hpShake}`} role="progressbar" aria-valuenow={hp.percentage} aria-valuemin={0} aria-valuemax={100}>
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
