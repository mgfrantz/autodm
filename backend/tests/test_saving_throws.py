"""
Tests for the saving throws engine and API.

Covers:
- Class saving throw proficiency queries
- Multiclassing: union of all class proficiencies
- Feat-based proficiency (Resilient feat)
- Saving throw bonus calculation (proficiency + ability mod)
- Save execution with advantage/disadvantage
- Condition effects: auto-fail (paralyzed/petrified/unconscious on Str/Dex),
  disadvantage (restrained on Dex)
- Save DC calculation
- REST API endpoints for proficiencies, rolling, and DC calculation
"""
import pytest

from app.engine import saving_throws as st
from app.engine.saving_throws import (
    ABILITIES,
    get_class_saving_throws,
    get_multiclass_saving_throws,
    get_saving_throw_proficiencies,
    calculate_save_bonus,
    roll_saving_throw,
    check_save_auto_fail,
    check_save_disadvantage,
    calculate_save_dc,
    calculate_character_save_dc,
    SaveResult,
)
from app.engine.dice import ability_modifier, proficiency_bonus
from app.models.models import Character, World, GameSave


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
    }
    defaults.update(kw)
    return Character(**defaults)


def make_multiclass_character(classes: dict[str, int], **kw) -> Character:
    """Create a multiclass character."""
    import json
    defaults = {
        "name": "Multiclass Hero",
        "race": "Half-Elf",
        "char_class": "Wizard",  # Primary class for backward compat
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
    }
    defaults.update(kw)
    return Character(**defaults)


# --------------------------------------------------------------------------- #
# Class proficiency queries
# --------------------------------------------------------------------------- #

class TestClassSavingThrows:
    def test_fighter_saving_throws(self):
        prof = get_class_saving_throws("Fighter")
        assert prof == {"strength", "constitution"}

    def test_wizard_saving_throws(self):
        prof = get_class_saving_throws("Wizard")
        assert prof == {"intelligence", "wisdom"}

    def test_rogue_saving_throws(self):
        prof = get_class_saving_throws("Rogue")
        assert prof == {"dexterity", "intelligence"}

    def test_cleric_saving_throws(self):
        prof = get_class_saving_throws("Cleric")
        assert prof == {"wisdom", "charisma"}

    def test_barbarian_saving_throws(self):
        prof = get_class_saving_throws("Barbarian")
        assert prof == {"strength", "constitution"}

    def test_all_core_classes_defined(self):
        classes = ["barbarian", "bard", "cleric", "druid", "fighter",
                   "monk", "paladin", "ranger", "rogue", "sorcerer",
                   "warlock", "wizard"]
        for cls in classes:
            prof = get_class_saving_throws(cls)
            assert isinstance(prof, set)
            assert len(prof) == 2
            assert all(a in ABILITIES for a in prof)

    def test_unknown_class_returns_empty_set(self):
        prof = get_class_saving_throws("commoner")
        assert prof == set()


# --------------------------------------------------------------------------- #
# Multiclass proficiency (union)
# --------------------------------------------------------------------------- #

class TestMulticlassSavingThrows:
    def test_single_class_union(self):
        prof = get_multiclass_saving_throws({"fighter": 5})
        assert prof == {"strength", "constitution"}

    def test_two_classes_union(self):
        prof = get_multiclass_saving_throws({"fighter": 3, "wizard": 2})
        # Fighter: Str/Con, Wizard: Int/Wis
        assert prof == {"strength", "constitution", "intelligence", "wisdom"}

    def test_three_classes_union(self):
        prof = get_multiclass_saving_throws({"fighter": 2, "rogue": 2, "cleric": 1})
        # Fighter: Str/Con, Rogue: Dex/Int, Cleric: Wis/Cha
        assert prof == {"strength", "constitution", "dexterity",
                       "intelligence", "wisdom", "charisma"}

    def test_overlap_no_duplicates(self):
        # Fighter and Barbarian both have Str/Con
        prof = get_multiclass_saving_throws({"fighter": 2, "barbarian": 1})
        assert prof == {"strength", "constitution"}
        assert len(prof) == 2


