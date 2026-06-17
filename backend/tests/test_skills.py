"""
Tests for the skill system engine and API.

Covers:
- Skill → ability mapping (all 18 skills)
- Class skill candidates & choice counts (all 12 core classes)
- Background skill proficiency
- Expertise grants (Rogue/Bard level thresholds) and slot counts
- Character proficiency queries (explicitly chosen vs auto-derived defaults)
- Feat-granted proficiency/expertise
- Skill modifier calculation (proficient, non-proficient, expertise, multiclass)
- Passive scores (Perception/Investigation/Insight) with adv/disadv
- Condition disadvantage effects (poisoned/restrained/blinded/deafened)
- Skill check execution (basic, advantage/disadvantage, condition disadvantage)
- Difficulty Class reference
- REST API endpoints (get skills, candidates, set proficiencies, set expertise,
  roll check, passive scores) and validation/error paths
"""
import json

import pytest

from app.engine import skills as sk
from app.engine.skills import (
    ALL_SKILLS,
    SKILL_ABILITIES,
    skill_ability,
    skills_for_ability,
    get_class_skill_info,
    get_class_skill_candidates,
    get_class_skill_count,
    get_background_skills,
    get_expertise_grants,
    get_expertise_slot_count,
    can_have_expertise,
    get_multiclass_expertise_slots,
    get_skill_proficiencies,
    get_skill_expertise,
    get_all_skill_proficiencies,
    get_all_skill_expertise,
    is_proficient,
    has_expertise,
    calculate_skill_modifier,
    calculate_skill_breakdown,
    calculate_passive_score,
    calculate_all_passive_scores,
    check_skill_disadvantage,
    check_skill_advantage,
    roll_skill_check,
    difficulty_class,
    DIFFICULTY_CLASSES,
    SkillCheckResult,
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
    }
    defaults.update(kw)
    return Character(**defaults)


def make_multiclass_character(classes: dict, **kw) -> Character:
    """Create a multiclass character."""
    defaults = {
        "name": "Multiclass Hero",
        "race": "Half-Elf",
        "char_class": "Wizard",
        "level": sum(classes.values()),
        "classes": json.dumps(classes),
        "background": "Sage",
        "strength": 10,
        "dexterity": 14,
        "constitution": 14,
        "intelligence": 18,
        "wisdom": 16,
        "charisma": 12,
        "max_hp": 40,
        "current_hp": 40,
        "armor_class": 13,
        "speed": 30,
        "xp": 14000,
        "asi_used": 0,
        "feats": "[]",
        "hit_dice_used": 0,
        "skill_proficiencies": "[]",
        "skill_expertise": "[]",
    }
    defaults.update(kw)
    return Character(**defaults)


# --------------------------------------------------------------------------- #
# Skill → ability mapping
# --------------------------------------------------------------------------- #

class TestSkillAbilityMapping:
    def test_all_18_skills_defined(self):
        assert len(ALL_SKILLS) == 18

    def test_strength_skill(self):
        assert skill_ability("athletics") == "strength"

    def test_dexterity_skills(self):
        assert skill_ability("acrobatics") == "dexterity"
        assert skill_ability("sleight_of_hand") == "dexterity"
        assert skill_ability("stealth") == "dexterity"

    def test_intelligence_skills(self):
        for s in ("arcana", "history", "investigation", "nature", "religion"):
            assert skill_ability(s) == "intelligence"

    def test_wisdom_skills(self):
        for s in ("animal_handling", "insight", "medicine", "perception", "survival"):
            assert skill_ability(s) == "wisdom"

    def test_charisma_skills(self):
        for s in ("deception", "intimidation", "performance", "persuasion"):
            assert skill_ability(s) == "charisma"

    def test_case_insensitive(self):
        assert skill_ability("Stealth") == "dexterity"
        assert skill_ability("ATHLETICS") == "strength"

    def test_unknown_skill_raises(self):
        with pytest.raises(ValueError, match="Unknown skill"):
            skill_ability("cooking")

    def test_skills_for_ability(self):
        dex_skills = skills_for_ability("dexterity")
        assert set(dex_skills) == {"acrobatics", "sleight_of_hand", "stealth"}

    def test_each_ability_has_expected_skills(self):
        assert len(skills_for_ability("strength")) == 1
        assert len(skills_for_ability("dexterity")) == 3
        assert len(skills_for_ability("intelligence")) == 5
        assert len(skills_for_ability("wisdom")) == 5
        assert len(skills_for_ability("charisma")) == 4
        assert len(skills_for_ability("constitution")) == 0

    def test_all_skills_map_to_valid_abilities(self):
        for s, a in SKILL_ABILITIES.items():
            assert a in ("strength", "dexterity", "constitution",
                         "intelligence", "wisdom", "charisma")


