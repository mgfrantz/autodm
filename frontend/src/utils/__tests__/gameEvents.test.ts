import { describe, it, expect } from 'vitest'
import {
  formatRollResult,
  formatAdvantage,
  getSuccessLabel,
  getRollColor,
  isCriticalHit,
  isCriticalMiss,
  summarizeEvent,
  inferSides,
  damageTypeColor,
  hpBarData,
  attackSummary,
  damageSummary,
  initiativeSummary,
} from '../gameEvents'
import type { GameEvent, InitiativeCombatant } from '../../types'

/* ------------------------------------------------------------------ *
 * Unit tests for gameEvents utility functions (DM function calling
 * Phase 1: pure formatting helpers for dice roll events).
 * ------------------------------------------------------------------ */

describe('formatRollResult', () => {
  it('formats a single roll with positive modifier', () => {
    expect(formatRollResult([18], 3, 21)).toBe('18 + 3 = 21')
  })

  it('formats a single roll with no modifier', () => {
    expect(formatRollResult([15], 0, 15)).toBe('15 = 15')
  })

  it('formats multiple dice (damage roll)', () => {
    expect(formatRollResult([6, 4, 3], 2, 15)).toBe('6 + 4 + 3 + 2 = 15')
  })

  it('formats a negative modifier', () => {
    expect(formatRollResult([12], -2, 10)).toBe('12 - 2 = 10')
  })
})

describe('formatAdvantage', () => {
  it('returns just the roll for normal rolls', () => {
    const result = formatAdvantage([15], false, false)
    expect(result.text).toBe('15')
    expect(result.struckIndex).toBeNull()
  })

  it('shows both rolls for advantage and strikes the lower', () => {
    const result = formatAdvantage([12, 18], true, false)
    expect(result.text).toBe('12 / 18')
    expect(result.struckIndex).toBe(0) // strike the 12 (lower)
  })

  it('shows both rolls for disadvantage and strikes the higher', () => {
    const result = formatAdvantage([18, 12], false, true)
    expect(result.text).toBe('18 / 12')
    expect(result.struckIndex).toBe(0) // strike the 18 (higher)
  })

  it('handles equal rolls for advantage', () => {
    const result = formatAdvantage([15, 15], true, false)
    expect(result.text).toBe('15 / 15')
    expect(result.struckIndex).toBe(1)
  })
})

describe('getSuccessLabel', () => {
  it('returns success label for true', () => {
    expect(getSuccessLabel(true, 15)).toBe('✅ Success')
  })

  it('returns failure label for false', () => {
    expect(getSuccessLabel(false, 15)).toBe('❌ Failure')
  })

  it('returns empty string for null success', () => {
    expect(getSuccessLabel(null, 15)).toBe('')
  })

  it('returns empty string for undefined success', () => {
    expect(getSuccessLabel(undefined, 15)).toBe('')
  })
})

describe('isCriticalHit', () => {
  it('detects natural 20 on d20', () => {
    expect(isCriticalHit([20], 20)).toBe(true)
  })

  it('detects nat 20 in advantage rolls', () => {
    expect(isCriticalHit([12, 20], 20)).toBe(true)
  })

  it('returns false for non-20 rolls', () => {
    expect(isCriticalHit([19], 20)).toBe(false)
  })

  it('returns false for non-d20 dice', () => {
    expect(isCriticalHit([6], 6)).toBe(false)
  })
})

describe('isCriticalMiss', () => {
  it('detects natural 1 on d20', () => {
    expect(isCriticalMiss([1], 20)).toBe(true)
  })

  it('returns false for non-1 rolls', () => {
    expect(isCriticalMiss([2], 20)).toBe(false)
  })

  it('returns false for non-d20 dice', () => {
    expect(isCriticalMiss([1], 6)).toBe(false)
  })
})

