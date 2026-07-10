"""
Tests for the subclass API endpoints.
"""
import pytest
from sqlalchemy.orm import Session

from app.models.models import Character


@pytest.fixture
def fighter(db_session: Session):
    """A level-5 fighter eligible to choose a Martial Archetype."""
    char = Character(
        name="Roland",
        race="Human",
        char_class="fighter",
        level=5,
        classes='{"fighter": 5}',
        strength=16,
        dexterity=14,
        constitution=14,
        max_hp=45,
        current_hp=45,
        armor_class=16,
        subclass="{}",
    )
    db_session.add(char)
    db_session.commit()
    db_session.refresh(char)
    return char


@pytest.fixture
def low_level_fighter(db_session: Session):
    """A level-2 fighter — too low to choose a subclass."""
    char = Character(
        name="Apprentice",
        race="Human",
        char_class="fighter",
        level=2,
        classes='{"fighter": 2}',
        strength=14,
        max_hp=20,
        current_hp=20,
        subclass="{}",
    )
    db_session.add(char)
    db_session.commit()
    db_session.refresh(char)
    return char


@pytest.fixture
def cleric(db_session: Session):
    """A level-3 cleric (chooses Divine Domain at level 1)."""
    char = Character(
        name="Liora",
        race="Elf",
        char_class="cleric",
        level=3,
        classes='{"cleric": 3}',
        wisdom=16,
        max_hp=24,
        current_hp=24,
        subclass="{}",
    )
    db_session.add(char)
    db_session.commit()
    db_session.refresh(char)
    return char


# --------------------------------------------------------------------------- #
# Registry endpoints                                                          #
# --------------------------------------------------------------------------- #

def test_list_all_subclasses(client):
    resp = client.get("/api/characters/subclasses/list")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 24
    first = data[0]
    assert {"id", "name", "char_class", "category", "features", "choice_level"} <= set(first)


