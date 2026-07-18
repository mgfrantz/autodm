"""
Tests for the high-level spell registry expansion — 25 iconic SRD spells added
to fill the thin upper tiers (levels 4-9), plus a regression guard for the
Thunderwave duplicate-registration bug (a second Level-3 registration had been
silently overwriting the canonical Level-1 entry via the shared id key).

Coverage:
- Registration shape for every new spell (name, level, school) — parametrized.
- Per-spell mechanical correctness (damage dice, save ability, concentration,
  heals/deals_damage flags) for the mechanically-interesting entries.
- Effect resolution for save spells, healers, upcast scaling, and no-damage
  save spells.
- Registry distribution sanity (levels 4-8 each have >= 10 spells now; the
  canonical Thunderwave is Level 1).
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
# Registry distribution sanity + the Thunderwave regression
# --------------------------------------------------------------------------- #
class TestRegistryShape:
    def test_total_spell_count_grew(self):
        # Was 108 before this expansion; now 133.
        assert len(SPELL_REGISTRY) >= 133

    def test_upper_tiers_are_filled(self):
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        # Levels 4-8 each now have at least 10 spells (previously 7-8).
        for level in range(4, 9):
            assert by_level[level] >= 10, (
                f"Level {level} has only {by_level[level]} spells (expected >=10)"
            )
        # Level 9 has at least 9.
        assert by_level[9] >= 9

    def test_thunderwave_is_level_1_regression(self):
        """Thunderwave is a 1st-level evocation spell. A duplicate Level-3
        registration previously overwrote the canonical entry (same id key).
        Guard against that regression."""
        spell = _spell("Thunderwave")
        assert spell.level == 1
        assert spell.school == SpellSchool.EVOCATION
        assert spell.save_ability == "con"
        assert spell.deals_damage is True
        # No Level-3 Thunderwave masquerading in the registry.
        assert all(not (s.name == "Thunderwave" and s.level == 3)
                   for s in SPELL_REGISTRY.values())


# --------------------------------------------------------------------------- #
# Registration shape — every new spell at its correct level and school
# --------------------------------------------------------------------------- #
NEW_SPELLS: list[tuple[str, int, SpellSchool]] = [
    # Level 4
    ("Banishment", 4, SpellSchool.ABJURATION),
    ("Confusion", 4, SpellSchool.ENCHANTMENT),
    ("Death Ward", 4, SpellSchool.ABJURATION),
    ("Dominate Beast", 4, SpellSchool.ENCHANTMENT),
    ("Evard's Black Tentacles", 4, SpellSchool.CONJURATION),
    ("Freedom of Movement", 4, SpellSchool.ABJURATION),
    # Level 5
    ("Dominate Person", 5, SpellSchool.ENCHANTMENT),
    ("Greater Restoration", 5, SpellSchool.ABJURATION),
    ("Insect Plague", 5, SpellSchool.CONJURATION),
    ("Mass Cure Wounds", 5, SpellSchool.EVOCATION),
    ("Wall of Force", 5, SpellSchool.EVOCATION),
    # Level 6
    ("Circle of Death", 6, SpellSchool.NECROMANCY),
    ("Harm", 6, SpellSchool.NECROMANCY),
    ("Heroes' Feast", 6, SpellSchool.CONJURATION),
    ("Otto's Irresistible Dance", 6, SpellSchool.ENCHANTMENT),
    ("Wall of Ice", 6, SpellSchool.EVOCATION),
    # Level 7
    ("Delayed Blast Fireball", 7, SpellSchool.EVOCATION),
    ("Prismatic Spray", 7, SpellSchool.EVOCATION),
    ("Resurrection", 7, SpellSchool.NECROMANCY),
    ("Reverse Gravity", 7, SpellSchool.TRANSMUTATION),
    # Level 8
    ("Antimagic Field", 8, SpellSchool.ABJURATION),
    ("Incendiary Cloud", 8, SpellSchool.CONJURATION),
    ("Mind Blank", 8, SpellSchool.ABJURATION),
    # Level 9
    ("Mass Heal", 9, SpellSchool.EVOCATION),
    ("Prismatic Wall", 9, SpellSchool.EVOCATION),
]


@pytest.mark.parametrize("name, level, school", NEW_SPELLS)
def test_new_spell_registered(name, level, school):
    spell = _spell(name)
    assert spell.level == level
    assert spell.school == school


def test_new_spell_count_matches_plan():
    """All 25 planned new spells are registered."""
    assert len(NEW_SPELLS) == 25
    for name, _, _ in NEW_SPELLS:
        assert get_spell(name) is not None, f"{name!r} missing from registry"


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness
# --------------------------------------------------------------------------- #
class TestLevel4Mechanics:
    def test_banishment(self):
        spell = _spell("Banishment")
        assert spell.save_ability == "wis"
        assert spell.concentration is True
        assert spell.deals_damage is False and spell.heals is False

    def test_confusion(self):
        spell = _spell("Confusion")
        assert spell.save_ability == "wis"
        assert spell.concentration is True
        assert spell.deals_damage is False

    def test_death_ward_is_a_buff(self):
        spell = _spell("Death Ward")
        assert spell.save_ability is None
        assert spell.concentration is False
        assert spell.deals_damage is False and spell.heals is False
        assert spell.duration == "8 hours"

    def test_dominate_beast(self):
        spell = _spell("Dominate Beast")
        assert spell.save_ability == "wis"
        assert spell.concentration is True

    def test_evrads_black_tentacles(self):
        spell = _spell("Evard's Black Tentacles")
        assert spell.save_ability == "dex"
        assert spell.deals_damage is True
        assert spell.damage_dice_count == 3 and spell.damage_dice_sides == 6
        assert spell.damage_type == "bludgeoning"
        assert spell.concentration is True

    def test_freedom_of_movement_is_a_buff(self):
        spell = _spell("Freedom of Movement")
        assert spell.save_ability is None
        assert spell.concentration is False
        assert spell.deals_damage is False and spell.heals is False
        assert spell.duration == "1 hour"


class TestLevel5Mechanics:
    def test_dominate_person(self):
        spell = _spell("Dominate Person")
        assert spell.save_ability == "wis"
        assert spell.concentration is True
        assert spell.deals_damage is False

    def test_greater_restoration_is_utility(self):
        spell = _spell("Greater Restoration")
        assert spell.save_ability is None
        assert spell.deals_damage is False and spell.heals is False
        assert spell.range == "touch"

    def test_insect_plague(self):
        spell = _spell("Insect Plague")
        assert spell.save_ability == "con"
        assert spell.deals_damage is True
        assert spell.damage_dice_count == 4 and spell.damage_dice_sides == 10
        assert spell.damage_type == "piercing"
        assert spell.concentration is True

    def test_mass_cure_wounds_heals(self):
        spell = _spell("Mass Cure Wounds")
        assert spell.heals is True
        assert spell.healing_dice_count == 3 and spell.healing_dice_sides == 8
        assert spell.at_higher_levels_dice == 1
        assert spell.deals_damage is False

    def test_wall_of_force_is_a_barrier(self):
        spell = _spell("Wall of Force")
        assert spell.concentration is True
        assert spell.deals_damage is False and spell.heals is False
        assert spell.save_ability is None  # barrier, no save


class TestLevel6Mechanics:
    def test_circle_of_death(self):
        spell = _spell("Circle of Death")
        assert spell.save_ability == "con"
        assert spell.damage_dice_count == 8 and spell.damage_dice_sides == 6
        assert spell.damage_type == "necrotic"
        # Upcast adds 2d6 per slot level above 6th.
        assert spell.at_higher_levels_dice == 2

    def test_harm(self):
        spell = _spell("Harm")
        assert spell.save_ability == "con"
        assert spell.damage_dice_count == 14 and spell.damage_dice_sides == 6
        assert spell.damage_type == "necrotic"

    def test_heroes_feast_is_a_buff(self):
        spell = _spell("Heroes' Feast")
        assert spell.deals_damage is False and spell.heals is False
        assert spell.concentration is False
        assert spell.duration == "24 hours"

    def test_ottos_irresistible_dance(self):
        spell = _spell("Otto's Irresistible Dance")
        # No save on cast (it's irresistible); concentration maintained.
        assert spell.concentration is True
        assert spell.deals_damage is False
        # The verbal-only components match the SRD.
        assert "V" in spell.components and "S" not in spell.components

    def test_wall_of_ice(self):
        spell = _spell("Wall of Ice")
        assert spell.concentration is True
        assert spell.save_ability == "dex"
        assert spell.deals_damage is True
        assert spell.damage_type == "cold"


class TestLevel7Mechanics:
    def test_delayed_blast_fireball(self):
        spell = _spell("Delayed Blast Fireball")
        assert spell.save_ability == "dex"
        assert spell.damage_dice_count == 12 and spell.damage_dice_sides == 6
        assert spell.damage_type == "fire"
        assert spell.at_higher_levels_dice == 1
        assert spell.concentration is True

    def test_prismatic_spray(self):
        spell = _spell("Prismatic Spray")
        assert spell.save_ability == "dex"
        assert spell.damage_dice_count == 8 and spell.damage_dice_sides == 6
        assert spell.deals_damage is True

    def test_resurrection_is_utility(self):
        spell = _spell("Resurrection")
        assert spell.save_ability is None
        assert spell.deals_damage is False and spell.heals is False
        assert spell.casting_time == "1 hour"

    def test_reverse_gravity(self):
        spell = _spell("Reverse Gravity")
        assert spell.save_ability == "dex"
        assert spell.concentration is True
        assert spell.deals_damage is False  # falling damage is environmental


class TestLevel8Mechanics:
    def test_antimagic_field(self):
        spell = _spell("Antimagic Field")
        assert spell.concentration is True
        assert spell.deals_damage is False and spell.heals is False
        assert spell.save_ability is None

    def test_incendiary_cloud(self):
        spell = _spell("Incendiary Cloud")
        assert spell.save_ability == "dex"
        assert spell.damage_dice_count == 8 and spell.damage_dice_sides == 6
        assert spell.damage_type == "fire"
        assert spell.concentration is True

    def test_mind_blank_is_a_buff(self):
        spell = _spell("Mind Blank")
        assert spell.concentration is False
        assert spell.deals_damage is False and spell.heals is False
        assert spell.duration == "24 hours"


class TestLevel9Mechanics:
    def test_mass_heal(self):
        spell = _spell("Mass Heal")
        # Flat 700 HP heal recorded; no dice (mirrors the Power Word Heal
        # precedent for large flat heals).
        assert spell.healing_bonus == 700
        assert spell.heals is False  # no dice -> not a rolling heal
        assert spell.deals_damage is False

    def test_prismatic_wall(self):
        spell = _spell("Prismatic Wall")
        assert spell.save_ability == "dex"
        # Modeled as 20d6 (10d6 fire + 10d6 radiant combined).
        assert spell.damage_dice_count == 20 and spell.damage_dice_sides == 6
        assert spell.deals_damage is True


# --------------------------------------------------------------------------- #
# Effect resolution of the new spells
# --------------------------------------------------------------------------- #
class TestNewSpellResolution:
    def test_delayed_blast_fireball_save_for_half(self):
        spell = _spell("Delayed Blast Fireball")
        # Failed save -> full 12d6 (12-72).
        effect = resolve_spell_effect(
            spell=spell, caster_level=13, proficiency_bonus=5,
            casting_mod=5, target_save_total=5, spell_save_dc=18,
        )
        assert effect.made_save is False
        assert effect.damage_type == "fire"
        assert 12 <= effect.damage <= 72
        # Made save -> half damage.
        effect = resolve_spell_effect(
            spell=spell, caster_level=13, proficiency_bonus=5,
            casting_mod=5, target_save_total=30, spell_save_dc=18,
        )
        assert effect.made_save is True
        assert effect.half_damage is True

    def test_delayed_blast_fireball_upcast_adds_dice(self):
        spell = _spell("Delayed Blast Fireball")
        # Base 7th level: 12d6. Upcast to 9th adds 2 dice -> 14d6 (14-84).
        base = spell.roll_damage(caster_level=13, slot_level=7)
        upcast = spell.roll_damage(caster_level=13, slot_level=9)
        assert 12 <= base <= 72
        assert 14 <= upcast <= 84

    def test_circle_of_death_upcast_adds_two_dice(self):
        spell = _spell("Circle of Death")
        # Base 6th level: 8d6 (8-48). Upcast to 8th adds 2*2=4 dice -> 12d6.
        base = spell.roll_damage(caster_level=11, slot_level=6)
        upcast = spell.roll_damage(caster_level=11, slot_level=8)
        assert 8 <= base <= 48
        assert 12 <= upcast <= 72

    def test_harm_resolution(self):
        spell = _spell("Harm")
        effect = resolve_spell_effect(
            spell=spell, caster_level=11, proficiency_bonus=4,
            casting_mod=5, target_save_total=5, spell_save_dc=17,
        )
        assert effect.made_save is False
        assert effect.damage_type == "necrotic"
        assert 14 <= effect.damage <= 84  # 14d6

    def test_mass_cure_wounds_heals_and_upcasts(self):
        spell = _spell("Mass Cure Wounds")
        effect = resolve_spell_effect(
            spell=spell, caster_level=9, proficiency_bonus=4, casting_mod=5,
        )
        assert effect.healing >= 3  # at least 3 from 3d8
        assert "HP" in effect.description
        # Upcast to a 7th-level slot adds 2 dice -> 5d8.
        assert 5 <= spell.roll_healing(caster_level=9, slot_level=7) <= 40

    def test_insect_plague_resolution(self):
        spell = _spell("Insect Plague")
        effect = resolve_spell_effect(
            spell=spell, caster_level=9, proficiency_bonus=4,
            casting_mod=5, target_save_total=30, spell_save_dc=17,
        )
        assert effect.made_save is True
        assert effect.half_damage is True
        assert effect.damage_type == "piercing"

    def test_banishment_resolves_as_save_utility(self):
        # Save spell with no damage -> resolved/description path.
        spell = _spell("Banishment")
        effect = resolve_spell_effect(
            spell=spell, caster_level=7, proficiency_bonus=3,
            casting_mod=5, target_save_total=30, spell_save_dc=16,
        )
        assert effect.made_save is True
        assert effect.damage == 0

    def test_death_ward_resolves_as_utility(self):
        spell = _spell("Death Ward")
        effect = resolve_spell_effect(
            spell=spell, caster_level=7, proficiency_bonus=3, casting_mod=5,
        )
        assert effect.damage == 0 and effect.healing == 0
        assert "takes effect" in effect.description

    def test_prismatic_wall_save_for_half(self):
        spell = _spell("Prismatic Wall")
        effect = resolve_spell_effect(
            spell=spell, caster_level=17, proficiency_bonus=6,
            casting_mod=5, target_save_total=5, spell_save_dc=19,
        )
        assert effect.made_save is False
        assert 20 <= effect.damage <= 120  # 20d6

    def test_wall_of_ice_save_resolution(self):
        spell = _spell("Wall of Ice")
        effect = resolve_spell_effect(
            spell=spell, caster_level=11, proficiency_bonus=4,
            casting_mod=5, target_save_total=30, spell_save_dc=17,
        )
        assert effect.made_save is True
        assert effect.half_damage is True
        assert effect.damage_type == "cold"