describe('getRollColor', () => {
  it('returns gold colors for critical hit', () => {
    const colors = getRollColor(true, true, false)
    expect(colors.border).toContain('amber')
    expect(colors.text).toContain('amber')
  })

  it('returns red colors for critical miss', () => {
    const colors = getRollColor(false, false, true)
    expect(colors.border).toContain('blood')
  })

  it('returns green colors for success', () => {
    const colors = getRollColor(true, false, false)
    expect(colors.border).toContain('emerald')
  })

  it('returns red colors for failure', () => {
    const colors = getRollColor(false, false, false)
    expect(colors.border).toContain('blood')
  })

  it('returns neutral colors for no success info', () => {
    const colors = getRollColor(null, false, false)
    expect(colors.border).toContain('parchment')
  })
})

describe('summarizeEvent', () => {
  it('summarizes a dice roll event', () => {
    const event: GameEvent = {
      type: 'dice_roll',
      label: 'Perception Check',
      data: { rolls: [18], modifier: 3, total: 21, dc: 15, success: true },
      timestamp: '',
    }
    const summary = summarizeEvent(event)
    expect(summary).toContain('Perception Check')
    expect(summary).toContain('18 + 3 = 21')
    expect(summary).toContain('DC 15')
    expect(summary).toContain('Success')
  })

  it('summarizes a check prompt event', () => {
    const event: GameEvent = {
      type: 'check_prompt',
      label: 'Stealth Check',
      data: { skill: 'Stealth', dc: 12 },
      timestamp: '',
    }
    const summary = summarizeEvent(event)
    expect(summary).toContain('Stealth')
    expect(summary).toContain('DC 12')
  })
})

describe('inferSides', () => {
  it('returns 20 for a single d20 roll', () => {
    const event: GameEvent = {
      type: 'dice_roll',
      label: 'Attack',
      data: { rolls: [15], modifier: 3, total: 18 },
      timestamp: '',
    }
    expect(inferSides(event)).toBe(20)
  })

  it('returns 20 for advantage rolls (2 dice)', () => {
    const event: GameEvent = {
      type: 'dice_roll',
      label: 'Perception',
      data: { rolls: [12, 18], modifier: 3, total: 21, advantage: true },
      timestamp: '',
    }
    expect(inferSides(event)).toBe(20)
  })

  it('returns 0 for damage rolls (many dice)', () => {
    const event: GameEvent = {
      type: 'dice_roll',
      label: 'Damage',
      data: { rolls: [6, 4, 3, 5], modifier: 2, total: 20 },
      timestamp: '',
    }
    expect(inferSides(event)).toBe(0)
  })
})

// ==========================================================================
// Phase 2: Combat event helpers
// ==========================================================================

describe('damageTypeColor', () => {
  it('returns fire colours for fire damage', () => {
    const colors = damageTypeColor('fire')
    expect(colors.text).toContain('orange')
  })

  it('returns cold colours for cold damage', () => {
    const colors = damageTypeColor('cold')
    expect(colors.text).toContain('cyan')
  })

  it('is case-insensitive', () => {
    const colors = damageTypeColor('FIRE')
    expect(colors.text).toContain('orange')
  })

  it('returns neutral colours for unknown types', () => {
    const colors = damageTypeColor('radiant-explosion')
    expect(colors.text).toContain('parchment')
  })

  it('handles undefined gracefully', () => {
    const colors = damageTypeColor(undefined as unknown as string)
    expect(colors.text).toContain('parchment')
  })
})

describe('hpBarData', () => {
  it('computes percentage from remaining/max', () => {
    const hp = hpBarData(15, 30)
    expect(hp.percentage).toBe(50)
    expect(hp.isDead).toBe(false)
    expect(hp.label).toBe('15 / 30')
  })

  it('marks dead at 0 HP', () => {
    const hp = hpBarData(0, 30)
    expect(hp.isDead).toBe(true)
    expect(hp.percentage).toBe(0)
  })

  it('clamps percentage to 100 for overheal', () => {
    const hp = hpBarData(40, 30)
    expect(hp.percentage).toBe(100)
  })

  it('handles undefined values gracefully', () => {
    const hp = hpBarData(undefined, undefined)
    expect(hp.isDead).toBe(true)
  })

  it('uses blood color for low HP', () => {
    const hp = hpBarData(5, 30) // ~17%
    expect(hp.color).toContain('blood')
  })

  it('uses emerald color for high HP', () => {
    const hp = hpBarData(28, 30) // ~93%
    expect(hp.color).toContain('emerald')
  })

  it('uses blood color for dead', () => {
    const hp = hpBarData(0, 30)
    expect(hp.color).toContain('blood')
  })
})

