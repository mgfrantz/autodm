"""
Tests for spell components parsing and condition-based casting restrictions.
"""
import pytest

from app.engine.spells import (
    Spell,
    SpellSchool,
    SpellComponents,
    parse_components,
    can_cast_with_conditions,
    SILENCED_CONDITIONS,
    NO_SOMATIC_CONDITIONS,
    Spellbook,
    register_spell,
    get_spell,
)


# ---------------------------------------------------------------------------
# Component Parsing
# ---------------------------------------------------------------------------

class TestSpellComponents:
    def test_parse_verbal_only(self):
        comp = parse_components("V")
        assert comp.has_verbal()
        assert not comp.has_somatic()
        assert not comp.has_material()

    def test_parse_somatic_only(self):
        comp = parse_components("S")
        assert not comp.has_verbal()
        assert comp.has_somatic()
        assert not comp.has_material()

    def test_parse_material_only(self):
        comp = parse_components("M")
        assert not comp.has_verbal()
        assert not comp.has_somatic()
        assert comp.has_material()

    def test_parse_verbal_somatic(self):
        comp = parse_components("V, S")
        assert comp.has_verbal()
        assert comp.has_somatic()
        assert not comp.has_material()

    def test_parse_verbal_material(self):
        comp = parse_components("V, M")
        assert comp.has_verbal()
        assert not comp.has_somatic()
        assert comp.has_material()

    def test_parse_all_components(self):
        comp = parse_components("V, S, M")
        assert comp.has_verbal()
        assert comp.has_somatic()
        assert comp.has_material()

    def test_parse_whitespace_tolerant(self):
        comp = parse_components("  V  ,  S  ")
        assert comp.has_verbal()
        assert comp.has_somatic()

    def test_parse_material_description(self):
        desc = "a tiny piece of phosphor"
        comp = parse_components("V, S, M", desc)
        assert comp.material_description == desc
        assert comp.material_cost_gp == 0.0

    def test_parse_material_cost_gp(self):
        desc = "a diamond worth at least 300 gp"
        comp = parse_components("V, S, M", desc)
        assert comp.material_cost_gp == 300.0
        assert "diamond" in comp.material_description

    def test_parse_material_cost_with_decimal(self):
        desc = "a gem worth 50.5 gp"
        comp = parse_components("M", desc)
        assert comp.material_cost_gp == 50.5

    def test_components_serialization(self):
        comp = SpellComponents(
            verbal=True,
            somatic=True,
            material=True,
            material_description="a diamond worth 300 gp",
            material_cost_gp=300.0,
            material_consumed=True,
        )
        data = comp.to_dict()
        assert data["verbal"] is True
        assert data["somatic"] is True
        assert data["material"] is True
        assert data["material_description"] == "a diamond worth 300 gp"
        assert data["material_cost_gp"] == 300.0

        comp2 = SpellComponents.from_dict(data)
        assert comp2.verbal == comp.verbal
        assert comp2.somatic == comp.somatic
        assert comp2.material == comp.material
        assert comp2.material_description == comp.material_description
        assert comp2.material_cost_gp == comp.material_cost_gp


# ---------------------------------------------------------------------------
# Condition-based Casting
# ---------------------------------------------------------------------------

class TestCanCastWithConditions:
    def test_no_conditions_allows_all_components(self):
        comp = parse_components("V, S, M")
        can, reason = can_cast_with_conditions(comp, [])
        assert can is True
        assert reason == ""

    def test_unconscious_blocks_verbal(self):
        comp = parse_components("V")
        can, reason = can_cast_with_conditions(comp, ["unconscious"])
        assert can is False
        assert "unable to speak" in reason

    def test_unconscious_blocks_somatic(self):
        comp = parse_components("S")
        can, reason = can_cast_with_conditions(comp, ["unconscious"])
        assert can is False
        assert "unable to move" in reason

    def test_paralyzed_blocks_verbal(self):
        comp = parse_components("V")
        can, reason = can_cast_with_conditions(comp, ["paralyzed"])
        assert can is False
        assert "unable to speak" in reason

    def test_paralyzed_blocks_somatic(self):
        comp = parse_components("S")
        can, reason = can_cast_with_conditions(comp, ["paralyzed"])
        assert can is False
        assert "unable to move" in reason

    def test_petrified_blocks_verbal(self):
        comp = parse_components("V")
        can, reason = can_cast_with_conditions(comp, ["petrified"])
        assert can is False
        assert "unable to speak" in reason

    def test_petrified_blocks_somatic(self):
        comp = parse_components("S")
        can, reason = can_cast_with_conditions(comp, ["petrified"])
        assert can is False
        assert "unable to move" in reason

    def test_stunned_blocks_verbal(self):
        comp = parse_components("V")
        can, reason = can_cast_with_conditions(comp, ["stunned"])
        assert can is False
        assert "unable to speak" in reason

    def test_stunned_allows_somatic(self):
        # Stunned creatures can't speak but can move
        comp = parse_components("S")
        can, reason = can_cast_with_conditions(comp, ["stunned"])
        assert can is True
        assert reason == ""

    def test_multiple_conditions_one_blocks(self):
        comp = parse_components("V")
        can, reason = can_cast_with_conditions(comp, ["grappled", "unconscious"])
        assert can is False
        assert "unable to speak" in reason

    def test_non_blocking_conditions_dont_matter(self):
        comp = parse_components("V, S")
        can, reason = can_cast_with_conditions(comp, ["grappled", "restrained", "frightened"])
        assert can is True
        assert reason == ""

    def test_material_only_no_condition_blocks(self):
        # Material-only spells (V, S) are not blocked by conditions in this basic implementation
        comp = parse_components("M")
        can, reason = can_cast_with_conditions(comp, ["unconscious", "paralyzed"])
        assert can is True  # In full implementation, material components would be blocked too
        assert reason == ""


