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
} from '../gameEvents'
import type { GameEvent } from '../../types'

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
