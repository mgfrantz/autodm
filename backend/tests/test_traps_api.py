"""
Tests for the traps API (DMG ch.5).

Uses the shared conftest ``client`` and ``db_session`` fixtures so the
dependency-override lifecycle is managed correctly across the full suite.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.models.models import Character, World, GameSave


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _make_game(db_session):
    """Create a character + world + game for trap testing."""
    char = Character(
        name="Trap Tester",
        race="Human",
        char_class="Rogue",
        level=3,
        classes='{"rogue": 3}',
        strength=10,
        dexterity=16,
        constitution=12,
        intelligence=12,
        wisdom=14,
        charisma=10,
        max_hp=24,
        current_hp=24,
    )
    db_session.add(char)
    db_session.flush()

    world = World(
        name="Dungeon World",
        description="A world full of traps.",
        world_data="{}",
    )
    db_session.add(world)
    db_session.flush()

    game = GameSave(
        name="Trap Game",
        character_id=char.id,
        world_id=world.id,
        game_state="{}",
        story_log="[]",
    )
    db_session.add(game)
    db_session.commit()
    return game


@pytest.fixture
def test_game(client: TestClient, db_session):
    """Create a test game and return it."""
    return _make_game(db_session)


# --------------------------------------------------------------------------- #
# Registry endpoints
# --------------------------------------------------------------------------- #

class TestTrapRegistry:
    def test_get_registry(self, client):
        response = client.get("/api/game/traps/registry")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 14
        trap = data[0]
        assert "id" in trap
        assert "name" in trap
        assert "trap_type" in trap
        assert "severity" in trap
        assert "effects" in trap

    def test_get_registry_filtered_by_type(self, client):
        response = client.get("/api/game/traps/registry", params={"trap_type": "magical"})
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        for t in data:
            assert t["trap_type"] == "magical"

    def test_get_registry_filtered_by_severity(self, client):
        response = client.get("/api/game/traps/registry", params={"severity": "deadly"})
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        for t in data:
            assert t["severity"] == "deadly"

    def test_get_trap_ids(self, client):
        response = client.get("/api/game/traps/registry/ids")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert "collapsing_roof" in data

    def test_get_by_type(self, client):
        response = client.get("/api/game/traps/registry/type/mechanical")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        for t in data:
            assert t["trap_type"] == "mechanical"

    def test_get_by_type_invalid(self, client):
        response = client.get("/api/game/traps/registry/type/invalid")
        assert response.status_code == 400

    def test_get_by_severity(self, client):
        response = client.get("/api/game/traps/registry/severity/setback")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        for t in data:
            assert t["severity"] == "setback"

    def test_get_by_severity_invalid(self, client):
        response = client.get("/api/game/traps/registry/severity/invalid")
        assert response.status_code == 400

    def test_get_trap_detail(self, client):
        response = client.get("/api/game/traps/registry/collapsing_roof")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "collapsing_roof"
        assert data["name"] == "Collapsing Roof"
        assert len(data["effects"]) > 0

    def test_get_trap_detail_not_found(self, client):
        response = client.get("/api/game/traps/registry/nonexistent")
        assert response.status_code == 404

    def test_get_guidelines(self, client):
        response = client.get("/api/game/traps/guidelines")
        assert response.status_code == 200
        data = response.json()
        assert "setback" in data
        assert "dangerous" in data
        assert "deadly" in data


# --------------------------------------------------------------------------- #
# Place / list / remove traps
# --------------------------------------------------------------------------- #

class TestPlaceAndListTraps:
    def test_place_trap(self, client, test_game):
        response = client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "hidden_pit", "location": "entrance corridor"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["trap_id"] == "hidden_pit"
        assert data["location"] == "entrance corridor"
        assert data["discovered"] is False
        assert data["disarmed"] is False

    def test_place_invalid_trap(self, client, test_game):
        response = client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "nonexistent"},
        )
        assert response.status_code == 404

    def test_list_traps_empty(self, client, test_game):
        response = client.get(f"/api/game/{test_game.id}/traps")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_traps_after_placement(self, client, test_game):
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "hidden_pit"},
        )
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "poison_darts", "location": "hall"},
        )
        response = client.get(f"/api/game/{test_game.id}/traps")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_remove_trap(self, client, test_game):
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "hidden_pit"},
        )
        response = client.delete(f"/api/game/{test_game.id}/traps/0")
        assert response.status_code == 200
        assert response.json()["status"] == "removed"
        list_resp = client.get(f"/api/game/{test_game.id}/traps")
        assert list_resp.json() == []

    def test_remove_trap_not_found(self, client, test_game):
        response = client.delete(f"/api/game/{test_game.id}/traps/99")
        assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #

class TestTrapDetection:
    def test_active_detection_success(self, client, test_game):
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "hidden_pit"},  # DC 12
        )
        response = client.post(
            f"/api/game/{test_game.id}/traps/0/detect",
            json={"perception_total": 15, "roll": 12},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["discovered"] is True

    def test_active_detection_failure(self, client, test_game):
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "hidden_pit"},  # DC 12
        )
        response = client.post(
            f"/api/game/{test_game.id}/traps/0/detect",
            json={"perception_total": 8, "roll": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["discovered"] is False

    def test_passive_detection_success(self, client, test_game):
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "falling_net"},  # DC 10
        )
        response = client.post(
            f"/api/game/{test_game.id}/traps/0/passive-detect",
            json={"passive_perception": 14},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["noticed"] is True
        assert data["discovered"] is True

    def test_passive_detection_failure(self, client, test_game):
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "falling_net"},  # DC 10
        )
        response = client.post(
            f"/api/game/{test_game.id}/traps/0/passive-detect",
            json={"passive_perception": 8},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["noticed"] is False


# --------------------------------------------------------------------------- #
# Disarm
# --------------------------------------------------------------------------- #

class TestTrapDisarm:
    def test_disarm_success(self, client, test_game):
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "hidden_pit"},  # disarm DC 12
        )
        client.post(
            f"/api/game/{test_game.id}/traps/0/detect",
            json={"perception_total": 15, "roll": 12},
        )
        response = client.post(
            f"/api/game/{test_game.id}/traps/0/disarm",
            json={"check_total": 15, "roll": 12, "method": "thieves_tools"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["disarmed"] is True

    def test_disarm_not_discovered(self, client, test_game):
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "hidden_pit"},
        )
        response = client.post(
            f"/api/game/{test_game.id}/traps/0/disarm",
            json={"check_total": 20, "roll": 18},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "haven't found" in data["narrative"].lower()

    def test_disarm_failure_may_trigger(self, client, test_game):
        """A failed disarm by 5+ can trigger the trap."""
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "hidden_pit"},  # disarm DC 12
        )
        client.post(
            f"/api/game/{test_game.id}/traps/0/detect",
            json={"perception_total": 15, "roll": 12},
        )
        response = client.post(
            f"/api/game/{test_game.id}/traps/0/disarm",
            json={"check_total": 5, "roll": 2},  # fail by 7
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "triggered" in data


# --------------------------------------------------------------------------- #
# Trigger
# --------------------------------------------------------------------------- #

class TestTrapTrigger:
    def test_trigger_damage_trap(self, client, test_game):
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "hidden_pit"},
        )
        response = client.post(
            f"/api/game/{test_game.id}/traps/0/trigger",
            json={},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["triggered"] is True
        assert data["damage"] >= 1
        assert data["damage_type"] == "bludgeoning"

    def test_trigger_with_save(self, client, test_game):
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "collapsing_roof"},  # 3d6 Dex save DC 15
        )
        response = client.post(
            f"/api/game/{test_game.id}/traps/0/trigger",
            json={"save_roll": 18, "save_modifier": 3},  # total 21 >= 15
        )
        assert response.status_code == 200
        data = response.json()
        assert data["triggered"] is True
        assert data["save_success"] is True
        assert data["damage"] <= 9  # halved 3d6

    def test_trigger_condition_trap(self, client, test_game):
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "falling_net"},  # restrained, DC 10 Dex
        )
        response = client.post(
            f"/api/game/{test_game.id}/traps/0/trigger",
            json={"save_roll": 5, "save_modifier": 0},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["triggered"] is True
        assert "restrained" in data["conditions"]

    def test_trigger_disarmed_trap(self, client, test_game):
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "hidden_pit"},
        )
        client.post(
            f"/api/game/{test_game.id}/traps/0/detect",
            json={"perception_total": 20, "roll": 18},
        )
        client.post(
            f"/api/game/{test_game.id}/traps/0/disarm",
            json={"check_total": 20, "roll": 18},
        )
        response = client.post(
            f"/api/game/{test_game.id}/traps/0/trigger",
            json={},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["triggered"] is False


# --------------------------------------------------------------------------- #
# Persistence & story logging
# --------------------------------------------------------------------------- #

class TestTrapPersistence:
    def test_trap_persists(self, client, test_game, db_session):
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "hidden_pit"},
        )
        db_session.expire_all()
        db_session.refresh(test_game)
        game_state = json.loads(test_game.game_state or "{}")
        assert "traps" in game_state
        assert len(game_state["traps"]) == 1
        assert game_state["traps"][0]["trap_id"] == "hidden_pit"

    def test_trap_state_persists_after_detect(self, client, test_game, db_session):
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "hidden_pit"},
        )
        client.post(
            f"/api/game/{test_game.id}/traps/0/detect",
            json={"perception_total": 15, "roll": 12},
        )
        db_session.expire_all()
        db_session.refresh(test_game)
        game_state = json.loads(test_game.game_state or "{}")
        assert game_state["traps"][0]["discovered"] is True

    def test_story_logged_on_placement(self, client, test_game, db_session):
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "hidden_pit"},
        )
        db_session.refresh(test_game)
        story = json.loads(test_game.story_log or "[]")
        assert len(story) > 0
        assert story[-1]["type"] == "system"

    def test_story_logged_on_trigger(self, client, test_game, db_session):
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "hidden_pit"},
        )
        client.post(
            f"/api/game/{test_game.id}/traps/0/trigger",
            json={},
        )
        db_session.refresh(test_game)
        story = json.loads(test_game.story_log or "[]")
        assert len(story) >= 2


# --------------------------------------------------------------------------- #
# DM summary
# --------------------------------------------------------------------------- #

class TestDMSummary:
    def test_dm_summary_empty(self, client, test_game):
        response = client.get(f"/api/game/{test_game.id}/traps/dm-summary")
        assert response.status_code == 200
        data = response.json()
        assert data["total_traps"] == 0
        assert data["summary"] == ""

    def test_dm_summary_with_traps(self, client, test_game):
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "hidden_pit"},
        )
        client.post(
            f"/api/game/{test_game.id}/traps",
            json={"trap_id": "collapsing_roof"},
        )
        client.post(
            f"/api/game/{test_game.id}/traps/0/detect",
            json={"perception_total": 20, "roll": 18},
        )
        response = client.get(f"/api/game/{test_game.id}/traps/dm-summary")
        assert response.status_code == 200
        data = response.json()
        assert data["total_traps"] == 2
        assert data["discovered"] == 1
        assert data["undiscovered"] == 1


# --------------------------------------------------------------------------- #
# Game not found
# --------------------------------------------------------------------------- #

class TestGameNotFound:
    def test_place_trap_game_not_found(self, client):
        response = client.post(
            "/api/game/99999/traps",
            json={"trap_id": "hidden_pit"},
        )
        assert response.status_code == 404

    def test_list_traps_game_not_found(self, client):
        response = client.get("/api/game/99999/traps")
        assert response.status_code == 404
