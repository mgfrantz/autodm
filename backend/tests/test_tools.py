"""
Tests for the tool proficiency system engine and API.

Covers:
- Tool registry (all categories, tool defs, normalization)
- Class tool grants (fixed + choice) for the core classes
- Background tool grants (fixed + choice) for PHB backgrounds
- Character proficiency queries (explicitly chosen vs auto-derived defaults)
- Feat-granted tool proficiency
- Tool modifier calculation (proficient, non-proficient, ability override)
- Tool check execution (basic, advantage/disadvantage, condition disadvantage)
- Xanathar's combined skill+tool check advantage
- Difficulty Class reference
- REST API endpoints (get tools, candidates, set proficiencies, roll check,
  registry) and validation/error paths
- Save/load snapshot preserves tool_proficiencies
"""
import json

import pytest

from app.engine import tools as tl
from app.engine.tools import (
    ALL_TOOL_IDS,
    TOOL_CATEGORIES,
    TOOL_REGISTRY,
    ToolDef,
    get_tool_def,
    tools_in_category,
    normalize_tool_id,
    get_class_tool_grants,
    get_class_fixed_tools,
    get_class_tool_choice,
    get_background_tool_grants,
    get_background_fixed_tools,
    get_background_tool_choice,
    get_tool_proficiencies,
    get_all_tool_proficiencies,
    is_proficient_with_tool,
    calculate_tool_modifier,
    calculate_tool_breakdown,
    check_tool_disadvantage,
    check_tool_advantage,
    roll_tool_check,
    combined_check_advantage,
    difficulty_class,
    DIFFICULTY_CLASSES,
    ToolCheckResult,
)
from app.engine.dice import ability_modifier, proficiency_bonus
from app.models.models import Character


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #

def make_character(**kw) -> Character:
    """Create a test character with defaults."""
    defaults = {
        "name": "Test Hero",
        "race": "Human",
        "char_class": "Fighter",
        "level": 5,
        "classes": '{"fighter": 5}',
        "background": "Soldier",
        "strength": 16,
        "dexterity": 14,
        "constitution": 14,
        "intelligence": 10,
        "wisdom": 12,
        "charisma": 10,
        "max_hp": 45,
        "current_hp": 45,
        "armor_class": 16,
        "speed": 30,
        "xp": 6500,
        "asi_used": 1,
        "feats": "[]",
        "hit_dice_used": 0,
        "skill_proficiencies": "[]",
        "skill_expertise": "[]",
        "tool_proficiencies": "[]",
    }
    defaults.update(kw)
    return Character(**defaults)


# --------------------------------------------------------------------------- #
# Tool registry
# --------------------------------------------------------------------------- #

class TestToolRegistry:
    def test_has_all_five_categories(self):
        assert set(TOOL_CATEGORIES) == {
            "artisan", "gaming_set", "musical_instrument", "kit", "vehicle"
        }

    def test_every_category_has_tools(self):
        for cat in TOOL_CATEGORIES:
            assert len(tools_in_category(cat)) > 0, f"{cat} has no tools"

    def test_tool_count(self):
        # 16 artisan + 4 gaming + 19 instruments + 6 kits + 2 vehicles = 47
        assert len(ALL_TOOL_IDS) == 47

    def test_all_ids_unique(self):
        assert len(ALL_TOOL_IDS) == len(set(ALL_TOOL_IDS))

    def test_get_tool_def(self):
        td = get_tool_def("thieves_tools")
        assert isinstance(td, ToolDef)
        assert td.name == "Thieves' Tools"
        assert td.category == "kit"
        assert td.ability == "dexterity"

    def test_get_tool_def_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            get_tool_def("plasma_welder")

    def test_tools_in_category(self):
        artisan = tools_in_category("artisan")
        assert all(td.category == "artisan" for td in artisan)
        assert len(artisan) == 16

    def test_each_tool_has_valid_ability(self):
        valid = {"strength", "dexterity", "constitution",
                 "intelligence", "wisdom", "charisma"}
        for td in TOOL_REGISTRY.values():
            assert td.ability in valid, f"{td.id} has bad ability {td.ability}"

    def test_tool_ids_match_keys(self):
        for tid, td in TOOL_REGISTRY.items():
            assert td.id == tid


# --------------------------------------------------------------------------- #
# Tool id normalization
# --------------------------------------------------------------------------- #

