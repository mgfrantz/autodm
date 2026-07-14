"""Tests for the quests API.

These tests use the shared, isolated test fixtures from ``conftest.py``
(``db_session``, ``client``, ``character``, ``world``) so they run against the
throwaway test database — never the real ``backend/data/dnd_game.db``. A local
``game_save`` fixture composes the conftest ``character`` + ``world`` fixtures.
"""
import json
import pytest

from app.models.models import GameSave


@pytest.fixture
def game_save(db_session, character, world):
    """Create a test game save linked to the conftest character + world."""
    game_state = {
        "location": "Start Town",
        "visited_locations": ["Start Town"],
        "active_quests": [],
        "completed_quests": [],
        "npcs_met": [],
        "conditions": [],
        "in_combat": False,
    }
    save = GameSave(
        name="Test Game",
        character_id=character.id,
        world_id=world.id,
        game_state=json.dumps(game_state),
        story_log=json.dumps([]),
    )
    db_session.add(save)
    db_session.commit()
    db_session.refresh(save)
    return save


class TestListQuests:
    """Test GET /{game_id}/quests endpoint."""

    def test_empty_quest_log(self, client, game_save):
        """Test listing quests when the log is empty."""
        response = client.get(f"/api/game/{game_save.id}/quests")
        assert response.status_code == 200
        data = response.json()
        assert data["quests"] == []

    def test_list_quests_with_some(self, client, game_save, db_session):
        """Test listing quests when there are some."""
        # Add quests to game_state
        game_state = json.loads(game_save.game_state)
        game_state["quest_log"] = {
            "quests": [
                {
                    "id": 1,
                    "title": "Quest 1",
                    "description": "First quest",
                    "status": "active",
                    "giver": "NPC1",
                    "objective": "Do something",
                    "reward_hint": "100 gold",
                    "created_at": "",
                    "updated_at": "",
                },
                {
                    "id": 2,
                    "title": "Quest 2",
                    "description": "Second quest",
                    "status": "completed",
                    "giver": "NPC2",
                    "objective": "Done something",
                    "reward_hint": "",
                    "created_at": "",
                    "updated_at": "",
                },
            ],
            "next_id": 3,
        }
        game_save.game_state = json.dumps(game_state)
        db_session.commit()

        response = client.get(f"/api/game/{game_save.id}/quests")
        assert response.status_code == 200
        data = response.json()
        assert len(data["quests"]) == 2
        assert data["quests"][0]["title"] == "Quest 1"
        assert data["quests"][1]["title"] == "Quest 2"

    def test_filter_by_status_active(self, client, game_save, db_session):
        """Test filtering quests by status (active)."""
        game_state = json.loads(game_save.game_state)
        game_state["quest_log"] = {
            "quests": [
                {
                    "id": 1,
                    "title": "Active Quest",
                    "description": "Test",
                    "status": "active",
                    "giver": "NPC",
                    "objective": "Test",
                    "reward_hint": "",
                    "created_at": "",
                    "updated_at": "",
                },
                {
                    "id": 2,
                    "title": "Completed Quest",
                    "description": "Test",
                    "status": "completed",
                    "giver": "NPC",
                    "objective": "Test",
                    "reward_hint": "",
                    "created_at": "",
                    "updated_at": "",
                },
            ],
            "next_id": 3,
        }
        game_save.game_state = json.dumps(game_state)
        db_session.commit()

        response = client.get(f"/api/game/{game_save.id}/quests?status=active")
        assert response.status_code == 200
        data = response.json()
        assert len(data["quests"]) == 1
        assert data["quests"][0]["title"] == "Active Quest"

    def test_filter_by_status_completed(self, client, game_save, db_session):
        """Test filtering quests by status (completed)."""
        game_state = json.loads(game_save.game_state)
        game_state["quest_log"] = {
            "quests": [
                {
                    "id": 1,
                    "title": "Active Quest",
                    "description": "Test",
                    "status": "active",
                    "giver": "NPC",
                    "objective": "Test",
                    "reward_hint": "",
                    "created_at": "",
                    "updated_at": "",
                },
                {
                    "id": 2,
                    "title": "Completed Quest",
                    "description": "Test",
                    "status": "completed",
                    "giver": "NPC",
                    "objective": "Test",
                    "reward_hint": "",
                    "created_at": "",
                    "updated_at": "",
                },
            ],
            "next_id": 3,
        }
        game_save.game_state = json.dumps(game_state)
        db_session.commit()

        response = client.get(f"/api/game/{game_save.id}/quests?status=completed")
        assert response.status_code == 200
        data = response.json()
        assert len(data["quests"]) == 1
        assert data["quests"][0]["title"] == "Completed Quest"

    def test_invalid_status_filter(self, client, game_save):
        """Test that invalid status filter returns 400."""
        response = client.get(f"/api/game/{game_save.id}/quests?status=invalid")
        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]

    def test_nonexistent_game(self, client):
        """Test that querying a nonexistent game returns 404."""
        response = client.get("/api/game/99999/quests")
        assert response.status_code == 404
        assert "Game not found" in response.json()["detail"]


