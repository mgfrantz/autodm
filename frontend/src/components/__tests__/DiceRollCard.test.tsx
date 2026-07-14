import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import DiceRollCard from '../DiceRollCard'
import type { GameEvent } from '../../types'

/* ------------------------------------------------------------------ *
 * Unit tests for DiceRollCard — the inline game-event card showing a
 * real dice roll with modifier, total, DC, and outcome.
 * ------------------------------------------------------------------ */

function diceEvent(overrides: Partial<GameEvent['data']> = {}, label = 'Attack'): GameEvent {
  return {
    type: 'dice_roll',
    label,
    data: {
      rolls: [15],
      modifier: 3,
      total: 18,
      ...overrides,
    },
    timestamp: '',
  }
}

describe('DiceRollCard', () => {
  it('renders the label and roll result for a basic roll', () => {
    render(<DiceRollCard event={diceEvent({}, 'Perception Check')} />)
    expect(screen.getByText('🎲')).toBeTruthy()
    expect(screen.getByText('Perception Check')).toBeTruthy()
    expect(screen.getByText('15 + 3 = 18')).toBeTruthy()
  })

  it('shows DC and success label when DC is present', () => {
    render(
      <DiceRollCard
        event={diceEvent({ dc: 15, success: true })}
      />,
    )
    expect(screen.getByText(/DC 15/)).toBeTruthy()
    expect(screen.getByText(/✅ Success/)).toBeTruthy()
  })

  it('shows failure label for a failed roll', () => {
    render(
      <DiceRollCard
        event={diceEvent({ rolls: [5], total: 8, dc: 15, success: false }, 'Investigation')}
      />,
    )
    expect(screen.getByText(/❌ Failure/)).toBeTruthy()
  })

  it('shows both rolls for advantage', () => {
    render(
      <DiceRollCard
        event={diceEvent({
          rolls: [12, 18], total: 21, advantage: true,
        }, 'Attack')}
      />,
    )
    expect(screen.getByText('▲ Advantage')).toBeTruthy()
  })

  it('shows critical hit label for natural 20', () => {
    render(
      <DiceRollCard
        event={diceEvent({
          rolls: [20], total: 23, dc: 15, success: true,
        }, 'Attack')}
      />,
    )
    expect(screen.getByText(/CRITICAL!/)).toBeTruthy()
  })

  it('shows critical miss label for natural 1', () => {
    render(
      <DiceRollCard
        event={diceEvent({
          rolls: [1], total: 4, dc: 15, success: false,
        }, 'Attack')}
      />,
    )
    expect(screen.getByText(/CRITICAL FAIL!/)).toBeTruthy()
  })

  it('fires onDismiss when the ✕ button is clicked', () => {
    const onDismiss = vi.fn()
    render(<DiceRollCard event={diceEvent()} onDismiss={onDismiss} />)
    const btn = screen.getByLabelText('Dismiss dice roll')
    fireEvent.click(btn)
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })
})