class TestNormalizeToolId:
    def test_exact_id(self):
        assert normalize_tool_id("thieves_tools") == "thieves_tools"

    def test_uppercase(self):
        assert normalize_tool_id("THIEVES_TOOLS") == "thieves_tools"

    def test_spaces_to_underscores(self):
        assert normalize_tool_id("thieves tools") == "thieves_tools"

    def test_apostrophe_dropped(self):
        assert normalize_tool_id("thieve's tools") == "thieves_tools"
        assert normalize_tool_id("Smith's Tools") == "smiths_tools"

    def test_aliases(self):
        assert normalize_tool_id("navigator") == "navigator_tools"
        assert normalize_tool_id("disguise") == "disguise_kit"
        assert normalize_tool_id("forgery") == "forgery_kit"
        assert normalize_tool_id("land") == "land_vehicle"

    def test_lute(self):
        assert normalize_tool_id("Lute") == "lute"

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            normalize_tool_id("")

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            normalize_tool_id("plasma_welder")


# --------------------------------------------------------------------------- #
# Class tool grants
# --------------------------------------------------------------------------- #

class TestClassToolGrants:
    def test_rogue_gets_thieves_tools(self):
        assert get_class_fixed_tools("rogue") == ["thieves_tools"]
        assert get_class_tool_choice("rogue") is None

    def test_bard_choice_three_instruments(self):
        assert get_class_fixed_tools("bard") == []
        choice = get_class_tool_choice("bard")
        assert choice == {"count": 3, "categories": ["musical_instrument"]}

    def test_monk_choice_artisan_or_instrument(self):
        choice = get_class_tool_choice("monk")
        assert choice is not None
        assert choice["count"] == 1
        assert "artisan" in choice["categories"]
        assert "musical_instrument" in choice["categories"]

    def test_druid_gets_herbalism_kit(self):
        assert get_class_fixed_tools("druid") == ["herbalism_kit"]

    def test_tool_less_classes(self):
        for cls in ["fighter", "wizard", "cleric", "barbarian",
                    "paladin", "ranger", "sorcerer", "warlock"]:
            grant = get_class_tool_grants(cls)
            assert grant["fixed"] == []
            assert grant["choice"] is None

    def test_case_insensitive(self):
        assert get_class_fixed_tools("ROGUE") == ["thieves_tools"]

    def test_unknown_class_empty(self):
        assert get_class_tool_grants("astronaut") == {"fixed": [], "choice": None}

    def test_grants_returned_are_copies(self):
        g1 = get_class_tool_grants("bard")
        g1["choice"]["count"] = 99
        g2 = get_class_tool_grants("bard")
        assert g2["choice"]["count"] == 3  # unchanged


# --------------------------------------------------------------------------- #
# Background tool grants
# --------------------------------------------------------------------------- #

class TestBackgroundToolGrants:
    def test_criminal(self):
        assert "thieves_tools" in get_background_fixed_tools("criminal")
        choice = get_background_tool_choice("criminal")
        assert choice == {"count": 1, "categories": ["gaming_set"]}

    def test_charlatan(self):
        assert set(get_background_fixed_tools("charlatan")) == {"disguise_kit", "forgery_kit"}
        assert get_background_tool_choice("charlatan") is None

    def test_sailor(self):
        assert set(get_background_fixed_tools("sailor")) == {"navigator_tools", "water_vehicle"}

    def test_folk_hero(self):
        assert "land_vehicle" in get_background_fixed_tools("folk hero")
        choice = get_background_tool_choice("folk hero")
        assert choice == {"count": 1, "categories": ["artisan"]}

    def test_entertainer(self):
        assert "disguise_kit" in get_background_fixed_tools("entertainer")
        choice = get_background_tool_choice("entertainer")
        assert choice == {"count": 1, "categories": ["musical_instrument"]}

    def test_soldier(self):
        assert "land_vehicle" in get_background_fixed_tools("soldier")
        choice = get_background_tool_choice("soldier")
        assert choice == {"count": 1, "categories": ["gaming_set"]}

    def test_urchin(self):
        assert set(get_background_fixed_tools("urchin")) == {"disguise_kit", "forgery_kit"}

    def test_hermit(self):
        assert get_background_fixed_tools("hermit") == ["herbalism_kit"]

    def test_no_tool_backgrounds(self):
        for bg in ["acolyte", "sage"]:
            assert get_background_fixed_tools(bg) == []
            assert get_background_tool_choice(bg) is None

    def test_unknown_background_empty(self):
        assert get_background_tool_grants("astronaut") == {"fixed": [], "choice": None}

    def test_case_insensitive_and_spaces(self):
        assert "land_vehicle" in get_background_fixed_tools("Folk Hero")


