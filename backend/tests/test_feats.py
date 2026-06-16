"""
Tests for the feat engine.
"""
import pytest
from app.engine.feats import (
    Feat,
    FeatPrerequisite,
    get_feat,
    list_feats,
    list_available_feats,
    check_prerequisites,
    apply_feat,
    CASTING_CLASSES,
    _has_armor_proficiency,
    ApplyFeatResult,
)


# --------------------------------------------------------------------------- #
# Registry tests                                                              #
# --------------------------------------------------------------------------- #

def test_list_feats_returns_all():
    feats = list_feats()
    assert len(feats) >= 20
    names = [f.name for f in feats]
    assert "Alert" in names
    assert "Sharpshooter" in names
    assert "Tough" in names
    assert "Resilient" in names


def test_get_feat_by_name_case_insensitive():
    alert = get_feat("ALERT")
    assert alert is not None
    assert alert.name == "Alert"
    assert alert.initiative_bonus == 5

    alert2 = get_feat("alert")
    assert alert2 is not None
    assert alert2.name == "Alert"

    unknown = get_feat("NonExistentFeat")
    assert unknown is None


def test_feat_half_feats_have_choice():
    resilient = get_feat("Resilient")
    assert resilient is not None
    assert len(resilient.ability_bonus_choices) == 6  # All six abilities

    athlete = get_feat("Athlete")
    assert athlete is not None
    assert set(athlete.ability_bonus_choices) == {"strength", "dexterity"}


def test_tough_has_hp_per_level():
    tough = get_feat("Tough")
    assert tough is not None
    assert tough.hp_per_level == 2
    assert tough.ability_bonus_choices == []
    assert tough.ability_bonus == {}


def test_alert_has_initiative_bonus():
    alert = get_feat("Alert")
    assert alert is not None
    assert alert.initiative_bonus == 5
    assert alert.speed_bonus == 0
    assert "cannot be surprised" in alert.notes[0]


def test_combat_feats_have_modifiers():
    gwm = get_feat("Great Weapon Master")
    assert gwm is not None
    assert "power_attack" in gwm.combat_modifiers
    assert gwm.combat_modifiers["power_attack"]["attack_penalty"] == -5
    assert gwm.combat_modifiers["power_attack"]["damage_bonus"] == 10

    sharpshooter = get_feat("Sharpshooter")
    assert sharpshooter is not None
    assert sharpshooter.combat_modifiers["no_long_range_disadvantage"] is True


# --------------------------------------------------------------------------- #
# Prerequisite tests                                                          #
# --------------------------------------------------------------------------- #

def test_no_prerequisites_met():
    alert = get_feat("Alert")
    assert alert is not None
    result = check_prerequisites(
        alert,
        ability_scores={"strength": 10, "dexterity": 10},
        level=1,
        classes={"fighter": 1},
    )
    assert result.met is True


def test_caster_prerequisite_fails_for_non_caster():
    war_caster = get_feat("War Caster")
    assert war_caster is not None
    result = check_prerequisites(
        war_caster,
        ability_scores={"strength": 14, "dexterity": 14},
        level=4,
        classes={"fighter": 4},  # Fighter is not a caster
    )
    assert result.met is False
    assert "spellcasting" in result.message.lower()


def test_caster_prerequisite_passes_for_caster():
    war_caster = get_feat("War Caster")
    assert war_caster is not None
    result = check_prerequisites(
        war_caster,
        ability_scores={"intelligence": 12},
        level=1,
        classes={"wizard": 1},
    )
    assert result.met is True


def test_armor_prerequisite_fails():
    # Heavy Armor Master requires heavy armor proficiency
    ham = get_feat("Heavy Armor Master")
    assert ham is not None
    result = check_prerequisites(
        ham,
        ability_scores={"strength": 14},
        level=4,
        classes={"rogue": 4},  # Rogue has light armor only
    )
    assert result.met is False
    assert "heavy armor" in result.message.lower()


