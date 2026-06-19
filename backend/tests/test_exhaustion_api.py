"""
Tests for the exhaustion REST API and its combat / rest integration.

Covers:
- Out-of-combat exhaustion: GET, and POST (set/add/reduce), persistence to
  game_state, story logging, and level-6 death (HP → 0).
- Guards: cannot modify out-of-combat exhaustion mid-combat; invalid modes.
- In-combat combatant exhaustion: GET and POST, reaching 6 slays the combatant
  and ends combat (winner reported).
- Long-rest integration: a long rest reduces exhaustion by one level.
- start_combat carries the character's exhaustion onto the player combatant.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.models.models import Character, World, GameSave


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _make_game(db_session, conditions=None, exhaustion=None, in_combat=False):
    char = Character(
        name="Rhea", race="Human", char_class="Fighter", level=5,
        classes=json.dumps({"fighter": 5}),
        strength=16, dexterity=12, constitution=14, intelligence=10,
        wisdom=10, charisma=10,
        max_hp=40, current_hp=40, armor_class=16, speed=30,
        hit_dice_used=0,
    )
    db_session.add(char)
    db_session.flush()

    w = World(
        name="Harsh World", description="A punishing world.",
        world_data='{"starting_settlement": {"name": "Camp"}}', tone="grim",
    )
    db_session.add(w)
    db_session.flush()

    state = {"location": "Camp", "in_combat": in_combat, "conditions": conditions or []}
    if exhaustion is not None:
        state["exhaustion"] = exhaustion
    save = GameSave(
        name="Test Game", character_id=char.id, world_id=w.id,
        game_state=json.dumps(state),
        story_log="[]",
    )
    db_session.add(save)
    db_session.commit()
    return save


@pytest.fixture
def game(client: TestClient, db_session):
    return _make_game(db_session)


@pytest.fixture
def exhausted_game(client: TestClient, db_session):
    return _make_game(db_session, exhaustion=3, conditions=["poisoned"])


# --------------------------------------------------------------------------- #
# Out-of-combat exhaustion
# --------------------------------------------------------------------------- #

class TestOutOfCombat:
    def test_get_default_zero(self, client, game):
        r = client.get(f"/api/game/{game.id}/exhaustion")
        assert r.status_code == 200
        body = r.json()
        assert body["exhaustion"] == 0
        assert body["level"] == 0
        assert body["dead"] is False
        assert body["in_combat"] is False

    def test_get_with_existing_level(self, client, exhausted_game):
        r = client.get(f"/api/game/{exhausted_game.id}/exhaustion")
        assert r.status_code == 200
        body = r.json()
        assert body["exhaustion"] == 3
        assert body["disadvantage_attack_rolls"] is True
        assert body["speed_divisor"] == 2

    def test_add_increases_and_persists(self, client, game):
        r = client.post(f"/api/game/{game.id}/exhaustion", json={"mode": "add", "levels": 2})
        assert r.status_code == 200
        body = r.json()
        assert body["before"] == 0
        assert body["after"] == 2
        assert body["changed"] is True
        assert body["died"] is False
        # Persisted to game_state.
        state = json.loads(game.game_state)
        assert state["exhaustion"] == 2
        # Logged to story log.
        log = json.loads(game.story_log)
        assert any("exhaustion" in e["content"] for e in log)

    def test_reduce_lowers(self, client, exhausted_game):
        r = client.post(
            f"/api/game/{exhausted_game.id}/exhaustion",
            json={"mode": "reduce", "levels": 1},
        )
        assert r.status_code == 200
        assert r.json()["after"] == 2
        assert json.loads(exhausted_game.game_state)["exhaustion"] == 2

    def test_set_absolute(self, client, game):
        r = client.post(f"/api/game/{game.id}/exhaustion", json={"mode": "set", "levels": 4})
        assert r.status_code == 200
        assert r.json()["after"] == 4
        assert r.json()["max_hp_halved"] is True

    def test_add_clamps_at_six_and_kills(self, client, game):
        r = client.post(f"/api/game/{game.id}/exhaustion", json={"mode": "add", "levels": 6})
        assert r.status_code == 200
        body = r.json()
        assert body["after"] == 6
        assert body["died"] is True
        assert body["dead"] is True
        # HP dropped to 0 on death.
        assert body["character"]["current_hp"] == 0

    def test_invalid_mode(self, client, game):
        r = client.post(f"/api/game/{game.id}/exhaustion", json={"mode": "gain", "levels": 1})
        assert r.status_code == 400

    def test_blocked_in_combat(self, client, db_session):
        save = _make_game(db_session, exhaustion=1, in_combat=True)
        r = client.post(f"/api/game/{save.id}/exhaustion", json={"mode": "add", "levels": 1})
        assert r.status_code == 400
        assert "mid-combat" in r.json()["detail"].lower()

    def test_404_unknown_game(self, client):
        assert client.get("/api/game/9999/exhaustion").status_code == 404


# --------------------------------------------------------------------------- #
# In-combat combatant exhaustion
# --------------------------------------------------------------------------- #

def _start_combat(client, game_id, enemy_hp=20):
    """Start a combat encounter and return the encounter payload."""
    r = client.post(
        f"/api/game/{game_id}/combat/start",
        json={"enemies": [{
            "name": "Goblin", "max_hp": enemy_hp, "armor_class": 13,
            "attacks": [{"name": "Scimitar", "attack_bonus": 4,
                         "damage_dice_sides": 6, "damage_bonus": 2}],
        }]},
    )
    assert r.status_code == 200
    return r.json()


class TestInCombat:
    def test_get_combatant_exhaustion(self, client, db_session):
        save = _make_game(db_session, exhaustion=2)
        _start_combat(client, save.id)
        r = client.get(f"/api/game/{save.id}/combat/exhaustion/player")
        assert r.status_code == 200
        body = r.json()
        assert body["exhaustion"] == 2  # carried from character state
        assert body["speed_divisor"] == 2

    def test_add_combatant_exhaustion(self, client, game):
        _start_combat(client, game.id)
        r = client.post(
            f"/api/game/{game.id}/combat/exhaustion/player",
            json={"mode": "add", "levels": 2},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["before"] == 0
        assert body["after"] == 2
        assert body["combat_active"] is True
        # Effective stats reflect exhaustion.
        assert body["combatant"]["effective_speed"] == 15

    def test_six_kills_combatant_and_ends_combat(self, client, game):
        _start_combat(client, game.id)
        r = client.post(
            f"/api/game/{game.id}/combat/exhaustion/player",
            json={"mode": "add", "levels": 6},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["after"] == 6
        assert body["died"] is True
        assert body["combatant"]["is_alive"] is False
        # Player dead → enemies win, combat no longer active.
        assert body["combat_active"] is False
        assert body["winner"] == "enemy"

    def test_combat_endpoint_blocked_out_of_combat(self, client, game):
        r = client.post(
            f"/api/game/{game.id}/combat/exhaustion/player",
            json={"mode": "add", "levels": 1},
        )
        assert r.status_code == 400
        assert "not in combat" in r.json()["detail"].lower()

    def test_unknown_combatant(self, client, game):
        _start_combat(client, game.id)
        r = client.get(f"/api/game/{game.id}/combat/exhaustion/ghost")
        assert r.status_code == 404

    def test_start_combat_carries_exhaustion(self, client, db_session):
        # A character with exhaustion 4 enters combat: player combatant should
        # have an effective max HP of half.
        save = _make_game(db_session, exhaustion=4)
        r = _start_combat(client, save.id)
        encounter = r["encounter"]
        player = next(c for c in encounter["combatants"] if c["id"] == "player")
        assert player["exhaustion"] == 4


# --------------------------------------------------------------------------- #
# Long-rest endpoint reduces exhaustion and persists it
# --------------------------------------------------------------------------- #

class TestLongRestExhaustion:
    def test_long_rest_endpoint_reduces_exhaustion(self, client, db_session):
        save = _make_game(db_session, exhaustion=2)
        r = client.post(f"/api/game/{save.id}/long-rest")
        assert r.status_code == 200
        body = r.json()
        assert body["exhaustion_reduced"] is True
        assert body["exhaustion_before"] == 2
        assert body["exhaustion_after"] == 1
        # Persisted into game_state.
        assert json.loads(save.game_state)["exhaustion"] == 1
        # Surfaced in the response envelope too.
        assert body["exhaustion"] == 1

    def test_long_rest_endpoint_no_exhaustion(self, client, game):
        r = client.post(f"/api/game/{game.id}/long-rest")
        assert r.status_code == 200
        assert r.json()["exhaustion_reduced"] is False

