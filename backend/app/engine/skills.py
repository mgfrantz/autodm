"""
Skill system engine — DnD 5e skills, proficiency, expertise, and checks.

Implements faithful DnD 5e skill mechanics:

- **18 core skills** mapped to the six abilities (Athletics/Str, Acrobatics/Dex,
  Arcana/Int, Perception/Wis, Persuasion/Cha, etc.).
- **Class skill proficiency**: Each class grants a fixed number of skill choices
  drawn from a class-specific list (e.g., Rogue chooses 4 of 11, Fighter 2 of 8).
- **Background skill proficiency**: Backgrounds grant 2 fixed skills (e.g.,
  Soldier: Athletics/Intimidation, Sage: Arcana/History).
- **Expertise**: Rogue (levels 1 & 6) and Bard (levels 3 & 10) gain Expertise,
  doubling the proficiency bonus on chosen skills.
- **Skill modifier**: ability_modifier + proficiency_bonus (×2 if Expertise).
- **Skill check**: d20 + skill modifier vs DC, with advantage/disadvantage and
  condition effects (poisoned → disadvantage on all; restrained → disadvantage
  on Dex skills; blinded/deafened → disadvantage on Perception).
- **Passive scores**: 10 + skill modifier (±5 for adv/disadv), used for passive
  Perception/Investigation/Insight.

The engine is pure (no DB, no LLM) and operates on a character-like object that
exposes: level, abilities, classes (dict or primary_class string), background,
optional skill_proficiencies / skill_expertise JSON columns, and feats.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.engine.dice import ability_modifier, proficiency_bonus, roll_d20, RollResult

# Reuse the general-purpose character helpers from the saving-throws engine
# (DRY — these operate on the same character-like shape every engine uses).
from app.engine.saving_throws import get_character_level, get_ability_score


# --------------------------------------------------------------------------- #
# Abilities
# --------------------------------------------------------------------------- #

ABILITIES = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")


# --------------------------------------------------------------------------- #
# Skill → ability mapping (all 18 PHB skills)
# --------------------------------------------------------------------------- #

SKILL_ABILITIES: dict[str, str] = {
    # Strength
    "athletics": "strength",
    # Dexterity
    "acrobatics": "dexterity",
    "sleight_of_hand": "dexterity",
    "stealth": "dexterity",
    # Intelligence
    "arcana": "intelligence",
    "history": "intelligence",
    "investigation": "intelligence",
    "nature": "intelligence",
    "religion": "intelligence",
    # Wisdom
    "animal_handling": "wisdom",
    "insight": "wisdom",
    "medicine": "wisdom",
    "perception": "wisdom",
    "survival": "wisdom",
    # Charisma
    "deception": "charisma",
    "intimidation": "charisma",
    "performance": "charisma",
    "persuasion": "charisma",
}

ALL_SKILLS: tuple[str, ...] = tuple(SKILL_ABILITIES.keys())


def skill_ability(skill: str) -> str:
    """Return the ability a skill is keyed to (raises ValueError if unknown)."""
    skill = skill.lower()
    if skill not in SKILL_ABILITIES:
        raise ValueError(f"Unknown skill: {skill}")
    return SKILL_ABILITIES[skill]


def skills_for_ability(ability: str) -> list[str]:
    """Return all skills keyed to a given ability."""
    ability = ability.lower()
    return [s for s, a in SKILL_ABILITIES.items() if a == ability]


# --------------------------------------------------------------------------- #
# Class skill proficiency (count + candidate list)
# --------------------------------------------------------------------------- #

# "any" means the class may choose from any of the 18 skills (Bard).
_CLASS_SKILLS: dict[str, dict] = {
    "barbarian": {"count": 2, "skills": ["animal_handling", "athletics", "intimidation", "nature", "perception", "survival"]},
    "bard": {"count": 3, "skills": "any"},
    "cleric": {"count": 2, "skills": ["history", "insight", "medicine", "persuasion", "religion"]},
    "druid": {"count": 2, "skills": ["arcana", "animal_handling", "insight", "medicine", "nature", "perception", "religion"]},
    "fighter": {"count": 2, "skills": ["acrobatics", "animal_handling", "athletics", "history", "insight", "intimidation", "perception", "survival"]},
    "monk": {"count": 2, "skills": ["acrobatics", "athletics", "history", "insight", "religion", "stealth"]},
    "paladin": {"count": 2, "skills": ["athletics", "insight", "intimidation", "medicine", "persuasion", "religion"]},
    "ranger": {"count": 3, "skills": ["animal_handling", "athletics", "insight", "investigation", "nature", "perception", "stealth", "survival"]},
    "rogue": {"count": 4, "skills": ["acrobatics", "athletics", "deception", "insight", "intimidation", "investigation", "perception", "performance", "persuasion", "sleight_of_hand", "stealth"]},
    "sorcerer": {"count": 2, "skills": ["arcana", "deception", "insight", "intimidation", "persuasion", "religion"]},
    "warlock": {"count": 2, "skills": ["arcana", "deception", "history", "intimidation", "investigation", "nature", "religion"]},
    "wizard": {"count": 2, "skills": ["arcana", "history", "insight", "investigation", "medicine", "religion"]},
}


def get_class_skill_info(char_class: str) -> dict:
    """Get the skill-choice info for a class: {'count': int, 'skills': list|'any'}.

    For unknown classes returns count 0 with an empty candidate list.
    """
    return _CLASS_SKILLS.get(char_class.lower(), {"count": 0, "skills": []})


def get_class_skill_candidates(char_class: str) -> list[str]:
    """Get the list of candidate skills a class may choose proficiency in.

    For the Bard ("any") returns all 18 skills.
    """
    info = get_class_skill_info(char_class)
    skills = info["skills"]
    if skills == "any":
        return list(ALL_SKILLS)
    return list(skills)


def get_class_skill_count(char_class: str) -> int:
    """Get the number of skill proficiencies a class grants."""
    return get_class_skill_info(char_class)["count"]


# --------------------------------------------------------------------------- #
# Background skill proficiency
# --------------------------------------------------------------------------- #
# Derived from the canonical backgrounds registry (app.engine.backgrounds) so
# the skill table never drifts from the full background definitions. The
# module-level dict is retained for backward compatibility (tests iterate it
# directly). Importing backgrounds here is cycle-free: backgrounds imports only
# the inventory engine, which has no engine-layer dependencies.
from app.engine.backgrounds import BACKGROUNDS as _BACKGROUNDS_REGISTRY

_BACKGROUND_SKILLS: dict[str, list[str]] = {
    bg_id: list(bg.skill_proficiencies)
    for bg_id, bg in _BACKGROUNDS_REGISTRY.items()
}


def get_background_skills(background: str) -> list[str]:
    """Get the 2 skills granted by a background (empty list if unknown)."""
    return list(_BACKGROUND_SKILLS.get((background or "").lower(), []))


# --------------------------------------------------------------------------- #
# Expertise
# --------------------------------------------------------------------------- #

# Class → list of levels at which an Expertise slot pair is gained.
# Rogue: 2 at level 1, 2 more at level 6 (4 total). Bard: 2 at level 3, 2 more
# at level 10 (4 total).
_EXPERTISE_LEVELS: dict[str, list[int]] = {
    "rogue": [1, 6],
    "bard": [3, 10],
}

# Number of skills per Expertise "grant" (always 2 per slot pair in 5e).
EXPERTISE_PER_GRANT = 2


def get_expertise_grants(char_class: str, level: int) -> int:
    """Number of Expertise skill *pairs* a class has unlocked by ``level``.

    Returns the count of grant-levels reached. Multiply by
    :data:`EXPERTISE_PER_GRANT` for the number of skills.
    """
    levels = _EXPERTISE_LEVELS.get(char_class.lower(), [])
    return sum(1 for lv in levels if level >= lv)


def get_expertise_slot_count(char_class: str, level: int) -> int:
    """Total number of skills a character may apply Expertise to."""
    return get_expertise_grants(char_class, level) * EXPERTISE_PER_GRANT


def can_have_expertise(char_class: str, level: int) -> bool:
    """Whether a class/level combo offers any Expertise slots."""
    return get_expertise_slot_count(char_class, level) > 0


def get_multiclass_expertise_slots(classes: dict[str, int]) -> int:
    """Total Expertise slots across all classes (sum of per-class slots).

    Each class's Expertise is tracked by that class's own levels (per the PHB
    multiclassing guidance that class features scale with class level, not total).
    """
    total = 0
    for cls_name, cls_level in classes.items():
        total += get_expertise_slot_count(cls_name, cls_level)
    return total


# --------------------------------------------------------------------------- #
# Character → class-name helpers
# --------------------------------------------------------------------------- #

def _iter_classes(character: Any) -> list[str]:
    """Yield the character's class names (handles single + multiclass shapes)."""
    import json
    # Prefer explicit classes dict
    if hasattr(character, "classes_dict") and character.classes_dict:
        return [c.lower() for c in character.classes_dict.keys()]
    if hasattr(character, "classes"):
        try:
            classes = json.loads(character.classes or "{}")
            if classes:
                return [c.lower() for c in classes.keys()]
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    # Fall back to single class
    if hasattr(character, "char_class"):
        return [(character.char_class or "commoner").lower()]
    if hasattr(character, "primary_class"):
        return [(character.primary_class or "commoner").lower()]
    return []


