import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import ConditionCard from '../ConditionCard'
import type { GameEvent } from '../../types'

function condEvent(
  overrides: Partial<GameEvent['data']> = {},
  label = '🌀 Player is now poisoned (3 rounds)',
): GameEvent {
  return {
    type: 'condition_applied',
    label,
    data: {
      operation: 'applied',
      condition: 'poisoned',
      target: 'Player',
      target_type: 'player',
      duration: 3,
      description: 'Disadvantage on attack rolls.',
      success: true,
      message: '',
      ...overrides,
    },
    timestamp: '',
  }
}

describe('ConditionCard', () => {
  it('renders an applied condition with name and target', () => {
    render(<ConditionCard event={condEvent()} />)
    expect(screen.getByText(/poisoned/)).toBeTruthy()
    expect(screen.getByText(/Player/)).toBeTruthy()
  })

  it('shows the condition icon', () => {
    render(<ConditionCard event={condEvent()} />)
    expect(screen.getByText('🤢')).toBeTruthy()
  })

  it('shows the duration badge', () => {
    render(<ConditionCard event={condEvent()} />)
    expect(screen.getByText(/3 rounds/)).toBeTruthy()
  })

  it('shows Permanent for conditions with no duration', () => {
    render(<ConditionCard event={condEvent({ duration: null },
      '🌀 Player is now blinded')} />)
    expect(screen.getByText(/Permanent/)).toBeTruthy()
  })

  it('shows the operation badge for applied conditions', () => {
    render(<ConditionCard event={condEvent()} />)
    expect(screen.getByText(/Condition Applied/)).toBeTruthy()
  })

  it('shows the mechanical effect description', () => {
    render(<ConditionCard event={condEvent()} />)
    expect(screen.getByText(/Disadvantage/)).toBeTruthy()
  })

  it('renders a removed condition with the removed badge', () => {
    render(<ConditionCard event={condEvent({
      operation: 'removed', duration: undefined,
    }, '🌀 Player is no longer poisoned')} />)
    expect(screen.getByText(/Condition Removed/)).toBeTruthy()
  })

  it('renders a combatant target with the combatant label', () => {
    render(<ConditionCard event={condEvent({
      target: 'Goblin Brute', target_type: 'combatant',
    })} />)
    expect(screen.getByText(/Goblin Brute/)).toBeTruthy()
    expect(screen.getByText(/combatant/)).toBeTruthy()
  })

  it('renders a muted failed card with the reason', () => {
    render(<ConditionCard event={condEvent({
      success: false, message: 'Unknown condition: bogus',
    }, '🌀 bogus (failed)')} />)
    expect(screen.getByText(/failed/)).toBeTruthy()
    expect(screen.getByText(/Unknown condition/)).toBeTruthy()
  })

  it('uses the correct icon for different conditions', () => {
    const { rerender } = render(<ConditionCard event={condEvent({
      condition: 'stunned',
    }, '🌀 Stunned')} />)
    expect(screen.getByText('💫')).toBeTruthy()
    rerender(<ConditionCard event={condEvent({
      condition: 'paralyzed',
    }, '🌀 Paralyzed')} />)
    expect(screen.getByText('⚡')).toBeTruthy()
  })

  it('fires onDismiss when ✕ is clicked', () => {
    const onDismiss = vi.fn()
    render(<ConditionCard event={condEvent()} onDismiss={onDismiss} />)
    fireEvent.click(screen.getByLabelText('Dismiss condition event'))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('renders without a dismiss button when no callback is given', () => {
    render(<ConditionCard event={condEvent()} />)
    expect(screen.queryByLabelText('Dismiss condition event')).toBeNull()
  })
})