describe('attackSummary', () => {
  it('summarizes a hit', () => {
    const s = attackSummary('Hero', 'Goblin', 18, 13, true, false, false, 8, 'slashing')
    expect(s).toContain('Hero → Goblin')
    expect(s).toContain('18 vs AC 13')
    expect(s).toContain('8 slashing')
  })

  it('summarizes a critical hit', () => {
    const s = attackSummary('Hero', 'Goblin', 25, 13, true, true, false, 16, 'slashing')
    expect(s).toContain('CRITICAL HIT!')
    expect(s).toContain('16 slashing')
  })

  it('summarizes a miss', () => {
    const s = attackSummary('Hero', 'Goblin', 8, 13, false, false, false, 0, 'slashing')
    expect(s).toContain('MISS')
  })

  it('summarizes a critical miss', () => {
    const s = attackSummary('Hero', 'Goblin', 6, 13, false, false, true, 0, 'slashing')
    expect(s).toContain('CRITICAL MISS!')
  })
})

describe('damageSummary', () => {
  it('summarizes damage with remaining HP', () => {
    const s = damageSummary('Goblin', 5, 'fire', 7, 12)
    expect(s).toContain('Goblin takes 5 fire')
    expect(s).toContain('7/12 HP')
  })

  it('shows DEFEATED at 0 HP', () => {
    const s = damageSummary('Goblin', 12, 'fire', 0, 12)
    expect(s).toContain('DEFEATED!')
  })
})

describe('initiativeSummary', () => {
  it('lists combatants in order', () => {
    const combatants: InitiativeCombatant[] = [
      { id: 'gob1', name: 'Goblin', initiative: 19, side: 'enemy' },
      { id: 'hero', name: 'Hero', initiative: 14, side: 'player' },
    ]
    const s = initiativeSummary(combatants)
    expect(s).toContain('1. Goblin (19)')
    expect(s).toContain('2. Hero (14)')
  })

  it('returns fallback for empty list', () => {
    expect(initiativeSummary([])).toBe('Initiative order')
    expect(initiativeSummary(undefined)).toBe('Initiative order')
  })
})

describe('summarizeEvent for combat types', () => {
  it('summarizes an attack event', () => {
    const event: GameEvent = {
      type: 'attack',
      label: 'Hero → Goblin',
      data: { attacker: 'Hero', target: 'Goblin', attack_total: 18, ac: 13,
        hit: true, critical: false, critical_miss: false, damage: 8,
        damage_type: 'slashing', target_remaining_hp: 4, target_max_hp: 12 },
      timestamp: '',
    }
    const s = summarizeEvent(event)
    expect(s).toContain('Hero → Goblin')
    expect(s).toContain('18 vs AC 13')
    expect(s).toContain('8 slashing')
  })

  it('summarizes a damage event', () => {
    const event: GameEvent = {
      type: 'damage',
      label: 'Fire damage',
      data: { target: 'Goblin', amount: 5, damage_type: 'fire',
        target_remaining_hp: 7, target_max_hp: 12 },
      timestamp: '',
    }
    const s = summarizeEvent(event)
    expect(s).toContain('Goblin')
    expect(s).toContain('5')
    expect(s).toContain('fire')
  })

  it('summarizes an initiative event', () => {
    const event: GameEvent = {
      type: 'initiative',
      label: 'Initiative Order',
      data: { combatants: [
        { id: 'g1', name: 'Goblin', initiative: 15, side: 'enemy' },
      ] },
      timestamp: '',
    }
    const s = summarizeEvent(event)
    expect(s).toContain('Goblin')
    expect(s).toContain('15')
  })
})
