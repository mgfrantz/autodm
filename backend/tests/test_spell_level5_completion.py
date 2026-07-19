"""
Tests for the PHB level-5 spell COMPLETION — 26 iconic PHB level-5 spells added
to bring level 5 to full Player's Handbook coverage (13 -> 39; catalogue
286 -> 312).

This finishes the catalogue-wide "PHB completeness" effort at the 5th-level
tier — the LAST leveled tier with room to grow. Levels 1, 2, 3, 4, 6, 7/8/9
were already PHB-complete; this run adds every remaining iconic PHB 5th-level
spell so **every Player's Handbook 5th-level spell is now registered**
(level 5: 13 -> 39). With this, **all ten leveled tiers (1-9) are now
PHB-complete** — the catalogue-wide effort is complete at the leveled tiers.

Mirrors the level-1 / level-2 / level-3 / level-4 / level-6 PHB-completeness
expansion test files.

The 26 additions (grouped by resolution path):
- Save-spell with damage: Destructive Wave (Con, 5d8 thunder + prone, +1d8/slot),
  Conjure Volley (Dex, 8d8 piercing, 40-ft cone, +1d8/slot).
- Save-debuff (no damage): Contagion (Con, touch, 7-day disease sequence),
  Modify Memory (Wis, concentration, charm + memory edit), Telekinesis (Str,
  concentration, push/grapple), Planar Binding (Cha, concentration, 1-hour
  cast, 24-hour bind), Geas (Wis, no concentration, 30-day, 5d10 psychic
  rider), Seeming (Cha, no concentration, 8-hour disguise).
- Utility / buff / ritual (18 spells): Awaken (8-hour cast, 1000gp agate),
  Banishing Smite (concentration smite, 5d10 + banish), Circle of Power
  (concentration, advantage vs spells aura), Commune (ritual, 3 yes/no),
  Commune with Nature (ritual, 3-mile knowledge), Conjure Elemental
  (concentration summon), Contact Other Plane (ritual, DC 15 self-risk
  documented), Creation (illusion, 1-min cast), Dispel Evil and Good
  (concentration, abjuration aegis), Dream (concentration, dream messaging),
  Hallow (24-hour cast, sanctuary), Legend Lore (10-min cast, lore),
  Passwall (transmutation, 1-hour passage), Raise Dead (1-hour cast, 500gp
  diamond), Reincarnate (1-hour cast, 1000gp oils), Swift Quiver
  (concentration, bonus-action double fire), Teleportation Circle (1-min
  cast, teleport to known circle), Tree Stride (concentration, tree teleport).

Coverage mirrors test_spell_level4_completion.py:
- Registry distribution (level 5 grew 13 -> 39; catalogue 286 -> 312; every
  other PHB-complete tier untouched at its floor — so all ten tiers are now
  PHB-complete).
- Registration shape for every new spell (name, level, school) — parametrized.
- Per-spell mechanical correctness (save ability, concentration, dice, flags).
- Effect resolution for the damage, save-debuff, and utility spells (all
  resolve without raising).
- Whole-registry no-duplicate-name guard + upcasting math (Destructive Wave
  +1d8, Conjure Volley +1d8).
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
# Registry distribution + level-5 tier growth
# --------------------------------------------------------------------------- #
class TestRegistryShape:
    def test_total_spell_count_grew(self):
        # Was 286 before this completion; now 312.
        assert len(SPELL_REGISTRY) >= 312

    def test_level_5_tier_grew(self):
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        # Level 5 grew 13 -> 39 (full PHB coverage).
        assert by_level[5] >= 39, (
            f"Level 5 has only {by_level[5]} spells (expected >=39)"
        )

    def test_all_ten_leveled_tiers_now_phb_complete(self):
        """This is the milestone assertion: every leveled tier (1-9) is at its
        PHB-complete floor after this run."""
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        assert by_level[1] >= 53   # PHB-complete
        assert by_level[2] >= 55   # PHB-complete
        assert by_level[3] >= 39   # PHB-complete
        assert by_level[4] >= 30   # PHB-complete
        assert by_level[5] >= 39   # PHB-complete (THIS run)
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
    ("Destructive Wave", 5, SpellSchool.EVOCATION),
    ("Conjure Volley", 5, SpellSchool.CONJURATION),
    # Save-debuff (no damage)
    ("Contagion", 5, SpellSchool.NECROMANCY),
    ("Modify Memory", 5, SpellSchool.ENCHANTMENT),
    ("Telekinesis", 5, SpellSchool.TRANSMUTATION),
    ("Planar Binding", 5, SpellSchool.ABJURATION),
    ("Geas", 5, SpellSchool.ENCHANTMENT),
    ("Seeming", 5, SpellSchool.TRANSMUTATION),
    # Utility / buff / ritual
    ("Awaken", 5, SpellSchool.TRANSMUTATION),
    ("Banishing Smite", 5, SpellSchool.ABJURATION),
    ("Circle of Power", 5, SpellSchool.ABJURATION),
    ("Commune", 5, SpellSchool.DIVINATION),
    ("Commune with Nature", 5, SpellSchool.DIVINATION),
    ("Conjure Elemental", 5, SpellSchool.CONJURATION),
    ("Contact Other Plane", 5, SpellSchool.DIVINATION),
    ("Creation", 5, SpellSchool.ILLUSION),
    ("Dispel Evil and Good", 5, SpellSchool.ABJURATION),
    ("Dream", 5, SpellSchool.ILLUSION),
    ("Hallow", 5, SpellSchool.EVOCATION),
    ("Legend Lore", 5, SpellSchool.DIVINATION),
    ("Passwall", 5, SpellSchool.TRANSMUTATION),
    ("Raise Dead", 5, SpellSchool.NECROMANCY),
    ("Reincarnate", 5, SpellSchool.TRANSMUTATION),
    ("Swift Quiver", 5, SpellSchool.TRANSMUTATION),
    ("Teleportation Circle", 5, SpellSchool.CONJURATION),
    ("Tree Stride", 5, SpellSchool.CONJURATION),
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
    def test_destructive_wave_is_con_save_thunder_with_upcast(self):
        spell = _spell("Destructive Wave")
        assert spell.save_ability == "con"
        # PHB: 5d8 thunder (+ 5d8 radiant rider documented in description).
        assert spell.concentration is False
        assert spell.damage_dice_count == 5 and spell.damage_dice_sides == 8
        assert spell.damage_type == "thunder"
        # +1d8 thunder per slot level above 5th (PHB p.154).
        assert spell.at_higher_levels_dice == 1
        assert spell.deals_damage is True
        assert spell.requires_attack_roll is False
        assert spell.range == "self (10-foot radius)"
        assert spell.duration == "instantaneous"
        assert spell.school == SpellSchool.EVOCATION
        # The radiant rider + knock-prone are documented, not dice-modeled.
        assert "radiant" in spell.description.lower()
        assert "prone" in spell.description.lower()

    def test_conjure_volley_is_dex_save_piercing_with_upcast(self):
        spell = _spell("Conjure Volley")
        assert spell.save_ability == "dex"
        assert spell.concentration is False
        assert spell.damage_dice_count == 8 and spell.damage_dice_sides == 8
        assert spell.damage_type == "piercing"
        # +1d8 per slot level above 5th (PHB p.69).
        assert spell.at_higher_levels_dice == 1
        assert spell.deals_damage is True
        assert spell.requires_attack_roll is False
        assert spell.range == "self (40-foot cone)"
        assert spell.duration == "instantaneous"
        assert spell.school == SpellSchool.CONJURATION


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness — save-debuff (no damage)
# --------------------------------------------------------------------------- #
class TestSaveDebuffMechanics:
    def test_contagion_is_con_save_touch_no_concentration(self):
        spell = _spell("Contagion")
        assert spell.save_ability == "con"
        # PHB: disease endures 7 days; not concentration-maintained.
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.requires_attack_roll is False
        assert spell.range == "touch"
        assert spell.duration == "7 days"
        assert spell.school == SpellSchool.NECROMANCY

    def test_modify_memory_is_wis_save_concentration_no_damage(self):
        spell = _spell("Modify Memory")
        assert spell.save_ability == "wis"
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.requires_attack_roll is False
        assert spell.range == "60 feet"
        assert spell.duration == "up to 1 minute"
        assert spell.school == SpellSchool.ENCHANTMENT

    def test_telekinesis_is_str_save_concentration_no_damage(self):
        spell = _spell("Telekinesis")
        assert spell.save_ability == "str"
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.requires_attack_roll is False
        assert spell.range == "60 feet"
        assert spell.duration == "up to 10 minutes"
        assert spell.school == SpellSchool.TRANSMUTATION

    def test_planar_binding_is_cha_save_concentration_long_cast(self):
        spell = _spell("Planar Binding")
        assert spell.save_ability == "cha"
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.requires_attack_roll is False
        # PHB signature: 1-hour casting time, 24-hour bound duration.
        assert spell.casting_time == "1 hour"
        assert spell.duration == "24 hours"
        assert spell.school == SpellSchool.ABJURATION

    def test_geas_is_wis_save_no_concentration_long_duration(self):
        spell = _spell("Geas")
        assert spell.save_ability == "wis"
        # PHB: 30-day geas is NOT concentration; the 5d10 psychic rider is
        # documented (effect-in-description convention).
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.duration == "30 days"
        assert spell.school == SpellSchool.ENCHANTMENT
        assert "5d10" in spell.description

    def test_seeming_is_cha_save_no_concentration_long_duration(self):
        spell = _spell("Seeming")
        assert spell.save_ability == "cha"
        # PHB: Seeming holds 8 hours with NO concentration (set illusion).
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.requires_attack_roll is False
        assert spell.range == "30 feet"
        assert spell.duration == "8 hours"
        assert spell.school == SpellSchool.TRANSMUTATION


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness — utility / buff / ritual
# --------------------------------------------------------------------------- #
class TestUtilityMechanics:
    def test_awaken_is_transmutation_with_long_cast(self):
        spell = _spell("Awaken")
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        # PHB signature: 8-hour casting time (ritual of awakening).
        assert spell.casting_time == "8 hours"
        assert spell.range == "touch"
        assert spell.duration == "instantaneous"
        assert spell.school == SpellSchool.TRANSMUTATION

    def test_banishing_smite_is_concentration_abjuration_spite(self):
        spell = _spell("Banishing Smite")
        # Paladin smite buff: the 5d10 force damage + banish rider fire on a
        # subsequent weapon hit, not on cast (effect-in-description).
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.requires_attack_roll is False
        assert spell.casting_time == "1 bonus action"
        assert spell.range == "self"
        assert spell.duration == "up to 1 minute"
        assert spell.school == SpellSchool.ABJURATION
        assert "5d10" in spell.description
        assert "banished" in spell.description.lower()

    def test_circle_of_power_is_concentration_abjuration_aura(self):
        spell = _spell("Circle of Power")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "self (30-foot radius)"
        assert spell.duration == "up to 10 minutes"
        assert spell.school == SpellSchool.ABJURATION

    def test_commune_is_ritual_divination(self):
        spell = _spell("Commune")
        # PHB: Commune is a ritual divination (no concentration).
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 minute"
        assert spell.school == SpellSchool.DIVINATION

    def test_commune_with_nature_is_ritual_divination(self):
        spell = _spell("Commune with Nature")
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 minute"
        assert spell.range == "self (3-mile radius)"
        assert spell.school == SpellSchool.DIVINATION

    def test_conjure_elemental_is_concentration_summon(self):
        spell = _spell("Conjure Elemental")
        assert spell.concentration is True
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 minute"
        assert spell.range == "90 feet"
        assert spell.duration == "up to 1 hour"
        assert spell.school == SpellSchool.CONJURATION

    def test_contact_other_plane_is_ritual_with_documented_self_risk(self):
        spell = _spell("Contact Other Plane")
        # PHB signature: the caster's own DC 15 Wis save + 6d6 self-psychic is
        # documented (effect-in-description — it is self-risk, not target
        # damage, so the engine resolves this as a ritual utility).
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.requires_attack_roll is False
        assert spell.casting_time == "1 minute"
        assert spell.school == SpellSchool.DIVINATION
        assert "6d6" in spell.description

    def test_creation_is_illusion_transmutation_note(self):
        spell = _spell("Creation")
        # PHB: Creation is an ILLUSION (quasi-real shadow material), not
        # transmutation. Concentration-free; duration depends on material.
        assert spell.school == SpellSchool.ILLUSION
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 minute"
        assert spell.range == "30 feet"

    def test_dispel_evil_and_good_is_concentration_abjuration(self):
        spell = _spell("Dispel Evil and Good")
        assert spell.concentration is True
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "self"
        assert spell.duration == "up to 10 minutes"
        assert spell.school == SpellSchool.ABJURATION

    def test_dream_is_concentration_illusion(self):
        spell = _spell("Dream")
        # PHB: Dream is an ILLUSION (10-minute concentration; range Special).
        assert spell.school == SpellSchool.ILLUSION
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 minute"
        assert spell.range == "special"
        assert spell.duration == "10 minutes"

    def test_hallow_is_evocation_with_long_cast(self):
        spell = _spell("Hallow")
        # PHB: Hallow is EVOCATION; a 24-hour ritual that creates a permanent
        # (until dispelled) sanctuary. No concentration (the effect endures).
        assert spell.school == SpellSchool.EVOCATION
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "24 hours"
        assert spell.range == "touch"

    def test_legend_lore_is_divination_long_cast(self):
        spell = _spell("Legend Lore")
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "10 minutes"
        assert spell.range == "self"
        assert spell.school == SpellSchool.DIVINATION

    def test_passwall_is_transmutation_one_hour_passage(self):
        spell = _spell("Passwall")
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 action"
        assert spell.range == "120 feet"
        assert spell.duration == "1 hour"
        assert spell.school == SpellSchool.TRANSMUTATION

    def test_raise_dead_is_necromancy_one_hour_cast(self):
        spell = _spell("Raise Dead")
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 hour"
        assert spell.range == "touch"
        assert spell.school == SpellSchool.NECROMANCY

    def test_reincarnate_is_transmutation_one_hour_cast(self):
        spell = _spell("Reincarnate")
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 hour"
        assert spell.range == "touch"
        assert spell.school == SpellSchool.TRANSMUTATION

    def test_swift_quiver_is_concentration_transmutation(self):
        spell = _spell("Swift Quiver")
        assert spell.concentration is True
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        # PHB: bonus-action cast (Ranger signature).
        assert spell.casting_time == "1 bonus action"
        assert spell.range == "touch"
        assert spell.duration == "up to 1 minute"
        assert spell.school == SpellSchool.TRANSMUTATION

    def test_teleportation_circle_is_conjuration_one_minute_cast(self):
        spell = _spell("Teleportation Circle")
        assert spell.concentration is False
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 minute"
        assert spell.range == "10 feet"
        assert spell.duration == "1 round"
        assert spell.school == SpellSchool.CONJURATION

    def test_tree_stride_is_concentration_conjuration(self):
        spell = _spell("Tree Stride")
        assert spell.concentration is True
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 action"
        assert spell.range == "self"
        assert spell.duration == "up to 1 minute"
        assert spell.school == SpellSchool.CONJURATION


# --------------------------------------------------------------------------- #
# Effect resolution of the new spells
# --------------------------------------------------------------------------- #
class TestNewSpellResolution:
    def test_destructive_wave_saves_and_fails(self):
        spell = _spell("Destructive Wave")
        # Made save: half damage (5d8 is 5-40; half is 2-20).
        effect = resolve_spell_effect(
            spell=spell, caster_level=9, proficiency_bonus=4,
            casting_mod=5, target_save_total=30, spell_save_dc=15,
        )
        assert effect.made_save is True
        assert 2 <= effect.damage <= 20
        assert effect.half_damage is True
        # Failed save: full damage.
        effect = resolve_spell_effect(
            spell=spell, caster_level=9, proficiency_bonus=4,
            casting_mod=5, target_save_total=2, spell_save_dc=15,
        )
        assert effect.made_save is False
        assert 5 <= effect.damage <= 40
        assert effect.half_damage is False
        assert effect.damage_type == "thunder"

    def test_conjure_volley_saves_and_fails(self):
        spell = _spell("Conjure Volley")
        # Made save: half damage (8d8 is 8-64; half is 4-32).
        effect = resolve_spell_effect(
            spell=spell, caster_level=9, proficiency_bonus=4,
            casting_mod=5, target_save_total=30, spell_save_dc=15,
        )
        assert effect.made_save is True
        assert 4 <= effect.damage <= 32
        assert effect.half_damage is True
        # Failed save: full damage.
        effect = resolve_spell_effect(
            spell=spell, caster_level=9, proficiency_bonus=4,
            casting_mod=5, target_save_total=2, spell_save_dc=15,
        )
        assert effect.made_save is False
        assert 8 <= effect.damage <= 64
        assert effect.half_damage is False
        assert effect.damage_type == "piercing"

    @pytest.mark.parametrize(
        "name, save_ability",
        [
            ("Contagion", "con"),
            ("Modify Memory", "wis"),
            ("Telekinesis", "str"),
            ("Planar Binding", "cha"),
            ("Geas", "wis"),
            ("Seeming", "cha"),
        ],
    )
    def test_save_debuff_spell_resolves(self, name, save_ability):
        spell = _spell(name)
        assert spell.save_ability == save_ability
        effect = resolve_spell_effect(
            spell=spell, caster_level=9, proficiency_bonus=4,
            casting_mod=5, target_save_total=30, spell_save_dc=15,
        )
        assert effect.made_save is True
        assert effect.damage == 0
        assert "save" in effect.description

    @pytest.mark.parametrize(
        "name",
        [
            "Awaken",
            "Banishing Smite",
            "Circle of Power",
            "Commune",
            "Commune with Nature",
            "Conjure Elemental",
            "Contact Other Plane",
            "Creation",
            "Dispel Evil and Good",
            "Dream",
            "Hallow",
            "Legend Lore",
            "Passwall",
            "Raise Dead",
            "Reincarnate",
            "Swift Quiver",
            "Teleportation Circle",
            "Tree Stride",
        ],
    )
    def test_utility_spell_resolves_cleanly(self, name):
        spell = _spell(name)
        effect = resolve_spell_effect(
            spell=spell, caster_level=9, proficiency_bonus=4, casting_mod=5,
        )
        assert effect.damage == 0 and effect.healing == 0
        assert "takes effect" in effect.description


# --------------------------------------------------------------------------- #
# Upcasting sanity (Destructive Wave +1d8, Conjure Volley +1d8)
# --------------------------------------------------------------------------- #
class TestUpcasting:
    def test_destructive_wave_upcasts_1d8_per_level(self):
        spell = _spell("Destructive Wave")
        assert spell.damage_dice_count == 5
        assert spell.at_higher_levels_dice == 1
        # At slot 7 (2 levels above base), dice count = 5 + 2*1 = 7.
        extra_levels = 2
        upcast_count = spell.damage_dice_count + spell.at_higher_levels_dice * extra_levels
        assert upcast_count == 7

    def test_conjure_volley_upcasts_1d8_per_level(self):
        spell = _spell("Conjure Volley")
        assert spell.damage_dice_count == 8
        assert spell.at_higher_levels_dice == 1
        # At slot 7 (2 levels above base), dice count = 8 + 2*1 = 10.
        extra_levels = 2
        upcast_count = spell.damage_dice_count + spell.at_higher_levels_dice * extra_levels
        assert upcast_count == 10

    def test_destructive_wave_roll_damage_at_upcast(self):
        """Upcasting the damage roll grows by the configured dice count."""
        spell = _spell("Destructive Wave")
        # Base slot: 5d8 = 5-40.
        base = spell.roll_damage(caster_level=9, slot_level=5)
        assert 5 <= base <= 40
        # Slot 7: 7d8 = 7-56.
        upcast = spell.roll_damage(caster_level=9, slot_level=7)
        assert 7 <= upcast <= 56

    def test_conjure_volley_roll_damage_at_upcast(self):
        """Upcasting the damage roll grows by the configured dice count."""
        spell = _spell("Conjure Volley")
        # Base slot: 8d8 = 8-64.
        base = spell.roll_damage(caster_level=9, slot_level=5)
        assert 8 <= base <= 64
        # Slot 7: 10d8 = 10-80.
        upcast = spell.roll_damage(caster_level=9, slot_level=7)
        assert 10 <= upcast <= 80
