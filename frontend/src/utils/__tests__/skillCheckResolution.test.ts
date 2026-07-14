import { describe, it, expect } from 'vitest'
import {
  DEGREE_ORDER,
  type DegreeMeta,
  type SkillCheckDegree,
  normalizeDegree,
  getDegreeMeta,
  degreeLabel,
  statLabel,
  formatStatChange,
  formatStatChanges,
  hasResolution,
  summarizeResolution,
} from '../skillCheckResolution'

describe('skillCheckResolution', () => {
  describe('normalizeDegree', () => {
    it.each(DEGREE_ORDER)('accepts the canonical value %s', (d) => {
      expect(normalizeDegree(d)).toBe(d)
    })

    it('normalises spaces to underscores', () => {
      expect(normalizeDegree('great success')).toBe('great_success')
      expect(normalizeDegree('partial success')).toBe('partial_success')
      expect(normalizeDegree('critical failure')).toBe('critical_failure')
    })

    it('normalises hyphens to underscores and lowercases', () => {
      expect(normalizeDegree('Critical-Failure')).toBe('critical_failure')
      expect(normalizeDegree('  SUCCESS  ')).toBe('success')
    })

    it('defaults unknown / empty values to failure', () => {
      expect(normalizeDegree(undefined)).toBe('failure')
      expect(normalizeDegree(null)).toBe('failure')
      expect(normalizeDegree('')).toBe('failure')
      expect(normalizeDegree('banana')).toBe('failure')
    })
  })

  describe('getDegreeMeta / degreeLabel', () => {
    it('returns DegreeMeta with label, icon, and colour classes for each degree', () => {
      for (const d of DEGREE_ORDER) {
        const meta: DegreeMeta = getDegreeMeta(d)
        expect(meta.label.length).toBeGreaterThan(0)
        expect(meta.icon.length).toBeGreaterThan(0)
        expect(meta.textClass.length).toBeGreaterThan(0)
        expect(meta.badgeClass.length).toBeGreaterThan(0)
      }
    })

    it('distinguishes success vs failure colouring', () => {
      const successMeta = getDegreeMeta('success')
      const failureMeta = getDegreeMeta('failure')
      expect(successMeta.textClass).not.toBe(failureMeta.textClass)
      expect(successMeta.badgeClass).not.toBe(failureMeta.badgeClass)
    })

    it('falls back to a neutral meta for garbage input', () => {
      const meta = getDegreeMeta('totally-bogus')
      expect(meta.label).toBe('Resolved')
      expect(meta.icon).toBe('🎲')
    })

    it('degreeLabel returns the human label', () => {
      expect(degreeLabel('great_success')).toBe('Great Success')
      expect(degreeLabel('critical_failure')).toBe('Critical Failure')
      expect(degreeLabel('whatever')).toBe('Resolved')
    })
  })

  describe('statLabel', () => {
    it('maps known keys to friendly names', () => {
      expect(statLabel('hp')).toBe('HP')
      expect(statLabel('max_hp')).toBe('Max HP')
      expect(statLabel('gold')).toBe('Gold')
      expect(statLabel('strength')).toBe('Strength')
    })

    it('title-cases unknown keys', () => {
      expect(statLabel('arcane_surge')).toBe('Arcane Surge')
      expect(statLabel('sanity')).toBe('Sanity')
    })
  })

  describe('formatStatChange', () => {
    it('prefixes positive deltas with +', () => {
      expect(formatStatChange('gold', 10)).toBe('Gold +10')
      expect(formatStatChange('hp', 5)).toBe('HP +5')
    })

    it('uses a typographic minus for negative deltas', () => {
      expect(formatStatChange('hp', -5)).toBe('HP −5')
    })

    it('renders a zero delta literally (not filtered here)', () => {
      expect(formatStatChange('gold', 0)).toBe('Gold +0')
    })
  })

  describe('formatStatChanges', () => {
    it('formats and sorts multiple stat changes', () => {
      const out = formatStatChanges({ gold: 10, hp: -5, strength: 1 })
      // sorted alphabetically by key
      expect(out).toEqual(['Gold +10', 'HP −5', 'Strength +1'])
    })

    it('filters out zero and non-number values', () => {
      const input = { gold: 0, hp: -5, junk: 'NaN' } as unknown as Record<string, number>
      expect(formatStatChanges(input)).toEqual(['HP −5'])
    })

    it('returns [] for null / undefined / empty', () => {
      expect(formatStatChanges(undefined)).toEqual([])
      expect(formatStatChanges(null)).toEqual([])
      expect(formatStatChanges({})).toEqual([])
    })
  })

  describe('hasResolution', () => {
    it('is false for undefined / null / empty', () => {
      expect(hasResolution(undefined)).toBe(false)
      expect(hasResolution(null)).toBe(false)
      expect(hasResolution({})).toBe(false)
    })

    it('is true when success is explicitly set', () => {
      expect(hasResolution({ success: true, degree: 'success' })).toBe(true)
    })

    it('is false for a bare failure with no other content', () => {
      expect(hasResolution({ success: false, degree: 'failure' })).toBe(false)
    })

    it('is true when XP is awarded', () => {
      expect(hasResolution({ experience_gained: 50 })).toBe(true)
    })

    it('is true when items are gained', () => {
      expect(hasResolution({ items_gained: ['Potion'] })).toBe(true)
    })

    it('is true when stat changes exist', () => {
      expect(hasResolution({ stat_changes: { hp: -3 } })).toBe(true)
    })

    it('is true when narrative notes are present', () => {
      expect(hasResolution({ narrative_notes: 'You stumble.' })).toBe(true)
    })

    it('is true for a non-failure degree even without other fields', () => {
      expect(hasResolution({ degree: 'great_success' })).toBe(true)
      expect(hasResolution({ degree: 'partial_success' })).toBe(true)
    })
  })

  describe('summarizeResolution', () => {
    it('is empty for a non-resolution', () => {
      expect(summarizeResolution(undefined)).toBe('')
      expect(summarizeResolution({})).toBe('')
    })

    it('includes icon + label + XP + item count', () => {
      const s = summarizeResolution({
        degree: 'success',
        experience_gained: 50,
        items_gained: ['Potion', 'Key'],
      })
      expect(s).toContain('✅')
      expect(s).toContain('Success')
      expect(s).toContain('+50 XP')
      expect(s).toContain('+2 items')
    })

    it('uses singular "item" for one item', () => {
      const s = summarizeResolution({ degree: 'success', items_gained: ['Map'] })
      expect(s).toContain('+1 item')
    })

    it('omits XP / items when not present', () => {
      const s = summarizeResolution({ degree: 'success' })
      expect(s).toBe('✅ Success')
    })
  })

  describe('DegreeMeta shape', () => {
    it('every degree in DEGREE_ORDER has a complete meta entry', () => {
      for (const d of DEGREE_ORDER as readonly SkillCheckDegree[]) {
        const meta = getDegreeMeta(d)
        expect(meta.label).toBeTruthy()
        expect(meta.icon).toBeTruthy()
        expect(meta.textClass).toContain('text-')
        expect(meta.badgeClass).toContain('border')
      }
    })
  })
})
