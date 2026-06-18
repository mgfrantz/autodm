"""
Tool proficiency system engine — DnD 5e tools, proficiency, and checks.

Implements faithful DnD 5e tool mechanics (PHB + Xanathar's Guide to Everything):

- **Tool registry**: every standard 5e tool grouped into categories
  (artisan's tools, gaming sets, musical instruments, kits, and vehicles),
  each with a default ability for checks and a short description.
- **Class tool proficiency**: each class grants fixed tools and/or tool
  *choices* (e.g., Bard → 3 musical instruments, Rogue → thieves' tools,
  Monk → 1 artisan's tool or instrument, Druid → herbalism kit).
- **Background tool proficiency**: backgrounds grant fixed tools and/or
  choices (e.g., Criminal → thieves' tools + 1 gaming set, Sailor →
  navigator's tools + water vehicles, Guild Artisan → 1 artisan's tool).
- **Tool modifier**: ability_modifier + proficiency_bonus when proficient.
- **Tool check**: d20 + tool modifier vs DC, with advantage/disadvantage
  and condition effects (poisoned → disadvantage on all; restrained → Dex).
- **Xanathar's combined checks**: when proficient in both a relevant skill
  *and* a relevant tool for the same task, the check gains advantage (a
  common house interpretation) — modelled by :func:`combined_check_advantage`.

The engine is pure (no DB, no LLM) and operates on a character-like object
that exposes: level, abilities, classes (dict or primary_class string),
background, optional ``tool_proficiencies`` JSON column, and feats.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.engine.dice import ability_modifier, proficiency_bonus, roll_d20, RollResult

# Reuse the general-purpose character helpers (DRY — same shape every engine
# uses) and the JSON-list / class-iteration helpers from the skills engine.
from app.engine.saving_throws import get_character_level, get_ability_score
from app.engine.skills import _iter_classes, _parse_json_list


# --------------------------------------------------------------------------- #
# Abilities
# --------------------------------------------------------------------------- #

ABILITIES = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")


# --------------------------------------------------------------------------- #
# Tool definition + registry
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ToolDef:
    """A single DnD 5e tool with its category, default ability, and description."""
    id: str            # snake_case unique id (the proficiency key)
    name: str          # display name
    category: str      # artisan | gaming_set | musical_instrument | kit | vehicle
    ability: str       # default ability for checks
    description: str = ""


# Artisan's tools — the 16 PHB sets. Crafting/knowledge → Intelligence.
_ARTISAN_TOOLS = [
    ("alchemists_supplies", "Alchemist's Supplies"),
    ("brewers_supplies", "Brewer's Supplies"),
    ("calligraphers_supplies", "Calligrapher's Supplies"),
    ("carpenters_tools", "Carpenter's Tools"),
    ("cobblers_tools", "Cobbler's Tools"),
    ("cooks_utensils", "Cook's Utensils"),
    ("glassblowers_tools", "Glassblower's Tools"),
    ("jewelers_tools", "Jeweler's Tools"),
    ("leatherworkers_tools", "Leatherworker's Tools"),
    ("masons_tools", "Mason's Tools"),
    ("painters_supplies", "Painter's Supplies"),
    ("potters_tools", "Potter's Tools"),
    ("smiths_tools", "Smith's Tools"),
    ("tinkers_tools", "Tinker's Tools"),
    ("weavers_tools", "Weaver's Tools"),
    ("woodcarvers_tools", "Woodcarver's Tools"),
]

# Gaming sets.
_GAMING_SETS = [
    ("dice_set", "Dice Set"),
    ("dragonchess_set", "Dragonchess Set"),
    ("playing_card_set", "Playing Card Set"),
    ("three_dragon_ante_set", "Three-Dragon Ante Set"),
]

# Musical instruments.
_MUSICAL_INSTRUMENTS = [
    ("bagpipes", "Bagpipes"),
    ("birdpipes", "Birdpipes"),
    ("drums", "Drums"),
    ("dulcimer", "Dulcimer"),
    ("flute", "Flute"),
    ("glaur", "Glaur"),
    ("hand_drum", "Hand Drum"),
    ("horn", "Horn"),
    ("longhorn", "Longhorn"),
    ("lute", "Lute"),
    ("lyre", "Lyre"),
    ("pan_flute", "Pan Flute"),
    ("shawm", "Shawm"),
    ("songhorn", "Songhorn"),
    ("tantan", "Tantan"),
    ("viol", "Viol"),
    ("wargong", "Wargong"),
    ("yarting", "Yarting"),
    ("zulkoon", "Zulkoon"),
]

# Standalone kits/tools with their own default ability.
_KITS = [
    ("disguise_kit", "Disguise Kit", "charisma",
     "Create disguises to pass as someone else."),
    ("forgery_kit", "Forgery Kit", "dexterity",
     "Duplicate documents, signatures, and seals."),
    ("herbalism_kit", "Herbalism Kit", "intelligence",
     "Identify plants and brew healing potions and antitoxins."),
    ("navigator_tools", "Navigator's Tools", "intelligence",
     "Chart a course at sea and avoid becoming lost."),
    ("poisoners_kit", "Poisoner's Kit", "intelligence",
     "Apply, harvest, and identify poisons."),
    ("thieves_tools", "Thieves' Tools", "dexterity",
     "Pick locks, disarm traps, and crack safes."),
]

# Vehicles.
_VEHICLES = [
    ("land_vehicle", "Land Vehicle", "dexterity",
     "Drive wagons, carts, and other land conveyances."),
    ("water_vehicle", "Water Vehicle", "wisdom",
     "Pilot ships and boats across rivers and seas."),
]


def _build_registry() -> dict[str, ToolDef]:
    reg: dict[str, ToolDef] = {}
    for tid, name in _ARTISAN_TOOLS:
        reg[tid] = ToolDef(tid, name, "artisan", "intelligence",
                           "Craft, repair, and appraise goods of the trade.")
    for tid, name in _GAMING_SETS:
        reg[tid] = ToolDef(tid, name, "gaming_set", "intelligence",
                           "Play games of chance or strategy.")
    for tid, name in _MUSICAL_INSTRUMENTS:
        reg[tid] = ToolDef(tid, name, "musical_instrument", "charisma",
                           "Play music to perform or entertain.")
    for tid, name, ability, desc in _KITS:
        reg[tid] = ToolDef(tid, name, "kit", ability, desc)
    for tid, name, ability, desc in _VEHICLES:
        reg[tid] = ToolDef(tid, name, "vehicle", ability, desc)
    return reg


TOOL_REGISTRY: dict[str, ToolDef] = _build_registry()

ALL_TOOL_IDS: tuple[str, ...] = tuple(TOOL_REGISTRY.keys())

TOOL_CATEGORIES: tuple[str, ...] = (
    "artisan",
    "gaming_set",
    "musical_instrument",
    "kit",
    "vehicle",
)


def get_tool_def(tool_id: str) -> ToolDef:
    """Return the :class:`ToolDef` for a tool id (raises ValueError if unknown)."""
    tool_id = tool_id.lower()
    if tool_id not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool: {tool_id}")
    return TOOL_REGISTRY[tool_id]


def tools_in_category(category: str) -> list[ToolDef]:
    """Return all tool definitions in a category."""
    category = category.lower()
    return [td for td in TOOL_REGISTRY.values() if td.category == category]


def normalize_tool_id(tool_id: str) -> str:
    """Normalize a tool reference to its registry id.

    Accepts the registry id itself, or a few common human spellings
    (e.g., "thieves tools" → "thieves_tools", "smith's tools" → "smiths_tools").
    Returns the canonical id, or raises ``ValueError`` if unrecognised.
    """
    if not tool_id:
        raise ValueError("Empty tool id")
    key = tool_id.lower().strip()

    # Direct registry hit.
    if key in TOOL_REGISTRY:
        return key

    # Common normalisations: drop apostrophes, replace spaces with underscores.
    normalized = key.replace("'", "").replace(" ", "_")
    # Collapse "thieve's" -> "thieves", "smiths" already fine.
    if normalized in TOOL_REGISTRY:
        return normalized

    # Try collapsing double underscores and singular/plural tweaks.
    normalized2 = normalized.replace("__", "_")
    if normalized2 in TOOL_REGISTRY:
        return normalized2

    # Map a few friendly aliases.
    aliases = {
        "thieves_tools": "thieves_tools",
        "thief_tools": "thieves_tools",
        "thieves_tool": "thieves_tools",
        "navigator_s_tools": "navigator_tools",
        "navigators_tools": "navigator_tools",
        "navigator": "navigator_tools",
        "disguise": "disguise_kit",
        "forgery": "forgery_kit",
        "herbalism": "herbalism_kit",
        "poisoner": "poisoners_kit",
        "poisoners_kit": "poisoners_kit",
        "poisoner_s_kit": "poisoners_kit",
        "land": "land_vehicle",
        "water": "water_vehicle",
    }
    if normalized in aliases:
        return aliases[normalized]

    raise ValueError(f"Unknown tool: {tool_id}")


# --------------------------------------------------------------------------- #
# Class tool proficiency
# --------------------------------------------------------------------------- #

# Each class's tool grants. ``fixed`` tools are always granted; ``choice``
# describes a player-chosen set (count + which category they pick from, or a
# union of categories). ``artisan_or_instrument`` means either category.
_CLASS_TOOLS: dict[str, dict] = {
    "bard": {
        "fixed": [],
        "choice": {"count": 3, "categories": ["musical_instrument"]},
    },
    "rogue": {
        "fixed": ["thieves_tools"],
        "choice": None,
    },
    "monk": {
        "fixed": [],
        # One artisan's tool OR one musical instrument.
        "choice": {"count": 1, "categories": ["artisan", "musical_instrument"]},
    },
    "druid": {
        "fixed": ["herbalism_kit"],
        "choice": None,
    },
    # Fighter, Barbarian, Cleric, Paladin, Ranger, Sorcerer, Warlock, Wizard: none.
}


def get_class_tool_grants(char_class: str) -> dict:
    """Get the tool grants for a class.

    Returns a dict: ``{"fixed": [...], "choice": {"count", "categories"} | None}``.
    Unknown / tool-less classes return an empty grant.
    """
    base = _CLASS_TOOLS.get(char_class.lower())
    if not base:
        return {"fixed": [], "choice": None}
    return {
        "fixed": list(base.get("fixed", [])),
        "choice": dict(base["choice"]) if base.get("choice") else None,
    }


def get_class_fixed_tools(char_class: str) -> list[str]:
    """Tools a class grants automatically (no choice needed)."""
    return get_class_tool_grants(char_class)["fixed"]


def get_class_tool_choice(char_class: str) -> Optional[dict]:
    """The choice-grant for a class (count + categories), or None."""
    return get_class_tool_grants(char_class)["choice"]


# --------------------------------------------------------------------------- #
# Background tool proficiency
# --------------------------------------------------------------------------- #

_BACKGROUND_TOOLS: dict[str, dict] = {
    "acolyte": {"fixed": [], "choice": None},
    "charlatan": {"fixed": ["disguise_kit", "forgery_kit"], "choice": None},
    "criminal": {
        "fixed": ["thieves_tools"],
        "choice": {"count": 1, "categories": ["gaming_set"]},
    },
    "spy": {
        "fixed": ["thieves_tools"],
        "choice": {"count": 1, "categories": ["gaming_set"]},
    },
    "entertainer": {
        "fixed": ["disguise_kit"],
        "choice": {"count": 1, "categories": ["musical_instrument"]},
    },
    "gladiator": {
        "fixed": ["disguise_kit"],
        "choice": {"count": 1, "categories": ["musical_instrument"]},
    },
    "folk hero": {
        "fixed": ["land_vehicle"],
        "choice": {"count": 1, "categories": ["artisan"]},
    },
    "guild artisan": {
        "fixed": [],
        "choice": {"count": 1, "categories": ["artisan"]},
    },
    "guild merchant": {
        "fixed": [],
        "choice": {"count": 1, "categories": ["artisan"]},
    },
    "hermit": {"fixed": ["herbalism_kit"], "choice": None},
    "noble": {
        "fixed": [],
        "choice": {"count": 1, "categories": ["gaming_set"]},
    },
    "knight": {
        "fixed": [],
        "choice": {"count": 1, "categories": ["gaming_set"]},
    },
    "outlander": {
        "fixed": [],
        "choice": {"count": 1, "categories": ["musical_instrument"]},
    },
    "sage": {"fixed": [], "choice": None},
    "sailor": {"fixed": ["navigator_tools", "water_vehicle"], "choice": None},
    "pirate": {"fixed": ["navigator_tools", "water_vehicle"], "choice": None},
    "soldier": {
        "fixed": ["land_vehicle"],
        "choice": {"count": 1, "categories": ["gaming_set"]},
    },
    "urchin": {"fixed": ["disguise_kit", "forgery_kit"], "choice": None},
    "haunted one": {
        # Variant background — pick any one tool set; model as a broad choice.
        "fixed": [],
        "choice": {"count": 1, "categories": ["artisan", "kit", "musical_instrument", "gaming_set"]},
    },
}


def get_background_tool_grants(background: str) -> dict:
    """Get the tool grants for a background (same shape as class grants)."""
    base = _BACKGROUND_TOOLS.get((background or "").lower())
    if not base:
        return {"fixed": [], "choice": None}
    return {
        "fixed": list(base.get("fixed", [])),
        "choice": dict(base["choice"]) if base.get("choice") else None,
    }


def get_background_fixed_tools(background: str) -> list[str]:
    """Tools a background grants automatically (no choice needed)."""
    return get_background_tool_grants(background)["fixed"]


def get_background_tool_choice(background: str) -> Optional[dict]:
    """The choice-grant for a background, or None."""
    return get_background_tool_grants(background)["choice"]


# --------------------------------------------------------------------------- #
# Character tool-proficiency queries
# --------------------------------------------------------------------------- #

def get_tool_proficiencies(character: Any) -> set[str]:
    """All tools a character is proficient in.

    If the character has explicitly chosen tools (the ``tool_proficiencies``
    JSON column), those are used directly. Otherwise proficiencies are
    auto-derived as a sensible default: the union of all *fixed* tools granted
    by the character's classes and background (choices are NOT auto-granted,
    because they require a player decision). This keeps the engine working for
    pre-existing characters that predate the tool column.
    """
    stored = _parse_json_list(getattr(character, "tool_proficiencies", None))
    if stored:
        return {normalize_tool_id(t) for t in stored if isinstance(t, str) and t.strip()}

    # Auto-derive defaults for backward compatibility: only fixed tools.
    prof: set[str] = set()
    for cls_name in _iter_classes(character):
        prof.update(get_class_fixed_tools(cls_name))
    bg = getattr(character, "background", "") or ""
    prof.update(get_background_fixed_tools(bg))
    return prof


def _feat_tool_proficiencies(character: Any) -> set[str]:
    """Tool proficiencies granted by feats.

    Recognised feat effect keys:
      - ``tool_proficiency``: str or list[str]
      - ``tool_proficiencies``: list[str]
    (e.g., the Skilled feat may grant tool proficiency.)
    """
    feats_raw = getattr(character, "feats", None)
    if not feats_raw:
        return set()
    try:
        import json
        feats = json.loads(feats_raw)
    except (Exception,):
        return set()

    profs: set[str] = set()
    if not isinstance(feats, list):
        return profs

    def _norm(val):
        if isinstance(val, str):
            return [val.lower()]
        if isinstance(val, list):
            return [str(v).lower() for v in val]
        return []

    for feat in feats:
        if not isinstance(feat, dict):
            continue
        effects = feat.get("effects", {}) if isinstance(feat.get("effects"), dict) else {}
        for raw in _norm(effects.get("tool_proficiency")) + _norm(effects.get("tool_proficiencies")):
            try:
                profs.add(normalize_tool_id(raw))
            except ValueError:
                # Unknown tool name in a feat payload — skip rather than crash.
                continue
    return profs


def get_all_tool_proficiencies(character: Any) -> set[str]:
    """Chosen/auto tool proficiencies UNION feat-granted proficiencies."""
    return get_tool_proficiencies(character) | _feat_tool_proficiencies(character)


def is_proficient_with_tool(tool_id: str, character: Any) -> bool:
    """Whether a character is proficient with a given tool."""
    return normalize_tool_id(tool_id) in get_all_tool_proficiencies(character)


# --------------------------------------------------------------------------- #
# Tool modifier calculation
# --------------------------------------------------------------------------- #

def calculate_tool_modifier(
    tool_id: str,
    character: Any,
    ability: Optional[str] = None,
    proficiencies: Optional[set[str]] = None,
) -> int:
    """Static tool modifier = ability_mod + proficiency_bonus (if proficient).

    Args:
        tool_id: Tool name/id (normalized internally).
        character: Character-like object.
        ability: Override the tool's default ability for this check.
        proficiencies: Pre-computed proficiency set (optional optimization).
    """
    td = get_tool_def(normalize_tool_id(tool_id))
    if proficiencies is None:
        proficiencies = get_all_tool_proficiencies(character)

    check_ability = (ability or td.ability).lower()
    if check_ability not in ABILITIES:
        raise ValueError(f"Invalid ability: {ability}")

    score = get_ability_score(character, check_ability)
    mod = ability_modifier(score)

    bonus = 0
    if td.id in proficiencies:
        level = get_character_level(character)
        bonus += proficiency_bonus(level)

    return mod + bonus


def calculate_tool_breakdown(
    tool_id: str,
    character: Any,
    ability: Optional[str] = None,
    proficiencies: Optional[set[str]] = None,
) -> dict:
    """Return a detailed breakdown of how a tool modifier is computed."""
    td = get_tool_def(normalize_tool_id(tool_id))
    if proficiencies is None:
        proficiencies = get_all_tool_proficiencies(character)

    check_ability = (ability or td.ability).lower()
    if check_ability not in ABILITIES:
        raise ValueError(f"Invalid ability: {ability}")

    score = get_ability_score(character, check_ability)
    mod = ability_modifier(score)
    level = get_character_level(character)
    pb = proficiency_bonus(level)
    proficient = td.id in proficiencies

    return {
        "tool": td.id,
        "name": td.name,
        "category": td.category,
        "default_ability": td.ability,
        "ability": check_ability,
        "ability_score": score,
        "ability_modifier": mod,
        "proficient": proficient,
        "proficiency_bonus": pb if proficient else 0,
        "modifier": mod + (pb if proficient else 0),
        "level": level,
    }


# --------------------------------------------------------------------------- #
# Condition effects on tool checks
# --------------------------------------------------------------------------- #

def check_tool_disadvantage(ability: str, conditions: list[str]) -> bool:
    """Whether a tool check suffers disadvantage from conditions.

    Mirrors the skill-check rules: poisoned → disadvantage on ALL ability
    checks; restrained → disadvantage on Dexterity checks.
    """
    if not conditions:
        return False
    cond = {c.lower() for c in conditions}
    if "poisoned" in cond:
        return True
    if "restrained" in cond and (ability or "").lower() == "dexterity":
        return True
    return False


def check_tool_advantage(ability: str, conditions: list[str]) -> bool:
    """No condition grants advantage on tool checks (per the skill model)."""
    return False


# --------------------------------------------------------------------------- #
# Tool check execution
# --------------------------------------------------------------------------- #

@dataclass
class ToolCheckResult:
    """Result of a tool check."""
    tool: str
    name: str
    category: str
    ability: str
    roll: RollResult
    modifier: int
    total: int
    success: bool
    dc: int
    proficient: bool
    advantage: bool = False
    disadvantage: bool = False
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "name": self.name,
            "category": self.category,
            "ability": self.ability,
            "roll": self.roll.description,
            "rolls": self.roll.rolls,
            "modifier": self.modifier,
            "total": self.total,
            "success": self.success,
            "dc": self.dc,
            "proficient": self.proficient,
            "advantage": self.advantage,
            "disadvantage": self.disadvantage,
            "description": self.description,
        }


def roll_tool_check(
    tool_id: str,
    character: Any,
    dc: int,
    ability: Optional[str] = None,
    advantage: bool = False,
    disadvantage: bool = False,
    conditions: Optional[list[str]] = None,
    proficiencies: Optional[set[str]] = None,
) -> ToolCheckResult:
    """Roll a tool check for a character against a DC.

    Args:
        tool_id: Tool name/id (normalized internally).
        character: Character-like object.
        dc: Difficulty Class to meet or beat.
        ability: Override the tool's default check ability.
        advantage: Explicit advantage override.
        disadvantage: Explicit disadvantage override.
        conditions: Active conditions (for disadvantage effects).
        proficiencies: Pre-computed proficiency set (optional optimization).

    Returns:
        A :class:`ToolCheckResult`.
    """
    td = get_tool_def(normalize_tool_id(tool_id))
    if conditions is None:
        conditions = []
    if proficiencies is None:
        proficiencies = get_all_tool_proficiencies(character)

    check_ability = (ability or td.ability).lower()
    if check_ability not in ABILITIES:
        raise ValueError(f"Invalid ability: {ability}")

    # Merge explicit advantage/disadvantage with condition-driven ones.
    has_advantage = advantage and not disadvantage
    has_disadvantage = disadvantage and not advantage
    if check_tool_disadvantage(check_ability, conditions):
        has_disadvantage = True
        if has_advantage:
            has_advantage = False
            has_disadvantage = False

    modifier = calculate_tool_modifier(td.id, character, check_ability, proficiencies)
    proficient = td.id in proficiencies

    roll_result = roll_d20(modifier=modifier, advantage=has_advantage, disadvantage=has_disadvantage)
    success = roll_result.total >= dc

    parts = [td.name]
    if has_advantage:
        parts.append("(advantage)")
    elif has_disadvantage:
        parts.append("(disadvantage)")
    parts.append(f"check DC {dc}")
    description = " ".join(parts)

    return ToolCheckResult(
        tool=td.id,
        name=td.name,
        category=td.category,
        ability=check_ability,
        roll=roll_result,
        modifier=modifier,
        total=roll_result.total,
        success=success,
        dc=dc,
        proficient=proficient,
        advantage=has_advantage,
        disadvantage=has_disadvantage,
        description=description,
    )


# --------------------------------------------------------------------------- #
# Xanathar's combined skill + tool checks
# --------------------------------------------------------------------------- #

def combined_check_advantage(
    has_skill_proficiency: bool,
    has_tool_proficiency: bool,
) -> bool:
    """Whether a combined skill+tool check gains advantage.

    Per Xanathar's Guide to Everything: when you gain proficiency in a skill
    and a tool that both apply to the same ability check, you gain advantage
    on that check (or, at the DM's option, a doubled proficiency bonus). This
    engine models the *advantage* option, which is the more common table rule.
    """
    return has_skill_proficiency and has_tool_proficiency


# --------------------------------------------------------------------------- #
# Difficulty Class reference (shared with skills; re-exposed for convenience)
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
