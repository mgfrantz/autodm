import { describe, it, expect } from 'vitest'
import {
  DICE_TUMBLE_DURATION_MS,
  MIN_TUMBLE_SIDES,
  clampSides,
  randomDieValue,
  tumbleProgress,
  tumbleComplete,
  shouldTumble,
  prefersReducedMotion,
} from '../diceTumble'

/* ------------------------------------------------------------------ *
 * Unit tests for the dice-tumble pure helpers (Game Event UI polish).
 * ------------------------------------------------------------------ */

describe('clampSides', () => {
  it('returns MIN_TUMBLE_SIDES for values below the minimum', () => {
    expect(clampSides(0)).toBe(MIN_TUMBLE_SIDES)
    expect(clampSides(1)).toBe(MIN_TUMBLE_SIDES)
    expect(clampSides(-5)).toBe(MIN_TUMBLE_SIDES)
  })

  it('clamps NaN to the minimum', () => {
    expect(clampSides(NaN)).toBe(MIN_TUMBLE_SIDES)
    expect(clampSides(Infinity)).toBe(MIN_TUMBLE_SIDES)
  })

  it('floors fractional sides', () => {
    expect(clampSides(20.9)).toBe(20)
    expect(clampSides(6.4)).toBe(6)
  })

  it('returns valid integer sides unchanged', () => {
    expect(clampSides(20)).toBe(20)
    expect(clampSides(6)).toBe(6)
    expect(clampSides(100)).toBe(100)
  })
})

describe('randomDieValue', () => {
  it('always returns values within [1, sides]', () => {
    for (let i = 0; i < 500; i++) {
      const v = randomDieValue(20)
      expect(v).toBeGreaterThanOrEqual(1)
      expect(v).toBeLessThanOrEqual(20)
    }
  })

  it('respects an injectable RNG for deterministic output', () => {
    expect(randomDieValue(20, () => 0)).toBe(1)
    expect(randomDieValue(20, () => 0.999)).toBe(20)
    expect(randomDieValue(6, () => 0.5)).toBe(4) // floor(0.5*6)+1 = 3+1
    expect(randomDieValue(4, () => 0.25)).toBe(2) // floor(1)+1
  })

  it('clamps sub-minimum sides before rolling', () => {
    // sides=1 → clamped to d2 → floor(0.5*2)+1 = 2
    expect(randomDieValue(1, () => 0.5)).toBe(2)
    expect(randomDieValue(1, () => 0)).toBe(1)
  })
})

describe('tumbleProgress', () => {
  it('is 0 at the start and 1 at/after the duration', () => {
    expect(tumbleProgress(0)).toBe(0)
    expect(tumbleProgress(DICE_TUMBLE_DURATION_MS)).toBe(1)
    expect(tumbleProgress(DICE_TUMBLE_DURATION_MS * 2)).toBe(1)
  })

  it('is 0.5 at the midpoint', () => {
    expect(tumbleProgress(DICE_TUMBLE_DURATION_MS / 2)).toBeCloseTo(0.5)
  })

  it('treats negative elapsed as 0', () => {
    expect(tumbleProgress(-100)).toBe(0)
  })

  it('treats a non-positive duration as already complete (1)', () => {
    expect(tumbleProgress(0, 0)).toBe(1)
    expect(tumbleProgress(100, -5)).toBe(1)
  })

  it('clamps a custom duration', () => {
    expect(tumbleProgress(50, 100)).toBe(0.5)
    expect(tumbleProgress(100, 100)).toBe(1)
  })
})

describe('tumbleComplete', () => {
  it('is true once elapsed reaches the duration', () => {
    expect(tumbleComplete(DICE_TUMBLE_DURATION_MS)).toBe(true)
    expect(tumbleComplete(DICE_TUMBLE_DURATION_MS * 3)).toBe(true)
  })

  it('is false before the duration elapses', () => {
    expect(tumbleComplete(0)).toBe(false)
    expect(tumbleComplete(DICE_TUMBLE_DURATION_MS - 1)).toBe(false)
  })

  it('respects a custom duration', () => {
    expect(tumbleComplete(500, 500)).toBe(true)
    expect(tumbleComplete(499, 500)).toBe(false)
  })
})

describe('shouldTumble', () => {
  it('is true for a valid integer value on a real die without reduced motion', () => {
    expect(shouldTumble(10, 20, false)).toBe(true)
    expect(shouldTumble(1, 6, false)).toBe(true)
  })

  it('is false when reduced motion is requested', () => {
    expect(shouldTumble(10, 20, true)).toBe(false)
  })

  it('is false for non-finite or non-integer values', () => {
    expect(shouldTumble(NaN, 20, false)).toBe(false)
    expect(shouldTumble(Infinity, 20, false)).toBe(false)
    expect(shouldTumble(10.5, 20, false)).toBe(false)
  })

  it('is false when the die cannot change face (sides < 2)', () => {
    expect(shouldTumble(10, 1, false)).toBe(false)
    expect(shouldTumble(10, 0, false)).toBe(false)
  })
})

describe('prefersReducedMotion', () => {
  it('returns true when matchMedia reports a match', () => {
    expect(prefersReducedMotion({ matchMedia: () => ({ matches: true }) })).toBe(true)
  })

  it('returns false when matchMedia reports no match', () => {
    expect(prefersReducedMotion({ matchMedia: () => ({ matches: false }) })).toBe(false)
  })

  it('returns false when matchMedia is unavailable', () => {
    expect(prefersReducedMotion({})).toBe(false)
    expect(prefersReducedMotion(null)).toBe(false)
    expect(prefersReducedMotion(undefined)).toBe(false)
  })

  it('returns false (never throws) if matchMedia itself throws', () => {
    const win = { matchMedia: () => { throw new Error('not implemented') } }
    expect(prefersReducedMotion(win)).toBe(false)
  })
})