# --------------------------------------------------------------------------- #
# Character proficiency queries
# --------------------------------------------------------------------------- #

class TestCharacterProficiencies:
    def test_explicit_proficiencies(self):
        char = make_character(tool_proficiencies=json.dumps(["thieves_tools", "lute"]))
        prof = get_tool_proficiencies(char)
        assert prof == {"thieves_tools", "lute"}

    def test_explicit_normalizes(self):
        char = make_character(tool_proficiencies=json.dumps(["Thieves' Tools", "Lute"]))
        prof = get_tool_proficiencies(char)
        assert prof == {"thieves_tools", "lute"}

    def test_auto_derived_rogue(self):
        # Rogue with Criminal background: fixed thieves_tools from both
        char = make_character(char_class="Rogue", classes='{"rogue": 5}',
                              background="Criminal")
        prof = get_tool_proficiencies(char)
        assert "thieves_tools" in prof
        # Choices (gaming set) are NOT auto-granted
        assert "dice_set" not in prof

    def test_auto_derived_sailor(self):
        char = make_character(background="Sailor")
        prof = get_tool_proficiencies(char)
        assert "navigator_tools" in prof
        assert "water_vehicle" in prof

    def test_auto_derived_druid(self):
        char = make_character(char_class="Druid", classes='{"druid": 3}',
                              background="Hermit")
        prof = get_tool_proficiencies(char)
        assert "herbalism_kit" in prof

    def test_explicit_overrides_auto(self):
        char = make_character(char_class="Rogue", classes='{"rogue": 5}',
                              background="Criminal",
                              tool_proficiencies=json.dumps(["lute"]))
        # Explicit list used directly; fixed thieves_tools NOT auto-added
        prof = get_tool_proficiencies(char)
        assert prof == {"lute"}

    def test_empty_string_column(self):
        char = make_character(tool_proficiencies="")
        # Fighter/Soldier fixed = land_vehicle only
        prof = get_tool_proficiencies(char)
        assert "land_vehicle" in prof

    def test_is_proficient_helper(self):
        char = make_character(tool_proficiencies=json.dumps(["thieves_tools"]))
        assert is_proficient_with_tool("thieves_tools", char)
        assert not is_proficient_with_tool("lute", char)

    def test_is_proficient_normalizes(self):
        char = make_character(tool_proficiencies=json.dumps(["thieves_tools"]))
        assert is_proficient_with_tool("Thieves' Tools", char)


# --------------------------------------------------------------------------- #
# Feat integration
# --------------------------------------------------------------------------- #

class TestFeatIntegration:
    def test_feat_tool_proficiency(self):
        char = make_character(
            tool_proficiencies=json.dumps(["thieves_tools"]),
            feats=json.dumps([
                {"name": "Skilled", "effects": {"tool_proficiency": "lute"}}
            ]),
        )
        all_profs = get_all_tool_proficiencies(char)
        assert "thieves_tools" in all_profs
        assert "lute" in all_profs

    def test_feat_tool_proficiency_list(self):
        char = make_character(
            tool_proficiencies="[]",
            feats=json.dumps([
                {"name": "Skilled",
                 "effects": {"tool_proficiencies": ["dice_set", "forgery_kit", "lute"]}}
            ]),
        )
        all_profs = get_all_tool_proficiencies(char)
        assert {"dice_set", "forgery_kit", "lute"} <= all_profs

    def test_feat_unknown_tool_ignored(self):
        char = make_character(
            tool_proficiencies="[]",
            feats=json.dumps([
                {"name": "Skilled", "effects": {"tool_proficiency": "plasma_welder"}}
            ]),
        )
        all_profs = get_all_tool_proficiencies(char)
        assert "plasma_welder" not in all_profs

    def test_feat_garbage_ignored(self):
        char = make_character(
            tool_proficiencies="[]",
            feats="not json",
        )
        assert get_all_tool_proficiencies(char) >= set()  # no crash


# --------------------------------------------------------------------------- #
# Tool modifier calculation
# --------------------------------------------------------------------------- #

