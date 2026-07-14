/**
 * Pure formatting helpers for the structured **skill-check resolution** data
 * returned by the DM after a freeform player action (DSPy tutorial pattern #5).
 *
 * The backend (`_resolve_skill_check` in `api/game.py`) returns a dict shaped:
 *
 * ```ts
 * {
 *   success: boolean,
 *   degree: 'great_success' | 'success' | 'partial_success' | 'failure' | 'critical_failure',
 *   stat_changes: Record<string, number>,   // e.g. { hp: -5, gold: 10 }
 *   items_gained: string[],                  // e.g. ['Healing Potion', 'Rusty Key']
 *   experience_gained: number,
 *   narrative_notes: string,
 * }
 * ```
 *
 * These helpers turn that raw payload into display-ready strings and metadata
 * (label / icon / colour) so the UI layer stays free of formatting logic —
 * keeping the resolution logic trivially unit-testable.
 */

/** Canonical resolution degrees, ordered best → worst. */
export const DEGREE_ORDER = [
  'great_success',
  'success',
  'partial_success',
  'failure',
  'critical_failure',
] as const

export type SkillCheckDegree = (typeof DEGREE_ORDER)[number]

/** Human-readable metadata for each resolution degree. */
export interface DegreeMeta {
  label: string
  icon: string
  /** Tailwind text colour class. */
  textClass: string
  /** Tailwind border/background classes for the badge. */
  badgeClass: string
}

const DEGREE_META: Record<SkillCheckDegree, DegreeMeta> = {
  great_success: {
    label: 'Great Success',
    icon: '🌟',
    textClass: 'text-amber-300',
    badgeClass: 'bg-amber-900/50 border-amber-600 text-amber-200',
  },
  success: {
    label: 'Success',
    icon: '✅',
    textClass: 'text-emerald-300',
    badgeClass: 'bg-emerald-900/50 border-emerald-600 text-emerald-200',
  },
  partial_success: {
    label: 'Partial Success',
    icon: '⚡',
    textClass: 'text-yellow-300',
    badgeClass: 'bg-yellow-900/50 border-yellow-600 text-yellow-200',
  },
  failure: {
    label: 'Failure',
    icon: '❌',
    textClass: 'text-blood-300',
    badgeClass: 'bg-blood-900/50 border-blood-600 text-blood-200',
  },
  critical_failure: {
    label: 'Critical Failure',
    icon: '💀',
    textClass: 'text-red-400',
    badgeClass: 'bg-red-950/60 border-red-800 text-red-300',
  },
}

/** A safe fallback for unrecognised / missing degrees. */
const UNKNOWN_DEGREE: DegreeMeta = {
  label: 'Resolved',
  icon: '🎲',
  textClass: 'text-parchment-300',
  badgeClass: 'bg-parchment-800 border-parchment-600 text-parchment-300',
}

/** Normalise a raw degree string (spaces/hyphens → underscores, lowercased). */
function canonicalDegreeKey(raw: string): string {
  return raw.trim().toLowerCase().replace(/[\s-]+/g, '_')
}

/** Whether `raw` is one of the known canonical degrees. */
function isKnownDegree(raw: string | undefined | null): boolean {
  if (!raw) return false
  return (DEGREE_ORDER as readonly string[]).includes(canonicalDegreeKey(raw))
}

/**
 * Canonicalise an arbitrary degree string into a known `SkillCheckDegree`.
 * Unknown / empty values default to `'failure'` (the safest game-logic
 * default). Use `getDegreeMeta()` when you need display metadata, since it
 * distinguishes "unknown" from "failure".
 */
export function normalizeDegree(raw: string | undefined | null): SkillCheckDegree {
  if (!raw || !isKnownDegree(raw)) return 'failure'
  return canonicalDegreeKey(raw) as SkillCheckDegree
}

/** Look up display metadata (label / icon / colour) for a degree string. */
export function getDegreeMeta(raw: string | undefined | null): DegreeMeta {
  if (!raw || !isKnownDegree(raw)) return UNKNOWN_DEGREE
  return DEGREE_META[canonicalDegreeKey(raw) as SkillCheckDegree]
}

