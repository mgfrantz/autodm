import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import LootCard from '../LootCard'
import type { GameEvent } from '../../types'

function lootEvent(
  overrides: Partial<GameEvent['data']> = {},
  label = '🎁 Health Potion acquired',
): GameEvent {
  return {
    type: 'loot',
    label,
    data: {
      operation: 'gained',
      item_name: 'Health Potion',
      item_type: 'potion',
      item_id: 'abc-123',
      quantity: 1,
      rarity: 'common',
      value: 0,
      source: '',
      healing: null,
      ac_after: null,
      uses_remaining: null,
      success: true,
      message: '',
      ...overrides,
    },
    timestamp: '',
  }
}

describe('LootCard', () => {
  it('renders a gained item with its name and type icon', () => {
    render(<LootCard event={lootEvent()} />)
    expect(screen.getByText(/Health Potion/)).toBeTruthy()
    // potion icon present
    expect(screen.getByText('🧪')).toBeTruthy()
  })

  it('shows a quantity badge when gained quantity > 1', () => {
    render(<LootCard event={lootEvent({ quantity: 2 })} />)
    expect(screen.getByText(/×2/)).toBeTruthy()
  })

  it('renders an equipped item with the AC indicator', () => {
    render(<LootCard event={lootEvent({
      operation: 'equipped', item_type: 'armor',
      item_name: 'Chain Mail', ac_after: 16, quantity: 1,
    }, '⚔️ Equipped Chain Mail')} />)
    expect(screen.getByText(/Equipped/)).toBeTruthy()
    expect(screen.getByText(/AC 16/)).toBeTruthy()
  })

  it('renders a used item with a healing indicator', () => {
    render(<LootCard event={lootEvent({
      operation: 'used', healing: 7, uses_remaining: null,
    }, '🧪 Used Health Potion')} />)
    expect(screen.getByText(/Used/)).toBeTruthy()
    expect(screen.getByText(/\+7 HP/)).toBeTruthy()
  })

  it('renders a used item with uses remaining', () => {
    render(<LootCard event={lootEvent({
      operation: 'used', healing: null, uses_remaining: 1,
    }, '🧪 Used Health Potion')} />)
    expect(screen.getByText(/1 use left/)).toBeTruthy()
  })

  it('renders a removed item', () => {
    render(<LootCard event={lootEvent({
      operation: 'removed', item_type: 'misc', item_name: 'Gold Pouch',
      quantity: 1,
    }, '📤 Gold Pouch removed')} />)
    expect(screen.getByText(/Removed/)).toBeTruthy()
    expect(screen.getByText(/Gold Pouch/)).toBeTruthy()
  })

  it('renders a muted failed card with the reason', () => {
    render(<LootCard event={lootEvent({
      success: false, message: 'Item not found',
    }, '🎒 Item (failed)')} />)
    expect(screen.getByText(/failed/)).toBeTruthy()
    expect(screen.getByText(/Item not found/)).toBeTruthy()
  })

  it('uses the correct icon for weapon and armor item types', () => {
    const { rerender } = render(<LootCard event={lootEvent({
      item_type: 'weapon', item_name: 'Longsword',
    })} />)
    expect(screen.getByText('⚔️')).toBeTruthy()
    rerender(<LootCard event={lootEvent({
      item_type: 'armor', item_name: 'Shield',
    })} />)
    expect(screen.getByText('🛡️')).toBeTruthy()
  })

  it('shows the source provenance label when present', () => {
    render(<LootCard event={lootEvent({ source: 'Goblin loot' })} />)
    expect(screen.getByText(/From: Goblin loot/)).toBeTruthy()
  })

  it('fires onDismiss when ✕ is clicked', () => {
    const onDismiss = vi.fn()
    render(<LootCard event={lootEvent()} onDismiss={onDismiss} />)
    fireEvent.click(screen.getByLabelText('Dismiss loot event'))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('renders without a dismiss button when no callback is given', () => {
    render(<LootCard event={lootEvent()} />)
    expect(screen.queryByLabelText('Dismiss loot event')).toBeNull()
  })
})
