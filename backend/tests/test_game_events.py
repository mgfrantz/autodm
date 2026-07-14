"""
Tests for the GameEvent system — construction, serialization, factory
classmethods, enum values, and JSON round-trip.
"""
import json
from datetime import datetime

import pytest

from app.engine.game_events import GameEvent, GameEventType


class TestGameEventType:
    """GameEventType enum is string-valued and JSON-serializable."""

    def test_enum_values_are_strings(self):
        assert GameEventType.DICE_ROLL.value == "dice_roll"
        assert GameEventType.CHECK_PROMPT.value == "check_prompt"

    def test_enum_is_json_serializable(self):
        data = {"type": GameEventType.DICE_ROLL.value}
        assert json.dumps(data) == '{"type": "dice_roll"}'


class TestGameEventConstruction:
    """Direct GameEvent construction + to_dict()."""

    def test_basic_construction(self):
        event = GameEvent(
            type=GameEventType.DICE_ROLL,
            label="Perception Check",
            data={"rolls": [18], "modifier": 3, "total": 21},
        )
        assert event.type == GameEventType.DICE_ROLL
        assert event.label == "Perception Check"
        assert event.data["rolls"] == [18]
        assert event.data["total"] == 21

    def test_timestamp_is_set_automatically(self):
        event = GameEvent(type=GameEventType.DICE_ROLL, label="Test")
        assert event.timestamp != ""
        # Should be a valid ISO format string
        datetime.fromisoformat(event.timestamp)

    def test_explicit_timestamp_is_preserved(self):
        ts = "2025-07-14T12:00:00+00:00"
        event = GameEvent(type=GameEventType.DICE_ROLL, label="Test", timestamp=ts)
        assert event.timestamp == ts

    def test_to_dict_serialization(self):
        event = GameEvent(
            type=GameEventType.CHECK_PROMPT,
            label="Perception Check",
            data={"skill": "Perception", "dc": 15},
        )
        d = event.to_dict()
        assert d["type"] == "check_prompt"
        assert d["label"] == "Perception Check"
        assert d["data"]["skill"] == "Perception"
        assert d["data"]["dc"] == 15
        assert "timestamp" in d

    def test_to_dict_is_json_serializable(self):
        event = GameEvent.dice_roll("Attack", [17], 5, 22, dc=15, success=True)
        d = event.to_dict()
        # Should not raise
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["type"] == "dice_roll"
        assert parsed["data"]["total"] == 22


class TestGameEventFactories:
    """Factory classmethods produce correct type/label/data."""

    def test_dice_roll_factory(self):
        event = GameEvent.dice_roll(
            label="Attack vs Goblin",
            rolls=[17],
            modifier=5,
            total=22,
            dc=15,
            success=True,
        )
        assert event.type == GameEventType.DICE_ROLL
        assert event.label == "Attack vs Goblin"
        assert event.data["rolls"] == [17]
        assert event.data["modifier"] == 5
        assert event.data["total"] == 22
        assert event.data["dc"] == 15
        assert event.data["success"] is True

    def test_dice_roll_factory_no_dc(self):
        event = GameEvent.dice_roll(
            label="Damage",
            rolls=[6, 4],
            modifier=2,
            total=12,
        )
        assert event.data["dc"] is None
        assert event.data["success"] is None
        assert event.data["advantage"] is False
        assert event.data["disadvantage"] is False

    def test_dice_roll_factory_with_advantage(self):
        event = GameEvent.dice_roll(
            label="Perception",
            rolls=[18, 12],
            modifier=3,
            total=21,
            advantage=True,
        )
        assert event.data["advantage"] is True
        assert event.data["disadvantage"] is False
        assert len(event.data["rolls"]) == 2

    def test_check_prompt_factory(self):
        event = GameEvent.check_prompt(
            skill="Perception",
            dc=15,
            reason="You hear a faint sound.",
        )
        assert event.type == GameEventType.CHECK_PROMPT
        assert event.label == "Perception Check"
        assert event.data["skill"] == "Perception"
        assert event.data["dc"] == 15
        assert event.data["reason"] == "You hear a faint sound."

    def test_check_prompt_factory_no_dc(self):
        event = GameEvent.check_prompt(skill="Investigation")
        assert event.data["dc"] is None
        assert event.data["reason"] == ""


class TestGameEventRoundTrip:
    """to_dict() → JSON → parse → matches original."""

    def test_dice_roll_round_trip(self):
        original = GameEvent.dice_roll(
            label="Attack",
            rolls=[17, 12],
            modifier=5,
            total=22,
            dc=15,
            success=True,
            advantage=True,
        )
        d = original.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["type"] == "dice_roll"
        assert parsed["label"] == "Attack"
        assert parsed["data"]["rolls"] == [17, 12]
        assert parsed["data"]["modifier"] == 5
        assert parsed["data"]["total"] == 22
        assert parsed["data"]["dc"] == 15
        assert parsed["data"]["success"] is True
        assert parsed["data"]["advantage"] is True

    def test_check_prompt_round_trip(self):
        original = GameEvent.check_prompt(
            skill="Stealth",
            dc=12,
            reason="Sneaking past guards.",
        )
        d = original.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["type"] == "check_prompt"
        assert parsed["label"] == "Stealth Check"
        assert parsed["data"]["skill"] == "Stealth"
        assert parsed["data"]["dc"] == 12
        assert parsed["data"]["reason"] == "Sneaking past guards."
