"""
Tests for the save/load API — named save-game snapshots and state restoration.

Covers snapshot creation, listing, detail retrieval, full restoration of
character + game state on load, deletion, and error cases. The most important
behaviour tested is that loading a snapshot rewinds *mutable character state*
(HP, XP, level, inventory) back to what it was at save time.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.models.models import Character, World, GameSave, SaveSlot


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def make_game(db_session):
    """Factory: insert a character + world + game save and return the save id."""

    counter = {"n": 0}

    def _make(**char_overrides):
        counter["n"] += 1
        n = counter["n"]
        char = Character(
            name=f"Hero {n}",
            race="Human",
            char_class="Fighter",
            level=char_overrides.pop("level", 1),
            strength=16,
            dexterity=12,
            constitution=14,
            intelligence=10,
            wisdom=10,
            charisma=10,
            max_hp=char_overrides.pop("max_hp", 12),
            current_hp=char_overrides.pop("current_hp", 12),
            armor_class=16,
            speed=30,
            xp=char_overrides.pop("xp", 0),
            inventory=char_overrides.pop("inventory", "[]"),
            spells=char_overrides.pop("spells", "{}"),
            **char_overrides,
        )
        db_session.add(char)
        db_session.flush()

        w = World(
            name=f"World {n}",
            description="A test world.",
            world_data='{"starting_settlement": {"name": "Test Town"}}',
            tone="heroic fantasy",
        )
        db_session.add(w)
        db_session.flush()

        save = GameSave(
            name=f"Game {n}",
            character_id=char.id,
            world_id=w.id,
            game_state='{"location": "Test Town", "in_combat": false}',
            story_log=json.dumps([{"role": "dm", "content": "Intro"}]),
            current_act=1,
            xp=0,
        )
        db_session.add(save)
        db_session.commit()
        return save.id

    return _make


# --------------------------------------------------------------------------- #
# Create save
# --------------------------------------------------------------------------- #
class TestCreateSave:
    def test_create_save_returns_summary(self, client: TestClient, make_game):
        game_id = make_game()

        resp = client.post(f"/api/game/{game_id}/save", json={"slot_name": "Before Dragon"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["slot_name"] == "Before Dragon"
        assert data["game_save_id"] == game_id
        assert data["id"] is not None
        assert data["character_level"] == 1
        assert data["character_hp"] == 12
        assert data["character_max_hp"] == 12
        assert data["xp"] == 0

    def test_create_save_captures_character_snapshot(self, client: TestClient, make_game):
        game_id = make_game(current_hp=7, max_hp=12, xp=300, level=2)

        resp = client.post(f"/api/game/{game_id}/save", json={"slot_name": "Mid Dungeon"})
        assert resp.status_code == 200

        # The snapshot should reflect the live (mutated) state at save time.
        detail = client.get(f"/api/game/{game_id}/saves/{resp.json()['id']}").json()
        snap = detail["character_snapshot"]
        assert snap["current_hp"] == 7
        assert snap["max_hp"] == 12
        assert snap["xp"] == 300
        assert snap["level"] == 2

    def test_create_save_404_missing_game(self, client: TestClient):
        resp = client.post("/api/game/9999/save", json={"slot_name": "x"})
        assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# List saves
# --------------------------------------------------------------------------- #
class TestListSaves:
    def test_list_saves_empty(self, client: TestClient, make_game):
        game_id = make_game()
        resp = client.get(f"/api/game/{game_id}/saves")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_saves_multiple(self, client: TestClient, make_game):
        game_id = make_game()
        client.post(f"/api/game/{game_id}/save", json={"slot_name": "A"})
        client.post(f"/api/game/{game_id}/save", json={"slot_name": "B"})

        resp = client.get(f"/api/game/{game_id}/saves")
        assert resp.status_code == 200
        names = [s["slot_name"] for s in resp.json()]
        assert names == ["B", "A"]  # newest first

    def test_list_saves_scoped_to_game(self, client: TestClient, make_game):
        """Saves from one game must not leak into another game's list."""
        game1 = make_game()
        game2 = make_game()
        client.post(f"/api/game/{game1}/save", json={"slot_name": "G1"})
        client.post(f"/api/game/{game2}/save", json={"slot_name": "G2"})

        resp1 = client.get(f"/api/game/{game1}/saves")
        resp2 = client.get(f"/api/game/{game2}/saves")
        assert [s["slot_name"] for s in resp1.json()] == ["G1"]
        assert [s["slot_name"] for s in resp2.json()] == ["G2"]


