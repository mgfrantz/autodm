"""
Tests for the trap/hazard engine (DMG ch.5).
"""

import pytest

from app.engine.traps import (
    Trap, TrapInstance, TrapEffect, TrapType, TrapSeverity, TrapEffectType,
    TRAP_REGISTRY, get_trap, list_traps, list_trap_ids, traps_by_severity,
    attempt_detection, check_passive_perception, attempt_disarm,
    trigger_trap, failed_disarm_triggers, trap_summary_for_dm,
    severity_guidelines, roll_dice,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestTrapRegistry:
    def test_registry_has_traps(self):
        traps = list_traps()
        assert len(traps) >= 14

    def test_list_trap_ids_sorted(self):
        ids = list_trap_ids()
        assert ids == sorted(ids)

    def test_get_trap_returns_template(self):
        trap = get_trap("collapsing_roof")
        assert trap is not None
        assert trap.name == "Collapsing Roof"
        assert trap.trap_type == TrapType.MECHANICAL

    def test_get_nonexistent_trap(self):
        assert get_trap("nonexistent") is None

    def test_filter_by_type(self):
        mechanical = list_traps(trap_type=TrapType.MECHANICAL)
        magical = list_traps(trap_type=TrapType.MAGICAL)
        assert len(mechanical) > 0
        assert len(magical) > 0
        for t in mechanical:
            assert t.trap_type == TrapType.MECHANICAL
        for t in magical:
            assert t.trap_type == TrapType.MAGICAL

    def test_filter_by_severity(self):
        deadly = traps_by_severity(TrapSeverity.DEADLY)
        assert len(deadly) >= 1
        for t in deadly:
            assert t.severity == TrapSeverity.DEADLY

    def test_all_traps_have_required_fields(self):
        for trap in TRAP_REGISTRY.values():
            assert trap.id
            assert trap.name
            assert trap.description
            assert len(trap.effects) > 0
            assert trap.detection_dc >= 1
            assert trap.disarm_dc >= 1

    def test_trap_type_coverage(self):
        """Registry covers both mechanical and magical trap types."""
        types = {t.trap_type for t in TRAP_REGISTRY.values()}
        assert TrapType.MECHANICAL in types
        assert TrapType.MAGICAL in types

    def test_severity_coverage(self):
        """Registry covers all three severity bands."""
        severities = {t.severity for t in TRAP_REGISTRY.values()}
        assert TrapSeverity.SETBACK in severities
        assert TrapSeverity.DANGEROUS in severities
        assert TrapSeverity.DEADLY in severities

    def test_known_dmg_traps_present(self):
        """Sample DMG traps are in the registry."""
        for tid in [
            "collapsing_roof", "falling_net", "fire_breathing_statue",
            "hidden_pit", "poison_darts", "poisoned_needle", "rolling_sphere",
            "swinging_blade", "glyph_of_warding", "bear_trap",
        ]:
            assert tid in TRAP_REGISTRY, f"Missing trap: {tid}"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

class TestTrapSerialization:
    def test_trap_round_trip(self):
        trap = get_trap("collapsing_roof")
        d = trap.to_dict()
        restored = Trap.from_dict(d)
        assert restored.id == trap.id
        assert restored.name == trap.name
        assert restored.trap_type == trap.trap_type
        assert restored.severity == trap.severity
        assert restored.detection_dc == trap.detection_dc
        assert len(restored.effects) == len(trap.effects)

    def test_effect_round_trip(self):
        effect = TrapEffect(
            type=TrapEffectType.DAMAGE,
            damage_dice="3d6",
            damage_type="fire",
            save_ability="dexterity",
            save_dc=15,
            save_result="half",
        )
        d = effect.to_dict()
        restored = TrapEffect.from_dict(d)
        assert restored.type == TrapEffectType.DAMAGE
        assert restored.damage_dice == "3d6"
        assert restored.save_dc == 15

    def test_instance_round_trip(self):
        trap = get_trap("poison_darts")
        inst = TrapInstance.from_trap(trap, location="corridor")
        inst.discovered = True
        inst.triggered = True
        inst.trigger_count = 2

        d = inst.to_dict()
        restored = TrapInstance.from_dict(d)
        assert restored.trap_id == "poison_darts"
        assert restored.discovered is True
        assert restored.triggered is True
        assert restored.trigger_count == 2
        assert restored.location == "corridor"

    def test_instance_from_trap_fresh_state(self):
        trap = get_trap("hidden_pit")
        inst = TrapInstance.from_trap(trap)
        assert inst.discovered is False
        assert inst.disarmed is False
        assert inst.triggered is False
        assert inst.trigger_count == 0


# ---------------------------------------------------------------------------
# Dice
# ---------------------------------------------------------------------------

class TestDiceHelper:
    def test_simple_roll(self):
        result = roll_dice("2d6", roller=lambda n, s: [3, 4])
        assert result == 7

    def test_roll_with_modifier(self):
        result = roll_dice("1d8+5", roller=lambda n, s: [6])
        assert result == 11

    def test_roll_negative_modifier(self):
        result = roll_dice("1d20-2", roller=lambda n, s: [15])
        assert result == 13

    def test_invalid_expression(self):
        with pytest.raises(ValueError):
            roll_dice("invalid")

    def test_random_roll_in_range(self):
        for _ in range(50):
            result = roll_dice("1d20")
            assert 1 <= result <= 20


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

class TestDetection:
    def test_successful_detection(self):
        trap = get_trap("hidden_pit")  # DC 12
        inst = TrapInstance.from_trap(trap)
        result = attempt_detection(inst, perception_total=15, roll=12)
        assert result.success is True
        assert inst.discovered is True
        assert result.dc == 12

    def test_failed_detection(self):
        trap = get_trap("hidden_pit")
        inst = TrapInstance.from_trap(trap)
        result = attempt_detection(inst, perception_total=8, roll=5)
        assert result.success is False
        assert inst.discovered is False

    def test_detection_already_disarmed(self):
        trap = get_trap("hidden_pit")
        inst = TrapInstance.from_trap(trap)
        inst.disarmed = True
        result = attempt_detection(inst, perception_total=20, roll=18)
        assert result.success is False
        assert "already been disarmed" in result.narrative.lower()

    def test_exact_dc_succeeds(self):
        trap = get_trap("hidden_pit")  # DC 12
        inst = TrapInstance.from_trap(trap)
        result = attempt_detection(inst, perception_total=12, roll=10)
        assert result.success is True

    def test_passive_perception_success(self):
        trap = get_trap("falling_net")  # DC 10
        inst = TrapInstance.from_trap(trap)
        assert check_passive_perception(inst, passive_perception=12) is True
        assert inst.discovered is True

    def test_passive_perception_failure(self):
        trap = get_trap("falling_net")  # DC 10
        inst = TrapInstance.from_trap(trap)
        assert check_passive_perception(inst, passive_perception=8) is False
        assert inst.discovered is False

    def test_passive_perception_already_discovered(self):
        trap = get_trap("falling_net")
        inst = TrapInstance.from_trap(trap)
        inst.discovered = True
        assert check_passive_perception(inst, passive_perception=5) is True


# ---------------------------------------------------------------------------
# Disarm
# ---------------------------------------------------------------------------

class TestDisarm:
    def test_successful_disarm(self):
        trap = get_trap("hidden_pit")  # disarm DC 12
        inst = TrapInstance.from_trap(trap)
        inst.discovered = True
        result = attempt_disarm(inst, check_total=15, roll=12)
        assert result.success is True
        assert inst.disarmed is True

    def test_failed_disarm(self):
        trap = get_trap("hidden_pit")
        inst = TrapInstance.from_trap(trap)
        inst.discovered = True
        result = attempt_disarm(inst, check_total=8, roll=5)
        assert result.success is False
        assert inst.disarmed is False

    def test_disarm_not_discovered(self):
        trap = get_trap("hidden_pit")
        inst = TrapInstance.from_trap(trap)
        result = attempt_disarm(inst, check_total=20, roll=18)
        assert result.success is False
        assert "haven't found" in result.narrative.lower()

    def test_disarm_already_disarmed(self):
        trap = get_trap("hidden_pit")
        inst = TrapInstance.from_trap(trap)
        inst.discovered = True
        inst.disarmed = True
        result = attempt_disarm(inst, check_total=5, roll=2)
        assert result.success is True
        assert result.disarmed is True
        assert "already disarmed" in result.narrative.lower()

    def test_exact_dc_succeeds(self):
        trap = get_trap("falling_net")  # disarm DC 10
        inst = TrapInstance.from_trap(trap)
        inst.discovered = True
        result = attempt_disarm(inst, check_total=10, roll=8)
        assert result.success is True

    def test_method_recorded(self):
        trap = get_trap("hidden_pit")
        inst = TrapInstance.from_trap(trap)
        inst.discovered = True
        result = attempt_disarm(inst, check_total=15, roll=12, method="arcana")
        assert result.method == "arcana"


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------

class TestTrigger:
    def test_basic_damage_trap(self):
        trap = get_trap("hidden_pit")  # 1d6 bludgeoning, no save
        inst = TrapInstance.from_trap(trap)
        result = trigger_trap(inst, roller=lambda n, s: [4])
        assert result.triggered is True
        assert result.damage == 4
        assert result.damage_type == "bludgeoning"
        assert inst.triggered is True
        assert inst.trigger_count == 1

    def test_trap_with_save_success(self):
        trap = get_trap("collapsing_roof")  # 3d6 bludgeoning, DC 15 Dex save
        inst = TrapInstance.from_trap(trap)
        # 3d6 rolls [2, 3, 4] = 9, save succeeds → half → 4
        result = trigger_trap(
            inst,
            save_roll=18, save_modifier=0,
            roller=lambda n, s: [2, 3, 4],
        )
        assert result.triggered is True
        assert result.damage == 4  # 9 // 2
        assert result.save_success is True

    def test_trap_with_save_failure(self):
        trap = get_trap("collapsing_roof")  # 3d6, DC 15
        inst = TrapInstance.from_trap(trap)
        result = trigger_trap(
            inst,
            save_roll=5, save_modifier=0,
            roller=lambda n, s: [2, 3, 4],
        )
        assert result.triggered is True
        assert result.damage == 9  # full damage
        assert result.save_success is False

    def test_condition_trap(self):
        trap = get_trap("falling_net")  # restrained, DC 10 Dex save
        inst = TrapInstance.from_trap(trap)
        result = trigger_trap(inst, save_roll=5, save_modifier=0)
        assert result.triggered is True
        assert "restrained" in result.conditions

    def test_condition_resisted(self):
        trap = get_trap("falling_net")  # DC 10 Dex save
        inst = TrapInstance.from_trap(trap)
        result = trigger_trap(inst, save_roll=18, save_modifier=0)
        assert result.triggered is True
        assert len(result.conditions) == 0  # resisted

    def test_poison_darts_multiple_effects(self):
        trap = get_trap("poison_darts")  # 2d10 piercing DC 15 Dex + poisoned DC 15 Con
        inst = TrapInstance.from_trap(trap)
        result = trigger_trap(
            inst,
            save_roll=5, save_modifier=0,  # fail both saves
            roller=lambda n, s: [10, 10],
        )
        assert result.triggered is True
        assert result.damage == 20  # 2d10
        assert "poisoned" in result.conditions

    def test_trigger_disarmed_trap(self):
        trap = get_trap("hidden_pit")
        inst = TrapInstance.from_trap(trap)
        inst.disarmed = True
        result = trigger_trap(inst, roller=lambda n, s: [6])
        assert result.triggered is False
        assert "already disarmed" in result.narrative.lower()

    def test_trigger_count_increments(self):
        trap = get_trap("hidden_pit")
        inst = TrapInstance.from_trap(trap)
        trigger_trap(inst, roller=lambda n, s: [3])
        trigger_trap(inst, roller=lambda n, s: [3])
        assert inst.trigger_count == 2

    def test_save_none_negates_damage(self):
        """poisoned_needle: save_result='none' → no damage on successful save."""
        trap = get_trap("poisoned_needle")  # 1d10 piercing DC 13 Dex, save_result="none"
        inst = TrapInstance.from_trap(trap)
        result = trigger_trap(
            inst,
            save_roll=18, save_modifier=0,
            roller=lambda n, s: [10],
        )
        assert result.damage == 0
        assert result.save_success is True

    def test_no_save_full_damage(self):
        """hidden_pit has no save → always takes full damage."""
        trap = get_trap("hidden_pit")
        inst = TrapInstance.from_trap(trap)
        result = trigger_trap(inst, roller=lambda n, s: [6])
        assert result.damage == 6
        assert result.save_ability == ""

    def test_teleport_trap(self):
        trap = get_trap("teleportation_trap")
        inst = TrapInstance.from_trap(trap)
        result = trigger_trap(inst, save_roll=5, save_modifier=0)
        assert result.triggered is True
        # Should have at least one effect description mentioning teleport
        assert len(result.effect_descriptions) > 0


# ---------------------------------------------------------------------------
# DM helpers
# ---------------------------------------------------------------------------

class TestDMHelpers:
    def test_trap_summary_empty(self):
        assert trap_summary_for_dm([]) == ""

    def test_trap_summary_all_undiscovered(self):
        trap = get_trap("hidden_pit")
        inst = TrapInstance.from_trap(trap)
        summary = trap_summary_for_dm([inst])
        assert "1 hidden trap" in summary

    def test_trap_summary_mixed(self):
        t1 = TrapInstance.from_trap(get_trap("hidden_pit"))
        t2 = TrapInstance.from_trap(get_trap("collapsing_roof"))
        t2.discovered = True
        summary = trap_summary_for_dm([t1, t2])
        assert "Collapsing Roof" in summary
        assert "1 hidden trap" in summary

    def test_severity_guidelines(self):
        guidelines = severity_guidelines()
        assert "setback" in guidelines
        assert "dangerous" in guidelines
        assert "deadly" in guidelines
        assert "damage" in guidelines["setback"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_trap_with_multiple_damage_effects(self):
        """A trap with multiple damage effects sums them."""
        custom = Trap(
            id="double_hit",
            name="Double Strike",
            description="Two blades strike at once.",
            effects=[
                TrapEffect(type=TrapEffectType.DAMAGE, damage_dice="1d6",
                           damage_type="slashing"),
                TrapEffect(type=TrapEffectType.DAMAGE, damage_dice="1d6",
                           damage_type="piercing"),
            ],
        )
        inst = TrapInstance.from_trap(custom)
        values = iter([4, 5])
        result = trigger_trap(inst, roller=lambda n, s: [next(values)])
        assert result.damage == 9

    def test_failed_disarm_triggers_returns_true(self):
        assert failed_disarm_triggers(TrapInstance.from_trap(get_trap("hidden_pit"))) is True

    def test_trigger_no_effects(self):
        """A trap with no effects still triggers."""
        custom = Trap(
            id="harmless",
            name="Harmless Trap",
            description="It does nothing.",
            effects=[],
        )
        inst = TrapInstance.from_trap(custom)
        result = trigger_trap(inst)
        assert result.triggered is True
        assert result.damage == 0
        assert len(result.conditions) == 0
