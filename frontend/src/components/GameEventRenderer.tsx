import { useMemo } from 'react'
import type { GameEvent } from '../types'
import {
  eventAccent,
  eventIcon,
  summarizeEvent,
} from '../utils/gameEvents'
import DiceRollCard from './DiceRollCard'
import CheckPromptCard from './CheckPromptCard'
import AttackCard from './AttackCard'
import DamageCard from './DamageCard'
import InitiativeCard from './InitiativeCard'
import SpellCastCard from './SpellCastCard'
import LootCard from './LootCard'
import ConditionCard from './ConditionCard'
import ConcentrationCard from './ConcentrationCard'

/* ------------------------------------------------------------------ *
 * GameEventRenderer — dispatches a GameEvent to the correct component.
 *
 * - dice_roll → <DiceRollCard />
 * - check_prompt → <CheckPromptCard />
 * - attack → <AttackCard />
 * - damage → <DamageCard />
 * - initiative → <InitiativeCard />
 * - spell_cast → <SpellCastCard />
 * - loot → <LootCard />
 * - condition_applied → <ConditionCard />
 * - concentration → <ConcentrationCard />
 * - unknown types → null (forward-compatible with future phases)
 *
 * UI polish:
 * - `animate` forwards to dice/attack cards to enable the dice-tumble flourish.
 * - `collapsed` renders a compact one-line summary (click to re-expand) instead
 *   of the full card, so old events don't crowd the log.
 * ------------------------------------------------------------------ */

interface GameEventRendererProps {
  event: GameEvent
  gameId: number
  onDismiss?: () => void
  /** Enable the dice-tumble animation on dice/attack cards (opt-in). */
  animate?: boolean
  /** When true, render a compact one-line summary instead of the full card. */
  collapsed?: boolean
  /** Called when the user clicks a collapsed event to expand it (or vice-versa). */
  onToggleCollapse?: () => void
}

export default function GameEventRenderer({
  event,
  gameId,
  onDismiss,
  animate = false,
  collapsed = false,
  onToggleCollapse,
}: GameEventRendererProps) {
  // Collapsed view — compact, accent-coloured one-line summary.
  if (collapsed) {
    return <CollapsedEventLine event={event} onDismiss={onDismiss} onToggleCollapse={onToggleCollapse} />
  }

  switch (event.type) {
    case 'dice_roll':
      return <DiceRollCard event={event} onDismiss={onDismiss} animate={animate} />
    case 'check_prompt':
      return <CheckPromptCard event={event} gameId={gameId} onDismiss={onDismiss} />
    case 'attack':
      return <AttackCard event={event} onDismiss={onDismiss} animate={animate} />
    case 'damage':
      return <DamageCard event={event} onDismiss={onDismiss} />
    case 'initiative':
      return <InitiativeCard event={event} onDismiss={onDismiss} />
    case 'spell_cast':
      return <SpellCastCard event={event} onDismiss={onDismiss} />
    case 'loot':
      return <LootCard event={event} onDismiss={onDismiss} />
    case 'condition_applied':
      return <ConditionCard event={event} onDismiss={onDismiss} />
    case 'concentration':
      return <ConcentrationCard event={event} onDismiss={onDismiss} />
    default:
      // Unknown event type — forward-compatible, render nothing
      return null
  }
}

/* ------------------------------------------------------------------ *
 * CollapsedEventLine — the compact one-line summary shown when an event
 * is collapsed. Click anywhere on the line (or the chevron) to expand.
 * ------------------------------------------------------------------ */

interface CollapsedEventLineProps {
  event: GameEvent
  onDismiss?: () => void
  onToggleCollapse?: () => void
}

function CollapsedEventLine({ event, onDismiss, onToggleCollapse }: CollapsedEventLineProps) {
  const accent = useMemo(() => eventAccent(event), [event])
  const icon = useMemo(() => eventIcon(event), [event])
  const summary = useMemo(() => summarizeEvent(event), [event])

  return (
    <div
      className={`rounded-lg border ${accent.border} ${accent.bg} px-3 py-1.5 mt-2 flex items-center gap-2 text-xs animate-scale-in`}
      role="status"
      aria-label={summary}
    >
      <button
        type="button"
        onClick={onToggleCollapse}
        className="flex items-center gap-1.5 min-w-0 flex-1 text-left hover:opacity-90 transition-opacity"
        aria-label={`Expand event: ${summary}`}
        title="Expand"
      >
        <span aria-hidden className="shrink-0">{icon}</span>
        <span className={`truncate font-medium ${accent.text}`}>{summary}</span>
        <span aria-hidden className="shrink-0 text-parchment-500">▾</span>
      </button>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="text-parchment-500 hover:text-parchment-200 px-1 rounded transition-colors shrink-0"
          aria-label="Dismiss event"
          title="Dismiss"
        >
          ✕
        </button>
      )}
    </div>
  )
}
