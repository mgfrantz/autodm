"""
Tests for the DMActionableNarration DSPy signature + module.

Covers: signature existence, module init, successful narration + game_actions
output, graceful failure, and singleton caching.
"""
from unittest.mock import patch

import dspy
import pytest

from app.llm.dspy_signatures import DMActionableNarration
from app.llm.dspy_modules import (
    DMActionableNarrationModule,
    get_dm_actionable_narration_module,
)


class TestDMActionableNarrationSignature:
    """The signature exists and has the expected fields."""

    def test_signature_exists(self):
        assert DMActionableNarration is not None

    def test_has_required_fields(self):
        # Input field
        assert "situation" in DMActionableNarration.input_fields
        # Output fields
        assert "narration" in DMActionableNarration.output_fields
        assert "game_actions" in DMActionableNarration.output_fields


class TestDMActionableNarrationModule:
    """Module initialization + forward() + singleton."""

    def test_module_init(self):
        mod = DMActionableNarrationModule()
        assert mod is not None
        assert hasattr(mod, "generate")

    def test_forward_returns_narration_and_actions(self):
        mod = DMActionableNarrationModule()
        mock_result = dspy.Prediction(
            narration="The goblin snarls.",
            game_actions=[
                {"function": "roll_dice", "label": "Attack",
                 "args": {"sides": 20, "modifier": 5, "dc": 12}},
            ],
        )
        with patch.object(mod, "generate", return_value=mock_result):
            result = mod(situation="A goblin appears.")
        assert result.narration == "The goblin snarls."
        assert len(result.game_actions) == 1
        assert result.game_actions[0]["function"] == "roll_dice"

    def test_forward_returns_empty_actions(self):
        mod = DMActionableNarrationModule()
        mock_result = dspy.Prediction(
            narration="The sun sets peacefully.",
            game_actions=[],
        )
        with patch.object(mod, "generate", return_value=mock_result):
            result = mod(situation="Evening falls.")
        assert result.narration == "The sun sets peacefully."
        assert result.game_actions == []

    def test_forward_failure_returns_empty(self):
        mod = DMActionableNarrationModule()
        with patch.object(mod, "generate", side_effect=RuntimeError("boom")):
            result = mod(situation="A dragon approaches.")
        assert result.narration == ""
        assert result.game_actions == []

    def test_singleton_is_cached(self):
        first = get_dm_actionable_narration_module()
        assert get_dm_actionable_narration_module() is first
