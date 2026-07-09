"""
Tests for the mounts & vehicles REST API.

Covers:
- GET /mounts/registry + /mounts/{id}: listing, type filtering, 404 on unknown.
- GET /mount: default (on foot) state + summary; reads persisted mount state.
- POST /mount/acquire: fresh healthy mount, gold payment (success, 402 when
  broke, skipped when free), Mounted Combatant feat auto-detection.
- POST /mount/mount-up / /mount/dismount: toggling the saddle; 400 when no
  mount or when the mount is downed.
- POST /mount/pace: sets pace + gallop, returns pace note.
- POST /mount/damage: partial damage narrates; lethal damage (0 HP) forces a
  dismount + prone outcome and persists.
- POST /mount/heal: clamps to max HP.
- POST /mount/combat: modifiers + advantage-vs-target resolution; Mounted
  Combatant feat auto-detected from the character's learned feats.
- POST /mount/travel: adjusted travel-hours preview reflects mount + pace.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.models.models import Character, World, GameSave


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _make_game(db_session, *, gold=500, mount=None, feats=None):
    """A Fighter with optional mount state and learned feats."""
    char = Character(
        name="Soren", race="Human", char_class="Fighter", level=5,
        classes=json.dumps({"fighter": 5}),
        strength=16, dexterity=12, constitution=14, intelligence=10,
        wisdom=10, charisma=10,
        max_hp=45, current_hp=45, armor_class=16, speed=30,
        gold=gold, feats=json.dumps(feats or []),
    )
    db_session.add(char)
    db_session.flush()

    w = World(
        name="Frontier", description="Open plains and distant peaks.",
        world_data='{"starting_settlement": {"name": "Crossroads"}}', tone="heroic",
    )
    db_session.add(w)
    db_session.flush()

    state = {"location": "Crossroads", "in_combat": False, "conditions": []}
    if mount is not None:
        state["mount"] = mount
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


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

class TestRegistry:
    def test_list_all(self, client, game):
        r = client.get(f"/api/game/{game.id}/mounts/registry")
        assert r.status_code == 200
        body = r.json()
        assert len(body) >= 18
        ids = {m["id"] for m in body}
        assert {"warhorse", "riding_horse", "pegasus", "cart"} <= ids
        # Each entry includes derived fields.
        horse = next(m for m in body if m["id"] == "warhorse")
        assert horse["speed_multiplier"] == 2.0
        assert "carrying_capacity_lbs" in horse

    def test_filter_by_type(self, client, game):
        r = client.get(f"/api/game/{game.id}/mounts/registry?type=flying")
        assert r.status_code == 200
        body = r.json()
        assert body and all(m["type"] == "flying" for m in body)
        assert "pegasus" in {m["id"] for m in body}

    def test_get_one(self, client, game):
        r = client.get(f"/api/game/{game.id}/mounts/pegasus")
        assert r.status_code == 200
        m = r.json()
        assert m["name"] == "Pegasus"
        assert m["can_fly"] is True

    def test_get_unknown_404(self, client, game):
        r = client.get(f"/api/game/{game.id}/mounts/titan")
        assert r.status_code == 404

    def test_registry_unknown_game_404(self, client):
        assert client.get("/api/game/9999/mounts/registry").status_code == 404


# --------------------------------------------------------------------------- #
# GET /mount
# --------------------------------------------------------------------------- #

class TestGetMount:
    def test_default_on_foot(self, client, game):
        r = client.get(f"/api/game/{game.id}/mount")
        assert r.status_code == 200
        body = r.json()
        assert body["summary"]["has_mount"] is False
        assert body["has_mounted_combatant"] is False
        assert body["state"]["mount_id"] == ""

    def test_reads_persisted_mount(self, client, db_session):
        mount = {
            "mount_id": "warhorse", "current_hp": 12, "max_hp": 19,
            "mounted": True, "conditions": [], "pace": "fast", "galloping": False,
        }
        game = _make_game(db_session, mount=mount)
        body = client.get(f"/api/game/{game.id}/mount").json()
        assert body["summary"]["has_mount"] is True
        assert body["summary"]["mounted"] is True
        assert body["summary"]["mount_hp"] == "12/19"


# --------------------------------------------------------------------------- #
# POST /mount/acquire
# --------------------------------------------------------------------------- #

class TestAcquire:
    def test_acquire_free_mount(self, client, game):
        r = client.post(f"/api/game/{game.id}/mount/acquire",
                        json={"mount_id": "riding_horse"})
        assert r.status_code == 200
        body = r.json()
        assert body["state"]["mount_id"] == "riding_horse"
        assert body["state"]["current_hp"] == body["state"]["max_hp"]
        assert body["state"]["mounted"] is True
        assert body["paid_gp"] == 0

    def test_acquire_paid_mount_deducts_gold(self, client, db_session):
        game = _make_game(db_session, gold=500)
        r = client.post(f"/api/game/{game.id}/mount/acquire",
                        json={"mount_id": "warhorse", "pay": True})  # 400 gp
        assert r.status_code == 200
        body = r.json()
        assert body["paid_gp"] == 400
        assert body["character_gold"] == 100

    def test_acquire_paid_mount_insufficient(self, client, db_session):
        game = _make_game(db_session, gold=100)
        r = client.post(f"/api/game/{game.id}/mount/acquire",
                        json={"mount_id": "warhorse", "pay": True})  # 400 gp
        assert r.status_code == 402
        # Gold unchanged.
        db_session.refresh(game.character)
        assert game.character.gold == 100

    def test_acquire_unknown_mount_404(self, client, game):
        r = client.post(f"/api/game/{game.id}/mount/acquire",
                        json={"mount_id": "titan"})
        assert r.status_code == 404

    def test_acquire_unmounted(self, client, game):
        r = client.post(f"/api/game/{game.id}/mount/acquire",
                        json={"mount_id": "mule", "mounted": False})
        assert r.status_code == 200
        assert r.json()["state"]["mounted"] is False

    def test_acquire_logs_to_story(self, client, game):
        client.post(f"/api/game/{game.id}/mount/acquire",
                    json={"mount_id": "riding_horse"})
        story = json.loads(game.story_log)
        assert any("acquires" in e["content"] for e in story)


# --------------------------------------------------------------------------- #
# mount-up / dismount
# --------------------------------------------------------------------------- #

class TestSaddle:
    def test_mount_up_and_dismount(self, client, game):
        # Acquire unmounted first.
        client.post(f"/api/game/{game.id}/mount/acquire",
                    json={"mount_id": "warhorse", "mounted": False})
        r = client.post(f"/api/game/{game.id}/mount/mount-up")
        assert r.status_code == 200
        assert r.json()["state"]["mounted"] is True
        r = client.post(f"/api/game/{game.id}/mount/dismount")
        assert r.status_code == 200
        assert r.json()["state"]["mounted"] is False

    def test_mount_up_no_mount_400(self, client, game):
        r = client.post(f"/api/game/{game.id}/mount/mount-up")
        assert r.status_code == 400

    def test_mount_up_downed_400(self, client, db_session):
        mount = {"mount_id": "warhorse", "current_hp": 0, "max_hp": 19,
                 "mounted": False}
        game = _make_game(db_session, mount=mount)
        r = client.post(f"/api/game/{game.id}/mount/mount-up")
        assert r.status_code == 400


# --------------------------------------------------------------------------- #
# POST /mount/pace
# --------------------------------------------------------------------------- #

class TestPace:
    def test_set_pace(self, client, game):
        client.post(f"/api/game/{game.id}/mount/acquire",
                    json={"mount_id": "riding_horse"})
        r = client.post(f"/api/game/{game.id}/mount/pace",
                        json={"pace": "fast", "galloping": True})
        assert r.status_code == 200
        body = r.json()
        assert body["state"]["pace"] == "fast"
        assert body["state"]["galloping"] is True
        assert "Fast pace" in body["pace_note"]


# --------------------------------------------------------------------------- #
# POST /mount/damage + /mount/heal
# --------------------------------------------------------------------------- #

class TestDamageHeal:
    def test_partial_damage(self, client, game):
        client.post(f"/api/game/{game.id}/mount/acquire",
                    json={"mount_id": "warhorse"})  # 19 hp
        r = client.post(f"/api/game/{game.id}/mount/damage", json={"amount": 5})
        assert r.status_code == 200
        body = r.json()
        assert body["state"]["current_hp"] == 14
        assert body["outcome"]["forced_dismount"] is False

    def test_lethal_damage_forces_dismount(self, client, game):
        client.post(f"/api/game/{game.id}/mount/acquire",
                    json={"mount_id": "warhorse"})
        r = client.post(f"/api/game/{game.id}/mount/damage", json={"amount": 25})
        assert r.status_code == 200
        body = r.json()
        assert body["state"]["current_hp"] == 0
        assert body["state"]["mounted"] is False
        assert body["outcome"]["forced_dismount"] is True
        assert body["outcome"]["rider_prone"] is True
        assert body["overflow"] == 6
        # Persisted to DB.
        persisted = client.get(f"/api/game/{game.id}/mount").json()
        assert persisted["state"]["current_hp"] == 0
        assert persisted["state"]["mounted"] is False

    def test_damage_no_mount_400(self, client, game):
        r = client.post(f"/api/game/{game.id}/mount/damage", json={"amount": 5})
        assert r.status_code == 400

    def test_heal_clamps(self, client, game):
        client.post(f"/api/game/{game.id}/mount/acquire",
                    json={"mount_id": "warhorse"})
        client.post(f"/api/game/{game.id}/mount/damage", json={"amount": 10})  # →9
        r = client.post(f"/api/game/{game.id}/mount/heal", json={"amount": 50})
        assert r.status_code == 200
        body = r.json()
        assert body["state"]["current_hp"] == 19  # max
        assert body["healed"] == 10


# --------------------------------------------------------------------------- #
# POST /mount/combat
# --------------------------------------------------------------------------- #

class TestCombatModifiers:
    def test_no_mount_no_advantage(self, client, game):
        r = client.post(f"/api/game/{game.id}/mount/combat",
                        json={"target_size": "medium"})
        assert r.status_code == 200
        body = r.json()
        assert body["modifiers"]["mounted"] is False
        assert body["melee_advantage_vs_target"] is False

    def test_mounted_advantage_vs_medium(self, client, game):
        client.post(f"/api/game/{game.id}/mount/acquire",
                    json={"mount_id": "warhorse"})  # large
        r = client.post(f"/api/game/{game.id}/mount/combat",
                        json={"target_size": "medium"})
        body = r.json()
        assert body["modifiers"]["mounted"] is True
        assert body["modifiers"]["melee_advantage"] is True
        assert body["melee_advantage_vs_target"] is True

    def test_no_advantage_vs_mounted_target(self, client, game):
        client.post(f"/api/game/{game.id}/mount/acquire",
                    json={"mount_id": "warhorse"})
        r = client.post(f"/api/game/{game.id}/mount/combat",
                        json={"target_size": "small", "target_mounted": True})
        assert r.json()["melee_advantage_vs_target"] is False

    def test_mounted_combatant_feat_autodetected(self, client, db_session):
        feats = [{"name": "Mounted Combatant"}]
        game = _make_game(db_session, feats=feats)
        client.post(f"/api/game/{game.id}/mount/acquire",
                    json={"mount_id": "warhorse"})
        r = client.post(f"/api/game/{game.id}/mount/combat",
                        json={"target_size": "medium"})
        body = r.json()
        assert body["has_mounted_combatant"] is True
        assert body["modifiers"]["mount_dex_save_advantage"] is True
        assert body["modifiers"]["can_redirect_attack_to_rider"] is True

    def test_feat_override_false(self, client, db_session):
        feats = [{"name": "Mounted Combatant"}]
        game = _make_game(db_session, feats=feats)
        client.post(f"/api/game/{game.id}/mount/acquire",
                    json={"mount_id": "warhorse"})
        r = client.post(f"/api/game/{game.id}/mount/combat",
                        json={"has_feat": False, "target_size": "medium"})
        body = r.json()
        assert body["has_mounted_combatant"] is False
        assert body["modifiers"]["mount_dex_save_advantage"] is False

    def test_weapon_rules_included(self, client, game):
        r = client.post(f"/api/game/{game.id}/mount/combat",
                        json={"target_size": "medium"})
        lance = r.json()["weapon_rules"]["lance"]
        assert lance["one_handed_while_mounted"] is True


# --------------------------------------------------------------------------- #
# POST /mount/travel
# --------------------------------------------------------------------------- #

class TestTravelPreview:
    def test_on_foot(self, client, game):
        r = client.post(f"/api/game/{game.id}/mount/travel", json={"base_hours": 24})
        assert r.status_code == 200
        assert r.json()["speed"]["adjusted_hours"] == 24

    def test_horse_halves(self, client, game):
        client.post(f"/api/game/{game.id}/mount/acquire",
                    json={"mount_id": "riding_horse"})
        r = client.post(f"/api/game/{game.id}/mount/travel", json={"base_hours": 24})
        assert r.json()["speed"]["adjusted_hours"] == 12

    def test_fast_pace_override(self, client, game):
        client.post(f"/api/game/{game.id}/mount/acquire",
                    json={"mount_id": "riding_horse"})
        r = client.post(f"/api/game/{game.id}/mount/travel",
                        json={"base_hours": 24, "pace": "fast"})
        assert r.json()["speed"]["adjusted_hours"] == 10
