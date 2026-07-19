"""
Tests for the PHB level-3 spell COMPLETION — 26 iconic PHB level-3 spells added
to bring level 3 to full Player's Handbook coverage (13 → 39; catalogue
244 → 270).

This finishes the catalogue-wide "PHB completeness" effort at the mid-tier.
Levels 1, 2, 6, 7/8/9 were already PHB-complete; this run adds the remaining
iconic PHB 3rd-level spells so **every Player's Handbook 3rd-level spell is now
registered** (level 3: 13 → 39).

Mirrors the level-1 / level-2 / level-6 PHB-completeness expansions
(test_spell_level1_completion.py, test_spell_level2_completion.py,
test_spell_level6_completion.py) and the level-2 expansion.

The 26 additions (grouped by resolution path):
- Save-spell with damage: Glyph of Warding (Dex, 5d8, +1d8/slot, 1-hour cast).
- Save-debuff (no damage): Bestow Curse (Wis, touch), Slow (Wis, 40-ft cube),
  Sleet Storm (Dex, 40-ft cylinder).
- Attack-roll: Vampiric Touch (melee spell attack, 3d6 necrotic, heal half,
  +1d6/slot).
- Damage zone (auto-damage, no save): Wind Wall (3d8 bludgeoning wall).
- Utility / buff / ritual (20 spells): Animate Dead (1-min cast, 24-hour
  undead), Beacon of Hope (concentration, advantage Wis/death saves + max
  heal), Clairvoyance (ritual + concentration, 10-min cast, sensor), Conjure
  Animals (concentration, summon), Create Food and Water (instant), Crusader's
  Mantle (concentration, +1d4 radiant aura), Daylight (1-hour, NO
  concentration), Elemental Weapon (concentration, +1 weapon / +1d4 element),
  Feign Death (ritual, 1-hour trance), Gaseous Form (concentration, 1-hour),
  Plant Growth (instant overgrowth), Protection from Energy (concentration,
  resist element), Remove Curse (instant), Sending (instant message), Speak
  with Dead (10-min cast, 5 questions), Speak with Plants (concentration,
  10-min), Tiny Hut (ritual, 1-min cast, 8-hour dome, NO concentration),
  Tongues (1-hour, NO concentration), Water Breathing (ritual, 24-hour, NO
  concentration), Water Walk (ritual, 1-hour, NO concentration).

Coverage mirrors test_spell_level2_completion.py / test_spell_level6_completion.py:
- Registry distribution (level 3 grew 13 -> 39; catalogue 244 -> 270; PHB-
  complete tiers untouched at their floors).
- Registration shape for every new spell (name, level, school) — parametrized.
- Per-spell mechanical correctness (save ability, concentration, dice, flags).
- Effect resolution for the damage, save-debuff, attack-roll, damage-zone, and
  utility spells (all resolve without raising).
- Whole-registry no-duplicate-name guard + upcasting math (Glyph of Warding,
  Vampiric Touch; Wind Wall correctly has no upcast dice).
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
# Registry distribution + level-3 tier growth
# --------------------------------------------------------------------------- #
class TestRegistryShape:
    def test_total_spell_count_grew(self):
        # Was 244 before this completion; now 270.
        assert len(SPELL_REGISTRY) >= 270

    def test_level_3_tier_grew(self):
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        # Level 3 grew 13 -> 39 (full PHB coverage).
        assert by_level[3] >= 39, (
            f"Level 3 has only {by_level[3]} spells (expected >=39)"
        )

    def test_other_tiers_floor_intact(self):
        """This completion touches only level 3; every PHB-complete tier is
        at least its canonical minimum (floors are robust against other test
        modules that may register additional spells in the shared registry)."""
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        # The PHB-complete tiers are untouched (at their canonical floors).
        assert by_level[1] >= 53   # PHB-complete
        assert by_level[2] >= 55   # PHB-complete
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
    ("Glyph of Warding", 3, SpellSchool.ABJURATION),
    # Save-debuff (no damage)
    ("Bestow Curse", 3, SpellSchool.NECROMANCY),
    ("Slow", 3, SpellSchool.TRANSMUTATION),
    ("Sleet Storm", 3, SpellSchool.CONJURATION),
    # Attack-roll
    ("Vampiric Touch", 3, SpellSchool.NECROMANCY),
    # Damage zone (auto-damage, no save)
    ("Wind Wall", 3, SpellSchool.EVOCATION),
    # Utility / buff / ritual
    ("Animate Dead", 3, SpellSchool.NECROMANCY),
    ("Beacon of Hope", 3, SpellSchool.ABJURATION),
    ("Clairvoyance", 3, SpellSchool.DIVINATION),
    ("Conjure Animals", 3, SpellSchool.CONJURATION),
    ("Create Food and Water", 3, SpellSchool.CONJURATION),
    ("Crusader's Mantle", 3, SpellSchool.ABJURATION),
    ("Daylight", 3, SpellSchool.EVOCATION),
    ("Elemental Weapon", 3, SpellSchool.TRANSMUTATION),
    ("Feign Death", 3, SpellSchool.NECROMANCY),
    ("Gaseous Form", 3, SpellSchool.TRANSMUTATION),
    ("Plant Growth", 3, SpellSchool.TRANSMUTATION),
    ("Protection from Energy", 3, SpellSchool.ABJURATION),
    ("Remove Curse", 3, SpellSchool.ABJURATION),
    ("Sending", 3, SpellSchool.EVOCATION),
    ("Speak with Dead", 3, SpellSchool.NECROMANCY),
    ("Speak with Plants", 3, SpellSchool.TRANSMUTATION),
    ("Tiny Hut", 3, SpellSchool.ABJURATION),
    ("Tongues", 3, SpellSchool.DIVINATION),
    ("Water Breathing", 3, SpellSchool.TRANSMUTATION),
    ("Water Walk", 3, SpellSchool.TRANSMUTATION),
]


@pytest.mark.parametrize("name, level, school", NEW_SPELLS)
def test_new_spell_registered(name, level, school):
    spell = _spell(name)
    assert spell.level == level
    assert spell.school == school


def test_new_spell_count_matches_plan():
    """All 26 planned new spells are registered."""
    assert len(NEW_SPELLS) == 26
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
    def test_glyph_of_warding_is_dex_save_damage_with_upcast(self):
        spell = _spell("Glyph of Warding")
        assert spell.save_ability == "dex"
        assert spell.concentration is False  # instantaneous trap; no concentration
        assert spell.damage_dice_count == 5 and spell.damage_dice_sides == 8
        assert spell.damage_type == "acid"
        # +1d8 per slot level above 3rd.
        assert spell.at_higher_levels_dice == 1
        # PHB signature: Glyph of Warding takes 1 hour to cast (a trap, not a
        # combat spell).
        assert spell.casting_time == "1 hour"
        assert spell.range == "touch"
        assert spell.deals_damage is True
        assert spell.requires_attack_roll is False


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness — save-debuff (no damage)
# --------------------------------------------------------------------------- #
class TestSaveDebuffMechanics:
    def test_bestow_curse_is_wis_save_concentration_touch(self):
        spell = _spell("Bestow Curse")
        assert spell.save_ability == "wis"
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.range == "touch"
        assert spell.duration == "up to 1 minute"
        assert spell.casting_time == "1 action"
        assert spell.school == SpellSchool.NECROMANCY

    def test_slow_is_wis_save_concentration_40_ft_cube(self):
        spell = _spell("Slow")
        assert spell.save_ability == "wis"
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.range == "120 feet"
        assert spell.duration == "up to 1 minute"
        assert spell.school == SpellSchool.TRANSMUTATION

    def test_sleet_storm_is_dex_save_concentration(self):
        spell = _spell("Sleet Storm")
        assert spell.save_ability == "dex"
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.range == "150 feet"
        assert spell.duration == "up to 1 minute"
        assert spell.school == SpellSchool.CONJURATION


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness — attack-roll
# --------------------------------------------------------------------------- #
class TestAttackRollMechanics:
    def test_vampiric_touch_is_melee_spell_attack_with_upcast(self):
        spell = _spell("Vampiric Touch")
        assert spell.requires_attack_roll is True
        assert spell.concentration is True
        assert spell.damage_dice_count == 3 and spell.damage_dice_sides == 6
        assert spell.damage_type == "necrotic"
        # +1d6 per slot level above 3rd.
        assert spell.at_higher_levels_dice == 1
        assert spell.deals_damage is True
        assert spell.range == "self"  # melee spell attack
        assert spell.duration == "up to 1 minute"
        assert spell.school == SpellSchool.NECROMANCY


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness — damage zone (auto-damage, no save)
# --------------------------------------------------------------------------- #
class TestDamageZoneMechanics:
    def test_wind_wall_is_auto_damage_no_save_no_upcast(self):
        spell = _spell("Wind Wall")
        # PHB: Wind Wall deals 3d8 bludgeoning to creatures entering/starting
        # their turn in the wall — no attack roll, no save (auto-damage path,
        # like Spike Growth / Heat Metal).
        assert spell.requires_attack_roll is False
        assert spell.save_ability is None
        assert spell.damage_dice_count == 3 and spell.damage_dice_sides == 8
        assert spell.damage_type == "bludgeoning"
        assert spell.deals_damage is True
        assert spell.concentration is True
        # PHB: Wind Wall has no damage upcast (the wall grows, damage stays 3d8).
        assert spell.at_higher_levels_dice == 0
        assert spell.duration == "up to 1 minute"
        assert spell.school == SpellSchool.EVOCATION


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness — utility / buff / ritual
# --------------------------------------------------------------------------- #
class TestUtilityMechanics:
    def test_animate_dead_is_long_cast_no_concentration(self):
        spell = _spell("Animate Dead")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.heals is False
        # PHB signature: Animate Dead has a 1-minute casting time (ritual
        # animation; not usable mid-combat).
        assert spell.casting_time == "1 minute"
        assert spell.range == "10 feet"
        assert spell.duration == "instantaneous"
        assert spell.school == SpellSchool.NECROMANCY

    def test_beacon_of_hope_is_concentration_buff(self):
        spell = _spell("Beacon of Hope")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.heals is False
        assert spell.range == "30 feet"
        assert spell.duration == "up to 1 minute"
        assert spell.school == SpellSchool.ABJURATION

    def test_clairvoyance_is_ritual_and_concentration(self):
        spell = _spell("Clairvoyance")
        # PHB: Clairvoyance is BOTH a ritual AND concentration (the rare
        # overlap — usable out of combat but ends if you cast another
        # concentration spell).
        assert spell.ritual is True
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        # PHB signature: 10-minute casting time (ritual scrying).
        assert spell.casting_time == "10 minutes"
        assert spell.range == "1 mile"
        assert spell.duration == "up to 10 minutes"
        assert spell.school == SpellSchool.DIVINATION

    def test_conjure_animals_is_concentration_summon(self):
        spell = _spell("Conjure Animals")
        assert spell.concentration is True
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "60 feet"
        assert spell.duration == "up to 1 hour"
        assert spell.school == SpellSchool.CONJURATION

    def test_create_food_and_water_is_instantaneous(self):
        spell = _spell("Create Food and Water")
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "instantaneous"
        assert spell.range == "30 feet"
        assert spell.school == SpellSchool.CONJURATION

    def test_crusaders_mantle_is_concentration_aura(self):
        spell = _spell("Crusader's Mantle")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "self"
        assert spell.duration == "up to 1 minute"
        assert spell.school == SpellSchool.ABJURATION

    def test_daylight_is_1_hour_no_concentration(self):
        spell = _spell("Daylight")
        # PHB signature: Daylight lasts 1 hour with NO concentration (a
        # light spell, not a concentration effect).
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "1 hour"
        assert spell.range == "60 feet"
        assert spell.school == SpellSchool.EVOCATION

    def test_elemental_weapon_is_concentration_buff(self):
        spell = _spell("Elemental Weapon")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "touch"
        assert spell.duration == "up to 1 hour"
        assert spell.school == SpellSchool.TRANSMUTATION

    def test_feign_death_is_ritual_long_cast_no_concentration(self):
        spell = _spell("Feign Death")
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        # PHB signature: 1-minute casting time (ritual trance).
        assert spell.casting_time == "1 minute"
        assert spell.range == "touch"
        assert spell.duration == "1 hour"
        assert spell.school == SpellSchool.NECROMANCY

    def test_gaseous_form_is_concentration_buff(self):
        spell = _spell("Gaseous Form")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "touch"
        assert spell.duration == "up to 1 hour"
        assert spell.school == SpellSchool.TRANSMUTATION

    def test_plant_growth_is_instantaneous_overgrowth(self):
        spell = _spell("Plant Growth")
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "150 feet"
        assert spell.school == SpellSchool.TRANSMUTATION

    def test_protection_from_energy_is_concentration_buff(self):
        spell = _spell("Protection from Energy")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "touch"
        assert spell.duration == "up to 1 hour"
        assert spell.school == SpellSchool.ABJURATION

    def test_remove_curse_is_instantaneous(self):
        spell = _spell("Remove Curse")
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "instantaneous"
        assert spell.range == "touch"
        assert spell.school == SpellSchool.ABJURATION

    def test_sending_is_instantaneous_unlimited_range(self):
        spell = _spell("Sending")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "instantaneous"
        # PHB signature: Sending crosses any distance, even to another plane.
        assert spell.range == "unlimited"
        assert spell.casting_time == "1 action"
        assert spell.school == SpellSchool.EVOCATION

    def test_speak_with_dead_is_10_min_cast(self):
        spell = _spell("Speak with Dead")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        # PHB signature: 10-minute casting time (ritual questioning; 5
        # questions, 10-day cooldown on the same corpse).
        assert spell.casting_time == "10 minutes"
        assert spell.range == "10 feet"
        assert spell.duration == "instantaneous"
        assert spell.school == SpellSchool.NECROMANCY

    def test_speak_with_plants_is_concentration(self):
        spell = _spell("Speak with Plants")
        # PHB: Speak with Plants requires concentration (10-minute duration),
        # and is NOT a ritual.
        assert spell.concentration is True
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "self (30-foot radius)"
        assert spell.duration == "10 minutes"
        assert spell.school == SpellSchool.TRANSMUTATION

    def test_tiny_hut_is_ritual_no_concentration_long_duration(self):
        spell = _spell("Tiny Hut")
        # PHB signature: Tiny Hut is a ritual with an 8-hour duration and NO
        # concentration (the dome persists for the rest).
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        # PHB signature: 1-minute casting time (ritual casting).
        assert spell.casting_time == "1 minute"
        assert spell.range == "self"
        assert spell.duration == "8 hours"
        assert spell.school == SpellSchool.ABJURATION

    def test_tongues_is_1_hour_no_concentration(self):
        spell = _spell("Tongues")
        # PHB signature: Tongues lasts 1 hour with NO concentration.
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "1 hour"
        assert spell.range == "touch"
        assert spell.school == SpellSchool.DIVINATION

    def test_water_breathing_is_ritual_long_duration_no_concentration(self):
        spell = _spell("Water Breathing")
        # PHB signature: Water Breathing is a ritual with a 24-hour duration
        # and NO concentration.
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "24 hours"
        assert spell.range == "30 feet"
        assert spell.school == SpellSchool.TRANSMUTATION

    def test_water_walk_is_ritual_no_concentration(self):
        spell = _spell("Water Walk")
        # PHB signature: Water Walk is a ritual with a 1-hour duration and NO
        # concentration.
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "1 hour"
        assert spell.range == "30 feet"
        assert spell.school == SpellSchool.TRANSMUTATION


# --------------------------------------------------------------------------- #
# Effect resolution of the new spells
# --------------------------------------------------------------------------- #
class TestNewSpellResolution:
    def _force_d20(self, monkeypatch, face: int):
        """Patch the d20 used by resolve_spell_effect to a fixed die face.

        ``resolve_spell_effect`` calls ``roll_d20(spell_attack)`` from the
        spells module, so we patch the name as imported there to make attack
        outcomes deterministic (avoids flaky natural-1 / low-roll misses).
        """
        from app.engine import spells as spells_module
        from app.engine.dice import RollResult

        def _fixed(modifier: int = 0, advantage: bool = False,
                   disadvantage: bool = False) -> RollResult:
            return RollResult(
                rolls=[face], modifier=modifier,
                total=face + modifier, description=f"d20 {modifier:+d}",
            )

        monkeypatch.setattr(spells_module, "roll_d20", _fixed)

    def test_glyph_of_warding_saves_and_fails(self):
        spell = _spell("Glyph of Warding")
        # Made save: half damage (5d8 is 5-40; half is 2-20).
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3,
            casting_mod=3, target_save_total=30, spell_save_dc=14,
        )
        assert effect.made_save is True
        assert 2 <= effect.damage <= 20
        assert effect.half_damage is True
        # Failed save: full damage.
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3,
            casting_mod=3, target_save_total=2, spell_save_dc=14,
        )
        assert effect.made_save is False
        assert 5 <= effect.damage <= 40
        assert effect.half_damage is False
        assert effect.damage_type == "acid"

    @pytest.mark.parametrize(
        "name, save_ability",
        [
            ("Bestow Curse", "wis"),
            ("Slow", "wis"),
            ("Sleet Storm", "dex"),
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

    def test_vampiric_touch_resolves_on_attack_roll(self, monkeypatch):
        spell = _spell("Vampiric Touch")
        assert spell.requires_attack_roll is True
        # spell_attack = proficiency 3 + casting_mod 3 = +6.
        # Hit (die 15, +6 = 21 vs AC 10): 3d6 (3-18) necrotic.
        self._force_d20(monkeypatch, 15)
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3,
            casting_mod=3, target_ac=10, spell_save_dc=14,
        )
        assert effect.hit is True
        assert effect.damage_type == "necrotic"
        assert 3 <= effect.damage <= 18  # 3d6 necrotic
        # Miss (die 2, +6 = 8 vs AC 30): not a natural 1/20, below AC -> miss.
        self._force_d20(monkeypatch, 2)
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3,
            casting_mod=3, target_ac=30, spell_save_dc=14,
        )
        assert effect.hit is False

    def test_wind_wall_resolves_as_auto_damage(self):
        spell = _spell("Wind Wall")
        # Auto-damage path (no attack roll, no save): like Spike Growth /
        # Heat Metal / Magic Missile — "deals N damage automatically".
        assert spell.requires_attack_roll is False
        assert spell.save_ability is None
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3, casting_mod=3,
        )
        assert 3 <= effect.damage <= 24  # 3d8 bludgeoning
        assert effect.damage_type == "bludgeoning"
        assert effect.made_save is None
        assert effect.hit is None

    @pytest.mark.parametrize(
        "name",
        [
            "Animate Dead",
            "Beacon of Hope",
            "Clairvoyance",
            "Conjure Animals",
            "Create Food and Water",
            "Crusader's Mantle",
            "Daylight",
            "Elemental Weapon",
            "Feign Death",
            "Gaseous Form",
            "Plant Growth",
            "Protection from Energy",
            "Remove Curse",
            "Sending",
            "Speak with Dead",
            "Speak with Plants",
            "Tiny Hut",
            "Tongues",
            "Water Breathing",
            "Water Walk",
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
# Upcasting sanity (Glyph of Warding damage, Vampiric Touch damage, Wind Wall
# correctly has no upcast)
# --------------------------------------------------------------------------- #
class TestUpcasting:
    def test_glyph_of_warding_upcasts_1d8_per_level(self):
        spell = _spell("Glyph of Warding")
        assert spell.damage_dice_count == 5
        assert spell.at_higher_levels_dice == 1
        # At slot 5 (2 levels above base), dice count = 5 + 2*1 = 7.
        extra_levels = 2
        upcast_count = spell.damage_dice_count + spell.at_higher_levels_dice * extra_levels
        assert upcast_count == 7

    def test_vampiric_touch_upcasts_1d6_per_level(self):
        spell = _spell("Vampiric Touch")
        assert spell.damage_dice_count == 3
        assert spell.at_higher_levels_dice == 1
        # At slot 5 (2 levels above base), dice count = 3 + 2*1 = 5.
        extra_levels = 2
        upcast_count = spell.damage_dice_count + spell.at_higher_levels_dice * extra_levels
        assert upcast_count == 5

    def test_wind_wall_has_no_damage_upcast(self):
        spell = _spell("Wind Wall")
        # PHB: Wind Wall's damage does NOT scale with slot level (the wall
        # grows, but damage stays 3d8). This is the deliberate exception to the
        # upcast-everything convention.
        assert spell.damage_dice_count == 3
        assert spell.at_higher_levels_dice == 0
        # At slot 5 (2 levels above base), dice count = 3 + 2*0 = 3 (unchanged).
        extra_levels = 2
        upcast_count = spell.damage_dice_count + spell.at_higher_levels_dice * extra_levels
        assert upcast_count == 3

    def test_glyph_of_warding_roll_damage_at_upcast(self):
        """Upcasting the damage roll grows by the configured dice count."""
        spell = _spell("Glyph of Warding")
        # Base slot: 5d8 = 5-40.
        base = spell.roll_damage(caster_level=5, slot_level=3)
        assert 5 <= base <= 40
        # Slot 5: 7d8 = 7-56.
        upcast = spell.roll_damage(caster_level=5, slot_level=5)
        assert 7 <= upcast <= 56

    def test_vampiric_touch_roll_damage_at_upcast(self):
        """Upcasting the damage roll grows by the configured dice count."""
        spell = _spell("Vampiric Touch")
        # Base slot: 3d6 = 3-18.
        base = spell.roll_damage(caster_level=5, slot_level=3)
        assert 3 <= base <= 18
        # Slot 5: 5d6 = 5-30.
        upcast = spell.roll_damage(caster_level=5, slot_level=5)
        assert 5 <= upcast <= 30

    def test_wind_wall_roll_damage_is_flat_across_slots(self):
        """Wind Wall deals the same 3d8 regardless of slot level (no upcast)."""
        spell = _spell("Wind Wall")
        base = spell.roll_damage(caster_level=5, slot_level=3)
        upcast = spell.roll_damage(caster_level=5, slot_level=5)
        # Both are 3d8 rolls (3-24); the distribution is identical because the
        # dice count doesn't change.
        assert 3 <= base <= 24
        assert 3 <= upcast <= 24
        assert spell.at_higher_levels_dice == 0
