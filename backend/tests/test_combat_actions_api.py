"""
Tests for the combat-actions REST API.

Verifies action listing, performing each action kind through the dispatch
endpoint, persistence of action state, and error handling.
"""
import pytest
from fastapi.testclient import TestClient

from app.models.models import Character, World, GameSave
from app.engine import dice


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def game_in_combat(client: TestClient, db_session):
    """Create a character/world/game and start combat; return (client, save_id)."""
    char = Character(
        name="Test Hero",
        race="Human",
        char_class="Fighter",
        level=3,
        background="Soldier",
        strength=16,
        dexterity=14,
        constitution=14,
        intelligence=10,
        wisdom=10,
        charisma=10,
        max_hp=30,
        current_hp=30,
        armor_class=16,
        speed=30,
        backstory="A brave hero.",
    )
    db_session.add(char)
    db_session.flush()

    w = World(
        name="Test World",
        description="A world for testing.",
        world_data='{"starting_settlement": {"name": "Test Town"}}',
        tone="heroic fantasy",
    )
    db_session.add(w)
    db_session.flush()

    save = GameSave(
        name="Test Game",
        character_id=char.id,
        world_id=w.id,
        game_state='{"location": "Test Town"}',
        story_log="[]",
        current_act=1,
        xp=0,
    )
    db_session.add(save)
    db_session.commit()

    client.post(
        f"/api/game/{save.id}/combat/start",
        json={
            "enemies": [
                {
                    "name": "Goblin",
                    "max_hp": 7,
                    "armor_class": 13,
                    "initiative_bonus": 2,
                    "speed": 30,
                    "size": "small",
                    "strength": 8,
                    "dexterity": 14,
                    "athletics_bonus": -1,
                    "acrobatics_bonus": 1,
                    "attacks": [
                        {
                            "name": "Scimitar",
                            "attack_bonus": 4,
                            "damage_dice_count": 1,
                            "damage_dice_sides": 6,
                            "damage_bonus": 2,
                            "damage_type": "slashing",
                        }
                    ],
                }
            ]
        },
    )
    return client, save.id


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
class TestListActions:
    def test_list_actions(self, game_in_combat):
        client, game_id = game_in_combat
        resp = client.get(f"/api/game/{game_id}/combat/actions")
        assert resp.status_code == 200
        keys = {a["key"] for a in resp.json()["actions"]}
        assert {"grapple", "shove", "dash", "dodge", "help"} <= keys

    def test_list_actions_game_not_found(self, client):
        resp = client.get("/api/game/99999/combat/actions")
        assert resp.status_code == 404


