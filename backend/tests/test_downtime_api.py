"""
Tests for the downtime activities REST API.

Covers:
- GET /downtime/activities + /activities/{id} (list/detail/404).
- POST /downtime/resolve for each activity: gold spends/earnings (with 402 when
  bankrupt), exhaustion easing (relaxation/religion), training proficiency
  grants (language + tool), condition clearing, and story-log narration.
- Character-derived default modifiers and DM-adjudication dice overrides.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.models.models import Character, World, GameSave


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _make_game(db_session, *, gold=500, exhaustion=0, conditions=None,
               tools=None, languages=None):
    char = Character(
        name="Wren", race="Human", char_class="Rogue", level=5,
        classes=json.dumps({"rogue": 5}),
        strength=12, dexterity=16, constitution=14, intelligence=12,
        wisdom=10, charisma=14,
        max_hp=40, current_hp=40, armor_class=15, speed=30,
        gold=gold, hit_dice_used=0,
        tool_proficiencies=json.dumps(
            tools if tools is not None else ["thieves_tools"]
        ),
        languages=json.dumps(languages or ["common"]),
    )
    db_session.add(char)
    db_session.flush()

    w = World(
        name="The Shire", description="A cozy locale.",
        world_data='{"starting_settlement": {"name": "Town"}}', tone="cozy",
    )
    db_session.add(w)
    db_session.flush()

    state = {"location": "Town", "in_combat": False, "conditions": conditions or []}
    if exhaustion:
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


# --------------------------------------------------------------------------- #
# Activity listing / detail
# --------------------------------------------------------------------------- #

class TestActivityListing:
    def test_list_activities(self, client, game):
        r = client.get(f"/api/game/{game.id}/downtime/activities")
        assert r.status_code == 200
        data = r.json()
        assert len(data["activities"]) == 11
        ids = {a["id"] for a in data["activities"]}
        assert "carousing" in ids and "training" in ids

    def test_get_activity_detail(self, client, game):
        r = client.get(f"/api/game/{game.id}/downtime/activities/gambling")
        assert r.status_code == 200
        assert r.json()["name"] == "Gambling"

    def test_get_activity_unknown_404(self, client, game):
        r = client.get(f"/api/game/{game.id}/downtime/activities/nope")
        assert r.status_code == 404

    def test_unknown_game_404(self, client):
        r = client.get("/api/game/9999/downtime/activities")
        assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Carousing
# --------------------------------------------------------------------------- #

class TestCarousingAPI:
    def test_carouse_spends_gold(self, client, game):
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "carousing", "tier": "middle", "d6": 6,  # no complication
        })
        assert r.status_code == 200
        data = r.json()
        assert data["gold_delta"] == -50
        assert data["character_gold"] == 450

    def test_carouse_complication_narrated(self, client, game):
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "carousing", "tier": "lower",
            "d6": 1, "complication_d20": 1, "save_roll": 1,
        })
        assert r.status_code == 200
        assert r.json()["complication"] is not None

    def test_carouse_bankrupt_402(self, client, db_session):
        g = _make_game(db_session, gold=20)
        r = client.post(f"/api/game/{g.id}/downtime/resolve", json={
            "activity": "carousing", "tier": "upper", "d6": 6,
        })
        assert r.status_code == 402


# --------------------------------------------------------------------------- #
# Crime
# --------------------------------------------------------------------------- #

class TestCrimeAPI:
    def test_crime_payout(self, client, game):
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "crime",
            "casing_modifier": 10, "casing_dc": 10, "casing_roll": 20,
            "heist_modifier": 10, "heist_dc": 10, "heist_rolls": [20, 20, 20],
            "max_payout": 300, "d6": 6,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["details"]["payout"] == 300
        assert data["gold_delta"] == 200  # 300 - 100
        assert data["character_gold"] == 700

    def test_crime_casing_fail_costs_only(self, client, game):
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "crime",
            "casing_modifier": -5, "casing_dc": 20, "casing_roll": 1,
            "d6": 6,
        })
        assert r.status_code == 200
        assert r.json()["gold_delta"] == -100


# --------------------------------------------------------------------------- #
# Gambling
# --------------------------------------------------------------------------- #

class TestGamblingAPI:
    def test_gamble_win(self, client, game):
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "gambling", "wager": 100,
            "modifier": 10, "dc": 20, "games": 3, "rolls": [20, 20, 20],
            "d6": 6,
        })
        assert r.status_code == 200
        assert r.json()["gold_delta"] == 100
        assert r.json()["character_gold"] == 600

    def test_gamble_lose_bankrupt_402(self, client, db_session):
        # wager more than the character holds.
        g = _make_game(db_session, gold=50)
        r = client.post(f"/api/game/{g.id}/downtime/resolve", json={
            "activity": "gambling", "wager": 100,
            "modifier": -5, "dc": 20, "games": 3, "rolls": [1, 1, 1],
            "d6": 6,
        })
        assert r.status_code == 402


# --------------------------------------------------------------------------- #
# Pit fighting
# --------------------------------------------------------------------------- #

class TestPitFightingAPI:
    def test_pit_fight_purse(self, client, game):
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "pit_fighting",
            "modifier": 10, "dc": 10, "rolls": [15, 15, 15], "d6": 6,
        })
        assert r.status_code == 200
        assert r.json()["gold_delta"] == 500


# --------------------------------------------------------------------------- #
# Research
# --------------------------------------------------------------------------- #

class TestResearchAPI:
    def test_research_spends_and_reveals(self, client, game):
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "research",
            "modifier": 10, "dc": 10, "workweeks": 2, "roll": 20,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["details"]["facts"] == 2
        assert data["gold_delta"] == -50


# --------------------------------------------------------------------------- #
# Relaxation
# --------------------------------------------------------------------------- #

class TestRelaxationAPI:
    def test_relaxation_eases_exhaustion(self, client, db_session):
        g = _make_game(db_session, gold=500, exhaustion=3,
                       conditions=["frightened", "poisoned", "stunned"])
        r = client.post(f"/api/game/{g.id}/downtime/resolve", json={
            "activity": "relaxation", "days": 5,
            "conditions": ["frightened", "poisoned", "stunned"],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["exhaustion"] == 2          # eased one level
        assert set(data["details"]["cleared_conditions"]) == {"frightened", "poisoned"}
        # Persisted?
        g2 = db_session.query(GameSave).get(g.id)
        gs = json.loads(g2.game_state)
        assert gs["exhaustion"] == 2
        assert "stunned" in gs["conditions"]


# --------------------------------------------------------------------------- #
# Crafting
# --------------------------------------------------------------------------- #

class TestCraftingAPI:
    def test_craft_requires_item_value(self, client, game):
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "crafting", "days": 5,
        })
        assert r.status_code == 400

    def test_craft_no_proficiency(self, client, game):
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "crafting", "item_value": 50, "days": 5,
            "has_proficiency": False,
        })
        assert r.status_code == 200
        assert r.json()["details"]["reason"] == "no_proficiency"

    def test_craft_progress_then_complete(self, client, game):
        # First period: materials + partial progress.
        r1 = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "crafting", "item_value": 50, "days": 5,
            "progress_before": 0,
        })
        assert r1.status_code == 200
        assert r1.json()["details"]["progress_now"] == 25
        assert r1.json()["gold_delta"] == -25  # materials

        # Second period: finish.
        r2 = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "crafting", "item_value": 50, "days": 5,
            "progress_before": 25,
        })
        assert r2.status_code == 200
        assert r2.json()["details"]["complete"] is True
        assert r2.json()["gold_delta"] == 50  # value produced


# --------------------------------------------------------------------------- #
# Profession / Work
# --------------------------------------------------------------------------- #

class TestProfessionWorkAPI:
    def test_profession_with_tool(self, client, game):
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "profession", "tool_proficiency": True,
        })
        # d25 default = 13 (random) but gold_delta > 0 guaranteed.
        assert r.status_code == 200
        assert r.json()["gold_delta"] > 0

    def test_profession_without_tool_falls_back(self, client, db_session):
        g = _make_game(db_session, gold=10, tools=[])
        r = client.post(f"/api/game/{g.id}/downtime/resolve", json={
            "activity": "profession",
        })
        assert r.status_code == 200
        assert r.json()["gold_delta"] == 5  # modest fallback

    def test_work_earns_modest(self, client, game):
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "work", "workweeks": 2,
        })
        assert r.status_code == 200
        assert r.json()["gold_delta"] == 10


# --------------------------------------------------------------------------- #
# Training
# --------------------------------------------------------------------------- #

class TestTrainingAPI:
    def test_training_requires_target(self, client, game):
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "training", "days": 50,
        })
        assert r.status_code == 400

    def test_training_partial(self, client, game):
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "training", "target": "elvish", "target_kind": "language",
            "days": 50,
        })
        assert r.status_code == 200
        assert r.json()["proficiency_granted"] is None
        assert r.json()["details"]["complete"] is False

    def test_training_completes_language(self, client, game, db_session):
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "training", "target": "elvish", "target_kind": "language",
            "days": 250,
        })
        assert r.status_code == 200
        assert r.json()["proficiency_granted"] == "elvish"
        # Persisted to character.languages.
        char = db_session_refresh_char(game, db_session)
        assert "elvish" in json.loads(char.languages or "[]")

    def test_training_completes_tool(self, client, game, db_session):
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "training", "target": "brewers_supplies",
            "target_kind": "tool", "days": 250,
        })
        assert r.status_code == 200
        assert r.json()["proficiency_granted"] == "brewers_supplies"
        char = db_session_refresh_char(game, db_session)
        assert "brewers_supplies" in json.loads(char.tool_proficiencies or "[]")


def db_session_refresh_char(game, db_session):
    """Re-fetch the character row fresh from the session."""
    from sqlalchemy.orm import object_session
    db_session.expire_all()
    return db_session.query(Character).get(game.character_id)


# --------------------------------------------------------------------------- #
# Religion + narration + defaults
# --------------------------------------------------------------------------- #

class TestReligionAndMisc:
    def test_religion_eases_exhaustion(self, client, db_session):
        g = _make_game(db_session, gold=500, exhaustion=2)
        r = client.post(f"/api/game/{g.id}/downtime/resolve", json={
            "activity": "religion", "modifier": 10, "dc": 10, "roll": 20,
        })
        assert r.status_code == 200
        assert r.json()["exhaustion"] == 1

    def test_unknown_activity_400(self, client, game):
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "skydiving",
        })
        assert r.status_code == 400

    def test_default_modifier_used_when_none(self, client, game):
        # No modifier/dice given: still resolves (default Dex+prof for crime).
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "crime", "casing_dc": 5, "d6": 6,
        })
        assert r.status_code == 200

    def test_narration_logged_to_story(self, client, game, db_session):
        r = client.post(f"/api/game/{game.id}/downtime/resolve", json={
            "activity": "work", "workweeks": 1,
        })
        assert r.status_code == 200
        story = json.loads(
            db_session.query(GameSave).get(game.id).story_log
        )
        assert story and "Laboured" in story[-1]["content"]