def test_list_filter_by_class(client):
    resp = client.get("/api/characters/subclasses/list", params={"class_name": "fighter"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2
    assert all(d["char_class"] == "fighter" for d in data)


def test_list_filter_class_case_insensitive(client):
    resp = client.get("/api/characters/subclasses/list", params={"class_name": "Wizard"})
    assert resp.status_code == 200
    assert all(d["char_class"] == "wizard" for d in resp.json())


def test_get_subclass_detail(client):
    resp = client.get("/api/characters/subclasses/list/champion")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "champion"
    assert data["name"] == "Champion"
    assert data["char_class"] == "fighter"
    assert data["choice_level"] == 3


def test_get_subclass_detail_unknown(client):
    resp = client.get("/api/characters/subclasses/list/does-not-exist")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Character subclass state                                                    #
# --------------------------------------------------------------------------- #

def test_get_character_subclass_empty(client, fighter):
    resp = client.get(f"/api/characters/subclasses/{fighter.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["character_id"] == fighter.id
    assert data["level"] == 5
    assert data["choices"] == []
    # Fighter is eligible → should be in pending.
    pending_classes = [p["class_name"] for p in data["pending"]]
    assert "fighter" in pending_classes


def test_get_character_subclass_not_found(client):
    resp = client.get("/api/characters/subclasses/9999")
    assert resp.status_code == 404


def test_pending_includes_options(client, fighter):
    resp = client.get(f"/api/characters/subclasses/{fighter.id}")
    pending = resp.json()["pending"]
    fighter_pending = [p for p in pending if p["class_name"] == "fighter"][0]
    assert "champion" in fighter_pending["options"]
    assert fighter_pending["category"] == "Martial Archetype"


def test_low_level_no_pending(client, low_level_fighter):
    resp = client.get(f"/api/characters/subclasses/{low_level_fighter.id}")
    assert resp.json()["pending"] == []


def test_timeline_includes_class_features(client, fighter):
    resp = client.get(f"/api/characters/subclasses/{fighter.id}")
    timeline = resp.json()["timeline"]
    sources = {entry["source"] for entry in timeline}
    assert "class" in sources
    levels = [entry["level"] for entry in timeline]
    assert levels == sorted(levels)


def test_dm_summary_eligible_not_chosen(client, fighter):
    resp = client.get(f"/api/characters/subclasses/{fighter.id}")
    summary = resp.json()["dm_summary"]
    assert "Martial Archetype" in summary or "should choose" in summary


# --------------------------------------------------------------------------- #
# Available subclasses                                                        #
# --------------------------------------------------------------------------- #

def test_available_subclasses(client, fighter):
    resp = client.get(f"/api/characters/subclasses/{fighter.id}/available")
    assert resp.status_code == 200
    data = resp.json()
    ids = [s["id"] for s in data["available"]]
    assert "champion" in ids
    assert all(s["char_class"] == "fighter" for s in data["available"])


def test_available_none_when_low_level(client, low_level_fighter):
    resp = client.get(f"/api/characters/subclasses/{low_level_fighter.id}/available")
    assert resp.status_code == 200
    assert resp.json()["available"] == []


def test_available_none_when_already_chosen(client, fighter):
    # Choose first, then check available is empty.
    client.post(
        f"/api/characters/subclasses/{fighter.id}/choose",
        json={"subclass_id": "champion"},
    )
    resp = client.get(f"/api/characters/subclasses/{fighter.id}/available")
    assert resp.json()["available"] == []


# --------------------------------------------------------------------------- #
# Choose subclass                                                             #
# --------------------------------------------------------------------------- #

def test_choose_subclass_success(client, fighter):
    resp = client.post(
        f"/api/characters/subclasses/{fighter.id}/choose",
        json={"subclass_id": "champion"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"]
    assert data["subclass_name"] == "Champion"
    assert data["class_name"] == "fighter"


def test_choose_persists_to_character(client, fighter, db_session: Session):
    client.post(
        f"/api/characters/subclasses/{fighter.id}/choose",
        json={"subclass_id": "battle-master"},
    )
    db_session.expire_all()
    char = db_session.query(Character).filter(Character.id == fighter.id).first()
    assert char is not None
    assert char.subclass_dict == {"fighter": "battle-master"}


def test_choose_then_choices_reflect(client, fighter):
    client.post(
        f"/api/characters/subclasses/{fighter.id}/choose",
        json={"subclass_id": "champion"},
    )
    resp = client.get(f"/api/characters/subclasses/{fighter.id}")
    choices = resp.json()["choices"]
    assert len(choices) == 1
    assert choices[0]["subclass_id"] == "champion"
    assert choices[0]["name"] == "Champion"


def test_choose_then_timeline_has_subclass_features(client, fighter):
    client.post(
        f"/api/characters/subclasses/{fighter.id}/choose",
        json={"subclass_id": "champion"},
    )
    resp = client.get(f"/api/characters/subclasses/{fighter.id}")
    sources = {e["source"] for e in resp.json()["timeline"]}
    assert "Champion" in sources


def test_choose_unknown_subclass(client, fighter):
    resp = client.post(
        f"/api/characters/subclasses/{fighter.id}/choose",
        json={"subclass_id": "nope"},
    )
    assert resp.status_code == 400


def test_choose_wrong_class(client, fighter):
    # Champion is a fighter subclass; targeting a wizard class the fighter
    # doesn't have → 400.
    resp = client.post(
        f"/api/characters/subclasses/{fighter.id}/choose",
        json={"subclass_id": "champion", "class_name": "wizard"},
    )
    assert resp.status_code == 400


def test_choose_below_level(client, low_level_fighter):
    resp = client.post(
        f"/api/characters/subclasses/{low_level_fighter.id}/choose",
        json={"subclass_id": "champion"},
    )
    assert resp.status_code == 400
    assert "level 3" in resp.json()["detail"].lower()


def test_choose_twice_rejected(client, fighter):
    client.post(
        f"/api/characters/subclasses/{fighter.id}/choose",
        json={"subclass_id": "champion"},
    )
    resp = client.post(
        f"/api/characters/subclasses/{fighter.id}/choose",
        json={"subclass_id": "battle-master"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("Already")


def test_choose_early_class_at_level_1(client, cleric):
    # Cleric chooses at level 1 — a level-3 cleric is eligible.
    resp = client.post(
        f"/api/characters/subclasses/{cleric.id}/choose",
        json={"subclass_id": "life-domain"},
    )
    assert resp.status_code == 200
    assert resp.json()["subclass_name"] == "Life Domain"


def test_choose_character_not_found(client):
    resp = client.post(
        "/api/characters/subclasses/9999/choose",
        json={"subclass_id": "champion"},
    )
    assert resp.status_code == 404


def test_choose_explicit_class_name(client, fighter):
    resp = client.post(
        f"/api/characters/subclasses/{fighter.id}/choose",
        json={"subclass_id": "champion", "class_name": "fighter"},
    )
    assert resp.status_code == 200
