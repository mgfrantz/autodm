"""
Tests for World State API endpoints.
"""
import json
import pytest
from fastapi.testclient import TestClient

from app.models.models import Character, World, GameSave


def test_get_world_state_empty(client: TestClient, db_session):
    """Test getting world state when empty."""
    # Create test data
    char = Character(
        name="Test Hero",
        race="Human",
        char_class="Fighter",
        level=1,
    )
    world = World(
        name="Test World",
        description="A test world",
        world_data=json.dumps({"name": "Test World", "regions": [], "npcs": [], "hook": ""}),
    )
    db_session.add(char)
    db_session.add(world)
    db_session.commit()

    save = GameSave(
        name="Test Game",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps({"location": "Start"}),
    )
    db_session.add(save)
    db_session.commit()

    response = client.get(f"/api/game/{save.id}/world-state")
    assert response.status_code == 200
    data = response.json()
    assert data["npc_relationships"] == {}
    assert data["faction_reputation"] == {}


def test_update_npc_relationship(client: TestClient, db_session):
    """Test updating an NPC relationship."""
    char = Character(
        name="Test Hero",
        race="Human",
        char_class="Fighter",
        level=1,
    )
    world = World(
        name="Test World",
        description="A test world",
        world_data=json.dumps({"name": "Test World", "regions": [], "npcs": [], "hook": ""}),
    )
    db_session.add(char)
    db_session.add(world)
    db_session.commit()

    save = GameSave(
        name="Test Game",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps({"location": "Start"}),
    )
    db_session.add(save)
    db_session.commit()

    # Update NPC relationship
    response = client.post(
        f"/api/game/{save.id}/npcs",
        json={
            "npc_name": "Gandalf",
            "trust_change": 30,
            "interaction_summary": "Helped defeat goblins",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["npc_name"] == "Gandalf"
    assert data["attitude"] == "friendly"
    assert data["trust"] == 30
    assert data["interactions"][0] == "Helped defeat goblins"

    # Verify it persists
    response = client.get(f"/api/game/{save.id}/world-state")
    assert response.status_code == 200
    data = response.json()
    assert "Gandalf" in data["npc_relationships"]
    assert data["npc_relationships"]["Gandalf"]["trust"] == 30


def test_update_npc_multiple_times(client: TestClient, db_session):
    """Test updating an NPC relationship multiple times."""
    char = Character(
        name="Test Hero",
        race="Human",
        char_class="Fighter",
        level=1,
    )
    world = World(
        name="Test World",
        description="A test world",
        world_data=json.dumps({"name": "Test World", "regions": [], "npcs": [], "hook": ""}),
    )
    db_session.add(char)
    db_session.add(world)
    db_session.commit()

    save = GameSave(
        name="Test Game",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps({"location": "Start"}),
    )
    db_session.add(save)
    db_session.commit()

    # First interaction
    client.post(
        f"/api/game/{save.id}/npcs",
        json={
            "npc_name": "Gandalf",
            "trust_change": 20,
            "interaction_summary": "First meeting",
        },
    )

    # Second interaction
    client.post(
        f"/api/game/{save.id}/npcs",
        json={
            "npc_name": "Gandalf",
            "trust_change": 15,
            "interaction_summary": "Second meeting",
        },
    )

    # Third (negative) interaction
    response = client.post(
        f"/api/game/{save.id}/npcs",
        json={
            "npc_name": "Gandalf",
            "trust_change": -10,
            "interaction_summary": "Minor disagreement",
        },
    )

    data = response.json()
    assert data["trust"] == 25  # 20 + 15 - 10
    assert len(data["interactions"]) == 3
    assert data["interactions"][2] == "Minor disagreement"


def test_get_npc_relationship(client: TestClient, db_session):
    """Test getting a specific NPC relationship."""
    char = Character(
        name="Test Hero",
        race="Human",
        char_class="Fighter",
        level=1,
    )
    world = World(
        name="Test World",
        description="A test world",
        world_data=json.dumps({"name": "Test World", "regions": [], "npcs": [], "hook": ""}),
    )
    db_session.add(char)
    db_session.add(world)
    db_session.commit()

    save = GameSave(
        name="Test Game",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps({"location": "Start"}),
    )
    db_session.add(save)
    db_session.commit()

    # Create NPC relationship
    client.post(
        f"/api/game/{save.id}/npcs",
        json={
            "npc_name": "Gandalf",
            "trust_change": 40,
            "interaction_summary": "Helped",
        },
    )

    # Get the specific NPC
    response = client.get(f"/api/game/{save.id}/npcs/Gandalf")
    assert response.status_code == 200
    data = response.json()
    assert data["npc_name"] == "Gandalf"
    assert data["trust"] == 40

    # Get non-existent NPC
    response = client.get(f"/api/game/{save.id}/npcs/Saruman")
    assert response.status_code == 404


def test_update_faction_reputation(client: TestClient, db_session):
    """Test updating faction reputation."""
    char = Character(
        name="Test Hero",
        race="Human",
        char_class="Fighter",
        level=1,
    )
    world = World(
        name="Test World",
        description="A test world",
        world_data=json.dumps({"name": "Test World", "regions": [], "npcs": [], "hook": ""}),
    )
    db_session.add(char)
    db_session.add(world)
    db_session.commit()

    save = GameSave(
        name="Test Game",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps({"location": "Start"}),
    )
    db_session.add(save)
    db_session.commit()

    # Update faction reputation
    response = client.post(
        f"/api/game/{save.id}/factions",
        json={
            "faction_name": "Mages Guild",
            "reputation_change": 30,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["faction_name"] == "Mages Guild"
    assert data["standing"] == "friendly"
    assert data["reputation"] == 30
    assert data["quests_completed"] == 0

    # Verify it persists
    response = client.get(f"/api/game/{save.id}/world-state")
    assert response.status_code == 200
    data = response.json()
    assert "Mages Guild" in data["faction_reputation"]
    assert data["faction_reputation"]["Mages Guild"]["reputation"] == 30


def test_get_faction_reputation(client: TestClient, db_session):
    """Test getting a specific faction reputation."""
    char = Character(
        name="Test Hero",
        race="Human",
        char_class="Fighter",
        level=1,
    )
    world = World(
        name="Test World",
        description="A test world",
        world_data=json.dumps({"name": "Test World", "regions": [], "npcs": [], "hook": ""}),
    )
    db_session.add(char)
    db_session.add(world)
    db_session.commit()

    save = GameSave(
        name="Test Game",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps({"location": "Start"}),
    )
    db_session.add(save)
    db_session.commit()

    # Create faction reputation
    client.post(
        f"/api/game/{save.id}/factions",
        json={
            "faction_name": "Mages Guild",
            "reputation_change": 50,
        },
    )

    # Get the specific faction
    response = client.get(f"/api/game/{save.id}/factions/Mages Guild")
    assert response.status_code == 200
    data = response.json()
    assert data["faction_name"] == "Mages Guild"
    assert data["reputation"] == 50

    # Get non-existent faction
    response = client.get(f"/api/game/{save.id}/factions/Thieves Guild")
    assert response.status_code == 404


def test_complete_faction_quest(client: TestClient, db_session):
    """Test completing a faction quest."""
    char = Character(
        name="Test Hero",
        race="Human",
        char_class="Fighter",
        level=1,
    )
    world = World(
        name="Test World",
        description="A test world",
        world_data=json.dumps({"name": "Test World", "regions": [], "npcs": [], "hook": ""}),
    )
    db_session.add(char)
    db_session.add(world)
    db_session.commit()

    save = GameSave(
        name="Test Game",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps({"location": "Start"}),
    )
    db_session.add(save)
    db_session.commit()

    # Complete a quest
    response = client.post(
        f"/api/game/{save.id}/quests/complete",
        json={"faction_name": "Mages Guild"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["faction_name"] == "Mages Guild"
    assert data["quests_completed"] == 1
    assert data["reputation"] == 10  # Base quest completion bonus
    assert data["standing"] == "neutral"  # 10 is still < 25

    # Complete another quest
    response = client.post(
        f"/api/game/{save.id}/quests/complete",
        json={"faction_name": "Mages Guild"},
    )
    data = response.json()
    assert data["quests_completed"] == 2
    assert data["reputation"] == 20  # Still neutral


def test_fail_faction_quest(client: TestClient, db_session):
    """Test failing a faction quest."""
    char = Character(
        name="Test Hero",
        race="Human",
        char_class="Fighter",
        level=1,
    )
    world = World(
        name="Test World",
        description="A test world",
        world_data=json.dumps({"name": "Test World", "regions": [], "npcs": [], "hook": ""}),
    )
    db_session.add(char)
    db_session.add(world)
    db_session.commit()

    save = GameSave(
        name="Test Game",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps({"location": "Start"}),
    )
    db_session.add(save)
    db_session.commit()

    # Fail a quest
    response = client.post(
        f"/api/game/{save.id}/quests/fail",
        json={"faction_name": "Mages Guild"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["faction_name"] == "Mages Guild"
    assert data["quests_failed"] == 1
    assert data["reputation"] == -15  # Base quest failure penalty
    assert data["standing"] == "neutral"  # -15 is still > -25

    # Fail another quest
    response = client.post(
        f"/api/game/{save.id}/quests/fail",
        json={"faction_name": "Mages Guild"},
    )
    data = response.json()
    assert data["quests_failed"] == 2
    assert data["reputation"] == -30


def test_get_world_state_summary(client: TestClient, db_session):
    """Test getting world state summary for DM context."""
    char = Character(
        name="Test Hero",
        race="Human",
        char_class="Fighter",
        level=1,
    )
    world = World(
        name="Test World",
        description="A test world",
        world_data=json.dumps({"name": "Test World", "regions": [], "npcs": [], "hook": ""}),
    )
    db_session.add(char)
    db_session.add(world)
    db_session.commit()

    save = GameSave(
        name="Test Game",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps({"location": "Start"}),
    )
    db_session.add(save)
    db_session.commit()

    # Add some relationships
    client.post(
        f"/api/game/{save.id}/npcs",
        json={
            "npc_name": "Gandalf",
            "trust_change": 40,
            "interaction_summary": "Helped defeat goblins",
        },
    )
    client.post(
        f"/api/game/{save.id}/npcs",
        json={
            "npc_name": "Saruman",
            "trust_change": -30,
            "interaction_summary": "Refused to help",
        },
    )
    client.post(
        f"/api/game/{save.id}/factions",
        json={
            "faction_name": "Mages Guild",
            "reputation_change": 50,
        },
    )
    client.post(
        f"/api/game/{save.id}/factions",
        json={
            "faction_name": "Thieves Guild",
            "reputation_change": -40,
        },
    )

    # Get summary
    response = client.get(f"/api/game/{save.id}/world-state/summary")
    assert response.status_code == 200
    data = response.json()
    assert "npc_summary" in data
    assert "faction_summary" in data
    assert "Gandalf" in data["npc_summary"]
    assert "Saruman" in data["npc_summary"]
    assert "Mages Guild" in data["faction_summary"]
    assert "Thieves Guild" in data["faction_summary"]


def test_trust_change_validation(client: TestClient, db_session):
    """Test that trust_change is validated to be within bounds."""
    char = Character(
        name="Test Hero",
        race="Human",
        char_class="Fighter",
        level=1,
    )
    world = World(
        name="Test World",
        description="A test world",
        world_data=json.dumps({"name": "Test World", "regions": [], "npcs": [], "hook": ""}),
    )
    db_session.add(char)
    db_session.add(world)
    db_session.commit()

    save = GameSave(
        name="Test Game",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps({"location": "Start"}),
    )
    db_session.add(save)
    db_session.commit()

    # Test too high
    response = client.post(
        f"/api/game/{save.id}/npcs",
        json={
            "npc_name": "Gandalf",
            "trust_change": 150,
            "interaction_summary": "Too much trust",
        },
    )
    assert response.status_code == 400

    # Test too low
    response = client.post(
        f"/api/game/{save.id}/npcs",
        json={
            "npc_name": "Gandalf",
            "trust_change": -150,
            "interaction_summary": "Too little trust",
        },
    )
    assert response.status_code == 400


def test_reputation_change_validation(client: TestClient, db_session):
    """Test that reputation_change is validated to be within bounds."""
    char = Character(
        name="Test Hero",
        race="Human",
        char_class="Fighter",
        level=1,
    )
    world = World(
        name="Test World",
        description="A test world",
        world_data=json.dumps({"name": "Test World", "regions": [], "npcs": [], "hook": ""}),
    )
    db_session.add(char)
    db_session.add(world)
    db_session.commit()

    save = GameSave(
        name="Test Game",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps({"location": "Start"}),
    )
    db_session.add(save)
    db_session.commit()

    # Test too high
    response = client.post(
        f"/api/game/{save.id}/factions",
        json={
            "faction_name": "Mages Guild",
            "reputation_change": 150,
        },
    )
    assert response.status_code == 400

    # Test too low
    response = client.post(
        f"/api/game/{save.id}/factions",
        json={
            "faction_name": "Mages Guild",
            "reputation_change": -150,
        },
    )
    assert response.status_code == 400


def test_game_not_found(client: TestClient):
    """Test that requests to non-existent games return 404."""
    response = client.get(f"/api/game/999/world-state")
    assert response.status_code == 404

    response = client.post(
        f"/api/game/999/npcs",
        json={
            "npc_name": "Gandalf",
            "trust_change": 30,
            "interaction_summary": "Test",
        },
    )
    assert response.status_code == 404