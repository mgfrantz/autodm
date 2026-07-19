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
from app.engine.leveling import VALID_ABILITIES


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


def test_registry_has_at_least_67_feats():
    """The expanded registry should have 67+ feats (PHB + XGE + Tasha's)."""
    assert len(list_feats()) >= 67


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


# --------------------------------------------------------------------------- #
# Tasha's Cauldron of Everything feat tests                                    #
# --------------------------------------------------------------------------- #

_TASHAS_FEATS = [
    "Chef", "Crusher", "Eldritch Adept", "Fey Touched", "Fighting Initiate",
    "Gunner", "Metamagic Adept", "Piercer", "Poisoner", "Shadow Touched",
    "Skill Expert", "Slasher", "Telekinetic", "Telepathic",
]


def test_tashas_feats_exist():
    names = {f.name for f in list_feats()}
    for name in _TASHAS_FEATS:
        assert name in names, f"Missing Tasha's feat: {name}"


def test_tashas_count_is_fourteen():
    """Exactly 14 canonical Tasha's Cauldron of Everything feats registered."""
    tashas = [f for f in list_feats() if f.source == "Tasha's Cauldron of Everything"]
    assert len(tashas) == 14


def test_tashas_feats_have_tashas_source():
    for name in _TASHAS_FEATS:
        feat = get_feat(name)
        assert feat is not None, name
        assert feat.source == "Tasha's Cauldron of Everything", f"{name}: {feat.source}"


def test_tashas_feats_no_duplicates():
    """Each Tasha's feat resolves to a distinct registry entry."""
    seen = set()
    for name in _TASHAS_FEATS:
        feat = get_feat(name)
        assert feat is not None, name
        key = feat.name.lower()
        assert key not in seen, f"Duplicate: {name}"
        seen.add(key)


# --- Half-feat ability choices -------------------------------------------------

def test_tashas_half_feats_have_ability_choices():
    """Tasha's half-feats must expose ability_bonus_choices."""
    expected = {
        "Chef": {"constitution", "wisdom"},
        "Crusher": {"strength", "constitution"},
        "Fey Touched": {"intelligence", "wisdom", "charisma"},
        "Gunner": {"dexterity"},
        "Piercer": {"strength", "dexterity", "constitution"},
        "Shadow Touched": {"intelligence", "wisdom", "charisma"},
        "Skill Expert": {"strength", "dexterity", "constitution",
                          "intelligence", "wisdom", "charisma"},
        "Slasher": {"strength", "dexterity"},
        "Telekinetic": {"intelligence", "wisdom", "charisma"},
        "Telepathic": {"intelligence", "wisdom", "charisma"},
    }
    for name, choices in expected.items():
        feat = get_feat(name)
        assert feat is not None, name
        assert set(feat.ability_bonus_choices) == choices, (
            f"{name}: expected {choices}, got {set(feat.ability_bonus_choices)}"
        )


def test_tashas_non_half_feats_have_no_ability_choice():
    """Eldritch Adept, Fighting Initiate, Metamagic Adept, and Poisoner give no
    ability bump (per Tasha's)."""
    for name in ["Eldritch Adept", "Fighting Initiate", "Metamagic Adept", "Poisoner"]:
        feat = get_feat(name)
        assert feat is not None, name
        assert feat.ability_bonus_choices == [], f"{name} should have no ability choice"
        assert feat.ability_bonus == {}, f"{name} should have no fixed ability bonus"


# --- Per-feat mechanical-correctness ------------------------------------------

def test_chef_feat():
    chef = get_feat("Chef")
    assert chef is not None
    assert chef.combat_modifiers["temp_hp_treats"]["during_rest"] is True
    assert chef.combat_modifiers["short_rest_share_hit_die"] is True


def test_crusher_feat():
    crusher = get_feat("Crusher")
    assert crusher is not None
    assert crusher.combat_modifiers["bludgeoning_hit_push"]["feet"] == 5
    assert crusher.combat_modifiers["bludgeoning_hit_push"]["per_turn"] == 1
    assert crusher.combat_modifiers["crit_advantage_vs_target"]["damage_type"] == "bludgeoning"


def test_eldritch_adept_feat():
    ea = get_feat("Eldritch Adept")
    assert ea is not None
    assert ea.combat_modifiers["learn_eldritch_invocation"] == 1
    assert ea.combat_modifiers["change_on_level_up"] is True


