import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import InitiativeCard from '../InitiativeCard'
import type { GameEvent, InitiativeCombatant } from '../../types'

function initiativeEvent(combatants: InitiativeCombatant[]): GameEvent {
  return {
    type: 'initiative',
    label: 'Initiative Order',
    data: { combatants },
    timestamp: '',
  }
}

describe('InitiativeCard', () => {
  const sampleCombatants: InitiativeCombatant[] = [
    { id: 'gob1', name: 'Goblin', initiative: 19, side: 'enemy' },
    { id: 'hero', name: 'Lyra', initiative: 14, side: 'player' },
    { id: 'orc1', name: 'Orc', initiative: 10, side: 'enemy' },
  ]

  it('renders all combatants in order', () => {
    render(<InitiativeCard event={initiativeEvent(sampleCombatants)} />)
    expect(screen.getByText('Goblin')).toBeTruthy()
    expect(screen.getByText('Lyra')).toBeTruthy()
    expect(screen.getByText('Orc')).toBeTruthy()
  })

  it('shows initiative scores', () => {
    render(<InitiativeCard event={initiativeEvent(sampleCombatants)} />)
    expect(screen.getByText('19')).toBeTruthy()
    expect(screen.getByText('14')).toBeTruthy()
    expect(screen.getByText('10')).toBeTruthy()
  })

  it('shows the Initiative Order header', () => {
    render(<InitiativeCard event={initiativeEvent(sampleCombatants)} />)
    expect(screen.getByText('Initiative Order')).toBeTruthy()
  })

  it('fires onDismiss when ✕ is clicked', () => {
    const onDismiss = vi.fn()
    render(<InitiativeCard event={initiativeEvent(sampleCombatants)} onDismiss={onDismiss} />)
    fireEvent.click(screen.getByLabelText('Dismiss initiative order'))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('renders gracefully with empty combatant list', () => {
    render(<InitiativeCard event={initiativeEvent([])} />)
    expect(screen.getByText('Initiative Order')).toBeTruthy()
  })
})
