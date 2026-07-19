"""
Tests for the PHB CANTRIP-TIER COMPLETION — 15 iconic PHB cantrips added to
bring the cantrip tier (level 0) to full Player's Handbook coverage
(14 -> 29; catalogue 312 -> 327).

This finishes the catalogue-wide "PHB completeness" effort at the LAST
remaining tier. The ten leveled tiers (1-9) were already PHB-complete; this
run adds every remaining PHB cantrip so **every Player's Handbook cantrip is
now registered** (level 0: 14 -> 29; PHB has 27, plus our 2 non-PHB
cantrips Toll the Dead [XGE] and Mind Sliver [Tasha's]). With this, **ALL
ELEVEN TIERS (cantrips + levels 1-9) are now PHB-complete** — the catalogue-
wide effort is complete at every tier.

Mirrors the level-1 / level-2 / level-3 / level-4 / level-5 / level-6
PHB-completeness expansion test files.

The 15 additions (grouped by resolution path):
- Attack-roll cantrip (damage, scales at 5/11/17): Produce Flame (conjuration,
  1d8 fire, thrown 30 ft), Thorn Whip (transmutation, 1d6 piercing, 30 ft,
  pulls target 10 ft).
- Utility / buff cantrip (no dice modelled, effect-in-description): Blade Ward
  (abjuration, self, weapon-damage resistance 1 round), Dancing Lights
  (evocation, concentration), Druidcraft (transmutation, minor nature
  effects), Friends (enchantment, hostile-after), Guidance (divination,
  concentration, +1d4 ability check), Mending (transmutation, repair, M),
  Message (transmutation, 120 ft whisper, M), Prestidigitation
  (transmutation, minor magic), Resistance (abjuration, concentration, +1d4
  save, M), Shillelagh (transmutation, bonus action, weapon buff, M), Spare
  the Dying (necromancy, stabilize), Thaumaturgy (transmutation, minor
  miracle), True Strike (divination, concentration, next attack advantage).

Coverage mirrors test_spell_level5_completion.py:
- Registry distribution (level 0 grew 14 -> 29; catalogue 312 -> 327; every
  leveled tier untouched at its PHB floor — so all ELEVEN tiers are now
  PHB-complete).
- Registration shape for every new cantrip (name, level, school) — parametrized.
- Per-spell mechanical correctness (attack roll, damage dice, concentration,
  range, material components, casting times).
- Effect resolution for the attack-roll cantrips (Produce Flame + Thorn Whip
  hit/miss/scaling) and the utility "takes effect" path for all 13 utility
  cantrips.
- Cantrip scaling math: cantrip_dice_multiplier identity + real roll_damage
  growth for both damage cantrips at caster levels 1/5/11/17.
"""
import pytest

from app.engine.spells import (
    Spell,
    SpellSchool,
    SPELL_REGISTRY,
    cantrip_dice_multiplier,
    get_spell,
    resolve_spell_effect,
)


def _spell(name: str) -> Spell:
    """Look up a spell by name/id and assert it is registered."""
    spell = get_spell(name)
    assert spell is not None, f"{name!r} should be registered"
    return spell


# --------------------------------------------------------------------------- #
# Registry distribution + cantrip-tier growth
# --------------------------------------------------------------------------- #
class TestRegistryShape:
    def test_total_spell_count_grew(self):
        # Was 312 before this completion; now 327.
        assert len(SPELL_REGISTRY) >= 327

    def test_cantrip_tier_grew(self):
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        # Cantrip tier grew 14 -> 29 (PHB 27 + Toll the Dead + Mind Sliver).
        assert by_level[0] >= 29, (
            f"Cantrip tier has only {by_level[0]} spells (expected >=29)"
        )

    def test_all_eleven_tiers_now_phb_complete(self):
        """This is the milestone assertion: EVERY tier (cantrips + levels 1-9)
        is at its PHB-complete floor after this run. The catalogue-wide 'PHB
        completeness' effort is now finished at all eleven tiers."""
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        assert by_level[0] >= 27   # PHB-complete (THIS run)
        assert by_level[1] >= 53   # PHB-complete
        assert by_level[2] >= 55   # PHB-complete
        assert by_level[3] >= 39   # PHB-complete
        assert by_level[4] >= 30   # PHB-complete
        assert by_level[5] >= 39   # PHB-complete
        assert by_level[6] >= 31   # PHB-complete
        assert by_level[7] >= 18   # PHB-complete
        assert by_level[8] >= 18   # PHB-complete
        assert by_level[9] >= 15   # PHB-complete

    def test_no_duplicate_spell_names_in_registry(self):
        """Every spell must have a unique name (no dict-key collisions)."""
        names = [s.name for s in SPELL_REGISTRY.values()]
        assert len(names) == len(set(names)), "Duplicate spell names detected"


