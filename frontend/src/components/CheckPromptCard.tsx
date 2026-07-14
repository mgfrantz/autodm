import { useState } from 'react'
import type { GameEvent } from '../types'
import { resolveCheck } from '../stores/api'
import DiceRollCard from './DiceRollCard'
import { summarizeEvent } from '../utils/gameEvents'

/* ------------------------------------------------------------------ *
 * CheckPromptCard — inline game-event card showing a DM-requested
 * check prompt with a roll button (DM function calling Phase 1:
 * check prompts).
 *
 * The DM emits a check_prompt event asking the player to roll. The
 * player clicks the 🎲 Roll button → calls resolveCheck() → shows
 * the result as a DiceRollCard.
 * ------------------------------------------------------------------ */

interface CheckPromptCardProps {
  event: GameEvent
  gameId: number
  onDismiss?: () => void
}

export default function CheckPromptCard({ event, gameId, onDismiss }: CheckPromptCardProps) {
  const [resultEvent, setResultEvent] = useState<GameEvent | null>(null)
  const [rolling, setRolling] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const skill = event.data.skill ?? 'Unknown'
  const dc = event.data.dc
  const reason = event.data.reason

  const handleRoll = async () => {
    setRolling(true)
    setError(null)
    try {
      const result = await resolveCheck(gameId, skill, dc ?? undefined)
      setResultEvent(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Roll failed')
    } finally {
      setRolling(false)
    }
  }

  // Once we have a result, render a DiceRollCard instead
  if (resultEvent) {
    return <DiceRollCard event={resultEvent} onDismiss={onDismiss} />
  }

  const summary = summarizeEvent(event)

  return (
    <div
      className="rounded-lg border border-arcane-600/50 bg-arcane-900/30 p-3 mt-2 animate-scale-in"
      role="status"
      aria-label={summary}
    >
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className="text-sm font-bold text-parchment-100 flex items-center gap-1.5">
          <span aria-hidden>📜</span>
          The DM calls for a roll!
        </span>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="text-parchment-500 hover:text-parchment-200 text-xs px-1.5 py-0.5 rounded transition-colors"
            aria-label="Dismiss check prompt"
            title="Dismiss"
          >
            ✕
          </button>
        )}
      </div>

      <div className="text-sm text-parchment-200 mb-2">
        <span className="font-semibold">Roll a {skill} check</span>
        {dc !== null && dc !== undefined && (
          <span className="text-parchment-400"> (DC {dc})</span>
        )}
      </div>

      {reason && (
        <p className="text-xs text-parchment-400 italic mb-2">{reason}</p>
      )}

      {error && (
        <p className="text-xs text-blood-300 mb-2">{error}</p>
      )}

      <button
        type="button"
        onClick={handleRoll}
        disabled={rolling}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-arcane-700/60 hover:bg-arcane-600/60 text-parchment-100 text-sm font-semibold border border-arcane-500/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <span aria-hidden>🎲</span>
        {rolling ? 'Rolling...' : 'Roll'}
      </button>
    </div>
  )
}
