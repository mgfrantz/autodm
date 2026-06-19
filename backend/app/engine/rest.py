"""
Rest engine — short rests and long rests (DnD 5e).

A character recovers resources by resting:

SHORT REST (≥1 hour)
- The character may spend one or more Hit Dice (up to their level). For each
  Hit Die spent, roll the die + CON modifier and regain that many HP, up to
  ``max_hp``. Spent dice are unavailable again until a long rest. The engine
  stops spending dice as soon as the character reaches full HP so none are
  wasted.

LONG REST (≥8 hours)
- The character regains all lost hit points (full HP).
- Recovers spent Hit Dice: up to half the character's total level (minimum 1).
- Recovers all expended spell slots (the caller invokes ``Spellbook.long_rest``).
- Clears "restable" conditions (e.g. poisoned, frightened). Which conditions a
  long rest may clear is controlled by ``LONG_REST_CLEARABLE_CONDITIONS``.

The engine is pure (no DB, no LLM) so it is trivially unit-testable. The API
layer feeds real character data in and persists the results.

Multiclass note: a character's Hit Dice are one die per level, sized to each
level's class. This engine rolls every die using a single supplied ``hit_die``
size (the primary class's) as a documented simplification; the leveling engine
already uses the same class-based hit-die table for HP growth.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.engine.dice import roll_die
from app.engine.leveling import hit_die_for_class


# --------------------------------------------------------------------------- #
# Conditions a long rest is permitted to clear.
#
# Strict 5e only clears *exhaustion* on a long rest; other conditions require
# magic (e.g. Lesser Restoration). For game feel this default set treats common
# short-term debuffs as things a full night's sleep can shake off. Callers may
# override the set to taste.
# --------------------------------------------------------------------------- #
LONG_REST_CLEARABLE_CONDITIONS: set[str] = {
    "poisoned",    # the venom works its way out of the system
    "frightened",  # fear fades with rest
    "charmed",     # the enchantment wears off (simplified)
    "blinded",     # temporary blindness clears
    "deafened",    # temporary deafness clears
    "prone",       # you simply stand up
}


def is_clearable_by_long_rest(name: str) -> bool:
    """True if a long rest may clear the named condition."""
    return name in LONG_REST_CLEARABLE_CONDITIONS


# --------------------------------------------------------------------------- #
# Hit-Dice pool helpers.
# --------------------------------------------------------------------------- #

def total_hit_dice(level: int) -> int:
    """A character's maximum Hit Dice = their total level (minimum 1)."""
    return max(1, level)


def available_hit_dice(level: int, hit_dice_used: int) -> int:
    """Hit Dice currently available to spend = total − already spent."""
    return max(0, total_hit_dice(level) - max(0, hit_dice_used))


def long_rest_hit_dice_recovered(level: int) -> int:
    """How many Hit Dice a long rest recovers: half the total (minimum 1)."""
    return max(1, total_hit_dice(level) // 2)


def hit_die_size(char_class: str) -> int:
    """The hit-die size for a class (delegates to the leveling table)."""
    return hit_die_for_class(char_class)


# --------------------------------------------------------------------------- #
# Result dataclasses.
# --------------------------------------------------------------------------- #

@dataclass
class DieRoll:
    """A single Hit-Die roll spent during a short rest."""
    faces: int       # die size rolled (e.g. 8 for a d8)
    roll: int        # raw die result
    modifier: int    # CON modifier applied
    total: int       # HP actually regained from this die (clamped, ≥1)

    def to_dict(self) -> dict:
        return {"faces": self.faces, "roll": self.roll,
                "modifier": self.modifier, "total": self.total}


@dataclass
class ShortRestResult:
    """Outcome of a short rest."""
    success: bool
    message: str
    hit_dice_spent: int
    hit_dice_available_after: int
    rolls: list[DieRoll] = field(default_factory=list)
    hp_before: int = 0
    hp_healed: int = 0
    hp_after: int = 0
    max_hp: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "hit_dice_spent": self.hit_dice_spent,
            "hit_dice_available_after": self.hit_dice_available_after,
            "rolls": [r.to_dict() for r in self.rolls],
            "hp_before": self.hp_before,
            "hp_healed": self.hp_healed,
            "hp_after": self.hp_after,
            "max_hp": self.max_hp,
        }