class TestToolModifierCalculation:
    def test_proficient_thieves_tools(self):
        # Dex 14 (+2), level 5 (prof +3) → 5
        char = make_character(dexterity=14, tool_proficiencies=json.dumps(["thieves_tools"]))
        mod = calculate_tool_modifier("thieves_tools", char)
        assert mod == 2 + 3

    def test_non_proficient(self):
        # Dex 14 (+2), not proficient → 2
        char = make_character(dexterity=14, tool_proficiencies=json.dumps(["lute"]))
        mod = calculate_tool_modifier("thieves_tools", char)
        assert mod == 2

    def test_artisan_intelligence(self):
        # Smith's tools default to Int. Int 16 (+3), level 5 (+3) → 6
        char = make_character(intelligence=16, tool_proficiencies=json.dumps(["smiths_tools"]))
        mod = calculate_tool_modifier("smiths_tools", char)
        assert mod == 3 + 3

    def test_instrument_charisma(self):
        # Lute defaults to Cha. Cha 16 (+3), level 5 (+3) → 6
        char = make_character(charisma=16, tool_proficiencies=json.dumps(["lute"]))
        mod = calculate_tool_modifier("lute", char)
        assert mod == 3 + 3

    def test_ability_override(self):
        # Thieves' tools (Dex) but override to Intelligence (10 → +0)
        char = make_character(dexterity=14, intelligence=10,
                              tool_proficiencies=json.dumps(["thieves_tools"]))
        mod = calculate_tool_modifier("thieves_tools", char, ability="intelligence")
        assert mod == 0 + 3  # +0 Int mod, +3 prof

    def test_high_level_proficiency(self):
        # Level 17 → +6 proficiency
        char = make_character(
            dexterity=18, level=17, classes='{"rogue": 17}',
            tool_proficiencies=json.dumps(["thieves_tools"]),
        )
        mod = calculate_tool_modifier("thieves_tools", char)
        assert mod == 4 + 6  # +4 Dex, +6 prof

    def test_negative_ability_modifier(self):
        # Int 8 → -1, proficient (+3) → +2
        char = make_character(intelligence=8, tool_proficiencies=json.dumps(["herbalism_kit"]))
        mod = calculate_tool_modifier("herbalism_kit", char)
        assert mod == -1 + 3

    def test_unknown_tool_raises(self):
        char = make_character()
        with pytest.raises(ValueError, match="Unknown tool"):
            calculate_tool_modifier("plasma_welder", char)

    def test_invalid_ability_raises(self):
        char = make_character(tool_proficiencies=json.dumps(["lute"]))
        with pytest.raises(ValueError, match="Invalid ability"):
            calculate_tool_modifier("lute", char, ability="luck")

    def test_breakdown(self):
        char = make_character(dexterity=14, tool_proficiencies=json.dumps(["thieves_tools"]))
        bd = calculate_tool_breakdown("thieves_tools", char)
        assert bd["tool"] == "thieves_tools"
        assert bd["name"] == "Thieves' Tools"
        assert bd["category"] == "kit"
        assert bd["default_ability"] == "dexterity"
        assert bd["ability"] == "dexterity"
        assert bd["ability_score"] == 14
        assert bd["ability_modifier"] == 2
        assert bd["proficient"] is True
        assert bd["proficiency_bonus"] == 3
        assert bd["modifier"] == 5
        assert bd["level"] == 5

    def test_breakdown_non_proficient(self):
        char = make_character(tool_proficiencies=json.dumps(["lute"]))
        bd = calculate_tool_breakdown("thieves_tools", char)
        assert bd["proficient"] is False
        assert bd["proficiency_bonus"] == 0
        assert bd["modifier"] == bd["ability_modifier"]


# --------------------------------------------------------------------------- #
# Condition effects
# --------------------------------------------------------------------------- #

class TestConditionEffects:
    def test_poisoned_disadvantage_on_all(self):
        for ability in ["strength", "dexterity", "intelligence", "charisma"]:
            assert check_tool_disadvantage(ability, ["poisoned"])

    def test_restrained_dex_disadvantage(self):
        assert check_tool_disadvantage("dexterity", ["restrained"])
        assert not check_tool_disadvantage("intelligence", ["restrained"])

    def test_no_conditions_no_disadvantage(self):
        assert not check_tool_disadvantage("dexterity", [])

    def test_other_conditions_no_effect(self):
        for cond in ["charmed", "frightened", "invisible", "prone"]:
            assert not check_tool_disadvantage("dexterity", [cond])

    def test_advantage_never_from_conditions(self):
        for cond in ["poisoned", "restrained", "blinded"]:
            assert not check_tool_advantage("dexterity", [cond])