# --------------------------------------------------------------------------- #
# Class skill candidates
# --------------------------------------------------------------------------- #

class TestClassSkills:
    def test_rogue_gets_4_skills(self):
        assert get_class_skill_count("rogue") == 4

    def test_rogue_candidates(self):
        candidates = get_class_skill_candidates("rogue")
        assert "stealth" in candidates
        assert "sleight_of_hand" in candidates
        assert len(candidates) == 11

    def test_fighter_gets_2_skills(self):
        assert get_class_skill_count("fighter") == 2

    def test_ranger_gets_3_skills(self):
        assert get_class_skill_count("ranger") == 3

    def test_bard_any_returns_all_skills(self):
        candidates = get_class_skill_candidates("bard")
        assert set(candidates) == set(ALL_SKILLS)

    def test_bard_count_is_3(self):
        assert get_class_skill_count("bard") == 3

    def test_all_core_classes_defined(self):
        classes = ["barbarian", "bard", "cleric", "druid", "fighter",
                   "monk", "paladin", "ranger", "rogue", "sorcerer",
                   "warlock", "wizard"]
        for cls in classes:
            info = get_class_skill_info(cls)
            assert info["count"] >= 2
            assert info["count"] <= 4

    def test_unknown_class_empty(self):
        assert get_class_skill_count("commoner") == 0
        assert get_class_skill_candidates("commoner") == []

    def test_class_skills_subset_of_all_skills(self):
        for cls in ["fighter", "wizard", "rogue", "cleric", "paladin", "monk"]:
            for s in get_class_skill_candidates(cls):
                assert s in ALL_SKILLS


# --------------------------------------------------------------------------- #
# Background skills
# --------------------------------------------------------------------------- #

class TestBackgroundSkills:
    def test_soldier(self):
        assert set(get_background_skills("soldier")) == {"athletics", "intimidation"}

    def test_sage(self):
        assert set(get_background_skills("sage")) == {"arcana", "history"}

    def test_criminal(self):
        assert set(get_background_skills("criminal")) == {"deception", "stealth"}

    def test_case_insensitive_and_spaces(self):
        assert set(get_background_skills("Folk Hero")) == {"animal_handling", "survival"}

    def test_unknown_background_empty(self):
        assert get_background_skills("astronaut") == []

    def test_all_background_skills_valid(self):
        # Every background skill must be a real skill
        from app.engine.skills import _BACKGROUND_SKILLS
        for bg, skills_list in _BACKGROUND_SKILLS.items():
            for s in skills_list:
                assert s in ALL_SKILLS


# --------------------------------------------------------------------------- #
# Expertise
# --------------------------------------------------------------------------- #

class TestExpertise:
    def test_rogue_level_1_has_expertise(self):
        assert get_expertise_grants("rogue", 1) == 1
        assert get_expertise_slot_count("rogue", 1) == 2
        assert can_have_expertise("rogue", 1)

    def test_rogue_level_6_more_expertise(self):
        assert get_expertise_grants("rogue", 6) == 2
        assert get_expertise_slot_count("rogue", 6) == 4

    def test_rogue_level_5_still_2(self):
        # Between 1 and 6, still only the level-1 grant
        assert get_expertise_slot_count("rogue", 5) == 2

    def test_bard_level_2_no_expertise_yet(self):
        assert get_expertise_grants("bard", 2) == 0
        assert not can_have_expertise("bard", 2)

    def test_bard_level_3_has_expertise(self):
        assert get_expertise_slot_count("bard", 3) == 2

    def test_bard_level_10_full_expertise(self):
        assert get_expertise_slot_count("bard", 10) == 4

    def test_non_expertise_class(self):
        assert get_expertise_slot_count("fighter", 20) == 0
        assert get_expertise_slot_count("wizard", 20) == 0
        assert not can_have_expertise("cleric", 10)

    def test_multiclass_expertise_slots(self):
        # Rogue 6 + Bard 10 = 4 + 4 = 8
        assert get_multiclass_expertise_slots({"rogue": 6, "bard": 10}) == 8

    def test_multiclass_expertise_one_class(self):
        assert get_multiclass_expertise_slots({"rogue": 6, "wizard": 2}) == 4