def test_armor_prerequisite_passes():
    ham = get_feat("Heavy Armor Master")
    assert ham is not None
    result = check_prerequisites(
        ham,
        ability_scores={"strength": 14},
        level=1,
        classes={"fighter": 1},  # Fighter has heavy armor
    )
    assert result.met is True


def test_min_level_prerequisite():
    # Some feats have implicit level checks (class features)
    defensive_duelist = get_feat("Defensive Duelist")
    assert defensive_duelist is not None
    result = check_prerequisites(
        defensive_duelist,
        ability_scores={"dexterity": 14},
        level=1,
        classes={"rogue": 1},
    )
    assert result.met is True  # No level requirement

    # If a feat had a min_level > 1
    custom_prereq = FeatPrerequisite(min_level=4)
    result = check_prerequisites(
        Feat("Test", "test", prerequisite=custom_prereq),
        ability_scores={},
        level=2,
        classes={},
    )
    assert result.met is False
    assert "level 4+" in result.message


# --------------------------------------------------------------------------- #
# Apply feat tests                                                            #
# --------------------------------------------------------------------------- #

def test_apply_feat_tough():
    tough = get_feat("Tough")
    assert tough is not None
    result = apply_feat(
        tough,
        abilities={},
        level=5,
        max_hp=30,
        current_hp=20,
    )

    assert result.success is True
    assert result.max_hp_change == 10  # 2 HP per level × 5 levels
    assert result.current_hp_change == 10
    assert result.ability_changes == {}


def test_apply_feat_alert():
    alert = get_feat("Alert")
    assert alert is not None
    result = apply_feat(
        alert,
        abilities={},
        level=3,
        max_hp=20,
        current_hp=15,
    )

    assert result.success is True
    assert result.ability_changes == {}
    assert result.max_hp_change == 0
    assert result.effects_applied["initiative_bonus"] == 5


def test_apply_feat_athlete_choice_required():
    athlete = get_feat("Athlete")
    assert athlete is not None
    result = apply_feat(
        athlete,
        abilities={"strength": 12, "dexterity": 12},
        level=4,
        max_hp=20,
        current_hp=20,
        chosen_ability=None,  # Not provided
    )

    assert result.success is False
    assert "requires choosing an ability" in result.message.lower()


def test_apply_feat_athlete_with_choice():
    athlete = get_feat("Athlete")
    assert athlete is not None
    result = apply_feat(
        athlete,
        abilities={"strength": 12, "dexterity": 12},
        level=4,
        max_hp=20,
        current_hp=20,
        chosen_ability="strength",
    )

    assert result.success is True
    assert result.ability_changes == {"strength": 1}


def test_apply_feat_resilient_with_choice():
    resilient = get_feat("Resilient")
    assert resilient is not None
    result = apply_feat(
        resilient,
        abilities={"constitution": 14, "dexterity": 12, "wisdom": 13},
        level=4,
        max_hp=25,
        current_hp=20,
        chosen_ability="constitution",
    )

    assert result.success is True
    assert result.ability_changes == {"constitution": 1}
    assert result.saving_throw_proficiency == "constitution"


def test_apply_feat_invalid_choice():
    athlete = get_feat("Athlete")
    assert athlete is not None
    result = apply_feat(
        athlete,
        abilities={"strength": 12, "dexterity": 12},
        level=4,
        max_hp=20,
        current_hp=20,
        chosen_ability="intelligence",  # Not a valid choice
    )

    assert result.success is False
    assert "not a valid choice" in result.message.lower()


def test_apply_feat_cap_at_20():
    # Create a custom feat that tries to go over the cap
    custom = Feat(
        "Test Feat",
        "Test",
        ability_bonus={"strength": 5},  # Too much
    )
    result = apply_feat(
        custom,
        abilities={"strength": 18},
        level=10,
        max_hp=50,
        current_hp=40,
    )

    # The feat succeeds but clamps the ability to 20 (change is +2, not +5)
    assert result.success is True
    assert result.ability_changes == {"strength": 2}  # 18 -> 20 (clamped)


