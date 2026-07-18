"""
Tests for the game lifecycle — list / load resilience against orphaned saves,
the new ``DELETE /game/{id}`` endpoint, and the relationship cascade that
prevents orphaned ``GameSave`` rows when a Character or World is deleted.

Background: ``GameSave.character_id`` / ``world_id`` are NOT NULL, but a
``GameSave`` can still be *orphaned* if its parent row is deleted without
cascading (raw SQL, a partial DB reset, or the legacy
``db.delete(character)`` before the relationship cascade existed). Before this
fix, dereferencing ``save.character.name`` on an orphan raised ``AttributeError``
and returned a 500 — taking down the whole "continue game" menu (``list_games``).
"""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.models import Character, World, GameSave, SaveSlot


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def make_save(db_session):
    """Factory: insert a character + world + game save and return the save.

    Returns the created (character, world, save) triple so tests can mutate or
    orphan the parents as needed.
    """
    counter = {"n": 0}

    def _make(*, name=None):
        counter["n"] += 1
        n = counter["n"]
        char = Character(
            name=f"Hero {n}",
            race="Human",
            char_class="Fighter",
            level=1,
            strength=16,
            dexterity=12,
            constitution=14,
            max_hp=12,
            current_hp=12,
            armor_class=16,
            speed=30,
            inventory="[]",
            spells="{}",
        )
        db_session.add(char)
        db_session.flush()
        w = World(
            name=f"World {n}",
            description="A test world.",
            world_data='{"starting_settlement": {"name": "Town"}}',
            tone="heroic fantasy",
        )
        db_session.add(w)
        db_session.flush()
        save = GameSave(
            name=name or f"Game {n}",
            character_id=char.id,
            world_id=w.id,
            game_state='{"location": "Town"}',
            story_log=json.dumps([{"role": "dm", "content": "Intro"}]),
        )
        db_session.add(save)
        db_session.commit()
        db_session.refresh(char)
        db_session.refresh(w)
        db_session.refresh(save)
        return char, w, save

    return _make


# --------------------------------------------------------------------------- #
# list_games — orphan resilience
# --------------------------------------------------------------------------- #
class TestListGamesOrphanResilience:
    def test_list_games_excludes_orphaned_saves(self, client: TestClient, make_save, db_session):
        """An orphaned save must NOT crash the list or appear in it."""
        _, _, save = make_save(name="Orphan Game")

        # Orphan the save by raw-deleting its character (bypasses ORM cascade,
        # simulating the legacy bug / a partial DB reset). ``db_session`` is the
        # same session the client's ``get_db`` override yields.
        db_session.execute(text("DELETE FROM characters WHERE id = :i"),
                           {"i": save.character_id})
        db_session.commit()
        db_session.expire_all()

        resp = client.get("/api/game/")
        assert resp.status_code == 200
        games = resp.json()
        # The orphan is excluded — no crash, no entry.
        assert all(g["id"] != save.id for g in games)
        assert games == []

    def test_list_games_keeps_playable_saves_alongside_orphans(
        self, client: TestClient, make_save, db_session
    ):
        """A playable save must still be listed when an orphan also exists."""
        char_good, _, save_good = make_save(name="Good Game")
        _, _, save_orphan = make_save(name="Orphan Game")

        # Orphan only the second save's world.
        db_session.execute(text("DELETE FROM worlds WHERE id = :i"),
                           {"i": save_orphan.world_id})
        db_session.commit()
        db_session.expire_all()

        resp = client.get("/api/game/")
        assert resp.status_code == 200
        games = resp.json()
        ids = {g["id"] for g in games}
        assert save_good.id in ids
        assert save_orphan.id not in ids
        # The playable entry has full details.
        good = next(g for g in games if g["id"] == save_good.id)
        assert good["character_name"] == char_good.name


