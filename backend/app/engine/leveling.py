"""
Leveling engine — XP thresholds, level-ups, HP growth, and ability increases.

Implements a faithful-but-simplified DnD 5e advancement system:

- **XP thresholds** (the standard 5e *cumulative* XP table, levels 1–20).
  ``level_for_xp`` maps a raw XP total to a character level; ``level_progress``
  reports how far through the current level a character is.
- **Hit-point growth** on level-up. By default a character gains the *fixed
  average* of their class hit die + CON modifier per level (the deterministic
  variant used by most organized play and very easy to test). Callers may pass
  explicit per-level rolls to mimic rolling at the table.
- **Ability Score Improvements (ASI).** Most classes gain an ASI at levels
  4/8/12/16/19; Fighters gain extra ones at 6 and 14. Each ASI can raise one
  ability by 2 or two abilities by 1 (capped at 20).
- **Proficiency bonus** is derived from level (delegated to ``app.engine.dice``)
  so it automatically tracks the character's level wherever it is read.
- **Class features.** A representative milestone feature table per class so the
  UI / DM can narrate what a character unlocks as they advance.

The engine is pure (no DB, no LLM) so it is trivially unit-testable. The API
layer feeds real character data in and persists the results.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.engine.dice import proficiency_bonus


# ---------------------------------------------------------------------------
# XP thresholds — cumulative XP required to *reach* a given level.
# Index 0 corresponds to level 1 (0 XP). Level 20 is the cap.
# Source: DnD 5e Player's Handbook advancement table.
# ---------------------------------------------------------------------------

_XP_TO_REACH_LEVEL: list[int] = [
    # level 1  2     3      4       5        6        7         8
           0,  300,  900,   2_700,  6_500,   14_000,  23_000,   34_000,
    # level 9     10      11      12       13       14       15
           48_000, 64_000, 85_000, 100_000, 120_000, 140_000, 165_000,
    # level 16      17       18       19       20
           195_000, 225_000, 265_000, 305_000, 355_000,
]

MAX_LEVEL = 20
MIN_LEVEL = 1


def xp_for_level(level: int) -> int:
    """Cumulative XP required to reach ``level``.

    Level 1 requires 0 XP. Levels below 1 clamp to 1; levels above the cap
    clamp to 20.
    """
    level = max(MIN_LEVEL, min(MAX_LEVEL, level))
    return _XP_TO_REACH_LEVEL[level - 1]


def level_for_xp(xp: int) -> int:
    """The character level achieved at the given cumulative XP total.

    XP below 0 is treated as 0; XP past the level-20 threshold is capped at 20.
    """
    if xp <= 0:
        return MIN_LEVEL
    for level in range(MAX_LEVEL, MIN_LEVEL, -1):
        if xp >= xp_for_level(level):
            return level
    return MIN_LEVEL


def xp_to_next_level(level: int) -> Optional[int]:
    """XP needed to advance from ``level`` to ``level + 1``.

    Returns ``None`` if ``level`` is already at the cap (20).
    """
    level = max(MIN_LEVEL, min(MAX_LEVEL, level))
    if level >= MAX_LEVEL:
        return None
    return xp_for_level(level + 1) - xp_for_level(level)


def level_progress(xp: int) -> dict:
    """Detailed progress breakdown for a character with ``xp`` total XP.

    Returns a dict with: ``level``, ``xp``, the threshold for the current
    level (``level_start_xp``), the threshold for the next level
    (``next_level_xp`` or ``None`` at cap), XP earned into the current level
    (``xp_into_level``), XP still required to level (``xp_to_next`` or
    ``None``), and a 0–1 ``progress`` fraction toward the next level.
    """
    level = level_for_xp(xp)
    start = xp_for_level(level)
    next_threshold = xp_for_level(level + 1) if level < MAX_LEVEL else None

    xp_into = max(0, xp - start)
    if next_threshold is not None:
        span = next_threshold - start
        xp_to_next = max(0, next_threshold - xp)
        progress = (xp_into / span) if span > 0 else 1.0
    else:
        xp_to_next = None
        progress = 1.0

    return {
        "level": level,
        "xp": xp,
        "level_start_xp": start,
        "next_level_xp": next_threshold,
        "xp_into_level": xp_into,
        "xp_to_next": xp_to_next,
        "progress": progress,
    }


# ---------------------------------------------------------------------------
# Hit dice and HP growth
# ---------------------------------------------------------------------------

# Hit die (sides) per class, keyed by lowercase class name.
CLASS_HIT_DICE: dict[str, int] = {
    "barbarian": 12,
    "fighter": 10,
    "paladin": 10,
    "ranger": 10,
    "bard": 8,
    "cleric": 8,
    "druid": 8,
    "monk": 8,
    "rogue": 8,
    "warlock": 8,
    "sorcerer": 6,
    "wizard": 6,
}


def hit_die_for_class(char_class: str) -> int:
    """The hit-die size for a class (defaults to d8 for unknown classes)."""
    return CLASS_HIT_DICE.get(char_class.lower(), 8)


def average_hp_gain(hit_die: int, con_mod: int) -> int:
    """HP gained for one level using the fixed-average rule.

    The fixed average of a die is ``die // 2 + 1`` (e.g. d8 -> 5, d10 -> 6,
    d12 -> 7, d6 -> 4). Each level grants at least 1 HP.
    """
    gained = (hit_die // 2 + 1) + con_mod
    return max(1, gained)


def hp_gained_for_levels(
    from_level: int,
    to_level: int,
    char_class: str,
    con_mod: int,
    rolls: Optional[list[int]] = None,
) -> int:
    """Total HP gained when advancing from ``from_level`` to ``to_level``.

    ``from_level`` is inclusive of the starting level (i.e. gains are counted
    for levels ``from_level + 1`` .. ``to_level``). If ``rolls`` is provided it
    must contain one entry per level gained and is used instead of the fixed
    average (each roll is the raw d-hit-die result before the CON modifier).
    """
    if to_level <= from_level:
        return 0

    hd = hit_die_for_class(char_class)
    levels_gained = to_level - from_level

    if rolls is not None:
        if len(rolls) != levels_gained:
            raise ValueError(
                f"Expected {levels_gained} hit-die roll(s), got {len(rolls)}"
            )
        total = 0
        for roll in rolls:
            total += max(1, roll + con_mod)
        return total

    return average_hp_gain(hd, con_mod) * levels_gained


# ---------------------------------------------------------------------------
# Ability Score Improvements
# ---------------------------------------------------------------------------

# Levels at which the standard classes gain an ASI.
_STANDARD_ASI_LEVELS: list[int] = [4, 8, 12, 16, 19]
# Fighters gain ASIs more often.
_FIGHTER_ASI_LEVELS: list[int] = [4, 6, 8, 12, 14, 16, 19]
# Rogues gain an extra ASI at 10 (standard 5e).
_ROGUE_ASI_LEVELS: list[int] = [4, 8, 10, 12, 16, 19]


def asi_levels(char_class: str) -> list[int]:
    """Levels at which a class earns an Ability Score Improvement."""
    cls = char_class.lower()
    if cls == "fighter":
        return list(_FIGHTER_ASI_LEVELS)
    if cls == "rogue":
        return list(_ROGUE_ASI_LEVELS)
    return list(_STANDARD_ASI_LEVELS)


def is_asi_level(level: int, char_class: str) -> bool:
    """True if this exact level grants an ASI for the class."""
    return level in asi_levels(char_class)


def asi_count_through(level: int, char_class: str) -> int:
    """How many ASIs a class has earned by reaching ``level`` (inclusive)."""
    level = max(MIN_LEVEL, min(MAX_LEVEL, level))
    return sum(1 for lvl in asi_levels(char_class) if lvl <= level)


def asi_available(level: int, char_class: str, asi_used: int) -> int:
    """ASIs available to spend = earned through level − already spent."""
    return max(0, asi_count_through(level, char_class) - max(0, asi_used))


# Standard ability score bounds.
MIN_ABILITY_SCORE = 1
MAX_ABILITY_SCORE = 20


def clamp_score(score: int) -> int:
    """Clamp an ability score to the legal 1–20 range."""
    return max(MIN_ABILITY_SCORE, min(MAX_ABILITY_SCORE, score))


@dataclass
class ASIChoice:
    """A single ability-score bump choice.

    ``amount`` is typically 1 or 2 and is applied to ``ability``. Two ASIChoice
    objects (each amount=1) together consume one ASI instance ("+1 to two
    abilities"). The API validates that the total amount per ASI instance is 2.
    """
    ability: str  # one of: strength, dexterity, constitution, intelligence, wisdom, charisma
    amount: int = 1


VALID_ABILITIES = (
    "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma",
)


@dataclass
class ASIResult:
    """Outcome of applying an ASI instance."""
    success: bool
    message: str
    applied: list[ASIChoice] = field(default_factory=list)
    remaining: int = 0


def apply_asi(
    abilities: dict[str, int],
    choices: list[ASIChoice],
    level: int,
    char_class: str,
    asi_used: int,
) -> ASIResult:
    """Validate and apply an ASI instance against an ability-score set.

    A single ASI instance grants exactly 2 points, distributed as one ``+2`` to
    a single ability OR two ``+1``s to two abilities. Scores are clamped to 20.

    Returns an :class:`ASIResult`. The returned ``applied`` list mirrors the
    input choices with clamped amounts; ``remaining`` is how many ASI instances
    are still unspent after this one. The caller is responsible for persisting
    the new ability dict and ``asi_used + 1``.
    """
    remaining = asi_available(level, char_class, asi_used)
    if remaining <= 0:
        return ASIResult(False, "No ASI instances available to spend")

    total = sum(c.amount for c in choices)
    if total != 2:
        return ASIResult(
            False,
            "An ASI instance must distribute exactly 2 points "
            "(one +2 or two +1s)",
        )

    for c in choices:
        if c.amount < 1:
            return ASIResult(False, f"Invalid amount {c.amount} for {c.ability}")
        if c.ability not in VALID_ABILITIES:
            return ASIResult(False, f"Unknown ability: {c.ability}")

    # Apply (with clamping). Detect per-ability over-cap.
    new_scores = dict(abilities)
    applied: list[ASIChoice] = []
    for c in choices:
        before = new_scores.get(c.ability, 10)
        after = clamp_score(before + c.amount)
        if after == before and c.amount > 0:
            return ASIResult(
                False,
                f"{c.ability} is already at the cap ({MAX_ABILITY_SCORE})",
            )
        new_scores[c.ability] = after
        applied.append(ASIChoice(ability=c.ability, amount=after - before))

    return ASIResult(
        success=True,
        message="Ability Score Improvement applied",
        applied=applied,
        remaining=remaining - 1,
    )


# ---------------------------------------------------------------------------
# Class features (milestone table, representative subset for flavor)
# ---------------------------------------------------------------------------

# Feature name -> short description, keyed by (class, level).
# A simplified-but-evocative subset of the 5e class progression.
_CLASS_FEATURES: dict[tuple[str, int], str] = {
    # Fighter
    ("fighter", 1): "Fighting Style, Second Wind",
    ("fighter", 2): "Action Surge",
    ("fighter", 3): "Martial Archetype",
    ("fighter", 5): "Extra Attack",
    ("fighter", 9): "Indomitable",
    ("fighter", 11): "Extra Attack (2)",
    ("fighter", 20): "Extra Attack (3)",
    # Wizard
    ("wizard", 1): "Arcane Recovery, Spellcasting",
    ("wizard", 2): "Arcane Tradition",
    ("wizard", 3): "Cantrip Formulas",
    ("wizard", 18): "Spell Mastery",
    ("wizard", 20): "Signature Spells",
    # Rogue
    ("rogue", 1): "Sneak Attack 1d6, Expertise, Thieves' Cant",
    ("rogue", 2): "Cunning Action",
    ("rogue", 3): "Roguish Archetype",
    ("rogue", 5): "Uncanny Dodge",
    ("rogue", 7): "Evasion",
    # Cleric
    ("cleric", 1): "Divine Domain, Spellcasting",
    ("cleric", 2): "Channel Divinity",
    ("cleric", 5): "Destroy Undead",
    ("cleric", 10): "Divine Intervention",
    # Barbarian
    ("barbarian", 1): "Rage, Unarmored Defense",
    ("barbarian", 2): "Reckless Attack, Danger Sense",
    ("barbarian", 3): "Primal Path",
    ("barbarian", 5): "Extra Attack, Fast Movement",
    ("barbarian", 9): "Brutal Critical",
    # Paladin
    ("paladin", 1): "Divine Sense, Lay on Hands",
    ("paladin", 2): "Fighting Style, Spellcasting, Divine Smite",
    ("paladin", 3): "Sacred Oath",
    ("paladin", 5): "Extra Attack",
    # Ranger
    ("ranger", 1): "Favored Enemy, Natural Explorer",
    ("ranger", 2): "Fighting Style, Spellcasting",
    ("ranger", 3): "Ranger Archetype, Primeval Awareness",
    ("ranger", 5): "Extra Attack",
    # Monk
    ("monk", 1): "Martial Arts, Unarmored Defense",
    ("monk", 2): "Ki, Unarmored Movement",
    ("monk", 3): "Monastic Tradition, Deflect Missiles",
    ("monk", 5): "Extra Attack, Stunning Strike",
    # Bard
    ("bard", 1): "Bardic Inspiration, Spellcasting",
    ("bard", 2): "Jack of All Trades, Song of Rest",
    ("bard", 3): "Bard College, Expertise",
    ("bard", 5): "Font of Inspiration",
    # Druid
    ("druid", 1): "Druidic, Spellcasting",
    ("druid", 2): "Wild Shape",
    ("druid", 3): "Druid Circle",
    # Sorcerer
    ("sorcerer", 1): "Sorcerous Origins Spellcasting",
    ("sorcerer", 2): "Font of Magic",
    ("sorcerer", 3): "Metamagic",
    ("sorcerer", 5): "Metamagic (additional)",
    # Warlock
    ("warlock", 1): "Otherworldly Patron, Pact Magic",
    ("warlock", 2): "Eldritch Invocations",
    ("warlock", 3): "Pact Boon",
    ("warlock", 5): "Thirsting Blade (if pact of the blade)",
}


def features_at_level(char_class: str, level: int) -> str:
    """Class features gained at exactly ``level`` (empty string if none)."""
    return _CLASS_FEATURES.get((char_class.lower(), level), "")


def features_through_level(char_class: str, level: int) -> list[tuple[int, str]]:
    """All ``(level, feature)`` pairs a class has earned through ``level``."""
    cls = char_class.lower()
    level = max(MIN_LEVEL, min(MAX_LEVEL, level))
    out: list[tuple[int, str]] = []
    for (c, lvl), feat in _CLASS_FEATURES.items():
        if c == cls and lvl <= level:
            out.append((lvl, feat))
    out.sort(key=lambda t: t[0])
    return out


# ---------------------------------------------------------------------------
# Level-up resolution
# ---------------------------------------------------------------------------

@dataclass
class LevelUpResult:
    """The outcome of applying an XP delta to a character."""
    leveled_up: bool
    from_level: int
    to_level: int
    levels_gained: int
    xp: int
    hp_gained: int
    proficiency_before: int
    proficiency_after: int
    proficiency_changed: bool
    asi_unlocked: bool          # a new ASI level was crossed
    asi_available: int          # ASI instances now available to spend
    new_features: list[tuple[int, str]] = field(default_factory=list)


def apply_xp(
    char_class: str,
    level: int,
    xp_before: int,
    xp_after: int,
    con_mod: int,
    asi_used: int,
    rolls: Optional[list[int]] = None,
) -> LevelUpResult:
    """Resolve what happens when a character's XP changes.

    Does *not* mutate any character object — it returns a :class:`LevelUpResult`
    describing the changes so the caller (typically the API) can persist them:
    set ``character.level = to_level``, ``character.xp = xp_after``, increase
    max/current HP by ``hp_gained``, etc. ASIs are *not* spent automatically —
    they are reported via ``asi_available`` so the player can choose.
    """
    from_level = max(MIN_LEVEL, min(MAX_LEVEL, level))
    to_level = level_for_xp(xp_after)

    hp_gained = hp_gained_for_levels(
        from_level=from_level,
        to_level=to_level,
        char_class=char_class,
        con_mod=con_mod,
        rolls=rolls,
    )

    prof_before = proficiency_bonus(from_level)
    prof_after = proficiency_bonus(to_level)

    new_features: list[tuple[int, str]] = []
    for lvl in range(from_level + 1, to_level + 1):
        feat = features_at_level(char_class, lvl)
        if feat:
            new_features.append((lvl, feat))

    # An ASI is "unlocked" if any ASI level falls strictly after from_level
    # and at or before to_level.
    asi_lvls = asi_levels(char_class)
    asi_unlocked = any(from_level < lvl <= to_level for lvl in asi_lvls)

    leveled_up = to_level > from_level

    return LevelUpResult(
        leveled_up=leveled_up,
        from_level=from_level,
        to_level=to_level,
        levels_gained=to_level - from_level,
        xp=xp_after,
        hp_gained=hp_gained,
        proficiency_before=prof_before,
        proficiency_after=prof_after,
        proficiency_changed=prof_before != prof_after,
        asi_unlocked=asi_unlocked,
        asi_available=asi_available(to_level, char_class, asi_used),
        new_features=new_features,
    )