# --------------------------------------------------------------------------- #
# Character proficiency queries
# --------------------------------------------------------------------------- #

class TestCharacterProficiencies:
    def test_explicit_proficiencies(self):
        char = make_character(
            skill_proficiencies=json.dumps(["athletics", "perception", "stealth"])
        )
        prof = get_skill_proficiencies(char)
        assert prof == {"athletics", "perception", "stealth"}

    def test_auto_derived_defaults(self):
        # No explicit proficiencies → auto-derive from class + background
        char = make_character(char_class="Fighter", classes='{"fighter": 5}',
                             background="Soldier")
        prof = get_skill_proficiencies(char)
        # Fighter gets 2 from list (first 2: acrobatics, animal_handling) + Soldier (athletics, intimidation)
        assert "acrobatics" in prof
        assert "animal_handling" in prof
        assert "athletics" in prof  # from Soldier background
        assert "intimidation" in prof  # from Soldier background

    def test_explicit_overrides_auto(self):
        char = make_character(
            char_class="Fighter", classes='{"fighter": 5}',
            background="Soldier",
            skill_proficiencies=json.dumps(["athletics", "history"]),
        )
        prof = get_skill_proficiencies(char)
        # Explicit choices used; background NOT auto-added
        assert prof == {"athletics", "history"}

    def test_expertise_query(self):
        char = make_character(skill_expertise=json.dumps(["stealth", "perception"]))
        exp = get_skill_expertise(char)
        assert exp == {"stealth", "perception"}

    def test_no_expertise_by_default(self):
        char = make_character()
        assert get_skill_expertise(char) == set()

    def test_is_proficient_helper(self):
        char = make_character(skill_proficiencies=json.dumps(["athletics"]))
        assert is_proficient("athletics", char)
        assert not is_proficient("stealth", char)

    def test_has_expertise_helper(self):
        char = make_character(
            skill_proficiencies=json.dumps(["stealth"]),
            skill_expertise=json.dumps(["stealth"]),
        )
        assert has_expertise("stealth", char)
        assert not has_expertise("athletics", char)

    def test_empty_string_columns(self):
        char = make_character(skill_proficiencies="", skill_expertise="")
        # Empty string → auto-derive for proficiencies, empty for expertise
        assert isinstance(get_skill_proficiencies(char), set)
        assert get_skill_expertise(char) == set()


# --------------------------------------------------------------------------- #
# Feat integration
# --------------------------------------------------------------------------- #

class TestFeatIntegration:
    def test_feat_skill_proficiency(self):
        char = make_character(
            skill_proficiencies=json.dumps(["athletics"]),
            feats=json.dumps([
                {"name": "Skilled", "effects": {"skill_proficiency": "stealth"}}
            ]),
        )
        all_profs = get_all_skill_proficiencies(char)
        assert "athletics" in all_profs
        assert "stealth" in all_profs

    def test_feat_skill_proficiency_list(self):
        char = make_character(
            skill_proficiencies="[]",
            feats=json.dumps([
                {"name": "Skilled",
                 "effects": {"skill_proficiencies": ["arcana", "history", "nature"]}}
            ]),
        )
        all_profs = get_all_skill_proficiencies(char)
        assert {"arcana", "history", "nature"} <= all_profs

    def test_feat_expertise(self):
        char = make_character(
            skill_proficiencies=json.dumps(["stealth"]),
            feats=json.dumps([
                {"name": "Skill Expert", "effects": {"expertise": "stealth"}}
            ]),
        )
        all_exp = get_all_skill_expertise(char)
        assert "stealth" in all_exp


# --------------------------------------------------------------------------- #
# Skill modifier calculation
# --------------------------------------------------------------------------- #