# --------------------------------------------------------------------------- #
# Tool check execution
# --------------------------------------------------------------------------- #

class TestToolCheckExecution:
    def test_basic_check(self):
        char = make_character(dexterity=14, tool_proficiencies=json.dumps(["thieves_tools"]))
        result = roll_tool_check("thieves_tools", char, dc=15)
        assert result.tool == "thieves_tools"
        assert result.name == "Thieves' Tools"
        assert result.category == "kit"
        assert result.ability == "dexterity"
        assert result.dc == 15
        assert result.proficient is True
        assert result.modifier == 5
        assert isinstance(result.success, bool)
        assert result.total == result.roll.total

    def test_check_with_advantage(self):
        char = make_character(dexterity=14, tool_proficiencies=json.dumps(["thieves_tools"]))
        result = roll_tool_check("thieves_tools", char, dc=12, advantage=True)
        assert result.advantage
        assert not result.disadvantage
        assert len(result.roll.rolls) == 2

    def test_check_with_disadvantage(self):
        char = make_character(dexterity=14, tool_proficiencies=json.dumps(["thieves_tools"]))
        result = roll_tool_check("thieves_tools", char, dc=12, disadvantage=True)
        assert result.disadvantage
        assert not result.advantage
        assert len(result.roll.rolls) == 2

    def test_advantage_and_disadvantage_cancel(self):
        char = make_character(dexterity=14, tool_proficiencies=json.dumps(["thieves_tools"]))
        result = roll_tool_check("thieves_tools", char, dc=12,
                                 advantage=True, disadvantage=True)
        assert not result.advantage
        assert not result.disadvantage
        assert len(result.roll.rolls) == 1

    def test_poisoned_imposes_disadvantage(self):
        char = make_character(dexterity=14, tool_proficiencies=json.dumps(["thieves_tools"]))
        result = roll_tool_check("thieves_tools", char, dc=12, conditions=["poisoned"])
        assert result.disadvantage

    def test_condition_disadvantage_cancels_explicit_advantage(self):
        char = make_character(dexterity=14, tool_proficiencies=json.dumps(["thieves_tools"]))
        result = roll_tool_check("thieves_tools", char, dc=12,
                                 advantage=True, conditions=["poisoned"])
        assert not result.advantage
        assert not result.disadvantage

    def test_non_proficient_check(self):
        char = make_character(dexterity=14, tool_proficiencies=json.dumps(["lute"]))
        result = roll_tool_check("thieves_tools", char, dc=10)
        assert result.proficient is False
        assert result.modifier == 2  # Dex only

    def test_ability_override_check(self):
        # Thieves' tools with Int override (10 → +0), proficient → +3
        char = make_character(intelligence=10, tool_proficiencies=json.dumps(["thieves_tools"]))
        result = roll_tool_check("thieves_tools", char, dc=10, ability="intelligence")
        assert result.ability == "intelligence"
        assert result.modifier == 3

    def test_unknown_tool_raises(self):
        char = make_character()
        with pytest.raises(ValueError, match="Unknown tool"):
            roll_tool_check("plasma_welder", char, dc=10)

    def test_description(self):
        char = make_character(dexterity=14, tool_proficiencies=json.dumps(["thieves_tools"]))
        result = roll_tool_check("thieves_tools", char, dc=15)
        assert "Thieves' Tools" in result.description
        assert "DC 15" in result.description

    def test_description_with_advantage(self):
        char = make_character(dexterity=14, tool_proficiencies=json.dumps(["thieves_tools"]))
        result = roll_tool_check("thieves_tools", char, dc=15, advantage=True)
        assert "advantage" in result.description.lower()

    def test_to_dict(self):
        char = make_character(dexterity=14, tool_proficiencies=json.dumps(["thieves_tools"]))
        result = roll_tool_check("thieves_tools", char, dc=15)
        d = result.to_dict()
        assert d["tool"] == "thieves_tools"
        assert d["dc"] == 15
        assert "rolls" in d
        assert "success" in d


