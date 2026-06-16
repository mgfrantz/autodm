"""
Multiclassing engine — handle characters with multiple classes.

Implements DnD 5e multiclassing rules:
- Ability score prerequisites for each class
- XP and level tracking across all classes
- HP calculation using hit dice from each class
- Proficiency bonus from total level
- ASI timing across all classes
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.engine.leveling import (
    CLASS_HIT_DICE,
    proficiency_bonus,
    asi_levels,
    asi_available as single_class_asi_available,
    clamp_score,
    MAX_ABILITY_SCORE,
    MIN_ABILITY_SCORE,
)


# ---------------------------------------------------------------------------
# Multiclass prerequisites
# ---------------------------------------------------------------------------
# Each class requires specific ability scores to multiclass into it.
# Source: DnD 5e Player's Handbook, Chapter 6 (Multiclassing)
_MULTiclass_PREREQS: dict[str, dict[str, int]] = {
    "barbarian": {"strength": 13},
    "bard": {"charisma": 13},
    "cleric": {"wisdom": 13},
    "druid": {"wisdom": 13},
    "fighter": {"strength": 13, "dexterity": 13},
    "monk": {"wisdom": 13, "dexterity": 13},
    "paladin": {"charisma": 13, "wisdom": 13},
    "ranger": {"dexterity": 13, "wisdom": 13},
    "rogue": {"dexterity": 13},
    "sorcerer": {"charisma": 13},
    "warlock": {"charisma": 13},
    "wizard": {"intelligence": 13},
}


@dataclass
class MulticlassCheck:
    """Result of checking if a character can add a class."""
    can_multiclass: bool
    message: str
    missing_requirements: dict[str, int] = field(default_factory=dict)


def check_multiclass_requirements(
    new_class: str,
    ability_scores: dict[str, int],
) -> MulticlassCheck:
    """Check if a character meets prerequisites to multiclass into a class.

    Args:
        new_class: The class the character wants to add (lowercase)
        ability_scores: Dict of ability_name -> score

    Returns:
        MulticlassCheck with success/failure and missing requirements
    """
    new_class = new_class.lower()
    prereqs = _MULTiclass_PREREQS.get(new_class, {})

    if not prereqs:
        # Unknown class - no requirements, allow it
        return MulticlassCheck(
            can_multiclass=True,
            message=f"Added {new_class} (no known requirements)"
        )

    missing = {}
    for ability, required in prereqs.items():
        current = ability_scores.get(ability, 10)
        if current < required:
            missing[ability] = required

    if missing:
        missing_str = ", ".join(f"{a} {req}" for a, req in missing.items())
        return MulticlassCheck(
            can_multiclass=False,
            message=f"Cannot multiclass into {new_class}: requires {missing_str}",
            missing_requirements=missing,
        )

    return MulticlassCheck(
        can_multiclass=True,
        message=f"Can multiclass into {new_class}"
    )


# ---------------------------------------------------------------------------
# Multiclass progression
# ---------------------------------------------------------------------------

@dataclass
class ClassLevel:
    """Track a single class's level."""
    name: str
    level: int


def parse_classes(classes_json: str) -> dict[str, int]:
    """Parse JSON string of classes into a dict.

    Args:
        classes_json: JSON string like '{"wizard": 5, "fighter": 2}'

    Returns:
        Dict mapping class name -> level. Any non-dict payload (empty string,
        JSON ``null``, etc.) is coerced to an empty dict.
    """
    import json
    if not classes_json or classes_json == "{}":
        return {}
    try:
        parsed = json.loads(classes_json)
    except (json.JSONDecodeError, TypeError):
        return {}
    # ``json.loads("null")`` -> None; defensively coerce anything that isn't a
    # dict into an empty mapping so callers always receive a dict.
    if not isinstance(parsed, dict):
        return {}
    return parsed


def serialize_classes(classes: dict[str, int]) -> str:
    """Serialize classes dict to JSON string."""
    import json
    return json.dumps(classes)


def calculate_total_level(classes: dict[str, int]) -> int:
    """Calculate total character level from all classes."""
    return sum(classes.values())


