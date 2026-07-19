"""
Tests for the PHB level-2 spell COMPLETION — 19 iconic PHB level-2 spells
added to bring level 2 to full Player's Handbook coverage (36 → 55; catalogue
225 → 244).

This finishes the catalogue-wide "PHB completeness" effort at the most-played
tier. Levels 1, 6, 7/8/9 were already PHB-complete; the level-2 expansion run
brought the tier to 36; this run adds the final 19 so **every Player's
Handbook 2nd-level spell is now registered** (level 2: 36 → 55).

Mirrors the level-1 / level-6 PHB-completeness expansions
(test_spell_level1_completion.py, test_spell_level6_completion.py) and the
level-2 expansion (test_spell_level2_expansion.py).

The 19 additions (grouped by resolution path):
- Save-spell with damage: Cordon of Arrows (Dex, 1d6 piercing, +1d6/slot).
- Save-debuff (no damage): Gust of Wind (Str, push 15 ft), Enthrall (Wis,
  NO concentration — PHB signature), Zone of Truth (Cha, can't lie).
- Healing: Prayer of Healing (2d8+mod to up to 6 creatures, +1d8/slot,
  10-minute cast, Cleric signature).
- Utility / buff / ritual (14 spells): Alter Self (concentration, three
  modes), Animal Messenger (ritual, 24-hour), Arcane Lock (permanent),
  Beast Sense (ritual + concentration), Continual Flame (permanent flame),
  Find Steed (10-minute cast, summon mount, Paladin), Find Traps
  (instantaneous divination), Gentle Repose (ritual, 10-day), Locate Object
  (concentration), Magic Mouth (ritual, 1-minute cast), Magic Weapon
  (concentration, +1 weapon), Protection from Poison (1-hour, no
  concentration), Rope Trick (concentration, extradimensional space),
  Warding Bond (1-hour bond, NO concentration — PHB signature).

Coverage mirrors test_spell_level6_completion.py / test_spell_level2_expansion.py:
- Registry distribution (level 2 grew 36 -> 55; catalogue 225 -> 244; PHB-
  complete tiers untouched at their floors).
- Registration shape for every new spell (name, level, school) — parametrized.
- Per-spell mechanical correctness (save ability, concentration, dice, flags).
- Effect resolution for the damage, save-debuff, healing, and utility spells
  (all resolve without raising).
- Whole-registry no-duplicate-name guard + upcasting math (Cordon of Arrows,
  Prayer of Healing).
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
        # Was 225 before this completion; now 244.
        assert len(SPELL_REGISTRY) >= 244

    def test_level_2_tier_grew(self):
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        # Level 2 grew 36 -> 55 (full PHB coverage).
        assert by_level[2] >= 55, (
            f"Level 2 has only {by_level[2]} spells (expected >=55)"
        )

    def test_other_tiers_floor_intact(self):
        """This completion touches only level 2; every PHB-complete tier is
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
    # Save-spell with damage
    ("Cordon of Arrows", 2, SpellSchool.TRANSMUTATION),
    # Save-debuff (no damage)
    ("Gust of Wind", 2, SpellSchool.EVOCATION),
    ("Enthrall", 2, SpellSchool.ENCHANTMENT),
    ("Zone of Truth", 2, SpellSchool.ENCHANTMENT),
    # Healing
    ("Prayer of Healing", 2, SpellSchool.EVOCATION),
    # Utility / buff / ritual
    ("Alter Self", 2, SpellSchool.TRANSMUTATION),
    ("Animal Messenger", 2, SpellSchool.ENCHANTMENT),
    ("Arcane Lock", 2, SpellSchool.ABJURATION),
    ("Beast Sense", 2, SpellSchool.DIVINATION),
    ("Continual Flame", 2, SpellSchool.EVOCATION),
    ("Find Steed", 2, SpellSchool.CONJURATION),
    ("Find Traps", 2, SpellSchool.DIVINATION),
    ("Gentle Repose", 2, SpellSchool.NECROMANCY),
    ("Locate Object", 2, SpellSchool.DIVINATION),
    ("Magic Mouth", 2, SpellSchool.ILLUSION),
    ("Magic Weapon", 2, SpellSchool.TRANSMUTATION),
    ("Protection from Poison", 2, SpellSchool.ABJURATION),
    ("Rope Trick", 2, SpellSchool.TRANSMUTATION),
    ("Warding Bond", 2, SpellSchool.ABJURATION),
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
# Per-spell mechanical correctness — save-spell with damage
# --------------------------------------------------------------------------- #
class TestDamageSpellMechanics:
    def test_cordon_of_arrows_is_dex_save_damage_with_upcast(self):
        spell = _spell("Cordon of Arrows")
        assert spell.save_ability == "dex"
        assert spell.concentration is True
        assert spell.damage_dice_count == 1 and spell.damage_dice_sides == 6
        assert spell.damage_type == "piercing"
        # +1d6 per slot level above 2.
        assert spell.at_higher_levels_dice == 1
        assert spell.casting_time == "1 action"
        assert spell.range == "60 feet"
        assert spell.duration == "up to 1 minute"


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness — save-debuff (no damage)
# --------------------------------------------------------------------------- #
class TestSaveDebuffMechanics:
    def test_gust_of_wind_is_str_save_concentration(self):
        spell = _spell("Gust of Wind")
        # PHB: Gust of Wind is a Strength save (rare for 2nd-level).
        assert spell.save_ability == "str"
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.duration == "up to 1 minute"
        assert spell.range == "self (60-foot line)"

    def test_enthral_is_wis_save_no_concentration(self):
        spell = _spell("Enthrall")
        assert spell.save_ability == "wis"
        # PHB: Enthrall is the signature NO-concentration distraction spell.
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.duration == "1 minute"
        assert spell.casting_time == "1 action"

    def test_zone_of_truth_is_cha_save_concentration(self):
        spell = _spell("Zone of Truth")
        assert spell.save_ability == "cha"
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.duration == "up to 10 minutes"
        assert spell.range == "60 feet"


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness — healing
# --------------------------------------------------------------------------- #
class TestHealingMechanics:
    def test_prayer_of_healing_is_2d8_heal_with_upcast(self):
        spell = _spell("Prayer of Healing")
        assert spell.heals is True
        assert spell.healing_dice_count == 2 and spell.healing_dice_sides == 8
        # The +spellcasting modifier is caster-dependent — documented in the
        # description, not baked into healing_bonus (mirrors Cure Wounds /
        # Spiritual Weapon's caster-dependent bonus convention).
        assert spell.healing_bonus == 0
        # +1d8 per slot level above 2nd.
        assert spell.at_higher_levels_dice == 1
        assert spell.casting_time == "10 minutes"
        assert spell.range == "30 feet"
        assert spell.duration == "instantaneous"
        assert spell.school == SpellSchool.EVOCATION


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness — utility / buff / ritual
# --------------------------------------------------------------------------- #
class TestUtilityMechanics:
    def test_alter_self_is_self_concentration_three_modes(self):
        spell = _spell("Alter Self")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.heals is False
        assert spell.range == "self"
        assert spell.duration == "up to 1 hour"
        assert spell.school == SpellSchool.TRANSMUTATION

    def test_animal_messenger_is_ritual_long_duration(self):
        spell = _spell("Animal Messenger")
        # PHB: Animal Messenger is a ritual (druid/ranger/bard staple).
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "24 hours"
        assert spell.range == "30 feet"

    def test_arcane_lock_is_permanent_no_save(self):
        spell = _spell("Arcane Lock")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "touch"
        # PHB: Arcane Lock's effect is permanent until dispelled (instantaneous
        # cast; the lock is the lasting consequence).
        assert spell.duration == "instantaneous"
        assert spell.school == SpellSchool.ABJURATION

    def test_beast_sense_is_ritual_and_concentration(self):
        spell = _spell("Beast Sense")
        # PHB: Beast Sense is BOTH a ritual AND concentration (the rare
        # overlap — usable out of combat but ends if you cast another
        # concentration spell).
        assert spell.ritual is True
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "touch"
        assert spell.duration == "up to 1 hour"

    def test_continual_flame_is_permanent_no_concentration(self):
        spell = _spell("Continual Flame")
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "touch"
        assert spell.duration == "instantaneous"
        assert spell.school == SpellSchool.EVOCATION

    def test_find_steed_is_long_cast_summon(self):
        spell = _spell("Find Steed")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        # PHB signature: Find Steed has a 10-minute casting time (summon
        # ritual; not usable mid-combat).
        assert spell.casting_time == "10 minutes"
        assert spell.range == "30 feet"
        assert spell.duration == "instantaneous"
        assert spell.school == SpellSchool.CONJURATION

    def test_find_traps_is_instantaneous_divination(self):
        spell = _spell("Find Traps")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "instantaneous"
        assert spell.range == "120 feet"
        assert spell.school == SpellSchool.DIVINATION

    def test_gentle_repose_is_ritual_10_day(self):
        spell = _spell("Gentle Repose")
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "10 days"
        assert spell.range == "touch"

    def test_locate_object_is_concentration_divination(self):
        spell = _spell("Locate Object")
        assert spell.concentration is True
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "self"
        assert spell.duration == "up to 10 minutes"

    def test_magic_mouth_is_ritual_1_minute_cast(self):
        spell = _spell("Magic Mouth")
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        # PHB signature: 1-minute casting time (ritual enchantment).
        assert spell.casting_time == "1 minute"
        assert spell.range == "30 feet"
        assert spell.school == SpellSchool.ILLUSION

    def test_magic_weapon_is_concentration_buff(self):
        spell = _spell("Magic Weapon")
        assert spell.concentration is True
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 bonus action"
        assert spell.range == "touch"
        assert spell.duration == "up to 1 hour"

    def test_protection_from_poison_is_1_hour_no_concentration(self):
        spell = _spell("Protection from Poison")
        # PHB: Protection from Poison lasts 1 hour with NO concentration.
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "1 hour"
        assert spell.range == "touch"

    def test_rope_trick_is_concentration_extradimensional(self):
        spell = _spell("Rope Trick")
        assert spell.concentration is True
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "touch"
        assert spell.duration == "up to 1 hour"

    def test_warding_bond_is_1_hour_no_concentration(self):
        spell = _spell("Warding Bond")
        # PHB signature: Warding Bond lasts 1 hour with NO concentration
        # (the bond persists; only ends early if HP/separation conditions met).
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "1 hour"
        assert spell.range == "touch"