class TestSkillModifierCalculation:
    def test_proficient_skill(self):
        # Fighter level 5 (prof bonus +3), Str 16 (+3 mod)
        char = make_character(strength=16, skill_proficiencies=json.dumps(["athletics"]))
        mod = calculate_skill_modifier("athletics", char)
        assert mod == 3 + 3  # +3 prof + 3 ability

    def test_non_proficient_skill(self):
        # Fighter not proficient in Arcana; Int 10 (+0)
        char = make_character(intelligence=10, skill_proficiencies=json.dumps(["athletics"]))
        mod = calculate_skill_modifier("arcana", char)
        assert mod == 0

    def test_expertise_doubles_proficiency(self):
        # Rogue level 5 (prof +3), Dex 16 (+3). Expertise in stealth → +3 + 2*3 = 9
        char = make_character(
            char_class="Rogue", classes='{"rogue": 5}',
            dexterity=16,
            skill_proficiencies=json.dumps(["stealth"]),
            skill_expertise=json.dumps(["stealth"]),
        )
        mod = calculate_skill_modifier("stealth", char)
        assert mod == 3 + (3 * 2)  # ability + 2×proficiency

    def test_negative_ability_modifier(self):
        char = make_character(intelligence=8, skill_proficiencies=json.dumps(["arcana"]))
        # Int 8 → -1 mod, proficient (+3) → +2
        mod = calculate_skill_modifier("arcana", char)
        assert mod == -1 + 3

    def test_high_level_proficiency_bonus(self):
        # Level 17 → +6 proficiency
        char = make_character(
            char_class="Fighter", classes='{"fighter": 17}',
            level=17, strength=20,
            skill_proficiencies=json.dumps(["athletics"]),
        )
        mod = calculate_skill_modifier("athletics", char)
        # Str 20 → +5, prof +6 → +11
        assert mod == 5 + 6

    def test_unknown_skill_raises(self):
        char = make_character()
        with pytest.raises(ValueError, match="Unknown skill"):
            calculate_skill_modifier("cooking", char)

    def test_breakdown(self):
        char = make_character(strength=16, skill_proficiencies=json.dumps(["athletics"]))
        bd = calculate_skill_breakdown("athletics", char)
        assert bd["skill"] == "athletics"
        assert bd["ability"] == "strength"
        assert bd["ability_score"] == 16
        assert bd["ability_modifier"] == 3
        assert bd["proficient"] is True
        assert bd["expertise"] is False
        assert bd["proficiency_bonus"] == 3
        assert bd["modifier"] == 6
        assert bd["level"] == 5

    def test_breakdown_expertise(self):
        char = make_character(
            char_class="Rogue", classes='{"rogue": 5}',
            dexterity=16,
            skill_proficiencies=json.dumps(["stealth"]),
            skill_expertise=json.dumps(["stealth"]),
        )
        bd = calculate_skill_breakdown("stealth", char)
        assert bd["proficient"] is True
        assert bd["expertise"] is True
        assert bd["proficiency_bonus"] == 6  # doubled
        assert bd["modifier"] == 9


# --------------------------------------------------------------------------- #
# Passive scores
# --------------------------------------------------------------------------- #

class TestPassiveScores:
    def test_basic_passive_perception(self):
        # Wis 12 (+1), not proficient → 10 + 1 = 11
        char = make_character(wisdom=12, skill_proficiencies="[]")
        # Force no auto-derive by setting explicit empty? get_all adds feats only.
        # Use skill_proficiencies empty → auto-derive. To test non-proficient, set
        # explicit proficiencies that exclude perception.
        char.skill_proficiencies = json.dumps(["athletics"])
        pp = calculate_passive_score("perception", char)
        assert pp == 11

    def test_proficient_passive_perception(self):
        # Wis 12 (+1), proficient (+3) → 10 + 1 + 3 = 14
        char = make_character(wisdom=12, skill_proficiencies=json.dumps(["perception"]))
        pp = calculate_passive_score("perception", char)
        assert pp == 14

    def test_passive_with_advantage(self):
        char = make_character(wisdom=12, skill_proficiencies=json.dumps(["perception"]))
        pp = calculate_passive_score("perception", char, advantage=True)
        assert pp == 14 + 5  # 19

    def test_passive_with_disadvantage(self):
        char = make_character(wisdom=12, skill_proficiencies=json.dumps(["perception"]))
        pp = calculate_passive_score("perception", char, disadvantage=True)
        assert pp == 14 - 5  # 9

    def test_passive_advantage_and_disadvantage_cancel(self):
        char = make_character(wisdom=12, skill_proficiencies=json.dumps(["perception"]))
        pp = calculate_passive_score("perception", char, advantage=True, disadvantage=True)
        assert pp == 14

    def test_all_passive_scores(self):
        char = make_character(wisdom=14, intelligence=14, skill_proficiencies=json.dumps([]))
        char.skill_proficiencies = json.dumps(["athletics"])  # exclude passive skills
        scores = calculate_all_passive_scores(char)
        assert set(scores.keys()) == {"perception", "investigation", "insight"}
        # Wis 14 → +2, Int 14 → +2; all non-proficient → 12 each
        assert scores["perception"] == 12
        assert scores["investigation"] == 12
        assert scores["insight"] == 12


