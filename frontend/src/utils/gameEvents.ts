/**
 * Pure formatting helpers for GameEvent data (DM function calling Phase 1).
 *
 * These functions turn raw GameEvent payloads into display-ready strings and
 * metadata (labels, colors, summaries) so the UI components stay declarative
 * and the logic is trivially unit-testable.
 */
import type { GameEvent, InitiativeCombatant } from '../types';

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
  if (event.type === 'attack') {
    const d = event.data;
    return attackSummary(d.attacker, d.target, d.attack_total, d.ac,
      d.hit, d.critical, d.critical_miss, d.damage, d.damage_type);
  }
  if (event.type === 'damage') {
    const d = event.data;
    return damageSummary(d.target, d.amount, d.damage_type,
      d.target_remaining_hp, d.target_max_hp);
  }
  if (event.type === 'initiative') {
    return initiativeSummary(event.data.combatants);
  }
  if (event.type === 'spell_cast') {
    const d = event.data;
    return spellCastSummary(
      d.spell_name, d.level, d.school, d.success, d.hit, d.made_save,
      d.damage, d.healing, d.damage_type, d.half_damage, d.target, d.message,
    );
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

// ==========================================================================
// Phase 2: Combat event helpers
// ==========================================================================

/**
 * Tailwind color classes for a given damage type.
 * Maps common DnD damage types to thematic colours.
 */
export function damageTypeColor(damageType: string): { text: string; bg: string; border: string } {
  const type = (damageType ?? '').toLowerCase();
  const map: Record<string, { text: string; bg: string; border: string }> = {
    fire:       { text: 'text-orange-300', bg: 'bg-orange-900/30', border: 'border-orange-700/50' },
    cold:       { text: 'text-cyan-300',   bg: 'bg-cyan-900/30',   border: 'border-cyan-700/50' },
    lightning:  { text: 'text-yellow-300', bg: 'bg-yellow-900/30', border: 'border-yellow-700/50' },
    thunder:    { text: 'text-indigo-300', bg: 'bg-indigo-900/30', border: 'border-indigo-700/50' },
    poison:     { text: 'text-green-300',  bg: 'bg-green-900/30',  border: 'border-green-700/50' },
    acid:       { text: 'text-lime-300',   bg: 'bg-lime-900/30',   border: 'border-lime-700/50' },
    necrotic:   { text: 'text-purple-300', bg: 'bg-purple-900/30', border: 'border-purple-700/50' },
    radiant:    { text: 'text-amber-200',  bg: 'bg-amber-900/30',  border: 'border-amber-700/50' },
    psychic:    { text: 'text-fuchsia-300',bg: 'bg-fuchsia-900/30',border: 'border-fuchsia-700/50' },
    force:      { text: 'text-blue-300',   bg: 'bg-blue-900/30',   border: 'border-blue-700/50' },
    bludgeoning:{ text: 'text-stone-300',  bg: 'bg-stone-900/30',  border: 'border-stone-700/50' },
    piercing:   { text: 'text-rose-300',   bg: 'bg-rose-900/30',   border: 'border-rose-700/50' },
    slashing:   { text: 'text-red-300',    bg: 'bg-red-900/30',    border: 'border-red-700/50' },
  };
  return map[type] ?? { text: 'text-parchment-200', bg: 'bg-parchment-900/30', border: 'border-parchment-700/50' };
}

/**
 * Compute HP bar display data from remaining/max HP.
 * Returns percentage (0-100), colour classes, and whether target is dead.
 */
export function hpBarData(
  remainingHp: number | undefined,
  maxHp: number | undefined,
): { percentage: number; color: string; isDead: boolean; label: string } {
  const remaining = remainingHp ?? 0;
  const max = maxHp ?? 1;
  const percentage = max > 0 ? Math.max(0, Math.min(100, (remaining / max) * 100)) : 0;
  const isDead = remaining <= 0;
  let color: string;
  if (isDead) {
    color = 'bg-blood-600';
  } else if (percentage <= 25) {
    color = 'bg-blood-500';
  } else if (percentage <= 50) {
    color = 'bg-orange-500';
  } else if (percentage <= 75) {
    color = 'bg-yellow-500';
  } else {
    color = 'bg-emerald-500';
  }
  return { percentage, color, isDead, label: `${remaining} / ${max}` };
}

/**
 * Generate a one-line summary for an attack event.
 */
export function attackSummary(
  attacker: string | undefined,
  target: string | undefined,
  attackTotal: number | undefined,
  ac: number | undefined,
  hit: boolean | null | undefined,
  critical: boolean | undefined,
  criticalMiss: boolean | undefined,
  damage: number | undefined,
  damageType: string | undefined,
): string {
  const att = attacker ?? 'Unknown';
  const tgt = target ?? 'Unknown';
  const parts: string[] = [`${att} → ${tgt}`];
  if (criticalMiss) {
    parts.push('CRITICAL MISS!');
  } else if (critical) {
    parts.push(`CRITICAL HIT! ${damage ?? 0} ${damageType ?? ''} damage`);
  } else if (hit) {
    parts.push(`${attackTotal ?? 0} vs AC ${ac ?? 0} — ${damage ?? 0} ${damageType ?? ''} damage`);
  } else {
    parts.push(`${attackTotal ?? 0} vs AC ${ac ?? 0} — MISS`);
  }
  return parts.join(' — ');
}

/**
 * Generate a one-line summary for a damage event.
 */
export function damageSummary(
  target: string | undefined,
  amount: number | undefined,
  damageType: string | undefined,
  remainingHp: number | undefined,
  maxHp: number | undefined,
): string {
  const tgt = target ?? 'Unknown';
  const dmg = amount ?? 0;
  const type = damageType ?? '';
  if ((remainingHp ?? 0) <= 0) {
    return `${tgt} takes ${dmg} ${type} damage — DEFEATED!`;
  }
  return `${tgt} takes ${dmg} ${type} damage (${remainingHp}/${maxHp} HP)`;
}

/**
 * Generate a summary for an initiative event.
 */
export function initiativeSummary(combatants: InitiativeCombatant[] | undefined): string {
  if (!combatants || combatants.length === 0) return 'Initiative order';
  return combatants.map((c, i) => `${i + 1}. ${c.name} (${c.initiative})`).join(', ');
}

// ==========================================================================
// Phase 3: Spell event helpers
// ==========================================================================

/**
 * Tailwind color classes for a given DnD spell school.
 * Maps the eight schools to thematic accent colours.
 */
export function spellSchoolColor(school: string | undefined): { text: string; bg: string; border: string } {
  const s = (school ?? '').toLowerCase();
  const map: Record<string, { text: string; bg: string; border: string }> = {
    abjuration:  { text: 'text-sky-300',     bg: 'bg-sky-900/30',     border: 'border-sky-700/50' },
    conjuration: { text: 'text-amber-300',   bg: 'bg-amber-900/30',   border: 'border-amber-700/50' },
    divination:  { text: 'text-teal-300',    bg: 'bg-teal-900/30',    border: 'border-teal-700/50' },
    enchantment: { text: 'text-pink-300',    bg: 'bg-pink-900/30',    border: 'border-pink-700/50' },
    evocation:   { text: 'text-orange-300',  bg: 'bg-orange-900/30',  border: 'border-orange-700/50' },
    illusion:    { text: 'text-violet-300',  bg: 'bg-violet-900/30',  border: 'border-violet-700/50' },
    necromancy:  { text: 'text-emerald-300', bg: 'bg-emerald-900/30', border: 'border-emerald-700/50' },
    transmutation:{ text: 'text-lime-300',   bg: 'bg-lime-900/30',    border: 'border-lime-700/50' },
  };
  return map[s] ?? { text: 'text-parchment-200', bg: 'bg-parchment-900/30', border: 'border-parchment-700/50' };
}

/**
 * A human-readable level label for a spell (cantrip / level N).
 */
export function spellLevelLabel(level: number | undefined): string {
  const lvl = level ?? 0;
  return lvl === 0 ? 'cantrip' : `level ${lvl}`;
}

/**
 * Generate a one-line summary for a spell_cast event.
 */
export function spellCastSummary(
  spellName: string | undefined,
  level: number | undefined,
  school: string | undefined,
  success: boolean | null | undefined,
  hit: boolean | null | undefined,
  madeSave: boolean | null | undefined,
  damage: number | undefined,
  healing: number | undefined,
  damageType: string | undefined,
  halfDamage: boolean | undefined,
  target: string | undefined,
  message: string | undefined,
): string {
  const name = spellName ?? 'Unknown spell';
  const parts: string[] = [`${name} (${spellLevelLabel(level)} ${school ?? ''})`.trim()];
  if (success === false) {
    parts.push('FAILED');
    if (message) parts.push(message);
    return parts.join(' — ');
  }
  if (healing && healing > 0) {
    parts.push(`+${healing} HP${target ? ` to ${target}` : ''}`);
  }
  if (damage && damage > 0) {
    parts.push(`${damage} ${damageType ?? ''} damage${halfDamage ? ' (half)' : ''}`);
  }
  if (hit === true) parts.push('hit');
  else if (hit === false) parts.push('miss');
  if (madeSave === true) parts.push('target saved');
  else if (madeSave === false) parts.push('target failed save');
  return parts.join(' — ');
}
