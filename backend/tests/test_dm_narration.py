"""
Tests for DM narration — DSPy-mediated non-streaming narration endpoints.

Covers the DMNarrationModule, the _dm_narrate threadpool wrapper, and the
POST /api/game/{id}/start and /action endpoints (non-streaming variants).
"""
import json
from unittest.mock import patch, AsyncMock

import dspy
import pytest

from app.models.models import Character, World, GameSave
from app.llm.dspy_modules import DMNarrationModule, get_dm_narration_module


def _make_game_save(db_session, story_log=None):
    """Create a character + world + game save in the test DB."""
    char = Character(
        name="Lyra", race="Elf", char_class="Wizard", level=3,
        strength=8, dexterity=14, constitution=12, intelligence=18,
        wisdom=15, charisma=10, max_hp=24, current_hp=24, armor_class=13,
    )
    world = World(
        name="The Shattered Vale",
        description="A land broken by ancient magic.",
        world_data=json.dumps({
            "description": "A land broken by ancient magic.",
            "starting_settlement": {"name": "Oakhaven"},
            "hook": "A strange light pulses from the old tower.",
        }),
        tone="heroic fantasy",
    )
    db_session.add(char)
    db_session.add(world)
    db_session.commit()
    db_session.refresh(char)
    db_session.refresh(world)
    save = GameSave(
        name="Test Adventure",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps({
            "location": "Oakhaven",
            "visited_locations": ["Oakhaven"],
            "conditions": [],
            "in_combat": False,
        }),
        story_log=json.dumps(story_log or []),
    )
    db_session.add(save)
    db_session.commit()
    db_session.refresh(save)
    return char, world, save


# ---------------------------------------------------------------------------
# Module tests
# ---------------------------------------------------------------------------

class TestDMNarrationModule:
    """Test the DMNarrationModule singleton + graceful failure."""

    def test_singleton_is_cached(self):
        first = get_dm_narration_module()
        assert get_dm_narration_module() is first

    def test_forward_returns_narration(self):
        mod = DMNarrationModule()
        mock_result = dspy.Prediction(narration="The tavern falls silent.")
        with patch.object(mod, "generate", return_value=mock_result):
            result = mod(situation="The hero enters the tavern.")
        assert result.narration == "The tavern falls silent."

    def test_forward_failure_returns_empty(self):
        mod = DMNarrationModule()
        with patch.object(mod, "generate", side_effect=RuntimeError("boom")):
            result = mod(situation="A dragon approaches.")
        assert result.narration == ""


# ---------------------------------------------------------------------------
# Start endpoint tests
# ---------------------------------------------------------------------------

class TestStartAdventure:
    """Test POST /api/game/{game_id}/start (non-streaming)."""

    def test_start_returns_narration(self, client, db_session):
        _, _, save = _make_game_save(db_session)
        with patch("app.api.game._dm_narrate", new=AsyncMock(return_value="The adventure begins in Oakhaven.")):
            response = client.post(f"/api/game/{save.id}/start")
        assert response.status_code == 200
        assert "adventure begins" in response.json()["narration"]

    def test_start_persists_to_story_log(self, client, db_session):
        _, _, save = _make_game_save(db_session)
        with patch("app.api.game._dm_narrate", new=AsyncMock(return_value="Opening scene.")):
            client.post(f"/api/game/{save.id}/start")
        db_session.expire_all()
        refreshed = db_session.query(GameSave).filter(GameSave.id == save.id).first()
        log = json.loads(refreshed.story_log)
        assert len(log) == 1
        assert log[0]["role"] == "dm"
        assert log[0]["content"] == "Opening scene."

    def test_start_missing_game_404(self, client, db_session):
        with patch("app.api.game._dm_narrate", new=AsyncMock(return_value="x")):
            response = client.post("/api/game/9999/start")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Action endpoint tests
# ---------------------------------------------------------------------------

class TestPlayerAction:
    """Test POST /api/game/{game_id}/action (non-streaming)."""

    def test_action_returns_narration(self, client, db_session):
        _, _, save = _make_game_save(db_session)
        with patch("app.api.game._dm_narrate", new=AsyncMock(return_value="The door creaks open.")):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I open the door."},
            )
        assert response.status_code == 200
        data = response.json()
        assert "creaks open" in data["narration"]
        assert data["combat_active"] is False

    def test_action_logs_player_and_dm(self, client, db_session):
        _, _, save = _make_game_save(db_session)
        with patch("app.api.game._dm_narrate", new=AsyncMock(return_value="A goblin appears!")):
            client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I attack the goblin."},
            )
        db_session.expire_all()
        refreshed = db_session.query(GameSave).filter(GameSave.id == save.id).first()
        log = json.loads(refreshed.story_log)
        assert len(log) == 2
        assert log[0]["role"] == "player"
        assert log[0]["content"] == "I attack the goblin."
        assert log[1]["role"] == "dm"
        assert log[1]["content"] == "A goblin appears!"

    def test_action_missing_game_404(self, client, db_session):
        with patch("app.api.game._dm_narrate", new=AsyncMock(return_value="x")):
            response = client.post(
                "/api/game/9999/action",
                json={"action": "look"},
            )
        assert response.status_code == 404

    def test_action_with_combat_flag(self, client, db_session):
        """When in_combat is true in game_state, the response reflects it."""
        _, _, save = _make_game_save(db_session)
        # Set combat flag
        save.game_state = json.dumps({"in_combat": True, "location": "Dungeon", "conditions": []})
        db_session.commit()

        with patch("app.api.game._dm_narrate", new=AsyncMock(return_value="You strike!")):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I swing my sword."},
            )
        assert response.status_code == 200
        assert response.json()["combat_active"] is True