def calculate_proficiency_bonus(classes: dict[str, int]) -> int:
    """Calculate proficiency bonus from total level."""
    total = calculate_total_level(classes)
    return proficiency_bonus(total)


@dataclass
class HPGainBreakdown:
    """HP gains broken down by class level."""
    class_name: str
    levels_in_class: int
    hit_die: int
    con_mod: int
    total_hp_gained: int


def calculate_multiclass_hp(
    classes: dict[str, int],
    con_mod: int,
) -> tuple[int, list[HPGainBreakdown]]:
    """Calculate total HP from multiclass levels.

    Uses the fixed-average rule for each class's hit die.
    First level in any class gains max hit die + CON mod.
    Subsequent levels gain (hit_die // 2 + 1) + CON mod.

    Args:
        classes: Dict of class_name -> level
        con_mod: Constitution modifier

    Returns:
        Tuple of (total_hp, list of breakdowns)
    """
    total_hp = 0
    breakdowns: list[HPGainBreakdown] = []

    for class_name, level in classes.items():
        hit_die = CLASS_HIT_DICE.get(class_name.lower(), 8)
        class_hp = 0

        # First level: max hit die + CON
        first_level_hp = hit_die + con_mod
        class_hp += max(1, first_level_hp)

        # Subsequent levels: average + CON
        if level > 1:
            avg_per_level = (hit_die // 2 + 1) + con_mod
            class_hp += max(1, avg_per_level) * (level - 1)

        total_hp += class_hp
        breakdowns.append(HPGainBreakdown(
            class_name=class_name,
            levels_in_class=level,
            hit_die=hit_die,
            con_mod=con_mod,
            total_hp_gained=class_hp,
        ))

    return max(1, total_hp), breakdowns


@dataclass
class ASIStatus:
    """ASI status for a multiclass character."""
    available: int
    used: int
    earned: int
    next_asi_level: Optional[int] = None
    next_asi_class: Optional[str] = None


def calculate_multiclass_asi_status(
    classes: dict[str, int],
    asi_used: int,
) -> ASIStatus:
    """Calculate ASI status across all classes.

    A character earns ASIs from each class independently. The character
    can spend ASIs on any ability, regardless of which class earned them.

    Args:
        classes: Dict of class_name -> level
        asi_used: Total ASIs already spent

    Returns:
        ASIStatus with available, used, earned, and next ASI info
    """
    total_earned = 0
    next_asi_level = None
    next_asi_class = None

    for class_name, level in classes.items():
        class_earned = len([lvl for lvl in asi_levels(class_name) if lvl <= level])
        total_earned += class_earned

        # Track the next ASI level for each class
        for lvl in asi_levels(class_name):
            if lvl > level:
                # Find the lowest next ASI level across all classes
                if next_asi_level is None or lvl < next_asi_level:
                    next_asi_level = lvl
                    next_asi_class = class_name
                break

    available = max(0, total_earned - asi_used)

    return ASIStatus(
        available=available,
        used=asi_used,
        earned=total_earned,
        next_asi_level=next_asi_level,
        next_asi_class=next_asi_class,
    )


@dataclass
class MulticlassSummary:
    """Full summary of a multiclass character's state."""
    classes: dict[str, int]
    total_level: int
    proficiency_bonus: int
    total_hp: int
    hp_breakdown: list[HPGainBreakdown]
    asi_status: ASIStatus
    primary_class: str


def build_multiclass_summary(
    classes: dict[str, int],
    con_mod: int,
    asi_used: int,
) -> MulticlassSummary:
    """Build a complete summary of a multiclass character."""
    total_level = calculate_total_level(classes)
    prof_bonus = calculate_proficiency_bonus(classes)
    total_hp, hp_breakdown = calculate_multiclass_hp(classes, con_mod)
    asi_status = calculate_multiclass_asi_status(classes, asi_used or 0)

    # Primary class is the one with the highest level
    primary_class = max(classes.items(), key=lambda x: x[1])[0] if classes else "commoner"

    return MulticlassSummary(
        classes=classes,
        total_level=total_level,
        proficiency_bonus=prof_bonus,
        total_hp=total_hp,
        hp_breakdown=hp_breakdown,
        asi_status=asi_status,
        primary_class=primary_class,
    )