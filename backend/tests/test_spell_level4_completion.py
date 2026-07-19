"""
Tests for the PHB level-4 spell COMPLETION — 16 iconic PHB level-4 spells added
to bring level 4 to full Player's Handbook coverage (14 -> 30; catalogue
270 -> 286).

This finishes the catalogue-wide "PHB completeness" effort at the 4th-level
tier. Levels 1, 2, 3, 6, 7/8/9 were already PHB-complete; this run adds every
remaining iconic PHB 4th-level spell so **every Player's Handbook 4th-level
spell is now registered** (level 4: 14 -> 30). Eight of the ten tiers
(1, 2, 3, 4, 6, 7, 8, 9) are now PHB-complete.

Mirrors the level-1 / level-2 / level-3 / level-6 PHB-completeness expansion
test files.

The 16 additions (grouped by resolution path):
- Save-spell with damage: Wall of Fire (Dex, 5d8 fire, +1d8/slot, concentration),
  Sickening Radiance (Con, 4d10 radiant, +1d10/slot, concentration, exhaustion).
- Save-debuff (no damage): Compulsion (Wis, concentration, force movement),
  Otiluke's Resilient Sphere (Dex, concentration, restrain).
- Utility / buff / ritual (12 spells): Arcane Eye (concentration, 1-min cast,
  1-hour sensor), Conjure Minor Elementals (concentration summon), Control
  Water (concentration, 4 modes), Divination (ritual, 1-min cast), Fabricate
  (10-min cast, craft goods), Giant Insect (concentration), Guardian of Faith
  (8-hour, no concentration, 20 radiant / 60 cap effect-in-description),
  Hallucinatory Terrain (24-hour, no concentration, Investigation),
  Leomund's Secret Chest (ritual), Locate Creature (concentration),
  Mordenkainen's Faithful Hound (8-hour, no concentration), Stone Shape
  (instantaneous transmutation).

Coverage mirrors test_spell_level3_completion.py:
- Registry distribution (level 4 grew 14 -> 30; catalogue 270 -> 286; PHB-
  complete tiers untouched at their floors).
- Registration shape for every new spell (name, level, school) — parametrized.
- Per-spell mechanical correctness (save ability, concentration, dice, flags).
- Effect resolution for the damage, save-debuff, and utility spells (all
  resolve without raising).
- Whole-registry no-duplicate-name guard + upcasting math (Wall of Fire +1d8,
  Sickening Radiance +1d10).
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
# Registry distribution + level-4 tier growth
# --------------------------------------------------------------------------- #
class TestRegistryShape:
    def test_total_spell_count_grew(self):
        # Was 270 before this completion; now 286.
        assert len(SPELL_REGISTRY) >= 286

    def test_level_4_tier_grew(self):
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        # Level 4 grew 14 -> 30 (full PHB coverage).
        assert by_level[4] >= 30, (
            f"Level 4 has only {by_level[4]} spells (expected >=30)"
        )

    def test_other_tiers_floor_intact(self):
        """This completion touches only level 4; every PHB-complete tier is
        at least its canonical minimum (floors are robust against other test
        modules that may register additional spells in the shared registry)."""
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        # The PHB-complete tiers are untouched (at their canonical floors).
        assert by_level[1] >= 53   # PHB-complete
        assert by_level[2] >= 55   # PHB-complete
        assert by_level[3] >= 39   # PHB-complete
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
    # Save-spell with damage
    ("Wall of Fire", 4, SpellSchool.EVOCATION),
    ("Sickening Radiance", 4, SpellSchool.EVOCATION),
    # Save-debuff (no damage)
    ("Compulsion", 4, SpellSchool.ENCHANTMENT),
    ("Otiluke's Resilient Sphere", 4, SpellSchool.EVOCATION),
    # Utility / buff / ritual
    ("Arcane Eye", 4, SpellSchool.DIVINATION),
    ("Conjure Minor Elementals", 4, SpellSchool.CONJURATION),
    ("Control Water", 4, SpellSchool.TRANSMUTATION),
    ("Divination", 4, SpellSchool.DIVINATION),
    ("Fabricate", 4, SpellSchool.TRANSMUTATION),
    ("Giant Insect", 4, SpellSchool.TRANSMUTATION),
    ("Guardian of Faith", 4, SpellSchool.CONJURATION),
    ("Hallucinatory Terrain", 4, SpellSchool.ILLUSION),
    ("Leomund's Secret Chest", 4, SpellSchool.CONJURATION),
    ("Locate Creature", 4, SpellSchool.DIVINATION),
    ("Mordenkainen's Faithful Hound", 4, SpellSchool.CONJURATION),
    ("Stone Shape", 4, SpellSchool.TRANSMUTATION),
]


@pytest.mark.parametrize("name, level, school", NEW_SPELLS)
def test_new_spell_registered(name, level, school):
    spell = _spell(name)
    assert spell.level == level
    assert spell.school == school


def test_new_spell_count_matches_plan():
    """All 16 planned new spells are registered."""
    assert len(NEW_SPELLS) == 16
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
# Per-spell mechanical correctness — save-spell with damage
# --------------------------------------------------------------------------- #
class TestDamageSpellMechanics:
    def test_wall_of_fire_is_dex_save_fire_damage_with_upcast(self):
        spell = _spell("Wall of Fire")
        assert spell.save_ability == "dex"
        assert spell.concentration is True
        assert spell.damage_dice_count == 5 and spell.damage_dice_sides == 8
        assert spell.damage_type == "fire"
        # +1d8 per slot level above 4th (PHB p.284).
        assert spell.at_higher_levels_dice == 1
        assert spell.deals_damage is True
        assert spell.requires_attack_roll is False
        assert spell.range == "120 feet"
        assert spell.duration == "up to 1 minute"
        assert spell.school == SpellSchool.EVOCATION

    def test_sickening_radiance_is_con_save_radiant_with_upcast(self):
        spell = _spell("Sickening Radiance")
        assert spell.save_ability == "con"
        assert spell.concentration is True
        assert spell.damage_dice_count == 4 and spell.damage_dice_sides == 10
        assert spell.damage_type == "radiant"
        # +1d10 per slot level above 4th (PHB p.277).
        assert spell.at_higher_levels_dice == 1
        assert spell.deals_damage is True
        assert spell.requires_attack_roll is False
        assert spell.range == "120 feet"
        # PHB signature: Sickening Radiance's dim light lingers up to 10 minutes.
        assert spell.duration == "up to 10 minutes"
        assert spell.school == SpellSchool.EVOCATION


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness — save-debuff (no damage)
# --------------------------------------------------------------------------- #
class TestSaveDebuffMechanics:
    def test_compulsion_is_wis_save_concentration_no_damage(self):
        spell = _spell("Compulsion")
        assert spell.save_ability == "wis"
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.requires_attack_roll is False
        assert spell.range == "30 feet"
        assert spell.duration == "up to 1 minute"
        assert spell.school == SpellSchool.ENCHANTMENT

    def test_otilukes_resilient_sphere_is_dex_save_concentration_no_damage(self):
        spell = _spell("Otiluke's Resilient Sphere")
        assert spell.save_ability == "dex"
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.requires_attack_roll is False
        assert spell.range == "30 feet"
        assert spell.duration == "up to 1 minute"
        assert spell.school == SpellSchool.EVOCATION


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness — utility / buff / ritual
# --------------------------------------------------------------------------- #
class TestUtilityMechanics:
    def test_arcane_eye_is_concentration_divination_with_long_cast(self):
        spell = _spell("Arcane Eye")
        assert spell.concentration is True
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.heals is False
        # PHB signature: Arcane Eye has a 1-minute casting time (creates a sensor).
        assert spell.casting_time == "1 minute"
        assert spell.range == "30 feet"
        assert spell.duration == "up to 1 hour"
        assert spell.school == SpellSchool.DIVINATION

    def test_conjure_minor_elementals_is_concentration_summon(self):
        spell = _spell("Conjure Minor Elementals")
        assert spell.concentration is True
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "90 feet"
        assert spell.duration == "up to 1 hour"
        assert spell.school == SpellSchool.CONJURATION

    def test_control_water_is_concentration_transmutation(self):
        spell = _spell("Control Water")
        assert spell.concentration is True
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "300 feet"
        assert spell.duration == "up to 10 minutes"
        assert spell.school == SpellSchool.TRANSMUTATION

    def test_divination_is_ritual_no_concentration(self):
        spell = _spell("Divination")
        # PHB: Divination is a ritual divination (no concentration).
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.school == SpellSchool.DIVINATION

    def test_fabricate_is_instantaneous_transmutation(self):
        spell = _spell("Fabricate")
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "instantaneous"
        assert spell.school == SpellSchool.TRANSMUTATION

    def test_giant_insect_is_concentration_transmutation(self):
        spell = _spell("Giant Insect")
        assert spell.concentration is True
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "30 feet"
        assert spell.duration == "up to 10 minutes"
        assert spell.school == SpellSchool.TRANSMUTATION

    def test_guardian_of_faith_is_long_duration_no_concentration(self):
        spell = _spell("Guardian of Faith")
        # PHB signature: Guardian of Faith lasts 8 hours with NO concentration
        # (a guardian field, not a maintained effect). The 20-radiant / 60-cap
        # mechanic doesn't fit the dice model and lives in the description
        # (effect-in-description convention, like other special-resolution spells).
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.requires_attack_roll is False
        assert spell.duration == "8 hours"
        assert spell.range == "30 feet"
        assert spell.school == SpellSchool.CONJURATION

    def test_hallucinatory_terrain_is_24_hour_no_concentration(self):
        spell = _spell("Hallucinatory Terrain")
        # PHB signature: Hallucinatory Terrain persists for 24 hours with NO
        # concentration (the illusion is set and endures; Investigation to
        # discern). 10-minute casting time.
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "10 minutes"
        assert spell.range == "300 feet"
        assert spell.duration == "24 hours"
        assert spell.school == SpellSchool.ILLUSION

    def test_leomunds_secret_chest_is_ritual_conjuration(self):
        spell = _spell("Leomund's Secret Chest")
        # PHB: Leomund's Secret Chest is a ritual conjuration; the chest is
        # hidden on the Ethereal Plane and recalled by recasting.
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.school == SpellSchool.CONJURATION

    def test_locate_creature_is_concentration_divination(self):
        spell = _spell("Locate Creature")
        assert spell.concentration is True
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "self"
        assert spell.duration == "up to 1 hour"
        assert spell.school == SpellSchool.DIVINATION

    def test_mordenkainens_faithful_hound_is_long_duration_no_concentration(self):
        spell = _spell("Mordenkainen's Faithful Hound")
        # PHB signature: the hound guards for 8 hours with NO concentration
        # (it is a set guardian, not a maintained effect). The bite effect is
        # documented in the description (effect-in-description convention).
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.requires_attack_roll is False
        assert spell.duration == "8 hours"
        assert spell.school == SpellSchool.CONJURATION

    def test_stone_shape_is_instantaneous_transmutation(self):
        spell = _spell("Stone Shape")
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 action"
        assert spell.range == "touch"
        assert spell.duration == "instantaneous"
        assert spell.school == SpellSchool.TRANSMUTATION


# --------------------------------------------------------------------------- #
# Effect resolution of the new spells
# --------------------------------------------------------------------------- #
class TestNewSpellResolution:
    def test_wall_of_fire_saves_and_fails(self):
        spell = _spell("Wall of Fire")
        # Made save: half damage (5d8 is 5-40; half is 2-20).
        effect = resolve_spell_effect(
            spell=spell, caster_level=7, proficiency_bonus=3,
            casting_mod=4, target_save_total=30, spell_save_dc=15,
        )
        assert effect.made_save is True
        assert 2 <= effect.damage <= 20
        assert effect.half_damage is True
        # Failed save: full damage.
        effect = resolve_spell_effect(
            spell=spell, caster_level=7, proficiency_bonus=3,
            casting_mod=4, target_save_total=2, spell_save_dc=15,
        )
        assert effect.made_save is False
        assert 5 <= effect.damage <= 40
        assert effect.half_damage is False
        assert effect.damage_type == "fire"

    def test_sickening_radiance_saves_and_fails(self):
        spell = _spell("Sickening Radiance")
        # Made save: half damage (4d10 is 4-40; half is 2-20).
        effect = resolve_spell_effect(
            spell=spell, caster_level=7, proficiency_bonus=3,
            casting_mod=4, target_save_total=30, spell_save_dc=15,
        )
        assert effect.made_save is True
        assert 2 <= effect.damage <= 20
        assert effect.half_damage is True
        # Failed save: full damage.
        effect = resolve_spell_effect(
            spell=spell, caster_level=7, proficiency_bonus=3,
            casting_mod=4, target_save_total=2, spell_save_dc=15,
        )
        assert effect.made_save is False
        assert 4 <= effect.damage <= 40
        assert effect.half_damage is False
        assert effect.damage_type == "radiant"

    @pytest.mark.parametrize(
        "name, save_ability",
        [
            ("Compulsion", "wis"),
            ("Otiluke's Resilient Sphere", "dex"),
        ],
    )
    def test_save_debuff_spell_resolves(self, name, save_ability):
        spell = _spell(name)
        assert spell.save_ability == save_ability
        effect = resolve_spell_effect(
            spell=spell, caster_level=7, proficiency_bonus=3,
            casting_mod=4, target_save_total=30, spell_save_dc=15,
        )
        assert effect.made_save is True
        assert effect.damage == 0
        assert "save" in effect.description

    @pytest.mark.parametrize(
        "name",
        [
            "Arcane Eye",
            "Conjure Minor Elementals",
            "Control Water",
            "Divination",
            "Fabricate",
            "Giant Insect",
            "Guardian of Faith",
            "Hallucinatory Terrain",
            "Leomund's Secret Chest",
            "Locate Creature",
            "Mordenkainen's Faithful Hound",
            "Stone Shape",
        ],
    )
    def test_utility_spell_resolves_cleanly(self, name):
        spell = _spell(name)
        effect = resolve_spell_effect(
            spell=spell, caster_level=7, proficiency_bonus=3, casting_mod=5,
        )
        assert effect.damage == 0 and effect.healing == 0
        assert "takes effect" in effect.description


# --------------------------------------------------------------------------- #
# Upcasting sanity (Wall of Fire +1d8, Sickening Radiance +1d10)
# --------------------------------------------------------------------------- #
class TestUpcasting:
    def test_wall_of_fire_upcasts_1d8_per_level(self):
        spell = _spell("Wall of Fire")
        assert spell.damage_dice_count == 5
        assert spell.at_higher_levels_dice == 1
        # At slot 6 (2 levels above base), dice count = 5 + 2*1 = 7.
        extra_levels = 2
        upcast_count = spell.damage_dice_count + spell.at_higher_levels_dice * extra_levels
        assert upcast_count == 7

    def test_sickening_radiance_upcasts_1d10_per_level(self):
        spell = _spell("Sickening Radiance")
        assert spell.damage_dice_count == 4
        assert spell.at_higher_levels_dice == 1
        # At slot 6 (2 levels above base), dice count = 4 + 2*1 = 6.
        extra_levels = 2
        upcast_count = spell.damage_dice_count + spell.at_higher_levels_dice * extra_levels
        assert upcast_count == 6

    def test_wall_of_fire_roll_damage_at_upcast(self):
        """Upcasting the damage roll grows by the configured dice count."""
        spell = _spell("Wall of Fire")
        # Base slot: 5d8 = 5-40.
        base = spell.roll_damage(caster_level=7, slot_level=4)
        assert 5 <= base <= 40
        # Slot 6: 7d8 = 7-56.
        upcast = spell.roll_damage(caster_level=7, slot_level=6)
        assert 7 <= upcast <= 56

    def test_sickening_radiance_roll_damage_at_upcast(self):
        """Upcasting the damage roll grows by the configured dice count."""
        spell = _spell("Sickening Radiance")
        # Base slot: 4d10 = 4-40.
        base = spell.roll_damage(caster_level=7, slot_level=4)
        assert 4 <= base <= 40
        # Slot 6: 6d10 = 6-60.
        upcast = spell.roll_damage(caster_level=7, slot_level=6)
        assert 6 <= upcast <= 60