# --------------------------------------------------------------------------- #
# Condition effects
# --------------------------------------------------------------------------- #

class TestConditionEffects:
    def test_poisoned_disadvantage_on_all(self):
        for skill in ["athletics", "arcana", "stealth", "persuasion", "perception"]:
            assert check_skill_disadvantage(skill, ["poisoned"]), (
                f"poisoned should impose disadvantage on {skill}")

    def test_restrained_disadvantage_on_dex_skills(self):
        for skill in ["acrobatics", "sleight_of_hand", "stealth"]:
            assert check_skill_disadvantage(skill, ["restrained"])
        # Non-dex skills unaffected
        assert not check_skill_disadvantage("athletics", ["restrained"])
        assert not check_skill_disadvantage("arcana", ["restrained"])

    def test_blinded_disadvantage_on_perception(self):
        assert check_skill_disadvantage("perception", ["blinded"])
        # Other skills unaffected by blinded (in this model)
        assert not check_skill_disadvantage("athletics", ["blinded"])

    def test_deafened_disadvantage_on_perception(self):
        assert check_skill_disadvantage("perception", ["deafened"])

    def test_no_conditions_no_disadvantage(self):
        assert not check_skill_disadvantage("athletics", [])
        assert not check_skill_disadvantage("perception", [])

    def test_other_conditions_no_effect(self):
        for cond in ["charmed", "frightened", "invisible", "prone", "grappled"]:
            assert not check_skill_disadvantage("stealth", [cond])

    def test_advantage_never_from_conditions(self):
        for cond in ["poisoned", "restrained", "blinded"]:
            assert not check_skill_advantage("perception", [cond])


# --------------------------------------------------------------------------- #
# Skill check execution
# --------------------------------------------------------------------------- #

class TestSkillCheckExecution:
    def test_basic_check(self):
        char = make_character(strength=16, skill_proficiencies=json.dumps(["athletics"]))
        result = roll_skill_check("athletics", char, dc=15)
        assert result.skill == "athletics"
        assert result.ability == "strength"
        assert result.dc == 15
        assert result.proficient is True
        assert result.expertise is False
        assert result.modifier == 6
        assert isinstance(result.success, bool)
        assert result.total == result.roll.total

    def test_check_with_advantage(self):
        char = make_character(dexterity=14, skill_proficiencies=json.dumps(["stealth"]))
        result = roll_skill_check("stealth", char, dc=12, advantage=True)
        assert result.advantage
        assert not result.disadvantage
        assert len(result.roll.rolls) == 2

    def test_check_with_disadvantage(self):
        char = make_character(dexterity=14, skill_proficiencies=json.dumps(["stealth"]))
        result = roll_skill_check("stealth", char, dc=12, disadvantage=True)
        assert result.disadvantage
        assert not result.advantage
        assert len(result.roll.rolls) == 2

    def test_advantage_and_disadvantage_cancel(self):
        char = make_character(dexterity=14, skill_proficiencies=json.dumps(["stealth"]))
        result = roll_skill_check("stealth", char, dc=12,
                                  advantage=True, disadvantage=True)
        assert not result.advantage
        assert not result.disadvantage
        assert len(result.roll.rolls) == 1

    def test_poisoned_imposes_disadvantage(self):
        char = make_character(strength=16, skill_proficiencies=json.dumps(["athletics"]))
        result = roll_skill_check("athletics", char, dc=12, conditions=["poisoned"])
        assert result.disadvantage
        assert len(result.roll.rolls) == 2

    def test_restrained_dex_disadvantage(self):
        char = make_character(dexterity=16, skill_proficiencies=json.dumps(["stealth"]))
        result = roll_skill_check("stealth", char, dc=12, conditions=["restrained"])
        assert result.disadvantage

    def test_condition_disadvantage_cancels_explicit_advantage(self):
        # 5e: any disadvantage + advantage → neither (they cancel)
        char = make_character(strength=16, skill_proficiencies=json.dumps(["athletics"]))
        result = roll_skill_check("athletics", char, dc=12,
                                  advantage=True, conditions=["poisoned"])
        assert not result.advantage
        assert not result.disadvantage

    def test_non_proficient_check(self):
        char = make_character(intelligence=10, skill_proficiencies=json.dumps(["athletics"]))
        result = roll_skill_check("arcana", char, dc=10)
        assert result.proficient is False
        assert result.modifier == 0

    def test_expertise_check(self):
        char = make_character(
            char_class="Rogue", classes='{"rogue": 5}',
            dexterity=16,
            skill_proficiencies=json.dumps(["stealth"]),
            skill_expertise=json.dumps(["stealth"]),
        )
        result = roll_skill_check("stealth", char, dc=15)
        assert result.expertise is True
        assert result.modifier == 9  # +3 ability + 2×3 expertise

    def test_unknown_skill_raises(self):
        char = make_character()
        with pytest.raises(ValueError, match="Unknown skill"):
            roll_skill_check("cooking", char, dc=10)

    def test_description(self):
        char = make_character(dexterity=14, skill_proficiencies=json.dumps(["stealth"]))
        result = roll_skill_check("stealth", char, dc=15)
        assert "Stealth" in result.description
        assert "DC 15" in result.description

    def test_description_with_advantage(self):
        char = make_character(dexterity=14, skill_proficiencies=json.dumps(["stealth"]))
        result = roll_skill_check("stealth", char, dc=15, advantage=True)
        assert "advantage" in result.description.lower()

    def test_to_dict(self):
        char = make_character(strength=16, skill_proficiencies=json.dumps(["athletics"]))
        result = roll_skill_check("athletics", char, dc=15)
        d = result.to_dict()
        assert d["skill"] == "athletics"
        assert d["dc"] == 15
        assert "rolls" in d
        assert "success" in d


