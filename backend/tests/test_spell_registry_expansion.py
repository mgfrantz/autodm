"""
Tests for the expanded spell registry — iconic PHB/XGE spells added to fill
gaps in the cantrip / level 1-3 catalogue (Shield, Mage Armor, Bless, Command,
Chill Touch, etc.). These cover registration shape, mechanical correctness, and
effect resolution so the new entries behave like the rest of the registry.
"""
import pytest

from app.engine.spells import (
    Spell,
    SpellSchool,
    STARTING_SPELLS,
    get_spell,
    get_starting_spellbook,
    resolve_spell_effect,
)


def _spell(name: str) -> Spell:
    """Look up a spell by name/id and assert it is registered (type-safe helper)."""
    spell = get_spell(name)
    assert spell is not None, f"{name!r} should be registered"
    return spell


# --------------------------------------------------------------------------- #
# New cantrips
# --------------------------------------------------------------------------- #
class TestNewCantrips:
    @pytest.mark.parametrize("name", [
        "Chill Touch", "Poison Spray", "Shocking Grasp",
        "Toll the Dead", "Mind Sliver",
    ])
    def test_cantrip_registered(self, name):
        spell = _spell(name)
        assert spell.level == 0
        assert spell.is_cantrip is True

    def test_chill_touch(self):
        spell = _spell("Chill Touch")
        assert spell.school == SpellSchool.NECROMANCY
        assert spell.requires_attack_roll is True
        assert spell.save_ability is None
        assert spell.damage_dice_count == 1 and spell.damage_dice_sides == 8
        assert spell.damage_type == "necrotic"
        assert spell.deals_damage is True

    def test_poison_spray(self):
        spell = _spell("Poison Spray")
        assert spell.school == SpellSchool.CONJURATION
        assert spell.save_ability == "con"
        assert spell.requires_attack_roll is False
        assert spell.damage_dice_count == 1 and spell.damage_dice_sides == 12
        assert spell.damage_type == "poison"
        assert spell.range == "10 feet"

    def test_shocking_grasp(self):
        spell = _spell("Shocking Grasp")
        assert spell.school == SpellSchool.EVOCATION
        assert spell.requires_attack_roll is True
        assert spell.damage_dice_count == 1 and spell.damage_dice_sides == 8
        assert spell.damage_type == "lightning"
        assert spell.range == "touch"

    def test_toll_the_dead(self):
        spell = _spell("Toll the Dead")
        assert spell.school == SpellSchool.NECROMANCY
        assert spell.save_ability == "wis"
        assert spell.damage_dice_count == 1 and spell.damage_dice_sides == 8
        assert spell.damage_type == "necrotic"

    def test_mind_sliver(self):
        spell = _spell("Mind Sliver")
        assert spell.school == SpellSchool.ENCHANTMENT
        assert spell.save_ability == "int"
        assert spell.damage_dice_count == 1 and spell.damage_dice_sides == 6
        assert spell.damage_type == "psychic"
        # Mind Sliver is verbal-only (a subtle cantrip)
        assert "V" in spell.components and "S" not in spell.components

    def test_cantrip_scaling_new_cantrip(self):
        spell = _spell("Chill Touch")
        # Levels 1-4: single die (1-8 necrotic)
        assert 1 <= spell.roll_damage(caster_level=1) <= 8
        # Level 5-10: two dice (2-16)
        assert 2 <= spell.roll_damage(caster_level=5) <= 16
        # Level 17+: four dice (4-32)
        assert 4 <= spell.roll_damage(caster_level=17) <= 32