# --------------------------------------------------------------------------- #
# Get save detail
# --------------------------------------------------------------------------- #
class TestGetSave:
    def test_get_save_detail(self, client: TestClient, make_game):
        game_id = make_game()
        slot_id = client.post(
            f"/api/game/{game_id}/save", json={"slot_name": "Checkpoint"
        }).json()["id"]

        resp = client.get(f"/api/game/{game_id}/saves/{slot_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slot_name"] == "Checkpoint"
        assert "character_snapshot" in data
        assert "game_state" in data
        assert data["story_log_length"] == 1

    def test_get_save_wrong_game_404(self, client: TestClient, make_game):
        game1 = make_game()
        game2 = make_game()
        slot_id = client.post(
            f"/api/game/{game1}/save", json={"slot_name": "G1"
        }).json()["id"]

        # Querying slot from game1 under game2 must 404.
        resp = client.get(f"/api/game/{game2}/saves/{slot_id}")
        assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Load save (the core feature)
# --------------------------------------------------------------------------- #
class TestLoadSave:
    def test_load_restores_character_state(self, client: TestClient, make_game, db_session):
        """Loading must rewind mutated character state to the snapshot."""
        game_id = make_game(current_hp=12, max_hp=12, level=1, xp=0)

        # Save while healthy.
        slot_id = client.post(
            f"/api/game/{game_id}/save", json={"slot_name": "Full HP"
        }).json()["id"]

        # Mutate the live character (simulate taking damage + gaining XP).
        save = db_session.get(GameSave, game_id)
        save.character.current_hp = 3
        save.character.xp = 450
        save.character.level = 2
        db_session.commit()
        # Expire the session cache so subsequent reads hit the DB.
        db_session.expire_all()

        # Load the snapshot.
        resp = client.post(f"/api/game/{game_id}/load/{slot_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Game loaded"
        assert data["slot_name"] == "Full HP"

        # Character should be back to the snapshotted state.
        db_session.expire_all()
        save = db_session.get(GameSave, game_id)
        assert save.character.current_hp == 12
        assert save.character.xp == 0
        assert save.character.level == 1

    def test_load_restores_story_log_and_game_state(
        self, client: TestClient, make_game, db_session
    ):
        game_id = make_game()

        slot_id = client.post(
            f"/api/game/{game_id}/save", json={"slot_name": "Early"
        }).json()["id"]

        # Append new story entries on the live game.
        save = db_session.get(GameSave, game_id)
        log = json.loads(save.story_log)
        log.append({"role": "player", "content": "attack"})
        log.append({"role": "dm", "content": "miss"})
        save.story_log = json.dumps(log)
        state = json.loads(save.game_state)
        state["location"] = "Dark Cave"
        save.game_state = json.dumps(state)
        db_session.commit()

        resp = client.post(f"/api/game/{game_id}/load/{slot_id}")
        assert resp.status_code == 200
        assert resp.json()["story_log_entries"] == 1  # only the original entry

        db_session.expire_all()
        save = db_session.get(GameSave, game_id)
        assert json.loads(save.story_log) == [{"role": "dm", "content": "Intro"}]
        assert json.loads(save.game_state)["location"] == "Test Town"

    def test_load_restores_inventory(self, client: TestClient, make_game, db_session):
        """Inventory changes between save and load must be rewound."""
        inv_at_save = [{"name": "Sword", "quantity": 1}]
        game_id = make_game(inventory=json.dumps(inv_at_save))

        slot_id = client.post(
            f"/api/game/{game_id}/save", json={"slot_name": "Has Sword"
        }).json()["id"]

        # Player picks up loot (mutates live inventory).
        save = db_session.get(GameSave, game_id)
        save.character.inventory = json.dumps(
            [{"name": "Sword", "quantity": 1}, {"name": "Potion", "quantity": 3}]
        )
        db_session.commit()

        client.post(f"/api/game/{game_id}/load/{slot_id}")

        db_session.expire_all()
        save = db_session.get(GameSave, game_id)
        assert json.loads(save.character.inventory) == inv_at_save

    def test_load_missing_slot_404(self, client: TestClient, make_game):
        game_id = make_game()
        resp = client.post(f"/api/game/{game_id}/load/9999")
        assert resp.status_code == 404

    def test_load_wrong_game_404(self, client: TestClient, make_game):
        game1 = make_game()
        game2 = make_game()
        slot_id = client.post(
            f"/api/game/{game1}/save", json={"slot_name": "G1"
        }).json()["id"]
        resp = client.post(f"/api/game/{game2}/load/{slot_id}")
        assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Delete save
# --------------------------------------------------------------------------- #
class TestDeleteSave:
    def test_delete_save(self, client: TestClient, make_game, db_session):
        game_id = make_game()
        slot_id = client.post(
            f"/api/game/{game_id}/save", json={"slot_name": "To Delete"
        }).json()["id"]

        resp = client.delete(f"/api/game/{game_id}/saves/{slot_id}")
        assert resp.status_code == 200

        # No longer listed.
        saves = client.get(f"/api/game/{game_id}/saves").json()
        assert saves == []

    def test_delete_missing_slot_404(self, client: TestClient, make_game):
        game_id = make_game()
        resp = client.delete(f"/api/game/{game_id}/saves/9999")
        assert resp.status_code == 404

    def test_delete_cascade_on_game_delete(self, client: TestClient, make_game, db_session):
        """Deleting the game save should cascade-delete its slots."""
        game_id = make_game()
        slot_id = client.post(
            f"/api/game/{game_id}/save", json={"slot_name": "Cascade"
        }).json()["id"]

        save = db_session.get(GameSave, game_id)
        db_session.delete(save)
        db_session.commit()

        # Slot row should be gone.
        assert db_session.get(SaveSlot, slot_id) is None


# --------------------------------------------------------------------------- #
# Snapshot/restore helpers (direct unit-level coverage)
# --------------------------------------------------------------------------- #
class TestSnapshotHelpers:
    def test_capture_and_apply_roundtrip(self, db_session):
        from app.api.saves import capture_character_snapshot, apply_character_snapshot

        char = Character(
            name="Roundtrip",
            race="Elf",
            char_class="Wizard",
            level=3,
            xp=900,
            asi_used=0,
            strength=8,
            dexterity=14,
            constitution=12,
            intelligence=17,
            wisdom=12,
            charisma=10,
            max_hp=20,
            current_hp=14,
            armor_class=13,
            speed=30,
            inventory='[{"name": "Staff"}]',
            spells='{"cantrips": ["fire bolt"]}',
        )
        db_session.add(char)
        db_session.commit()

        snap = capture_character_snapshot(char)
        # JSON fields should be parsed into structured form.
        assert snap["inventory"] == [{"name": "Staff"}]
        assert snap["spells"] == {"cantrips": ["fire bolt"]}
        assert snap["current_hp"] == 14
        assert snap["intelligence"] == 17

        # Mutate, then restore.
        char.current_hp = 1
        char.xp = 5000
        char.intelligence = 18
        char.inventory = "[]"
        apply_character_snapshot(char, snap)

        assert char.current_hp == 14
        assert char.xp == 900
        assert char.intelligence == 17
        # Inventory written back as JSON text.
        assert json.loads(char.inventory) == [{"name": "Staff"}]

    def test_apply_snapshot_skips_unknown_keys(self, db_session):
        from app.api.saves import apply_character_snapshot

        char = Character(
            name="Defensive",
            race="Human",
            char_class="Fighter",
            level=1,
            max_hp=10,
            current_hp=10,
            armor_class=15,
            speed=30,
            strength=16,
            dexterity=12,
            constitution=14,
            intelligence=10,
            wisdom=10,
            charisma=10,
        )
        db_session.add(char)
        db_session.commit()
        original_hp = char.current_hp
        apply_character_snapshot(char, {"current_hp": 5, "bogus_field": 999})
        assert char.current_hp == 5
        assert not hasattr(char, "bogus_field")
