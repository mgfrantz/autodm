import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import GameEventRenderer from '../GameEventRenderer'
import type { GameEvent } from '../../types'

/* ------------------------------------------------------------------ *
 * Unit tests for GameEventRenderer — focused on the collapsed-by-default
 * UI polish: compact one-line summary, expand toggle, and dismiss.
 * ------------------------------------------------------------------ */

function diceEvent(): GameEvent {
  return {
    type: 'dice_roll',
    label: 'Perception Check',
    data: { rolls: [15], modifier: 3, total: 18 },
    timestamp: '',
  }
}

describe('GameEventRenderer — expanded (default)', () => {
  it('renders the full card when not collapsed', () => {
    render(<GameEventRenderer event={diceEvent()} gameId={1} />)
    expect(screen.getByText('Perception Check')).toBeTruthy()
    expect(screen.getByText('15 + 3 = 18')).toBeTruthy()
    // No collapsed affordance in expanded mode
    expect(screen.queryByLabelText(/Expand event/)).toBeNull()
  })

  it('forwards animate to dice cards without breaking render', () => {
    render(<GameEventRenderer event={diceEvent()} gameId={1} animate />)
    expect(screen.getByText('Perception Check')).toBeTruthy()
  })
})

describe('GameEventRenderer — collapsed', () => {
  it('renders a compact one-line summary instead of the full card', () => {
    render(
      <GameEventRenderer event={diceEvent()} gameId={1} collapsed onToggleCollapse={vi.fn()} />,
    )
    // Summary text is present...
    expect(screen.getByText(/Perception Check/)).toBeTruthy()
    // ...but the full breakdown line is not rendered as its own node.
    expect(screen.queryByText('15 + 3 = 18')).toBeNull()
    // Expand affordance exists.
    expect(screen.getByLabelText(/Expand event/)).toBeTruthy()
  })

  it('calls onToggleCollapse when the collapsed line is clicked', () => {
    const onToggle = vi.fn()
    render(<GameEventRenderer event={diceEvent()} gameId={1} collapsed onToggleCollapse={onToggle} />)
    fireEvent.click(screen.getByLabelText(/Expand event/))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('fires onDismiss from the collapsed line', () => {
    const onDismiss = vi.fn()
    render(<GameEventRenderer event={diceEvent()} gameId={1} collapsed onDismiss={onDismiss} />)
    fireEvent.click(screen.getByLabelText('Dismiss event'))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('renders a collapsed loot summary with its item name', () => {
    const event: GameEvent = {
      type: 'loot',
      label: '🎒 Loot',
      data: {
        operation: 'gained',
        item_name: 'Health Potion',
        item_type: 'potion',
        quantity: 1,
        success: true,
        source: 'Goblin',
      },
      timestamp: '',
    }
    render(<GameEventRenderer event={event} gameId={1} collapsed />)
    expect(screen.getByText(/Health Potion/)).toBeTruthy()
  })

  it('renders a collapsed attack summary', () => {
    const event: GameEvent = {
      type: 'attack',
      label: '⚔️ Attack',
      data: { attacker: 'Hero', target: 'Goblin', attack_total: 18, ac: 14, hit: true, damage: 8, damage_type: 'slashing' },
      timestamp: '',
    }
    render(<GameEventRenderer event={event} gameId={1} collapsed />)
    expect(screen.getByText(/Goblin/)).toBeTruthy()
  })
})
