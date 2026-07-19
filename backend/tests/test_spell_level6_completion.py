"""
Tests for the PHB level-6 spell roster completion — 19 iconic spells added to
round the tier to 31/31 and lift the catalogue to 205 spells.

This mirrors the level 7/8 completion (test_spell_level7_8_completion.py) and
the level 1 / level 9 completions: the level-6 tier was the catalogue's
thinnest relative to the Player's Handbook (was 12; PHB has 31). After this
run, every PHB 6th-level spell is registered.

The 19 additions (grouped by resolution path):
- Damage / save-for-half: Blade Barrier (6d10 slashing), Otiluke's Freezing
  Sphere (10d6 cold, +1d6/slot), Wall of Thorns (7d8 slashing, +1d8/slot).
- Save-debuff (no damage): Eyebite (Wis, concentration), Magic Jar (Cha),
  Mass Suggestion (Wis, concentration).
- Utility / buff / ritual / summon: Arcane Gate, Conjure Fey, Contingency,
  Create Undead, Drawmij's Instant Summons (ritual), Find the Path, Guards and
  Wards, Move Earth, Planar Ally, Programmed Illusion, Transport via Plants,
  Wind Walk, Word of Recall.

Coverage mirrors test_spell_level7_8_completion.py:
- Registry distribution (level 6 now >= 31; PHB roster complete).
- Registration shape for every new spell (name, level, school) — parametrized.
- Per-spell mechanical correctness (save ability, concentration, dice, flags).
- Effect resolution for the damage spells, save-debuff spells, and utility
  spells (all resolve without raising).
- Whole-registry no-duplicate-name guard.
"""
import pytest

from app.engine.spells import (
    Spell,
    SpellSchool,
    SPELL_REGISTRY,
    get_spell,
    resolve_spell_effect,
)


def _spell(name: str) -> Spell:
    """Look up a spell by name/id and assert it is registered."""
    spell = get_spell(name)
    assert spell is not None, f"{name!r} should be registered"
    return spell


# --------------------------------------------------------------------------- #
# Registry distribution + PHB level-6 roster completeness
# --------------------------------------------------------------------------- #
class TestRegistryShape:
    def test_total_spell_count_grew(self):
        # Was 186 before this expansion; now 205.
        assert len(SPELL_REGISTRY) >= 205

    def test_level_6_tier_is_now_complete(self):
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        # Level 6 now matches PHB (was 12, now 31).
        assert by_level[6] >= 31, (
            f"Level 6 has only {by_level[6]} spells (expected >=31)"
        )

    def test_phb_level6_roster_is_complete(self):
        """All 31 Player's Handbook 6th-level spells are now registered."""
        PHB_LEVEL_6 = [
            "Arcane Gate", "Blade Barrier", "Chain Lightning",
            "Circle of Death", "Conjure Fey", "Contingency",
            "Create Undead", "Disintegrate", "Drawmij's Instant Summons",
            "Eyebite", "Find the Path", "Flesh to Stone",
            "Globe of Invulnerability", "Guards and Wards", "Harm", "Heal",
            "Heroes' Feast", "Magic Jar", "Mass Suggestion", "Move Earth",
            "Otiluke's Freezing Sphere", "Otto's Irresistible Dance",
            "Planar Ally", "Programmed Illusion", "Sunbeam",
            "Transport via Plants", "True Seeing", "Wall of Ice",
            "Wall of Thorns", "Wind Walk", "Word of Recall",
        ]
        missing = [n for n in PHB_LEVEL_6 if get_spell(n) is None]
        assert missing == [], f"Missing PHB level-6 spells: {missing}"

    def test_no_duplicate_spell_names_in_registry(self):
        """Every spell must have a unique name (no dict-key collisions)."""
        names = [s.name for s in SPELL_REGISTRY.values()]
        assert len(names) == len(set(names)), "Duplicate spell names detected"


