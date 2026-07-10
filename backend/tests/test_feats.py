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


# --------------------------------------------------------------------------- #
# Expanded PHB general-feat registry tests                                     #
# --------------------------------------------------------------------------- #

# Feats added in the feat-expansion pass (build priority #14).
_EXPANDED_PHB_FEATS = [
    "Actor", "Charger", "Durable", "Elemental Adept", "Grappler",
    "Inspiring Leader", "Lightly Armored", "Linguist", "Magic Initiate",
    "Martial Adept", "Medium Armor Master", "Mounted Combatant",
    "Savage Attacker", "Shield Master", "Skulker", "Weapon Master",
]


def test_expanded_phb_feats_exist():
    names = {f.name for f in list_feats()}
    for name in _EXPANDED_PHB_FEATS:
        assert name in names, f"Missing expanded PHB feat: {name}"


def test_registry_has_at_least_50_feats():
    """The expanded registry should have 50+ feats (was 23)."""
    assert len(list_feats()) >= 50


def test_actor_feat():
    actor = get_feat("Actor")
    assert actor is not None
    assert actor.ability_bonus_choices == ["charisma"]
    assert "deception" in actor.combat_modifiers["skill_advantage"]
    assert "performance" in actor.combat_modifiers["skill_advantage"]


def test_charger_feat():
    charger = get_feat("Charger")
    assert charger is not None
    assert charger.combat_modifiers["dash_bonus_action_attack"] is True
    assert charger.combat_modifiers["straight_line_bonus"]["damage_bonus"] == 5


def test_durable_feat():
    durable = get_feat("Durable")
    assert durable is not None
    assert durable.ability_bonus_choices == ["constitution"]
    assert durable.combat_modifiers["hit_die_minimum"] == "twice_con_mod_minimum_2"


def test_elemental_adept_requires_caster():
    ea = get_feat("Elemental Adept")
    assert ea is not None
    assert ea.prerequisite is not None
    assert ea.prerequisite.requires_caster is True
    elements = ea.combat_modifiers["element_choices"]
    assert set(elements) == {"acid", "cold", "fire", "lightning", "poison", "thunder"}

    # Non-caster fails
    result = check_prerequisites(ea, {"intelligence": 14}, 4, {"fighter": 4})
    assert result.met is False
    assert "spellcasting" in result.message.lower()

    # Caster passes
    result = check_prerequisites(ea, {"intelligence": 14}, 4, {"wizard": 4})
    assert result.met is True


def test_grappler_requires_strength_13():
    grappler = get_feat("Grappler")
    assert grappler is not None
    assert grappler.prerequisite is not None
    assert grappler.prerequisite.min_abilities == {"strength": 13}

    # Too weak
    result = check_prerequisites(grappler, {"strength": 12}, 4, {"fighter": 4})
    assert result.met is False
    assert "strength 13+" in result.message

    # Strong enough
    result = check_prerequisites(grappler, {"strength": 13}, 4, {"fighter": 4})
    assert result.met is True


def test_inspiring_leader_requires_cha_13():
    il = get_feat("Inspiring Leader")
    assert il is not None
    assert il.prerequisite.min_abilities == {"charisma": 13}
    assert il.combat_modifiers["temp_hp_ritual"]["targets"] == 6


def test_lightly_armored_grants_armor_prof():
    la = get_feat("Lightly Armored")
    assert la is not None
    assert "light armor" in la.skill_proficiencies
    assert "shields" in la.skill_proficiencies
    assert set(la.ability_bonus_choices) == {"strength", "dexterity"}


def test_linguist_grants_languages():
    ling = get_feat("Linguist")
    assert ling is not None
    assert ling.ability_bonus_choices == ["intelligence"]
    assert any("languages" in p for p in ling.skill_proficiencies)


def test_magic_initiate_choices():
    mi = get_feat("Magic Initiate")
    assert mi is not None
    assert mi.combat_modifiers["learn_cantrips"] == 2
    assert mi.combat_modifiers["learn_spell"]["level"] == 1
    classes = mi.combat_modifiers["spell_class_choices"]
    assert "wizard" in classes and "cleric" in classes


def test_martial_adept_superiority_die():
    ma = get_feat("Martial Adept")
    assert ma is not None
    assert ma.combat_modifiers["maneuvers_learned"] == 2
    die = ma.combat_modifiers["superiority_dice"]
    assert die["count"] == 1 and die["sides"] == 6


