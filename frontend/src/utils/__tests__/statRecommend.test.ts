import { describe, it, expect } from 'vitest'
import {
  recommendStats,
  totalPoints,
  isOverBudget,
  CLASS_STAT_BUILD,
  STAT_BUDGET,
  STANDARD_ARRAY,
  type AbilityKey,
} from '../statRecommend'

describe('statRecommend', () => {
  describe('recommendStats', () => {
    it('returns exactly the standard array values, no duplicates', () => {
      const result = recommendStats('Wizard')
      const values = Object.values(result).sort((a, b) => b - a)
      expect(values).toEqual([...STANDARD_ARRAY].sort((a, b) => b - a))
    })

    it('always totals exactly STAT_BUDGET (72)', () => {
      for (const charClass of Object.keys(CLASS_STAT_BUILD)) {
        expect(totalPoints(recommendStats(charClass))).toBe(STAT_BUDGET)
      }
    })

    it('assigns the primary (highest) stat for each class correctly', () => {
      const primaries: Record<string, AbilityKey> = {
        Barbarian: 'strength',
        Bard: 'charisma',
        Cleric: 'wisdom',
        Druid: 'wisdom',
        Fighter: 'strength',
        Monk: 'dexterity',
        Paladin: 'strength',
        Ranger: 'dexterity',
        Rogue: 'dexterity',
        Sorcerer: 'charisma',
        Warlock: 'charisma',
        Wizard: 'intelligence',
      }
      for (const [charClass, key] of Object.entries(primaries)) {
        const stats = recommendStats(charClass)
        const max = Math.max(...Object.values(stats))
        expect(stats[key]).toBe(max)
        expect(stats[key]).toBe(15) // standard array top value
      }
    })

    it('assigns the dump (lowest) stat = 8 for each class', () => {
      for (const charClass of Object.keys(CLASS_STAT_BUILD)) {
        const stats = recommendStats(charClass)
        const min = Math.min(...Object.values(stats))
        expect(min).toBe(8)
      }
    })

    it('covers all six abilities', () => {
      const result = recommendStats('Fighter')
      expect(Object.keys(result)).toHaveLength(6)
      expect(Object.keys(result).sort()).toEqual(
        ['charisma', 'constitution', 'dexterity', 'intelligence', 'strength', 'wisdom'],
      )
    })

    it('falls back gracefully for an unknown class', () => {
      const result = recommendStats('Necromancer')
      expect(totalPoints(result)).toBe(STAT_BUDGET)
    })

    it('gives the Fighter their expected build (STR heavy)', () => {
      const r = recommendStats('Fighter')
      expect(r.strength).toBe(15)
      expect(r.constitution).toBe(14)
      expect(r.dexterity).toBe(13)
      expect(r.intelligence).toBe(8)
    })

    it('gives the Wizard their expected build (INT heavy)', () => {
      const r = recommendStats('Wizard')
      expect(r.intelligence).toBe(15)
      expect(r.constitution).toBe(14)
      expect(r.strength).toBe(8)
    })

    it('gives the Rogue their expected build (DEX heavy)', () => {
      const r = recommendStats('Rogue')
      expect(r.dexterity).toBe(15)
      expect(r.constitution).toBe(14)
      expect(r.strength).toBe(8)
    })
  })

  describe('totalPoints / isOverBudget', () => {
    it('computes the total correctly', () => {
      expect(totalPoints({ strength: 15, dexterity: 14, constitution: 13, intelligence: 12, wisdom: 10, charisma: 8 })).toBe(72)
    })

    it('flags over-budget builds', () => {
      expect(isOverBudget({ strength: 20, dexterity: 20, constitution: 20, intelligence: 20, wisdom: 20, charisma: 20 })).toBe(true)
    })

    it('does not flag an at-budget build', () => {
      const r = recommendStats('Bard')
      expect(isOverBudget(r)).toBe(false)
    })

    it('does not flag an under-budget build', () => {
      expect(isOverBudget({ strength: 8, dexterity: 8, constitution: 8, intelligence: 8, wisdom: 8, charisma: 8 })).toBe(false)
    })
  })

  describe('CLASS_STAT_BUILD integrity', () => {
    it('every class lists all six abilities exactly once', () => {
      const allSix = (['strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma'] as AbilityKey[]).sort()
      for (const [charClass, order] of Object.entries(CLASS_STAT_BUILD)) {
        expect(order).toHaveLength(6)
        expect([...order].sort()).toEqual(allSix)
        // guard: no duplicates
        expect(charClass).toBeTruthy()
      }
    })
  })
})
