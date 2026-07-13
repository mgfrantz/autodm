"""Tests for the quests API."""
import json
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.database import SessionLocal
from app.models.models import Character, World, GameSave


@pytest.fixture
def db():
    """Create a fresh database session for each test."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def character(db):
    """Create a test character."""
    char = Character(
        name="Test Hero",
        race="Human",
        char_class="Fighter",
        level=1,
        current_hp=10,
        max_hp=10,
        gold=50,
        alignment="neutral_good",
        background="Soldier",
        strength=16,
        dexterity=14,
        constitution=14,
        intelligence=10,
        wisdom=12,
        charisma=10,
    )
    db.add(char)
    db.commit()
    db.refresh(char)
    yield char
    db.delete(char)
    db.commit()


@pytest.fixture
def world(db):
    """Create a test world."""
    world_data = {
        "name": "Test World",
        "description": "A test world",
        "tone": "heroic fantasy",
        "regions": [],
        "campaign_arc": {},
        "starting_settlement": {"name": "Start Town"},
        "npcs": [],
        "factions": [],
        "hook": "Test hook",
    }
    world = World(name="Test World", description="Test", world_data=json.dumps(world_data))
    db.add(world)
    db.commit()
    db.refresh(world)
    yield world
    db.delete(world)
    db.commit()


@pytest.fixture
def game_save(db, character, world):
    """Create a test game save."""
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
    db.add(save)
    db.commit()
    db.refresh(save)
    yield save
    db.delete(save)
    db.commit()


class TestListQuests:
    """Test GET /{game_id}/quests endpoint."""

    def test_empty_quest_log(self, client, game_save):
        """Test listing quests when the log is empty."""
        response = client.get(f"/api/game/{game_save.id}/quests")
        assert response.status_code == 200
        data = response.json()
        assert data["quests"] == []

    def test_list_quests_with_some(self, client, game_save, db):
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
        db.commit()

        response = client.get(f"/api/game/{game_save.id}/quests")
        assert response.status_code == 200
        data = response.json()
        assert len(data["quests"]) == 2
        assert data["quests"][0]["title"] == "Quest 1"
        assert data["quests"][1]["title"] == "Quest 2"

    def test_filter_by_status_active(self, client, game_save, db):
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
        db.commit()

        response = client.get(f"/api/game/{game_save.id}/quests?status=active")
        assert response.status_code == 200
        data = response.json()
        assert len(data["quests"]) == 1
        assert data["quests"][0]["title"] == "Active Quest"

    def test_filter_by_status_completed(self, client, game_save, db):
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
        db.commit()

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

    def test_get_quest_by_id(self, client, game_save, db):
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
        db.commit()

        response = client.get(f"/api/game/{game_save.id}/quests/1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["title"] == "Test Quest"

    def test_get_nonexistent_quest(self, client, game_save, db):
        """Test getting a quest that doesn't exist."""
        game_state = json.loads(game_save.game_state)
        game_state["quest_log"] = {"quests": [], "next_id": 1}
        game_save.game_state = json.dumps(game_state)
        db.commit()

        response = client.get(f"/api/game/{game_save.id}/quests/999")
        assert response.status_code == 404
        assert "Quest not found" in response.json()["detail"]


class TestUpdateQuestStatus:
    """Test PATCH /{game_id}/quests/{quest_id} endpoint."""

    def test_update_quest_status(self, client, game_save, db):
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
        db.commit()

        response = client.patch(
            f"/api/game/{game_save.id}/quests/1",
            json={"status": "completed"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"

        # Verify persistence
        db.refresh(game_save)
        updated_state = json.loads(game_save.game_state)
        assert updated_state["quest_log"]["quests"][0]["status"] == "completed"

    def test_update_nonexistent_quest(self, client, game_save, db):
        """Test updating a quest that doesn't exist."""
        game_state = json.loads(game_save.game_state)
        game_state["quest_log"] = {"quests": [], "next_id": 1}
        game_save.game_state = json.dumps(game_state)
        db.commit()

        response = client.patch(
            f"/api/game/{game_save.id}/quests/999",
            json={"status": "completed"},
        )
        assert response.status_code == 404
        assert "Quest not found" in response.json()["detail"]

    def test_invalid_status(self, client, game_save, db):
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
        db.commit()

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