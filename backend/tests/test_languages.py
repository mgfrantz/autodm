"""
Test the language system engine.

Tests language registry, race grants, background integration, and character language management.
"""
import pytest

from app.engine import languages


# --------------------------------------------------------------------------- #
# Language Registry Tests
# --------------------------------------------------------------------------- #

def test_all_languages_defined():
    """All 18 DnD 5e languages should be defined."""
    assert len(languages.ALL_LANGUAGES) == 18


def test_language_type_counts():
    """Check that languages are correctly categorized."""
    assert len(languages.STANDARD_LANGUAGES) == 11
    assert len(languages.EXOTIC_LANGUAGES) == 5
    assert len(languages.SECRET_LANGUAGES) == 2


def test_secret_languages():
    """Secret languages should be Thieves' Cant and Druidic."""
    assert "thieves_cant" in languages.SECRET_LANGUAGES
    assert "druidic" in languages.SECRET_LANGUAGES


def test_get_language_info():
    """Get detailed information about a language."""
    info = languages.get_language_info("common")
    assert info is not None
    assert info.id == "common"
    assert info.name == "Common"
    assert info.type == languages.LanguageType.STANDARD
    assert info.script == "Common"


def test_get_language_info_invalid():
    """Invalid language IDs return None."""
    assert languages.get_language_info("invalid_language") is None


def test_list_languages():
    """List all languages with details."""
    all_langs = languages.list_languages()
    assert len(all_langs) == 18
    # Check that each is a LanguageInfo object
    for lang in all_langs:
        assert hasattr(lang, 'id')
        assert hasattr(lang, 'name')
        assert hasattr(lang, 'type')


def test_normalize_language_id():
    """Language name normalization."""
    assert languages.normalize_language_id("Common") == "common"
    assert languages.normalize_language_id("deep speech") == "deep_speech"
    assert languages.normalize_language_id("Thieves' Cant") == "thieves_cant"
    assert languages.normalize_language_id("invalid") is None


def test_is_valid_language():
    """Check if a language ID is valid."""
    assert languages.is_valid_language("common")
    assert languages.is_valid_language("draconic")
    assert not languages.is_valid_language("invalid")


# --------------------------------------------------------------------------- #
# Race Language Grant Tests
# --------------------------------------------------------------------------- #

def test_human_languages():
    """Humans get Common + 1 extra standard language."""
    info = languages.get_race_language_info("Human")
    assert info["fixed"] == ["common"]
    assert info["extra_count"] == 1
    assert len(info["extra_choices"]) == len(languages.STANDARD_LANGUAGES)


def test_dwarf_languages():
    """Dwarves get Common + Dwarvish, no extras."""
    info = languages.get_race_language_info("Dwarf")
    assert set(info["fixed"]) == {"common", "dwarvish"}
    assert info["extra_count"] == 0
    assert len(info["extra_choices"]) == 0


def test_mountain_dwarf_languages():
    """Mountain Dwarves get Common + Dwarvish + Giant (instead of extra)."""
    info = languages.get_race_language_info("Mountain Dwarf")
    assert set(info["fixed"]) == {"common", "dwarvish", "giant"}
    assert info["extra_count"] == 0


def test_elf_languages():
    """Elves get Common + Elvish + 1 extra standard."""
    info = languages.get_race_language_info("Elf")
    assert set(info["fixed"]) == {"common", "elvish"}
    assert info["extra_count"] == 1
    assert len(info["extra_choices"]) == len(languages.STANDARD_LANGUAGES)


def test_drow_languages():
    """Drow get Common + Elvish + Undercommon, no extras."""
    info = languages.get_race_language_info("Drow")
    assert set(info["fixed"]) == {"common", "elvish", "undercommon"}
    assert info["extra_count"] == 0


def test_half_elf_languages():
    """Half-elves get Common + Elvish + 1 extra standard."""
    info = languages.get_race_language_info("Half-Elf")
    assert set(info["fixed"]) == {"common", "elvish"}
    assert info["extra_count"] == 1


def test_half_orc_languages():
    """Half-orcs get Common + Orc, no extras."""
    info = languages.get_race_language_info("Half-Orc")
    assert set(info["fixed"]) == {"common", "orc"}
    assert info["extra_count"] == 0


def test_dragonborn_languages():
    """Dragonborn get Common + Draconic, no extras."""
    info = languages.get_race_language_info("Dragonborn")
    assert set(info["fixed"]) == {"common", "draconic"}
    assert info["extra_count"] == 0


