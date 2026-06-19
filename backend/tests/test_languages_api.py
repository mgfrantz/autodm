"""
Test the languages REST API.

Tests the language registry, character language endpoints, and validation.

These tests create characters via the shared ``character`` fixture and persist
character-state changes through the same ``db_session`` that the test ``client``
uses (via its dependency override). Previously the tests opened a *production*
``SessionLocal()`` and called ``db.add(character)`` on an object already
attached to the test session, which raised
``sqlalchemy.exc.InvalidRequestError: Object is already attached to session``.
Going through the shared session keeps everything in one transaction so the
character's modified state is visible to the API routes.
"""
import pytest


# --------------------------------------------------------------------------- #
# Global registry endpoints (no character required)
# --------------------------------------------------------------------------- #

def test_get_languages_registry(client):
    """Get the complete language registry."""
    response = client.get("/api/languages/registry")
    assert response.status_code == 200

    data = response.json()
    assert "standard" in data
    assert "exotic" in data
    assert "secret" in data
    assert "all" in data

    # Check counts
    assert len(data["standard"]) == 11
    assert len(data["exotic"]) == 5
    assert len(data["secret"]) == 2
    assert len(data["all"]) == 18


def test_get_language_info_by_id(client):
    """Get detailed information about a specific language."""
    response = client.get("/api/languages/info/common")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == "common"
    assert data["name"] == "Common"
    assert data["type"] == "standard"


def test_get_language_info_invalid_id(client):
    """Invalid language ID returns 404."""
    response = client.get("/api/languages/info/klingon")
    assert response.status_code == 404


def test_character_not_found(client):
    """Character ID that doesn't exist returns 404."""
    response = client.get("/api/characters/99999/languages/choices")
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Character endpoints
#
# A small helper applies character-state changes through the shared ``db_session``
# fixture (the same session the ``client`` talks to) and commits, so subsequent
# HTTP requests see the updated character.
# --------------------------------------------------------------------------- #

def _apply(client, character, db_session, **fields):
    """Mutate a character's fields and commit through the shared test session."""
    for key, value in fields.items():
        setattr(character, key, value)
    db_session.commit()
    db_session.refresh(character)
    return character


def test_get_character_language_choices_human(client, character, db_session):
    """Get language choices for a human character."""
    _apply(client, character, db_session, race="Human", languages='["common"]')

    response = client.get(f"/api/characters/{character.id}/languages/choices")
    assert response.status_code == 200

    data = response.json()
    assert data["character_id"] == character.id
    assert data["race"] == "Human"
    assert "common" in data["known_languages"]
    assert data["remaining_choices"] == 1  # Human gets 1 extra
    assert len(data["available_choices"]) > 0


def test_get_character_language_choices_dwarf(client, character, db_session):
    """Get language choices for a dwarf character."""
    _apply(
        client, character, db_session,
        race="Dwarf", languages='["common", "dwarvish"]',
    )

    response = client.get(f"/api/characters/{character.id}/languages/choices")
    assert response.status_code == 200

    data = response.json()
    assert "common" in data["known_languages"]
    assert "dwarvish" in data["known_languages"]
    assert data["remaining_choices"] == 0  # Dwarf has no extras


def test_get_character_language_choices_with_class(client, character, db_session):
    """Class languages (Druidic, Thieves' Cant) appear in automatic languages."""
    # Druid gets Druidic
    _apply(
        client, character, db_session,
        race="Human", char_class="Druid",
        classes='{"druid": 1}', languages='["common"]',
    )

    response = client.get(f"/api/characters/{character.id}/languages/choices")
    assert response.status_code == 200

    data = response.json()
    assert "druidic" in data["automatic_languages"]


def test_set_character_languages_valid(client, character, db_session):
    """Set valid languages for a character."""
    _apply(client, character, db_session, race="Human", languages='["common"]')

    # Set Common + 1 extra
    response = client.post(
        f"/api/characters/{character.id}/languages",
        json={"languages": ["common", "elvish"]},
    )
    assert response.status_code == 200

    data = response.json()
    assert "common" in data["known_languages"]
    assert "elvish" in data["known_languages"]
    assert data["remaining_choices"] == 0


def test_set_character_languages_missing_automatic(client, character, db_session):
    """Setting languages without automatic ones returns 400."""
    _apply(client, character, db_session, race="Dwarf")

    response = client.post(
        f"/api/characters/{character.id}/languages",
        json={"languages": ["common"]},  # Missing dwarvish
    )
    assert response.status_code == 400
    assert "Missing automatic languages" in response.json()["detail"]


def test_set_character_languages_too_many(client, character, db_session):
    """Setting too many extra languages returns 400."""
    _apply(client, character, db_session, race="Human")

    # Human only gets 1 extra, but we try to set 2
    response = client.post(
        f"/api/characters/{character.id}/languages",
        json={"languages": ["common", "elvish", "dwarvish"]},
    )
    assert response.status_code == 400
    assert "Too many languages" in response.json()["detail"]


def test_set_character_languages_invalid_choice(client, character, db_session):
    """Setting invalid extra choices returns 400."""
    _apply(client, character, db_session, race="Human")

    # Try to pick a secret language (not in racial pool)
    response = client.post(
        f"/api/characters/{character.id}/languages",
        json={"languages": ["common", "druidic"]},
    )
    assert response.status_code == 400
    assert "Invalid extra language choices" in response.json()["detail"]


def test_validate_languages_valid(client, character, db_session):
    """Validate valid languages without saving."""
    _apply(client, character, db_session, race="Dwarf")

    response = client.post(
        f"/api/characters/{character.id}/languages/validate",
        json={"languages": ["common", "dwarvish"]},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["valid"] is True
    assert data["error"] is None
    assert "common" in data["known_languages"]
    assert "dwarvish" in data["known_languages"]


def test_validate_languages_invalid(client, character, db_session):
    """Validate invalid languages without saving."""
    _apply(client, character, db_session, race="Dwarf")

    response = client.post(
        f"/api/characters/{character.id}/languages/validate",
        json={"languages": ["common"]},  # Missing dwarvish
    )
    assert response.status_code == 200

    data = response.json()
    assert data["valid"] is False
    assert "Missing automatic languages" in data["error"]


def test_language_summary(client, character, db_session):
    """The language choices endpoint includes a human-readable summary."""
    _apply(client, character, db_session, race="Human", languages='["common"]')

    response = client.get(f"/api/characters/{character.id}/languages/choices")
    assert response.status_code == 200

    data = response.json()
    assert "summary" in data
    assert isinstance(data["summary"], str)
    assert len(data["summary"]) > 0


def test_normalize_language_names(client, character, db_session):
    """Language endpoint should handle various name formats."""
    _apply(
        client, character, db_session,
        race="Elf", languages='["common", "elvish"]',
    )

    # Try setting with uppercase and spaces
    response = client.post(
        f"/api/characters/{character.id}/languages",
        json={"languages": ["Common", "Elvish", "Dwarvish"]},  # 1 extra
    )
    assert response.status_code == 200

    data = response.json()
    # Should be normalized to lowercase IDs
    assert "common" in data["known_languages"]
    assert "elvish" in data["known_languages"]
    assert "dwarvish" in data["known_languages"]