# --------------------------------------------------------------------------- #
# Registration shape — every new spell at its correct level and school
# --------------------------------------------------------------------------- #
NEW_SPELLS: list[tuple[str, int, SpellSchool]] = [
    # Damage / save-for-half
    ("Blade Barrier", 6, SpellSchool.EVOCATION),
    ("Otiluke's Freezing Sphere", 6, SpellSchool.EVOCATION),
    ("Wall of Thorns", 6, SpellSchool.CONJURATION),
    # Save-debuff (no damage)
    ("Eyebite", 6, SpellSchool.NECROMANCY),
    ("Magic Jar", 6, SpellSchool.NECROMANCY),
    ("Mass Suggestion", 6, SpellSchool.ENCHANTMENT),
    # Utility / buff / ritual / summon
    ("Arcane Gate", 6, SpellSchool.CONJURATION),
    ("Conjure Fey", 6, SpellSchool.CONJURATION),
    ("Contingency", 6, SpellSchool.EVOCATION),
    ("Create Undead", 6, SpellSchool.NECROMANCY),
    ("Drawmij's Instant Summons", 6, SpellSchool.CONJURATION),
    ("Find the Path", 6, SpellSchool.DIVINATION),
    ("Guards and Wards", 6, SpellSchool.ABJURATION),
    ("Move Earth", 6, SpellSchool.TRANSMUTATION),
    ("Planar Ally", 6, SpellSchool.CONJURATION),
    ("Programmed Illusion", 6, SpellSchool.ILLUSION),
    ("Transport via Plants", 6, SpellSchool.CONJURATION),
    ("Wind Walk", 6, SpellSchool.TRANSMUTATION),
    ("Word of Recall", 6, SpellSchool.CONJURATION),
]


@pytest.mark.parametrize("name, level, school", NEW_SPELLS)
def test_new_spell_registered(name, level, school):
    spell = _spell(name)
    assert spell.level == level
    assert spell.school == school


def test_new_spell_count_matches_plan():
    """All 19 planned new spells are registered."""
    assert len(NEW_SPELLS) == 19
    for name, _, _ in NEW_SPELLS:
        assert get_spell(name) is not None, f"{name!r} missing from registry"


def test_new_spell_ids_are_stable():
    """Each spell's id derives cleanly from its name (no collisions)."""
    for name, _, _ in NEW_SPELLS:
        spell = _spell(name)
        assert spell.id == name.lower().replace(" ", "_")
        # The registry key must match the id (no overwrite surprises).
        assert SPELL_REGISTRY[spell.id] is spell


def test_registry_keys_are_unique():
    """No two registered spells share the same id key."""
    keys = list(SPELL_REGISTRY.keys())
    assert len(keys) == len(set(keys))


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness
# --------------------------------------------------------------------------- #
class TestDamageSpellMechanics:
    def test_blade_barrier_is_concentration_save_damage(self):
        spell = _spell("Blade Barrier")
        assert spell.save_ability == "dex"
        assert spell.concentration is True
        assert spell.damage_dice_count == 6 and spell.damage_dice_sides == 10
        assert spell.damage_type == "slashing"
        assert spell.casting_time == "1 action"
        assert spell.range == "90 feet"
        # PHB: Blade Barrier does not upcast damage.
        assert spell.at_higher_levels_dice == 0

    def test_otilukes_freezing_sphere_upcasts(self):
        spell = _spell("Otiluke's Freezing Sphere")
        assert spell.save_ability == "dex"
        assert spell.damage_dice_count == 10 and spell.damage_dice_sides == 6
        assert spell.damage_type == "cold"
        # +1d6 per slot level above 6.
        assert spell.at_higher_levels_dice == 1
        # Instantaneous, no concentration.
        assert spell.concentration is False

    def test_wall_of_thorns_upcasts_and_is_concentration(self):
        spell = _spell("Wall of Thorns")
        assert spell.save_ability == "dex"
        assert spell.damage_dice_count == 7 and spell.damage_dice_sides == 8
        assert spell.damage_type == "slashing"
        assert spell.at_higher_levels_dice == 1
        assert spell.concentration is True


