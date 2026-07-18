"""
Tests for the level-9 spell roster completion — 6 iconic PHB 9th-level spells
added to fill the tier's last documented gap ("only level 9 remains at 9").

This closes the roster: every Player's Handbook 9th-level spell is now
registered (15/15). The 6 additions: Astral Projection, Gate, Imprisonment,
Shapechange, Storm of Vengeance, Weird.

Coverage mirrors test_spell_high_level_expansion.py:
- Registry distribution (level 9 now >= 15; PHB roster complete).
- Registration shape for every new spell (name, level, school) — parametrized.
- Per-spell mechanical correctness (save ability, concentration, dice, flags).
- Effect resolution for the damage spells (save-for-half) and the
  save/utility spells (resolve without raising).
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
# Registry distribution + PHB level-9 roster completeness
# --------------------------------------------------------------------------- #
class TestRegistryShape:
    def test_total_spell_count_grew(self):
        # Was 133 before this expansion; now 139.
        assert len(SPELL_REGISTRY) >= 139

    def test_level_9_tier_is_now_complete(self):
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        # Level 9 now matches mid-tier density (was 9, now 15).
        assert by_level[9] >= 15, (
            f"Level 9 has only {by_level[9]} spells (expected >=15)"
        )

    def test_phb_level9_roster_is_complete(self):
        """All 15 Player's Handbook 9th-level spells are now registered."""
        PHB_LEVEL_9 = [
            "Astral Projection", "Foresight", "Gate", "Imprisonment",
            "Mass Heal", "Meteor Swarm", "Power Word Heal", "Power Word Kill",
            "Prismatic Wall", "Shapechange", "Storm of Vengeance",
            "Time Stop", "True Polymorph", "Weird", "Wish",
        ]
        missing = [n for n in PHB_LEVEL_9 if get_spell(n) is None]
        assert missing == [], f"Missing PHB level-9 spells: {missing}"


# --------------------------------------------------------------------------- #
# Registration shape — every new spell at level 9 and its correct school
# --------------------------------------------------------------------------- #
NEW_SPELLS: list[tuple[str, int, SpellSchool]] = [
    ("Astral Projection", 9, SpellSchool.NECROMANCY),
    ("Gate", 9, SpellSchool.CONJURATION),
    ("Imprisonment", 9, SpellSchool.ABJURATION),
    ("Shapechange", 9, SpellSchool.TRANSMUTATION),
    ("Storm of Vengeance", 9, SpellSchool.CONJURATION),
    ("Weird", 9, SpellSchool.ILLUSION),
]


@pytest.mark.parametrize("name, level, school", NEW_SPELLS)
def test_new_spell_registered(name, level, school):
    spell = _spell(name)
    assert spell.level == level
    assert spell.school == school


def test_new_spell_count_matches_plan():
    """All 6 planned new spells are registered."""
    assert len(NEW_SPELLS) == 6
    for name, _, _ in NEW_SPELLS:
        assert get_spell(name) is not None, f"{name!r} missing from registry"