class TestGetQuest:
    """Test GET /{game_id}/quests/{quest_id} endpoint."""

    def test_get_quest_by_id(self, client, game_save, db_session):
        """Test getting a specific quest."""
        game_state = json.loads(game_save.game_state)
        game_state["quest_log"] = {
            "quests": [
                {
                    "id": 1,
                    "title": "Test Quest",
                    "description": "Test description",
                    "status": "active",
                    "giver": "NPC",
                    "objective": "Test",
                    "reward_hint": "",
                    "created_at": "",
                    "updated_at": "",
                }
            ],
            "next_id": 2,
        }
        game_save.game_state = json.dumps(game_state)
        db_session.commit()

        response = client.get(f"/api/game/{game_save.id}/quests/1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["title"] == "Test Quest"

    def test_get_nonexistent_quest(self, client, game_save, db_session):
        """Test getting a quest that doesn't exist."""
        game_state = json.loads(game_save.game_state)
        game_state["quest_log"] = {"quests": [], "next_id": 1}
        game_save.game_state = json.dumps(game_state)
        db_session.commit()

        response = client.get(f"/api/game/{game_save.id}/quests/999")
        assert response.status_code == 404
        assert "Quest not found" in response.json()["detail"]


class TestUpdateQuestStatus:
    """Test PATCH /{game_id}/quests/{quest_id} endpoint."""

    def test_update_quest_status(self, client, game_save, db_session):
        """Test updating a quest's status."""
        game_state = json.loads(game_save.game_state)
        game_state["quest_log"] = {
            "quests": [
                {
                    "id": 1,
                    "title": "Active Quest",
                    "description": "Test",
                    "status": "active",
                    "giver": "NPC",
                    "objective": "Test",
                    "reward_hint": "",
                    "created_at": "",
                    "updated_at": "",
                }
            ],
            "next_id": 2,
        }
        game_save.game_state = json.dumps(game_state)
        db_session.commit()

        response = client.patch(
            f"/api/game/{game_save.id}/quests/1",
            json={"status": "completed"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"

        # Verify persistence
        db_session.refresh(game_save)
        updated_state = json.loads(game_save.game_state)
        assert updated_state["quest_log"]["quests"][0]["status"] == "completed"

    def test_update_nonexistent_quest(self, client, game_save, db_session):
        """Test updating a quest that doesn't exist."""
        game_state = json.loads(game_save.game_state)
        game_state["quest_log"] = {"quests": [], "next_id": 1}
        game_save.game_state = json.dumps(game_state)
        db_session.commit()

        response = client.patch(
            f"/api/game/{game_save.id}/quests/999",
            json={"status": "completed"},
        )
        assert response.status_code == 404
        assert "Quest not found" in response.json()["detail"]

    def test_invalid_status(self, client, game_save, db_session):
        """Test updating with an invalid status."""
        game_state = json.loads(game_save.game_state)
        game_state["quest_log"] = {
            "quests": [
                {
                    "id": 1,
                    "title": "Test Quest",
                    "description": "Test",
                    "status": "active",
                    "giver": "NPC",
                    "objective": "Test",
                    "reward_hint": "",
                    "created_at": "",
                    "updated_at": "",
                }
            ],
            "next_id": 2,
        }
        game_save.game_state = json.dumps(game_state)
        db_session.commit()

        response = client.patch(
            f"/api/game/{game_save.id}/quests/1",
            json={"status": "invalid"},
        )
        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]

    def test_nonexistent_game(self, client):
        """Test updating a quest for a nonexistent game."""
        response = client.patch(
            "/api/game/99999/quests/1",
            json={"status": "completed"},
        )
        assert response.status_code == 404
        assert "Game not found" in response.json()["detail"]