# --------------------------------------------------------------------------- #
# Registration shape — every new cantrip at its correct level and school
# --------------------------------------------------------------------------- #
NEW_SPELLS: list[tuple[str, int, SpellSchool]] = [
    # Attack-roll cantrip (damage)
    ("Produce Flame", 0, SpellSchool.CONJURATION),
    ("Thorn Whip", 0, SpellSchool.TRANSMUTATION),
    # Utility / buff cantrip
    ("Blade Ward", 0, SpellSchool.ABJURATION),
    ("Dancing Lights", 0, SpellSchool.EVOCATION),
    ("Druidcraft", 0, SpellSchool.TRANSMUTATION),
    ("Friends", 0, SpellSchool.ENCHANTMENT),
    ("Guidance", 0, SpellSchool.DIVINATION),
    ("Mending", 0, SpellSchool.TRANSMUTATION),
    ("Message", 0, SpellSchool.TRANSMUTATION),
    ("Prestidigitation", 0, SpellSchool.TRANSMUTATION),
    ("Resistance", 0, SpellSchool.ABJURATION),
    ("Shillelagh", 0, SpellSchool.TRANSMUTATION),
    ("Spare the Dying", 0, SpellSchool.NECROMANCY),
    ("Thaumaturgy", 0, SpellSchool.TRANSMUTATION),
    ("True Strike", 0, SpellSchool.DIVINATION),
]


@pytest.mark.parametrize("name, level, school", NEW_SPELLS)
def test_new_cantrip_registered(name, level, school):
    spell = _spell(name)
    assert spell.level == level
    assert spell.school == school
    assert spell.is_cantrip is True


def test_new_cantrip_count_matches_plan():
    """All 15 planned new cantrips are registered."""
    assert len(NEW_SPELLS) == 15
    for name, _, _ in NEW_SPELLS:
        assert get_spell(name) is not None, f"{name!r} missing from registry"