# --------------------------------------------------------------------------- #
# get_game_state — orphan resilience
# --------------------------------------------------------------------------- #
class TestGetGameStateOrphanResilience:
    def test_get_game_state_410_for_orphaned_save(self, client: TestClient, make_save, db_session):
        """Loading an orphaned save returns 410 Gone, not a 500 crash."""
        _, _, save = make_save(name="Orphan")

        db_session.execute(text("DELETE FROM characters WHERE id = :i"),
                           {"i": save.character_id})
        db_session.commit()
        db_session.expire_all()

        resp = client.get(f"/api/game/{save.id}/state")
        assert resp.status_code == 410
        assert "corrupted" in resp.json()["detail"].lower()
        assert "delete" in resp.json()["detail"].lower()

    def test_get_game_state_works_for_valid_save(self, client: TestClient, make_save):
        """A healthy save loads normally with full character + world data."""
        char, world, save = make_save(name="Healthy")

        resp = client.get(f"/api/game/{save.id}/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] == save.id
        assert data["character"]["name"] == char.name
        assert data["world"]["name"] == world.name


# --------------------------------------------------------------------------- #
# DELETE /game/{id} — new cleanup endpoint
# --------------------------------------------------------------------------- #
class TestDeleteGame:
    def test_delete_game_removes_save(self, client: TestClient, make_save, db_session):
        _, _, save = make_save(name="Doomed")

        resp = client.delete(f"/api/game/{save.id}")
        assert resp.status_code == 200
        assert resp.json() == {"status": "deleted", "id": save.id}
        assert db_session.get(GameSave, save.id) is None

    def test_delete_game_cascades_save_slots(self, client: TestClient, make_save, db_session):
        char, _, save = make_save(name="With Slots")
        # Attach a named snapshot to the game.
        slot = SaveSlot(
            name="Checkpoint",
            game_save_id=save.id,
            character_snapshot='{"level": 1}',
        )
        db_session.add(slot)
        db_session.commit()

        resp = client.delete(f"/api/game/{save.id}")
        assert resp.status_code == 200
        assert db_session.get(GameSave, save.id) is None
        assert db_session.get(SaveSlot, slot.id) is None  # cascaded

    def test_delete_game_works_on_orphaned_save(self, client: TestClient, make_save, db_session):
        """The recovery path: an orphaned save can still be deleted."""
        _, _, save = make_save(name="Orphan")
        # Orphan it via raw SQL (character gone).
        db_session.execute(text("DELETE FROM characters WHERE id = :i"),
                           {"i": save.character_id})
        db_session.commit()
        db_session.expire_all()

        resp = client.delete(f"/api/game/{save.id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        assert db_session.get(GameSave, save.id) is None

    def test_delete_game_404_missing(self, client: TestClient):
        resp = client.delete("/api/game/99999")
        assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Relationship cascade — root-cause fix (prevents future orphans)
# --------------------------------------------------------------------------- #
class TestRelationshipCascade:
    def test_delete_character_cascades_to_saves(self, client: TestClient, make_save, db_session):
        """Deleting a character removes its GameSaves (no orphans left)."""
        char, _, save = make_save(name="Char Cascade")

        resp = client.delete(f"/api/characters/{char.id}")
        assert resp.status_code == 200
        # GameSave must be gone — not orphaned.
        db_session.expire_all()
        assert db_session.get(GameSave, save.id) is None

    def test_delete_world_cascades_to_saves(self, client: TestClient, make_save, db_session):
        """Deleting a world removes its GameSaves (no orphans left)."""
        _, world, save = make_save(name="World Cascade")

        # Worlds have no DELETE endpoint, so delete via ORM directly.
        db_session.delete(world)
        db_session.commit()
        db_session.expire_all()
        assert db_session.get(GameSave, save.id) is None

    def test_delete_character_cascades_to_save_slots(
        self, client: TestClient, make_save, db_session
    ):
        """Character → GameSave → SaveSlot cascade chain."""
        char, _, save = make_save(name="Slot Cascade")
        slot = SaveSlot(
            name="Snap",
            game_save_id=save.id,
            character_snapshot='{"level": 1}',
        )
        db_session.add(slot)
        db_session.commit()

        resp = client.delete(f"/api/characters/{char.id}")
        assert resp.status_code == 200
        db_session.expire_all()
        assert db_session.get(GameSave, save.id) is None
        assert db_session.get(SaveSlot, slot.id) is None