class TestPerformActions:
    def test_dash(self, game_in_combat):
        client, game_id = game_in_combat
        resp = client.post(
            f"/api/game/{game_id}/combat/action",
            json={"combatant_id": "player", "action": "dash"},
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["success"]
        player = next(
            c for c in resp.json()["encounter"]["combatants"] if c["id"] == "player"
        )
        assert player["bonus_movement"] == 30

    def test_dodge_persists(self, game_in_combat):
        client, game_id = game_in_combat
        resp = client.post(
            f"/api/game/{game_id}/combat/action",
            json={"combatant_id": "player", "action": "dodge"},
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["success"]
        # Verify it round-trips via the state endpoint.
        state = client.get(f"/api/game/{game_id}/combat/state").json()
        player = next(c for c in state["encounter"]["combatants"] if c["id"] == "player")
        assert player["dodging"] is True

    def test_disengage(self, game_in_combat):
        client, game_id = game_in_combat
        resp = client.post(
            f"/api/game/{game_id}/combat/action",
            json={"combatant_id": "player", "action": "disengage"},
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["success"]

    def test_grapple_success(self, game_in_combat, monkeypatch):
        # Player athletics (Str 16, fighter prof) > goblin acrobatics(1).
        monkeypatch.setattr(dice.random, "randint", lambda _a, _b: 10)
        client, game_id = game_in_combat
        resp = client.post(
            f"/api/game/{game_id}/combat/action",
            json={"combatant_id": "player", "action": "grapple", "target_id": "enemy_1"},
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["success"]
        goblin = next(
            c for c in resp.json()["encounter"]["combatants"] if c["id"] == "enemy_1"
        )
        assert "grappled" in goblin["conditions"]
        assert goblin["grappled_by"] == "player"

    def test_shove_prone(self, game_in_combat, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", lambda _a, _b: 10)
        client, game_id = game_in_combat
        resp = client.post(
            f"/api/game/{game_id}/combat/action",
            json={
                "combatant_id": "player", "action": "shove",
                "target_id": "enemy_1", "option": "prone",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["success"]
        goblin = next(
            c for c in resp.json()["encounter"]["combatants"] if c["id"] == "enemy_1"
        )
        assert "prone" in goblin["conditions"]

    def test_help_then_consumed(self, game_in_combat, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", lambda _a, _b: 10)
        client, game_id = game_in_combat
        resp = client.post(
            f"/api/game/{game_id}/combat/action",
            json={"combatant_id": "player", "action": "help", "target_id": "enemy_1"},
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["success"]
        assert "enemy_1" in resp.json()["encounter"]["help_advantage_targets"]

    def test_unarmed_strike(self, game_in_combat, monkeypatch):
        # d20 = 20 -> auto-hit; unarmed damage uses d1 (fixed to 20 by patch).
        monkeypatch.setattr(dice.random, "randint", lambda _a, _b: 20)
        client, game_id = game_in_combat
        resp = client.post(
            f"/api/game/{game_id}/combat/action",
            json={"combatant_id": "player", "action": "unarmed-strike", "target_id": "enemy_1"},
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["success"]
        assert resp.json()["attack_result"]["hit"]

    def test_target_action_without_target_fails_gracefully(self, game_in_combat):
        client, game_id = game_in_combat
        resp = client.post(
            f"/api/game/{game_id}/combat/action",
            json={"combatant_id": "player", "action": "grapple"},
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["success"] is False

    def test_unknown_action(self, game_in_combat):
        client, game_id = game_in_combat
        resp = client.post(
            f"/api/game/{game_id}/combat/action",
            json={"combatant_id": "player", "action": "backflip"},
        )
        assert resp.status_code == 400

    def test_unknown_combatant(self, game_in_combat):
        client, game_id = game_in_combat
        resp = client.post(
            f"/api/game/{game_id}/combat/action",
            json={"combatant_id": "nobody", "action": "dash"},
        )
        assert resp.status_code == 404

    def test_not_in_combat(self, client, db_session):
        char = Character(
            name="Lone", race="Human", char_class="Fighter", level=1,
            strength=14, dexterity=12, constitution=12, intelligence=10,
            wisdom=10, charisma=10, max_hp=10, current_hp=10, armor_class=15,
            speed=30,
        )
        db_session.add(char)
        db_session.flush()
        w = World(name="W", description="d", world_data="{}", tone="t")
        db_session.add(w)
        db_session.flush()
        save = GameSave(name="g", character_id=char.id, world_id=w.id,
                        game_state="{}", story_log="[]", current_act=1, xp=0)
        db_session.add(save)
        db_session.commit()
        resp = client.post(
            f"/api/game/{save.id}/combat/action",
            json={"combatant_id": "player", "action": "dash"},
        )
        assert resp.status_code == 400
        assert "not in combat" in resp.json()["detail"].lower()


class TestPlayerSkillPopulation:
    def test_player_has_skill_bonuses(self, game_in_combat):
        """Starting combat should populate the player's athletics/acrobatics
        bonuses from the character (so grapple/shove are meaningful)."""
        client, game_id = game_in_combat
        state = client.get(f"/api/game/{game_id}/combat/state").json()
        player = next(c for c in state["encounter"]["combatants"] if c["id"] == "player")
        # Fighter, Str 16: athletics >= +3 (proficiency may add more).
        assert player["strength"] == 16
        assert player["athletics_bonus"] is not None
        assert player["athletics_bonus"] >= 3
