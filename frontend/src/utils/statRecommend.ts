/**
 * Class-appropriate ability-score recommendations for character creation.
 *
 * Uses the D&D 5e **Standard Array** (15, 14, 13, 12, 10, 8 — total 72) and
 * distributes it across the six abilities according to each class's
 * optimisation priority.  The total point budget is enforced so that a
 * generated build always lands exactly at 72.
 */

export const STAT_BUDGET = 72

/** The canonical 5e standard array, highest first. */
export const STANDARD_ARRAY = [15, 14, 13, 12, 10, 8] as const

export type AbilityKey =
  | 'strength'
  | 'dexterity'
  | 'constitution'
  | 'intelligence'
  | 'wisdom'
  | 'charisma'

export type AbilityScores = Record<AbilityKey, number>

/**
 * Per-class ability priority (highest → lowest).
 *
 * Sourced from common 5e optimisation guidance; the primary stat is what the
 * class casts/attacks with, followed by survivability (CON/DEX) and then
 * tertiary utility stats.  "Fighter" defaults to a melee (STR) build.
 */
export const CLASS_STAT_BUILD: Record<string, AbilityKey[]> = {
  Barbarian: ['strength', 'constitution', 'dexterity', 'wisdom', 'charisma', 'intelligence'],
  Bard: ['charisma', 'dexterity', 'constitution', 'wisdom', 'intelligence', 'strength'],
  Cleric: ['wisdom', 'strength', 'constitution', 'charisma', 'dexterity', 'intelligence'],
  Druid: ['wisdom', 'constitution', 'dexterity', 'strength', 'intelligence', 'charisma'],
  Fighter: ['strength', 'constitution', 'dexterity', 'wisdom', 'charisma', 'intelligence'],
  Monk: ['dexterity', 'wisdom', 'constitution', 'strength', 'intelligence', 'charisma'],
  Paladin: ['strength', 'charisma', 'constitution', 'wisdom', 'dexterity', 'intelligence'],
  Ranger: ['dexterity', 'wisdom', 'constitution', 'strength', 'intelligence', 'charisma'],
  Rogue: ['dexterity', 'constitution', 'charisma', 'wisdom', 'intelligence', 'strength'],
  Sorcerer: ['charisma', 'constitution', 'dexterity', 'wisdom', 'intelligence', 'strength'],
  Warlock: ['charisma', 'constitution', 'dexterity', 'wisdom', 'intelligence', 'strength'],
  Wizard: ['intelligence', 'constitution', 'dexterity', 'wisdom', 'charisma', 'strength'],
}

/** Fallback priority if a class isn't in the map (balanced spread). */
const DEFAULT_BUILD: AbilityKey[] = [
  'strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma',
]

/**
 * Distribute the standard array across the six abilities for a given class.
 * The returned scores always sum to exactly `STAT_BUDGET`.
 *
 * Each ability in the class's priority list receives the next-highest value
 * from the standard array, so the class's primary stat gets 15, the next 14,
 * and so on down to 8.
 */
export function recommendStats(charClass: string): AbilityScores {
  const order = CLASS_STAT_BUILD[charClass] ?? DEFAULT_BUILD
  const scores: AbilityScores = {
    strength: 8,
    dexterity: 8,
    constitution: 8,
    intelligence: 8,
    wisdom: 8,
    charisma: 8,
  }
  STANDARD_ARRAY.forEach((value, i) => {
    scores[order[i]] = value
  })
  return scores
}

/** Sum of all six ability scores. */
export function totalPoints(scores: AbilityScores): number {
  return Object.values(scores).reduce((sum, v) => sum + v, 0)
}

/** A build is "over budget" when it exceeds the standard-array total. */
export function isOverBudget(scores: AbilityScores): boolean {
  return totalPoints(scores) > STAT_BUDGET
}
