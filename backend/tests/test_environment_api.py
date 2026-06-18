"""
Tests for the environment API endpoints.

Covers the registry, default environment, full + partial updates, validation
errors, the effects probe, deterministic procedural weather rolls (with seed),
and the combat-modifiers convenience endpoint.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.models.models import Character, World, GameSave


# --------------------------------------------------------------------------- #
# Fixtures.
# --------------------------------------------------------------------------- #

@pytest.fixture
def game(client: TestClient, db_session):
    """A minimal game save with normal daytime environment fields."""
    char = Character(
        name="Ranger", race="Human", char_class="ranger", level=3,
        classes=json.dumps({"ranger": 3}),
        strength=12, dexterity=16, constitution=14, intelligence=10,
        wisdom=14, charisma=10,
        max_hp=28, current_hp=28, armor_class=14, speed=30,
    )
    db_session.add(char)
    db_session.flush()

    w = World(
        name="Wilds", description="A wilderness world.",
        world_data='{"starting_settlement": {"name": "Outpost"}}', tone="wilderness",
    )
    db_session.add(w)
    db_session.flush()

    save = GameSave(
        name="Wild Game", character_id=char.id, world_id=w.id,
        game_state=json.dumps({
            "location": "Outpost",
            "in_combat": False,
            "environment": {
                "light": "bright", "weather": "clear", "terrain": "normal",
                "temperature": "normal", "time_of_day": "day", "notes": "",
            },
        }),
        story_log="[]",
    )
    db_session.add(save)
    db_session.commit()
    return save


@pytest.fixture
def bare_game(client: TestClient, db_session):
    """A game save with NO environment key (backward-compat default)."""
    char = Character(
        name="Wanderer", race="Elf", char_class="rogue", level=2,
        classes=json.dumps({"rogue": 2}),
        strength=10, dexterity=16, constitution=12, intelligence=12,
        wisdom=10, charisma=12,
        max_hp=18, current_hp=18, armor_class=13, speed=30,
    )
    db_session.add(char)
    db_session.flush()

    w = World(
        name="Plains", description="Open plains.",
        world_data='{}', tone="heroic",
    )
    db_session.add(w)
    db_session.flush()

    save = GameSave(
        name="Bare Game", character_id=char.id, world_id=w.id,
        game_state=json.dumps({"location": "Plains", "in_combat": False}),
        story_log="[]",
    )
    db_session.add(save)
    db_session.commit()
    return save


# --------------------------------------------------------------------------- #
# Registry.
# --------------------------------------------------------------------------- #

class TestRegistry:
    def test_registry_lists_all_categories(self, client: TestClient):
        r = client.get("/api/game/environment/registry")
        assert r.status_code == 200
        data = r.json()
        assert "light_levels" in data
        assert "weather" in data
        assert "terrain" in data
        assert "temperature" in data
        assert "time_of_day" in data
        assert "climates" in data
        assert "seasons" in data
        weather_names = {w["name"] for w in data["weather"]}
        assert {"fog", "storm", "blizzard", "strong_wind"} <= weather_names
        terrain_names = {t["name"] for t in data["terrain"]}
        assert "ice" in terrain_names

    def test_registry_does_not_require_game(self, client: TestClient):
        # /environment/registry is global (no game_id).
        r = client.get("/api/game/environment/registry")
        assert r.status_code == 200


# --------------------------------------------------------------------------- #
# GET environment.
# --------------------------------------------------------------------------- #

class TestGetEnvironment:
    def test_get_stored_environment(self, client: TestClient, game):
        r = client.get(f"/api/game/{game.id}/environment")
        assert r.status_code == 200
        data = r.json()
        env = data["environment"]
        assert env["weather"] == "clear"
        assert env["light"] == "bright"
        assert data["effects"]["obscurement"] == "clear"
        assert data["effects"]["summary"] == "No environmental penalties."

    def test_get_default_when_absent(self, client: TestClient, bare_game):
        r = client.get(f"/api/game/{bare_game.id}/environment")
        assert r.status_code == 200
        env = r.json()["environment"]
        # Defaults: clear bright day.
        assert env["weather"] == "clear"
        assert env["light"] == "bright"
        assert env["terrain"] == "normal"

    def test_get_unknown_game_404(self, client: TestClient):
        r = client.get("/api/game/999999/environment")
        assert r.status_code == 404


# --------------------------------------------------------------------------- #
# PUT environment.
# --------------------------------------------------------------------------- #

class TestSetEnvironment:
    def test_full_update(self, client: TestClient, game):
        r = client.put(f"/api/game/{game.id}/environment", json={
            "light": "darkness", "weather": "storm", "terrain": "ice",
            "temperature": "extreme_cold", "time_of_day": "night",
            "notes": "The blizzard howls.",
        })
        assert r.status_code == 200
        data = r.json()
        env = data["environment"]
        assert env["weather"] == "storm"
        assert env["terrain"] == "ice"
        assert env["temperature"] == "extreme_cold"
        assert env["notes"] == "The blizzard howls."
        eff = data["effects"]
        assert eff["heavily_obscured"]
        assert eff["ranged_attack_disadvantage"]
        assert eff["movement_cost_multiplier"] == 2.0
        assert eff["exhaustion_save"]["reason"] == "extreme_cold"

    def test_partial_update_preserves_other_fields(self, client: TestClient, game):
        # Only change weather; everything else stays.
        r = client.put(f"/api/game/{game.id}/environment", json={"weather": "fog"})
        assert r.status_code == 200
        env = r.json()["environment"]
        assert env["weather"] == "fog"
        assert env["light"] == "bright"  # unchanged
        assert env["terrain"] == "normal"  # unchanged
        # Fog heavily obscures even in bright light.
        assert r.json()["effects"]["heavily_obscured"]

    def test_update_notes_only(self, client: TestClient, game):
        r = client.put(f"/api/game/{game.id}/environment", json={"notes": "Wind picks up."})
        assert r.status_code == 200
        assert r.json()["environment"]["notes"] == "Wind picks up."

    def test_update_persists_to_db(self, client: TestClient, game, db_session):
        client.put(f"/api/game/{game.id}/environment", json={"weather": "heavy_rain"})
        db_session.expire_all()
        save = db_session.query(GameSave).filter(GameSave.id == game.id).first()
        state = json.loads(save.game_state)
        assert state["environment"]["weather"] == "heavy_rain"

    def test_invalid_weather_rejected(self, client: TestClient, game):
        r = client.put(f"/api/game/{game.id}/environment", json={"weather": "tornado"})
        assert r.status_code == 422

    def test_invalid_light_rejected(self, client: TestClient, game):
        r = client.put(f"/api/game/{game.id}/environment", json={"light": "twilight"})
        assert r.status_code == 422

    def test_invalid_terrain_rejected(self, client: TestClient, game):
        r = client.put(f"/api/game/{game.id}/environment", json={"terrain": "lava"})
        assert r.status_code == 422

    def test_unknown_game_404(self, client: TestClient):
        r = client.put("/api/game/999999/environment", json={"weather": "fog"})
        assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Effects probe (no persistence).
# --------------------------------------------------------------------------- #

class TestEffectsProbe:
    def test_probe_does_not_persist(self, client: TestClient, game):
        r = client.post(f"/api/game/{game.id}/environment/effects", json={
            "weather": "blizzard", "light": "darkness", "terrain": "ice",
        })
        assert r.status_code == 200
        eff = r.json()["effects"]
        assert eff["heavily_obscured"]
        assert eff["ranged_attack_disadvantage"]
        # The actual stored environment is unchanged.
        env = client.get(f"/api/game/{game.id}/environment").json()["environment"]
        assert env["weather"] == "clear"

    def test_probe_invalid_value(self, client: TestClient, game):
        r = client.post(f"/api/game/{game.id}/environment/effects", json={"weather": "tornado"})
        assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Procedural roll.
# --------------------------------------------------------------------------- #

class TestRollEnvironment:
    def test_roll_deterministic_with_seed(self, client: TestClient, game):
        r1 = client.post(f"/api/game/{game.id}/environment/roll", json={
            "climate": "arctic", "season": "winter", "time_of_day": "night",
            "seed": 42,
        })
        r2 = client.post(f"/api/game/{game.id}/environment/roll", json={
            "climate": "arctic", "season": "winter", "time_of_day": "night",
            "seed": 42,
        })
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["environment"] == r2.json()["environment"]
        env = r1.json()["environment"]
        assert env["time_of_day"] == "night"
        assert env["light"] == "darkness"

    def test_roll_persists_weather(self, client: TestClient, game):
        r = client.post(f"/api/game/{game.id}/environment/roll", json={
            "climate": "arctic", "season": "winter", "time_of_day": "day",
            "seed": 7,
        })
        assert r.status_code == 200
        env = r.json()["environment"]
        # Stored value matches returned value.
        stored = client.get(f"/api/game/{game.id}/environment").json()["environment"]
        assert stored["weather"] == env["weather"]
        assert stored["temperature"] == env["temperature"]
        assert "message" in r.json()

    def test_roll_preserves_existing_terrain_and_notes(self, client: TestClient, game):
        # Set a terrain + note first.
        client.put(f"/api/game/{game.id}/environment", json={
            "terrain": "undergrowth", "notes": "Dense forest",
        })
        r = client.post(f"/api/game/{game.id}/environment/roll", json={
            "climate": "temperate", "season": "summer", "time_of_day": "day",
            "seed": 1,
        })
        assert r.status_code == 200
        env = r.json()["environment"]
        assert env["terrain"] == "undergrowth"
        assert env["notes"] == "Dense forest"

    def test_roll_invalid_climate(self, client: TestClient, game):
        r = client.post(f"/api/game/{game.id}/environment/roll", json={
            "climate": "tropical", "season": "summer",
        })
        assert r.status_code == 422

    def test_roll_invalid_season(self, client: TestClient, game):
        r = client.post(f"/api/game/{game.id}/environment/roll", json={
            "climate": "temperate", "season": "monsoon",
        })
        assert r.status_code == 422

    def test_roll_invalid_time(self, client: TestClient, game):
        r = client.post(f"/api/game/{game.id}/environment/roll", json={
            "climate": "temperate", "season": "summer", "time_of_day": "eclipse",
        })
        assert r.status_code == 422

    def test_roll_unknown_game_404(self, client: TestClient):
        r = client.post("/api/game/999999/environment/roll", json={
            "climate": "temperate", "season": "summer",
        })
        assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Combat modifiers.
# --------------------------------------------------------------------------- #

class TestCombatModifiersEndpoint:
    def test_ranged_in_storm(self, client: TestClient, game):
        client.put(f"/api/game/{game.id}/environment", json={"weather": "storm"})
        r = client.post(
            f"/api/game/{game.id}/environment/combat-modifiers?attack_is_ranged=true"
        )
        assert r.status_code == 200
        mods = r.json()["modifiers"]
        assert mods["attacker_ranged_disadvantage"] is True
        assert mods["target_unseen_by_attacker"] is True  # storm is heavily obscured

    def test_melee_in_clear(self, client: TestClient, game):
        r = client.post(
            f"/api/game/{game.id}/environment/combat-modifiers?attack_is_ranged=false"
        )
        assert r.status_code == 200
        mods = r.json()["modifiers"]
        assert mods["attacker_melee_disadvantage"] is False
        assert mods["attacker_ranged_disadvantage"] is False

    def test_unknown_game_404(self, client: TestClient):
        r = client.post("/api/game/999999/environment/combat-modifiers")
        assert r.status_code == 404