# ---------------------------------------------------------------------------
# Spell Integration
# ---------------------------------------------------------------------------

class TestSpellComponentsIntegration:
    def test_spell_has_parsed_components(self):
        spell = Spell(
            name="Test Spell",
            level=1,
            school=SpellSchool.EVOCATION,
            components="V, S, M",
            material_description="a diamond worth 100 gp",
        )
        assert spell.parsed_components.has_verbal()
        assert spell.parsed_components.has_somatic()
        assert spell.parsed_components.has_material()
        assert spell.parsed_components.material_cost_gp == 100.0

    def test_spell_serialization_includes_components(self):
        spell = Spell(
            name="Test Spell",
            level=1,
            school=SpellSchool.EVOCATION,
            components="V, S, M",
            material_description="a small crystal worth 50 gp",
        )
        data = spell.to_dict()
        assert "material_description" in data
        assert data["material_description"] == "a small crystal worth 50 gp"
        assert "parsed_components" in data
        assert data["parsed_components"]["verbal"] is True
        assert data["parsed_components"]["material_cost_gp"] == 50.0

    def test_spell_from_dict_preserves_components(self):
        data = {
            "name": "Test Spell",
            "level": 1,
            "school": "evocation",
            "components": "V, M",
            "material_description": "a piece of red wool",
            "damage_dice_count": 2,
            "damage_dice_sides": 6,
            "damage_type": "fire",
        }
        spell = Spell.from_dict(data)
        assert spell.components == "V, M"
        assert spell.material_description == "a piece of red wool"
        assert spell.parsed_components.has_verbal()
        assert spell.parsed_components.has_material()
        assert not spell.parsed_components.has_somatic()


# ---------------------------------------------------------------------------
# Spellbook Integration
# ---------------------------------------------------------------------------

class TestSpellbookComponents:
    def test_spellbook_cast_with_blocking_conditions(self):
        # Create a test spell
        register_spell(Spell(
            name="Test V Spell",
            level=1,
            school=SpellSchool.EVOCATION,
            components="V",
            damage_dice_count=2,
            damage_dice_sides=6,
            damage_type="fire",
        ))

        book = Spellbook("wizard", level=1)
        book.learn_spell("test_v_spell")
        book.prepare_spell("test_v_spell")

        # Cast without conditions should succeed
        outcome = book.cast("test_v_spell", caster_mod=3)
        assert outcome.success

        # Cast with unconscious condition should fail
        outcome = book.cast("test_v_spell", caster_mod=3, active_conditions=["unconscious"])
        assert not outcome.success
        assert "unable to speak" in outcome.message

    def test_spellbook_cast_somatic_with_paralyzed(self):
        register_spell(Spell(
            name="Test S Spell",
            level=1,
            school=SpellSchool.EVOCATION,
            components="S",
            damage_dice_count=2,
            damage_dice_sides=6,
            damage_type="fire",
        ))

        book = Spellbook("wizard", level=1)
        book.learn_spell("test_s_spell")
        book.prepare_spell("test_s_spell")

        # Cast with paralyzed condition should fail
        outcome = book.cast("test_s_spell", caster_mod=3, active_conditions=["paralyzed"])
        assert not outcome.success
        assert "unable to move" in outcome.message

    def test_spellbook_cast_no_components_succeeds_anyway(self):
        # Test with a spell that has no component restrictions
        register_spell(Spell(
            name="Test No Components Spell",
            level=1,
            school=SpellSchool.EVOCATION,
            components="",  # No components
            damage_dice_count=2,
            damage_dice_sides=6,
            damage_type="fire",
        ))

        book = Spellbook("wizard", level=1)
        book.learn_spell("test_no_components_spell")
        book.prepare_spell("test_no_components_spell")

        # Should succeed even with conditions
        outcome = book.cast("test_no_components_spell", caster_mod=3, active_conditions=["unconscious", "paralyzed"])
        # Note: empty components string parses to no components, so no blocking
        # But spell would still fail if it requires slots
        # For cantrip-level, this would work
        assert outcome.success