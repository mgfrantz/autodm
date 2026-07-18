"""
Tests for the DM-callable condition functions (Phase 5) —
``dm_apply_condition`` and ``dm_remove_condition`` wrap the real conditions
engine and produce ``condition_applied`` GameEvents.
"""
import pytest

from app.engine.game_events import GameEvent, GameEventType
from app.engine.dm_functions import (
    dm_apply_condition,
    dm_remove_condition,
    _norm_condition,
)
from app.engine.conditions import CONDITIONS


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

class _Target:
    """Minimal combatant-like object for the conditions engine."""

    def __init__(self, name="Goblin", conditions=None, condition_durations=None):
        self.name = name
        self.conditions = list(conditions or [])
        self.condition_durations = dict(condition_durations or {})


# =========================================================================== #
# _norm_condition
# =========================================================================== #

class TestNormCondition:
    """_norm_condition normalises DM-supplied condition strings."""

    def test_lowercase(self):
        assert _norm_condition("Poisoned") == "poisoned"

    def test_spaces_to_underscores(self):
        assert _norm_condition("knocked prone") == "knocked_prone"

    def test_hyphens_to_underscores(self):
        assert _norm_condition("stunned-effect") == "stunned_effect"

    def test_empty(self):
        assert _norm_condition("") == ""

    def test_none(self):
        assert _norm_condition(None) == ""


# =========================================================================== #
# dm_apply_condition
# =========================================================================== #

class TestDmApplyCondition:
    """dm_apply_condition wraps conditions.apply_condition and returns events."""

    def test_apply_valid_condition(self):
        target = _Target(name="Player")
        event = dm_apply_condition(target, "poisoned")
        assert event.type == GameEventType.CONDITION_APPLIED
        assert event.data["operation"] == "applied"
        assert event.data["condition"] == "poisoned"
        assert event.data["target"] == "Player"
        assert event.data["success"] is True
        assert "poisoned" in target.conditions

    def test_apply_case_insensitive(self):
        target = _Target()
        event = dm_apply_condition(target, "POISONED")
        assert event.data["condition"] == "poisoned"
        assert event.data["success"] is True
        assert "poisoned" in target.conditions

    def test_apply_with_duration(self):
        target = _Target()
        event = dm_apply_condition(target, "frightened", duration=3)
        assert event.data["success"] is True
        assert event.data["duration"] == 3
        assert target.condition_durations["frightened"] == 3

    def test_apply_permanent_duration_is_none(self):
        target = _Target()
        event = dm_apply_condition(target, "blinded")
        assert event.data["duration"] is None

    def test_apply_includes_description(self):
        target = _Target()
        event = dm_apply_condition(target, "poisoned")
        assert event.data["description"]
        assert "disadvantage" in event.data["description"]

    def test_apply_already_present_refreshes(self):
        target = _Target(conditions=["poisoned"], condition_durations={"poisoned": 1})
        event = dm_apply_condition(target, "poisoned", duration=5)
        assert event.data["success"] is True
        # Duration refreshed to 5.
        assert target.condition_durations["poisoned"] == 5

    def test_apply_invalid_condition_returns_failed_event(self):
        target = _Target()
        event = dm_apply_condition(target, "bogus")
        assert event.data["success"] is False
        assert "Unknown condition" in event.data["message"]
        assert "bogus" not in target.conditions

    def test_apply_invalid_condition_lists_valid(self):
        target = _Target()
        event = dm_apply_condition(target, "bogus")
        # The message should mention at least one valid condition.
        assert "poisoned" in event.data["message"]

    def test_apply_label_includes_duration(self):
        target = _Target(name="Goblin")
        event = dm_apply_condition(target, "stunned", duration=2)
        assert "2 rounds" in event.label
        assert "Goblin" in event.label

    def test_apply_label_singular_duration(self):
        target = _Target()
        event = dm_apply_condition(target, "stunned", duration=1)
        assert "1 round" in event.label
        assert "rounds" not in event.label.split("(")[1]

    def test_apply_all_fourteen_conditions(self):
        """Every core DnD 5e condition can be applied."""
        for name in CONDITIONS:
            target = _Target()
            event = dm_apply_condition(target, name)
            assert event.data["success"] is True, f"Failed for {name}"
            assert name in target.conditions


# =========================================================================== #
# dm_remove_condition
# =========================================================================== #

class TestDmRemoveCondition:
    """dm_remove_condition wraps conditions.remove_condition and returns events."""

    def test_remove_present_condition(self):
        target = _Target(conditions=["poisoned", "blinded"])
        event = dm_remove_condition(target, "poisoned")
        assert event.type == GameEventType.CONDITION_APPLIED
        assert event.data["operation"] == "removed"
        assert event.data["condition"] == "poisoned"
        assert event.data["success"] is True
        assert "poisoned" not in target.conditions
        assert "blinded" in target.conditions

    def test_remove_absent_condition_returns_failed(self):
        target = _Target(conditions=["blinded"])
        event = dm_remove_condition(target, "poisoned")
        assert event.data["success"] is False
        assert "did not have" in event.data["message"]

    def test_remove_invalid_condition_returns_failed(self):
        target = _Target()
        event = dm_remove_condition(target, "bogus")
        assert event.data["success"] is False
        assert "Unknown condition" in event.data["message"]

    def test_remove_case_insensitive(self):
        target = _Target(conditions=["frightened"])
        event = dm_remove_condition(target, "FRIGHTENED")
        assert event.data["success"] is True
        assert "frightened" not in target.conditions

    def test_remove_includes_description(self):
        target = _Target(conditions=["restrained"])
        event = dm_remove_condition(target, "restrained")
        assert event.data["description"]
        assert "speed" in event.data["description"].lower()

    def test_remove_clears_duration(self):
        target = _Target(
            conditions=["poisoned"],
            condition_durations={"poisoned": 3},
        )
        dm_remove_condition(target, "poisoned")
        assert "poisoned" not in target.condition_durations

    def test_remove_label(self):
        target = _Target(name="Ogre", conditions=["stunned"])
        event = dm_remove_condition(target, "stunned")
        assert "Ogre" in event.label
        assert "no longer" in event.label


# =========================================================================== #
# Event serialization
# =========================================================================== #

class TestConditionEventSerialization:
    """condition_applied events serialize cleanly for SSE/API responses."""

    def test_to_dict_round_trip(self):
        target = _Target(name="Player")
        event = dm_apply_condition(target, "paralyzed", duration=2)
        d = event.to_dict()
        assert d["type"] == "condition_applied"
        assert d["data"]["condition"] == "paralyzed"
        assert d["data"]["operation"] == "applied"
        assert d["data"]["duration"] == 2
        assert d["data"]["success"] is True
        assert "timestamp" in d

    def test_failed_event_has_message(self):
        target = _Target()
        event = dm_apply_condition(target, "bogus")
        d = event.to_dict()
        assert d["data"]["success"] is False
        assert d["data"]["message"]

    def test_removed_event_to_dict(self):
        target = _Target(conditions=["blinded"])
        event = dm_remove_condition(target, "blinded")
        d = event.to_dict()
        assert d["data"]["operation"] == "removed"
        assert d["data"]["success"] is True