# --------------------------------------------------------------------------- #
# Difficulty classes
# --------------------------------------------------------------------------- #

class TestDifficultyClasses:
    def test_known_difficulties(self):
        assert difficulty_class("easy") == 10
        assert difficulty_class("medium") == 15
        assert difficulty_class("hard") == 20
        assert difficulty_class("nearly impossible") == 30

    def test_case_insensitive(self):
        assert difficulty_class("VERY_HARD") == 25

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown difficulty"):
            difficulty_class("trivial")


# --------------------------------------------------------------------------- #
# REST API
# --------------------------------------------------------------------------- #

class TestSkillsAPI:
    def _create_character(self, client, **overrides):
        payload = {
            "name": "Skill Test Hero",
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
        assert response.status_code == 200
        return response.json()["id"]

    def test_get_skills(self, client, db_session):
        char_id = self._create_character(client)
        response = client.get(f"/api/characters/{char_id}/skills")
        assert response.status_code == 200
        data = response.json()
        assert data["character_id"] == char_id
        assert len(data["skills"]) == 18
        # Each skill info has expected fields
        skill_names = [s["skill"] for s in data["skills"]]
        assert "athletics" in skill_names
        # Find athletics
        athletics = next(s for s in data["skills"] if s["skill"] == "athletics")
        assert athletics["ability"] == "strength"
        assert athletics["ability_modifier"] == 3
        # Default auto-derived: Soldier gives athletics proficiency
        assert athletics["proficient"] is True
        assert athletics["modifier"] == 6  # +3 ability + 3 proficiency
        assert "passive_scores" in data

    def test_get_skill_candidates(self, client, db_session):
        char_id = self._create_character(client, char_class="Rogue", level=3)
        response = client.get(f"/api/characters/{char_id}/skills/candidates")
        assert response.status_code == 200
        data = response.json()
        assert data["character_id"] == char_id
        # Rogue class choice
        rogue_choice = next(c for c in data["class_choices"] if c["class"] == "rogue")
        assert rogue_choice["count"] == 4
        assert "stealth" in rogue_choice["candidates"]
        # Background skills present
        assert "background_skills" in data

    def test_set_skill_proficiencies(self, client, db_session):
        char_id = self._create_character(client, char_class="Fighter", level=3)
        response = client.post(
            f"/api/characters/{char_id}/skills/proficiencies",
            json={"skills": ["athletics", "perception"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert "athletics" in data["proficiencies"]
        assert "perception" in data["proficiencies"]
        # Modifier reflects proficiency
        athletics = next(s for s in data["skills"] if s["skill"] == "athletics")
        assert athletics["proficient"] is True

    def test_set_too_many_proficiencies_rejected(self, client, db_session):
        # Fighter (2) + Soldier (2) = max 4
        char_id = self._create_character(client, char_class="Fighter", level=3,
                                         background="Soldier")
        response = client.post(
            f"/api/characters/{char_id}/skills/proficiencies",
            json={"skills": ["athletics", "perception", "stealth", "arcana", "history"]},
        )
        assert response.status_code == 400
        assert "Too many" in response.json()["detail"]

    def test_set_invalid_skill_rejected(self, client, db_session):
        char_id = self._create_character(client)
        response = client.post(
            f"/api/characters/{char_id}/skills/proficiencies",
            json={"skills": ["cooking"]},
        )
        assert response.status_code == 400
        assert "Invalid skill" in response.json()["detail"]

    def test_set_skill_not_in_class_list(self, client, db_session):
        # Fighter can't pick arcana
        char_id = self._create_character(client, char_class="Fighter", level=1,
                                         background="Soldier")
        response = client.post(
            f"/api/characters/{char_id}/skills/proficiencies",
            json={"skills": ["arcana"]},
        )
        assert response.status_code == 400
        assert "not in" in response.json()["detail"].lower()

    def test_set_expertise(self, client, db_session):
        char_id = self._create_character(client, char_class="Rogue", level=6)
        # First set proficiencies including stealth & perception
        client.post(
            f"/api/characters/{char_id}/skills/proficiencies",
            json={"skills": ["stealth", "perception"]},
        )
        response = client.post(
            f"/api/characters/{char_id}/skills/expertise",
            json={"skills": ["stealth", "perception"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert "stealth" in data["expertise"]
        assert "perception" in data["expertise"]
        stealth = next(s for s in data["skills"] if s["skill"] == "stealth")
        assert stealth["expertise"] is True

    def test_set_expertise_without_proficiency_rejected(self, client, db_session):
        char_id = self._create_character(client, char_class="Rogue", level=6)
        # Don't set proficiencies; expertise requires proficiency
        response = client.post(
            f"/api/characters/{char_id}/skills/expertise",
            json={"skills": ["stealth"]},
        )
        assert response.status_code == 400
        assert "proficiency" in response.json()["detail"].lower()

    def test_set_expertise_non_expertise_class_rejected(self, client, db_session):
        char_id = self._create_character(client, char_class="Fighter", level=5)
        client.post(
            f"/api/characters/{char_id}/skills/proficiencies",
            json={"skills": ["athletics"]},
        )
        response = client.post(
            f"/api/characters/{char_id}/skills/expertise",
            json={"skills": ["athletics"]},
        )
        assert response.status_code == 400

    def test_roll_skill_check(self, client, db_session):
        char_id = self._create_character(client)
        response = client.post(
            f"/api/characters/{char_id}/skills/check",
            json={"skill": "athletics", "dc": 15},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["skill"] == "athletics"
        assert data["dc"] == 15
        assert "total" in data
        assert "success" in data
        assert isinstance(data["success"], bool)

    def test_roll_check_with_conditions(self, client, db_session):
        char_id = self._create_character(client)
        response = client.post(
            f"/api/characters/{char_id}/skills/check",
            json={"skill": "athletics", "dc": 10, "conditions": ["poisoned"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["disadvantage"] is True

    def test_roll_invalid_skill_400(self, client, db_session):
        char_id = self._create_character(client)
        response = client.post(
            f"/api/characters/{char_id}/skills/check",
            json={"skill": "cooking", "dc": 10},
        )
        assert response.status_code == 400

    def test_get_passive_scores(self, client, db_session):
        char_id = self._create_character(client)
        response = client.get(f"/api/characters/{char_id}/skills/passive")
        assert response.status_code == 200
        data = response.json()
        assert data["character_id"] == char_id
        assert "perception" in data
        assert "investigation" in data
        assert "insight" in data

    def test_character_not_found_404(self, client, db_session):
        response = client.get("/api/characters/99999/skills")
        assert response.status_code == 404

    def test_skill_proficiencies_in_character_response(self, client, db_session):
        char_id = self._create_character(client)
        client.post(
            f"/api/characters/{char_id}/skills/proficiencies",
            json={"skills": ["athletics", "perception"]},
        )
        response = client.get(f"/api/characters/{char_id}")
        assert response.status_code == 200
        data = response.json()
        assert "skill_proficiencies" in data
        assert set(data["skill_proficiencies"]) == {"athletics", "perception"}
