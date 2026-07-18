import { describe, it, expect, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useDiceTumble, useDiceTumbleRolls } from '../useDiceTumble'

/* ------------------------------------------------------------------ *
 * Unit tests for the useDiceTumble / useDiceTumbleRolls hooks
 * (Game Event UI polish). Covers the deterministic (non-tumbling) paths
 * plus a settle check; the underlying maths is covered by diceTumble.test.ts.
 * ------------------------------------------------------------------ */

afterEach(() => {
  // jsdom has no matchMedia by default; remove any stub a test may have added.
  // @ts-expect-error matchMedia is not part of jsdom's window type
  delete window.matchMedia
})

describe('useDiceTumble', () => {
  it('returns the final value immediately when animate is false', () => {
    const { result } = renderHook(() => useDiceTumble(15, { sides: 20, animate: false }))
    expect(result.current.value).toBe(15)
    expect(result.current.isTumbling).toBe(false)
  })

  it('returns the final value immediately when reduced motion is requested', () => {
    // @ts-expect-error matchMedia is not part of jsdom's window type
    window.matchMedia = (q: string) => ({ matches: q.includes('reduce') })
    const { result } = renderHook(() => useDiceTumble(15, { sides: 20, animate: true }))
    expect(result.current.value).toBe(15)
    expect(result.current.isTumbling).toBe(false)
  })

  it('does not tumble when the value is non-tumblable (sub-min sides)', () => {
    const { result } = renderHook(() => useDiceTumble(15, { sides: 1, animate: true }))
    expect(result.current.value).toBe(15)
    expect(result.current.isTumbling).toBe(false)
  })

  it('settles to the final value after tumbling when animate is true', async () => {
    // duration 0 → the first animation frame settles immediately.
    const { result } = renderHook(() =>
      useDiceTumble(15, { sides: 20, durationMs: 0, animate: true }),
    )
    // Wait on the settle flag, not the value: the initial flicker frame sets
    // `value` to a random face, and ~1/20 of the time that random value
    // equals the final value (15). Waiting on `value` would resolve against
    // that pre-settle render where `isTumbling` is still true (a real flake
    // under full-suite rAF load). `isTumbling` only flips to false in the
    // same batched tick that commits the final value, so it is the correct
    // synchronization point.
    await waitFor(() => expect(result.current.isTumbling).toBe(false))
    expect(result.current.value).toBe(15)
  })
})

describe('useDiceTumbleRolls', () => {
  it('returns the final rolls when animate is false', () => {
    const { result } = renderHook(() =>
      useDiceTumbleRolls([12, 18], { sides: 20, animate: false }),
    )
    expect(result.current.rolls).toEqual([12, 18])
    expect(result.current.isTumbling).toBe(false)
  })

  it('returns an empty array unchanged (nothing to tumble)', () => {
    const { result } = renderHook(() => useDiceTumbleRolls([], { sides: 20, animate: true }))
    expect(result.current.rolls).toEqual([])
    expect(result.current.isTumbling).toBe(false)
  })

  it('does not tumble if any roll is non-tumblable', () => {
    const { result } = renderHook(() =>
      useDiceTumbleRolls([12, NaN], { sides: 20, animate: true }),
    )
    expect(result.current.rolls).toEqual([12, NaN])
    expect(result.current.isTumbling).toBe(false)
  })

  it('settles to the final rolls after tumbling when animate is true', async () => {
    const { result } = renderHook(() =>
      useDiceTumbleRolls([12, 18], { sides: 20, durationMs: 0, animate: true }),
    )
    // See the single-value test above: wait on the settle flag, not the
    // (random) initial flicker values, to avoid a pre-settle resolution race.
    await waitFor(() => expect(result.current.isTumbling).toBe(false))
    expect(result.current.rolls).toEqual([12, 18])
  })
})
