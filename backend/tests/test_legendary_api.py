"""
Tests for the Legendary Actions & Lair Actions API (api/legendary.py).

Covers the registry endpoints plus the in-combat legendary/lair flow: starting
combat with a legendary boss + lair, inspecting the budget, spending a
legendary action (attack-kind resolution), exhausting the budget, firing the
lair action, double-fire prevention, and 404/400 error paths.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.models.models import Character, World, GameSave
from app.engine.legendary import ADULT_RED_DRAGON


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _make_game(db_session, *, lair: bool = False):
    """Create a character + world + game save and return the save id."""
    char = Character(
        name="Test Hero",
        race="Human",
        char_class="Fighter",
        level=8,
        classes='{"fighter": 8}',
        strength=18,
        dexterity=12,
        constitution=16,
        intelligence=10,
        wisdom=10,
        charisma=10,
        max_hp=80,
        current_hp=80,
        armor_class=18,
        speed=30,
        inventory="[]",
        spells="{}",
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
        game_state='{"location": "Dragon Lair"}',
        story_log="[]",
        current_act=1,
        xp=0,
    )
    db_session.add(save)
    db_session.commit()
    return save.id


def _start_legendary_combat(client, game_id, *, lair: bool = True):
    """Start combat with the Adult Red Dragon preset (legendary + optional lair)."""
    preset = ADULT_RED_DRAGON.to_dict()
    enemy = {
        "name": preset["name"],
        "max_hp": preset["max_hp"],
        "armor_class": preset["armor_class"],
        "initiative_bonus": preset["initiative_bonus"],
        "speed": preset["speed"],
        "size": preset["size"],
        "strength": preset["strength"],
        "dexterity": preset["dexterity"],
        "cr": preset["cr"],
        "damage_modifiers": preset["damage_modifiers"],
        "attacks": preset["attacks"],
        "is_legendary": True,
        "legendary_actions": preset["legendary_actions"],
        "legendary_budget_max": preset["legendary_budget_max"],
    }
    if lair:
        enemy["lair_actions"] = preset["lair_actions"]
    response = client.post(f"/api/game/{game_id}/combat/start", json={"enemies": [enemy]})
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
class TestRegistry:
    def test_list_creatures(self, client: TestClient):
        r = client.get("/api/game/legendary/creatures")
        assert r.status_code == 200
        data = r.json()
        assert "creatures" in data
        ids = {c["id"] for c in data["creatures"]}
        assert "adult_red_dragon" in ids
        assert "lich" in ids
        assert "tarrasque" in ids
        assert len(data["creatures"]) == 6

    def test_get_creature(self, client: TestClient):
        r = client.get("/api/game/legendary/creatures/lich")
        assert r.status_code == 200
        p = r.json()
        assert p["name"] == "Lich"
        assert p["cr"] == 21
        assert len(p["legendary_actions"]) >= 3

    def test_get_creature_404(self, client: TestClient):
        r = client.get("/api/game/legendary/creatures/nope")
        assert r.status_code == 404


# --------------------------------------------------------------------------- #
# In-combat legendary state
# --------------------------------------------------------------------------- #
class TestLegendaryState:
    def test_get_legendary_state(self, client: TestClient, db_session):
        gid = _make_game(db_session)
        _start_legendary_combat(client, gid)
        # The legendary enemy is enemy_1.
        r = client.get(f"/api/game/{gid}/legendary/enemy_1")
        assert r.status_code == 200
        data = r.json()
        assert data["is_legendary"] is True
        assert data["name"] == "Adult Red Dragon"
        assert data["budget_max"] == 3
        assert data["budget_remaining"] == 3
        assert len(data["legendary_actions"]) == 3
        # All 3 actions affordable at full budget.
        assert len(data["available_actions"]) == 3

    def test_get_legendary_state_nonexistent_combatant(self, client: TestClient, db_session):
        gid = _make_game(db_session)
        _start_legendary_combat(client, gid)
        r = client.get(f"/api/game/{gid}/legendary/ghost")
        assert r.status_code == 404

    def test_get_encounter_legendary(self, client: TestClient, db_session):
        gid = _make_game(db_session)
        _start_legendary_combat(client, gid)
        r = client.get(f"/api/game/{gid}/legendary")
        assert r.status_code == 200
        data = r.json()
        assert data["in_combat"] is True
        assert data["has_lair"] is True
        assert len(data["legendary_creatures"]) == 1
        assert data["legendary_creatures"][0]["name"] == "Adult Red Dragon"

    def test_not_in_combat(self, client: TestClient, db_session):
        gid = _make_game(db_session)
        r = client.get(f"/api/game/{gid}/legendary/enemy_1")
        assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Using legendary actions
# --------------------------------------------------------------------------- #
class TestUseLegendaryAction:
    def test_use_detect_action(self, client: TestClient, db_session):
        gid = _make_game(db_session)
        _start_legendary_combat(client, gid)
        r = client.post(
            f"/api/game/{gid}/legendary/use",
            json={"combatant_id": "enemy_1", "action_id": "detect"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["used"] is True
        assert data["remaining_budget"] == 2
        assert "Detect" in data["description"]

    def test_use_attack_action_resolves_attack(self, client: TestClient, db_session):
        gid = _make_game(db_session)
        _start_legendary_combat(client, gid)
        # Tail Attack is an attack-kind action; needs a target_id.
        r = client.post(
            f"/api/game/{gid}/legendary/use",
            json={"combatant_id": "enemy_1", "action_id": "tail_attack",
                  "target_id": "player"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["used"] is True
        assert data["remaining_budget"] == 2
        # The attack resolution description names attacker + target + weapon.
        assert "Adult Red Dragon" in data["description"]
        assert "Tail" in data["description"]
        assert "Test Hero" in data["description"]

    def test_attack_action_requires_target(self, client: TestClient, db_session):
        gid = _make_game(db_session)
        _start_legendary_combat(client, gid)
        r = client.post(
            f"/api/game/{gid}/legendary/use",
            json={"combatant_id": "enemy_1", "action_id": "tail_attack"},
        )
        assert r.status_code == 400
        assert "target_id" in r.json()["detail"]

    def test_use_two_cost_action(self, client: TestClient, db_session):
        gid = _make_game(db_session)
        _start_legendary_combat(client, gid)
        r = client.post(
            f"/api/game/{gid}/legendary/use",
            json={"combatant_id": "enemy_1", "action_id": "wing_attack"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["used"] is True
        assert data["remaining_budget"] == 1  # cost 2

    def test_exhaust_budget_blocks_further_use(self, client: TestClient, db_session):
        gid = _make_game(db_session)
        _start_legendary_combat(client, gid)
        # Spend detect (1) + tail (1) + wing (2) = 4 > 3, so wing should fail
        # after detect + tail + detect... actually 3 budget: detect+tail+detect?
        # Use detect (1), tail (1) — 1 left. Wing costs 2 → blocked.
        client.post(f"/api/game/{gid}/legendary/use",
                    json={"combatant_id": "enemy_1", "action_id": "detect"})
        client.post(f"/api/game/{gid}/legendary/use",
                    json={"combatant_id": "enemy_1", "action_id": "detect"})
        # Now 1 left; wing (cost 2) blocked.
        r = client.post(f"/api/game/{gid}/legendary/use",
                        json={"combatant_id": "enemy_1", "action_id": "wing_attack"})
        assert r.status_code == 400
        assert "Not enough" in r.json()["detail"]

    def test_unknown_action_400(self, client: TestClient, db_session):
        gid = _make_game(db_session)
        _start_legendary_combat(client, gid)
        r = client.post(
            f"/api/game/{gid}/legendary/use",
            json={"combatant_id": "enemy_1", "action_id": "nope"},
        )
        assert r.status_code == 400

    def test_story_log_recorded(self, client: TestClient, db_session):
        gid = _make_game(db_session)
        _start_legendary_combat(client, gid)
        client.post(f"/api/game/{gid}/legendary/use",
                    json={"combatant_id": "enemy_1", "action_id": "detect"})
        save = db_session.query(GameSave).filter(GameSave.id == gid).first()
        story = json.loads(save.story_log)
        assert any("legendary action Detect" in e["content"] for e in story)


# --------------------------------------------------------------------------- #
# Lair actions
# --------------------------------------------------------------------------- #
class TestLairActions:
    def test_get_lair_state(self, client: TestClient, db_session):
        gid = _make_game(db_session)
        _start_legendary_combat(client, gid, lair=True)
        r = client.get(f"/api/game/{gid}/lair")
        assert r.status_code == 200
        data = r.json()
        assert data["has_lair"] is True
        assert data["initiative_count"] == 20
        assert len(data["lair_actions"]) == 2

    def test_fire_lair_action(self, client: TestClient, db_session):
        gid = _make_game(db_session)
        _start_legendary_combat(client, gid, lair=True)
        r = client.post(f"/api/game/{gid}/lair/action")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["triggered"] is True
        assert data["action"] is not None
        assert "Lair action" in data["description"]
        assert data["lair_last_fired_round"] == 1

    def test_lair_action_no_repeat_same_round(self, client: TestClient, db_session):
        gid = _make_game(db_session)
        _start_legendary_combat(client, gid, lair=True)
        first = client.post(f"/api/game/{gid}/lair/action")
        assert first.status_code == 200
        second = client.post(f"/api/game/{gid}/lair/action")
        assert second.status_code == 400  # already fired this round

    def test_lair_action_no_lair_400(self, client: TestClient, db_session):
        gid = _make_game(db_session)
        _start_legendary_combat(client, gid, lair=False)
        r = client.post(f"/api/game/{gid}/lair/action")
        assert r.status_code == 400

    def test_lair_action_logged(self, client: TestClient, db_session):
        gid = _make_game(db_session)
        _start_legendary_combat(client, gid, lair=True)
        client.post(f"/api/game/{gid}/lair/action")
        save = db_session.query(GameSave).filter(GameSave.id == gid).first()
        story = json.loads(save.story_log)
        assert any("Lair action" in e["content"] for e in story)
