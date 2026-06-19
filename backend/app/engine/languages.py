"""
Language system engine — DnD 5e languages, race grants, and background choices.

Implements DnD 5e language mechanics:

- **Standard languages**: Common, Dwarf, Elf, Halfling, Gnomish, Goblin, Orc, Giant,
  Draconic, Primordial, Undercommon, Abyssal, Celestial, Deep Speech, Infernal,
  Sylvan, Thieves' Cant (Rogue special), Druidic (Druid special).
- **Race language grants**: Most races grant 1-2 fixed languages + extra language
  choices from a subset (PHB p. 121-123).
- **Background extra languages**: Some backgrounds grant 1-2 extra languages
  (e.g., Acolyte grants 2 of any language).
- **Character languages**: Tracks all languages a character knows, including
  racial languages, background extras, and any additional languages learned.

The engine is pure (no DB, no LLM) and operates on a character-like object that
exposes: race, background, and optional `languages` JSON column.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# --------------------------------------------------------------------------- #
# Language registry (all DnD 5e standard languages)
# --------------------------------------------------------------------------- #

# Language type categories
class LanguageType:
    STANDARD = "standard"
    EXOTIC = "exotic"
    SECRET = "secret"


# All DnD 5e languages with metadata
_LANGUAGES: dict[str, dict[str, Any]] = {
    "common": {
        "id": "common",
        "name": "Common",
        "type": LanguageType.STANDARD,
        "typical_speakers": "Humans, many other races",
        "script": "Common",
    },
    "dwarvish": {
        "id": "dwarvish",
        "name": "Dwarvish",
        "type": LanguageType.STANDARD,
        "typical_speakers": "Dwarves",
        "script": "Dwarvish",
    },
    "elvish": {
        "id": "elvish",
        "name": "Elvish",
        "type": LanguageType.STANDARD,
        "typical_speakers": "Elves",
        "script": "Elvish",
    },
    "halfling": {
        "id": "halfling",
        "name": "Halfling",
        "type": LanguageType.STANDARD,
        "typical_speakers": "Halflings",
        "script": "Common",
    },
    "gnomish": {
        "id": "gnomish",
        "name": "Gnomish",
        "type": LanguageType.STANDARD,
        "typical_speakers": "Gnomes",
        "script": "Dwarvish",
    },
    "goblin": {
        "id": "goblin",
        "name": "Goblin",
        "type": LanguageType.STANDARD,
        "typical_speakers": "Goblins, hobgoblins",
        "script": "Dwarvish",
    },
    "orc": {
        "id": "orc",
        "name": "Orc",
        "type": LanguageType.STANDARD,
        "typical_speakers": "Orcs",
        "script": "Dwarvish",
    },
    "giant": {
        "id": "giant",
        "name": "Giant",
        "type": LanguageType.STANDARD,
        "typical_speakers": "Giants, ogres",
        "script": "Dwarvish",
    },
    "draconic": {
        "id": "draconic",
        "name": "Draconic",
        "type": LanguageType.STANDARD,
        "typical_speakers": "Dragons, dragonborn",
        "script": "Draconic",
    },
    "primordial": {
        "id": "primordial",
        "name": "Primordial",
        "type": LanguageType.STANDARD,
        "typical_speakers": "Elementals",
        "script": "Dwarvish",
    },
    "undercommon": {
        "id": "undercommon",
        "name": "Undercommon",
        "type": LanguageType.STANDARD,
        "typical_speakers": "Drow, Underdark dwellers",
        "script": "Elvish",
    },
    "abyssal": {
        "id": "abyssal",
        "name": "Abyssal",
        "type": LanguageType.EXOTIC,
        "typical_speakers": "Demons",
        "script": "Infernal",
    },
    "celestial": {
        "id": "celestial",
        "name": "Celestial",
        "type": LanguageType.EXOTIC,
        "typical_speakers": "Celestials",
        "script": "Celestial",
    },
    "deep_speech": {
        "id": "deep_speech",
        "name": "Deep Speech",
        "type": LanguageType.EXOTIC,
        "typical_speakers": "Aboleths, mind flayers",
        "script": None,  # No written form
    },
    "infernal": {
        "id": "infernal",
        "name": "Infernal",
        "type": LanguageType.EXOTIC,
        "typical_speakers": "Devils, tieflings",
        "script": "Infernal",
    },
    "sylvan": {
        "id": "sylvan",
        "name": "Sylvan",
        "type": LanguageType.EXOTIC,
        "typical_speakers": "Fey creatures",
        "script": "Elvish",
    },
    "thieves_cant": {
        "id": "thieves_cant",
        "name": "Thieves' Cant",
        "type": LanguageType.SECRET,
        "typical_speakers": "Rogues",
        "script": None,  # Secret mix of dialect, slang, and hand signs
    },
    "druidic": {
        "id": "druidic",
        "name": "Druidic",
        "type": LanguageType.SECRET,
        "typical_speakers": "Druids",
        "script": None,  # Secret language known only to druids
    },
}

# Aliases for common lookups (case-insensitive)
_LANGUAGE_ALIASES = {
    "common": "common",
    "dwarvish": "dwarvish",
    "elvish": "elvish",
    "elven": "elvish",
    "halfling": "halfling",
    "gnomish": "gnomish",
    "goblin": "goblin",
    "orc": "orc",
    "orcish": "orc",
    "giant": "giant",
    "giantish": "giant",
    "draconic": "draconic",
    "primordial": "primordial",
    "undercommon": "undercommon",
    "abyssal": "abyssal",
    "celestial": "celestial",
    "deep speech": "deep_speech",
    "deep_speech": "deep_speech",
    "infernal": "infernal",
    "sylvan": "sylvan",
    "thieves' cant": "thieves_cant",
    "thieves_cant": "thieves_cant",
    "druidic": "druidic",
}

ALL_LANGUAGES: tuple[str, ...] = tuple(_LANGUAGES.keys())
STANDARD_LANGUAGES: tuple[str, ...] = tuple(
    k for k, v in _LANGUAGES.items() if v["type"] == LanguageType.STANDARD
)
EXOTIC_LANGUAGES: tuple[str, ...] = tuple(
    k for k, v in _LANGUAGES.items() if v["type"] == LanguageType.EXOTIC
)
SECRET_LANGUAGES: tuple[str, ...] = tuple(
    k for k, v in _LANGUAGES.items() if v["type"] == LanguageType.SECRET
)


@dataclass
class LanguageInfo:
    """Information about a single language."""
    id: str
    name: str
    type: str
    typical_speakers: str
    script: Optional[str]


def get_language_info(language_id: str) -> Optional[LanguageInfo]:
    """Get detailed information about a language by ID.

    Returns None if the language doesn't exist.
    """
    lang = _LANGUAGES.get(language_id)
    if not lang:
        return None
    return LanguageInfo(**lang)


def list_languages() -> list[LanguageInfo]:
    """List all available languages."""
    return [LanguageInfo(**v) for v in _LANGUAGES.values()]


def normalize_language_id(name: str) -> Optional[str]:
    """Normalize a language name/alias to its canonical ID.

    Case-insensitive, handles spaces, hyphens, and apostrophes.
    Returns None if the language doesn't exist.
    """
    # Try direct lookup first (exact match)
    direct = name.lower().strip()
    if direct in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[direct]

    # Try normalized versions
    # Replace various separators with underscores
    normalized = direct.replace(" ", "_").replace("-", "_").replace("'", "_")
    if normalized in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[normalized]

    # Handle double underscores (from "thieves' cant" -> "thieves__cant")
    double_normalized = normalized.replace("__", "_")
    if double_normalized in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[double_normalized]

    return None


def is_valid_language(language_id: str) -> bool:
    """Check if a language ID is valid."""
    return language_id in _LANGUAGES


# --------------------------------------------------------------------------- #
# Race language grants (PHB p. 121-123)
# --------------------------------------------------------------------------- #

# Format: {race_id: {"fixed": [language_ids], "extra_count": int, "extra_choices": [language_ids]}}
_RACE_LANGUAGES: dict[str, dict[str, Any]] = {
    # Human
    "human": {
        "fixed": ["common"],
        "extra_count": 1,
        "extra_choices": STANDARD_LANGUAGES,  # Any standard
    },
    "human_variant": {  # Variant human can take a feat instead, but we model the base here
        "fixed": ["common"],
        "extra_count": 1,
        "extra_choices": STANDARD_LANGUAGES,
    },
    # Dwarf (Hill, Mountain) - Mountain gets Giant instead of extra
    "dwarf": {
        "fixed": ["common", "dwarvish"],
        "extra_count": 0,
        "extra_choices": [],
    },
    "hill_dwarf": {
        "fixed": ["common", "dwarvish"],
        "extra_count": 0,
        "extra_choices": [],
    },
    "mountain_dwarf": {
        "fixed": ["common", "dwarvish", "giant"],  # PHB: Mountain Dwarf learns Giant instead of extra
        "extra_count": 0,
        "extra_choices": [],
    },
    # Elf (High, Wood, Drow)
    "elf": {
        "fixed": ["common", "elvish"],
        "extra_count": 1,
        "extra_choices": STANDARD_LANGUAGES,
    },
    "high_elf": {
        "fixed": ["common", "elvish"],
        "extra_count": 1,
        "extra_choices": STANDARD_LANGUAGES,
    },
    "wood_elf": {
        "fixed": ["common", "elvish"],
        "extra_count": 1,
        "extra_choices": STANDARD_LANGUAGES,
    },
    "drow": {
        "fixed": ["common", "elvish", "undercommon"],
        "extra_count": 0,
        "extra_choices": [],
    },
    # Halfling (Lightfoot, Stout)
    "halfling": {
        "fixed": ["common", "halfling"],
        "extra_count": 0,
        "extra_choices": [],
    },
    "lightfoot_halfling": {
        "fixed": ["common", "halfling"],
        "extra_count": 0,
        "extra_choices": [],
    },
    "stout_halfling": {
        "fixed": ["common", "halfling"],
        "extra_count": 0,
        "extra_choices": [],
    },
    # Gnome (Rock, Forest, Deep)
    "gnome": {
        "fixed": ["common", "gnomish"],
        "extra_count": 0,
        "extra_choices": [],
    },
    "rock_gnome": {
        "fixed": ["common", "gnomish"],
        "extra_count": 0,
        "extra_choices": [],
    },
    "forest_gnome": {
        "fixed": ["common", "gnomish"],
        "extra_count": 0,
        "extra_choices": [],
    },
    "deep_gnome": {
        "fixed": ["common", "gnomish", "undercommon"],
        "extra_count": 0,
        "extra_choices": [],
    },
    # Half-elf
    "half_elf": {
        "fixed": ["common", "elvish"],
        "extra_count": 1,
        "extra_choices": STANDARD_LANGUAGES,
    },
    # Half-orc
    "half_orc": {
        "fixed": ["common", "orc"],
        "extra_count": 0,
        "extra_choices": [],
    },
    # Dragonborn
    "dragonborn": {
        "fixed": ["common", "draconic"],
        "extra_count": 0,
        "extra_choices": [],
    },
    # Tiefling
    "tiefling": {
        "fixed": ["common", "infernal"],
        "extra_count": 0,
        "extra_choices": [],
    },
    # Goliath (Volo's/MPMM) - Giant as bonus language
    "goliath": {
        "fixed": ["common", "giant"],
        "extra_count": 0,
        "extra_choices": [],
    },
    # Aasimar (Volo's)
    "aasimar": {
        "fixed": ["common", "celestial"],
        "extra_count": 0,
        "extra_choices": [],
    },
    # Firbolg (Volo's)
    "firbolg": {
        "fixed": ["common", "elvish", "giant"],
        "extra_count": 0,
        "extra_choices": [],
    },
    # Kenku (Volo's) - Kenku speak Aarakocra but it's not a standard PHB language
    # We omit it from our registry since it's rarely used; kenku effectively have no extra choices
    "kenku": {
        "fixed": ["common"],
        "extra_count": 0,
        "extra_choices": [],
    },
    # Loxodon (Ravnica) - Loxodon have their own language, not in standard PHB
    "loxodon": {
        "fixed": ["common"],
        "extra_count": 0,
        "extra_choices": [],
    },
    # Minotaur (Ravnica)
    "minotaur": {
        "fixed": ["common"],
        "extra_count": 1,
        "extra_choices": STANDARD_LANGUAGES,
    },
    # Tabaxi (Volo's)
    "tabaxi": {
        "fixed": ["common"],
        "extra_count": 1,
        "extra_choices": STANDARD_LANGUAGES,
    },
    # Triton (Volo's)
    "triton": {
        "fixed": ["common", "primordial"],
        "extra_count": 0,
        "extra_choices": [],
    },
    # Bugbear (Volo's)
    "bugbear": {
        "fixed": ["common", "goblin"],
        "extra_count": 0,
        "extra_choices": [],
    },
    # Goblin (Volo's)
    "goblin_race": {  # "goblin_race" to avoid conflict with language ID
        "fixed": ["common", "goblin"],
        "extra_count": 0,
        "extra_choices": [],
    },
    # Hobgoblin (Volo's)
    "hobgoblin": {
        "fixed": ["common", "goblin"],
        "extra_count": 0,
        "extra_choices": [],
    },
    # Kobold (Volo's)
    "kobold": {
        "fixed": ["common", "draconic"],
        "extra_count": 0,
        "extra_choices": [],
    },
    # Orc (Volo's)
    "orc_race": {  # "orc_race" to avoid conflict with language ID
        "fixed": ["common", "orc"],
        "extra_count": 0,
        "extra_choices": [],
    },
    # Yuan-ti Pureblood (Volo's)
    "yuan_ti_pureblood": {
        "fixed": ["common", "abyssal", "draconic"],
        "extra_count": 0,
        "extra_choices": [],
    },
}


def normalize_race_id(race: str) -> str:
    """Normalize a race name to its canonical ID (lowercase, underscores)."""
    return race.lower().strip().replace(" ", "_").replace("-", "_")


def get_race_language_info(race: str) -> dict[str, Any]:
    """Get language grant info for a race.

    Returns a dict with:
    - fixed: list of automatically-known language IDs
    - extra_count: number of extra languages the character may choose
    - extra_choices: list of valid language IDs for extra choices

    For unknown races, returns Common + 1 extra standard language.
    """
    race_id = normalize_race_id(race)
    return _RACE_LANGUAGES.get(
        race_id,
        {"fixed": ["common"], "extra_count": 1, "extra_choices": STANDARD_LANGUAGES},
    )


def get_race_fixed_languages(race: str) -> list[str]:
    """Get the fixed languages granted by a race."""
    return get_race_language_info(race)["fixed"]


def get_race_extra_choices(race: str) -> list[str]:
    """Get the valid extra language choices for a race."""
    return get_race_language_info(race)["extra_choices"]


def get_race_extra_count(race: str) -> int:
    """Get the number of extra languages a race grants."""
    return get_race_language_info(race)["extra_count"]


# --------------------------------------------------------------------------- #
# Character language operations
# --------------------------------------------------------------------------- #


def parse_languages(languages_json: str) -> list[str]:
    """Parse the languages JSON column from the Character model.

    Returns an empty list if the field is None, empty, or invalid JSON.
    """
    if not languages_json or languages_json.strip() == "":
        return []
    try:
        parsed = eval(languages_json) if isinstance(languages_json, str) else languages_json
        if isinstance(parsed, list):
            return [str(l) for l in parsed]
        elif isinstance(parsed, dict):
            # Handle dict format: {"languages": [...], "extra_chosen": [...]}
            if "languages" in parsed:
                langs = parsed["languages"]
                if isinstance(langs, list):
                    return [str(l) for l in langs]
            return []
        return []
    except (TypeError, ValueError, SyntaxError):
        return []


def serialize_languages(languages: list[str]) -> str:
    """Serialize a list of language IDs to JSON for storage."""
    return str([str(l) for l in languages])


def get_character_languages(character: Any) -> list[str]:
    """Get all languages a character knows.

    Includes the languages stored in the `languages` JSON column.
    If the column is empty/invalid, returns an empty list.
    """
    try:
        languages_json = getattr(character, "languages", None)
        if languages_json is None:
            return []
        return parse_languages(languages_json)
    except (AttributeError, TypeError):
        return []


def get_derived_languages(character: Any) -> dict[str, list[str]]:
    """Calculate all languages a character *should* know based on race and background.

    This is used for UI previews and validation. It does NOT include the
    character's stored languages (use get_character_languages for that).

    Returns:
        {
            "racial_fixed": [...],      # Automatic racial languages
            "racial_extra_count": int,  # Number of extra racial choices available
            "racial_extra_choices": [...],  # Valid choices for racial extras
            "background_languages": [...],  # Extra languages from background
            "class_languages": [...],   # Any class-granted languages (Druidic, Thieves' Cant)
            "all_automatic": [...],     # Union of racial_fixed + background + class
        }
    """
    race = getattr(character, "race", "Human")
    background = getattr(character, "background", None)
    char_class = getattr(character, "char_class", None)
    classes_dict = getattr(character, "classes_dict", {})

    # Racial languages
    race_info = get_race_language_info(race)
    racial_fixed = race_info["fixed"]
    racial_extra_count = race_info["extra_count"]
    racial_extra_choices = race_info["extra_choices"]

    # Background extra languages (import from backgrounds engine to avoid circular import)
    background_languages: list[str] = []
    if background:
        try:
            from app.engine.backgrounds import get_background_languages

            # get_background_languages returns (fixed_languages, extra_language_choices)
            # We use the fixed languages as automatic grants
            bg_langs_tuple = get_background_languages(background)
            if bg_langs_tuple and isinstance(bg_langs_tuple, tuple) and len(bg_langs_tuple) >= 1:
                background_languages = bg_langs_tuple[0] if isinstance(bg_langs_tuple[0], list) else []
        except ImportError:
            # Backgrounds engine not available, skip
            pass

    # Class languages (Druidic, Thieves' Cant)
    class_languages: list[str] = []
    if classes_dict:
        # Check for druid (any level)
        if "druid" in classes_dict and classes_dict["druid"] >= 1:
            class_languages.append("druidic")
        # Check for rogue (any level)
        if "rogue" in classes_dict and classes_dict["rogue"] >= 1:
            class_languages.append("thieves_cant")
    elif char_class:
        char_class_lower = char_class.lower()
        if char_class_lower == "druid":
            class_languages.append("druidic")
        elif char_class_lower == "rogue":
            class_languages.append("thieves_cant")

    # Union of all automatic languages
    all_automatic = list(set(racial_fixed + background_languages + class_languages))

    return {
        "racial_fixed": racial_fixed,
        "racial_extra_count": racial_extra_count,
        "racial_extra_choices": racial_extra_choices,
        "background_languages": background_languages,
        "class_languages": class_languages,
        "all_automatic": all_automatic,
    }


def validate_character_languages(
    character: Any,
    chosen_languages: list[str],
) -> tuple[bool, str]:
    """Validate a character's chosen languages.

    Args:
        character: Character-like object with race, background, languages
        chosen_languages: List of language IDs the character knows

    Returns:
        (is_valid, error_message) tuple
    """
    # Normalize all language IDs
    normalized_chosen = [normalize_language_id(l) for l in chosen_languages]
    valid_chosen = [l for l in normalized_chosen if l is not None]
    invalid = [l for l in chosen_languages if normalize_language_id(l) is None]

    if invalid:
        return False, f"Unknown languages: {', '.join(invalid)}"

    # Get derived languages
    derived = get_derived_languages(character)

    # Automatic languages must be included
    missing_automatic = [
        l for l in derived["all_automatic"] if l not in valid_chosen
    ]
    if missing_automatic:
        return False, f"Missing automatic languages: {', '.join(missing_automatic)}"

    # Count extra languages beyond automatic
    extra_count = len(valid_chosen) - len(derived["all_automatic"])
    racial_extra_count = derived["racial_extra_count"]

    # Can't exceed racial extra count + background extras
    if extra_count > racial_extra_count:
        return (
            False,
            f"Too many languages: {extra_count} extra chosen, "
            f"but race + background only grant {racial_extra_count}.",
        )

    # All extra choices must be from the valid pool
    extra_choices_pool = set(derived["racial_extra_choices"])
    extras = [
        l for l in valid_chosen if l not in derived["all_automatic"]
    ]
    invalid_extras = [l for l in extras if l not in extra_choices_pool]

    if invalid_extras:
        return (
            False,
            f"Invalid extra language choices: {', '.join(invalid_extras)}. "
            f"Must choose from: {', '.join(extra_choices_pool)}",
        )

    return True, ""


def calculate_language_summary(character: Any) -> dict[str, Any]:
    """Generate a full language summary for a character.

    Returns:
        {
            "known": [...],              # All languages the character knows
            "automatic": [...],          # Languages granted by race/background/class
            "extra": [...],              # Extra languages chosen beyond automatic
            "available_choices": [...],  # Remaining choices for extra languages
            "summary": str,              # Human-readable summary
        }
    """
    known = get_character_languages(character)
    derived = get_derived_languages(character)
    automatic = derived["all_automatic"]
    extra = [l for l in known if l not in automatic]

    # Calculate remaining choices
    racial_extra_count = derived["racial_extra_count"]
    used_extra = len(extra)
    remaining_choices = max(0, racial_extra_count - used_extra)

    # Available choices from racial pool (excluding already-known languages)
    pool = set(derived["racial_extra_choices"])
    known_set = set(known)
    available_choices = sorted(l for l in pool if l not in known_set)

    # Build summary string
    summary_parts = []
    if automatic:
        summary_parts.append(f"Automatic: {', '.join(automatic)}")
    if extra:
        summary_parts.append(f"Extra: {', '.join(extra)}")
    if remaining_choices > 0:
        summary_parts.append(f"Choose {remaining_choices} more from: {', '.join(available_choices[:5])}{'...' if len(available_choices) > 5 else ''}")
    summary = "; ".join(summary_parts) if summary_parts else "No languages"

    return {
        "known": known,
        "automatic": automatic,
        "extra": extra,
        "available_choices": available_choices,
        "remaining_choices": remaining_choices,
        "summary": summary,
    }


@dataclass
class LanguageChoiceInfo:
    """Information about valid language choices for a character."""
    race_fixed: list[str]  # Automatic racial languages
    race_extra_count: int  # Number of extra racial choices
    race_extra_choices: list[str]  # Valid pool for racial extras
    background_languages: list[str]  # Background extra languages
    class_languages: list[str]  # Class-granted languages (Druidic, Thieves' Cant)
    current_languages: list[str]  # Currently stored languages
    remaining_choices: int  # How many more can be chosen
    available_choices: list[str]  # Valid pool for remaining choices


def get_language_choices(character: Any) -> LanguageChoiceInfo:
    """Get detailed information about valid language choices for a character."""
    known = get_character_languages(character)
    derived = get_derived_languages(character)
    automatic = derived["all_automatic"]
    racial_extra_count = derived["racial_extra_count"]

    # Calculate remaining
    extra = [l for l in known if l not in automatic]
    used_extra = len(extra)
    remaining_choices = max(0, racial_extra_count - used_extra)

    # Available pool
    pool = set(derived["racial_extra_choices"])
    known_set = set(known)
    available_choices = sorted(l for l in pool if l not in known_set)

    return LanguageChoiceInfo(
        race_fixed=derived["racial_fixed"],
        race_extra_count=racial_extra_count,
        race_extra_choices=derived["racial_extra_choices"],
        background_languages=derived["background_languages"],
        class_languages=derived["class_languages"],
        current_languages=known,
        remaining_choices=remaining_choices,
        available_choices=available_choices,
    )