def test_medium_armor_master_requires_medium():
    mam = get_feat("Medium Armor Master")
    assert mam is not None
    assert mam.prerequisite.requires_armor_proficiency == "medium"
    assert mam.combat_modifiers["medium_armor_max_dex"] == 3

    # Rogue (light only) fails
    result = check_prerequisites(mam, {"dexterity": 16}, 4, {"rogue": 4})
    assert result.met is False
    assert "medium armor" in result.message.lower()

    # Fighter (has medium) passes
    result = check_prerequisites(mam, {"dexterity": 16}, 4, {"fighter": 4})
    assert result.met is True


def test_mounted_combatant_modifiers():
    mc = get_feat("Mounted Combatant")
    assert mc is not None
    assert mc.combat_modifiers["advantage_vs_unmounted_smaller"] is True
    assert mc.combat_modifiers["mount_evasion"] is True


def test_savage_attacker_reroll():
    sa = get_feat("Savage Attacker")
    assert sa is not None
    assert sa.combat_modifiers["reroll_weapon_damage"]["per_turn"] == 1
    assert sa.combat_modifiers["reroll_weapon_damage"]["use_higher"] is True


def test_shield_master_modifiers():
    sm = get_feat("Shield Master")
    assert sm is not None
    assert sm.combat_modifiers["bonus_action_shield_shove"] is True
    assert sm.combat_modifiers["reaction_shield_ac_to_dex_save"] is True


def test_skulker_modifiers():
    sk = get_feat("Skulker")
    assert sk is not None
    assert sk.combat_modifiers["hide_when_lightly_obscured"] is True
    assert sk.combat_modifiers["miss_doesnt_reveal_position"] is True


def test_weapon_master_proficiencies():
    wm = get_feat("Weapon Master")
    assert wm is not None
    assert any("weapons" in p for p in wm.skill_proficiencies)
    assert set(wm.ability_bonus_choices) == {"strength", "dexterity"}


def test_expanded_phb_feats_have_source():
    """All expanded PHB feats should reference the Player's Handbook."""
    for name in _EXPANDED_PHB_FEATS:
        feat = get_feat(name)
        assert feat is not None, name
        assert feat.source == "Player's Handbook", f"{name} source: {feat.source}"


# --------------------------------------------------------------------------- #
# XGE race-specific feat tests                                                 #
# --------------------------------------------------------------------------- #

_XGE_RACE_FEATS = [
    "Bountiful Luck", "Dragon Fear", "Dragon Hide", "Dwarven Fortitude",
    "Elven Accuracy", "Fade Away", "Fey Teleportation", "Flames of Phlegethos",
    "Infernal Constitution", "Orcish Fury", "Prodigy", "Second Chance",
    "Squat Nimbleness", "Wood Elf Magic",
]


def test_xge_race_feats_exist():
    names = {f.name for f in list_feats()}
    for name in _XGE_RACE_FEATS:
        assert name in names, f"Missing XGE race feat: {name}"


def test_xge_race_feats_have_xge_source():
    for name in _XGE_RACE_FEATS:
        feat = get_feat(name)
        assert feat is not None, name
        assert feat.source == "Xanathar's Guide to Everything", f"{name}: {feat.source}"


def test_xge_race_feats_require_race():
    """Every XGE race feat must set requires_race."""
    for name in _XGE_RACE_FEATS:
        feat = get_feat(name)
        assert feat is not None, name
        assert feat.prerequisite is not None, f"{name} has no prerequisite"
        assert feat.prerequisite.requires_race, f"{name} has no requires_race"


def test_dwarven_fortitude_race_gate():
    df = get_feat("Dwarven Fortitude")
    assert df is not None
    # Dwarf passes
    assert check_prerequisites(df, {"constitution": 12}, 4, {"fighter": 4}, race="Dwarf").met is True
    assert check_prerequisites(df, {"constitution": 12}, 4, {"fighter": 4}, race="Mountain Dwarf").met is True
    # Human fails
    result = check_prerequisites(df, {"constitution": 12}, 4, {"fighter": 4}, race="Human")
    assert result.met is False
    assert "dwarf" in result.message.lower()


def test_elven_accuracy_race_gate():
    ea = get_feat("Elven Accuracy")
    assert ea is not None
    # Elf and half-elf both pass
    assert check_prerequisites(ea, {"dexterity": 14}, 4, {"wizard": 4}, race="Elf").met is True
    assert check_prerequisites(ea, {"dexterity": 14}, 4, {"wizard": 4}, race="High Elf").met is True
    assert check_prerequisites(ea, {"dexterity": 14}, 4, {"wizard": 4}, race="Half-Elf").met is True
    # Human fails
    result = check_prerequisites(ea, {"dexterity": 14}, 4, {"wizard": 4}, race="Human")
    assert result.met is False
    assert "elf" in result.message.lower() or "half-elf" in result.message.lower()


