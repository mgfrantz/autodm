"""
Saving throw engine — per-ability saves with class proficiency tracking.

Implements faithful DnD 5e saving throw mechanics:

- **Class proficiency**: Each class is proficient in two specific saving throws
  (e.g., Fighter: Str/Con, Wizard: Int/Wis). Proficiency adds the character's
  proficiency bonus to the save.
- **Save formula**: d20 + proficiency_bonus (if proficient) + ability_modifier
- **Condition effects**:
  - Paralyzed/Petrified/Unconscious: auto-fail Strength and Dexterity saves
  - Restrained: disadvantage on Dexterity saves
- **Multiclassing**: When a character has multiple classes, they're proficient
  in the union of all their class's proficient saves.
- **Feat integration**: Resilient feat grants proficiency in one saving throw.

The engine is pure (no DB, no LLM) and operates on a character-like object
that exposes: level, abilities (dict), classes (dict or primary_class string),
feats (list), and optional conditions (for auto-fail/disadvantage).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.engine import conditions as cond
from app.engine.dice import ability_modifier, proficiency_bonus, roll_d20, RollResult


# --------------------------------------------------------------------------- #
# Ability names
# --------------------------------------------------------------------------- #

ABILITIES = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")


# --------------------------------------------------------------------------- #
# Class saving throw proficiency
# --------------------------------------------------------------------------- #

# Saving throw proficiency per class (lowercase class name -> set of abilities)
_CLASS_SAVE_PROFICIENCY: dict[str, set[str]] = {
    "barbarian": {"strength", "constitution"},
    "bard": {"dexterity", "charisma"},
    "cleric": {"wisdom", "charisma"},
    "druid": {"intelligence", "wisdom"},
    "fighter": {"strength", "constitution"},
    "monk": {"strength", "dexterity"},
    "paladin": {"wisdom", "charisma"},
    "ranger": {"strength", "dexterity"},
    "rogue": {"dexterity", "intelligence"},
    "sorcerer": {"constitution", "charisma"},
    "warlock": {"wisdom", "charisma"},
    "wizard": {"intelligence", "wisdom"},
}


def get_class_saving_throws(char_class: str) -> set[str]:
    """Get the saving throws a class is proficient in."""
    return set(_CLASS_SAVE_PROFICIENCY.get(char_class.lower(), set()))


def get_multiclass_saving_throws(classes: dict[str, int]) -> set[str]:
    """Get the union of saving throw proficiencies from all classes.

    In DnD 5e, multiclass characters are proficient in the union of all
    their class's saving throws.
    """
    proficient: set[str] = set()
    for cls_name in classes.keys():
        proficient.update(get_class_saving_throws(cls_name))
    return proficient


# --------------------------------------------------------------------------- #
# Character-saving-throw queries
# --------------------------------------------------------------------------- #

def get_saving_throw_proficiencies(character: Any) -> set[str]:
    """Get all saving throw proficiencies for a character.

    Includes class-based proficiencies (union of all classes) and feat-based
    proficiencies (e.g., Resilient feat).
    """
    # Get classes dict or fall back to primary class
    if hasattr(character, "classes_dict") and character.classes_dict:
        classes = character.classes_dict
    elif hasattr(character, "classes"):
        import json
        try:
            classes = json.loads(character.classes or "{}")
            if not classes:
                # Backward compatibility
                classes = {character.primary_class.lower(): character.level or 1}
        except (json.JSONDecodeError, ValueError):
            classes = {character.primary_class.lower(): character.level or 1}
    else:
        # Single class
        classes = {character.char_class.lower(): character.level or 1}

    # Start with class proficiencies
    proficient = get_multiclass_saving_throws(classes)

    # Add feat-based proficiencies (Resilient feat)
    if hasattr(character, "feats"):
        import json
        try:
            feats = json.loads(character.feats or "[]")
            for feat in feats:
                feat_name = feat.get("name", "").lower()
                # Resilient feat format: "Resilient (Constitution)" or just "Resilient"
                if "resilient" in feat_name:
                    # Extract ability from parentheses or feat effects
                    if "(" in feat_name and ")" in feat_name:
                        ability_part = feat_name[feat_name.find("(")+1:feat_name.find(")")].strip().lower()
                        if ability_part in ABILITIES:
                            proficient.add(ability_part)
                    elif "effects" in feat:
                        effects = feat["effects"]
                        if "save_proficiency" in effects:
                            save_abil = effects["save_proficiency"].lower()
                            if save_abil in ABILITIES:
                                proficient.add(save_abil)
        except (json.JSONDecodeError, ValueError, AttributeError):
            pass

    return proficient


def get_character_level(character: Any) -> int:
    """Get the character's total level."""
    if hasattr(character, "level"):
        return max(1, character.level or 1)
    # For multiclassing, sum class levels
    if hasattr(character, "classes_dict") and character.classes_dict:
        return max(1, sum(character.classes_dict.values()))
    if hasattr(character, "classes"):
        import json
        try:
            classes = json.loads(character.classes or "{}")
            if classes:
                return max(1, sum(classes.values()))
        except (json.JSONDecodeError, ValueError):
            pass
    return 1