def test_new_cantrip_ids_are_stable():
    """Each cantrip's id derives cleanly from its name (no collisions)."""
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
# Per-spell mechanical correctness — attack-roll cantrip (damage)
# --------------------------------------------------------------------------- #
class TestDamageCantripMechanics:
    def test_produce_flame_is_attack_roll_fire_with_thrown_range(self):
        spell = _spell("Produce Flame")
        assert spell.school == SpellSchool.CONJURATION
        # PHB: ranged spell attack (thrown 30 ft) for 1d8 fire.
        assert spell.requires_attack_roll is True
        assert spell.save_ability is None
        assert spell.damage_dice_count == 1 and spell.damage_dice_sides == 8
        assert spell.damage_type == "fire"
        assert spell.deals_damage is True
        # Cantrips do not consume slots / do not upcast.
        assert spell.at_higher_levels_dice == 0
        assert spell.concentration is False
        assert spell.ritual is False
        # Light radius + thrown attack documented in the description.
        assert "bright light" in spell.description.lower()
        assert "thrown" in spell.description.lower()
        assert "thrown 30 feet" in spell.range

    def test_thorn_whip_is_melee_spell_attack_piercing_with_pull(self):
        spell = _spell("Thorn Whip")
        assert spell.school == SpellSchool.TRANSMUTATION
        # PHB: melee spell attack, 1d6 piercing, pull up to 10 ft.
        assert spell.requires_attack_roll is True
        assert spell.save_ability is None
        assert spell.damage_dice_count == 1 and spell.damage_dice_sides == 6
        assert spell.damage_type == "piercing"
        assert spell.deals_damage is True
        assert spell.at_higher_levels_dice == 0
        assert spell.concentration is False
        assert spell.range == "30 feet"
        # The 10-foot pull rider is documented, not dice-modelled.
        assert "pull" in spell.description.lower()
        assert "10 feet" in spell.description.lower()
        # Material component per PHB.
        assert spell.material_description == "the stem of a plant with thorns"


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness — utility / buff cantrip
# --------------------------------------------------------------------------- #
class TestUtilityCantripMechanics:
    def test_blade_ward_is_self_abjuration_one_round(self):
        spell = _spell("Blade Ward")
        assert spell.school == SpellSchool.ABJURATION
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.requires_attack_roll is False
        assert spell.save_ability is None
        assert spell.casting_time == "1 action"
        assert spell.range == "self"
        assert spell.duration == "1 round"
        # Weapon-damage resistance documented.
        desc = spell.description.lower()
        assert "resistance" in desc
        assert "weapon" in desc

    def test_dancing_lights_is_concentration_evocation(self):
        spell = _spell("Dancing Lights")
        assert spell.school == SpellSchool.EVOCATION
        # PHB: concentration, up to 1 minute; range 120 feet.
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.range == "120 feet"
        assert spell.duration == "up to 1 minute"
        assert spell.material_description  # PHB material component present
        assert spell.casting_time == "1 action"

    def test_druidcraft_is_transmutation_utility(self):
        spell = _spell("Druidcraft")
        assert spell.school == SpellSchool.TRANSMUTATION
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.requires_attack_roll is False
        assert spell.save_ability is None
        assert spell.range == "30 feet"
        assert spell.ritual is False

    def test_friends_is_enchantment_self_no_concentration_hostile(self):
        spell = _spell("Friends")
        assert spell.school == SpellSchool.ENCHANTMENT
        # PHB: NOT concentration; the post-spell hostility is the trade-off.
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.range == "self"
        assert spell.duration == "1 minute"
        assert spell.material_description  # makeup material component
        # The "becomes hostile" rider is documented (effect-in-description).
        assert "hostile" in spell.description.lower()

    def test_guidance_is_concentration_divination_touch(self):
        spell = _spell("Guidance")
        assert spell.school == SpellSchool.DIVINATION
        # PHB: concentration, +1d4 ability check.
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.requires_attack_roll is False
        assert spell.save_ability is None
        assert spell.range == "touch"
        assert spell.duration == "up to 1 minute"
        assert "1d4" in spell.description
        assert "ability check" in spell.description.lower()

    def test_mending_is_transmutation_touch_with_material(self):
        spell = _spell("Mending")
        assert spell.school == SpellSchool.TRANSMUTATION
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.range == "touch"
        assert spell.duration == "instantaneous"
        # PHB material component: two lodestones.
        assert spell.material_description == "two lodestones"

    def test_message_is_transmutation_120ft_with_material(self):
        spell = _spell("Message")
        assert spell.school == SpellSchool.TRANSMUTATION
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.range == "120 feet"
        assert spell.material_description == "a short piece of copper wire"
        assert spell.duration == "instantaneous"

    def test_prestidigitation_is_transmutation_utility(self):
        spell = _spell("Prestidigitation")
        assert spell.school == SpellSchool.TRANSMUTATION
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.range == "10 feet"
        # Long-lived minor effect (up to 1 hour).
        assert "1 hour" in spell.duration.lower()

    def test_resistance_is_concentration_abjuration_touch_with_material(self):
        spell = _spell("Resistance")
        assert spell.school == SpellSchool.ABJURATION
        # PHB: concentration, +1d4 saving throw.
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.requires_attack_roll is False
        assert spell.save_ability is None
        assert spell.range == "touch"
        assert spell.duration == "up to 1 minute"
        assert spell.material_description == "a miniature cloak"
        assert "1d4" in spell.description
        assert "saving throw" in spell.description.lower()

    def test_shillelagh_is_bonus_action_transmutation_weapon_buff(self):
        spell = _spell("Shillelagh")
        assert spell.school == SpellSchool.TRANSMUTATION
        # PHB: bonus action, 1-minute weapon buff (NOT concentration).
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.casting_time == "1 bonus action"
        assert spell.range == "touch"
        assert spell.duration == "1 minute"
        assert spell.material_description  # mistletoe + shamrock + club/staff
        # The d8/d10 weapon-damage upgrade is documented, not dice-modelled
        # (it modifies a weapon attack, not the spell itself).
        desc = spell.description.lower()
        assert "d8" in spell.description
        assert "spellcasting" in desc

    def test_spare_the_dying_is_necromancy_touch_stabilize(self):
        spell = _spell("Spare the Dying")
        assert spell.school == SpellSchool.NECROMANCY
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.requires_attack_roll is False
        assert spell.save_ability is None
        assert spell.range == "touch"
        assert spell.duration == "instantaneous"
        # The stabilize-on-0-HP effect is documented.
        assert "stable" in spell.description.lower()
        assert "0 hit points" in spell.description.lower()

    def test_thaumaturgy_is_transmutation_minor_miracle(self):
        spell = _spell("Thaumaturgy")
        assert spell.school == SpellSchool.TRANSMUTATION
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.range == "30 feet"
        assert spell.components == "V"  # verbal-only per PHB
        assert "1 minute" in spell.duration.lower()

    def test_true_strike_is_concentration_divination_advantage(self):
        spell = _spell("True Strike")
        assert spell.school == SpellSchool.DIVINATION
        # PHB: concentration, next attack roll has advantage.
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.requires_attack_roll is False
        assert spell.save_ability is None
        assert spell.range == "30 feet"
        assert spell.components == "S"  # somatic-only per PHB
        assert spell.duration == "1 round"
        assert "advantage" in spell.description.lower()