# --------------------------------------------------------------------------- #
# Effect resolution of the new spells
# --------------------------------------------------------------------------- #
class TestNewSpellResolution:
    def test_cordon_of_arrows_saves_and_fails(self):
        spell = _spell("Cordon of Arrows")
        # Made save: half damage (1d6 is 1-6; half is 0-3).
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3,
            casting_mod=3, target_save_total=30, spell_save_dc=14,
        )
        assert effect.made_save is True
        assert 0 <= effect.damage <= 6
        # Failed save: full damage.
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3,
            casting_mod=3, target_save_total=2, spell_save_dc=14,
        )
        assert effect.made_save is False
        assert 1 <= effect.damage <= 6
        assert effect.half_damage is False
        assert effect.damage_type == "piercing"

    @pytest.mark.parametrize(
        "name, save_ability",
        [
            ("Gust of Wind", "str"),
            ("Enthrall", "wis"),
            ("Zone of Truth", "cha"),
        ],
    )
    def test_save_debuff_spell_resolves(self, name, save_ability):
        spell = _spell(name)
        assert spell.save_ability == save_ability
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3,
            casting_mod=3, target_save_total=30, spell_save_dc=14,
        )
        assert effect.made_save is True
        assert effect.damage == 0
        assert "save" in effect.description

    def test_prayer_of_healing_heals(self):
        spell = _spell("Prayer of Healing")
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3, casting_mod=3,
        )
        # 2d8 healing = 2-16 (the +spellcasting mod is caster-dependent and
        # lives in the description; healing_bonus is 0 here).
        assert 2 <= effect.healing <= 16
        assert effect.damage == 0
        assert "restores" in effect.description

    @pytest.mark.parametrize(
        "name",
        [
            "Alter Self",
            "Animal Messenger",
            "Arcane Lock",
            "Beast Sense",
            "Continual Flame",
            "Find Steed",
            "Find Traps",
            "Gentle Repose",
            "Locate Object",
            "Magic Mouth",
            "Magic Weapon",
            "Protection from Poison",
            "Rope Trick",
            "Warding Bond",
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
# Upcasting sanity (Cordon of Arrows damage, Prayer of Healing healing)
# --------------------------------------------------------------------------- #
class TestUpcasting:
    def test_cordon_of_arrows_upcasts_1d6_per_level(self):
        spell = _spell("Cordon of Arrows")
        assert spell.damage_dice_count == 1
        assert spell.at_higher_levels_dice == 1
        # At slot 4 (2 levels above base), dice count = 1 + 2*1 = 3.
        extra_levels = 2
        upcast_count = spell.damage_dice_count + spell.at_higher_levels_dice * extra_levels
        assert upcast_count == 3

    def test_prayer_of_healing_upcasts_1d8_per_level(self):
        spell = _spell("Prayer of Healing")
        assert spell.healing_dice_count == 2
        assert spell.at_higher_levels_dice == 1
        # At slot 4 (2 levels above base), dice count = 2 + 2*1 = 4.
        extra_levels = 2
        upcast_count = spell.healing_dice_count + spell.at_higher_levels_dice * extra_levels
        assert upcast_count == 4

    def test_cordon_of_arrows_roll_damage_at_upcast(self):
        """Upcasting the damage roll grows by the configured dice count."""
        spell = _spell("Cordon of Arrows")
        # Base slot: 1d6 = 1-6.
        base = spell.roll_damage(caster_level=5, slot_level=2)
        assert 1 <= base <= 6
        # Slot 4: 3d6 = 3-18.
        upcast = spell.roll_damage(caster_level=5, slot_level=4)
        assert 3 <= upcast <= 18

    def test_prayer_of_healing_roll_healing_at_upcast(self):
        """Upcasting the healing roll grows by the configured dice count."""
        spell = _spell("Prayer of Healing")
        # Base slot: 2d8 = 2-16.
        base = spell.roll_healing(caster_level=5, slot_level=2)
        assert 2 <= base <= 16
        # Slot 4: 4d8 = 4-32.
        upcast = spell.roll_healing(caster_level=5, slot_level=4)
        assert 4 <= upcast <= 32