# --------------------------------------------------------------------------- #
# New level-1 spells
# --------------------------------------------------------------------------- #
class TestNewLevel1Spells:
    def test_shield(self):
        spell = _spell("Shield")
        assert spell.level == 1
        assert spell.school == SpellSchool.ABJURATION
        assert spell.casting_time == "1 reaction"
        assert spell.duration == "1 round"
        assert spell.deals_damage is False and spell.heals is False
        assert spell.save_ability is None and spell.requires_attack_roll is False
        assert spell.concentration is False  # Shield does not require concentration

    def test_mage_armor(self):
        spell = _spell("Mage Armor")
        assert spell.level == 1
        assert spell.school == SpellSchool.ABJURATION
        assert spell.duration == "8 hours"
        assert "M" in spell.components
        assert spell.deals_damage is False and spell.heals is False

    def test_bless(self):
        spell = _spell("Bless")
        assert spell.level == 1
        assert spell.school == SpellSchool.ENCHANTMENT
        assert spell.concentration is True
        assert spell.deals_damage is False

    def test_bane(self):
        spell = _spell("Bane")
        assert spell.level == 1
        assert spell.school == SpellSchool.ENCHANTMENT
        assert spell.save_ability == "cha"
        assert spell.concentration is True

    def test_command(self):
        spell = _spell("Command")
        assert spell.level == 1
        assert spell.school == SpellSchool.ENCHANTMENT
        assert spell.save_ability == "wis"
        assert spell.duration == "1 round"

    def test_charm_person(self):
        spell = _spell("Charm Person")
        assert spell.level == 1
        assert spell.school == SpellSchool.ENCHANTMENT
        assert spell.save_ability == "wis"

    def test_hunters_mark(self):
        # Registry key preserves the apostrophe.
        spell = _spell("hunter's_mark")
        assert spell.name == "Hunter's Mark"
        assert spell.level == 1
        assert spell.school == SpellSchool.DIVINATION
        assert spell.concentration is True
        # The 1d6 extra weapon damage is applied on weapon hits, not by the spell
        # itself, so the spell carries no damage dice of its own.
        assert spell.deals_damage is False

    def test_faerie_fire(self):
        spell = _spell("Faerie Fire")
        assert spell.level == 1
        assert spell.school == SpellSchool.EVOCATION
        assert spell.save_ability == "dex"
        assert spell.concentration is True

    def test_grease(self):
        spell = _spell("Grease")
        assert spell.level == 1
        assert spell.school == SpellSchool.CONJURATION
        assert spell.save_ability == "dex"


# --------------------------------------------------------------------------- #
# New level-2 spells
# --------------------------------------------------------------------------- #
class TestNewLevel2Spells:
    def test_aid(self):
        spell = _spell("Aid")
        assert spell.level == 2
        assert spell.school == SpellSchool.ABJURATION
        assert spell.duration == "8 hours"
        assert spell.concentration is False

    def test_lesser_restoration(self):
        spell = _spell("Lesser Restoration")
        assert spell.level == 2
        assert spell.school == SpellSchool.ABJURATION
        assert spell.range == "touch"
        assert spell.deals_damage is False and spell.heals is False

    def test_melfs_acid_arrow(self):
        spell = _spell("Melf's Acid Arrow")
        assert spell.level == 2
        assert spell.school == SpellSchool.EVOCATION
        assert spell.requires_attack_roll is True
        assert spell.damage_dice_count == 4 and spell.damage_dice_sides == 4
        assert spell.damage_type == "acid"
        assert spell.at_higher_levels_dice == 1

    def test_enhance_ability(self):
        spell = _spell("Enhance Ability")
        assert spell.level == 2
        assert spell.school == SpellSchool.TRANSMUTATION
        assert spell.concentration is True


# --------------------------------------------------------------------------- #
# New level-3 spells
# --------------------------------------------------------------------------- #
class TestNewLevel3Spells:
    def test_mass_healing_word(self):
        spell = _spell("Mass Healing Word")
        assert spell.level == 3
        assert spell.school == SpellSchool.EVOCATION
        assert spell.casting_time == "1 bonus action"
        assert spell.heals is True
        assert spell.healing_dice_count == 1 and spell.healing_dice_sides == 4
        assert spell.at_higher_levels_dice == 1

    def test_fear(self):
        spell = _spell("Fear")
        assert spell.level == 3
        assert spell.school == SpellSchool.ILLUSION
        assert spell.save_ability == "wis"
        assert spell.concentration is True


