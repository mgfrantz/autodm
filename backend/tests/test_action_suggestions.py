"""Tests for action suggestions generation (DSPy pattern #4)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.dspy_modules import ActionSuggestionsModule, get_action_suggestions_module
from app.llm.dspy_signatures import GenerateActionSuggestions


@pytest.fixture
def mock_dspy_lm():
    """Mock the DSPy LM configuration."""
    with patch("app.llm.dspy_config.ensure_dspy_configured"):
        yield


@pytest.fixture
def action_suggestions_module():
    """Fixture providing a clean ActionSuggestionsModule instance."""
    return ActionSuggestionsModule()


class TestActionSuggestionsModule:
    """Tests for the ActionSuggestionsModule."""

    def test_module_initialization(self, action_suggestions_module):
        """Test that the module initializes correctly."""
        assert hasattr(action_suggestions_module, "generate")
        assert action_suggestions_module.generate is not None

    def test_successful_suggestion_generation(self, action_suggestions_module):
        """Test successful action suggestions generation."""
        mock_result = MagicMock()
        mock_result.action_suggestions = [
            "Ask the innkeeper about rumors",
            "Search the chest for traps",
            "Inspect the ancient mural",
            "Approach the mysterious stranger",
        ]
        action_suggestions_module.generate = MagicMock(return_value=mock_result)

        narration = "You enter the bustling tavern. The innkeeper waves at you from behind the bar, and a hooded figure sits in the corner. An old chest rests near the fireplace."

        result = action_suggestions_module(narration=narration)

        assert result.action_suggestions == [
            "Ask the innkeeper about rumors",
            "Search the chest for traps",
            "Inspect the ancient mural",
            "Approach the mysterious stranger",
        ]

    def test_returns_raw_suggestions_from_llm(self, action_suggestions_module):
        """Test that the module returns raw suggestions from the LLM without filtering."""
        mock_result = MagicMock()
        mock_result.action_suggestions = [
            "Ask the guard",
            "",
            "  ",
            "Search the room",
            None,
        ]
        action_suggestions_module.generate = MagicMock(return_value=mock_result)

        narration = "You see a guard and a room."

        result = action_suggestions_module(narration=narration)

        # Module returns raw results; filtering happens in _generate_action_suggestions helper
        assert result.action_suggestions == [
            "Ask the guard",
            "",
            "  ",
            "Search the room",
            None,
        ]

    def test_handles_exception_gracefully(self, action_suggestions_module):
        """Test that exceptions are caught and return empty list."""
        action_suggestions_module.generate = MagicMock(side_effect=Exception("LLM error"))

        narration = "Test narration"

        result = action_suggestions_module(narration=narration)

        assert result.action_suggestions == []


class TestActionSuggestionsHelper:
    """Tests for the _generate_action_suggestions helper in game.py."""

    @pytest.mark.asyncio
    async def test_generate_action_suggestions_integration(self):
        """Test the _generate_action_suggestions helper function."""
        # Import here to avoid circular imports
        from app.api.game import _generate_action_suggestions

        with patch("app.api.game.ensure_dspy_configured"), \
             patch("app.api.game.get_action_suggestions_module") as mock_get_module:

            mock_module = MagicMock()
            mock_result = MagicMock()
            mock_result.action_suggestions = [
                "Attack the goblin",
                "Talk to the merchant",
                "Search the chest",
            ]
            mock_module.return_value = mock_result
            mock_get_module.return_value = mock_module

            narration = "A goblin stands guard while a merchant watches nervously. A chest sits behind them."

            suggestions = _generate_action_suggestions(narration)

            assert suggestions == [
                "Attack the goblin",
                "Talk to the merchant",
                "Search the chest",
            ]
            mock_module.assert_called_once_with(narration=narration)

    @pytest.mark.asyncio
    async def test_generate_action_suggestions_exception(self):
        """Test that _generate_action_suggestions returns empty list on exception."""
        from app.api.game import _generate_action_suggestions

        with patch("app.api.game.ensure_dspy_configured"), \
             patch("app.api.game.get_action_suggestions_module") as mock_get_module:

            mock_get_module.side_effect = Exception("LLM error")

            narration = "Test narration"

            suggestions = _generate_action_suggestions(narration)

            assert suggestions == []

    @pytest.mark.asyncio
    async def test_generate_action_suggestions_strips_whitespace(self):
        """Test that suggestions are stripped of leading/trailing whitespace."""
        from app.api.game import _generate_action_suggestions

        with patch("app.api.game.ensure_dspy_configured"), \
             patch("app.api.game.get_action_suggestions_module") as mock_get_module:

            mock_module = MagicMock()
            mock_result = MagicMock()
            mock_result.action_suggestions = [
                "  Attack the goblin  ",
                "\tTalk to the merchant\n",
                "Search the chest",
            ]
            mock_module.return_value = mock_result
            mock_get_module.return_value = mock_module

            narration = "Test narration"

            suggestions = _generate_action_suggestions(narration)

            assert suggestions == [
                "Attack the goblin",
                "Talk to the merchant",
                "Search the chest",
            ]


class TestActionSuggestionsSignature:
    """Tests for the GenerateActionSuggestions signature."""

    def test_signature_docstring_exists(self):
        """Test that the signature has a helpful docstring."""
        assert GenerateActionSuggestions.__doc__ is not None
        assert "action suggestions" in GenerateActionSuggestions.__doc__.lower()


class TestActionSuggestionsSingleton:
    """Tests for the ActionSuggestionsModule singleton accessor."""

    def test_singleton_returns_same_instance(self):
        """Test that get_action_suggestions_module returns the same instance."""
        module1 = get_action_suggestions_module()
        module2 = get_action_suggestions_module()

        assert module1 is module2

    def test_singleton_returns_action_suggestions_module(self):
        """Test that the singleton returns the correct module type."""
        module = get_action_suggestions_module()

        assert isinstance(module, ActionSuggestionsModule)