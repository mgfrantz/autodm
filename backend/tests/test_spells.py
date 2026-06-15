"""
Tests for the spell engine: spells, spell slots, casting, and effects.
"""
import pytest

from app.engine.spells import (
    Spell,
    SpellLevel,
    SpellSchool,
    Spellbook,
    CasterType,
    CastingStyle,
    CASTER_PROFILES,
    STARTING_SPELLS,
    get_spell,
    get_starting_spellbook,
    register_spell,
    resolve_spell_effect,
    SPELL_REGISTRY,
    slots_for_level,
    effective_caster_level,
    cantrip_dice_multiplier,
    _norm,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def fire_bolt() -> Spell:
    return get_spell("fire_bolt") or Spell(
        name="Fire Bolt", level=0, school=SpellSchool.EVOCATION,
        requires_attack_roll=True, damage_dice_count=1, damage_dice_sides=10,
        damage_type="fire",
    )


def magic_missile() -> Spell:
    return get_spell("magic_missile") or Spell(
        name="Magic Missile", level=1, school=SpellSchool.EVOCATION,
        damage_dice_count=3, damage_dice_sides=4, damage_bonus=1,
        damage_type="force", at_higher_levels_dice=1,
    )


def cure_wounds() -> Spell:
    return get_spell("cure_wounds") or Spell(
        name="Cure Wounds", level=1, school=SpellSchool.EVOCATION,
        healing_dice_count=1, healing_dice_sides=8,
        at_higher_levels_dice=1,
    )


def burning_hands() -> Spell:
    return get_spell("burning_hands") or Spell(
        name="Burning Hands", level=1, school=SpellSchool.EVOCATION,
        save_ability="dex", damage_dice_count=3, damage_dice_sides=6,
        damage_type="fire", at_higher_levels_dice=1,
    )


# ---------------------------------------------------------------------------
# Spell level & school enums
# ---------------------------------------------------------------------------

class TestEnums:
    def test_spell_levels(self):
        assert SpellLevel.CANTRIP == 0
        assert SpellLevel.ONE == 1
        assert SpellLevel.FIVE == 5

    def test_spell_schools(self):
        assert SpellSchool.EVOCATION == "evocation"
        assert SpellSchool.ABJURATION == "abjuration"
        assert SpellSchool.NECROMANCY == "necromancy"


# ---------------------------------------------------------------------------
# Spell model
# ---------------------------------------------------------------------------

class TestSpell:
    def test_spell_creation(self):
        spell = Spell(
            name="Test Spell",
            level=1,
            school=SpellSchool.EVOCATION,
            description="A test spell.",
            damage_dice_count=2,
            damage_dice_sides=6,
            damage_type="fire",
        )
        assert spell.name == "Test Spell"
        assert spell.level == 1
        assert spell.school == SpellSchool.EVOCATION
        assert spell.is_cantrip == False
        assert spell.deals_damage == True
        assert spell.heals == False
        assert spell.id == "test_spell"

    def test_cantrip_flag(self):
        cantrip = Spell(name="Cantrip", level=0, school=SpellSchool.EVOCATION)
        spell = Spell(name="Spell", level=1, school=SpellSchool.EVOCATION)
        assert cantrip.is_cantrip == True
        assert spell.is_cantrip == False

    def test_spell_serialization(self):
        spell = Spell(
            name="Test Spell", level=1, school=SpellSchool.EVOCATION,
            damage_dice_count=2, damage_dice_sides=6, damage_type="fire",
            at_higher_levels_dice=1,
        )
        data = spell.to_dict()

        assert data["name"] == "Test Spell"
        assert data["level"] == 1
        assert data["school"] == "evocation"
        assert data["damage_dice_count"] == 2
        assert data["damage_dice_sides"] == 6
        assert data["damage_type"] == "fire"

        # Round-trip
        restored = Spell.from_dict(data)
        assert restored.name == spell.name
        assert restored.level == spell.level
        assert restored.damage_dice_count == spell.damage_dice_count

    def test_cantrip_scaling(self):
        spell = Spell(
            name="Cantrip", level=0, school=SpellSchool.EVOCATION,
            damage_dice_count=1, damage_dice_sides=8, damage_type="fire",
        )
        # Level 1-4: 1x dice
        dmg = spell.roll_damage(caster_level=1)
        assert dmg >= 1 and dmg <= 8

        # Level 5-10: 2x dice
        dmg = spell.roll_damage(caster_level=5)
        assert dmg >= 2 and dmg <= 16

        # Level 11-16: 3x dice
        dmg = spell.roll_damage(caster_level=11)
        assert dmg >= 3 and dmg <= 24

        # Level 17+: 4x dice
        dmg = spell.roll_damage(caster_level=17)
        assert dmg >= 4 and dmg <= 32

    def test_upcasting(self):
        spell = Spell(
            name="Upcastable", level=1, school=SpellSchool.EVOCATION,
            damage_dice_count=3, damage_dice_sides=6, damage_type="fire",
            at_higher_levels_dice=1,
        )
        # Base level 1: 3d6
        dmg = spell.roll_damage(caster_level=5, slot_level=1)
        assert dmg >= 3 and dmg <= 18

        # Level 2 slot: 4d6
        dmg = spell.roll_damage(caster_level=5, slot_level=2)
        assert dmg >= 4 and dmg <= 24

        # Level 4 slot: 6d6
        dmg = spell.roll_damage(caster_level=5, slot_level=4)
        assert dmg >= 6 and dmg <= 36

    def test_healing_spell(self):
        spell = Spell(
            name="Healing", level=1, school=SpellSchool.EVOCATION,
            healing_dice_count=1, healing_dice_sides=8, at_higher_levels_dice=1,
        )
        healing = spell.roll_healing(caster_level=1, slot_level=1)
        assert healing >= 1 and healing <= 8

        healing = spell.roll_healing(caster_level=5, slot_level=2)
        assert healing >= 2 and healing <= 16


# ---------------------------------------------------------------------------
# Spell registry
# ---------------------------------------------------------------------------

class TestSpellRegistry:
    def test_registry_has_common_spells(self):
        assert get_spell("fire_bolt") is not None
        assert get_spell("magic_missile") is not None
        assert get_spell("cure_wounds") is not None
        assert get_spell("fireball") is not None

    def test_registry_lookup_by_id(self):
        firebolt = get_spell("fire_bolt")
        assert firebolt is not None
        assert firebolt.name == "Fire Bolt"
        assert firebolt.level == 0

    def test_registry_lookup_by_name(self):
        firebolt = get_spell("Fire Bolt")
        assert firebolt is not None
        assert firebolt.id == "fire_bolt"

    def test_registry_returns_none_for_unknown(self):
        unknown = get_spell("unknown_spell")
        assert unknown is None

    def test_register_new_spell(self):
        new_spell = Spell(
            name="Test Spell", level=1, school=SpellSchool.EVOCATION,
        )
        registered = register_spell(new_spell)
        assert registered.id == new_spell.id
        assert get_spell(new_spell.id) == new_spell


# ---------------------------------------------------------------------------
# Spell slot progression
# ---------------------------------------------------------------------------

class TestSpellSlots:
    def test_full_caster_level_1(self):
        slots = slots_for_level(1, CasterType.FULL)
        assert slots == [2, 0, 0, 0, 0, 0, 0, 0, 0]

    def test_full_caster_level_5(self):
        slots = slots_for_level(5, CasterType.FULL)
        assert slots == [4, 3, 2, 0, 0, 0, 0, 0, 0]

    def test_full_caster_level_20(self):
        slots = slots_for_level(20, CasterType.FULL)
        assert slots == [4, 3, 3, 3, 3, 2, 2, 2, 1]

    def test_half_caster(self):
        # Paladin at level 2 is effective level 1
        slots = slots_for_level(2, CasterType.HALF)
        assert slots == [2, 0, 0, 0, 0, 0, 0, 0, 0]

        # Paladin at level 5 is effective level 3
        slots = slots_for_level(5, CasterType.HALF)
        assert slots == [4, 2, 0, 0, 0, 0, 0, 0, 0]

    def test_third_caster(self):
        # Eldritch knight fighter at level 3 is effective level 1
        slots = slots_for_level(3, CasterType.THIRD)
        assert slots == [2, 0, 0, 0, 0, 0, 0, 0, 0]

    def test_non_caster(self):
        slots = slots_for_level(10, CasterType.NONE)
        assert slots == [0] * 9

    def test_effective_caster_level(self):
        assert effective_caster_level(1, CasterType.FULL) == 1
        assert effective_caster_level(5, CasterType.FULL) == 5
        assert effective_caster_level(20, CasterType.FULL) == 20

        assert effective_caster_level(2, CasterType.HALF) == 1
        assert effective_caster_level(5, CasterType.HALF) == 3
        assert effective_caster_level(10, CasterType.HALF) == 5

        assert effective_caster_level(3, CasterType.THIRD) == 1
        assert effective_caster_level(6, CasterType.THIRD) == 2
        assert effective_caster_level(9, CasterType.THIRD) == 3


# ---------------------------------------------------------------------------
# Caster profiles
# ---------------------------------------------------------------------------

class TestCasterProfiles:
    def test_wizard_profile(self):
        profile = CASTER_PROFILES["wizard"]
        assert profile == (CasterType.FULL, CastingStyle.PREPARED, "int")

    def test_sorcerer_profile(self):
        profile = CASTER_PROFILES["sorcerer"]
        assert profile == (CasterType.FULL, CastingStyle.KNOWN, "cha")

    def test_fighter_profile(self):
        profile = CASTER_PROFILES["fighter"]
        assert profile == (CasterType.NONE, CastingStyle.NONE, "int")


# ---------------------------------------------------------------------------
# Starting spells
# ---------------------------------------------------------------------------

class TestStartingSpells:
    def test_wizard_starting_spells(self):
        spellbook = get_starting_spellbook("wizard", level=1)
        assert spellbook.is_caster
        assert "fire_bolt" in spellbook.known_spells
        assert "magic_missile" in spellbook.known_spells
        assert "burning_hands" in spellbook.prepared_spells  # prepared caster

    def test_sorcerer_starting_spells(self):
        spellbook = get_starting_spellbook("sorcerer", level=1)
        assert spellbook.is_caster
        assert "fire_bolt" in spellbook.known_spells
        assert "magic_missile" in spellbook.known_spells
        # Known caster — no prep, just known
        assert spellbook.casting_style == CastingStyle.KNOWN

    def test_fighter_starting_spells(self):
        spellbook = get_starting_spellbook("fighter", level=1)
        assert not spellbook.is_caster
        assert len(spellbook.known_spells) == 0


# ---------------------------------------------------------------------------
# Spellbook
# ---------------------------------------------------------------------------

class TestSpellbook:
    def test_wizard_spellbook(self):
        book = Spellbook(char_class="wizard", level=1)
        assert book.caster_type == CasterType.FULL
        assert book.casting_style == CastingStyle.PREPARED
        assert book.casting_ability == "int"

    def test_slots_tracking(self):
        book = Spellbook(char_class="wizard", level=1)
        assert book.max_slots(1) == 2
        assert book.slots_used(1) == 0
        assert book.available_slots(1) == 2

    def test_slots_after_level_up(self):
        book = Spellbook(char_class="wizard", level=1)
        book.set_level(3)
        assert book.max_slots(1) == 4
        assert book.max_slots(2) == 2

    def test_learn_spell(self):
        book = Spellbook(char_class="wizard", level=1)
        success = book.learn_spell("fireball")
        assert success == True
        assert "fireball" in book.known_spells

    def test_learn_duplicate_fails(self):
        book = Spellbook(char_class="wizard", level=1)
        book.learn_spell("fireball")
        success = book.learn_spell("fireball")
        assert success == False

    def test_forget_spell(self):
        book = Spellbook(char_class="wizard", level=1)
        book.learn_spell("fireball")
        success = book.forget_spell("fireball")
        assert success == True
        assert "fireball" not in book.known_spells

    def test_prepare_spell(self):
        book = Spellbook(char_class="wizard", level=1)
        book.learn_spell("fireball")
        success = book.prepare_spell("fireball")
        assert success == True
        assert "fireball" in book.prepared_spells

    def test_prepare_unknown_fails(self):
        book = Spellbook(char_class="wizard", level=1)
        success = book.prepare_spell("fireball")
        assert success == False

    def test_unprepare_spell(self):
        book = Spellbook(char_class="wizard", level=1)
        book.learn_spell("fireball")
        book.prepare_spell("fireball")
        success = book.unprepare_spell("fireball")
        assert success == True
        assert "fireball" not in book.prepared_spells

    def test_castable_spells_known_caster(self):
        book = Spellbook(char_class="sorcerer", level=1)
        book.known_spells = ["fire_bolt", "magic_missile"]
        castable = book.castable_spells()
        names = [s.name for s in castable]
        assert "Fire Bolt" in names
        assert "Magic Missile" in names

    def test_castable_spells_prepared_caster(self):
        book = Spellbook(char_class="wizard", level=1)
        book.known_spells = ["fire_bolt", "magic_missile", "burning_hands"]
        book.prepared_spells = ["burning_hands"]
        castable = book.castable_spells()
        names = [s.name for s in castable]
        # Cantrips are always castable
        assert "Fire Bolt" in names
        # Only prepared leveled spells
        assert "Burning Hands" in names
        assert "Magic Missile" not in names

    def test_long_rest(self):
        book = Spellbook(char_class="wizard", level=1)
        book._slots_used[0] = 2  # Exhaust level 1 slots
        assert book.available_slots(1) == 0

        book.long_rest()
        assert book.available_slots(1) == 2

    def test_serialization(self):
        book = Spellbook(
            char_class="wizard", level=3,
            known_spells=["fire_bolt", "magic_missile"],
            prepared_spells=["magic_missile"],
            slots_used=[1, 0, 0, 0, 0, 0, 0, 0, 0],
        )
        data = book.to_dict()

        assert data["char_class"] == "wizard"
        assert data["level"] == 3
        assert "fire_bolt" in data["known_spells"]
        assert data["slots_used"][0] == 1

        # Round-trip
        restored = Spellbook.from_dict(data)
        assert restored.char_class == book.char_class
        assert restored.level == book.level
        assert restored.known_spells == book.known_spells
        assert restored.slots_used(1) == 1


# ---------------------------------------------------------------------------
# Casting logic
# ---------------------------------------------------------------------------

class TestCasting:
    def test_cast_cantrip_no_slot(self):
        book = Spellbook(char_class="wizard", level=1)
        book.known_spells = ["fire_bolt"]

        outcome = book.cast("fire_bolt", target_ac=15, caster_mod=3)
        assert outcome.success
        assert outcome.spell and outcome.spell.level == 0
        assert outcome.slot_level == 0  # Cantrips use no slot
        assert outcome.effect is not None

    def test_cast_leveled_spell_consumes_slot(self):
        book = Spellbook(char_class="wizard", level=1)
        book.known_spells = ["magic_missile"]
        book.prepared_spells = ["magic_missile"]

        # Cast once
        outcome = book.cast("magic_missile")
        assert outcome.success
        assert outcome.slot_level == 1
        assert book.slots_used(1) == 1
        assert book.available_slots(1) == 1

    def test_cast_without_slots_fails(self):
        book = Spellbook(char_class="wizard", level=1)
        book.known_spells = ["magic_missile"]
        book.prepared_spells = ["magic_missile"]
        book._slots_used[0] = 2  # Exhaust all level 1 slots

        outcome = book.cast("magic_missile")
        assert not outcome.success
        assert "No spell slots" in outcome.message

    def test_cast_unknown_spell_fails(self):
        book = Spellbook(char_class="wizard", level=1)
        outcome = book.cast("unknown_spell")
        assert not outcome.success
        assert "Unknown spell" in outcome.message


# ---------------------------------------------------------------------------
# Effect resolution
# ---------------------------------------------------------------------------

class TestEffectResolution:
    def test_attack_roll_hit(self):
        spell = fire_bolt()
        effect = resolve_spell_effect(
            spell=spell,
            caster_level=1,
            proficiency_bonus=2,
            casting_mod=0,
            target_ac=10,
        )
        # Result depends on random dice, but structure should be correct
        assert effect.spell_name == "Fire Bolt"
        assert effect.damage_type == "fire"
        assert effect.rolled_attack is not None
        assert effect.hit is not None

    def test_save_spell(self):
        spell = burning_hands()
        effect = resolve_spell_effect(
            spell=spell,
            caster_level=1,
            proficiency_bonus=2,
            casting_mod=0,
            target_save_total=15,  # Saved
        )
        assert effect.spell_name == "Burning Hands"
        assert effect.made_save == True
        assert effect.half_damage == True
        assert 0 <= effect.damage <= 9  # Half of 3d6

    def test_save_spell_fail(self):
        spell = burning_hands()
        effect = resolve_spell_effect(
            spell=spell,
            caster_level=1,
            proficiency_bonus=2,
            casting_mod=0,
            target_save_total=8,  # Failed
        )
        assert effect.made_save == False
        assert effect.half_damage == False
        assert 3 <= effect.damage <= 18  # Full 3d6

    def test_healing_spell(self):
        spell = cure_wounds()
        effect = resolve_spell_effect(
            spell=spell,
            caster_level=1,
            proficiency_bonus=2,
            casting_mod=0,
        )
        assert effect.spell_name == "Cure Wounds"
        assert effect.healing > 0
        assert effect.damage == 0

    def test_utility_spell(self):
        spell = get_spell("light")
        assert spell is not None
        effect = resolve_spell_effect(
            spell=spell,
            caster_level=1,
            proficiency_bonus=2,
            casting_mod=0,
        )
        assert effect.spell_name == "Light"
        assert effect.damage == 0
        assert effect.healing == 0


# ---------------------------------------------------------------------------
# Helper normalization
# ---------------------------------------------------------------------------

class TestNormalization:
    def test_normalize_spell_id(self):
        assert _norm("Fire Bolt") == "fire_bolt"
        assert _norm("fire_bolt") == "fire_bolt"
        assert _norm("Magic Missile") == "magic_missile"
        assert _norm("MAGIC MISSILE") == "magic_missile"