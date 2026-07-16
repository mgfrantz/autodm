import type { GameEvent } from '../types'
import { initiativeSummary } from '../utils/gameEvents'

/* ------------------------------------------------------------------ *
 * InitiativeCard — inline game-event card showing the initiative order
 * for a combat encounter (DM function calling Phase 2: combat resolution).
 *
 * Lists combatants in turn order with their initiative scores.
 * Player side is highlighted differently from enemy side. Dismissible.
 * ------------------------------------------------------------------ */

interface InitiativeCardProps {
  event: GameEvent
  onDismiss?: () => void
}

export default function InitiativeCard({ event, onDismiss }: InitiativeCardProps) {
  const combatants = event.data.combatants ?? []
  const summary = initiativeSummary(combatants)

  return (
    <div
      className="rounded-lg border border-arcane-600/50 bg-arcane-900/30 p-3 mt-2 animate-scale-in"
      role="status"
      aria-label={summary}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-sm font-bold text-parchment-100 flex items-center gap-1.5">
          <span aria-hidden>🎯</span>
          Initiative Order
        </span>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="text-parchment-500 hover:text-parchment-200 text-xs px-1.5 py-0.5 rounded transition-colors"
            aria-label="Dismiss initiative order"
            title="Dismiss"
          >
            ✕
          </button>
        )}
      </div>

      {/* Turn order list */}
      <ol className="space-y-1">
        {combatants.map((c, i) => (
          <li
            key={c.id ?? i}
            className={`flex items-center justify-between gap-2 text-sm px-2 py-1 rounded ${
              c.side === 'player'
                ? 'bg-emerald-900/30 text-emerald-200'
                : 'bg-blood-900/30 text-blood-200'
            } ${i === 0 ? 'ring-1 ring-amber-500/40' : ''}`}
          >
            <span className="flex items-center gap-2">
              <span className="text-xs text-parchment-500 font-mono w-4 text-right">{i + 1}.</span>
              <span className="font-semibold">{c.name}</span>
            </span>
            <span className="font-mono font-bold">{c.initiative}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}
