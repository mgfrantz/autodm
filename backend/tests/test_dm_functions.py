"""
Tests for DM-callable game functions — thin wrappers around the dice engine
that produce GameEvent objects.
"""
from unittest.mock import patch

import pytest

from app.engine.dice import RollResult
from app.engine.game_events import GameEvent, GameEventType
from app.engine.dm_functions import dm_roll_d20, dm_roll_dice, dm_request_check


class TestDmRollD20:
    """dm_roll_d20 produces correct dice_roll GameEvent."""

    def test_produces_correct_game_event(self):
        with patch("app.engine.dm_functions.roll_d20") as mock_roll:
            mock_roll.return_value = RollResult(
                rolls=[15], modifier=3, total=18,
                description="d20 +3",
            )
            event = dm_roll_d20("Perception Check", modifier=3)
        assert event.type == GameEventType.DICE_ROLL
        assert event.label == "Perception Check"
        assert event.data["rolls"] == [15]
        assert event.data["modifier"] == 3
        assert event.data["total"] == 18

    def test_with_dc_sets_success(self):
        with patch("app.engine.dm_functions.roll_d20") as mock_roll:
            mock_roll.return_value = RollResult(
                rolls=[18], modifier=3, total=21,
                description="d20 +3",
            )
            event = dm_roll_d20("Investigation", modifier=3, dc=15)
        assert event.data["dc"] == 15
        assert event.data["success"] is True

    def test_with_dc_sets_failure(self):
        with patch("app.engine.dm_functions.roll_d20") as mock_roll:
            mock_roll.return_value = RollResult(
                rolls=[5], modifier=3, total=8,
                description="d20 +3",
            )
            event = dm_roll_d20("Investigation", modifier=3, dc=15)
        assert event.data["dc"] == 15
        assert event.data["success"] is False

    def test_with_advantage_produces_two_rolls(self):
        with patch("app.engine.dm_functions.roll_d20") as mock_roll:
            mock_roll.return_value = RollResult(
                rolls=[18, 12], modifier=3, total=21,
                description="d20(advantage) +3",
            )
            event = dm_roll_d20("Attack", modifier=3, advantage=True)
        assert event.data["advantage"] is True
        assert len(event.data["rolls"]) == 2
        assert event.data["rolls"] == [18, 12]

    def test_no_dc_means_success_is_none(self):
        with patch("app.engine.dm_functions.roll_d20") as mock_roll:
            mock_roll.return_value = RollResult(
                rolls=[10], modifier=0, total=10,
                description="d20",
            )
            event = dm_roll_d20("Raw Roll")
        assert event.data["dc"] is None
        assert event.data["success"] is None

    def test_uses_real_randomness(self):
        """Without mocking, dm_roll_d20 should produce valid d20 results."""
        event = dm_roll_d20("Real Roll", modifier=2)
        assert len(event.data["rolls"]) == 1
        assert 1 <= event.data["rolls"][0] <= 20
        assert event.data["total"] == event.data["rolls"][0] + 2


class TestDmRollDice:
    """dm_roll_dice produces correct dice_roll GameEvent for arbitrary dice."""

    def test_produces_correct_roll_count_and_total(self):
        with patch("app.engine.dm_functions.engine_roll_dice") as mock_roll:
            mock_roll.return_value = RollResult(
                rolls=[6, 4, 3], modifier=2, total=15,
                description="3d6+2",
            )
            event = dm_roll_dice("Sneak Attack", count=3, sides=6, modifier=2)
        assert event.type == GameEventType.DICE_ROLL
        assert event.label == "Sneak Attack"
        assert event.data["rolls"] == [6, 4, 3]
        assert event.data["modifier"] == 2
        assert event.data["total"] == 15

    def test_no_modifier(self):
        with patch("app.engine.dm_functions.engine_roll_dice") as mock_roll:
            mock_roll.return_value = RollResult(
                rolls=[5, 3], modifier=0, total=8,
                description="2d6",
            )
            event = dm_roll_dice("Damage", count=2, sides=6)
        assert event.data["modifier"] == 0
        assert event.data["total"] == 8

    def test_uses_real_randomness(self):
        """Without mocking, dm_roll_dice should produce valid results."""
        event = dm_roll_dice("Fire Damage", count=3, sides=6, modifier=0)
        assert len(event.data["rolls"]) == 3
        for r in event.data["rolls"]:
            assert 1 <= r <= 6
        assert event.data["total"] == sum(event.data["rolls"])


class TestDmRequestCheck:
    """dm_request_check produces a check_prompt GameEvent."""

    def test_produces_check_prompt_event(self):
        event = dm_request_check(skill="Perception", dc=15, reason="You hear something.")
        assert event.type == GameEventType.CHECK_PROMPT
        assert event.label == "Perception Check"
        assert event.data["skill"] == "Perception"
        assert event.data["dc"] == 15
        assert event.data["reason"] == "You hear something."

    def test_no_dc(self):
        event = dm_request_check(skill="Investigation")
        assert event.data["dc"] is None
        assert event.data["reason"] == ""

    def test_no_reason(self):
        event = dm_request_check(skill="Stealth", dc=12)
        assert event.data["dc"] == 12
        assert event.data["reason"] == ""