# --------------------------------------------------------------------------- #
# Character proficiency queries
# --------------------------------------------------------------------------- #

class TestCharacterProficiencies:
    def test_single_class_proficiencies(self):
        char = make_character(char_class="Wizard", level=3, classes='{"wizard": 3}')
        prof = get_saving_throw_proficiencies(char)
        assert prof == {"intelligence", "wisdom"}

    def test_multiclass_proficiencies(self):
        char = make_multiclass_character({"fighter": 2, "rogue": 2})
        prof = get_saving_throw_proficiencies(char)
        assert prof == {"strength", "constitution", "dexterity", "intelligence"}

    def test_resilient_feat_adds_proficiency(self):
        import json
        char = make_character(feats=json.dumps([
            {"name": "Resilient (Constitution)", "description": "+1 Con, Con save proficiency",
             "effects": {"save_proficiency": "constitution"}}
        ]))
        prof = get_saving_throw_proficiencies(char)
        # Fighter: Str/Con + Resilient: Con = Str/Con (no duplicate)
        assert prof == {"strength", "constitution"}

    def test_resilient_feat_new_proficiency(self):
        import json
        # Fighter gets Str/Con, add Resilient Wisdom
        char = make_character(char_class="Fighter", level=3, classes='{"fighter": 3}',
                             feats=json.dumps([
            {"name": "Resilient (Wisdom)", "description": "+1 Wis, Wis save proficiency",
             "effects": {"save_proficiency": "wisdom"}}
        ]))
        prof = get_saving_throw_proficiencies(char)
        assert prof == {"strength", "constitution", "wisdom"}

    def test_backward_compat_single_class_no_classes_dict(self):
        char = make_character(char_class="Wizard", level=3, classes="{}")
        prof = get_saving_throw_proficiencies(char)
        assert prof == {"intelligence", "wisdom"}

    def test_resilient_persisted_format_effects_applied(self):
        """The REAL format produced by the feats learn flow: base feat name
        ("Resilient", no parentheses) + effects stored under ``effects_applied``
        with key ``saving_throw_proficiency``. This previously went undetected
        because the engine read ``effects``/``save_proficiency``."""
        import json
        char = make_character(
            char_class="Fighter", level=3, classes='{"fighter": 3}',
            feats=json.dumps([{
                "name": "Resilient",
                "description": "+1 Wis, Wis save proficiency",
                "effects_applied": {"saving_throw_proficiency": "wisdom"},
                "ability_changes": {"wisdom": 1},
                "learned_at_level": 3,
            }]),
        )
        prof = get_saving_throw_proficiencies(char)
        assert "wisdom" in prof
        assert prof == {"strength", "constitution", "wisdom"}

    def test_feat_save_sources_real_format(self):
        """get_feat_saving_throw_sources attributes the right feat name."""
        import json
        from app.engine.saving_throws import get_feat_saving_throw_sources
        char = make_character(feats=json.dumps([{
            "name": "Resilient",
            "effects_applied": {"saving_throw_proficiency": "wisdom"},
        }]))
        assert get_feat_saving_throw_sources(char) == {"wisdom": "Resilient"}

    def test_feat_save_sources_name_parens_format(self):
        """Legacy/fixture format: ability encoded in the feat name."""
        from app.engine.saving_throws import get_feat_saving_throw_sources
        char = make_character(feats='[{"name": "Resilient (Wisdom)"}]')
        assert get_feat_saving_throw_sources(char) == {"wisdom": "Resilient (Wisdom)"}

    def test_feat_save_sources_empty(self):
        """No feats → no feat save sources."""
        from app.engine.saving_throws import get_feat_saving_throw_sources
        char = make_character(feats="[]")
        assert get_feat_saving_throw_sources(char) == {}