def get_ability_score(character: Any, ability: str) -> int:
    """Get an ability score from a character."""
    ability = ability.lower()
    if hasattr(character, "abilities") and isinstance(character.abilities, dict):
        return character.abilities.get(ability, 10)
    if hasattr(character, ability):
        return getattr(character, ability, 10)
    return 10


# --------------------------------------------------------------------------- #
# Save execution
# --------------------------------------------------------------------------- #

@dataclass
class SaveResult:
    """Result of a saving throw attempt."""
    ability: str
    roll: RollResult
    modifier: int
    total: int
    success: bool
    dc: int
    advantage: bool = False
    disadvantage: bool = False
    auto_failed: bool = False
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "ability": self.ability,
            "roll": self.roll.description,
            "rolls": self.roll.rolls,
            "modifier": self.modifier,
            "total": self.total,
            "success": self.success,
            "dc": self.dc,
            "advantage": self.advantage,
            "disadvantage": self.disadvantage,
            "auto_failed": self.auto_failed,
            "description": self.description,
        }


def check_save_auto_fail(ability: str, conditions: list[str]) -> bool:
    """Check if a saving throw auto-fails due to conditions.

    Paralyzed, petrified, and unconscious all cause auto-failure on
    Strength and Dexterity saving throws.
    """
    ability = ability.lower()
    if ability not in ("strength", "dexterity"):
        return False

    auto_fail_conditions = {"paralyzed", "petrified", "unconscious"}
    return any(c in auto_fail_conditions for c in conditions)


def check_save_disadvantage(ability: str, conditions: list[str]) -> bool:
    """Check if a saving throw has disadvantage due to conditions.

    Restrained imposes disadvantage on Dexterity saving throws.
    """
    ability = ability.lower()
    if ability == "dexterity" and "restrained" in conditions:
        return True
    return False


def calculate_save_bonus(
    ability: str,
    character: Any,
    proficiencies: Optional[set[str]] = None,
) -> int:
    """Calculate the static bonus for a saving throw (proficiency + ability mod).

    If ``proficiencies`` is provided, it's used directly; otherwise, it's
    queried from the character.
    """
    ability = ability.lower()
    if proficiencies is None:
        proficiencies = get_saving_throw_proficiencies(character)

    score = get_ability_score(character, ability)
    mod = ability_modifier(score)

    prof = 0
    if ability in proficiencies:
        level = get_character_level(character)
        prof = proficiency_bonus(level)

    return prof + mod