def test_apply_feat_clamps_at_20():
    # A feat that would go over, but clamps
    abilities = {"strength": 19, "constitution": 20}
    result = apply_feat(
        Feat("Test", "Test", ability_bonus_choices=["strength"]),
        abilities=abilities,
        level=10,
        max_hp=50,
        current_hp=40,
        chosen_ability="strength",
    )

    assert result.success is True
    # Strength should go from 19 to 20 (clamped)
    assert result.ability_changes == {"strength": 1}


# --------------------------------------------------------------------------- #
# List available feats tests                                                 #
# --------------------------------------------------------------------------- #

def test_list_available_feats_filters_by_prereqs():
    available = list_available_feats(
        ability_scores={"strength": 10, "dexterity": 10, "wisdom": 10, "charisma": 10},
        level=1,
        classes={"fighter": 1},
        known_feats=None,
    )

    # Alert should be available (no prereqs)
    alert_names = [f.name for f in available]
    assert "Alert" in alert_names

    # War Caster should NOT be available (not a caster)
    assert "War Caster" not in alert_names


def test_list_available_feats_excludes_known():
    available = list_available_feats(
        ability_scores={"strength": 10, "dexterity": 10},
        level=4,
        classes={"fighter": 4},
        known_feats=["alert", "tough"],
    )

    alert_names = [f.name.lower() for f in available]
    assert "alert" not in alert_names
    assert "tough" not in alert_names
    assert "sharpshooter" in alert_names  # Still available


def test_list_available_feats_for_caster():
    available = list_available_feats(
        ability_scores={"intelligence": 14},
        level=4,
        classes={"wizard": 4},
        known_feats=None,
    )

    names = [f.name for f in available]
    assert "War Caster" in names
    assert "Spell Sniper" in names


# --------------------------------------------------------------------------- #
# Helper function tests                                                      #
# --------------------------------------------------------------------------- #

def test_has_armor_proficiency():
    # Fighter has heavy armor
    assert _has_armor_proficiency({"fighter": 1}, "heavy") is True
    assert _has_armor_proficiency({"fighter": 1}, "medium") is True
    assert _has_armor_proficiency({"fighter": 1}, "light") is True

    # Rogue has light armor only
    assert _has_armor_proficiency({"rogue": 1}, "light") is True
    assert _has_armor_proficiency({"rogue": 1}, "medium") is False
    assert _has_armor_proficiency({"rogue": 1}, "heavy") is False

    # Monk has light armor
    assert _has_armor_proficiency({"monk": 1}, "light") is True
    assert _has_armor_proficiency({"monk": 1}, "medium") is False

    # Multiclass: Fighter/Rogue has heavy
    assert _has_armor_proficiency({"fighter": 2, "rogue": 1}, "heavy") is True


def test_casting_classes_set():
    assert "wizard" in CASTING_CLASSES
    assert "sorcerer" in CASTING_CLASSES
    assert "cleric" in CASTING_CLASSES
    assert "druid" in CASTING_CLASSES
    assert "bard" in CASTING_CLASSES
    assert "warlock" in CASTING_CLASSES
    assert "paladin" in CASTING_CLASSES
    assert "ranger" in CASTING_CLASSES

    # Fighter and Rogue are NOT casters
    assert "fighter" not in CASTING_CLASSES
    assert "rogue" not in CASTING_CLASSES


# --------------------------------------------------------------------------- #
# Feat.to_dict() tests                                                       #
# --------------------------------------------------------------------------- #

def test_feat_to_dict():
    alert = get_feat("Alert")
    assert alert is not None
    d = alert.to_dict()

    assert d["name"] == "Alert"
    assert d["initiative_bonus"] == 5
    assert d["ability_bonus"] == {}
    assert d["ability_bonus_choices"] == []
    assert d["prerequisite"] is None

    resilient = get_feat("Resilient")
    assert resilient is not None
    d2 = resilient.to_dict()
    assert len(d2["ability_bonus_choices"]) == 6
    assert d2["source"] == "Player's Handbook"