def test_wood_elf_magic_specific_race():
    wem = get_feat("Wood Elf Magic")
    assert wem is not None
    # Wood elf passes
    assert check_prerequisites(wem, {}, 4, {"ranger": 4}, race="Wood Elf").met is True
    # High elf fails (not a wood elf)
    result = check_prerequisites(wem, {}, 4, {"ranger": 4}, race="High Elf")
    assert result.met is False
    assert "wood elf" in result.message.lower()


def test_prodigy_multi_race_gate():
    p = get_feat("Prodigy")
    assert p is not None
    # Human, half-elf, half-orc all pass
    assert check_prerequisites(p, {"charisma": 12}, 4, {"rogue": 4}, race="Human").met is True
    assert check_prerequisites(p, {"charisma": 12}, 4, {"rogue": 4}, race="Half-Elf").met is True
    assert check_prerequisites(p, {"charisma": 12}, 4, {"rogue": 4}, race="Half-Orc").met is True
    # Dwarf fails
    result = check_prerequisites(p, {"charisma": 12}, 4, {"rogue": 4}, race="Dwarf")
    assert result.met is False


def test_race_prereq_missing_race_param():
    """When race is None/omitted, race-gated feats should fail."""
    df = get_feat("Dwarven Fortitude")
    result = check_prerequisites(df, {"constitution": 12}, 4, {"fighter": 4}, race=None)
    assert result.met is False
    assert "race" in result.message.lower()


def test_matches_race_helper():
    from app.engine.feats import _matches_race
    assert _matches_race("Dwarf", ["dwarf"]) is True
    assert _matches_race("Mountain Dwarf", ["dwarf"]) is True
    assert _matches_race("Human", ["dwarf"]) is False
    assert _matches_race("High Elf", ["elf", "half-elf"]) is True
    assert _matches_race("Half-Elf", ["elf", "half-elf"]) is True
    assert _matches_race("Wood Elf", ["wood elf"]) is True
    assert _matches_race("High Elf", ["wood elf"]) is False
    assert _matches_race(None, ["dwarf"]) is False
    assert _matches_race("", ["dwarf"]) is False


def test_list_available_feats_race_filtering():
    """Race-specific feats should only appear for matching races."""
    # Dwarf fighter should see Dwarven Fortitude but not Elven Accuracy
    dwarf_available = list_available_feats(
        ability_scores={"strength": 14, "constitution": 14, "dexterity": 12},
        level=4,
        classes={"fighter": 4},
        race="Dwarf",
    )
    dwarf_names = {f.name for f in dwarf_available}
    assert "Dwarven Fortitude" in dwarf_names
    assert "Squat Nimbleness" in dwarf_names
    assert "Elven Accuracy" not in dwarf_names
    assert "Fade Away" not in dwarf_names

    # Elf wizard should see Elven Accuracy but not Dwarven Fortitude
    elf_available = list_available_feats(
        ability_scores={"intelligence": 14, "dexterity": 14},
        level=4,
        classes={"wizard": 4},
        race="High Elf",
    )
    elf_names = {f.name for f in elf_available}
    assert "Elven Accuracy" in elf_names
    assert "Fey Teleportation" in elf_names
    assert "Dwarven Fortitude" not in elf_names


def test_list_available_feats_no_race_hides_race_feats():
    """Without a race, race-gated feats should not appear."""
    available = list_available_feats(
        ability_scores={"strength": 14, "dexterity": 14, "constitution": 14},
        level=4,
        classes={"fighter": 4},
        race=None,
    )
    names = {f.name for f in available}
    assert "Dwarven Fortitude" not in names
    assert "Elven Accuracy" not in names
    # But non-race feats should still appear
    assert "Alert" in names
    assert "Tough" in names


def test_prerequisite_to_dict_includes_race():
    df = get_feat("Dwarven Fortitude")
    assert df is not None
    d = df.to_dict()
    assert d["prerequisite"] is not None
    assert d["prerequisite"]["requires_race"] == ["dwarf"]

    alert = get_feat("Alert")
    d2 = alert.to_dict()
    assert d2["prerequisite"] is None