# --------------------------------------------------------------------------- #
# Effect resolution — attack-roll cantrips resolve via the engine
# --------------------------------------------------------------------------- #
class TestEffectResolution:
    def test_produce_flame_attacks_hit_and_miss(self):
        spell = _spell("Produce Flame")
        # Generous attack bonus vs low AC = reliable hit.
        hit = resolve_spell_effect(
            spell=spell, caster_level=1, proficiency_bonus=2,
            casting_mod=5, target_ac=10,
        )
        assert hit.hit is True
        assert hit.damage >= 1   # 1d8 fire
        assert hit.damage_type == "fire"
        # Impossibly high AC with low bonus = reliable miss.
        miss = resolve_spell_effect(
            spell=spell, caster_level=1, proficiency_bonus=2,
            casting_mod=0, target_ac=35,
        )
        assert miss.hit is False
        assert miss.damage == 0

    def test_produce_flame_can_crit(self):
        """A natural 20 doubles the damage. Force the d20 via repeated rolls —
        we just assert a hit ever produces a CRITICAL description at most."""
        spell = _spell("Produce Flame")
        crit_seen = False
        for _ in range(400):
            r = resolve_spell_effect(
                spell=spell, caster_level=1, proficiency_bonus=2,
                casting_mod=5, target_ac=10,
            )
            if r.hit and "CRITICAL" in r.description:
                crit_seen = True
                break
        # With 400 trials a natural 20 is overwhelmingly likely (1 - 0.95^400).
        assert crit_seen

    def test_produce_flame_scales_with_caster_level(self):
        spell = _spell("Produce Flame")
        # Caster level 1: 1d8 = 1-8.
        low = spell.roll_damage(caster_level=1)
        assert 1 <= low <= 8
        # Caster level 5: 2d8 = 2-16.
        mid = spell.roll_damage(caster_level=5)
        assert 2 <= mid <= 16
        # Caster level 17: 4d8 = 4-32.
        high = spell.roll_damage(caster_level=17)
        assert 4 <= high <= 32

    def test_thorn_whip_attacks_hit_and_miss(self):
        spell = _spell("Thorn Whip")
        hit = resolve_spell_effect(
            spell=spell, caster_level=1, proficiency_bonus=2,
            casting_mod=5, target_ac=10,
        )
        assert hit.hit is True
        assert hit.damage >= 1   # 1d6 piercing
        assert hit.damage_type == "piercing"
        miss = resolve_spell_effect(
            spell=spell, caster_level=1, proficiency_bonus=2,
            casting_mod=0, target_ac=35,
        )
        assert miss.hit is False
        assert miss.damage == 0

    def test_thorn_whip_scales_with_caster_level(self):
        spell = _spell("Thorn Whip")
        # Caster level 1: 1d6 = 1-6.
        low = spell.roll_damage(caster_level=1)
        assert 1 <= low <= 6
        # Caster level 11: 3d6 = 3-18.
        mid = spell.roll_damage(caster_level=11)
        assert 3 <= mid <= 18
        # Caster level 17: 4d6 = 4-24.
        high = spell.roll_damage(caster_level=17)
        assert 4 <= high <= 24

    @pytest.mark.parametrize(
        "name",
        [
            "Blade Ward",
            "Dancing Lights",
            "Druidcraft",
            "Friends",
            "Guidance",
            "Mending",
            "Message",
            "Prestidigitation",
            "Resistance",
            "Shillelagh",
            "Spare the Dying",
            "Thaumaturgy",
            "True Strike",
        ],
    )
    def test_utility_cantrip_resolves_cleanly(self, name):
        """All 13 utility cantrips take effect via the engine's utility path."""
        spell = _spell(name)
        effect = resolve_spell_effect(
            spell=spell, caster_level=1, proficiency_bonus=2, casting_mod=3,
        )
        assert effect.damage == 0 and effect.healing == 0
        assert "takes effect" in effect.description