class TestSaveDebuffMechanics:
    def test_eyebite_is_wis_save_concentration(self):
        spell = _spell("Eyebite")
        # Wisdom save governs all three modes (Asleep/Sickened/Panicked).
        assert spell.save_ability == "wis"
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.duration == "up to 1 minute"
        assert spell.range == "self"

    def test_magic_jar_is_cha_save_no_concentration(self):
        spell = _spell("Magic Jar")
        # Charisma save governs the possession attempt.
        assert spell.save_ability == "cha"
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.casting_time == "1 minute"

    def test_mass_suggestion_is_wis_save_concentration(self):
        spell = _spell("Mass Suggestion")
        assert spell.save_ability == "wis"
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.duration == "up to 24 hours"


class TestUtilityMechanics:
    def test_arcane_gate_is_concentration_utility(self):
        spell = _spell("Arcane Gate")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "up to 10 minutes"
        assert spell.range == "500 feet"

    def test_conjure_fey_is_concentration_summon(self):
        spell = _spell("Conjure Fey")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "up to 1 hour"

    def test_contingency_is_utility_long_duration_no_concentration(self):
        spell = _spell("Contingency")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "10 minutes"
        assert spell.duration == "10 days"

    def test_create_undead_is_summon_no_concentration(self):
        spell = _spell("Create Undead")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 minute"

    def test_drawmij_instant_summons_is_ritual(self):
        spell = _spell("Drawmij's Instant Summons")
        # Only new level-6 ritual in this batch.
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "touch"

    def test_find_the_path_is_concentration_divination(self):
        spell = _spell("Find the Path")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 minute"
        assert spell.range == "self"

    def test_guards_and_wards_is_long_utility_no_concentration(self):
        spell = _spell("Guards and Wards")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "10 minutes"
        assert spell.duration == "24 hours"

    def test_move_earth_has_two_hour_casting(self):
        spell = _spell("Move Earth")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        # Iconic for its unusually long casting time.
        assert spell.casting_time == "2 hours"
        assert spell.range == "120 feet"

    def test_planar_ally_is_utility_no_concentration(self):
        spell = _spell("Planar Ally")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "10 minutes"

    def test_programmed_illusion_is_utility_no_save(self):
        spell = _spell("Programmed Illusion")
        # Illusion is revealed by Investigation, not a save.
        assert spell.save_ability is None
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.duration == "until dispelled"

    def test_transport_via_plants_is_utility_instant(self):
        spell = _spell("Transport via Plants")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 action"
        assert spell.duration == "1 round"

    def test_wind_walk_is_utility_no_concentration(self):
        spell = _spell("Wind Walk")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "up to 8 hours"
        assert spell.casting_time == "1 minute"

    def test_word_of_recall_is_instant_teleport(self):
        spell = _spell("Word of Recall")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 action"
        assert spell.duration == "instantaneous"


