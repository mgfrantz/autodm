"""Tests for NPC mood detection integration with game narration."""
import pytest
from unittest.mock import MagicMock, patch

from app.api.game import _detect_and_update_npc_mood
from app.engine.world_state import (
    WorldState,
    NPCRelationship,
    extract_world_state_from_game_state,
    merge_world_state_into_game_state,
)


class TestNPCMoodHelper:
    """Test the _detect_and_update_npc_mood helper function."""

    def test_empty_narration_no_changes(self):
        """Test that empty narration doesn't create spurious entries."""
        game_state = {}

        with patch("app.api.game.get_npc_mood_detection_module") as mock_get_module:
            mock_module = MagicMock()
            mock_result = MagicMock()
            mock_result.npc_mood_changes = []
            mock_module.return_value = mock_result
            mock_get_module.return_value = mock_module

            updated = _detect_and_update_npc_mood("", game_state)

        # World state should be present but empty
        assert "world_state" in updated
        assert updated["world_state"]["npc_relationships"] == {}

    def test_detects_positive_mood_change(self):
        """Test detecting a positive mood change (e.g., NPC becomes friendly)."""
        game_state = {}

        with patch("app.api.game.get_npc_mood_detection_module") as mock_get_module:
            mock_module = MagicMock()
            mock_result = MagicMock()
            mock_result.npc_mood_changes = [
                {
                    "npc_name": "Eldrin",
                    "mood_change": "positive",
                    "trust_change": 20,  # 25 would be neutral boundary; 40 for friendly
                    "reason": "NPC appreciates player's help",
                }
            ]
            mock_module.return_value = mock_result
            mock_get_module.return_value = mock_module

            updated = _detect_and_update_npc_mood(
                "Eldrin smiles warmly and thanks you for your assistance.",
                game_state,
            )

        # NPC should be in world_state with positive trust
        world_state = extract_world_state_from_game_state(updated)
        assert "Eldrin" in world_state.npc_relationships
        npc = world_state.npc_relationships["Eldrin"]
        assert npc.trust > 0
        # 20 is neutral (<=25). For friendly we need >25, which requires multiple
        # positive interactions or a single large interaction (beyond -20..20 range).
        # Since signature limits to -20..20 per interaction, we assert neutral here.
        assert npc.attitude == "neutral"
        assert npc.trust == 20

    def test_detects_negative_mood_change(self):
        """Test detecting a negative mood change (e.g., NPC becomes hostile)."""
        game_state = {}

        with patch("app.api.game.get_npc_mood_detection_module") as mock_get_module:
            mock_module = MagicMock()
            mock_result = MagicMock()
            mock_result.npc_mood_changes = [
                {
                    "npc_name": "Guard Captain",
                    "mood_change": "negative",
                    "trust_change": -15,
                    "reason": "NPC disapproves of player's actions",
                }
            ]
            mock_module.return_value = mock_result
            mock_get_module.return_value = mock_module

            updated = _detect_and_update_npc_mood(
                "The guard captain glares at you in disapproval.",
                game_state,
            )

        world_state = extract_world_state_from_game_state(updated)
        assert "Guard Captain" in world_state.npc_relationships
        npc = world_state.npc_relationships["Guard Captain"]
        assert npc.trust < 0
        # -15 is > -25 so still "unfriendly", not "hostile"

    def test_trust_change_clamping(self):
        """Test that trust changes are clamped to -20..20 per signature."""
        game_state = {}

        with patch("app.api.game.get_npc_mood_detection_module") as mock_get_module:
            mock_module = MagicMock()
            mock_result = MagicMock()
            # Try to exceed bounds
            mock_result.npc_mood_changes = [
                {
                    "npc_name": "Test NPC",
                    "mood_change": "positive",
                    "trust_change": 100,  # Should be clamped to 20
                    "reason": "Excessive trust",
                }
            ]
            mock_module.return_value = mock_result
            mock_get_module.return_value = mock_module

            updated = _detect_and_update_npc_mood("Test narration", game_state)

        world_state = extract_world_state_from_game_state(updated)
        npc = world_state.npc_relationships["Test NPC"]
        # Should be clamped to 20
        assert npc.trust == 20

    def test_negative_clamping(self):
        """Test negative clamping to -20."""
        game_state = {}

        with patch("app.api.game.get_npc_mood_detection_module") as mock_get_module:
            mock_module = MagicMock()
            mock_result = MagicMock()
            mock_result.npc_mood_changes = [
                {
                    "npc_name": "Test NPC",
                    "mood_change": "negative",
                    "trust_change": -50,  # Should be clamped to -20
                    "reason": "Excessive distrust",
                }
            ]
            mock_module.return_value = mock_result
            mock_get_module.return_value = mock_module

            updated = _detect_and_update_npc_mood("Test narration", game_state)

        world_state = extract_world_state_from_game_state(updated)
        npc = world_state.npc_relationships["Test NPC"]
        assert npc.trust == -20

    def test_ignores_empty_npc_name(self):
        """Test that entries with empty NPC names are skipped."""
        game_state = {}

        with patch("app.api.game.get_npc_mood_detection_module") as mock_get_module:
            mock_module = MagicMock()
            mock_result = MagicMock()
            mock_result.npc_mood_changes = [
                {"npc_name": "", "mood_change": "positive", "trust_change": 10, "reason": "Empty name"},
                {"npc_name": "   ", "mood_change": "negative", "trust_change": -5, "reason": "Whitespace name"},
            ]
            mock_module.return_value = mock_result
            mock_get_module.return_value = mock_module

            updated = _detect_and_update_npc_mood("Test narration", game_state)

        world_state = extract_world_state_from_game_state(updated)
        # No NPCs should be created
        assert len(world_state.npc_relationships) == 0

    def test_updates_existing_npc(self):
        """Test that an existing NPC's trust is updated (cumulative)."""
        # Start with an existing NPC at trust=10, with an initial interaction
        initial_npc = NPCRelationship(
            npc_name="Eldrin",
            trust=10,
            attitude="neutral",
            interactions=["Initial meeting"],
        )
        world_state = WorldState()
        world_state.npc_relationships["Eldrin"] = initial_npc
        game_state = merge_world_state_into_game_state({}, world_state)

        with patch("app.api.game.get_npc_mood_detection_module") as mock_get_module:
            mock_module = MagicMock()
            mock_result = MagicMock()
            mock_result.npc_mood_changes = [
                {
                    "npc_name": "Eldrin",
                    "mood_change": "positive",
                    "trust_change": 20,
                    "reason": "Another positive interaction",
                }
            ]
            mock_module.return_value = mock_result
            mock_get_module.return_value = mock_module

            updated = _detect_and_update_npc_mood("Eldrin thanks you again", game_state)

        world_state = extract_world_state_from_game_state(updated)
        npc = world_state.npc_relationships["Eldrin"]
        # Trust should be 10 + 20 = 30
        assert npc.trust == 30
        assert npc.attitude == "friendly"  # 30 > 25
        # Should have 2 interactions (initial + this one)
        assert len(npc.interactions) == 2
        assert npc.interactions[0] == "Initial meeting"
        assert npc.interactions[1] == "Another positive interaction"

    def test_handles_dspy_failure_gracefully(self):
        """Test that DSPy failure returns game_state unchanged."""
        game_state = {"existing_key": "value"}

        with patch("app.api.game.get_npc_mood_detection_module") as mock_get_module:
            mock_module = MagicMock()
            mock_module.side_effect = Exception("DSPy failed")
            mock_get_module.return_value = mock_module

            updated = _detect_and_update_npc_mood("Test narration", game_state)

        # Should return unchanged (no world_state added)
        assert updated == game_state

    def test_multiple_npcs_in_one_narration(self):
        """Test detecting mood changes for multiple NPCs in one narration."""
        game_state = {}

        with patch("app.api.game.get_npc_mood_detection_module") as mock_get_module:
            mock_module = MagicMock()
            mock_result = MagicMock()
            mock_result.npc_mood_changes = [
                {
                    "npc_name": "Eldrin",
                    "mood_change": "positive",
                    "trust_change": 10,
                    "reason": "Appreciates help",
                },
                {
                    "npc_name": "Thorne",
                    "mood_change": "negative",
                    "trust_change": -10,
                    "reason": "Disapproves of tactics",
                },
            ]
            mock_module.return_value = mock_result
            mock_get_module.return_value = mock_module

            updated = _detect_and_update_npc_mood(
                "Eldrin thanks you, but Thorne frowns at your methods.",
                game_state,
            )

        world_state = extract_world_state_from_game_state(updated)
        assert "Eldrin" in world_state.npc_relationships
        assert "Thorne" in world_state.npc_relationships
        assert world_state.npc_relationships["Eldrin"].trust > 0
        assert world_state.npc_relationships["Thorne"].trust < 0

    def test_preserves_other_game_state_fields(self):
        """Test that NPC mood updates don't clobber other game_state fields."""
        game_state = {
            "location": "Town Square",
            "in_combat": False,
            "hp": 50,
            "existing_key": "value",
        }

        with patch("app.api.game.get_npc_mood_detection_module") as mock_get_module:
            mock_module = MagicMock()
            mock_result = MagicMock()
            mock_result.npc_mood_changes = [
                {
                    "npc_name": "Eldrin",
                    "mood_change": "positive",
                    "trust_change": 10,
                    "reason": "Test",
                }
            ]
            mock_module.return_value = mock_result
            mock_get_module.return_value = mock_module

            updated = _detect_and_update_npc_mood("Test", game_state)

        assert updated["location"] == "Town Square"
        assert updated["in_combat"] is False
        assert updated["hp"] == 50
        assert updated["existing_key"] == "value"
        assert "world_state" in updated