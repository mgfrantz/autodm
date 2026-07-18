"""
Tests for the DM-callable concentration functions (Phase 3.5) —
``dm_start_concentration``, ``dm_end_concentration``, and
``dm_check_concentration`` wrap the real concentration engine and produce
``concentration`` GameEvents.
"""
import pytest

from app.engine.game_events import GameEvent, GameEventType
from app.engine.dm_functions import (
    dm_start_concentration,
    dm_end_concentration,
    dm_check_concentration,
)
from app.engine.concentration import ConcentrationState


# =========================================================================== #
# dm_start_concentration
# =========================================================================== #

class TestDmStartConcentration:
    """dm_start_concentration wraps concentration.start_concentration."""

    def test_start_basic(self):
        event = dm_start_concentration("Shield", "shield")
        assert event.type == GameEventType.CONCENTRATION
        assert event.data["operation"] == "started"
        assert event.data["spell_name"] == "Shield"
        assert event.data["spell_id"] == "shield"
        assert event.data["success"] is True

    def test_start_includes_reason(self):
        event = dm_start_concentration("Hold Person", "hold_person")
        assert event.data["reason"] == "Concentration spell cast"

    def test_start_label_has_spell(self):
        event = dm_start_concentration("Bless", "bless")
        assert "Bless" in event.label

    def test_start_empty_spell_name(self):
        event = dm_start_concentration("", "")
        assert event.data["operation"] == "started"
        assert event.data["success"] is True


# =========================================================================== #
# dm_end_concentration
# =========================================================================== #

class TestDmEndConcentration:
    """dm_end_concentration wraps concentration.end_concentration."""

    def test_end_basic(self):
        event = dm_end_concentration(spell_name="Shield")
        assert event.type == GameEventType.CONCENTRATION
        assert event.data["operation"] == "ended"
        assert event.data["spell_name"] == "Shield"
        assert event.data["success"] is True

    def test_end_with_reason(self):
        event = dm_end_concentration(spell_name="Hold Person", reason="Player drops spell")
        assert event.data["reason"] == "Player drops spell"

    def test_end_no_spell_name(self):
        event = dm_end_concentration()
        assert event.data["operation"] == "ended"
        assert event.data["success"] is True

    def test_end_default_reason(self):
        event = dm_end_concentration(spell_name="Bless")
        assert event.data["reason"] == "Concentration ended"

    def test_end_label_has_spell(self):
        event = dm_end_concentration(spell_name="Shield")
        assert "Shield" in event.label


# =========================================================================== #
# dm_check_concentration
# =========================================================================== #

class TestDmCheckConcentration:
    """dm_check_concentration wraps concentration.check_concentration."""

    def test_check_returns_event(self):
        event = dm_check_concentration(
            spell_name="Shield",
            damage_taken=10,
            con_score=14,
            proficiency_bonus=2,
            con_proficient=True,
        )
        assert event.type == GameEventType.CONCENTRATION
        assert event.data["operation"] in ("check_passed", "check_failed")
        assert event.data["spell_name"] == "Shield"
        assert event.data["damage_taken"] == 10

    def test_check_dc_is_half_damage_or_10(self):
        # DC = max(10, damage // 2). 10 damage → DC 10. 30 damage → DC 15.
        event = dm_check_concentration(
            spell_name="Shield", damage_taken=30, con_score=10, proficiency_bonus=0,
        )
        assert event.data["concentration_dc"] == 15

    def test_check_dc_minimum_10(self):
        event = dm_check_concentration(
            spell_name="Shield", damage_taken=5, con_score=10, proficiency_bonus=0,
        )
        assert event.data["concentration_dc"] == 10

    def test_check_includes_roll_total(self):
        event = dm_check_concentration(
            spell_name="Shield", damage_taken=10, con_score=14, proficiency_bonus=2,
        )
        assert event.data["roll_total"] is not None
        assert isinstance(event.data["roll_total"], int)

    def test_check_passed_vs_failed_label(self):
        event = dm_check_concentration(
            spell_name="Shield", damage_taken=10, con_score=14, proficiency_bonus=2,
        )
        if event.data["operation"] == "check_passed":
            assert "held" in event.label.lower()
        else:
            assert "lost" in event.label.lower()

    def test_check_reason_includes_breakdown(self):
        event = dm_check_concentration(
            spell_name="Shield", damage_taken=10, con_score=14, proficiency_bonus=2,
        )
        assert "DC" in event.data["reason"]

    def test_check_check_passed_operation(self):
        # Very high Con + proficiency should usually pass vs DC 10.
        # Run multiple times to be robust against random rolls.
        results = [
            dm_check_concentration(
                spell_name="Shield", damage_taken=1, con_score=30, proficiency_bonus=6,
                con_proficient=True,
            ).data["operation"]
            for _ in range(5)
        ]
        assert all(op == "check_passed" for op in results), results

    def test_check_check_failed_operation(self):
        # Con 1 (mod -5), no prof, high damage DC, should usually fail.
        results = [
            dm_check_concentration(
                spell_name="Shield", damage_taken=40, con_score=1, proficiency_bonus=0,
            ).data["operation"]
            for _ in range(5)
        ]
        assert all(op == "check_failed" for op in results), results


# =========================================================================== #
# Serialization
# =========================================================================== #

class TestSerialization:
    """GameEvent.concentration serializes correctly."""

    def test_started_round_trip(self):
        event = dm_start_concentration("Shield", "shield")
        d = event.to_dict()
        assert d["type"] == "concentration"
        assert d["data"]["operation"] == "started"
        restored = GameEvent(
            type=GameEventType(d["type"]),
            label=d["label"],
            data=d["data"],
        )
        assert restored.data["spell_name"] == "Shield"

    def test_check_round_trip(self):
        event = dm_check_concentration(
            spell_name="Bless", damage_taken=12, con_score=10, proficiency_bonus=2,
        )
        d = event.to_dict()
        assert d["data"]["damage_taken"] == 12
        assert d["data"]["concentration_dc"] is not None

    def test_failed_event_serializes(self):
        event = dm_end_concentration(spell_name="Shield", reason="test")
        d = event.to_dict()
        assert d["data"]["success"] is True

    def test_concentration_in_enum(self):
        assert GameEventType.CONCENTRATION.value == "concentration"
