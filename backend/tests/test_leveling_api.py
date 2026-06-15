"""
Tests for the leveling API endpoints.

Covers: progress reporting, XP awarding with auto level-up, ability score
improvements (including CON-driven max HP recompute), and class features.
"""
import pytest
from fastapi.testclient import TestClient

from app.models.models import Character


def make_character(
    db_session,
    name="Test Hero",
    char_class="Fighter",
    level=1,
    xp=0,
    constitution=14,
    asi_used=0,
    max_hp=None,
) -> Character:
    """Insert a character and return it."""
    char = Character(
        name=name,
        race="Human",
        char_class=char_class,
        level=level,
        background="Soldier",
        strength=16,
        dexterity=12,
        constitution=constitution,
        intelligence=10,
        wisdom=10,
        charisma=10,
        max_hp=max_hp if max_hp is not None else 12,
        current_hp=max_hp if max_hp is not None else 12,
        armor_class=16,
        speed=30,
        xp=xp,
        asi_used=asi_used,
        backstory="A brave hero.",
    )
    db_session.add(char)
    db_session.commit()
    db_session.refresh(char)
    return char


# ---------------------------------------------------------------------------
# GET /leveling (progress)
# ---------------------------------------------------------------------------

class TestGetLeveling:
    def test_progress_for_fresh_character(self, client: TestClient, db_session):
        char = make_character(db_session, char_class="Wizard", xp=0)
        r = client.get(f"/api/characters/{char.id}/leveling")
        assert r.status_code == 200
        data = r.json()
        assert data["level"] == 1
        assert data["xp"] == 0
        assert data["proficiency_bonus"] == 2
        assert data["asi_available"] == 0
        assert data["next_level_xp"] == 300
        assert data["next_asi_level"] == 4

    def test_progress_mid_level(self, client: TestClient, db_session):
        char = make_character(db_session, xp=600)
        r = client.get(f"/api/characters/{char.id}/leveling")
        assert r.status_code == 200
        data = r.json()
        # 600 XP -> level 2
        assert data["level"] == 1  # level column not synced with xp here
        assert data["xp"] == 600

    def test_404_for_missing_character(self, client: TestClient):
        r = client.get("/api/characters/9999/leveling")
        assert r.status_code == 404

    def test_fighter_next_asi_at_6(self, client: TestClient, db_session):
        char = make_character(db_session, char_class="Fighter", level=4, xp=2700, asi_used=0)
        r = client.get(f"/api/characters/{char.id}/leveling")
        data = r.json()
        # Fighter next ASI after level 4 is 6.
        assert data["next_asi_level"] == 6
        assert data["asi_available"] == 1


# ---------------------------------------------------------------------------
# POST /leveling/award-xp
# ---------------------------------------------------------------------------

class TestAwardXP:
    def test_award_xp_no_level_up(self, client: TestClient, db_session):
        char = make_character(db_session, char_class="Wizard", xp=0)
        r = client.post(f"/api/characters/{char.id}/leveling/award-xp", json={"xp": 100})
        assert r.status_code == 200
        data = r.json()
        assert data["leveled_up"] is False
        assert data["xp_total"] == 100
        assert data["hp_gained"] == 0

    def test_award_xp_single_level_up(self, client: TestClient, db_session):
        char = make_character(
            db_session, char_class="Wizard", constitution=10, xp=0, max_hp=6,
        )
        r = client.post(f"/api/characters/{char.id}/leveling/award-xp", json={"xp": 300})
        assert r.status_code == 200
        data = r.json()
        assert data["leveled_up"] is True
        assert data["from_level"] == 1
        assert data["to_level"] == 2
        # Wizard d6, CON 10 (+0): 4 HP per level.
        assert data["hp_gained"] == 4
        assert data["max_hp"] == 6 + 4  # started at 6, +4

    def test_award_xp_persists_level_and_hp(self, client: TestClient, db_session):
        char = make_character(db_session, char_class="Fighter", constitution=14, xp=0)
        client.post(f"/api/characters/{char.id}/leveling/award-xp", json={"xp": 300})
        db_session.refresh(char)
        assert char.level == 2
        assert char.xp == 300
        # Fighter d10, CON 14 (+2): 8 HP gained.
        assert char.max_hp == 12 + 8

    def test_award_xp_multi_level_up(self, client: TestClient, db_session):
        char = make_character(db_session, char_class="Wizard", constitution=10, xp=0)
        r = client.post(f"/api/characters/{char.id}/leveling/award-xp", json={"xp": 900})
        data = r.json()
        assert data["to_level"] == 3
        assert data["levels_gained"] == 2
        # 2 levels * 4 HP = 8
        assert data["hp_gained"] == 8

    def test_award_xp_unlocks_asi(self, client: TestClient, db_session):
        char = make_character(db_session, char_class="Wizard", constitution=10, level=3, xp=2000, asi_used=0)
        r = client.post(f"/api/characters/{char.id}/leveling/award-xp", json={"xp": 700})
        data = r.json()
        assert data["to_level"] == 4
        assert data["asi_unlocked"] is True
        assert data["asi_available"] == 1

    def test_award_xp_negative_treated_as_floor(self, client: TestClient, db_session):
        char = make_character(db_session, char_class="Wizard", xp=50)
        r = client.post(f"/api/characters/{char.id}/leveling/award-xp", json={"xp": -100})
        assert r.status_code == 200
        data = r.json()
        assert data["xp_total"] == 0  # floored at 0, not negative

    def test_award_xp_new_features(self, client: TestClient, db_session):
        char = make_character(db_session, char_class="Fighter", constitution=14, xp=0)
        r = client.post(f"/api/characters/{char.id}/leveling/award-xp", json={"xp": 300})
        data = r.json()
        feat_levels = [f["level"] for f in data["new_features"]]
        assert 2 in feat_levels  # Action Surge

    def test_404_award_missing_character(self, client: TestClient):
        r = client.post("/api/characters/9999/leveling/award-xp", json={"xp": 100})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /leveling/apply-asi
