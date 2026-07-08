"""
Tests for the starvation/dehydration REST API.

Covers:
- GET /survival: default state, deficit summary, exhaustion read-through,
  and 'hot' auto-detection from the stored environment.
- POST /survival/advance: full intake (no effect), starvation beyond grace
  (inflicts + persists exhaustion), dehydration save failure/success, hot
  weather doubling the water need, exhaustion clamping + death at 6 (HP → 0),
  and story-log narration.
- POST /survival/reset: counters reset to zero.
- CON save bonus includes proficiency when the class grants CON save
  proficiency (Fighter is CON-proficient).
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.models.models import Character, World, GameSave


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _make_game(db_session, *, constitution=14, exhaustion=0, environment=None,
               survival=None):
    """A Fighter (CON-save proficient) with optional survival/exhaustion/env state."""
    char = Character(
        name="Rhea", race="Human", char_class="Fighter", level=5,
        classes=json.dumps({"fighter": 5}),
        strength=16, dexterity=12, constitution=constitution, intelligence=10,
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

    state = {"location": "Camp", "in_combat": False, "conditions": []}
    if exhaustion:
        state["exhaustion"] = exhaustion
    if environment is not None:
        state["environment"] = environment
    if survival is not None:
        state["survival"] = survival
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
# GET /survival
# --------------------------------------------------------------------------- #

class TestGetSurvival:
    def test_default_state_and_summary(self, client, game):
        r = client.get(f"/api/game/{game.id}/survival")
        assert r.status_code == 200
        body = r.json()
        assert body["character_id"] == game.character_id
        assert body["exhaustion"] == 0
        assert body["state"] == {"days_without_food": 0, "days_without_water": 0}
        # Fighter CON 14 → +2 mod → grace 5.
        assert body["deficit"]["food_grace_days"] == 5
        assert body["deficit"]["daily_water_gal"] == 1.0
        assert body["daily_needs"]["water"] == 1.0

    def test_reads_existing_exhaustion(self, client, db_session):
        game = _make_game(db_session, exhaustion=2)
        body = client.get(f"/api/game/{game.id}/survival").json()
        assert body["exhaustion"] == 2

    def test_hot_autodetect_from_environment(self, client, db_session):
        game = _make_game(db_session, environment={"temperature": "extreme_heat"})
        body = client.get(f"/api/game/{game.id}/survival").json()
        assert body["deficit"]["hot"] is True
        assert body["deficit"]["daily_water_gal"] == 2.0
        assert body["daily_needs"]["water"] == 2.0


# --------------------------------------------------------------------------- #
# POST /survival/advance
# --------------------------------------------------------------------------- #

class TestAdvance:
    def test_full_intake_no_exhaustion_and_persists(self, client, game):
        r = client.post(
            f"/api/game/{game.id}/survival/advance",
            json={"food_lbs": 1, "water_gal": 1},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["exhaustion_added"] == 0
        assert body["exhaustion_after"] == 0
        assert body["changed"] is False
        # State persisted.
        state = client.get(f"/api/game/{game.id}/survival").json()["state"]
        assert state == {"days_without_food": 0, "days_without_water": 0}

    def test_starvation_inflicts_and_persists_exhaustion(self, client, db_session):
        # CON 14 → +2 → grace 5. Seed 5 prior days without food; day 6 inflicts.
        game = _make_game(db_session, survival={"days_without_food": 5, "days_without_water": 0})
        r = client.post(
            f"/api/game/{game.id}/survival/advance",
            json={"food_lbs": 0, "water_gal": 1},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["exhaustion_from_food"] == 1
        assert body["exhaustion_after"] == 1
        assert body["changed"] is True
        # The driver counter advanced to 6.
        assert body["state"]["days_without_food"] == 6
        # Exhaustion persisted to game_state.
        persisted = client.get(f"/api/game/{game.id}/survival").json()["exhaustion"]
        assert persisted == 1

    def test_dehydration_auto_when_less_than_half(self, client, game):
        r = client.post(
            f"/api/game/{game.id}/survival/advance",
            json={"food_lbs": 1, "water_gal": 0},
        )
        body = r.json()
        assert body["exhaustion_from_water"] == 1
        assert body["exhaustion_added"] == 1

    def test_dehydration_save_failure(self, client, game):
        # Half water, force a low save roll → fail → exhaustion.
        r = client.post(
            f"/api/game/{game.id}/survival/advance",
            json={"food_lbs": 1, "water_gal": 0.5, "save_roll": 1},
        )
        body = r.json()
        assert body["thirst_save_success"] is False
        assert body["exhaustion_from_water"] == 1

    def test_dehydration_save_success_with_con_proficiency(self, client, game):
        # Fighter is CON-save proficient (CON 14 → +2, prof bonus +3 at lvl 5 → +5).
        # Half water, roll 10 → 10 + 5 = 15 >= 15 → success, no exhaustion.
        r = client.post(
            f"/api/game/{game.id}/survival/advance",
            json={"food_lbs": 1, "water_gal": 0.5, "save_roll": 10},
        )
        body = r.json()
        assert body["thirst_save_bonus"] == 5  # +2 CON + +3 prof
        assert body["thirst_save_success"] is True
        assert body["exhaustion_from_water"] == 0

    def test_hot_doubles_water_need(self, client, game):
        # 1 gallon in hot weather is half the 2-gallon need → save (forced success).
        r = client.post(
            f"/api/game/{game.id}/survival/advance",
            json={"food_lbs": 1, "water_gal": 1, "hot": True, "save_roll": 20},
        )
        body = r.json()
        assert body["hot"] is True
        assert body["water_needed"] == 2.0
        assert body["exhaustion_added"] == 0

    def test_death_at_exhaustion_six(self, client, db_session):
        game = _make_game(db_session, exhaustion=5)
        r = client.post(
            f"/api/game/{game.id}/survival/advance",
            json={"food_lbs": 1, "water_gal": 0},  # dehydration auto → +1 = 6
        )
        body = r.json()
        assert body["exhaustion_after"] == 6
        assert body["died"] is True
        assert body["dead"] is True
        assert body["character"]["current_hp"] == 0

    def test_story_log_narration(self, client, game):
        r = client.post(
            f"/api/game/{game.id}/survival/advance",
            json={"food_lbs": 1, "water_gal": 0},
        )
        body = r.json()
        # The day's narration lines are surfaced via the result messages,
        # and the summary line flags the deprivation.
        joined = " ".join(body["messages"]).lower()
        assert "dehydration" in joined or "water" in joined


# --------------------------------------------------------------------------- #
# POST /survival/reset
# --------------------------------------------------------------------------- #

class TestReset:
    def test_reset_clears_counters(self, client, db_session):
        game = _make_game(
            db_session,
            survival={"days_without_food": 4, "days_without_water": 3},
            exhaustion=1,
        )
        r = client.post(f"/api/game/{game.id}/survival/reset")
        assert r.status_code == 200
        body = r.json()
        assert body["state"] == {"days_without_food": 0, "days_without_water": 0}
        # Exhaustion is NOT cleared by restocking (needs resting).
        assert body["exhaustion"] == 1


# --------------------------------------------------------------------------- #
# 404 / error handling
# --------------------------------------------------------------------------- #

class TestErrors:
    def test_unknown_game_404(self, client):
        assert client.get("/api/game/9999/survival").status_code == 404
        assert client.post(
            "/api/game/9999/survival/advance",
            json={"food_lbs": 1, "water_gal": 1},
        ).status_code == 404