def test_new_spell_ids_are_stable():
    """Each spell's id derives cleanly from its name (no collisions)."""
    for name, _, _ in NEW_SPELLS:
        spell = _spell(name)
        assert spell.id == name.lower().replace(" ", "_")
        # The registry key must match the id (no overwrite surprises).
        assert SPELL_REGISTRY[spell.id] is spell


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness
# --------------------------------------------------------------------------- #
class TestLevel9Mechanics:
    def test_astral_projection_is_a_utility_ritual_buff(self):
        spell = _spell("Astral Projection")
        assert spell.concentration is False
        assert spell.deals_damage is False and spell.heals is False
        assert spell.save_ability is None
        assert spell.casting_time == "1 hour"
        assert spell.duration == "until dispelled"

    def test_gate_is_a_concentration_portal(self):
        spell = _spell("Gate")
        assert spell.concentration is True
        assert spell.deals_damage is False and spell.heals is False
        # No default save — only a pulled creature may resist with Cha.
        assert spell.save_ability is None
        assert spell.duration == "up to 1 minute"
        assert spell.range == "60 feet"

    def test_imprisonment_is_a_save_debuff(self):
        spell = _spell("Imprisonment")
        # Default burial version uses a Str save; the description lists all six.
        assert spell.save_ability == "str"
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.duration == "until dispelled"
        assert spell.range == "30 feet"

    def test_shapechange_is_a_concentration_transformation(self):
        spell = _spell("Shapechange")
        assert spell.concentration is True
        assert spell.deals_damage is False and spell.heals is False
        assert spell.save_ability is None
        assert spell.duration == "up to 1 hour"
        assert spell.range == "self"

    def test_storm_of_vengeance(self):
        spell = _spell("Storm of Vengeance")
        assert spell.save_ability == "con"
        assert spell.deals_damage is True
        # Signature 10d6 lightning strike (the recurring round 5-10 effect).
        assert spell.damage_dice_count == 10 and spell.damage_dice_sides == 6
        assert spell.damage_type == "lightning"
        assert spell.concentration is True
        assert spell.duration == "up to 1 minute"

    def test_weird(self):
        spell = _spell("Weird")
        assert spell.save_ability == "wis"
        assert spell.deals_damage is True
        assert spell.damage_dice_count == 4 and spell.damage_dice_sides == 8
        assert spell.damage_type == "psychic"
        assert spell.concentration is True
        assert spell.duration == "up to 1 minute"


# --------------------------------------------------------------------------- #
# Effect resolution of the new spells
# --------------------------------------------------------------------------- #
class TestNewSpellResolution:
    def test_storm_of_vengeance_save_for_half(self):
        spell = _spell("Storm of Vengeance")
        # Failed save -> full 10d6 (10-60).
        effect = resolve_spell_effect(
            spell=spell, caster_level=17, proficiency_bonus=6,
            casting_mod=5, target_save_total=5, spell_save_dc=19,
        )
        assert effect.made_save is False
        assert effect.damage_type == "lightning"
        assert 10 <= effect.damage <= 60
        # Made save -> half damage.
        effect = resolve_spell_effect(
            spell=spell, caster_level=17, proficiency_bonus=6,
            casting_mod=5, target_save_total=30, spell_save_dc=19,
        )
        assert effect.made_save is True
        assert effect.half_damage is True

    def test_weird_save_for_half(self):
        spell = _spell("Weird")
        effect = resolve_spell_effect(
            spell=spell, caster_level=17, proficiency_bonus=6,
            casting_mod=5, target_save_total=5, spell_save_dc=19,
        )
        assert effect.made_save is False
        assert effect.damage_type == "psychic"
        assert 4 <= effect.damage <= 32  # 4d8
        # Made save -> no psychic damage (save negates Weird's damage).
        effect = resolve_spell_effect(
            spell=spell, caster_level=17, proficiency_bonus=6,
            casting_mod=5, target_save_total=30, spell_save_dc=19,
        )
        assert effect.made_save is True

    def test_imprisonment_resolves_as_save_debuff(self):
        # Save spell with no damage -> resolves via the made_save path.
        spell = _spell("Imprisonment")
        effect = resolve_spell_effect(
            spell=spell, caster_level=17, proficiency_bonus=6,
            casting_mod=5, target_save_total=30, spell_save_dc=19,
        )
        assert effect.made_save is True
        assert effect.damage == 0

    def test_gate_resolves_as_utility(self):
        spell = _spell("Gate")
        effect = resolve_spell_effect(
            spell=spell, caster_level=17, proficiency_bonus=6, casting_mod=5,
        )
        assert effect.damage == 0 and effect.healing == 0
        assert "takes effect" in effect.description

    def test_shapechange_resolves_as_utility(self):
        spell = _spell("Shapechange")
        effect = resolve_spell_effect(
            spell=spell, caster_level=17, proficiency_bonus=6, casting_mod=5,
        )
        assert effect.damage == 0 and effect.healing == 0
        assert "takes effect" in effect.description

    def test_astral_projection_resolves_as_utility(self):
        spell = _spell("Astral Projection")
        effect = resolve_spell_effect(
            spell=spell, caster_level=17, proficiency_bonus=6, casting_mod=5,
        )
        assert effect.damage == 0 and effect.healing == 0
        assert "takes effect" in effect.description