def roll_saving_throw(
    ability: str,
    character: Any,
    dc: int,
    advantage: bool = False,
    disadvantage: bool = False,
    conditions: Optional[list[str]] = None,
    proficiencies: Optional[set[str]] = None,
) -> SaveResult:
    """Roll a saving throw for a character against a DC.

    Args:
        ability: The ability to save with (e.g., "strength").
        character: Character-like object with level, abilities, classes, feats.
        dc: The Difficulty Class to beat.
        advantage: Explicit advantage override.
        disadvantage: Explicit disadvantage override.
        conditions: List of active conditions (for auto-fail/disadvantage).
        proficiencies: Pre-computed proficiency set (optional optimization).

    Returns:
        A :class:`SaveResult` with the roll, modifier, total, and success.
    """
    ability = ability.lower()
    if ability not in ABILITIES:
        raise ValueError(f"Invalid ability: {ability}")

    if conditions is None:
        conditions = []

    # Advantage and disadvantage cancel each other out
    has_advantage = advantage and not disadvantage
    has_disadvantage = disadvantage and not advantage

    # Check for auto-fail conditions
    if check_save_auto_fail(ability, conditions):
        # Still calculate the roll for reporting, but mark as auto-failed
        bonus = calculate_save_bonus(ability, character, proficiencies)
        return SaveResult(
            ability=ability,
            roll=RollResult(rolls=[1], modifier=bonus, total=1 + bonus,
                           description=f"d20 (auto-fail) {bonus:+d}"),
            modifier=bonus,
            total=1 + bonus,
            success=False,
            dc=dc,
            advantage=False,
            disadvantage=False,
            auto_failed=True,
            description=f"{ability.capitalize()} save auto-failed due to conditions",
        )

    # Check for disadvantage from conditions (stacks with explicit disadvantage)
    if check_save_disadvantage(ability, conditions):
        has_disadvantage = True
        has_advantage = False  # Condition disadvantage overrides explicit advantage

    # Calculate bonus
    bonus = calculate_save_bonus(ability, character, proficiencies)

    # Roll with advantage/disadvantage
    roll_result = roll_d20(modifier=bonus, advantage=has_advantage, disadvantage=has_disadvantage)

    # Determine success
    success = roll_result.total >= dc

    # Build description
    prof_bon = proficiency_bonus(get_character_level(character))
    is_proficient = (proficiencies or get_saving_throw_proficiencies(character)).__contains__(ability)
    prof_str = f"+{prof_bon} proficiency" if is_proficient else ""
    mod_str = f"{ability_modifier(get_ability_score(character, ability)):+d}"
    desc_parts = [f"{ability.capitalize()} save"]
    if has_advantage:
        desc_parts.append("(advantage)")
    elif has_disadvantage:
        desc_parts.append("(disadvantage)")
    desc_parts.append(f"DC {dc}")
    description = " ".join(desc_parts)

    return SaveResult(
        ability=ability,
        roll=roll_result,
        modifier=bonus,
        total=roll_result.total,
        success=success,
        dc=dc,
        advantage=has_advantage,
        disadvantage=has_disadvantage,
        auto_failed=False,
        description=description,
    )


# --------------------------------------------------------------------------- #
# Save DC calculation (for enemies/spells)
# --------------------------------------------------------------------------- #

def calculate_save_dc(
    ability_score: int,
    proficiency_bonus: int,
    bonus: int = 0,
) -> int:
    """Calculate a save DC from a stat + proficiency.

    Standard formula: 8 + proficiency_bonus + ability_modifier + bonus
    """
    mod = ability_modifier(ability_score)
    return 8 + proficiency_bonus + mod + bonus


def calculate_character_save_dc(
    character: Any,
    spellcasting_ability: str,
    bonus: int = 0,
) -> int:
    """Calculate a save DC for a character's spells/abilities.

    Args:
        character: Character-like object.
        spellcasting_ability: The ability used for spellcasting (e.g., "intelligence").
        bonus: Additional bonuses to the DC.

    Returns:
        The save DC.
    """
    ability_score = get_ability_score(character, spellcasting_ability)
    prof = proficiency_bonus(get_character_level(character))
    return calculate_save_dc(ability_score, prof, bonus)