# --------------------------------------------------------------------------- #
# JSON-list parsing helper
# --------------------------------------------------------------------------- #

def _parse_json_list(raw: Any) -> list:
    """Parse a JSON-encoded list from a model column or return []."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    import json
    try:
        val = json.loads(raw)
        if isinstance(val, list):
            return val
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return []


# --------------------------------------------------------------------------- #
# Character skill proficiency / expertise queries
# --------------------------------------------------------------------------- #

def get_skill_proficiencies(character: Any) -> set[str]:
    """All skills a character is proficient in.

    If the character has explicitly chosen skills (the ``skill_proficiencies``
    JSON column), those are used directly. Otherwise proficiencies are
    auto-derived as a sensible default: the first N skills from each class's
    candidate list plus all background skills. (This keeps the engine working
    for pre-existing characters that predate the skill columns.)
    """
    stored = _parse_json_list(getattr(character, "skill_proficiencies", None))
    if stored:
        return {s.lower() for s in stored if isinstance(s, str)}

    # Auto-derive defaults for backward compatibility
    prof: set[str] = set()
    for cls_name in _iter_classes(character):
        candidates = get_class_skill_candidates(cls_name)
        count = get_class_skill_count(cls_name)
        if candidates and count:
            prof.update(candidates[:count])
    bg = getattr(character, "background", "") or ""
    prof.update(get_background_skills(bg))
    return prof


def get_skill_expertise(character: Any) -> set[str]:
    """Skills a character has Expertise in (double proficiency bonus)."""
    stored = _parse_json_list(getattr(character, "skill_expertise", None))
    return {s.lower() for s in stored if isinstance(s, str)}


def is_proficient(skill: str, character: Any) -> bool:
    return skill.lower() in get_skill_proficiencies(character)


def has_expertise(skill: str, character: Any) -> bool:
    return skill.lower() in get_skill_expertise(character)


# --------------------------------------------------------------------------- #
# Feat-based skill proficiency / expertise
# --------------------------------------------------------------------------- #

def _feat_skill_bonuses(character: Any) -> tuple[set[str], set[str]]:
    """Return (proficiencies, expertise) granted by feats.

    Recognised feat effect keys:
      - ``skill_proficiency``: str or list[str]
      - ``skill_proficiencies``: list[str]
      - ``expertise``: str or list[str]   (e.g., Skill Expert feat)
    """
    import json
    feats_raw = getattr(character, "feats", None)
    if not feats_raw:
        return set(), set()
    try:
        feats = json.loads(feats_raw)
    except (json.JSONDecodeError, ValueError, TypeError):
        return set(), set()

    profs: set[str] = set()
    exp: set[str] = set()
    if not isinstance(feats, list):
        return profs, exp
    for feat in feats:
        if not isinstance(feat, dict):
            continue
        name = (feat.get("name", "") or "").lower()
        effects = feat.get("effects", {}) if isinstance(feat.get("effects"), dict) else {}

        def _norm(val):
            if isinstance(val, str):
                return [val.lower()]
            if isinstance(val, list):
                return [str(v).lower() for v in val]
            return []

        profs.update(s for s in _norm(effects.get("skill_proficiency")) if s in SKILL_ABILITIES)
        profs.update(s for s in _norm(effects.get("skill_proficiencies")) if s in SKILL_ABILITIES)
        exp.update(s for s in _norm(effects.get("expertise")) if s in SKILL_ABILITIES)

        # Skilled feat: grants any 3 skill proficiencies (we represent the
        # chosen skills under skill_proficiency in the effects payload).
        if "skilled" in name:
            profs.update(s for s in _norm(effects.get("skill_proficiency")) if s in SKILL_ABILITIES)
    return profs, exp


# --------------------------------------------------------------------------- #
# Combined character proficiency/expertise (class + background + feats)
# --------------------------------------------------------------------------- #

def get_all_skill_proficiencies(character: Any) -> set[str]:
    """Proficiencies from chosen/auto skills UNION feat-granted proficiencies."""
    profs = get_skill_proficiencies(character)
    feat_profs, _ = _feat_skill_bonuses(character)
    return profs | feat_profs


def get_all_skill_expertise(character: Any) -> set[str]:
    """Expertise from stored column UNION feat-granted expertise."""
    exp = get_skill_expertise(character)
    _, feat_exp = _feat_skill_bonuses(character)
    return exp | feat_exp


# --------------------------------------------------------------------------- #
# Skill modifier calculation
# --------------------------------------------------------------------------- #

def calculate_skill_modifier(
    skill: str,
    character: Any,
    proficiencies: Optional[set[str]] = None,
    expertise: Optional[set[str]] = None,
) -> int:
    """Static skill modifier = ability_mod + proficiency_bonus (×2 if Expertise)."""
    skill = skill.lower()
    if skill not in SKILL_ABILITIES:
        raise ValueError(f"Unknown skill: {skill}")

    if proficiencies is None:
        proficiencies = get_all_skill_proficiencies(character)
    if expertise is None:
        expertise = get_all_skill_expertise(character)

    ability = SKILL_ABILITIES[skill]
    score = get_ability_score(character, ability)
    mod = ability_modifier(score)

    bonus = 0
    if skill in proficiencies:
        level = get_character_level(character)
        pb = proficiency_bonus(level)
        bonus += pb
        if skill in expertise:
            bonus += pb  # Expertise doubles the proficiency bonus

    return mod + bonus


def calculate_skill_breakdown(
    skill: str,
    character: Any,
    proficiencies: Optional[set[str]] = None,
    expertise: Optional[set[str]] = None,
) -> dict:
    """Return a detailed breakdown of how a skill modifier is computed."""
    skill = skill.lower()
    if proficiencies is None:
        proficiencies = get_all_skill_proficiencies(character)
    if expertise is None:
        expertise = get_all_skill_expertise(character)

    ability = SKILL_ABILITIES[skill]
    score = get_ability_score(character, ability)
    mod = ability_modifier(score)
    level = get_character_level(character)
    pb = proficiency_bonus(level)
    proficient = skill in proficiencies
    expert = skill in expertise

    prof_mult = 0
    if proficient:
        prof_mult = 2 if expert else 1

    return {
        "skill": skill,
        "ability": ability,
        "ability_score": score,
        "ability_modifier": mod,
        "proficient": proficient,
        "expertise": expert,
        "proficiency_bonus": pb * prof_mult,
        "modifier": mod + pb * prof_mult,
        "level": level,
    }


# --------------------------------------------------------------------------- #
# Passive scores
# --------------------------------------------------------------------------- #

def calculate_passive_score(
    skill: str,
    character: Any,
    advantage: bool = False,
    disadvantage: bool = False,
    proficiencies: Optional[set[str]] = None,
    expertise: Optional[set[str]] = None,
) -> int:
    """Passive score = 10 + skill modifier (+5 advantage / -5 disadvantage).

    Used most often for passive Perception (10 + Wis mod + prof), but works for
    any skill. Advantage/disadvantage on the underlying check shifts the passive
    score by ±5 (per PHB).
    """
    modifier = calculate_skill_modifier(skill, character, proficiencies, expertise)
    base = 10 + modifier
    # adv + disadv cancel
    if advantage and not disadvantage:
        base += 5
    elif disadvantage and not advantage:
        base -= 5
    return base


def calculate_all_passive_scores(character: Any) -> dict[str, int]:
    """Passive scores for the most-used passive skills: Perception, Investigation, Insight."""
    return {
        "perception": calculate_passive_score("perception", character),
        "investigation": calculate_passive_score("investigation", character),
        "insight": calculate_passive_score("insight", character),
    }


# --------------------------------------------------------------------------- #
# Condition effects on skill checks
# --------------------------------------------------------------------------- #

def check_skill_advantage(skill: str, conditions: list[str]) -> bool:
    """Whether a skill check gains advantage from conditions (none by default)."""
    return False


def check_skill_disadvantage(skill: str, conditions: list[str]) -> bool:
    """Whether a skill check suffers disadvantage from conditions.

    - poisoned → disadvantage on ALL skill checks (ability checks).
    - restrained → disadvantage on Dexterity-based skills.
    - blinded → disadvantage on Perception (and sight-based checks).
    - deafened → disadvantage on Perception (and hearing-based checks).
    """
    skill = skill.lower()
    if not conditions:
        return False
    cond = {c.lower() for c in conditions}

    # Poisoned: disadvantage on all ability checks
    if "poisoned" in cond:
        return True

    ability = SKILL_ABILITIES.get(skill)
    # Restrained: disadvantage on Dex-based skill checks
    if "restrained" in cond and ability == "dexterity":
        return True

    # Blinded / deafened: disadvantage on Perception
    if skill == "perception" and ("blinded" in cond or "deafened" in cond):
        return True

    return False


# --------------------------------------------------------------------------- #
# Skill check execution
# --------------------------------------------------------------------------- #

@dataclass
class SkillCheckResult:
    """Result of a skill check."""
    skill: str
    ability: str
    roll: RollResult
    modifier: int
    total: int
    success: bool
    dc: int
    proficient: bool
    expertise: bool
    advantage: bool = False
    disadvantage: bool = False
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "skill": self.skill,
            "ability": self.ability,
            "roll": self.roll.description,
            "rolls": self.roll.rolls,
            "modifier": self.modifier,
            "total": self.total,
            "success": self.success,
            "dc": self.dc,
            "proficient": self.proficient,
            "expertise": self.expertise,
            "advantage": self.advantage,
            "disadvantage": self.disadvantage,
            "description": self.description,
        }


def roll_skill_check(
    skill: str,
    character: Any,
    dc: int,
    advantage: bool = False,
    disadvantage: bool = False,
    conditions: Optional[list[str]] = None,
    proficiencies: Optional[set[str]] = None,
    expertise: Optional[set[str]] = None,
) -> SkillCheckResult:
    """Roll a skill check for a character against a DC.

    Args:
        skill: Skill name (e.g., "stealth").
        character: Character-like object with level, abilities, classes, etc.
        dc: Difficulty Class to meet or beat.
        advantage: Explicit advantage override.
        disadvantage: Explicit disadvantage override.
        conditions: Active conditions (for disadvantage effects).
        proficiencies: Pre-computed proficiency set (optional optimization).
        expertise: Pre-computed expertise set (optional optimization).

    Returns:
        A :class:`SkillCheckResult`.
    """
    skill = skill.lower()
    if skill not in SKILL_ABILITIES:
        raise ValueError(f"Unknown skill: {skill}")

    if conditions is None:
        conditions = []

    if proficiencies is None:
        proficiencies = get_all_skill_proficiencies(character)
    if expertise is None:
        expertise = get_all_skill_expertise(character)

    # Merge explicit advantage/disadvantage with condition-driven ones.
    has_advantage = advantage and not disadvantage
    has_disadvantage = disadvantage and not advantage
    if check_skill_disadvantage(skill, conditions):
        has_disadvantage = True
        # Per 5e, if you have any source of disadvantage and none of advantage,
        # you roll with disadvantage. If you ALSO have advantage, they cancel.
        if has_advantage:
            has_advantage = False
            has_disadvantage = False

    modifier = calculate_skill_modifier(skill, character, proficiencies, expertise)
    proficient = skill in proficiencies
    expert = skill in expertise

    roll_result = roll_d20(modifier=modifier, advantage=has_advantage, disadvantage=has_disadvantage)
    success = roll_result.total >= dc

    # Human-readable description
    parts = [skill.replace("_", " ").title()]
    if has_advantage:
        parts.append("(advantage)")
    elif has_disadvantage:
        parts.append("(disadvantage)")
    parts.append(f"check DC {dc}")
    description = " ".join(parts)

    return SkillCheckResult(
        skill=skill,
        ability=SKILL_ABILITIES[skill],
        roll=roll_result,
        modifier=modifier,
        total=roll_result.total,
        success=success,
        dc=dc,
        proficient=proficient,
        expertise=expert,
        advantage=has_advantage,
        disadvantage=has_disadvantage,
        description=description,
    )


# --------------------------------------------------------------------------- #
# Difficulty Class reference (PHB p.58 / DMG)
# --------------------------------------------------------------------------- #

DIFFICULTY_CLASSES: dict[str, int] = {
    "very_easy": 5,
    "easy": 10,
    "medium": 15,
    "hard": 20,
    "very_hard": 25,
    "nearly_impossible": 30,
}


def difficulty_class(name: str) -> int:
    """Look up a DC by descriptive name (case-insensitive)."""
    key = name.lower().replace(" ", "_")
    if key not in DIFFICULTY_CLASSES:
        raise ValueError(f"Unknown difficulty: {name}")
    return DIFFICULTY_CLASSES[key]