# ---------------------------------------------------------------------------

class TestApplyASI:
    def test_apply_single_plus_two(self, client: TestClient, db_session):
        char = make_character(db_session, char_class="Wizard", level=4, xp=2700, asi_used=0, constitution=10)
        r = client.post(
            f"/api/characters/{char.id}/leveling/apply-asi",
            json={"choices": [{"ability": "intelligence", "amount": 2}]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["abilities"]["intelligence"] == 12  # 10 + 2
        assert data["asi_used"] == 1
        assert data["asi_available"] == 0

    def test_apply_two_plus_ones(self, client: TestClient, db_session):
        char = make_character(db_session, char_class="Wizard", level=4, xp=2700, asi_used=0, constitution=10)
        r = client.post(
            f"/api/characters/{char.id}/leveling/apply-asi",
            json={"choices": [
                {"ability": "intelligence", "amount": 1},
                {"ability": "dexterity", "amount": 1},
            ]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["abilities"]["intelligence"] == 11
        assert data["abilities"]["dexterity"] == 13  # 12 + 1

    def test_apply_asi_none_available_rejected(self, client: TestClient, db_session):
        # Level 1 wizard has no ASI.
        char = make_character(db_session, char_class="Wizard", level=1, xp=0, asi_used=0)
        r = client.post(
            f"/api/characters/{char.id}/leveling/apply-asi",
            json={"choices": [{"ability": "intelligence", "amount": 2}]},
        )
        assert r.status_code == 400

    def test_apply_asi_wrong_total_rejected(self, client: TestClient, db_session):
        char = make_character(db_session, char_class="Wizard", level=4, xp=2700, asi_used=0)
        r = client.post(
            f"/api/characters/{char.id}/leveling/apply-asi",
            json={"choices": [{"ability": "intelligence", "amount": 3}]},
        )
        assert r.status_code == 400

    def test_apply_asi_con_increases_max_hp(self, client: TestClient, db_session):
        # Wizard level 4, CON 12 (+1). After +2 CON -> CON 14 (+2), max HP rises
        # by (2 - 1) * 4 levels = 4.
        char = make_character(
            db_session, char_class="Wizard", level=4, xp=2700,
            asi_used=0, constitution=12, max_hp=17,
        )
        r = client.post(
            f"/api/characters/{char.id}/leveling/apply-asi",
            json={"choices": [{"ability": "constitution", "amount": 2}]},
        )
        assert r.status_code == 200
        data = r.json()
        # max_hp recomputed: base d6 + con + (avg per level * (level-1))
        # CON now +2: base 6+2=8, per level 4+2=6, *3 = 18, +8 = 26.
        assert data["max_hp"] == 26

    def test_apply_asi_persists(self, client: TestClient, db_session):
        char = make_character(db_session, char_class="Wizard", level=4, xp=2700, asi_used=0, constitution=10)
        client.post(
            f"/api/characters/{char.id}/leveling/apply-asi",
            json={"choices": [{"ability": "wisdom", "amount": 2}]},
        )
        db_session.refresh(char)
        assert char.wisdom == 12
        assert char.asi_used == 1

    def test_404_apply_asi_missing_character(self, client: TestClient):
        r = client.post(
            "/api/characters/9999/leveling/apply-asi",
            json={"choices": [{"ability": "strength", "amount": 2}]},
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /leveling/features
# ---------------------------------------------------------------------------

class TestGetFeatures:
    def test_features_for_level_1_fighter(self, client: TestClient, db_session):
        char = make_character(db_session, char_class="Fighter", level=1, xp=0)
        r = client.get(f"/api/characters/{char.id}/leveling/features")
        assert r.status_code == 200
        data = r.json()
        assert data["char_class"] == "Fighter"
        levels = [f["level"] for f in data["features"]]
        assert 1 in levels  # Fighting Style, Second Wind

    def test_features_next_level_preview(self, client: TestClient, db_session):
        char = make_character(db_session, char_class="Fighter", level=1, xp=0)
        r = client.get(f"/api/characters/{char.id}/leveling/features")
        data = r.json()
        assert data["next_level_feature"] is not None
        assert data["next_level_feature"]["level"] == 2
        assert "Action Surge" in data["next_level_feature"]["feature"]

    def test_features_404(self, client: TestClient):
        r = client.get("/api/characters/9999/leveling/features")
        assert r.status_code == 404
