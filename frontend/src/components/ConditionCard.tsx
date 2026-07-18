import { useMemo } from 'react'
import type { GameEvent } from '../types'
import {
  conditionColor,
  conditionIcon,
  conditionSummary,
} from '../utils/gameEvents'

/* ------------------------------------------------------------------ *
 * ConditionCard — inline game-event card showing a condition change
 * (DM function calling Phase 5: condition application).
 *
 * Renders the condition name + icon, the target creature, the operation
 * (applied / removed), a duration indicator (rounds remaining or
 * permanent), and the mechanical effect description. Colour-coded by
 * severity tier (severe=red, moderate=amber, mild=parchment). Failed
 * operations render a muted card with the reason. Dismissible.
 * ------------------------------------------------------------------ */

interface ConditionCardProps {
  event: GameEvent
  onDismiss?: () => void
}

export default function ConditionCard({ event, onDismiss }: ConditionCardProps) {
  const d = event.data
  const success = d.success ?? true
  const operation = (d.operation ?? 'applied').toLowerCase()
  const condition = d.condition ?? 'unknown'
  const target = d.target ?? 'Target'
  const targetType = d.target_type ?? 'player'
  const duration = d.duration
  const description = d.description

  const summary = useMemo(
    () => conditionSummary(
      d.operation, d.condition, d.target, d.duration, d.success, d.message,
    ),
    [d.operation, d.condition, d.target, d.duration, d.success, d.message],
  )
  const colors = useMemo(() => conditionColor(condition), [condition])
  const icon = useMemo(() => conditionIcon(condition), [condition])

  // Operation badge (verb + glyph).
  const opBadge = useMemo(() => {
    switch (operation) {
      case 'applied': return { glyph: '➕', label: 'Condition Applied', tone: 'text-amber-300' }
      case 'removed': return { glyph: '➖', label: 'Condition Removed', tone: 'text-emerald-300' }
      default:        return { glyph: '🌀', label: operation, tone: 'text-parchment-300' }
    }
  }, [operation])

  // Duration label.
  const durationLabel = useMemo(() => {
    if (operation === 'removed') return null
    if (duration === null || duration === undefined) return 'Permanent'
    return `${duration} round${duration === 1 ? '' : 's'}`
  }, [duration, operation])

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
            {condition}
            <span className="text-parchment-500 font-normal">— {opBadge.label.toLowerCase()} failed</span>
          </span>
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              className="text-parchment-500 hover:text-parchment-200 text-xs px-1.5 py-0.5 rounded transition-colors"
              aria-label="Dismiss condition event"
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
      {/* Header: condition icon + name + target */}
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className={`text-sm font-bold ${colors.text} flex items-center gap-1.5`}>
          <span aria-hidden>{icon}</span>
          <span className="capitalize">{condition}</span>
          <span className="text-parchment-400 font-normal text-xs">
            → {target}
            {targetType === 'combatant' && (
              <span className="text-parchment-500"> (combatant)</span>
            )}
          </span>
        </span>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="text-parchment-500 hover:text-parchment-200 text-xs px-1.5 py-0.5 rounded transition-colors"
            aria-label="Dismiss condition event"
            title="Dismiss"
          >
            ✕
          </button>
        )}
      </div>

      {/* Operation + duration */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`text-sm font-semibold ${opBadge.tone} flex items-center gap-1`}>
          <span aria-hidden>{opBadge.glyph}</span>
          {opBadge.label}
        </span>

        {/* Duration badge */}
        {durationLabel && (
          <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${
            durationLabel === 'Permanent'
              ? 'bg-parchment-800/40 text-parchment-500'
              : 'bg-parchment-800/60 text-parchment-300'
          }`}>
            ⏱ {durationLabel}
          </span>
        )}
      </div>

      {/* Mechanical effect description */}
      {description && (
        <div className="text-xs text-parchment-400 mt-1.5 leading-relaxed">
          {description}
        </div>
      )}
    </div>
  )
}
