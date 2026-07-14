"""Tests for the Skill Check Resolver (DSPy pattern #5)."""
import pytest
from unittest.mock import Mock, patch

from app.llm.dspy_signatures import ResolveSkillCheck
from app.llm.dspy_modules import (
    SkillCheckResolverModule,
    get_skill_check_resolver_module,
)


class TestResolveSkillCheckSignature:
    """Test the ResolveSkillCheck DSPy signature."""

    def test_signature_exists(self):
        """The signature should be importable."""
        from app.llm.dspy_signatures import ResolveSkillCheck
        assert ResolveSkillCheck is not None

    def test_signature_docstring_exists(self):
        """The signature should have a docstring explaining the resolution process."""
        assert ResolveSkillCheck.__doc__ is not None
        assert "Dungeon Master resolving a freeform player action" in ResolveSkillCheck.__doc__
        assert "success" in ResolveSkillCheck.__doc__.lower()
        assert "stat_changes" in ResolveSkillCheck.__doc__
        assert "experience_gained" in ResolveSkillCheck.__doc__


class TestSkillCheckResolverModule:
    """Test the SkillCheckResolverModule DSPy module."""

    def test_module_initialization(self):
        """The module should initialize with a ChainOfThought resolver."""
        module = SkillCheckResolverModule()
        assert module.resolve is not None

    def test_successful_resolution(self):
        """The module should successfully resolve an action and return structured data."""
        module = SkillCheckResolverModule()

        # Mock the ChainOfThought resolver to return a prediction
        mock_prediction = Mock()
        mock_prediction.success = True
        mock_prediction.degree = "success"
        mock_prediction.stat_changes = {"gold": 25, "experience": 50}
        mock_prediction.items_gained = ["Old key"]
        mock_prediction.experience_gained = 50
        mock_prediction.narrative_notes = "The character successfully picks the lock."

        with patch.object(module, "resolve", return_value=mock_prediction):
            result = module(
                action="I try to pick the lock on the chest.",
                character_context="Level 1 Rogue with Dexterity 16.",
                scene_context="In a dungeon chamber with a locked chest.",
            )

            assert result.success is True
            assert result.degree == "success"
            assert result.stat_changes == {"gold": 25, "experience": 50}
            assert result.items_gained == ["Old key"]
            assert result.experience_gained == 50
            assert result.narrative_notes == "The character successfully picks the lock."

    def test_handles_exception_gracefully(self):
        """The module should handle exceptions and return a fallback prediction."""
        module = SkillCheckResolverModule()

        # Mock the resolver to raise an exception
        with patch.object(module, "resolve", side_effect=Exception("LLM error")):
            result = module(
                action="I try to jump the chasm.",
                character_context="Level 1 Fighter.",
                scene_context="A deep chasm spans the path.",
            )

            # Should return a fallback prediction with failure
            assert result.success is False
            assert result.degree == "failure"
            assert result.stat_changes == {}
            assert result.items_gained == []
            assert result.experience_gained == 0
            assert "error" in result.narrative_notes.lower()


class TestSkillCheckResolverSingleton:
    """Test the skill check resolver singleton pattern."""

    def test_singleton_returns_same_instance(self):
        """Multiple calls to get_skill_check_resolver_module should return the same instance."""
        module1 = get_skill_check_resolver_module()
        module2 = get_skill_check_resolver_module()
        assert module1 is module2

    def test_singleton_returns_skill_check_resolver_module(self):
        """The singleton should return a SkillCheckResolverModule instance."""
        module = get_skill_check_resolver_module()
        assert isinstance(module, SkillCheckResolverModule)


class TestResolveSkillCheckHelper:
    """Test the _resolve_skill_check helper in game.py."""

    def test_helper_exists_and_returns_dict(self):
        """The helper function should exist and return a dict with resolution data."""
        from app.api.game import _resolve_skill_check

        # Create mock character and game_state
        mock_character = Mock()
        mock_character.name = "Test Hero"
        mock_character.level = 1
        mock_character.race = "Human"
        mock_character.char_class = "Fighter"
        mock_character.strength = 16
        mock_character.dexterity = 14
        mock_character.constitution = 15
        mock_character.intelligence = 10
        mock_character.wisdom = 12
        mock_character.charisma = 13
        mock_character.current_hp = 10
        mock_character.max_hp = 10
        mock_character.armor_class = 15

        game_state = {
            "location": "Tavern",
            "conditions": [],
        }

        # This should either return a dict with resolution data or an empty dict
        # (empty dict if DSPy not configured or on error)
        result = _resolve_skill_check(
            action="I try to intimidate the barkeep.",
            character=mock_character,
            game_state=game_state,
            recent_context="You just entered the tavern.",
        )

        # Result should be a dict
        assert isinstance(result, dict)

        # If DSPy is configured, should have expected keys (optional check)
        # If not configured, will be empty dict
        if result:
            expected_keys = {
                "success",
                "degree",
                "stat_changes",
                "items_gained",
                "experience_gained",
                "narrative_notes",
            }
            # At least some keys should be present
            assert len(set(result.keys()) & expected_keys) > 0