# --------------------------------------------------------------------------- #
# Xanathar's combined checks
# --------------------------------------------------------------------------- #

class TestCombinedCheckAdvantage:
    def test_both_proficient_grants_advantage(self):
        assert combined_check_advantage(True, True)

    def test_skill_only_no_advantage(self):
        assert not combined_check_advantage(True, False)

    def test_tool_only_no_advantage(self):
        assert not combined_check_advantage(False, True)

    def test_neither_no_advantage(self):
        assert not combined_check_advantage(False, False)


# --------------------------------------------------------------------------- #
# Difficulty classes
# --------------------------------------------------------------------------- #

class TestDifficultyClasses:
    def test_known_difficulties(self):
        assert difficulty_class("easy") == 10
        assert difficulty_class("hard") == 20

    def test_case_insensitive(self):
        assert difficulty_class("VERY_HARD") == 25

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown difficulty"):
            difficulty_class("trivial")


# --------------------------------------------------------------------------- #
# REST API
# --------------------------------------------------------------------------- #

class TestToolsAPI:
    def _create_character(self, client, **overrides):
        payload = {
            "name": "Tool Test Hero",
            "race": "Human",
            "char_class": "Fighter",
            "level": 5,
            "background": "Soldier",
            "strength": 16,
            "dexterity": 14,
            "constitution": 14,
            "intelligence": 10,
            "wisdom": 12,
            "charisma": 10,
        }
        payload.update(overrides)
        response = client.post("/api/characters", json=payload)
        assert response.status_code == 200, response.text
        return response.json()["id"]

    def test_get_tools(self, client, db_session):
        char_id = self._create_character(client, char_class="Rogue", background="Criminal")
        response = client.get(f"/api/characters/{char_id}/tools")
        assert response.status_code == 200
        data = response.json()
        assert data["character_id"] == char_id
        # Rogue + Criminal → thieves_tools auto-granted
        assert "thieves_tools" in data["proficiencies"]
        # All five categories present
        assert set(data["tools_by_category"].keys()) == set(TOOL_CATEGORIES)
        # thieves_tools lives in the kit category
        kit_tools = data["tools_by_category"]["kit"]
        tt = next(t for t in kit_tools if t["tool"] == "thieves_tools")
        assert tt["proficient"] is True
        assert tt["ability"] == "dexterity"
        assert tt["modifier"] == 5  # Dex 14 (+2) + prof 3

    def test_get_tool_candidates(self, client, db_session):
        char_id = self._create_character(client, char_class="Bard", background="Entertainer")
        response = client.get(f"/api/characters/{char_id}/tools/candidates")
        assert response.status_code == 200
        data = response.json()
        assert data["character_id"] == char_id
        # Bard grants 3 instruments
        bard_grant = next(g for g in data["class_grants"] if g["class"] == "bard")
        assert bard_grant["choice"]["count"] == 3
        assert "musical_instrument" in bard_grant["choice"]["categories"]
        # Entertainer grants disguise kit + 1 instrument
        assert "disguise_kit" in data["background_grants"]["fixed"]
        assert data["background_grants"]["choice"]["categories"] == ["musical_instrument"]

    def test_set_tool_proficiencies(self, client, db_session):
        # Bard + Entertainer: fixed disguise_kit, choices 3 (bard inst) + 1 (entertainer inst)
        char_id = self._create_character(client, char_class="Bard", background="Entertainer")
        response = client.post(
            f"/api/characters/{char_id}/tools/proficiencies",
            json={"tools": ["lute", "flute", "drums", "lyre"]},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert "lute" in data["proficiencies"]
        assert "disguise_kit" in data["proficiencies"]  # fixed, auto-added

    def test_set_too_many_choices_rejected(self, client, db_session):
        # Fighter + Soldier: fixed land_vehicle, choice = 1 gaming set
        char_id = self._create_character(client, char_class="Fighter", background="Soldier")
        response = client.post(
            f"/api/characters/{char_id}/tools/proficiencies",
            json={"tools": ["dice_set", "dragonchess_set", "playing_card_set"]},
        )
        assert response.status_code == 400
        assert "Too many" in response.json()["detail"]

    def test_set_unknown_tool_rejected(self, client, db_session):
        char_id = self._create_character(client)
        response = client.post(
            f"/api/characters/{char_id}/tools/proficiencies",
            json={"tools": ["plasma_welder"]},
        )
        assert response.status_code == 400
        assert "Unknown tool" in response.json()["detail"]

    def test_set_proficiencies_normalizes(self, client, db_session):
        char_id = self._create_character(client, char_class="Fighter", background="Soldier")
        response = client.post(
            f"/api/characters/{char_id}/tools/proficiencies",
            json={"tools": ["Dice Set"]},
        )
        assert response.status_code == 200
        assert "dice_set" in response.json()["proficiencies"]

    def test_roll_tool_check(self, client, db_session):
        char_id = self._create_character(client, char_class="Rogue", background="Criminal")
        response = client.post(
            f"/api/characters/{char_id}/tools/check",
            json={"tool": "thieves_tools", "dc": 15},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["tool"] == "thieves_tools"
        assert data["dc"] == 15
        assert data["proficient"] is True
        assert "total" in data
        assert isinstance(data["success"], bool)

    def test_roll_check_with_ability_override(self, client, db_session):
        char_id = self._create_character(client, char_class="Rogue", background="Criminal")
        response = client.post(
            f"/api/characters/{char_id}/tools/check",
            json={"tool": "thieves_tools", "dc": 10, "ability": "intelligence"},
        )
        assert response.status_code == 200
        assert response.json()["ability"] == "intelligence"

    def test_roll_check_with_conditions(self, client, db_session):
        char_id = self._create_character(client, char_class="Rogue", background="Criminal")
        response = client.post(
            f"/api/characters/{char_id}/tools/check",
            json={"tool": "thieves_tools", "dc": 10, "conditions": ["poisoned"]},
        )
        assert response.status_code == 200
        assert response.json()["disadvantage"] is True

    def test_roll_invalid_tool_400(self, client, db_session):
        char_id = self._create_character(client)
        response = client.post(
            f"/api/characters/{char_id}/tools/check",
            json={"tool": "plasma_welder", "dc": 10},
        )
        assert response.status_code == 400

    def test_get_registry(self, client, db_session):
        char_id = self._create_character(client)
        response = client.get(f"/api/characters/{char_id}/tools/registry")
        assert response.status_code == 200
        data = response.json()
        assert set(data["categories"]) == set(TOOL_CATEGORIES)
        kit_tools = data["tools_by_category"]["kit"]
        assert any(t["id"] == "thieves_tools" for t in kit_tools)

    def test_character_not_found_404(self, client, db_session):
        assert client.get("/api/characters/99999/tools").status_code == 404

    def test_tool_proficiencies_in_character_response(self, client, db_session):
        char_id = self._create_character(client, char_class="Fighter", background="Soldier")
        client.post(
            f"/api/characters/{char_id}/tools/proficiencies",
            json={"tools": ["dice_set"]},
        )
        response = client.get(f"/api/characters/{char_id}")
        assert response.status_code == 200
        data = response.json()
        assert "tool_proficiencies" in data
        assert "dice_set" in data["tool_proficiencies"]
        assert "land_vehicle" in data["tool_proficiencies"]  # fixed Soldier grant


# --------------------------------------------------------------------------- #
# Save/load snapshot preserves tool_proficiencies
# --------------------------------------------------------------------------- #

class TestSaveLoadSnapshot:
    def test_capture_and_apply_round_trip(self):
        from app.api.saves import capture_character_snapshot, apply_character_snapshot
        char = make_character(tool_proficiencies=json.dumps(["thieves_tools", "lute"]))
        snap = capture_character_snapshot(char)
        assert snap["tool_proficiencies"] == ["thieves_tools", "lute"]

        # Apply to a fresh character with no tools
        fresh = make_character(tool_proficiencies=json.dumps([]))
        apply_character_snapshot(fresh, snap)
        assert fresh.tool_proficiencies == json.dumps(["lute", "thieves_tools"]) or \
               fresh.tool_proficiencies == json.dumps(["thieves_tools", "lute"])

    def test_snapshot_handles_missing_key(self, client, db_session):
        # An old snapshot without tool_proficiencies must not crash restore.
        from app.api.saves import apply_character_snapshot
        fresh = make_character(tool_proficiencies=json.dumps([]))
        apply_character_snapshot(fresh, {"max_hp": 1})
        assert fresh.max_hp == 1
        # tool_proficiencies untouched
        assert fresh.tool_proficiencies == json.dumps([])