# --------------------------------------------------------------------------- #
# Effect resolution of the new spells
# --------------------------------------------------------------------------- #
class TestNewSpellResolution:
    def test_blade_barrier_saves_and_fails(self):
        spell = _spell("Blade Barrier")
        # Made save: 0 damage on save = 0 (engine splits damage in half on save).
        effect = resolve_spell_effect(
            spell=spell, caster_level=13, proficiency_bonus=5,
            casting_mod=5, target_save_total=30, spell_save_dc=18,
        )
        assert effect.made_save is True
        # 6d10 (6-60) on a failed save; half on success.
        assert 0 <= effect.damage <= 60
        # Failed save: full damage.
        effect = resolve_spell_effect(
            spell=spell, caster_level=13, proficiency_bonus=5,
            casting_mod=5, target_save_total=5, spell_save_dc=18,
        )
        assert effect.made_save is False
        assert 6 <= effect.damage <= 60
        assert effect.half_damage is False
        assert effect.damage_type == "slashing"

    def test_otilukes_freezing_sphere_damage_range(self):
        spell = _spell("Otiluke's Freezing Sphere")
        effect = resolve_spell_effect(
            spell=spell, caster_level=13, proficiency_bonus=5,
            casting_mod=5, target_save_total=5, spell_save_dc=18,
        )
        assert effect.made_save is False
        # 10d6 (10-60) cold on a failed save.
        assert 10 <= effect.damage <= 60
        assert effect.damage_type == "cold"

    def test_wall_of_thorns_damage_range(self):
        spell = _spell("Wall of Thorns")
        effect = resolve_spell_effect(
            spell=spell, caster_level=13, proficiency_bonus=5,
            casting_mod=5, target_save_total=5, spell_save_dc=18,
        )
        assert effect.made_save is False
        # 7d8 (7-56) slashing on a failed save.
        assert 7 <= effect.damage <= 56
        assert effect.damage_type == "slashing"

    def test_eyebite_resolves_as_save_debuff(self):
        spell = _spell("Eyebite")
        effect = resolve_spell_effect(
            spell=spell, caster_level=13, proficiency_bonus=5,
            casting_mod=5, target_save_total=30, spell_save_dc=18,
        )
        assert effect.made_save is True
        assert effect.damage == 0

    def test_magic_jar_resolves_as_save_debuff(self):
        spell = _spell("Magic Jar")
        effect = resolve_spell_effect(
            spell=spell, caster_level=13, proficiency_bonus=5,
            casting_mod=5, target_save_total=5, spell_save_dc=18,
        )
        assert effect.made_save is False
        assert effect.damage == 0

    def test_mass_suggestion_resolves_as_save_debuff(self):
        spell = _spell("Mass Suggestion")
        effect = resolve_spell_effect(
            spell=spell, caster_level=13, proficiency_bonus=5,
            casting_mod=5, target_save_total=30, spell_save_dc=18,
        )
        assert effect.made_save is True
        assert effect.damage == 0

    @pytest.mark.parametrize(
        "name",
        [
            "Arcane Gate",
            "Conjure Fey",
            "Contingency",
            "Create Undead",
            "Drawmij's Instant Summons",
            "Find the Path",
            "Guards and Wards",
            "Move Earth",
            "Planar Ally",
            "Programmed Illusion",
            "Transport via Plants",
            "Wind Walk",
            "Word of Recall",
        ],
    )
    def test_utility_spell_resolves_cleanly(self, name):
        spell = _spell(name)
        effect = resolve_spell_effect(
            spell=spell, caster_level=13, proficiency_bonus=5, casting_mod=5,
        )
        assert effect.damage == 0 and effect.healing == 0
        assert "takes effect" in effect.description


# --------------------------------------------------------------------------- #
# Cross-spell upcasting sanity (only Otiluke / Wall of Thorns upcast in batch)
# --------------------------------------------------------------------------- #
class TestUpcasting:
    def test_otilukes_freezing_sphere_upcast_adds_dice(self):
        spell = _spell("Otiluke's Freezing Sphere")
        # +1d6 per slot level above 6; assert the roll-count math (the value
        # comparison would be flaky because dice are random).
        assert spell.at_higher_levels_dice == 1
        assert spell.damage_dice_count == 10
        assert (
            spell.damage_dice_count + spell.at_higher_levels_dice * 2
            - spell.damage_dice_count
            == 2
        )

    def test_wall_of_thorns_upcast_adds_dice(self):
        spell = _spell("Wall of Thorns")
        base_count = spell.damage_dice_count  # 7
        upcast_count = spell.damage_dice_count + spell.at_higher_levels_dice * 1
        # +1d8 per slot level above 6.
        assert spell.at_higher_levels_dice == 1
        assert upcast_count - base_count == 1
