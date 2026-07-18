import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import SpellCastCard from '../SpellCastCard'
import type { GameEvent } from '../../types'

function spellEvent(overrides: Partial<GameEvent['data']> = {}, label = '🔮 Fire Bolt'): GameEvent {
  return {
    type: 'spell_cast',
    label,
    data: {
      spell_name: 'Fire Bolt',
      spell_id: 'fire_bolt',
      level: 0,
      school: 'evocation',
      slot_level: null,
      success: true,
      attack_total: 18,
      hit: true,
      made_save: null,
      save_dc: null,
      save_ability: null,
      damage: 10,
      healing: 0,
      damage_type: 'fire',
      half_damage: false,
      target: 'Goblin',
      target_remaining_hp: 12,
      target_max_hp: 22,
      message: '',
      ...overrides,
    },
    timestamp: '',
  }
}

describe('SpellCastCard', () => {
  it('renders the spell name and school', () => {
    render(<SpellCastCard event={spellEvent()} />)
    expect(screen.getByText(/Fire Bolt/)).toBeTruthy()
    expect(screen.getByText(/evocation cantrip/i)).toBeTruthy()
  })

  it('shows HIT and attack total for an attack-roll spell', () => {
    render(<SpellCastCard event={spellEvent()} />)
    expect(screen.getByText(/✅ HIT/)).toBeTruthy()
    expect(screen.getByText(/18 vs AC/)).toBeTruthy()
  })

  it('shows MISS for a missed attack', () => {
    render(<SpellCastCard event={spellEvent({
      hit: false, attack_total: 6, damage: 0,
    })} />)
    expect(screen.getByText(/❌ MISS/)).toBeTruthy()
  })

  it('shows damage amount and type', () => {
    render(<SpellCastCard event={spellEvent({ damage: 10, damage_type: 'fire' })} />)
    expect(screen.getByText(/10 fire damage/)).toBeTruthy()
  })

  it('shows a saving-throw resolution with DC', () => {
    render(<SpellCastCard event={spellEvent({
      spell_name: 'Sacred Flame', school: 'evocation',
      hit: null, made_save: true, save_dc: 14, save_ability: 'dex',
      damage: 4, damage_type: 'radiant', half_damage: true,
      attack_total: undefined,
    })} />)
    expect(screen.getByText(/🛡️ Saved/)).toBeTruthy()
    expect(screen.getByText(/DC 14 dex/)).toBeTruthy()
    expect(screen.getByText(/4 radiant damage/)).toBeTruthy()
  })

  it('shows healing for a healing spell', () => {
    render(<SpellCastCard event={spellEvent({
      spell_name: 'Cure Wounds', level: 1, slot_level: 1,
      hit: null, attack_total: undefined, damage: 0, healing: 8,
      damage_type: '', target: 'Lyra',
      target_remaining_hp: undefined, target_max_hp: undefined,
    })} />)
    expect(screen.getByText(/\+8 HP healed/)).toBeTruthy()
  })

  it('shows the slot-level badge for a leveled spell', () => {
    render(<SpellCastCard event={spellEvent({ level: 1, slot_level: 1 })} />)
    expect(screen.getByText(/L1 slot/)).toBeTruthy()
  })

  it('shows cantrip badge when no slot expended', () => {
    render(<SpellCastCard event={spellEvent({ slot_level: null })} />)
    // Exact match: the header also contains "cantrip" via spellLevelLabel(0),
    // but the resource badge is the standalone "cantrip" span.
    expect(screen.getByText('cantrip')).toBeTruthy()
  })

  it('renders the HP bar with remaining/max for a combatant target', () => {
    render(<SpellCastCard event={spellEvent({
      target_remaining_hp: 12, target_max_hp: 22,
    })} />)
    expect(screen.getByText('12 / 22')).toBeTruthy()
  })

  it('shows Defeated when target is at 0 HP', () => {
    render(<SpellCastCard event={spellEvent({
      target_remaining_hp: 0, target_max_hp: 22,
    })} />)
    expect(screen.getByText(/Defeated/)).toBeTruthy()
  })

  it('renders a muted failed-cast card with the reason', () => {
    render(<SpellCastCard event={spellEvent({
      success: false, message: 'No spell slots available',
      damage: 0, hit: null, attack_total: undefined,
      target_remaining_hp: undefined, target_max_hp: undefined,
    }, '🔮 Fireball (failed)')} />)
    expect(screen.getByText(/cast failed/)).toBeTruthy()
    expect(screen.getByText(/No spell slots available/)).toBeTruthy()
  })

  it('fires onDismiss when ✕ is clicked', () => {
    const onDismiss = vi.fn()
    render(<SpellCastCard event={spellEvent()} onDismiss={onDismiss} />)
    fireEvent.click(screen.getByLabelText('Dismiss spell cast result'))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('renders without a dismiss button when no callback is given', () => {
    render(<SpellCastCard event={spellEvent()} />)
    expect(screen.queryByLabelText('Dismiss spell cast result')).toBeNull()
  })
})

describe('SpellCastCard — AoE mode (Phase 3.5b)', () => {
  function aoeEvent(overrides: Partial<GameEvent['data']> = {}, label = '🎯 Fireball'): GameEvent {
    return {
      type: 'spell_cast',
      label,
      data: {
        spell_name: 'Fireball',
        spell_id: 'fireball',
        level: 3,
        school: 'evocation',
        slot_level: 3,
        success: true,
        is_aoe: true,
        target_count: 3,
        total_damage: 42,
        damage_type: 'fire',
        save_dc: 15,
        save_ability: 'dex',
        message: '',
        ...overrides,
      },
      timestamp: '',
    }
  }

  it('renders the AoE spell header with school + level', () => {
    render(<SpellCastCard event={aoeEvent()} />)
    expect(screen.getByText(/Fireball/)).toBeTruthy()
    expect(screen.getByText(/evocation level 3/i)).toBeTruthy()
  })

  it('shows the target-count badge', () => {
    render(<SpellCastCard event={aoeEvent()} />)
    expect(screen.getByText(/Hits 3 targets/)).toBeTruthy()
  })

  it('shows the total-damage badge', () => {
    render(<SpellCastCard event={aoeEvent()} />)
    expect(screen.getByText(/42 fire total damage/)).toBeTruthy()
  })

  it('shows the save DC badge', () => {
    render(<SpellCastCard event={aoeEvent()} />)
    expect(screen.getByText(/DC 15 dex/)).toBeTruthy()
  })

  it('shows the slot-level badge', () => {
    render(<SpellCastCard event={aoeEvent()} />)
    expect(screen.getByText(/L3 slot/)).toBeTruthy()
  })

  it('does NOT render an HP bar in AoE mode', () => {
    render(<SpellCastCard event={aoeEvent({ target_remaining_hp: 5, target_max_hp: 12 })} />)
    expect(screen.queryByRole('progressbar')).toBeNull()
  })

  it('renders a muted failed card for a failed AoE cast', () => {
    render(<SpellCastCard event={aoeEvent({
      success: false, is_aoe: true, message: 'No spell slots available',
      total_damage: 0, target_count: 0,
    }, '🔮 Fireball (failed)')} />)
    expect(screen.getByText(/cast failed/)).toBeTruthy()
    expect(screen.getByText(/No spell slots available/)).toBeTruthy()
  })

  it('fires onDismiss in AoE mode', () => {
    const onDismiss = vi.fn()
    render(<SpellCastCard event={aoeEvent()} onDismiss={onDismiss} />)
    fireEvent.click(screen.getByLabelText('Dismiss spell cast result'))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })
})