/** A human-readable short label, e.g. "Great Success". */
export function degreeLabel(raw: string | undefined | null): string {
  return getDegreeMeta(raw).label
}

/**
 * Friendly display name for common stat-change keys returned by the resolver.
 * Unknown keys are title-cased so they still render sensibly.
 */
const STAT_LABELS: Record<string, string> = {
  hp: 'HP',
  max_hp: 'Max HP',
  temp_hp: 'Temp HP',
  gold: 'Gold',
  ac: 'Armor Class',
  strength: 'Strength',
  dexterity: 'Dexterity',
  constitution: 'Constitution',
  intelligence: 'Intelligence',
  wisdom: 'Wisdom',
  charisma: 'Charisma',
  inspiration: 'Inspiration',
}

function titleCase(key: string): string {
  return key
    .replace(/[_\s]+/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

/** A human-readable name for a stat-change key. */
export function statLabel(key: string): string {
  return STAT_LABELS[key] ?? titleCase(key)
}

/** A single formatted stat-change line, e.g. "Gold +10" or "HP −5". */
export function formatStatChange(key: string, delta: number): string {
  const sign = delta < 0 ? '−' : '+' // U+2212 minus for nicer typography
  // Use the raw value for negative deltas so we don't double the minus sign.
  return `${statLabel(key)} ${sign}${Math.abs(delta)}`
}

/** Produce sorted, human-readable stat-change lines from a resolution payload. */
export function formatStatChanges(
  statChanges: Record<string, number> | undefined | null,
): string[] {
  if (!statChanges) return []
  return Object.entries(statChanges)
    .filter(([, v]) => typeof v === 'number' && v !== 0)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => formatStatChange(k, v))
}

export interface SkillCheckResolutionData {
  success?: boolean
  degree?: string
  stat_changes?: Record<string, number>
  items_gained?: string[]
  experience_gained?: number
  narrative_notes?: string
}

/**
 * Determine whether a resolution payload has *any* meaningful content worth
 * showing. An empty `{}` (the no-LLM / failure case) renders nothing.
 *
 * A great/success/partial-success degree is always worth surfacing (something
 * positive happened). A bare failure/critical-failure is only worth showing
 * when it carries additional content (notes, stat changes, items, XP) — a
 * failure card saying only "❌ Failure" adds nothing.
 */
export function hasResolution(res: SkillCheckResolutionData | undefined | null): boolean {
  if (!res || typeof res !== 'object') return false
  const hasXp = typeof res.experience_gained === 'number' && res.experience_gained > 0
  const hasItems = Array.isArray(res.items_gained) && res.items_gained.length > 0
  const hasStats =
    typeof res.stat_changes === 'object' && Object.keys(res.stat_changes ?? {}).length > 0
  const hasNotes = typeof res.narrative_notes === 'string' && res.narrative_notes.trim().length > 0
  const positiveDegree = isKnownDegree(res.degree) && normalizeDegree(res.degree) !== 'failure'
  return hasXp || hasItems || hasStats || hasNotes || positiveDegree
}

/**
 * One-line summary of the mechanical outcome, e.g.
 * "✅ Success · +50 XP · Gold +10".
 *
 * Useful for compact/toast-style displays and as a screen-reader label.
 */
export function summarizeResolution(
  res: SkillCheckResolutionData | undefined | null,
): string {
  if (!hasResolution(res)) return ''
  const parts: string[] = []
  const meta = getDegreeMeta(res?.degree)
  parts.push(`${meta.icon} ${meta.label}`)

  const xp = res?.experience_gained
  if (typeof xp === 'number' && xp > 0) parts.push(`+${xp} XP`)

  const items = res?.items_gained
  if (Array.isArray(items) && items.length > 0) {
    parts.push(`+${items.length} item${items.length > 1 ? 's' : ''}`)
  }

  return parts.join(' · ')
}