# --------------------------------------------------------------------------- #
# Save bonus calculation
# --------------------------------------------------------------------------- #

class TestSaveBonusCalculation:
    def test_proficient_save_bonus(self):
        char = make_character(strength=16)  # +3 mod, level 5 -> +3 prof
        bonus = calculate_save_bonus("strength", char)
        # Proficient: +3 (prof) + 3 (mod) = +6
        assert bonus == 6

    def test_non_proficient_save_bonus(self):
        char = make_character(dexterity=14)  # +2 mod
        # Fighter not proficient in Dex
        bonus = calculate_save_bonus("dexterity", char)
        # Not proficient: 0 + 2 (mod) = +2
        assert bonus == 2

    def test_negative_ability_modifier(self):
        char = make_character(intelligence=8)  # -1 mod
        bonus = calculate_save_bonus("intelligence", char)
        # Fighter not proficient in Int: 0 + (-1) = -1
        assert bonus == -1

    def test_high_level_proficiency_bonus(self):
        char = make_character(strength=18, level=17)  # +4 mod, +6 prof
        bonus = calculate_save_bonus("strength", char)
        # Proficient: 6 + 4 = +10
        assert bonus == 10

    def test_multiclass_proficiency_bonus(self):
        char = make_multiclass_character({"fighter": 2, "wizard": 2},
                                        strength=16, intelligence=18)
        # Fighter level 2, Wizard level 2 -> total level 4 -> +2 prof
        # Strength: proficient (+2 prof + 3 mod) = +5
        assert calculate_save_bonus("strength", char) == 5
        # Intelligence: proficient (+2 prof + 4 mod) = +6
        assert calculate_save_bonus("intelligence", char) == 6
        # Dexterity: not proficient (0 + 2 mod) = +2
        assert calculate_save_bonus("dexterity", char) == 2


# --------------------------------------------------------------------------- #
# Condition effects on saves
# --------------------------------------------------------------------------- #

class TestConditionSaveEffects:
    def test_paralyzed_auto_fails_str_and_dex(self):
        assert check_save_auto_fail("strength", ["paralyzed"])
        assert check_save_auto_fail("dexterity", ["paralyzed"])
        assert not check_save_auto_fail("constitution", ["paralyzed"])
        assert not check_save_auto_fail("wisdom", ["paralyzed"])

    def test_petrified_auto_fails_str_and_dex(self):
        assert check_save_auto_fail("strength", ["petrified"])
        assert check_save_auto_fail("dexterity", ["petrified"])
        assert not check_save_auto_fail("constitution", ["petrified"])

    def test_unconscious_auto_fails_str_and_dex(self):
        assert check_save_auto_fail("strength", ["unconscious"])
        assert check_save_auto_fail("dexterity", ["unconscious"])
        assert not check_save_auto_fail("constitution", ["unconscious"])

    def test_other_conditions_no_auto_fail(self):
        for cond in ["blinded", "charmed", "deafened", "frightened",
                    "grappled", "incapacitated", "invisible", "poisoned",
                    "prone", "restrained", "stunned"]:
            assert not check_save_auto_fail("strength", [cond])
            assert not check_save_auto_fail("constitution", [cond])

    def test_restrained_disadvantage_on_dex(self):
        assert check_save_disadvantage("dexterity", ["restrained"])
        assert not check_save_disadvantage("strength", ["restrained"])
        assert not check_save_disadvantage("constitution", ["restrained"])

    def test_multiple_conditions(self):
        # Multiple conditions: if any imposes disadvantage, it applies
        assert check_save_disadvantage("dexterity", ["restrained", "poisoned"])
        # Multiple auto-fail conditions: still auto-fails
        assert check_save_auto_fail("strength", ["paralyzed", "unconscious"])


# --------------------------------------------------------------------------- #
# Save execution
# --------------------------------------------------------------------------- #

