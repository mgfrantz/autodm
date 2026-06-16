"""
Tests for the rest API endpoints.

Covers short rest (spend hit dice), long rest (full HP + slot/dice recovery +
condition clearing), the rest-info overview, and guards (in-combat, 404).
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.models.models import Character, World, GameSave


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def fighter_game(client: TestClient, db_session):
    """A level-5 fighter (d10) with some damage taken and hit dice available."""
    char = Character(
        name="Borin", race="Dwarf", char_class="Fighter", level=5,
        classes=json.dumps({"fighter": 5}),
        strength=16, dexterity=12, constitution=14, intelligence=10,
        wisdom=10, charisma=10,
        max_hp=40, current_hp=15, armor_class=16, speed=30,
        hit_dice_used=0,
    )
    db_session.add(char)
    db_session.flush()

    w = World(
        name="Test World", description="A world.",
        world_data='{"starting_settlement": {"name": "Town"}}', tone="heroic",
    )
    db_session.add(w)
    db_session.flush()

    save = GameSave(
        name="Test Game", character_id=char.id, world_id=w.id,
        game_state=json.dumps({
            "location": "Town", "in_combat": False, "conditions": [],
        }),
        story_log="[]",
    )
    db_session.add(save)
    db_session.commit()
    return save


@pytest.fixture
def wizard_game(client: TestClient, db_session):
    """A level-3 wizard caster for spell-slot recovery tests."""
    char = Character(
        name="Elara", race="Elf", char_class="Wizard", level=3,
        classes=json.dumps({"wizard": 3}),
        strength=8, dexterity=14, constitution=12, intelligence=16,
        wisdom=12, charisma=10,
        max_hp=20, current_hp=8, armor_class=13, speed=30,
        hit_dice_used=0,
    )
    db_session.add(char)
    db_session.flush()

    w = World(
        name="Magic World", description="A magical world.",
        world_data='{"starting_settlement": {"name": "Tower"}}', tone="arcane",
    )
    db_session.add(w)
    db_session.flush()

    save = GameSave(
        name="Wizard Game", character_id=char.id, world_id=w.id,
        game_state=json.dumps({"location": "Tower", "in_combat": False, "conditions": []}),
        story_log="[]",
    )
    db_session.add(save)
    db_session.commit()
    return save


# --------------------------------------------------------------------------- #
# GET /rest — rest info
# --------------------------------------------------------------------------- #

class TestRestInfo:
    def test_get_rest_info(self, client: TestClient, fighter_game):
        save = fighter_game
        r = client.get(f"/api/game/{save.id}/rest")
        assert r.status_code == 200
        data = r.json()
        assert data["character_name"] == "Borin"
        assert data["level"] == 5
        assert data["primary_class"] == "fighter"
        assert data["constitution_modifier"] == 2  # CON 14
        assert data["current_hp"] == 15
        assert data["max_hp"] == 40
        assert data["hit_dice_total"] == 5
        assert data["hit_dice_available"] == 5
        assert data["hit_dice_used"] == 0
        assert data["hit_die_size"] == 10  # fighter d10
        assert data["is_caster"] is False

    def test_rest_info_404(self, client: TestClient):
        r = client.get("/api/game/9999/rest")
        assert r.status_code == 404


# --------------------------------------------------------------------------- #
# POST /short-rest
# --------------------------------------------------------------------------- #

class TestShortRestAPI:
    def test_short_rest_heals_and_spends_dice(self, client: TestClient, fighter_game):
        save = fighter_game
        # 15/40 HP, spend 2 dice -> heals some HP
        r = client.post(f"/api/game/{save.id}/short-rest", json={"num_dice": 2})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["hit_dice_spent"] == 2
        assert data["hp_after"] > 15
        assert data["hp_after"] <= 40
        assert len(data["rolls"]) == 2
        # Persisted: character HP raised, hit_dice_used incremented
        assert data["character"]["current_hp"] == data["hp_after"]
        assert data["character"]["hit_dice_used"] == 2

    def test_short_rest_no_body_defaults(self, client: TestClient, fighter_game):
        save = fighter_game
        # No body -> default behavior (spend until full or exhausted)
        r = client.post(f"/api/game/{save.id}/short-rest")
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["hit_dice_spent"] >= 1
        # Spends available dice (max 5 at level 5)
        assert data["hit_dice_spent"] <= 5

    def test_short_rest_stops_at_full_hp(self, client: TestClient, db_session):
        # Character near full HP
        char = Character(
            name="Fullish", race="Human", char_class="Fighter", level=5,
            classes=json.dumps({"fighter": 5}),
            strength=16, dexterity=12, constitution=14, intelligence=10,
            wisdom=10, charisma=10,
            max_hp=40, current_hp=39, armor_class=16, speed=30, hit_dice_used=0,
        )
        db_session.add(char)
        db_session.flush()
        w = World(name="W", description="d",
                  world_data='{"starting_settlement": {"name": "T"}}', tone="heroic")
        db_session.add(w)
        db_session.flush()
        save = GameSave(name="G", character_id=char.id, world_id=w.id,
                        game_state=json.dumps({"in_combat": False}), story_log="[]")
        db_session.add(save)
        db_session.commit()

        r = client.post(f"/api/game/{save.id}/short-rest", json={"num_dice": 3})
        data = r.json()
        # A single die tops off the 1 missing HP; no waste
        assert data["hp_after"] == 40
        assert data["hp_healed"] == 1
        assert data["hit_dice_spent"] == 1

    def test_short_rest_full_hp_is_noop(self, client: TestClient, db_session):
        char = Character(
            name="Max", race="Human", char_class="Fighter", level=5,
            classes=json.dumps({"fighter": 5}),
            strength=16, dexterity=12, constitution=14, intelligence=10,
            wisdom=10, charisma=10,
            max_hp=40, current_hp=40, armor_class=16, speed=30, hit_dice_used=0,
        )
        db_session.add(char)
        db_session.flush()
        w = World(name="W", description="d",
                  world_data='{"starting_settlement": {"name": "T"}}', tone="heroic")
        db_session.add(w)
        db_session.flush()
        save = GameSave(name="G", character_id=char.id, world_id=w.id,
                        game_state=json.dumps({"in_combat": False}), story_log="[]")
        db_session.add(save)
        db_session.commit()

        r = client.post(f"/api/game/{save.id}/short-rest")
        data = r.json()
        assert data["success"] is False
        assert data["hit_dice_spent"] == 0
        assert data["hp_after"] == 40

    def test_short_rest_no_dice_left(self, client: TestClient, db_session):
        char = Character(
            name="Tired", race="Human", char_class="Fighter", level=3,
            classes=json.dumps({"fighter": 3}),
            strength=16, dexterity=12, constitution=14, intelligence=10,
            wisdom=10, charisma=10,
            max_hp=30, current_hp=5, armor_class=16, speed=30, hit_dice_used=3,
        )
        db_session.add(char)
        db_session.flush()
        w = World(name="W", description="d",
                  world_data='{"starting_settlement": {"name": "T"}}', tone="heroic")
        db_session.add(w)
        db_session.flush()
        save = GameSave(name="G", character_id=char.id, world_id=w.id,
                        game_state=json.dumps({"in_combat": False}), story_log="[]")
        db_session.add(save)
        db_session.commit()

        r = client.post(f"/api/game/{save.id}/short-rest")
        data = r.json()
        assert data["success"] is False
        assert "No Hit Dice" in data["message"]
        # HP unchanged
        assert data["character"]["current_hp"] == 5

    def test_short_rest_blocked_in_combat(self, client: TestClient, db_session):
        char = Character(
            name="Fighting", race="Human", char_class="Fighter", level=5,
            classes=json.dumps({"fighter": 5}),
            strength=16, dexterity=12, constitution=14, intelligence=10,
            wisdom=10, charisma=10,
            max_hp=40, current_hp=10, armor_class=16, speed=30, hit_dice_used=0,
        )
        db_session.add(char)
        db_session.flush()
        w = World(name="W", description="d",
                  world_data='{"starting_settlement": {"name": "T"}}', tone="heroic")
        db_session.add(w)
        db_session.flush()
        save = GameSave(name="G", character_id=char.id, world_id=w.id,
                        game_state=json.dumps({"in_combat": True}), story_log="[]")
        db_session.add(save)
        db_session.commit()

        r = client.post(f"/api/game/{save.id}/short-rest")
        assert r.status_code == 400

    def test_short_rest_404(self, client: TestClient):
        r = client.post("/api/game/9999/short-rest")
        assert r.status_code == 404

    def test_short_rest_logs_to_story(self, client: TestClient, fighter_game):
        save = fighter_game
        client.post(f"/api/game/{save.id}/short-rest", json={"num_dice": 1})
        state = client.get(f"/api/game/{save.id}/state").json()
        assert any(e["role"] == "system" and "Short rest" in e["content"]
                   for e in state["story_log"])


# --------------------------------------------------------------------------- #
# POST /long-rest
# --------------------------------------------------------------------------- #

class TestLongRestAPI:
    def test_long_rest_restores_full_hp_and_dice(self, client: TestClient, db_session):
        # Fighter level 4 with some damage and 3 dice used
        char = Character(
            name="Worn", race="Human", char_class="Fighter", level=4,
            classes=json.dumps({"fighter": 4}),
            strength=16, dexterity=12, constitution=14, intelligence=10,
            wisdom=10, charisma=10,
            max_hp=35, current_hp=10, armor_class=16, speed=30, hit_dice_used=3,
        )
        db_session.add(char)
        db_session.flush()
        w = World(name="W", description="d",
                  world_data='{"starting_settlement": {"name": "T"}}', tone="heroic")
        db_session.add(w)
        db_session.flush()
        save = GameSave(name="G", character_id=char.id, world_id=w.id,
                        game_state=json.dumps({"in_combat": False, "conditions": []}),
                        story_log="[]")
        db_session.add(save)
        db_session.commit()

        r = client.post(f"/api/game/{save.id}/long-rest")
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["hp_after"] == 35
        assert data["hp_healed"] == 25
        # level 4 -> recover half (2), capped by spent (3) -> regain 2
        assert data["hit_dice_recovered"] == 2
        assert data["hit_dice_used_after"] == 1
        assert data["character"]["current_hp"] == 35
        assert data["character"]["hit_dice_used"] == 1
        # Non-caster -> no slots
        assert data["slots_recovered"] is False

    def test_long_rest_clears_conditions(self, client: TestClient, db_session):
        char = Character(
            name="Sick", race="Human", char_class="Fighter", level=5,
            classes=json.dumps({"fighter": 5}),
            strength=16, dexterity=12, constitution=14, intelligence=10,
            wisdom=10, charisma=10,
            max_hp=40, current_hp=20, armor_class=16, speed=30, hit_dice_used=1,
        )
        db_session.add(char)
        db_session.flush()
        w = World(name="W", description="d",
                  world_data='{"starting_settlement": {"name": "T"}}', tone="heroic")
        db_session.add(w)
        db_session.flush()
        save = GameSave(
            name="G", character_id=char.id, world_id=w.id,
            game_state=json.dumps({
                "in_combat": False,
                "conditions": ["poisoned", "frightened", "paralyzed"],
            }),
            story_log="[]",
        )
        db_session.add(save)
        db_session.commit()

        r = client.post(f"/api/game/{save.id}/long-rest")
        data = r.json()
        assert "poisoned" in data["conditions_cleared"]
        assert "frightened" in data["conditions_cleared"]
        # paralyzed NOT cleared -> remains in game state
        assert "paralyzed" not in data["conditions_cleared"]
        assert data["conditions"] == ["paralyzed"]

    def test_long_rest_recovers_spell_slots(self, client: TestClient, wizard_game):
        save = wizard_game
        # Initialize the wizard's spellbook (caster)
        client.post(f"/api/characters/{save.character_id}/spells/initialize")
        # Cast a spell to deplete a level-1 slot
        cast = client.post(
            f"/api/characters/{save.character_id}/spells/cast",
            json={"spell_id": "magic_missile"},
        )
        assert cast.status_code == 200
        assert cast.json()["slot_level"] == 1

        # Verify one level-1 slot is used before the rest
        book = client.get(f"/api/characters/{save.character_id}/spells").json()
        used_before = next(s for s in book["slots"] if s["level"] == 1)["used"]
        assert used_before == 1

        # Long rest recovers all slots
        r = client.post(f"/api/game/{save.id}/long-rest")
        data = r.json()
        assert data["slots_recovered"] is True
        assert data["spell_slots"] is not None
        slot1 = next(s for s in data["spell_slots"] if s["level"] == 1)
        assert slot1["used"] == 0

    def test_long_rest_full_hp_when_already_full(self, client: TestClient, db_session):
        char = Character(
            name="Fresh", race="Human", char_class="Fighter", level=5,
            classes=json.dumps({"fighter": 5}),
            strength=16, dexterity=12, constitution=14, intelligence=10,
            wisdom=10, charisma=10,
            max_hp=40, current_hp=40, armor_class=16, speed=30, hit_dice_used=2,
        )
        db_session.add(char)
        db_session.flush()
        w = World(name="W", description="d",
                  world_data='{"starting_settlement": {"name": "T"}}', tone="heroic")
        db_session.add(w)
        db_session.flush()
        save = GameSave(name="G", character_id=char.id, world_id=w.id,
                        game_state=json.dumps({"in_combat": False, "conditions": []}),
                        story_log="[]")
        db_session.add(save)
        db_session.commit()

        r = client.post(f"/api/game/{save.id}/long-rest")
        data = r.json()
        assert data["hp_healed"] == 0
        assert data["hp_after"] == 40
        # dice still recover
        assert data["hit_dice_recovered"] == 2

    def test_long_rest_blocked_in_combat(self, client: TestClient, db_session):
        char = Character(
            name="Fighting", race="Human", char_class="Fighter", level=5,
            classes=json.dumps({"fighter": 5}),
            strength=16, dexterity=12, constitution=14, intelligence=10,
            wisdom=10, charisma=10,
            max_hp=40, current_hp=10, armor_class=16, speed=30, hit_dice_used=0,
        )
        db_session.add(char)
        db_session.flush()
        w = World(name="W", description="d",
                  world_data='{"starting_settlement": {"name": "T"}}', tone="heroic")
        db_session.add(w)
        db_session.flush()
        save = GameSave(name="G", character_id=char.id, world_id=w.id,
                        game_state=json.dumps({"in_combat": True}), story_log="[]")
        db_session.add(save)
        db_session.commit()

        r = client.post(f"/api/game/{save.id}/long-rest")
        assert r.status_code == 400

    def test_long_rest_404(self, client: TestClient):
        r = client.post("/api/game/9999/long-rest")
        assert r.status_code == 404

    def test_long_rest_logs_to_story(self, client: TestClient, fighter_game):
        save = fighter_game
        client.post(f"/api/game/{save.id}/long-rest")
        state = client.get(f"/api/game/{save.id}/state").json()
        assert any(e["role"] == "system" and "Long rest" in e["content"]
                   for e in state["story_log"])
