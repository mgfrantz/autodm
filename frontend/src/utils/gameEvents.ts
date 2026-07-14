/**
 * Pure formatting helpers for GameEvent data (DM function calling Phase 1).
 *
 * These functions turn raw GameEvent payloads into display-ready strings and
 * metadata (labels, colors, summaries) so the UI components stay declarative
 * and the logic is trivially unit-testable.
 */
import type { GameEvent } from '../types';

/**
 * Format a roll result as a human-readable string.
 * e.g. "18 + 3 = 21" or "6 + 4 + 2 = 12" or "15 = 15"
 */
export function formatRollResult(
  rolls: number[],
  modifier: number,
  total: number,
): string {
  const rollStr = rolls.join(' + ');
  if (modifier > 0) {
    return `${rollStr} + ${modifier} = ${total}`;
  }
  if (modifier < 0) {
    return `${rollStr} - ${Math.abs(modifier)} = ${total}`;
  }
  return `${rollStr} = ${total}`;
}

/**
 * Format advantage/disadvantage display.
 * For advantage: shows both rolls, strikes through the lower one.
 * e.g. "~~12~~ 18" (advantage — took 18)
 * For disadvantage: shows both rolls, strikes through the higher one.
 * e.g. "18 ~~12~~" (disadvantage — took 12)
 * For normal: returns just the roll value.
 */
export function formatAdvantage(
  rolls: number[],
  advantage: boolean,
  disadvantage: boolean,
): { text: string; struckIndex: number | null } {
  if (!advantage && !disadvantage) {
    return { text: String(rolls[0] ?? 0), struckIndex: null };
  }
  if (rolls.length < 2) {
    return { text: String(rolls[0] ?? 0), struckIndex: null };
  }
  const [r1, r2] = rolls;
  if (advantage) {
    // Take the higher roll, strike the lower
    const struckIndex = r1 >= r2 ? 1 : 0;
    return { text: `${r1} / ${r2}`, struckIndex };
  }
  if (disadvantage) {
    // Take the lower roll, strike the higher
    const struckIndex = r1 <= r2 ? 1 : 0;
    return { text: `${r1} / ${r2}`, struckIndex };
  }
  return { text: String(rolls[0] ?? 0), struckIndex: null };
}

/**
 * Get a success/failure label string.
 * Returns "✅ Success", "❌ Failure", or "" (no DC/success info).
 */
export function getSuccessLabel(
  success: boolean | null | undefined,
  dc: number | null | undefined,
): string {
  if (success === null || success === undefined) return '';
  if (dc !== null && dc !== undefined) {
    return success ? '✅ Success' : '❌ Failure';
  }
  return success ? '✅ Success' : '❌ Failure';
}

/**
 * Get the Tailwind color classes for a dice roll based on outcome.
 * Returns border + text classes for color-coding.
 */
export function getRollColor(
  success: boolean | null | undefined,
  isCritical: boolean,
  isCriticalFail: boolean,
): { border: string; text: string; bg: string } {
  if (isCritical) {
    return {
      border: 'border-amber-500/60',
      text: 'text-amber-200',
      bg: 'bg-amber-900/30',
    };
  }
  if (isCriticalFail) {
    return {
      border: 'border-blood-600/60',
      text: 'text-blood-200',
      bg: 'bg-blood-900/30',
    };
  }
  if (success === true) {
    return {
      border: 'border-emerald-600/50',
      text: 'text-emerald-200',
      bg: 'bg-emerald-900/30',
    };
  }
  if (success === false) {
    return {
      border: 'border-blood-600/50',
      text: 'text-blood-200',
      bg: 'bg-blood-900/30',
    };
  }
  return {
    border: 'border-parchment-700/50',
    text: 'text-parchment-200',
    bg: 'bg-parchment-900/30',
  };
}

/**
 * Detect if a roll is a critical hit (natural 20 on a d20).
 */
export function isCriticalHit(rolls: number[], sides: number): boolean {
  if (sides !== 20) return false;
  // For advantage/disadvantage, check if either roll is a nat 20
  return rolls.some((r) => r === 20);
}

/**
 * Detect if a roll is a critical miss (natural 1 on a d20).
 */
export function isCriticalMiss(rolls: number[], sides: number): boolean {
  if (sides !== 20) return false;
  return rolls.some((r) => r === 1);
}

/**
 * Generate a one-line summary of a game event for aria-labels and tooltips.
 */
export function summarizeEvent(event: GameEvent): string {
  if (event.type === 'dice_roll') {
    const { rolls, modifier, total, dc, success } = event.data;
    const parts: string[] = [event.label];
    if (rolls && rolls.length > 0) {
      parts.push(formatRollResult(rolls, modifier ?? 0, total ?? 0));
    }
    if (dc !== null && dc !== undefined) {
      parts.push(`DC ${dc}`);
    }
    if (success === true) parts.push('Success');
    if (success === false) parts.push('Failure');
    return parts.join(' — ');
  }
  if (event.type === 'check_prompt') {
    const { skill, dc } = event.data;
    const parts = [`${skill} check`];
    if (dc !== null && dc !== undefined) parts.push(`DC ${dc}`);
    return parts.join(' — ');
  }
  return event.label;
}

/**
 * Infer the die sides from a game event for critical detection.
 * Assumes d20 for single-roll events without explicit sides info.
 */
export function inferSides(event: GameEvent): number {
  // For d20 checks (single roll or advantage/disadvantage with 2 rolls)
  const rolls = event.data.rolls ?? [];
  if (event.type === 'dice_roll' && rolls.length <= 2) {
    return 20;
  }
  return 0; // Unknown sides — don't check for crits
}
