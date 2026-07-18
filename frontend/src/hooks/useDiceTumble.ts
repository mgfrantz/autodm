import { useEffect, useRef, useState } from 'react'
import {
  DICE_TUMBLE_DURATION_MS,
  prefersReducedMotion,
  randomDieValue,
  shouldTumble,
  tumbleComplete,
} from '../utils/diceTumble'

export interface UseDiceTumbleOptions {
  /** Die faces used for the tumbling flicker (e.g. 20 for a d20). */
  sides?: number
  /** How long to tumble before settling, in ms. */
  durationMs?: number
}

export interface UseDiceTumbleResult {
  /** The value to render right now (random during tumble, final afterwards). */
  value: number
  /** True while the tumble is still in progress. */
  isTumbling: boolean
}

/**
 * Tumble a numeric die value for ~`durationMs` on mount, then settle to
 * `finalValue`. The result is a quick "rolling die" flourish before the true
 * roll snaps into place.
 *
 * - Respects `prefers-reduced-motion`: returns the final value immediately.
 * - If the value/sides aren't tumblable, returns the final value immediately.
 * - Re-runs the tumble only when `finalValue` changes identity.
 *
 * Kept deliberately framework-thin: all the maths lives in
 * `utils/diceTumble.ts` (pure, unit-tested).
 */
export function useDiceTumble(
  finalValue: number,
  { sides = 20, durationMs = DICE_TUMBLE_DURATION_MS, animate = false }: UseDiceTumbleOptions & { animate?: boolean } = {},
): UseDiceTumbleResult {
  const reduced = prefersReducedMotion()
  const tumblable = animate && !reduced && shouldTumble(finalValue, sides, reduced)

  // Lazy initialisers give a clean first paint: already tumbling if applicable.
  const [display, setDisplay] = useState<number>(() =>
    tumblable ? randomDieValue(sides) : finalValue,
  )
  const [isTumbling, setIsTumbling] = useState<boolean>(tumblable)

  const rafRef = useRef<number | null>(null)
  const startRef = useRef<number | null>(null)

  useEffect(() => {
    if (!tumblable) {
      setDisplay(finalValue)
      setIsTumbling(false)
      return
    }

    startRef.current = null
    setIsTumbling(true)

    const tick = (now: number) => {
      if (startRef.current === null) startRef.current = now
      const elapsed = now - startRef.current
      if (tumbleComplete(elapsed, durationMs)) {
        setDisplay(finalValue)
        setIsTumbling(false)
        return
      }
      setDisplay(randomDieValue(sides))
      rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    // Re-tumble only when the inputs meaningfully change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finalValue, sides, durationMs, tumblable])

  return { value: display, isTumbling }
}

/**
 * Tumble an array of die values (e.g. a d20, or both dice of an
 * advantage/disadvantage roll) together, then settle on `finalRolls`.
 *
 * - Only animates when `animate` is true (opt-in from the real app; tests and
 *   SSR render the final values immediately).
 * - Respects `prefers-reduced-motion`.
 *
 * Returns the values to render right now and whether the tumble is ongoing.
 */
export function useDiceTumbleRolls(
  finalRolls: number[],
  {
    sides = 20,
    durationMs = DICE_TUMBLE_DURATION_MS,
    animate = false,
  }: UseDiceTumbleOptions & { animate?: boolean } = {},
): { rolls: number[]; isTumbling: boolean } {
  const reduced = prefersReducedMotion()
  const active =
    animate &&
    !reduced &&
    finalRolls.length > 0 &&
    finalRolls.every((r) => shouldTumble(r, sides, reduced))

  const [display, setDisplay] = useState<number[]>(() =>
    active ? finalRolls.map(() => randomDieValue(sides)) : finalRolls,
  )
  const [isTumbling, setIsTumbling] = useState<boolean>(active)

  const rafRef = useRef<number | null>(null)
  const startRef = useRef<number | null>(null)

  useEffect(() => {
    if (!active) {
      setDisplay(finalRolls)
      setIsTumbling(false)
      return
    }

    startRef.current = null
    setIsTumbling(true)

    const tick = (now: number) => {
      if (startRef.current === null) startRef.current = now
      const elapsed = now - startRef.current
      if (tumbleComplete(elapsed, durationMs)) {
        setDisplay(finalRolls)
        setIsTumbling(false)
        return
      }
      setDisplay(finalRolls.map(() => randomDieValue(sides)))
      rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, durationMs, sides, finalRolls.join(',')])

  return { rolls: display, isTumbling }
}
