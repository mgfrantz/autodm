import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import DamageCard from '../DamageCard'
import type { GameEvent } from '../../types'

function damageEvent(overrides: Partial<GameEvent['data']> = {}, label = 'Fire damage'): GameEvent {
  return {
    type: 'damage',
    label,
    data: {
      target: 'Goblin',
      amount: 5,
      damage_type: 'fire',
      target_remaining_hp: 7,
      target_max_hp: 12,
      ...overrides,
    },
    timestamp: '',
  }
}

describe('DamageCard', () => {
  it('renders target, amount, and damage type', () => {
    render(<DamageCard event={damageEvent()} />)
    expect(screen.getByText(/Goblin takes 5 fire damage/)).toBeTruthy()
  })

  it('renders the HP bar with remaining/max', () => {
    render(<DamageCard event={damageEvent({ target_remaining_hp: 7, target_max_hp: 12 })} />)
    expect(screen.getByText('7 / 12')).toBeTruthy()
  })

  it('shows Defeated when target is at 0 HP', () => {
    render(<DamageCard event={damageEvent({
      target_remaining_hp: 0, target_max_hp: 12, amount: 12,
    })} />)
    expect(screen.getByText(/Defeated/)).toBeTruthy()
  })

  it('does not show Defeated when target has HP remaining', () => {
    render(<DamageCard event={damageEvent({ target_remaining_hp: 7 })} />)
    expect(screen.queryByText(/Defeated/)).toBeNull()
  })

  it('fires onDismiss when ✕ is clicked', () => {
    const onDismiss = vi.fn()
    render(<DamageCard event={damageEvent()} onDismiss={onDismiss} />)
    fireEvent.click(screen.getByLabelText('Dismiss damage result'))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })
})
