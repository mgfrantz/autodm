"""
Exhaustion engine — DnD 5e exhaustion (Special State).

Exhaustion is a stacking 6-level affliction distinct from the 14 conditions.
Some hazards (extreme heat/cold, starvation, forced marches, certain monsters
and spells) force Constitution saves that add a level of exhaustion on a
failure. The effects escalate sharply and culminate in death at level 6:

    Level  Effect
    ------ -------------------------------------------------------------
       1   Disadvantage on ability checks
       2   Speed halved
       3   Disadvantage on attack rolls AND saving throws
       4   Hit point maximum halved
       5   Speed reduced to 0
       6   Death

Recovery: finishing a long rest reduces exhaustion by 1 level (provided the
creature has ingested some food and drink). Level 6 is fatal and cannot be
recovered from by resting alone — it requires magic such as *Greater
Restoration*.

The module is pure: helpers operate on an object that exposes an integer
``exhaustion`` attribute (a combatant) OR accept the level directly. This keeps
the engine fully unit-testable without a database or LLM.

Reference: DnD 5e Player's Handbook, "Exhaustion" (Appendix A / ch. 8).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


#: The fatal threshold. At (or above) this level the creature is dead.
MAX_EXHAUSTION: int = 6


@dataclass(frozen=True)
class ExhaustionLevel:
    """The mechanical effects of a given exhaustion level."""

    level: int
    description: str
    # Disadvantage on ability checks (NOT attacks/saves — those are separate).
    disadvantage_ability_checks: bool = False
    # Disadvantage on the creature's own attack rolls.
    disadvantage_attack_rolls: bool = False
    # Disadvantage on the creature's own saving throws.
    disadvantage_saving_throws: bool = False
    # Speed divisor: 1 = full speed, 2 = halved, 0 = speed reduced to 0.
    speed_divisor: int = 1
    # Hit-point maximum halved (rounded down).
    max_hp_halved: bool = False
    # The creature is dead.
    dead: bool = False


# --------------------------------------------------------------------------- #
# Registry — effects for each exhaustion level (0 = none, 6 = death).
#
# Effects are CUMULATIVE: a given level confers every effect at or below it,
# which the query helpers below resolve by scanning the active band.
# --------------------------------------------------------------------------- #
_EXHAUSTION_LEVELS: dict[int, ExhaustionLevel] = {
    0: ExhaustionLevel(
        level=0,
        description="No exhaustion.",
    ),
    1: ExhaustionLevel(
        level=1,
        description="Disadvantage on ability checks.",
        disadvantage_ability_checks=True,
    ),
    2: ExhaustionLevel(
        level=2,
        description="Speed halved.",
        speed_divisor=2,
    ),
    3: ExhaustionLevel(
        level=3,
        description="Disadvantage on attack rolls and saving throws.",
        disadvantage_attack_rolls=True,
        disadvantage_saving_throws=True,
    ),
    4: ExhaustionLevel(
        level=4,
        description="Hit point maximum halved.",
        max_hp_halved=True,
    ),
    5: ExhaustionLevel(
        level=5,
        description="Speed reduced to 0.",
        speed_divisor=0,
    ),
    6: ExhaustionLevel(
        level=6,
        description="Death.",
        dead=True,
    ),
}


def level_rules(level: int) -> ExhaustionLevel:
    """Return the :class:`ExhaustionLevel` for *level* (clamped to 0–6)."""
    return _EXHAUSTION_LEVELS[_clamp(level)]


def _clamp(level: int) -> int:
    """Clamp an exhaustion level into the valid 0–6 range."""
    return max(0, min(MAX_EXHAUSTION, int(level)))


# --------------------------------------------------------------------------- #
# Object-level state helpers.
#
# Each operates on a combatant/character-like object exposing an ``exhaustion``
# integer attribute. When the object has no such attribute it is treated as
# level 0 (read) or the attribute is created (write), so the helpers are safe
# to call on plain objects and dicts-backed wrappers alike.
# --------------------------------------------------------------------------- #

def get_exhaustion(obj: Any) -> int:
    """Return the object's current exhaustion level (0 when untracked)."""
    return _clamp(getattr(obj, "exhaustion", 0) or 0)


