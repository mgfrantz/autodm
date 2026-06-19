"""
Test the languages REST API.

Tests the language registry, character language endpoints, and validation.
"""
import pytest


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


def test_get_character_language_choices_human(client, character):
    """Get language choices for a human character."""
    # Update character to be human
    character.race = "Human"
    character.languages = '["common"]'
    from app.models.database import SessionLocal
    db = SessionLocal()
    db.add(character)
    db.commit()
    db.refresh(character)

    response = client.get(f"/api/characters/{character.id}/languages/choices")
    assert response.status_code == 200

    data = response.json()
    assert data["character_id"] == character.id
    assert data["race"] == "Human"
    assert "common" in data["known_languages"]
    assert data["remaining_choices"] == 1  # Human gets 1 extra
    assert len(data["available_choices"]) > 0


def test_get_character_language_choices_dwarf(client, character):
    """Get language choices for a dwarf character."""
    character.race = "Dwarf"
    character.languages = '["common", "dwarvish"]'
    from app.models.database import SessionLocal
    db = SessionLocal()
    db.add(character)
    db.commit()
    db.refresh(character)

    response = client.get(f"/api/characters/{character.id}/languages/choices")
    assert response.status_code == 200

    data = response.json()
    assert "common" in data["known_languages"]
    assert "dwarvish" in data["known_languages"]
    assert data["remaining_choices"] == 0  # Dwarf has no extras


def test_get_character_language_choices_with_class(client, character):
    """Class languages (Druidic, Thieves' Cant) appear in automatic languages."""
    from app.models.database import SessionLocal

    # Druid gets Druidic
    character.race = "Human"
    character.char_class = "Druid"
    character.classes_dict = {"druid": 1}
    character.languages = '["common"]'
    db = SessionLocal()
    db.add(character)
    db.commit()
    db.refresh(character)

    response = client.get(f"/api/characters/{character.id}/languages/choices")
    assert response.status_code == 200

    data = response.json()
    assert "druidic" in data["automatic_languages"]


def test_set_character_languages_valid(client, character):
    """Set valid languages for a character."""
    character.race = "Human"
    character.languages = '["common"]'
    from app.models.database import SessionLocal
    db = SessionLocal()
    db.add(character)
    db.commit()
    db.refresh(character)

    # Set Common + 1 extra
    response = client.post(
        f"/api/characters/{character.id}/languages",
        json={"languages": ["common", "elvish"]}
    )
    assert response.status_code == 200

    data = response.json()
    assert "common" in data["known_languages"]
    assert "elvish" in data["known_languages"]
    assert data["remaining_choices"] == 0


def test_set_character_languages_missing_automatic(client, character):
    """Setting languages without automatic ones returns 400."""
    character.race = "Dwarf"
    from app.models.database import SessionLocal
    db = SessionLocal()
    db.add(character)
    db.commit()
    db.refresh(character)

    response = client.post(
        f"/api/characters/{character.id}/languages",
        json={"languages": ["common"]}  # Missing dwarvish
    )
    assert response.status_code == 400
    assert "Missing automatic languages" in response.json()["detail"]


def test_set_character_languages_too_many(client, character):
    """Setting too many extra languages returns 400."""
    character.race = "Human"
    from app.models.database import SessionLocal
    db = SessionLocal()
    db.add(character)
    db.commit()
    db.refresh(character)

    # Human only gets 1 extra, but we try to set 2
    response = client.post(
        f"/api/characters/{character.id}/languages",
        json={"languages": ["common", "elvish", "dwarvish"]}
    )
    assert response.status_code == 400
    assert "Too many languages" in response.json()["detail"]


def test_set_character_languages_invalid_choice(client, character):
    """Setting invalid extra choices returns 400."""
    character.race = "Human"
    from app.models.database import SessionLocal
    db = SessionLocal()
    db.add(character)
    db.commit()
    db.refresh(character)

    # Try to pick a secret language (not in racial pool)
    response = client.post(
        f"/api/characters/{character.id}/languages",
        json={"languages": ["common", "druidic"]}
    )
    assert response.status_code == 400
    assert "Invalid extra language choices" in response.json()["detail"]


def test_validate_languages_valid(client, character):
    """Validate valid languages without saving."""
    character.race = "Dwarf"
    from app.models.database import SessionLocal
    db = SessionLocal()
    db.add(character)
    db.commit()
    db.refresh(character)

    response = client.post(
        f"/api/characters/{character.id}/languages/validate",
        json={"languages": ["common", "dwarvish"]}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["valid"] is True
    assert data["error"] is None
    assert "common" in data["known_languages"]
    assert "dwarvish" in data["known_languages"]


def test_validate_languages_invalid(client, character):
    """Validate invalid languages without saving."""
    character.race = "Dwarf"
    from app.models.database import SessionLocal
    db = SessionLocal()
    db.add(character)
    db.commit()
    db.refresh(character)

    response = client.post(
        f"/api/characters/{character.id}/languages/validate",
        json={"languages": ["common"]}  # Missing dwarvish
    )
    assert response.status_code == 200

    data = response.json()
    assert data["valid"] is False
    assert "Missing automatic languages" in data["error"]


def test_character_not_found(client):
    """Character ID that doesn't exist returns 404."""
    response = client.get("/api/characters/99999/languages/choices")
    assert response.status_code == 404


def test_language_summary(client, character):
    """The language choices endpoint includes a human-readable summary."""
    character.race = "Human"
    character.languages = '["common"]'
    from app.models.database import SessionLocal
    db = SessionLocal()
    db.add(character)
    db.commit()
    db.refresh(character)

    response = client.get(f"/api/characters/{character.id}/languages/choices")
    assert response.status_code == 200

    data = response.json()
    assert "summary" in data
    assert isinstance(data["summary"], str)
    assert len(data["summary"]) > 0


def test_normalize_language_names(client, character):
    """Language endpoint should handle various name formats."""
    character.race = "Elf"
    character.languages = '["common", "elvish"]'
    from app.models.database import SessionLocal
    db = SessionLocal()
    db.add(character)
    db.commit()
    db.refresh(character)

    # Try setting with uppercase and spaces
    response = client.post(
        f"/api/characters/{character.id}/languages",
        json={"languages": ["Common", "Elvish", "Dwarvish"]}  # 1 extra
    )
    assert response.status_code == 200

    data = response.json()
    # Should be normalized to lowercase IDs
    assert "common" in data["known_languages"]
    assert "elvish" in data["known_languages"]
    assert "dwarvish" in data["known_languages"]