def test_fey_touched_feat():
    ft = get_feat("Fey Touched")
    assert ft is not None
    assert ft.combat_modifiers["learn_spell_fixed"]["name"] == "Misty Step"
    assert ft.combat_modifiers["learn_spell_fixed"]["level"] == 2
    assert ft.combat_modifiers["learn_spell_fixed"]["casts_per_long_rest"] == 1
    assert "divination" in ft.combat_modifiers["learn_spell_choice"]["school"]
    assert "enchantment" in ft.combat_modifiers["learn_spell_choice"]["school"]
    assert ft.combat_modifiers["learn_spell_choice"]["level"] == 1


def test_fighting_initiate_feat():
    fi = get_feat("Fighting Initiate")
    assert fi is not None
    assert fi.combat_modifiers["learn_fighting_style"] == 1
    assert fi.combat_modifiers["style_choices"] == "fighter_list"
    assert fi.combat_modifiers["change_on_level_up"] is True


def test_gunner_feat():
    gunner = get_feat("Gunner")
    assert gunner is not None
    assert "firearms" in gunner.skill_proficiencies
    assert gunner.combat_modifiers["ignore_loading_property"]["weapons"] == "firearms"
    assert gunner.combat_modifiers["ranged_no_disadvantage_in_melee"]["weapons"] == "firearms"


def test_metamagic_adept_feat():
    ma = get_feat("Metamagic Adept")
    assert ma is not None
    assert ma.combat_modifiers["learn_metamagic"] == 2
    assert ma.combat_modifiers["sorcery_points"]["amount"] == 2
    assert ma.combat_modifiers["sorcery_points"]["refresh"] == "long_rest"
    assert ma.combat_modifiers["change_one_on_level_up"] is True


def test_piercer_feat():
    piercer = get_feat("Piercer")
    assert piercer is not None
    assert piercer.combat_modifiers["reroll_damage_die"]["per_turn"] == 1
    assert piercer.combat_modifiers["reroll_damage_die"]["damage_type"] == "piercing"
    assert piercer.combat_modifiers["reroll_damage_die"]["use_higher"] is True
    assert piercer.combat_modifiers["crit_extra_damage_die"]["damage_type"] == "piercing"


def test_poisoner_feat():
    poisoner = get_feat("Poisoner")
    assert poisoner is not None
    assert poisoner.combat_modifiers["apply_poison_bonus_action"] is True
    assert poisoner.combat_modifiers["bonus_poison_damage"]["dice"] == "2d8"
    assert poisoner.combat_modifiers["bonus_poison_damage"]["damage_type"] == "poison"
    assert poisoner.combat_modifiers["bonus_poison_damage"]["per_turn"] == 1
    assert poisoner.combat_modifiers["poison_save_dc"] == "8 + prof + int_mod"


def test_shadow_touched_feat():
    st = get_feat("Shadow Touched")
    assert st is not None
    assert st.combat_modifiers["learn_spell_fixed"]["name"] == "Invisibility"
    assert st.combat_modifiers["learn_spell_fixed"]["level"] == 2
    assert "illusion" in st.combat_modifiers["learn_spell_choice"]["school"]
    assert "necromancy" in st.combat_modifiers["learn_spell_choice"]["school"]


def test_skill_expert_feat():
    se = get_feat("Skill Expert")
    assert se is not None
    assert se.combat_modifiers["expertise"]["count"] == 1
    assert se.combat_modifiers["expertise"]["double_proficiency"] is True
    assert any("skill" in p for p in se.skill_proficiencies)


def test_slasher_feat():
    slasher = get_feat("Slasher")
    assert slasher is not None
    assert slasher.combat_modifiers["slashing_hit_speed_reduction"]["feet"] == 10
    assert slasher.combat_modifiers["slashing_hit_speed_reduction"]["per_turn"] == 1
    assert slasher.combat_modifiers["slashing_hit_speed_reduction"]["damage_type"] == "slashing"
    assert slasher.combat_modifiers["crit_target_disadvantage"]["damage_type"] == "slashing"


def test_telekinetic_feat():
    tk = get_feat("Telekinetic")
    assert tk is not None
    assert tk.combat_modifiers["learn_cantrip_fixed"]["name"] == "Mage Hand"
    assert tk.combat_modifiers["learn_cantrip_fixed"]["no_verbal"] is True
    assert tk.combat_modifiers["learn_cantrip_fixed"]["no_somatic"] is True
    assert tk.combat_modifiers["telekinetic_shove"]["range_ft"] == 30
    assert tk.combat_modifiers["telekinetic_shove"]["save"] == "strength"
    assert tk.combat_modifiers["telekinetic_shove"]["push_pull_ft"] == 5