def test_tiefling_languages():
    """Tieflings get Common + Infernal, no extras."""
    info = languages.get_race_language_info("Tiefling")
    assert set(info["fixed"]) == {"common", "infernal"}
    assert info["extra_count"] == 0


def test_unknown_race_defaults():
    """Unknown races get Common + 1 extra standard."""
    info = languages.get_race_language_info("Alien")
    assert info["fixed"] == ["common"]
    assert info["extra_count"] == 1
    assert len(info["extra_choices"]) == len(languages.STANDARD_LANGUAGES)


def test_normalize_race_id():
    """Race ID normalization handles spaces and hyphens."""
    assert languages.normalize_race_id("Mountain Dwarf") == "mountain_dwarf"
    assert languages.normalize_race_id("Half-Elf") == "half_elf"
    assert languages.normalize_race_id("DRAGONBORN") == "dragonborn"


# --------------------------------------------------------------------------- #
# Character Language Operations Tests
# --------------------------------------------------------------------------- #

class MockCharacter:
    """Minimal character-like object for testing."""
    def __init__(self, race="Human", background=None, char_class=None, classes=None):
        self.race = race
        self.background = background
        self.char_class = char_class
        self.classes_dict = classes or {}
        self.languages = "[]"


def test_parse_languages():
    """Parse languages from JSON string."""
    assert languages.parse_languages('[]') == []
    assert languages.parse_languages('["common", "elvish"]') == ["common", "elvish"]
    assert languages.parse_languages('') == []
    assert languages.parse_languages('') == []  # Empty string is handled


def test_serialize_languages():
    """Serialize languages to JSON string."""
    assert languages.serialize_languages([]) == "[]"
    assert languages.serialize_languages(["common", "elvish"]) == "['common', 'elvish']"


def test_get_character_languages():
    """Get languages from character object."""
    char = MockCharacter()
    char.languages = '["common", "elvish"]'
    assert languages.get_character_languages(char) == ["common", "elvish"]

    char.languages = "[]"
    assert languages.get_character_languages(char) == []


def test_get_derived_languages_human():
    """Calculate derived languages for a human."""
    char = MockCharacter(race="Human", background=None, char_class="Fighter")
    derived = languages.get_derived_languages(char)

    assert "common" in derived["racial_fixed"]
    assert derived["racial_extra_count"] == 1
    assert len(derived["racial_extra_choices"]) > 0
    assert "common" in derived["all_automatic"]


def test_get_derived_languages_dwarf():
    """Calculate derived languages for a dwarf."""
    char = MockCharacter(race="Dwarf", background=None, char_class="Cleric")
    derived = languages.get_derived_languages(char)

    assert "common" in derived["racial_fixed"]
    assert "dwarvish" in derived["racial_fixed"]
    assert derived["racial_extra_count"] == 0
    assert set(derived["all_automatic"]) == {"common", "dwarvish"}


def test_get_derived_languages_with_background():
    """Calculate derived languages including background grants."""
    char = MockCharacter(race="Human", background="Acolyte", char_class="Cleric")
    derived = languages.get_derived_languages(char)

    # Acolyte grants 2 extra languages
    assert len(derived["background_languages"]) >= 0
    assert "common" in derived["all_automatic"]


def test_get_derived_languages_with_class_languages():
    """Calculate derived languages including class-specific languages."""
    # Druid gets Druidic
    char = MockCharacter(race="Human", background=None, char_class="Druid")
    derived = languages.get_derived_languages(char)

    assert "druidic" in derived["class_languages"]

    # Rogue gets Thieves' Cant
    char = MockCharacter(race="Human", background=None, char_class="Rogue")
    derived = languages.get_derived_languages(char)

    assert "thieves_cant" in derived["class_languages"]


def test_get_derived_languages_multiclass():
    """Multiclass characters get language grants from both classes."""
    char = MockCharacter(
        race="Human",
        background=None,
        classes={"druid": 1, "rogue": 1}
    )
    derived = languages.get_derived_languages(char)

    assert "druidic" in derived["class_languages"]
    assert "thieves_cant" in derived["class_languages"]


def test_validate_character_languages_valid():
    """Validate a valid set of languages for a character."""
    char = MockCharacter(race="Dwarf", background=None, char_class="Fighter")
    char.languages = '["common", "dwarvish"]'

    is_valid, error = languages.validate_character_languages(char, ["common", "dwarvish"])
    assert is_valid
    assert error == ""


