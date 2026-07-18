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
  spellSchoolColor,
  spellLevelLabel,
  spellCastSummary,
  spellAoeSummary,
  itemRarityColor,
  lootSummary,
  lootIcon,
  conditionColor,
  conditionIcon,
  conditionSummary,
  concentrationColor,
  concentrationIcon,
  concentrationSummary,
  eventIcon,
  eventAccent,
  shouldCollapse,
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

  it('appends saved note when madeSave is true', () => {
    const s = damageSummary('Goblin', 6, 'fire', 7, 12, true)
    expect(s).toContain('(saved — half)')
  })

  it('does not append saved note when madeSave is false', () => {
    const s = damageSummary('Goblin', 12, 'fire', 7, 12, false)
    expect(s).not.toContain('saved')
  })

  it('does not append saved note when madeSave is undefined', () => {
    const s = damageSummary('Goblin', 5, 'fire', 7, 12)
    expect(s).not.toContain('saved')
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

// ==========================================================================
// Phase 3: Spell event helpers
// ==========================================================================

describe('spellSchoolColor', () => {
  it('returns orange colours for evocation', () => {
    const c = spellSchoolColor('evocation')
    expect(c.text).toContain('orange')
    expect(c.border).toContain('orange')
  })

  it('returns necromancy colours (not dark-green literal)', () => {
    const c = spellSchoolColor('necromancy')
    expect(c.text).toContain('emerald')
  })

  it('is case-insensitive', () => {
    const c = spellSchoolColor('ILLUSION')
    expect(c.text).toContain('violet')
  })

  it('returns distinct colours for all eight schools', () => {
    const schools = [
      'abjuration', 'conjuration', 'divination', 'enchantment',
      'evocation', 'illusion', 'necromancy', 'transmutation',
    ]
    const texts = schools.map((s) => spellSchoolColor(s).text)
    expect(new Set(texts).size).toBe(8)
  })

  it('returns neutral colours for unknown / undefined school', () => {
    const c = spellSchoolColor(undefined)
    expect(c.text).toContain('parchment')
    const c2 = spellSchoolColor('not-a-school')
    expect(c2.text).toContain('parchment')
  })
})

describe('spellLevelLabel', () => {
  it('returns "cantrip" for level 0', () => {
    expect(spellLevelLabel(0)).toBe('cantrip')
    expect(spellLevelLabel(undefined)).toBe('cantrip')
  })

  it('returns "level N" for leveled spells', () => {
    expect(spellLevelLabel(1)).toBe('level 1')
    expect(spellLevelLabel(3)).toBe('level 3')
    expect(spellLevelLabel(9)).toBe('level 9')
  })
})

describe('spellCastSummary', () => {
  it('summarizes an attack-roll hit with damage', () => {
    const s = spellCastSummary('Fire Bolt', 0, 'evocation', true, true, null,
      10, 0, 'fire', false, 'Goblin', '')
    expect(s).toContain('Fire Bolt')
    expect(s).toContain('cantrip')
    expect(s).toContain('10 fire damage')
    expect(s).toContain('hit')
  })

  it('summarizes a miss', () => {
    const s = spellCastSummary('Fire Bolt', 0, 'evocation', true, false, null,
      0, 0, 'fire', false, 'Goblin', '')
    expect(s).toContain('miss')
  })

  it('summarizes a save spell with half damage', () => {
    const s = spellCastSummary('Sacred Flame', 0, 'evocation', true, null, true,
      4, 0, 'radiant', true, 'Goblin', '')
    expect(s).toContain('4 radiant damage')
    expect(s).toContain('(half)')
    expect(s).toContain('target saved')
  })

  it('summarizes a healing spell', () => {
    const s = spellCastSummary('Cure Wounds', 1, 'evocation', true, null, null,
      0, 8, '', false, 'Lyra', '')
    expect(s).toContain('+8 HP')
    expect(s).toContain('Lyra')
  })

  it('summarizes a failed cast', () => {
    const s = spellCastSummary('Fireball', 3, 'evocation', false, null, null,
      0, 0, 'fire', false, '', 'No spell slots available')
    expect(s).toContain('FAILED')
    expect(s).toContain('No spell slots available')
  })

  it('handles undefined inputs gracefully', () => {
    const s = spellCastSummary(undefined, undefined, undefined, true,
      null, null, 0, 0, undefined, false, undefined, undefined)
    expect(s).toContain('Unknown spell')
  })
})

describe('summarizeEvent for spell_cast', () => {
  it('summarizes a spell cast hit', () => {
    const event: GameEvent = {
      type: 'spell_cast',
      label: '🔮 Fire Bolt',
      data: {
        spell_name: 'Fire Bolt', spell_id: 'fire_bolt', level: 0,
        school: 'evocation', slot_level: null, success: true,
        hit: true, attack_total: 18, damage: 10, damage_type: 'fire',
        target: 'Goblin', target_remaining_hp: 2, target_max_hp: 12,
        message: '',
      },
      timestamp: '',
    }
    const s = summarizeEvent(event)
    expect(s).toContain('Fire Bolt')
    expect(s).toContain('10 fire damage')
    expect(s).toContain('hit')
  })

  it('summarizes a failed spell cast', () => {
    const event: GameEvent = {
      type: 'spell_cast',
      label: '🔮 Fireball (failed)',
      data: {
        spell_name: 'Fireball', spell_id: 'fireball', level: 3,
        school: 'evocation', slot_level: null, success: false,
        message: 'No spell slots available for Fireball',
      },
      timestamp: '',
    }
    const s = summarizeEvent(event)
    expect(s).toContain('FAILED')
    expect(s).toContain('No spell slots')
  })

  it('summarizes an AoE spell cast (is_aoe branch)', () => {
    const event: GameEvent = {
      type: 'spell_cast',
      label: '🎯 Fireball',
      data: {
        spell_name: 'Fireball', spell_id: 'fireball', level: 3,
        school: 'evocation', slot_level: 3, success: true,
        is_aoe: true, target_count: 3, total_damage: 42,
        damage_type: 'fire', save_dc: 15, save_ability: 'dex',
      },
      timestamp: '',
    }
    const s = summarizeEvent(event)
    expect(s).toContain('Fireball')
    expect(s).toContain('hits 3 targets')
    expect(s).toContain('42 fire total damage')
    expect(s).toContain('DC 15 dex')
  })
})

// ==========================================================================
// Phase 3.5b: AoE spell helpers
// ==========================================================================

describe('spellAoeSummary', () => {
  it('summarizes a multi-target AoE cast', () => {
    const s = spellAoeSummary('Fireball', 3, 'evocation', 3, 42, 'fire', 'dex', 15)
    expect(s).toContain('Fireball')
    expect(s).toContain('level 3')
    expect(s).toContain('hits 3 targets')
    expect(s).toContain('42 fire total damage')
    expect(s).toContain('DC 15 dex')
  })

  it('uses singular target for count of 1', () => {
    const s = spellAoeSummary('Shatter', 2, 'evocation', 1, 8, 'thunder', 'con', 13)
    expect(s).toContain('hits 1 target')
    expect(s).not.toContain('targets')
  })

  it('omits damage and count when zero/missing', () => {
    const s = spellAoeSummary('Stinking Cloud', 3, 'conjuration', 0, 0, '', 'con', 14)
    expect(s).not.toContain('hits')
    expect(s).not.toContain('total damage')
    expect(s).toContain('DC 14')
  })

  it('handles undefined inputs gracefully', () => {
    const s = spellAoeSummary(undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined)
    expect(s).toContain('Unknown spell')
  })
})

// ==========================================================================
// Phase 4: Loot helpers
// ==========================================================================

describe('itemRarityColor', () => {
  it('maps each rarity tier to a distinct colour set', () => {
    const common = itemRarityColor('common')
    const uncommon = itemRarityColor('uncommon')
    const rare = itemRarityColor('rare')
    const veryRare = itemRarityColor('very_rare')
    const legendary = itemRarityColor('legendary')
    // Each tier has its own text colour.
    expect(common.text).not.toBe(uncommon.text)
    expect(uncommon.text).not.toBe(rare.text)
    expect(rare.text).not.toBe(veryRare.text)
    expect(veryRare.text).not.toBe(legendary.text)
  })

  it('falls back to common for unknown rarity', () => {
    const fallback = itemRarityColor('not-a-rarity')
    expect(fallback).toEqual(itemRarityColor('common'))
  })

  it('handles undefined input', () => {
    expect(itemRarityColor(undefined)).toEqual(itemRarityColor('common'))
  })

  it('is case-insensitive', () => {
    expect(itemRarityColor('LEGENDARY')).toEqual(itemRarityColor('legendary'))
  })
})

describe('lootIcon', () => {
  it('returns the right emoji for each item type', () => {
    expect(lootIcon('weapon')).toBe('⚔️')
    expect(lootIcon('armor')).toBe('🛡️')
    expect(lootIcon('potion')).toBe('🧪')
    expect(lootIcon('scroll')).toBe('📜')
    expect(lootIcon('quest')).toBe('🗝️')
    expect(lootIcon('misc')).toBe('📦')
  })

  it('falls back to the backpack for unknown types', () => {
    expect(lootIcon('whatever')).toBe('🎒')
    expect(lootIcon(undefined)).toBe('🎒')
  })
})

describe('lootSummary', () => {
  it('summarizes a gained item with quantity', () => {
    const s = lootSummary('gained', 'Health Potion', 'potion', 2, true,
      null, null, null, '', '')
    expect(s).toContain('Health Potion')
    expect(s).toContain('acquired')
    expect(s).toContain('2')
    expect(s).toContain('🧪')
  })

  it('summarizes a removed item', () => {
    const s = lootSummary('removed', 'Gold Pouch', 'misc', 1, true,
      null, null, null, '', '')
    expect(s).toContain('removed')
    expect(s).toContain('Gold Pouch')
  })

  it('summarizes an equipped item with AC', () => {
    const s = lootSummary('equipped', 'Chain Mail', 'armor', 1, true,
      null, 16, null, '', '')
    expect(s).toContain('Equipped')
    expect(s).toContain('AC 16')
  })

  it('summarizes a used item with healing', () => {
    const s = lootSummary('used', 'Health Potion', 'potion', 1, true,
      7, null, null, '', '')
    expect(s).toContain('Used')
    expect(s).toContain('+7 HP')
  })

  it('summarizes a used item with uses remaining', () => {
    const s = lootSummary('used', 'Elixir', 'potion', 1, true,
      null, null, 2, '', '')
    expect(s).toContain('2 uses left')
  })

  it('summarizes a failed operation with the reason', () => {
    const s = lootSummary('gained', 'Garbage', 'misc', 1, false,
      null, null, null, 'Unknown item type', '')
    expect(s).toContain('Failed')
    expect(s).toContain('Unknown item type')
  })

  it('includes the source provenance when present', () => {
    const s = lootSummary('gained', 'Health Potion', 'potion', 1, true,
      null, null, null, '', 'Goblin loot')
    expect(s).toContain('Goblin loot')
  })

  it('handles undefined inputs gracefully', () => {
    const s = lootSummary(undefined, undefined, undefined, undefined,
      true, null, null, null, undefined, undefined)
    expect(s).toContain('Unknown item')
  })
})

describe('summarizeEvent for loot', () => {
  it('summarizes a gained item', () => {
    const event: GameEvent = {
      type: 'loot',
      label: '🎁 Health Potion acquired',
      data: {
        operation: 'gained', item_name: 'Health Potion', item_type: 'potion',
        quantity: 2, rarity: 'common', success: true,
      },
      timestamp: '',
    }
    const s = summarizeEvent(event)
    expect(s).toContain('Health Potion')
    expect(s).toContain('acquired')
  })

  it('summarizes a failed loot event', () => {
    const event: GameEvent = {
      type: 'loot',
      label: '🎒 Garbage (failed)',
      data: {
        operation: 'gained', item_name: 'Garbage', item_type: 'misc',
        success: false, message: 'Unknown item type',
      },
      timestamp: '',
    }
    const s = summarizeEvent(event)
    expect(s).toContain('Failed')
  })
})

/* ------------------------------------------------------------------ *
 * Phase 5: Condition event helpers
 * ------------------------------------------------------------------ */

describe('conditionColor', () => {
  it('returns red for severe conditions', () => {
    expect(conditionColor('paralyzed').text).toContain('rose')
    expect(conditionColor('stunned').text).toContain('rose')
    expect(conditionColor('unconscious').text).toContain('rose')
  })

  it('returns amber for moderate conditions', () => {
    expect(conditionColor('poisoned').text).toContain('amber')
    expect(conditionColor('frightened').text).toContain('amber')
    expect(conditionColor('blinded').text).toContain('amber')
  })

  it('returns indigo for invisible', () => {
    expect(conditionColor('invisible').text).toContain('indigo')
  })

  it('returns stone for deafened', () => {
    expect(conditionColor('deafened').text).toContain('stone')
  })

  it('returns parchment fallback for unknown conditions', () => {
    expect(conditionColor('bogus').text).toContain('parchment')
  })

  it('is case-insensitive', () => {
    expect(conditionColor('POISONED').text).toContain('amber')
  })

  it('handles undefined', () => {
    expect(conditionColor(undefined).text).toContain('parchment')
  })
})

describe('conditionIcon', () => {
  it('returns the correct emoji for each known condition', () => {
    expect(conditionIcon('poisoned')).toBe('🤢')
    expect(conditionIcon('stunned')).toBe('💫')
    expect(conditionIcon('paralyzed')).toBe('⚡')
    expect(conditionIcon('invisible')).toBe('👻')
    expect(conditionIcon('blinded')).toBe('🙈')
  })

  it('returns the default icon for unknown conditions', () => {
    expect(conditionIcon('bogus')).toBe('🌀')
  })

  it('is case-insensitive', () => {
    expect(conditionIcon('POISONED')).toBe('🤢')
  })

  it('handles undefined', () => {
    expect(conditionIcon(undefined)).toBe('🌀')
  })
})

describe('conditionSummary', () => {
  it('summarizes an applied condition with duration', () => {
    const s = conditionSummary('applied', 'poisoned', 'Player', 3, true, '')
    expect(s).toContain('poisoned')
    expect(s).toContain('Player')
    expect(s).toContain('3 rounds')
  })

  it('summarizes an applied permanent condition', () => {
    const s = conditionSummary('applied', 'blinded', 'Player', null, true, '')
    expect(s).toContain('permanent')
  })

  it('summarizes a singular round duration', () => {
    const s = conditionSummary('applied', 'stunned', 'Goblin', 1, true, '')
    expect(s).toContain('1 round')
    expect(s).not.toContain('1 rounds')
  })

  it('summarizes a removed condition', () => {
    const s = conditionSummary('removed', 'frightened', 'Player', null, true, '')
    expect(s).toContain('no longer')
    expect(s).toContain('frightened')
  })

  it('summarizes a failed operation', () => {
    const s = conditionSummary('applied', 'bogus', 'Player', null, false, 'Unknown condition')
    expect(s).toContain('Failed')
    expect(s).toContain('Unknown condition')
  })

  it('handles undefined inputs gracefully', () => {
    const s = conditionSummary(undefined, undefined, undefined, undefined, true, undefined)
    expect(s).toContain('unknown condition')
    expect(s).toContain('Target')
  })
})

describe('summarizeEvent for condition_applied', () => {
  it('summarizes an applied condition event', () => {
    const event: GameEvent = {
      type: 'condition_applied',
      label: '🌀 Player is now poisoned (3 rounds)',
      data: {
        operation: 'applied', condition: 'poisoned', target: 'Player',
        duration: 3, success: true,
      },
      timestamp: '',
    }
    const s = summarizeEvent(event)
    expect(s).toContain('poisoned')
    expect(s).toContain('Player')
    expect(s).toContain('3 rounds')
  })

  it('summarizes a removed condition event', () => {
    const event: GameEvent = {
      type: 'condition_applied',
      label: '🌀 Goblin is no longer stunned',
      data: {
        operation: 'removed', condition: 'stunned', target: 'Goblin',
        success: true,
      },
      timestamp: '',
    }
    const s = summarizeEvent(event)
    expect(s).toContain('no longer')
    expect(s).toContain('stunned')
  })

  it('summarizes a failed condition event', () => {
    const event: GameEvent = {
      type: 'condition_applied',
      label: '🌀 bogus (failed)',
      data: {
        operation: 'applied', condition: 'bogus', target: 'Player',
        success: false, message: 'Unknown condition',
      },
      timestamp: '',
    }
    const s = summarizeEvent(event)
    expect(s).toContain('Failed')
  })
})

describe('concentrationColor', () => {
  it('returns indigo for started', () => {
    expect(concentrationColor('started').text).toContain('indigo')
  })

  it('returns rose for broken', () => {
    expect(concentrationColor('broken').text).toContain('rose')
  })

  it('returns emerald for check_passed', () => {
    expect(concentrationColor('check_passed').text).toContain('emerald')
  })

  it('returns amber for check_failed', () => {
    expect(concentrationColor('check_failed').text).toContain('amber')
  })

  it('returns stone for ended', () => {
    expect(concentrationColor('ended').text).toContain('stone')
  })

  it('returns stone fallback for unknown operations', () => {
    expect(concentrationColor('bogus').text).toContain('stone')
  })

  it('is case-insensitive', () => {
    expect(concentrationColor('STARTED').text).toContain('indigo')
  })

  it('handles undefined', () => {
    expect(concentrationColor(undefined).text).toContain('stone')
  })
})

describe('concentrationIcon', () => {
  it('returns the correct emoji for each operation', () => {
    expect(concentrationIcon('started')).toBe('🧠')
    expect(concentrationIcon('broken')).toBe('💥')
    expect(concentrationIcon('ended')).toBe('🛑')
    expect(concentrationIcon('check_passed')).toBe('✅')
    expect(concentrationIcon('check_failed')).toBe('⚠️')
  })

  it('returns the default icon for unknown operations', () => {
    expect(concentrationIcon('bogus')).toBe('🧠')
  })

  it('is case-insensitive', () => {
    expect(concentrationIcon('BROKEN')).toBe('💥')
  })

  it('handles undefined', () => {
    expect(concentrationIcon(undefined)).toBe('🧠')
  })
})

describe('concentrationSummary', () => {
  it('summarizes a started concentration', () => {
    const s = concentrationSummary('started', 'Hold Person', '', null, null, null, true, '')
    expect(s).toContain('Hold Person')
    expect(s).toContain('concentrating')
  })

  it('summarizes a broken concentration with reason', () => {
    const s = concentrationSummary('broken', 'Bless', 'Incapacitated by stunned', null, null, null, true, '')
    expect(s).toContain('broken')
    expect(s).toContain('Bless')
    expect(s).toContain('Incapacitated')
  })

  it('summarizes an ended concentration with reason', () => {
    const s = concentrationSummary('ended', 'Shield', 'Player drops the spell', null, null, null, true, '')
    expect(s).toContain('ended')
    expect(s).toContain('Shield')
    expect(s).toContain('drops')
  })

  it('summarizes a passed concentration check', () => {
    const s = concentrationSummary('check_passed', 'Hold Person', '', 10, 10, 15, true, '')
    expect(s).toContain('held')
    expect(s).toContain('15')
    expect(s).toContain('10')
  })

  it('summarizes a failed concentration check', () => {
    const s = concentrationSummary('check_failed', 'Hold Person', '', 22, 11, 8, true, '')
    expect(s).toContain('lost')
    expect(s).toContain('22')
  })

  it('summarizes a failed operation', () => {
    const s = concentrationSummary('ended', 'Hold Person', '', null, null, null, false, 'Not concentrating')
    expect(s).toContain('Hold Person')
    expect(s).toContain('Not concentrating')
  })

  it('handles undefined inputs gracefully', () => {
    const s = concentrationSummary(undefined, undefined, undefined, undefined, undefined, undefined, true, undefined)
    expect(s).toContain('spell')
  })
})

describe('summarizeEvent for concentration', () => {
  it('summarizes a started concentration event', () => {
    const event: GameEvent = {
      type: 'concentration',
      label: '🧠 Concentrating on Hold Person',
      data: { operation: 'started', spell_name: 'Hold Person', success: true },
      timestamp: '',
    }
    const s = summarizeEvent(event)
    expect(s).toContain('Hold Person')
    expect(s).toContain('concentrating')
  })

  it('summarizes a check_passed concentration event', () => {
    const event: GameEvent = {
      type: 'concentration',
      label: '✅ Concentration held on Hold Person',
      data: {
        operation: 'check_passed', spell_name: 'Hold Person',
        damage_taken: 10, concentration_dc: 10, roll_total: 15, success: true,
      },
      timestamp: '',
    }
    const s = summarizeEvent(event)
    expect(s).toContain('held')
    expect(s).toContain('15')
  })

  it('summarizes a check_failed concentration event', () => {
    const event: GameEvent = {
      type: 'concentration',
      label: '⚠️ Concentration lost on Hold Person',
      data: {
        operation: 'check_failed', spell_name: 'Hold Person',
        damage_taken: 22, concentration_dc: 11, roll_total: 8, success: true,
      },
      timestamp: '',
    }
    const s = summarizeEvent(event)
    expect(s).toContain('lost')
  })
})

/* ------------------------------------------------------------------ *
 * UI polish helpers: eventIcon, eventAccent, shouldCollapse
 * ------------------------------------------------------------------ */

describe('eventIcon', () => {
  it('returns the expected emoji per event type', () => {
    expect(eventIcon({ type: 'dice_roll', label: '', data: {}, timestamp: '' })).toBe('🎲')
    expect(eventIcon({ type: 'check_prompt', label: '', data: {}, timestamp: '' })).toBe('📜')
    expect(eventIcon({ type: 'attack', label: '', data: {}, timestamp: '' })).toBe('⚔️')
    expect(eventIcon({ type: 'damage', label: '', data: {}, timestamp: '' })).toBe('💥')
    expect(eventIcon({ type: 'initiative', label: '', data: {}, timestamp: '' })).toBe('🏃')
    expect(eventIcon({ type: 'spell_cast', label: '', data: {}, timestamp: '' })).toBe('🔮')
    expect(eventIcon({ type: 'loot', label: '', data: {}, timestamp: '' })).toBe('🎒')
  })

  it('delegates to conditionIcon for condition_applied events', () => {
    const event: GameEvent = { type: 'condition_applied', label: '', data: { condition: 'poisoned' }, timestamp: '' }
    expect(eventIcon(event)).toBe('🤢')
  })

  it('delegates to concentrationIcon for concentration events', () => {
    const event: GameEvent = { type: 'concentration', label: '', data: { operation: 'broken' }, timestamp: '' }
    expect(eventIcon(event)).toBe('💥')
  })

  it('falls back to a bullet for unknown types', () => {
    expect(eventIcon({ type: 'unknown' as GameEvent['type'], label: '', data: {}, timestamp: '' })).toBe('•')
  })
})

describe('eventAccent', () => {
  it('returns accent colour objects for each major type', () => {
    const types: GameEvent['type'][] = [
      'dice_roll', 'check_prompt', 'attack', 'damage', 'initiative',
      'spell_cast', 'loot', 'condition_applied', 'concentration',
    ]
    for (const type of types) {
      const accent = eventAccent({ type, label: '', data: {}, timestamp: '' })
      expect(accent).toHaveProperty('text')
      expect(accent).toHaveProperty('bg')
      expect(accent).toHaveProperty('border')
      expect(typeof accent.text).toBe('string')
    }
  })

  it('colour-codes a dice roll by outcome', () => {
    const crit: GameEvent = { type: 'dice_roll', label: '', data: { rolls: [20], success: true }, timestamp: '' }
    expect(eventAccent(crit).text).toBe('text-amber-200')

    const fail: GameEvent = { type: 'dice_roll', label: '', data: { rolls: [3], success: false }, timestamp: '' }
    expect(eventAccent(fail).text).toBe('text-blood-200')
  })

  it('falls back to parchment for unknown types', () => {
    const accent = eventAccent({ type: 'unknown' as GameEvent['type'], label: '', data: {}, timestamp: '' })
    expect(accent.text).toBe('text-parchment-200')
  })
})

describe('shouldCollapse', () => {
  it('keeps the most recent N events expanded', () => {
    // 5 events, keep last 2 expanded → indices 0,1,2 collapse; 3,4 expand
    expect(shouldCollapse(0, 5, 2)).toBe(true)
    expect(shouldCollapse(2, 5, 2)).toBe(true)
    expect(shouldCollapse(3, 5, 2)).toBe(false)
    expect(shouldCollapse(4, 5, 2)).toBe(false)
  })

  it('expands everything when total <= recentCount', () => {
    expect(shouldCollapse(0, 2, 2)).toBe(false)
    expect(shouldCollapse(1, 2, 2)).toBe(false)
    expect(shouldCollapse(0, 1, 2)).toBe(false)
  })

  it('returns false when there are no events', () => {
    expect(shouldCollapse(0, 0, 2)).toBe(false)
  })

  it('with recentCount <= 0, collapses everything except the last', () => {
    expect(shouldCollapse(0, 3, 0)).toBe(true)
    expect(shouldCollapse(1, 3, 0)).toBe(true)
    expect(shouldCollapse(2, 3, 0)).toBe(false) // the last one stays expanded
  })
})
