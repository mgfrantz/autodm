"""
Tests for the iconic PHB level-1 spell expansion — 16 spells added to round out
the most-played tier and lift the catalogue to 170 spells.

This mirrors the level-7/8/9 completion tests
(test_spell_level7_8_completion.py / test_spell_level9_completion.py). With the
top three tiers (7, 8, 9) now PHB-complete, this run extends the same treatment
down to the most-played tier — level 1 — covering all five effect-resolution
paths (attack-roll, save-for-half damage, save-debuff, healing, utility).

The 16 additions (all iconic PHB level-1 spells):
- Attack-roll: Inflict Wounds, Ray of Sickness, Witch Bolt.
- Save damage: Hellish Rebuke.
- Save debuff (no damage): Tasha's Hideous Laughter, Sanctuary.
- Healing (temp HP): False Life.
- Utility / buff: Alarm, Comprehend Languages, Disguise Self, Find Familiar,
  Fog Cloud, Identify, Longstrider, Protection from Evil and Good,
  Speak with Animals.

Coverage mirrors test_spell_level7_8_completion.py:
- Registry distribution (level 1 grew from 21 to 37; total 154 -> 170).
- Registration shape for every new spell (name, level, school) — parametrized.
- Per-spell mechanical correctness (save ability, concentration, ritual, dice,
  attack-roll flag).
- Effect resolution for the attack-roll spells, the save-damage spell, the
  save-debuff spells, the healing spell, and the utility spells (all resolve
  without raising).
- Whole-registry no-duplicate-name / no-duplicate-id guards.
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
# Registry distribution
# --------------------------------------------------------------------------- #
class TestRegistryShape:
    def test_total_spell_count_grew(self):
        # Was 154 before this expansion; now 170.
        assert len(SPELL_REGISTRY) >= 170

    def test_level_1_tier_grew(self):
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        # Level 1 grew from 21 to 37 — approaching PHB completeness.
        assert by_level[1] >= 37, (
            f"Level 1 has only {by_level[1]} spells (expected >=37)"
        )

    def test_iconic_phb_level1_subset_present(self):
        """The 16 newly-added iconic PHB level-1 spells are all registered."""
        ICONIC = [
            "Alarm", "Comprehend Languages", "Disguise Self", "False Life",
            "Find Familiar", "Fog Cloud", "Hellish Rebuke", "Identify",
            "Inflict Wounds", "Longstrider", "Protection from Evil and Good",
            "Ray of Sickness", "Sanctuary", "Speak with Animals",
            "Tasha's Hideous Laughter", "Witch Bolt",
        ]
        missing = [n for n in ICONIC if get_spell(n) is None]
        assert missing == [], f"Missing iconic PHB level-1 spells: {missing}"

    def test_no_duplicate_spell_names_in_registry(self):
        """Every spell must have a unique name (no dict-key collisions)."""
        names = [s.name for s in SPELL_REGISTRY.values()]
        assert len(names) == len(set(names)), "Duplicate spell names detected"


# --------------------------------------------------------------------------- #
# Registration shape — every new spell at its correct level and school
# --------------------------------------------------------------------------- #
NEW_SPELLS: list[tuple[str, int, SpellSchool]] = [
    ("Alarm", 1, SpellSchool.ABJURATION),
    ("Comprehend Languages", 1, SpellSchool.DIVINATION),
    ("Disguise Self", 1, SpellSchool.ILLUSION),
    ("False Life", 1, SpellSchool.NECROMANCY),
    ("Find Familiar", 1, SpellSchool.CONJURATION),
    ("Fog Cloud", 1, SpellSchool.CONJURATION),
    ("Hellish Rebuke", 1, SpellSchool.EVOCATION),
    ("Identify", 1, SpellSchool.DIVINATION),
    ("Inflict Wounds", 1, SpellSchool.NECROMANCY),
    ("Longstrider", 1, SpellSchool.TRANSMUTATION),
    ("Protection from Evil and Good", 1, SpellSchool.ABJURATION),
    ("Ray of Sickness", 1, SpellSchool.NECROMANCY),
    ("Sanctuary", 1, SpellSchool.ABJURATION),
    ("Speak with Animals", 1, SpellSchool.DIVINATION),
    ("Tasha's Hideous Laughter", 1, SpellSchool.ENCHANTMENT),
    ("Witch Bolt", 1, SpellSchool.EVOCATION),
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
# Per-spell mechanical correctness
# --------------------------------------------------------------------------- #
class TestLevel1Mechanics:
    def test_alarm_is_ritual_utility(self):
        spell = _spell("Alarm")
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False and spell.heals is False
        assert spell.casting_time == "1 minute"
        assert spell.duration == "8 hours"

    def test_comprehend_languages_is_ritual_utility(self):
        spell = _spell("Comprehend Languages")
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False and spell.heals is False
        assert spell.range == "self"
        assert spell.duration == "1 hour"

    def test_disguise_self_is_illusion_no_save(self):
        spell = _spell("Disguise Self")
        assert spell.school == SpellSchool.ILLUSION
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "self"
        assert spell.duration == "1 hour"

    def test_false_life_is_temp_hp_healing(self):
        spell = _spell("False Life")
        assert spell.heals is True
        # 1d4 + 4 temporary hit points.
        assert spell.healing_dice_count == 1 and spell.healing_dice_sides == 4
        assert spell.healing_bonus == 4
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "1 hour"
        # Upcasting adds 5 temp HP per slot level above 1st.
        assert spell.at_higher_levels_dice == 5

    def test_find_familiar_is_ritual_utility(self):
        spell = _spell("Find Familiar")
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False and spell.heals is False
        assert spell.casting_time == "1 hour"
        assert spell.duration == "until dismissed"

    def test_fog_cloud_is_concentration_no_save(self):
        spell = _spell("Fog Cloud")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "120 feet"

    def test_hellish_rebuke_is_save_damage(self):
        spell = _spell("Hellish Rebuke")
        # Dex save for half; 2d10 fire.
        assert spell.save_ability == "dex"
        assert spell.deals_damage is True
        assert spell.damage_dice_count == 2 and spell.damage_dice_sides == 10
        assert spell.damage_type == "fire"
        assert spell.concentration is False
        assert spell.casting_time == "1 reaction"
        assert spell.at_higher_levels_dice == 1

    def test_identify_is_ritual_utility(self):
        spell = _spell("Identify")
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False and spell.heals is False
        assert spell.casting_time == "1 minute"
        assert spell.range == "touch"

    def test_inflict_wounds_is_attack_roll(self):
        spell = _spell("Inflict Wounds")
        assert spell.requires_attack_roll is True
        assert spell.deals_damage is True
        # 3d10 necrotic.
        assert spell.damage_dice_count == 3 and spell.damage_dice_sides == 10
        assert spell.damage_type == "necrotic"
        assert spell.concentration is False
        assert spell.range == "touch"
        assert spell.at_higher_levels_dice == 1

    def test_longstrider_is_touch_buff(self):
        spell = _spell("Longstrider")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False and spell.heals is False
        assert spell.range == "touch"
        assert spell.duration == "1 hour"

    def test_protection_from_evil_and_good_is_concentration_ward(self):
        spell = _spell("Protection from Evil and Good")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "touch"
        assert spell.duration == "up to 10 minutes"

    def test_ray_of_sickness_is_attack_roll(self):
        spell = _spell("Ray of Sickness")
        assert spell.requires_attack_roll is True
        assert spell.deals_damage is True
        # 2d8 poison; the Con-save-vs-poisoned rider lives in the description.
        assert spell.damage_dice_count == 2 and spell.damage_dice_sides == 8
        assert spell.damage_type == "poison"
        assert spell.concentration is False
        assert spell.range == "60 feet"
        assert spell.at_higher_levels_dice == 1

    def test_sanctuary_is_wis_save_no_concentration(self):
        spell = _spell("Sanctuary")
        assert spell.save_ability == "wis"
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.casting_time == "1 bonus action"
        assert spell.duration == "1 minute"

    def test_speak_with_animals_is_concentration_ritual(self):
        spell = _spell("Speak with Animals")
        assert spell.concentration is True
        assert spell.ritual is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "self"
        assert spell.duration == "10 minutes"

    def test_tashas_hideous_laughter_is_save_debuff_concentration(self):
        spell = _spell("Tasha's Hideous Laughter")
        assert spell.save_ability == "wis"
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.range == "30 feet"
        assert spell.duration == "up to 1 minute"

    def test_witch_bolt_is_attack_roll_concentration(self):
        spell = _spell("Witch Bolt")
        assert spell.requires_attack_roll is True
        assert spell.deals_damage is True
        # 1d12 lightning, concentration.
        assert spell.damage_dice_count == 1 and spell.damage_dice_sides == 12
        assert spell.damage_type == "lightning"
        assert spell.concentration is True
        assert spell.range == "30 feet"
        assert spell.at_higher_levels_dice == 1


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

    def test_inflict_wounds_attack_roll_hits_and_misses(self, monkeypatch):
        spell = _spell("Inflict Wounds")
        # Hit (die 15, +7 = 22 vs AC 10): 3d10 (3-30) necrotic.
        self._force_d20(monkeypatch, 15)
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3,
            casting_mod=4, target_ac=10,
        )
        assert effect.hit is True
        assert effect.damage_type == "necrotic"
        assert 3 <= effect.damage <= 30
        # Miss (die 2, +7 = 9 vs AC 30): not a natural 1/20, below AC -> miss.
        self._force_d20(monkeypatch, 2)
        effect = resolve_spell_effect(
            spell=spell, caster_level=5, proficiency_bonus=3,
            casting_mod=4, target_ac=30,
        )
        assert effect.hit is False
        assert effect.damage == 0

    def test_witch_bolt_attack_roll_damage_range(self, monkeypatch):
        spell = _spell("Witch Bolt")
        self._force_d20(monkeypatch, 15)
        effect = resolve_spell_effect(
            spell=spell, caster_level=3, proficiency_bonus=2,
            casting_mod=4, target_ac=10,
        )
        assert effect.hit is True
        assert effect.damage_type == "lightning"
        assert 1 <= effect.damage <= 12

    def test_ray_of_sickness_attack_roll_damage_range(self, monkeypatch):
        spell = _spell("Ray of Sickness")
        self._force_d20(monkeypatch, 15)
        effect = resolve_spell_effect(
            spell=spell, caster_level=3, proficiency_bonus=2,
            casting_mod=4, target_ac=10,
        )
        assert effect.hit is True
        assert effect.damage_type == "poison"
        assert 2 <= effect.damage <= 16

    def test_hellish_rebuke_save_for_half(self):
        spell = _spell("Hellish Rebuke")
        # Failed save (total below DC) -> full 2d10 (2-20) fire.
        effect = resolve_spell_effect(
            spell=spell, caster_level=3, proficiency_bonus=2,
            casting_mod=4, target_save_total=5, spell_save_dc=15,
        )
        assert effect.made_save is False
        assert effect.damage_type == "fire"
        assert 2 <= effect.damage <= 20
        assert effect.half_damage is False
        # Made save -> half damage.
        effect = resolve_spell_effect(
            spell=spell, caster_level=3, proficiency_bonus=2,
            casting_mod=4, target_save_total=20, spell_save_dc=15,
        )
        assert effect.made_save is True
        assert effect.half_damage is True

    def test_tashas_hideous_laughter_resolves_as_save_debuff(self):
        spell = _spell("Tasha's Hideous Laughter")
        effect = resolve_spell_effect(
            spell=spell, caster_level=3, proficiency_bonus=2,
            casting_mod=4, target_save_total=20, spell_save_dc=15,
        )
        assert effect.made_save is True
        assert effect.damage == 0

    def test_sanctuary_resolves_as_save_debuff(self):
        spell = _spell("Sanctuary")
        effect = resolve_spell_effect(
            spell=spell, caster_level=3, proficiency_bonus=2,
            casting_mod=4, target_save_total=5, spell_save_dc=15,
        )
        assert effect.made_save is False
        assert effect.damage == 0

    def test_false_life_heals_temp_hp(self):
        spell = _spell("False Life")
        effect = resolve_spell_effect(
            spell=spell, caster_level=3, proficiency_bonus=2, casting_mod=4,
        )
        # 1d4 + 4 -> 5 to 8 temporary hit points.
        assert effect.healing >= 5 and effect.healing <= 8
        assert effect.damage == 0

    @pytest.mark.parametrize(
        "name",
        [
            "Alarm",
            "Comprehend Languages",
            "Disguise Self",
            "Find Familiar",
            "Fog Cloud",
            "Identify",
            "Longstrider",
            "Protection from Evil and Good",
            "Speak with Animals",
        ],
    )
    def test_utility_spell_resolves_cleanly(self, name):
        spell = _spell(name)
        effect = resolve_spell_effect(
            spell=spell, caster_level=3, proficiency_bonus=2, casting_mod=4,
        )
        assert effect.damage == 0 and effect.healing == 0
        assert "takes effect" in effect.description