# --------------------------------------------------------------------------- #
# Effect resolution of the new spells
# --------------------------------------------------------------------------- #
class TestNewSpellResolution:
    def test_chill_touch_attack_roll(self):
        spell = _spell("Chill Touch")
        effect = resolve_spell_effect(
            spell=spell, caster_level=1, proficiency_bonus=2,
            casting_mod=0, target_ac=10,
        )
        assert effect.spell_name == "Chill Touch"
        assert effect.rolled_attack is not None
        assert effect.hit is not None
        assert effect.damage_type == "necrotic"
        if effect.hit:
            # 1d8 necrotic; a critical hit (natural 20) doubles it (up to 16).
            assert 1 <= effect.damage <= 16

    def test_poison_spray_save(self):
        spell = _spell("Poison Spray")
        # High save total -> made save, half damage.
        effect = resolve_spell_effect(
            spell=spell, caster_level=1, proficiency_bonus=2,
            casting_mod=3, target_save_total=30,
        )
        assert effect.made_save is True
        assert effect.half_damage is True
        assert 0 <= effect.damage <= 6  # half of 1d12

    def test_shield_resolves_as_utility(self):
        spell = _spell("Shield")
        effect = resolve_spell_effect(
            spell=spell, caster_level=1, proficiency_bonus=2, casting_mod=3,
        )
        assert effect.damage == 0 and effect.healing == 0
        assert "Shield takes effect" in effect.description

    def test_mass_healing_word_resolves_as_healing(self):
        spell = _spell("Mass Healing Word")
        effect = resolve_spell_effect(
            spell=spell, caster_level=1, proficiency_bonus=2, casting_mod=3,
        )
        assert effect.healing >= 1
        assert "HP" in effect.description

    def test_melfs_acid_arrow_hit_and_upcast(self):
        spell = _spell("Melf's Acid Arrow")
        assert spell.requires_attack_roll is True
        # Base 4d4 acid -> 4-16 at base (2nd) level.
        assert 4 <= spell.roll_damage(caster_level=3, slot_level=2) <= 16
        # Upcasting to a 3rd-level slot adds one die -> 5d4 (5-20)
        assert 5 <= spell.roll_damage(caster_level=3, slot_level=3) <= 20
        # Resolution path is structurally an attack roll producing acid damage.
        # A natural 1 always misses, so guard the damage-range assertion on hit.
        effect = resolve_spell_effect(
            spell=spell, caster_level=3, proficiency_bonus=2,
            casting_mod=0, target_ac=1,
        )
        assert effect.rolled_attack is not None
        assert effect.hit is not None
        assert effect.damage_type == "acid"
        if effect.hit:
            # 4d4 acid (4-16); a critical hit (natural 20) doubles it (up to 32).
            assert 4 <= effect.damage <= 32
        else:
            assert effect.damage == 0  # natural-1 auto-miss

    def test_command_save_resolution(self):
        spell = _spell("Command")
        # Save-only spell with no damage -> resolved/description path.
        effect = resolve_spell_effect(
            spell=spell, caster_level=1, proficiency_bonus=2,
            casting_mod=3, target_save_total=30,
        )
        assert effect.made_save is True
        assert effect.damage == 0


# --------------------------------------------------------------------------- #
# Starting spellbook now grants the iconic new spells
# --------------------------------------------------------------------------- #
class TestStartingSpellbookExpanded:
    def test_all_starting_spell_ids_resolve(self):
        """Every id referenced in STARTING_SPELLS must exist in the registry."""
        for char_class, data in STARTING_SPELLS.items():
            for sid in data.get("cantrips", []) + data.get("spells", []):
                assert get_spell(sid) is not None, (
                    f"{char_class} starting spell id {sid!r} is not registered"
                )

    def test_wizard_gets_shield_and_mage_armor(self):
        book = get_starting_spellbook("wizard", level=1)
        assert "shield" in book.known_spells
        assert "mage_armor" in book.known_spells
        # Prepared caster -> leveled starting spells are also prepared.
        assert "mage_armor" in book.prepared_spells

    def test_cleric_gets_bless(self):
        book = get_starting_spellbook("cleric", level=1)
        assert "bless" in book.known_spells
        assert "bless" in book.prepared_spells  # cleric is a prepared caster

    def test_ranger_gets_hunters_mark(self):
        book = get_starting_spellbook("ranger", level=1)
        # Ranger is a half-caster (known style) -> in known_spells.
        assert "hunter's_mark" in book.known_spells

    def test_paladin_gets_command(self):
        book = get_starting_spellbook("paladin", level=1)
        assert "command" in book.known_spells