# --------------------------------------------------------------------------- #
# Cantrip scaling math — the multiplier identity + real roll growth
# --------------------------------------------------------------------------- #
class TestCantripScaling:
    def test_cantrip_dice_multiplier_identity(self):
        assert cantrip_dice_multiplier(1) == 1
        assert cantrip_dice_multiplier(4) == 1
        assert cantrip_dice_multiplier(5) == 2
        assert cantrip_dice_multiplier(10) == 2
        assert cantrip_dice_multiplier(11) == 3
        assert cantrip_dice_multiplier(16) == 3
        assert cantrip_dice_multiplier(17) == 4
        assert cantrip_dice_multiplier(20) == 4

    def test_produce_flame_dice_multiply_at_each_tier(self):
        spell = _spell("Produce Flame")
        assert spell.damage_dice_count == 1 and spell.damage_dice_sides == 8
        # The static identity: count = base * multiplier.
        assert spell.damage_dice_count * cantrip_dice_multiplier(1) == 1
        assert spell.damage_dice_count * cantrip_dice_multiplier(5) == 2
        assert spell.damage_dice_count * cantrip_dice_multiplier(11) == 3
        assert spell.damage_dice_count * cantrip_dice_multiplier(17) == 4

    def test_thorn_whip_dice_multiply_at_each_tier(self):
        spell = _spell("Thorn Whip")
        assert spell.damage_dice_count == 1 and spell.damage_dice_sides == 6
        assert spell.damage_dice_count * cantrip_dice_multiplier(1) == 1
        assert spell.damage_dice_count * cantrip_dice_multiplier(5) == 2
        assert spell.damage_dice_count * cantrip_dice_multiplier(11) == 3
        assert spell.damage_dice_count * cantrip_dice_multiplier(17) == 4

    def test_produce_flame_roll_damage_grows_across_tiers(self):
        spell = _spell("Produce Flame")
        # Base (cl 1): 1d8. Tier 5: 2d8. Tier 11: 3d8. Tier 17: 4d8.
        assert 1 <= spell.roll_damage(caster_level=1) <= 8
        assert 2 <= spell.roll_damage(caster_level=5) <= 16
        assert 3 <= spell.roll_damage(caster_level=11) <= 24
        assert 4 <= spell.roll_damage(caster_level=17) <= 32

    def test_thorn_whip_roll_damage_grows_across_tiers(self):
        spell = _spell("Thorn Whip")
        # Base (cl 1): 1d6. Tier 5: 2d6. Tier 11: 3d6. Tier 17: 4d6.
        assert 1 <= spell.roll_damage(caster_level=1) <= 6
        assert 2 <= spell.roll_damage(caster_level=5) <= 12
        assert 3 <= spell.roll_damage(caster_level=11) <= 18
        assert 4 <= spell.roll_damage(caster_level=17) <= 24