@dataclass
class LongRestResult:
    """Outcome of a long rest."""
    success: bool
    message: str
    hp_before: int = 0
    hp_after: int = 0
    hp_healed: int = 0
    max_hp: int = 0
    hit_dice_recovered: int = 0       # dice that became available again
    hit_dice_available_after: int = 0
    hit_dice_used_after: int = 0
    slots_recovered: bool = False
    conditions_cleared: list[str] = field(default_factory=list)
    exhaustion_before: int = 0
    exhaustion_after: int = 0          # one level lower than before (min 0)
    exhaustion_reduced: bool = False

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "hp_before": self.hp_before,
            "hp_after": self.hp_after,
            "hp_healed": self.hp_healed,
            "max_hp": self.max_hp,
            "hit_dice_recovered": self.hit_dice_recovered,
            "hit_dice_available_after": self.hit_dice_available_after,
            "hit_dice_used_after": self.hit_dice_used_after,
            "slots_recovered": self.slots_recovered,
            "conditions_cleared": list(self.conditions_cleared),
            "exhaustion_before": self.exhaustion_before,
            "exhaustion_after": self.exhaustion_after,
            "exhaustion_reduced": self.exhaustion_reduced,
        }


# --------------------------------------------------------------------------- #
# Rest resolution.
# --------------------------------------------------------------------------- #

def short_rest(
    char_class: str,
    level: int,
    current_hp: int,
    max_hp: int,
    hit_dice_used: int,
    con_mod: int,
    num_dice: Optional[int] = None,
    rolls: Optional[list[int]] = None,
) -> ShortRestResult:
    """Resolve a short rest: spend Hit Dice to regain HP.

    Parameters
    ----------
    char_class
        Class whose hit die to roll (the character's primary class).
    level
        Total character level (determines the Hit-Dice pool size).
    current_hp, max_hp
        Current and maximum hit points before resting.
    hit_dice_used
        Hit Dice already spent since the last long rest.
    con_mod
        Constitution modifier added to each die.
    num_dice
        How many dice to spend. If ``None`` (default) the engine spends dice
        until HP is full or the pool is exhausted. Takes precedence over
        ``rolls`` for deciding the count when both are supplied.
    rolls
        Optional explicit die results (for deterministic testing / scripted
        play), consumed in order up to the number of dice rolled.

    A rest that can do nothing (no dice available, or already at full HP)
    returns ``success=False`` with an explanatory message. Dice are never
    wasted: spending stops as soon as the character reaches maximum HP.
    """
    hd = hit_die_for_class(char_class)
    available = available_hit_dice(level, hit_dice_used)
    hp_before = current_hp

    # --- Guards -----------------------------------------------------------
    if current_hp >= max_hp:
        return ShortRestResult(
            success=False,
            message="Already at full HP — no need to spend Hit Dice.",
            hit_dice_spent=0,
            hit_dice_available_after=available,
            rolls=[],
            hp_before=hp_before,
            hp_healed=0,
            hp_after=current_hp,
            max_hp=max_hp,
        )

    if available <= 0:
        return ShortRestResult(
            success=False,
            message="No Hit Dice available to spend (a long rest recovers them).",
            hit_dice_spent=0,
            hit_dice_available_after=available,
            rolls=[],
            hp_before=hp_before,
            hp_healed=0,
            hp_after=current_hp,
            max_hp=max_hp,
        )

    # --- Determine how many dice to roll ---------------------------------
    # ``num_dice`` controls the *count*; ``rolls`` provides deterministic die
    # results (used in order). When both are given, ``num_dice`` wins and only
    # that many entries of ``rolls`` are consumed.
    if num_dice is not None:
        requested = max(0, num_dice)
    elif rolls is not None:
        requested = len(rolls)
    else:
        # Spend until full or exhausted.
        requested = available
    dice_to_roll = min(requested, available)

    # --- Roll dice, stopping at full HP ----------------------------------
    spent_rolls: list[DieRoll] = []
    healed = 0
    for i in range(dice_to_roll):
        if current_hp + healed >= max_hp:
            break  # already full — don't waste a die
        face = rolls[i] if rolls is not None else roll_die(hd)
        die_heal = max(1, face + con_mod)
        room = max_hp - (current_hp + healed)
        actual = min(die_heal, room)
        healed += actual
        spent_rolls.append(
            DieRoll(faces=hd, roll=face, modifier=con_mod, total=actual)
        )

    dice_consumed = len(spent_rolls)
    hp_after = min(max_hp, current_hp + healed)
    total_healed = hp_after - current_hp

    if dice_consumed == 0:
        return ShortRestResult(
            success=False,
            message="No Hit Dice were spent (request resulted in zero rolls).",
            hit_dice_spent=0,
            hit_dice_available_after=available,
            rolls=[],
            hp_before=hp_before,
            hp_healed=0,
            hp_after=current_hp,
            max_hp=max_hp,
        )

    return ShortRestResult(
        success=True,
        message=f"Spent {dice_consumed} Hit Die(s) and recovered {total_healed} HP.",
        hit_dice_spent=dice_consumed,
        hit_dice_available_after=available - dice_consumed,
        rolls=spent_rolls,
        hp_before=hp_before,
        hp_healed=total_healed,
        hp_after=hp_after,
        max_hp=max_hp,
    )


