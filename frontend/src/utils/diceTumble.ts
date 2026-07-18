/**
 * Pure helpers for the dice-tumble animation (Game Event UI polish).
 *
 * The DM function-calling pipeline already renders real dice rolls as inline
 * cards (Phase 1). These helpers back an optional "tumble" flourish: when a
 * DiceRollCard mounts, the raw die value flickers through random faces for
 * ~480ms before settling on the true result.
 *
 * All functions here are pure / injectable so they are trivial to unit-test
 * (per the frontend convention of keeping logic out of React components).
 */

/** Default tumble duration in milliseconds (~8 frames at 60fps feels lively). */
export const DICE_TUMBLE_DURATION_MS = 480

/** Minimum die sides worth tumbling (a d1 can't change face). */
export const MIN_TUMBLE_SIDES = 2

/** A minimal shape of `MediaQueryList` so this file stays DOM-light & testable. */
export interface MediaQueryListLike {
  matches: boolean
}

/** Clamp die sides to a sane positive integer (>= MIN_TUMBLE_SIDES). */
export function clampSides(sides: number): number {
  if (!Number.isFinite(sides) || sides < MIN_TUMBLE_SIDES) return MIN_TUMBLE_SIDES
  return Math.floor(sides)
}

/**
 * Return a random face value for a die of `sides`, in the range [1, sides].
 * Accepts an injectable RNG for deterministic tests.
 */
export function randomDieValue(sides: number, rng: () => number = Math.random): number {
  const s = clampSides(sides)
  return Math.floor(rng() * s) + 1
}

/**
 * Normalised tumble progress in [0, 1] for a given elapsed time. Clamps to the
 * endpoints so callers never overshoot. A non-positive duration is treated as
 * "already complete".
 */
export function tumbleProgress(
  elapsedMs: number,
  durationMs: number = DICE_TUMBLE_DURATION_MS,
): number {
  if (durationMs <= 0) return 1
  if (!Number.isFinite(elapsedMs) || elapsedMs <= 0) return 0
  if (elapsedMs >= durationMs) return 1
  return elapsedMs / durationMs
}

/** True once the tumble has run for at least `durationMs`. */
export function tumbleComplete(
  elapsedMs: number,
  durationMs: number = DICE_TUMBLE_DURATION_MS,
): boolean {
  return tumbleProgress(elapsedMs, durationMs) >= 1
}

/**
 * Decides whether a value should tumble at all. It should NOT when:
 *  - the user prefers reduced motion, or
 *  - the die can't change face (sides < 2), or
 *  - the value is not a finite integer.
 */
export function shouldTumble(value: number, sides: number, reducedMotion: boolean): boolean {
  if (reducedMotion) return false
  if (!Number.isFinite(value)) return false
  if (!Number.isInteger(value)) return false
  // A die that can't change face (raw sides < 2) has nothing to tumble through.
  if (sides < MIN_TUMBLE_SIDES) return false
  return true
}

/**
 * Read the user's prefers-reduced-motion setting. SSR / non-browser / missing
 * matchMedia all default to `false` (no reduced motion) so the animation can
 * run in the browser while staying safe in jsdom / tests.
 */
export function prefersReducedMotion(
  win?: { matchMedia?: (query: string) => MediaQueryListLike } | null,
): boolean {
  const w = win ?? (typeof window !== 'undefined' ? (window as Window) : null)
  if (!w || typeof w.matchMedia !== 'function') return false
  try {
    return w.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}