class TestSaveExecution:
    def test_basic_save_roll(self):
        char = make_character(strength=16, level=5)  # +3 mod, +3 prof = +6
        result = roll_saving_throw("strength", char, dc=15)
        assert result.ability == "strength"
        assert result.modifier == 6
        assert result.dc == 15
        assert not result.auto_failed
        assert isinstance(result.success, bool)
        assert result.total == result.roll.total

    def test_save_with_advantage(self):
        char = make_character(strength=14, level=3)
        result = roll_saving_throw("strength", char, dc=12, advantage=True)
        assert result.advantage
        assert not result.disadvantage
        assert len(result.roll.rolls) == 2  # Two dice for advantage

    def test_save_with_disadvantage(self):
        char = make_character(strength=14, level=3)
        result = roll_saving_throw("strength", char, dc=12, disadvantage=True)
        assert result.disadvantage
        assert not result.advantage
        assert len(result.roll.rolls) == 2

    def test_advantage_and_disadvantage_cancel(self):
        char = make_character(strength=14, level=3)
        result = roll_saving_throw("strength", char, dc=12,
                                  advantage=True, disadvantage=True)
        assert not result.advantage
        assert not result.disadvantage
        assert len(result.roll.rolls) == 1

    def test_paralyzed_auto_fail_str(self):
        char = make_character(strength=20, level=10)  # Even great stats auto-fail
        result = roll_saving_throw("strength", char, dc=5,
                                  conditions=["paralyzed"])
        assert result.auto_failed
        assert not result.success
        assert "auto-fail" in result.description

    def test_paralyzed_constitution_save_normal(self):
        char = make_character(constitution=16, level=5)
        result = roll_saving_throw("constitution", char, dc=12,
                                  conditions=["paralyzed"])
        assert not result.auto_failed
        # Constitution save is not affected by paralyzed

    def test_restrained_disadvantage_dex(self):
        char = make_character(dexterity=16, level=5)
        result = roll_saving_throw("dexterity", char, dc=12,
                                  conditions=["restrained"])
        assert result.disadvantage
        assert len(result.roll.rolls) == 2

    def test_invalid_ability_raises_error(self):
        char = make_character()
        with pytest.raises(ValueError, match="Invalid ability"):
            roll_saving_throw("luck", char, dc=10)

    def test_save_description(self):
        char = make_character(dexterity=14, level=3)
        result = roll_saving_throw("dexterity", char, dc=15)
        assert "Dexterity save" in result.description
        assert "DC 15" in result.description


# --------------------------------------------------------------------------- #
# Save DC calculation
# --------------------------------------------------------------------------- #

class TestSaveDCCalculation:
    def test_basic_dc_calculation(self):
        # DC = 8 + proficiency + ability_mod + bonus
        dc = calculate_save_dc(ability_score=18, proficiency_bonus=3, bonus=0)
        assert dc == 8 + 3 + 4  # +4 mod from 18

    def test_dc_with_bonus(self):
        dc = calculate_save_dc(ability_score=14, proficiency_bonus=2, bonus=1)
        assert dc == 8 + 2 + 2 + 1  # +2 mod from 14

    def test_negative_ability_modifier(self):
        dc = calculate_save_dc(ability_score=8, proficiency_bonus=2, bonus=0)
        assert dc == 8 + 2 - 1  # -1 mod from 8

    def test_character_dc_calculation(self):
        char = make_character(intelligence=18, level=5)  # +4 mod, +3 prof
        dc = calculate_character_save_dc(char, "intelligence", bonus=0)
        assert dc == 8 + 3 + 4  # 8 + prof + mod

    def test_character_dc_with_bonus(self):
        char = make_character(charisma=16, level=3)  # +3 mod, +2 prof
        dc = calculate_character_save_dc(char, "charisma", bonus=2)
        assert dc == 8 + 2 + 3 + 2

    def test_multiclass_dc_uses_total_level(self):
        char = make_multiclass_character({"fighter": 2, "wizard": 2},
                                        intelligence=18)
        # Total level 4 -> +2 prof
        dc = calculate_character_save_dc(char, "intelligence", bonus=0)
        assert dc == 8 + 2 + 4  # +4 mod from 18


