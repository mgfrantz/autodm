import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import AttackCard from '../AttackCard'
import type { GameEvent } from '../../types'

function attackEvent(overrides: Partial<GameEvent['data']> = {}, label = 'Hero → Goblin'): GameEvent {
  return {
    type: 'attack',
    label,
    data: {
      attacker: 'Hero',
      target: 'Goblin',
      attack_total: 18,
      ac: 13,
      hit: true,
      critical: false,
      critical_miss: false,
      damage: 8,
      damage_type: 'slashing',
      target_remaining_hp: 4,
      target_max_hp: 12,
      ...overrides,
    },
    timestamp: '',
  }
}

describe('AttackCard', () => {
  it('renders attacker and target for a hit', () => {
    render(<AttackCard event={attackEvent()} />)
    expect(screen.getByText(/Hero → Goblin/)).toBeTruthy()
  })

  it('shows HIT label for a normal hit', () => {
    render(<AttackCard event={attackEvent()} />)
    expect(screen.getByText(/✅ HIT/)).toBeTruthy()
  })

  it('shows attack total vs AC', () => {
    render(<AttackCard event={attackEvent()} />)
    expect(screen.getByText(/18 vs AC 13/)).toBeTruthy()
  })

  it('shows damage amount and type on hit', () => {
    render(<AttackCard event={attackEvent({ damage: 8, damage_type: 'slashing' })} />)
    expect(screen.getByText(/8 slashing damage/)).toBeTruthy()
  })

  it('shows CRITICAL HIT for a crit', () => {
    render(<AttackCard event={attackEvent({ critical: true, damage: 16 })} />)
    expect(screen.getByText(/CRITICAL HIT/)).toBeTruthy()
  })

  it('shows MISS for a miss', () => {
    render(<AttackCard event={attackEvent({
      attack_total: 8, hit: false, damage: 0,
    })} />)
    expect(screen.getByText(/❌ MISS/)).toBeTruthy()
  })

  it('shows CRITICAL MISS for a fumble', () => {
    render(<AttackCard event={attackEvent({
      hit: false, critical_miss: true, damage: 0,
    })} />)
    expect(screen.getByText(/CRITICAL MISS/)).toBeTruthy()
  })

  it('renders the HP bar with remaining/max', () => {
    render(<AttackCard event={attackEvent({ target_remaining_hp: 4, target_max_hp: 12 })} />)
    expect(screen.getByText('4 / 12')).toBeTruthy()
  })

  it('shows Defeated when target is at 0 HP', () => {
    render(<AttackCard event={attackEvent({
      target_remaining_hp: 0, target_max_hp: 12,
    })} />)
    expect(screen.getByText(/Defeated/)).toBeTruthy()
  })

  it('fires onDismiss when ✕ is clicked', () => {
    const onDismiss = vi.fn()
    render(<AttackCard event={attackEvent()} onDismiss={onDismiss} />)
    fireEvent.click(screen.getByLabelText('Dismiss attack result'))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })
})