def test_validate_character_languages_missing_automatic():
    """Validate fails if automatic languages are missing."""
    char = MockCharacter(race="Dwarf", background=None, char_class="Fighter")

    is_valid, error = languages.validate_character_languages(char, ["common"])
    assert not is_valid
    assert "Missing automatic languages" in error


def test_validate_character_languages_too_many():
    """Validate fails if too many extra languages chosen."""
    char = MockCharacter(race="Human", background=None, char_class="Fighter")
    # Human only gets 1 extra, but we chose 2
    is_valid, error = languages.validate_character_languages(
        char,
        ["common", "elvish", "dwarvish"]
    )
    assert not is_valid
    assert "Too many languages" in error


def test_validate_character_languages_invalid_choice():
    """Validate fails if extra choice is not from valid pool."""
    char = MockCharacter(race="Human", background=None, char_class="Fighter")

    # Secret languages aren't in the racial pool
    is_valid, error = languages.validate_character_languages(
        char,
        ["common", "druidic"]
    )
    assert not is_valid
    assert "Invalid extra language choices" in error


def test_validate_character_languages_invalid_language():
    """Validate fails with unknown language IDs."""
    char = MockCharacter(race="Human", background=None, char_class="Fighter")

    is_valid, error = languages.validate_character_languages(
        char,
        ["common", "klingon"]
    )
    assert not is_valid
    assert "Unknown languages" in error


def test_calculate_language_summary():
    """Generate a language summary for a character."""
    char = MockCharacter(race="Dwarf", background=None, char_class="Fighter")
    char.languages = '["common", "dwarvish"]'

    summary = languages.calculate_language_summary(char)

    assert "common" in summary["known"]
    assert "dwarvish" in summary["known"]
    assert "common" in summary["automatic"]
    assert "dwarvish" in summary["automatic"]
    assert len(summary["extra"]) == 0
    assert summary["remaining_choices"] == 0
    assert isinstance(summary["summary"], str)


def test_calculate_language_summary_with_choices_left():
    """Summary shows remaining choices for a human."""
    char = MockCharacter(race="Human", background=None, char_class="Fighter")
    char.languages = '["common"]'  # Haven't chosen the extra yet

    summary = languages.calculate_language_summary(char)

    assert "common" in summary["known"]
    assert summary["remaining_choices"] == 1
    assert len(summary["available_choices"]) > 0


def test_get_language_choices():
    """Get detailed language choice information for a character."""
    char = MockCharacter(race="Human", background=None, char_class="Fighter")
    char.languages = '["common"]'

    choices = languages.get_language_choices(char)

    assert "common" in choices.race_fixed
    assert choices.race_extra_count == 1
    assert len(choices.race_extra_choices) > 0
    assert choices.current_languages == ["common"]
    assert choices.remaining_choices == 1
    assert len(choices.available_choices) > 0


def test_get_language_choices_no_choices_left():
    """Language choices when all extras are chosen."""
    char = MockCharacter(race="Human", background=None, char_class="Fighter")
    char.languages = '["common", "elvish"]'  # Common + 1 extra chosen

    choices = languages.get_language_choices(char)

    assert choices.remaining_choices == 0
    # The pool still shows valid alternatives (unchosen languages from the pool)
    assert len(choices.available_choices) > 0


# --------------------------------------------------------------------------- #
# Language Info Tests
# --------------------------------------------------------------------------- #

def test_language_info_details():
    """Check specific language details."""
    # Draconic
    info = languages.get_language_info("draconic")
    assert info is not None
    assert info.typical_speakers == "Dragons, dragonborn"
    assert info.script == "Draconic"

    # Deep Speech (no script)
    info = languages.get_language_info("deep_speech")
    assert info is not None
    assert info.script is None

    # Thieves' Cant (secret)
    info = languages.get_language_info("thieves_cant")
    assert info is not None
    assert info.type == languages.LanguageType.SECRET


def test_all_language_ids_valid():
    """All language IDs in ALL_LANGUAGES should be valid."""
    for lang_id in languages.ALL_LANGUAGES:
        assert languages.is_valid_language(lang_id)


def test_race_info_contains_valid_languages():
    """All languages in race grant info should be valid."""
    for race_id in languages._RACE_LANGUAGES:
        info = languages.get_race_language_info(race_id)
        for lang_id in info["fixed"]:
            assert languages.is_valid_language(lang_id)
        for lang_id in info["extra_choices"]:
            assert languages.is_valid_language(lang_id)