def test_telepathic_feat():
    tp = get_feat("Telepathic")
    assert tp is not None
    assert tp.combat_modifiers["telepathy"]["range_ft"] == 60
    assert tp.combat_modifiers["telepathy"]["shared_language_only"] is True
    assert tp.combat_modifiers["cast_detect_thoughts"]["level"] == 2
    assert tp.combat_modifiers["cast_detect_thoughts"]["action"] == "bonus"
    assert tp.combat_modifiers["cast_detect_thoughts"]["uses"] == "proficiency_bonus"
    assert tp.combat_modifiers["cast_detect_thoughts"]["refresh"] == "long_rest"


# --- Prerequisites -----------------------------------------------------------

def test_eldritch_adept_requires_caster():
    ea = get_feat("Eldritch Adept")
    assert ea.prerequisite is not None
    assert ea.prerequisite.requires_caster is True
    # Wizard passes
    assert check_prerequisites(
        ea, {"intelligence": 12}, 4, {"wizard": 4}
    ).met is True
    # Fighter fails
    result = check_prerequisites(ea, {"strength": 14}, 4, {"fighter": 4})
    assert result.met is False
    assert "spellcasting" in result.message.lower()


def test_metamagic_adept_requires_sorcerer():
    ma = get_feat("Metamagic Adept")
    assert ma.prerequisite is not None
    assert ma.prerequisite.requires_class == "sorcerer"
    # Sorcerer passes
    assert check_prerequisites(
        ma, {"charisma": 14}, 4, {"sorcerer": 4}
    ).met is True
    # Wizard fails (caster, but not sorcerer)
    result = check_prerequisites(ma, {"intelligence": 14}, 4, {"wizard": 4})
    assert result.met is False
    assert "sorcerer" in result.message.lower()


def test_tashas_no_prerequisite_feats_are_ungated():
    """Feats with no prerequisite should be available to a level-1 character."""
    ungated = [
        "Chef", "Crusher", "Fey Touched", "Fighting Initiate", "Gunner",
        "Piercer", "Poisoner", "Shadow Touched", "Skill Expert",
        "Slasher", "Telekinetic", "Telepathic",
    ]
    for name in ungated:
        feat = get_feat(name)
        assert feat is not None, name
        result = check_prerequisites(
            feat,
            ability_scores={a: 10 for a in VALID_ABILITIES},
            level=1,
            classes={"fighter": 1},
        )
        assert result.met is True, f"{name}: {result.message}"


def test_tashas_feats_in_available_list():
    """Ungated Tasha's feats should surface in list_available_feats."""
    available = list_available_feats(
        ability_scores={a: 10 for a in VALID_ABILITIES},
        level=4,
        classes={"fighter": 4},
    )
    names = {f.name for f in available}
    # These ungated feats should all appear for a fighter
    for name in ["Chef", "Crusher", "Fey Touched", "Fighting Initiate",
                 "Gunner", "Piercer", "Poisoner", "Shadow Touched",
                 "Skill Expert", "Slasher", "Telekinetic", "Telepathic"]:
        assert name in names, f"{name} should be available to a fighter"
    # Metamagic Adept requires sorcerer — should NOT appear for a fighter
    assert "Metamagic Adept" not in names
    # Eldritch Adept requires a caster — should NOT appear for a fighter
    assert "Eldritch Adept" not in names


def test_metamagic_adept_available_to_sorcerer():
    available = list_available_feats(
        ability_scores={"charisma": 14, "dexterity": 12},
        level=4,
        classes={"sorcerer": 4},
    )
    names = {f.name for f in available}
    assert "Metamagic Adept" in names
    assert "Eldritch Adept" in names  # sorcerer is a caster


# --- to_dict serialization ----------------------------------------------------

def test_tashas_feats_to_dict_shape():
    for name in _TASHAS_FEATS:
        feat = get_feat(name)
        assert feat is not None, name
        d = feat.to_dict()
        assert d["name"] == name
        assert d["source"] == "Tasha's Cauldron of Everything"
        assert "description" in d
        assert "combat_modifiers" in d
        # prerequisite must serialize (None or dict)
        assert d["prerequisite"] is None or isinstance(d["prerequisite"], dict)


def test_tashas_feats_have_notes():
    """Every Tasha's feat documents its effects in plain-language notes."""
    for name in _TASHAS_FEATS:
        feat = get_feat(name)
        assert feat is not None, name
        assert len(feat.notes) >= 1, f"{name} has no notes"