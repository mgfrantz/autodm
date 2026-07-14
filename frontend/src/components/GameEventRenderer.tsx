import type { GameEvent } from '../types'
import DiceRollCard from './DiceRollCard'
import CheckPromptCard from './CheckPromptCard'

/* ------------------------------------------------------------------ *
 * GameEventRenderer — dispatches a GameEvent to the correct component.
 *
 * - dice_roll → <DiceRollCard />
 * - check_prompt → <CheckPromptCard />
 * - unknown types → null (forward-compatible with Phase 2+)
 * ------------------------------------------------------------------ */

interface GameEventRendererProps {
  event: GameEvent
  gameId: number
  onDismiss?: () => void
}

export default function GameEventRenderer({ event, gameId, onDismiss }: GameEventRendererProps) {
  switch (event.type) {
    case 'dice_roll':
      return <DiceRollCard event={event} onDismiss={onDismiss} />
    case 'check_prompt':
      return <CheckPromptCard event={event} gameId={gameId} onDismiss={onDismiss} />
    default:
      // Unknown event type — forward-compatible, render nothing
      return null
  }
}