def set_exhaustion(obj: Any, level: int) -> int:
    """Set the object's exhaustion level (clamped to 0–6). Returns the new level."""
    new_level = _clamp(level)
    obj.exhaustion = new_level
    return new_level


def add_exhaustion(obj: Any, levels: int = 1) -> int:
    """Add *levels* of exhaustion (clamped at 6). Returns the new level."""
    return set_exhaustion(obj, get_exhaustion(obj) + max(0, int(levels)))


def reduce_exhaustion(obj: Any, levels: int = 1) -> int:
    """Reduce exhaustion by *levels* (floored at 0). Returns the new level.

    This models long-rest recovery (one level per long rest).
    """
    return set_exhaustion(obj, get_exhaustion(obj) - max(0, int(levels)))


# --------------------------------------------------------------------------- #
# Effect queries — cumulative across all levels at or below the current one.
# --------------------------------------------------------------------------- #

def is_dead(obj: Any) -> bool:
    """True if the object has died from exhaustion (level 6)."""
    return get_exhaustion(obj) >= MAX_EXHAUSTION


def disadvantage_ability_checks(obj: Any) -> bool:
    """Disadvantage on ability checks (level 1+)."""
    lvl = get_exhaustion(obj)
    return any(_EXHAUSTION_LEVELS[l].disadvantage_ability_checks for l in range(1, lvl + 1))


def disadvantage_attack_rolls(obj: Any) -> bool:
    """Disadvantage on the creature's own attack rolls (level 3+)."""
    lvl = get_exhaustion(obj)
    return any(_EXHAUSTION_LEVELS[l].disadvantage_attack_rolls for l in range(1, lvl + 1))


def disadvantage_saving_throws(obj: Any) -> bool:
    """Disadvantage on the creature's own saving throws (level 3+)."""
    lvl = get_exhaustion(obj)
    return any(_EXHAUSTION_LEVELS[l].disadvantage_saving_throws for l in range(1, lvl + 1))


def effective_speed(base_speed: int, level: int) -> int:
    """Apply exhaustion's cumulative speed effects to *base_speed*.

    Effects stack: level 2 halves speed (rounded down) and level 5 reduces it
    to 0. A creature at level 4 still suffers the level-2 halving, and a
    creature at level 6 has speed 0.
    """
    divisor = _cumulative_speed_divisor(level)
    if divisor == 0:
        return 0
    if divisor == 2:
        return max(0, base_speed // 2)
    return max(0, base_speed)


def effective_max_hp(base_max_hp: int, level: int) -> int:
    """Apply exhaustion's max-HP effect (halved at level 4+, rounded down).

    Never returns below 1 (a creature always has at least 1 max HP while alive).
    """
    if level >= 4:
        return max(1, base_max_hp // 2)
    return base_max_hp


# --------------------------------------------------------------------------- #
# Description / serialisation helpers (for the UI and DM context).
# --------------------------------------------------------------------------- #

def level_effects(level: int) -> dict[str, Any]:
    """A serialisable summary of every effect active at *level* (cumulative)."""
    level = _clamp(level)
    return {
        "level": level,
        "description": _EXHAUSTION_LEVELS[level].description,
        "disadvantage_ability_checks": disadvantage_ability_checks(_Stub(level)),
        "disadvantage_attack_rolls": disadvantage_attack_rolls(_Stub(level)),
        "disadvantage_saving_throws": disadvantage_saving_throws(_Stub(level)),
        "speed_divisor": _cumulative_speed_divisor(level),
        "max_hp_halved": level >= 4,
        "dead": level >= MAX_EXHAUSTION,
        "active_effects": [l.description for l in
                           (_EXHAUSTION_LEVELS[i] for i in range(1, level + 1))],
    }


@dataclass
class _Stub:
    """Tiny stand-in so the cumulative query helpers work on a raw int."""
    exhaustion: int


def _cumulative_speed_divisor(level: int) -> int:
    """The most severe speed divisor active at *level* (0 > 2 > 1)."""
    if level >= 5:
        return 0
    if level >= 2:
        return 2
    return 1


def describe(obj: Any) -> dict[str, Any]:
    """A serialisable snapshot of an object's exhaustion state + effects."""
    level = get_exhaustion(obj)
    return {
        "exhaustion": level,
        **level_effects(level),
    }