# --------------------------------------------------------------------------- #
# Integration tests
# --------------------------------------------------------------------------- #

class TestSavingThrowIntegration:
    def test_full_save_flow_proficient(self):
        char = make_character(char_class="Cleric", level=3,
                             classes='{"cleric": 3}',
                             wisdom=18, charisma=14)
        # Cleric: Wis/Cha proficient
        # Wis 18 -> +4 mod, level 3 -> +2 prof = +6
        result = roll_saving_throw("wisdom", char, dc=15)
        assert result.modifier == 6
        # Test either success or failure (random roll)
        assert isinstance(result.success, bool)

    def test_full_save_flow_non_proficient(self):
        char = make_character(char_class="Cleric", level=3,
                             classes='{"cleric": 3}',
                             wisdom=14, constitution=12)
        # Cleric not proficient in Con
        # Con 12 -> +1 mod, not proficient = +1
        result = roll_saving_throw("constitution", char, dc=15)
        assert result.modifier == 1

    def test_high_level_character_save(self):
        char = make_character(level=17, strength=20,
                             classes='{"fighter": 17}')
        # Str 20 -> +5 mod, level 17 -> +6 prof = +11
        result = roll_saving_throw("strength", char, dc=20)
        assert result.modifier == 11

    def test_resilient_feat_integration(self):
        import json
        # Fighter gets Str/Con, add Resilient Wisdom
        # Resilient gives +1 to the stat, so we set Dex to 17 (16 + 1)
        char = make_character(
            char_class="Fighter", level=3,
            classes='{"fighter": 3}',
            strength=16, constitution=16, dexterity=17,  # 17 = 16 + 1 from Resilient
            feats=json.dumps([
                {"name": "Resilient (Dexterity)", "description": "+1 Dex, Dex save proficiency",
                 "effects": {"save_proficiency": "dexterity"}}
            ])
        )
        # Fighter: Str/Con proficient + Resilient: Dex
        prof = get_saving_throw_proficiencies(char)
        assert "dexterity" in prof

        # Dex save should include proficiency
        result = roll_saving_throw("dexterity", char, dc=15)
        # Dex 17 -> +3 mod, level 3 -> +2 prof = +5
        assert result.modifier == 5