def long_rest(
    char_class: str,
    level: int,
    current_hp: int,
    max_hp: int,
    hit_dice_used: int,
    is_caster: bool,
    conditions: Optional[list[str]] = None,
    exhaustion: int = 0,
) -> LongRestResult:
    """Resolve a long rest: full HP, recover Hit Dice, clear restable conditions.

    Parameters mirror :func:`short_rest` plus:

    is_caster
        Whether the character has spell slots to recover (the caller resets the
        actual slots via ``Spellbook.long_rest``).
    conditions
        The player's current conditions (out-of-combat). Any that are in
        :data:`LONG_REST_CLEARABLE_CONDITIONS` are reported as cleared for the
        caller to remove from game state.
    exhaustion
        The player's current exhaustion level (0–6). A long rest reduces it by
        one level (provided the creature has eaten and drunk — assumed true).
        Level 6 is death and so cannot rest; the caller should not reach here.

    A long rest always succeeds. HP is restored to ``max_hp``; Hit Dice recover
    up to half the total (minimum 1), but never more than were actually spent.
    """
    conditions = conditions or []
    recovered_total = long_rest_hit_dice_recovered(level)
    dice_regained = min(recovered_total, max(0, hit_dice_used))
    new_used = max(0, hit_dice_used - dice_regained)

    cleared = [c for c in conditions if is_clearable_by_long_rest(c)]
    hp_healed = max(0, max_hp - current_hp)

    # Exhaustion recovers by one level per long rest (PHB). Fatal level 6
    # cannot rest, but we still clamp defensively so the engine stays pure.
    from app.engine.exhaustion import MAX_EXHAUSTION
    exhaustion_before = max(0, min(MAX_EXHAUSTION, int(exhaustion)))
    exhaustion_after = max(0, exhaustion_before - 1) if exhaustion_before < MAX_EXHAUSTION else exhaustion_before
    exhaustion_reduced = exhaustion_after < exhaustion_before

    bits = [f"recovered {hp_healed} HP"]
    bits.append(f"regained {dice_regained} Hit Die(s)")
    if is_caster:
        bits.append("recovered all spell slots")
    if cleared:
        bits.append(f"cleared {', '.join(cleared)}")
    if exhaustion_reduced:
        bits.append(f"recovered 1 exhaustion level (now {exhaustion_after})")
    message = "Long rest complete: " + "; ".join(bits) + "."

    return LongRestResult(
        success=True,
        message=message,
        hp_before=current_hp,
        hp_after=max_hp,
        hp_healed=hp_healed,
        max_hp=max_hp,
        hit_dice_recovered=dice_regained,
        hit_dice_available_after=total_hit_dice(level) - new_used,
        hit_dice_used_after=new_used,
        slots_recovered=is_caster,
        conditions_cleared=cleared,
        exhaustion_before=exhaustion_before,
        exhaustion_after=exhaustion_after,
        exhaustion_reduced=exhaustion_reduced,
    )
