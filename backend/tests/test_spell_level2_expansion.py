"""
Tests for the PHB level-2 spell expansion — 20 iconic PHB level-2 spells added
to expand the catalogue's thinnest remaining tier relative to the Player's
Handbook (was 16; PHB has ~54). After this run, level 2 stands at 36 and the
catalogue at 225 spells.

This mirrors the level-1 / level-6 PHB-completeness expansions
(test_spell_level1_completion.py, test_spell_level6_completion.py).

The 20 additions (grouped by resolution path):
- Save-for-half damage: Moonbeam (Con, 2d10 radiant, +1d10/slot).
- Attack-roll: Flame Blade (3d6 fire melee spell attack, +1d6/slot),
  Spiritual Weapon (1d8 force + spellcasting mod, no concentration, +1d8/slot).
- Direct damage (no attack roll, no save): Heat Metal (2d8 fire, +1d8/slot),
  Spike Growth (2d4 piercing zone).
- Save-spell with damage: Phantasmal Force (Int save, 1d6 psychic).
- Save-debuff (no damage): Crown of Madness (Wis), Calm Emotions (Cha),
  Enlarge/Reduce (Con), Levitate (Con).
- Utility / buff / ritual: Darkness, Silence (ritual), Blur, Barkskin,
  Detect Thoughts, See Invisibility, Darkvision (ritual), Knock, Augury
  (ritual), Pass Without Trace.

Coverage mirrors test_spell_level6_completion.py:
- Registry distribution (level 2 grew 16 -> 36; catalogue 205 -> 225).
- Registration shape for every new spell (name, level, school) — parametrized.
- Per-spell mechanical correctness (save ability, concentration, dice, flags).
- Effect resolution for the damage, attack-roll, save-debuff, and utility
  spells (all resolve without raising).
- Whole-registry no-duplicate-name guard + upcasting math.
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
# Registry distribution + level-2 tier growth
# --------------------------------------------------------------------------- #
class TestRegistryShape:
    def test_total_spell_count_grew(self):
        # Was 205 before this expansion; now 225.
        assert len(SPELL_REGISTRY) >= 225

    def test_level_2_tier_grew(self):
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        # Level 2 grew 16 -> 36.
        assert by_level[2] >= 36, (
            f"Level 2 has only {by_level[2]} spells (expected >=36)"
        )

    def test_other_tiers_floor_intact(self):
        """This expansion touches only level 2; every PHB-complete tier is
        at least its canonical minimum (floors are robust against other test
        modules that may register additional spells in the shared registry)."""
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        # The PHB-complete tiers are untouched (at their canonical floors).
        assert by_level[1] >= 53   # PHB-complete
        assert by_level[6] >= 31   # PHB-complete
        assert by_level[7] >= 18   # PHB-complete
        assert by_level[8] >= 18   # PHB-complete
        assert by_level[9] >= 15   # PHB-complete

    def test_no_duplicate_spell_names_in_registry(self):
        """Every spell must have a unique name (no dict-key collisions)."""
        names = [s.name for s in SPELL_REGISTRY.values()]
        assert len(names) == len(set(names)), "Duplicate spell names detected"


# --------------------------------------------------------------------------- #
# Registration shape — every new spell at its correct level and school
# --------------------------------------------------------------------------- #
NEW_SPELLS: list[tuple[str, int, SpellSchool]] = [
    # Save-for-half damage
    ("Moonbeam", 2, SpellSchool.EVOCATION),
    # Attack-roll
    ("Flame Blade", 2, SpellSchool.EVOCATION),
    ("Spiritual Weapon", 2, SpellSchool.EVOCATION),
    # Direct damage (no attack roll, no save)
    ("Heat Metal", 2, SpellSchool.TRANSMUTATION),
    ("Spike Growth", 2, SpellSchool.TRANSMUTATION),
    # Save-spell with damage
    ("Phantasmal Force", 2, SpellSchool.ILLUSION),
    # Save-debuff (no damage)
    ("Crown of Madness", 2, SpellSchool.ENCHANTMENT),
    ("Calm Emotions", 2, SpellSchool.ENCHANTMENT),
    ("Enlarge/Reduce", 2, SpellSchool.TRANSMUTATION),
    ("Levitate", 2, SpellSchool.TRANSMUTATION),
    # Utility / buff / ritual
    ("Darkness", 2, SpellSchool.EVOCATION),
    ("Silence", 2, SpellSchool.ILLUSION),
    ("Blur", 2, SpellSchool.ILLUSION),
    ("Barkskin", 2, SpellSchool.TRANSMUTATION),
    ("Detect Thoughts", 2, SpellSchool.DIVINATION),
    ("See Invisibility", 2, SpellSchool.DIVINATION),
    ("Darkvision", 2, SpellSchool.TRANSMUTATION),
    ("Knock", 2, SpellSchool.TRANSMUTATION),
    ("Augury", 2, SpellSchool.DIVINATION),
    ("Pass Without Trace", 2, SpellSchool.ABJURATION),
]


@pytest.mark.parametrize("name, level, school", NEW_SPELLS)
def test_new_spell_registered(name, level, school):
    spell = _spell(name)
    assert spell.level == level
    assert spell.school == school


def test_new_spell_count_matches_plan():
    """All 20 planned new spells are registered."""
    assert len(NEW_SPELLS) == 20
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
# Per-spell mechanical correctness — damage / attack-roll / direct-damage
# --------------------------------------------------------------------------- #
class TestDamageAndAttackRollMechanics:
    def test_moonbeam_is_con_save_damage_with_upcast(self):
        spell = _spell("Moonbeam")
        assert spell.save_ability == "con"
        assert spell.concentration is True
        assert spell.damage_dice_count == 2 and spell.damage_dice_sides == 10
        assert spell.damage_type == "radiant"
        # +1d10 per slot level above 2.
        assert spell.at_higher_levels_dice == 1
        assert spell.casting_time == "1 action"
        assert spell.range == "120 feet"

    def test_flame_blade_is_melee_spell_attack(self):
        spell = _spell("Flame Blade")
        assert spell.requires_attack_roll is True
        assert spell.damage_dice_count == 3 and spell.damage_dice_sides == 6
        assert spell.damage_type == "fire"
        assert spell.concentration is True
        assert spell.at_higher_levels_dice == 1
        assert spell.casting_time == "1 bonus action"
        assert spell.range == "self"

    def test_spiritual_weapon_is_attack_no_concentration(self):
        spell = _spell("Spiritual Weapon")
        assert spell.requires_attack_roll is True
        assert spell.damage_dice_count == 1 and spell.damage_dice_sides == 8
        assert spell.damage_type == "force"
        # PHB: Spiritual Weapon does NOT require concentration.
        assert spell.concentration is False
        assert spell.at_higher_levels_dice == 1
        assert spell.casting_time == "1 bonus action"
        assert spell.range == "60 feet"

    def test_heat_metal_is_direct_damage_no_save(self):
        spell = _spell("Heat Metal")
        # No attack roll, no save — the engine's direct-damage path.
        assert spell.requires_attack_roll is False
        assert spell.save_ability is None
        assert spell.damage_dice_count == 2 and spell.damage_dice_sides == 8
        assert spell.damage_type == "fire"
        assert spell.concentration is True
        assert spell.at_higher_levels_dice == 1

    def test_spike_growth_is_direct_damage_zone(self):
        spell = _spell("Spike Growth")
        assert spell.requires_attack_roll is False
        assert spell.save_ability is None
        assert spell.damage_dice_count == 2 and spell.damage_dice_sides == 4
        assert spell.damage_type == "piercing"
        assert spell.concentration is True
        # PHB: Spike Growth does not upcast damage dice.
        assert spell.at_higher_levels_dice == 0
        assert spell.range == "150 feet"

    def test_phantasmal_force_is_int_save_damage(self):
        spell = _spell("Phantasmal Force")
        assert spell.save_ability == "int"
        assert spell.damage_dice_count == 1 and spell.damage_dice_sides == 6
        assert spell.damage_type == "psychic"
        assert spell.concentration is True


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness — save-debuff (no damage)
# --------------------------------------------------------------------------- #
class TestSaveDebuffMechanics:
    def test_crown_of_madness_is_wis_save_concentration(self):
        spell = _spell("Crown of Madness")
        assert spell.save_ability == "wis"
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.range == "120 feet"

    def test_calm_emotions_is_cha_save_concentration(self):
        spell = _spell("Calm Emotions")
        assert spell.save_ability == "cha"
        assert spell.concentration is True
        assert spell.deals_damage is False

    def test_enlarge_reduce_is_con_save_concentration(self):
        spell = _spell("Enlarge/Reduce")
        assert spell.save_ability == "con"
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.range == "30 feet"

    def test_levitate_is_con_save_concentration(self):
        spell = _spell("Levitate")
        assert spell.save_ability == "con"
        assert spell.concentration is True
        assert spell.deals_damage is False


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness — utility / buff / ritual
# --------------------------------------------------------------------------- #
class TestUtilityMechanics:
    def test_darkness_is_concentration_utility(self):
        spell = _spell("Darkness")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "up to 10 minutes"
        assert spell.school == SpellSchool.EVOCATION

    def test_silence_is_ritual_no_concentration(self):
        spell = _spell("Silence")
        # PHB: Silence is a ritual with NO concentration.
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "10 minutes"

    def test_blur_is_self_concentration_utility(self):
        spell = _spell("Blur")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "self"
        assert spell.duration == "up to 1 minute"

    def test_barkskin_is_touch_concentration_ac_buff(self):
        spell = _spell("Barkskin")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "touch"
        assert spell.duration == "up to 1 hour"

    def test_detect_thoughts_is_concentration_divination(self):
        spell = _spell("Detect Thoughts")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.school == SpellSchool.DIVINATION

    def test_see_invisibility_is_self_no_concentration(self):
        spell = _spell("See Invisibility")
        # PHB: See Invisibility has NO concentration.
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "1 hour"
        assert spell.school == SpellSchool.DIVINATION

    def test_darkvision_is_ritual_touch(self):
        spell = _spell("Darkvision")
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "touch"
        assert spell.duration == "8 hours"

    def test_knock_is_instantaneous_unlock(self):
        spell = _spell("Knock")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 action"
        assert spell.duration == "instantaneous"

    def test_augury_is_ritual_divination(self):
        spell = _spell("Augury")
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.school == SpellSchool.DIVINATION
        assert spell.casting_time == "1 minute"

    def test_pass_without_trace_is_self_concentration(self):
        spell = _spell("Pass Without Trace")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "self"
        assert spell.school == SpellSchool.ABJURATION


# --------------------------------------------------------------------------- #
# Effect resolution of the new spells
# --------------------------------------------------------------------------- #
class TestNewSpellResolution:
    def test_moonbeam_saves_and_fails(self):
        spell = _spell("Moonbeam")
        # Made save: half damage (2d10 is 2-20; half is 0-10).
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3,
            casting_mod=3, target_save_total=30, spell_save_dc=14,
        )
        assert effect.made_save is True
        assert 0 <= effect.damage <= 20
        # Failed save: full damage.
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3,
            casting_mod=3, target_save_total=2, spell_save_dc=14,
        )
        assert effect.made_save is False
        assert 2 <= effect.damage <= 20
        assert effect.half_damage is False
        assert effect.damage_type == "radiant"

    def test_flame_blade_attack_hits_and_misses(self):
        spell = _spell("Flame Blade")
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3,
            casting_mod=3, target_ac=10,
        )
        # On a hit, 3-18 fire damage; on a miss, 0.
        if effect.hit:
            assert 3 <= effect.damage <= 18
            assert effect.damage_type == "fire"
        else:
            assert effect.damage == 0

    def test_flame_blade_hit_requires_ac(self):
        spell = _spell("Flame Blade")
        # Attack-roll spells raise if no AC is given.
        with pytest.raises(ValueError):
            resolve_spell_effect(
                spell=spell, caster_level=5, proficiency_bonus=3,
                casting_mod=3,
            )

    def test_spiritual_weapon_attack_resolves(self):
        spell = _spell("Spiritual Weapon")
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3,
            casting_mod=3, target_ac=5,
        )
        # AC 5 nearly guarantees a hit (only a nat 1 misses).
        if effect.hit:
            assert 1 <= effect.damage <= 8
            assert effect.damage_type == "force"

    def test_heat_metal_applies_direct_damage(self):
        spell = _spell("Heat Metal")
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3, casting_mod=3,
        )
        # Direct-damage path: no save, no attack roll, 2-16 fire.
        assert effect.hit is None
        assert effect.made_save is None
        assert 2 <= effect.damage <= 16
        assert effect.damage_type == "fire"

    def test_spike_growth_applies_direct_damage(self):
        spell = _spell("Spike Growth")
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3, casting_mod=3,
        )
        assert effect.hit is None
        assert effect.made_save is None
        assert 2 <= effect.damage <= 8
        assert effect.damage_type == "piercing"

    def test_phantasmal_force_save_spell(self):
        spell = _spell("Phantasmal Force")
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3,
            casting_mod=3, target_save_total=2, spell_save_dc=14,
        )
        assert effect.made_save is False
        # 1d6 (1-6) psychic on a failed save.
        assert 1 <= effect.damage <= 6
        assert effect.damage_type == "psychic"

    @pytest.mark.parametrize(
        "name",
        ["Crown of Madness", "Calm Emotions", "Enlarge/Reduce", "Levitate"],
    )
    def test_save_debuff_spell_resolves(self, name):
        spell = _spell(name)
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3,
            casting_mod=3, target_save_total=30, spell_save_dc=14,
        )
        assert effect.made_save is True
        assert effect.damage == 0
        assert "save" in effect.description

    @pytest.mark.parametrize(
        "name",
        [
            "Darkness",
            "Silence",
            "Blur",
            "Barkskin",
            "Detect Thoughts",
            "See Invisibility",
            "Darkvision",
            "Knock",
            "Augury",
            "Pass Without Trace",
        ],
    )
    def test_utility_spell_resolves_cleanly(self, name):
        spell = _spell(name)
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3, casting_mod=5,
        )
        assert effect.damage == 0 and effect.healing == 0
        assert "takes effect" in effect.description


# --------------------------------------------------------------------------- #
# Upcasting sanity (Moonbeam / Flame Blade / Spiritual Weapon / Heat Metal)
# --------------------------------------------------------------------------- #
class TestUpcasting:
    @pytest.mark.parametrize(
        "name, base_count, per_level",
        [
            ("Moonbeam", 2, 1),
            ("Flame Blade", 3, 1),
            ("Spiritual Weapon", 1, 1),
            ("Heat Metal", 2, 1),
        ],
    )
    def test_upcast_dice_math(self, name, base_count, per_level):
        spell = _spell(name)
        assert spell.damage_dice_count == base_count
        assert spell.at_higher_levels_dice == per_level
        # At slot 4 (2 levels above base), dice count = base + 2*per_level.
        extra_levels = 2
        upcast_count = spell.damage_dice_count + spell.at_higher_levels_dice * extra_levels
        assert upcast_count == base_count + per_level * extra_levels

    def test_spike_growth_does_not_upcast(self):
        spell = _spell("Spike Growth")
        assert spell.at_higher_levels_dice == 0