class TestSavingThrowAPI:
    def test_get_proficiencies_endpoint(self, client, db_session):
        # Create a character
        response = client.post("/api/characters", json={
            "name": "Test Wizard",
            "race": "Human",
            "char_class": "Wizard",
            "level": 5,
            "background": "Sage",
            "strength": 10,
            "dexterity": 14,
            "constitution": 14,
            "intelligence": 18,
            "wisdom": 16,
            "charisma": 10,
        })
        assert response.status_code == 200
        char_id = response.json()["id"]

        response = client.get(f"/api/characters/{char_id}/saving-throws/proficiencies")
        assert response.status_code == 200
        data = response.json()
        assert data["character_id"] == char_id
        assert "intelligence" in data["proficiencies"]
        assert "wisdom" in data["proficiencies"]
        assert "strength" not in data["proficiencies"]

    def test_roll_save_endpoint(self, client, db_session):
        # Create a character
        response = client.post("/api/characters", json={
            "name": "Test Fighter",
            "race": "Human",
            "char_class": "Fighter",
            "level": 3,
            "background": "Soldier",
            "strength": 16,
            "dexterity": 14,
            "constitution": 14,
            "intelligence": 10,
            "wisdom": 12,
            "charisma": 10,
        })
        assert response.status_code == 200
        char_id = response.json()["id"]

        response = client.post(f"/api/characters/{char_id}/saving-throws/roll", json={
            "ability": "strength",
            "dc": 15,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ability"] == "strength"
        assert data["dc"] == 15
        assert "total" in data
        assert "success" in data
        assert isinstance(data["success"], bool)

    def test_roll_save_with_conditions(self, client, db_session):
        # Create a character
        response = client.post("/api/characters", json={
            "name": "Test Rogue",
            "race": "Elf",
            "char_class": "Rogue",
            "level": 3,
            "background": "Criminal",
            "strength": 14,
            "dexterity": 16,
            "constitution": 12,
            "intelligence": 12,
            "wisdom": 14,
            "charisma": 10,
        })
        assert response.status_code == 200
        char_id = response.json()["id"]

        # Paralyzed should auto-fail strength save
        response = client.post(f"/api/characters/{char_id}/saving-throws/roll", json={
            "ability": "strength",
            "dc": 5,
            "conditions": ["paralyzed"],
        })
        assert response.status_code == 200
        data = response.json()
        assert data["auto_failed"] is True
        assert data["success"] is False

    def test_calculate_dc_endpoint(self, client, db_session):
        # Create a character
        response = client.post("/api/characters", json={
            "name": "Test Wizard DC",
            "race": "High Elf",
            "char_class": "Wizard",
            "level": 5,
            "background": "Sage",
            "strength": 10,
            "dexterity": 14,
            "constitution": 14,
            "intelligence": 18,
            "wisdom": 16,
            "charisma": 10,
        })
        assert response.status_code == 200
        char_id = response.json()["id"]

        response = client.get(
            f"/api/characters/{char_id}/saving-throws/dc",
            params={"spellcasting_ability": "intelligence"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["spellcasting_ability"] == "intelligence"
        assert data["ability_score"] == 18
        assert data["ability_modifier"] == 4
        assert data["proficiency_bonus"] == 3
        # DC = 8 + 3 + 4 = 15
        assert data["dc"] == 15

    def test_invalid_ability_400_error(self, client, db_session):
        # Create a character
        response = client.post("/api/characters", json={
            "name": "Test Fighter Error",
            "race": "Human",
            "char_class": "Fighter",
            "level": 1,
            "background": "Soldier",
            "strength": 16,
            "dexterity": 14,
            "constitution": 14,
            "intelligence": 10,
            "wisdom": 12,
            "charisma": 10,
        })
        assert response.status_code == 200
        char_id = response.json()["id"]

        response = client.post(f"/api/characters/{char_id}/saving-throws/roll", json={
            "ability": "luck",
            "dc": 15,
        })
        assert response.status_code == 400
        assert "Invalid ability" in response.json()["detail"]

    def test_proficiencies_include_feat_sources(self, client, db_session):
        """The proficiencies response should surface feat-source attribution
        (ability → feat name) for save proficiencies granted by a feat."""
        import json
        # Create a fighter (Str/Con saves), then learn Resilient (Wisdom) by
        # writing the feat directly (the real persisted shape).
        response = client.post("/api/characters", json={
            "name": "Resilient Hero",
            "race": "Human",
            "char_class": "Fighter",
            "level": 4,
            "background": "Soldier",
            "strength": 16, "dexterity": 14, "constitution": 14,
            "intelligence": 10, "wisdom": 12, "charisma": 10,
        })
        assert response.status_code == 200
        char_id = response.json()["id"]

        from app.models.models import Character
        char = db_session.query(Character).filter(Character.id == char_id).first()
        char.feats = json.dumps([{
            "name": "Resilient",
            "effects_applied": {"saving_throw_proficiency": "wisdom"},
            "learned_at_level": 4,
        }])
        db_session.commit()

        response = client.get(f"/api/characters/{char_id}/saving-throws/proficiencies")
        assert response.status_code == 200
        data = response.json()
        # Fighter base (Str/Con) + Resilient (Wisdom)
        assert set(data["proficiencies"]) == {"strength", "constitution", "wisdom"}
        assert data["feat_sources"] == {"wisdom": "Resilient"}