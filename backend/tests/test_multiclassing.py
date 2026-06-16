"""
Tests for multiclassing engine and API.
"""
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models.database import get_db
from app.models.models import Base
from app.engine.multiclassing import (
    check_multiclass_requirements,
    parse_classes,
    serialize_classes,
    calculate_total_level,
    calculate_proficiency_bonus,
    calculate_multiclass_hp,
    calculate_multiclass_asi_status,
    build_multiclass_summary,
    MulticlassCheck,
    HPGainBreakdown,
    ASIStatus,
    MulticlassSummary,
)

# Test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_multiclass.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture
def db_session():
    """Create a fresh database session for each test."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Multiclassing engine tests
# ---------------------------------------------------------------------------

def test_check_multiclass_requirements_success():
    """Test successful multiclass prerequisite check."""
    abilities = {
        "strength": 15,
        "dexterity": 14,
        "constitution": 13,
        "intelligence": 10,
        "wisdom": 12,
        "charisma": 8,
    }

    # Barbarian requires Str 13
    result = check_multiclass_requirements("barbarian", abilities)
    assert result.can_multiclass is True
    assert "barbarian" in result.message.lower()
    assert result.missing_requirements == {}


def test_check_multiclass_requirements_failure():
    """Test failed multiclass prerequisite check."""
    abilities = {
        "strength": 10,
        "dexterity": 12,
        "constitution": 10,
        "intelligence": 10,
        "wisdom": 10,
        "charisma": 10,
    }

    # Fighter requires Str 13 AND Dex 13
    result = check_multiclass_requirements("fighter", abilities)
    assert result.can_multiclass is False
    assert result.missing_requirements == {"strength": 13}
    # Note: Only checks first missing requirement


def test_check_multiclass_requirements_partial():
    """Test partial failure - only one of two stats met."""
    abilities = {
        "strength": 14,
        "dexterity": 12,
        "constitution": 10,
        "intelligence": 10,
        "wisdom": 10,
        "charisma": 10,
    }

    # Fighter requires Str 13 AND Dex 13
    result = check_multiclass_requirements("fighter", abilities)
    assert result.can_multiclass is False
    assert "dexterity" in result.missing_requirements


def test_check_multiclass_requirements_unknown_class():
    """Test that unknown classes are allowed."""
    abilities = {
        "strength": 10,
        "dexterity": 10,
        "constitution": 10,
        "intelligence": 10,
        "wisdom": 10,
        "charisma": 10,
    }

    result = check_multiclass_requirements("unknown_class", abilities)
    assert result.can_multiclass is True
    assert result.missing_requirements == {}


def test_parse_classes_empty():
    """Test parsing empty classes."""
    assert parse_classes("{}") == {}
    assert parse_classes("") == {}
    assert parse_classes("null") == {}


def test_parse_classes_valid():
    """Test parsing valid classes JSON."""
    json_str = '{"wizard": 5, "fighter": 2, "rogue": 3}'
    result = parse_classes(json_str)
    assert result == {"wizard": 5, "fighter": 2, "rogue": 3}


def test_parse_classes_invalid():
    """Test parsing invalid classes JSON."""
    result = parse_classes("invalid json")
    assert result == {}


def test_serialize_classes():
    """Test serializing classes to JSON."""
    classes = {"wizard": 5, "fighter": 2}
    result = serialize_classes(classes)
    assert json.loads(result) == classes


def test_calculate_total_level():
    """Test total level calculation."""
    assert calculate_total_level({"wizard": 5, "fighter": 2}) == 7
    assert calculate_total_level({"rogue": 1}) == 1
    assert calculate_total_level({}) == 0


def test_calculate_proficiency_bonus():
    """Test proficiency bonus from total level."""
    assert calculate_proficiency_bonus({"wizard": 1, "fighter": 1}) == 2  # Level 2
    assert calculate_proficiency_bonus({"wizard": 4, "fighter": 1}) == 2  # Level 5
    assert calculate_proficiency_bonus({"wizard": 5, "fighter": 5}) == 3  # Level 10
    assert calculate_proficiency_bonus({"wizard": 16, "fighter": 4}) == 5  # Level 20


def test_calculate_multiclass_hp_single_class():
    """Test HP calculation for single class."""
    # Level 5 wizard (d6 hit die, +2 CON mod)
    classes = {"wizard": 5}
    con_mod = 2

    total_hp, breakdown = calculate_multiclass_hp(classes, con_mod)

    # Level 1: d6 + 2 = 6 + 2 = 8
    # Levels 2-5: (6//2+1+2) * 4 = (3+1+2) * 4 = 6 * 4 = 24
    # Total: 8 + 24 = 32
    assert total_hp == 32
    assert len(breakdown) == 1
    assert breakdown[0].class_name == "wizard"
    assert breakdown[0].levels_in_class == 5
    assert breakdown[0].hit_die == 6
    assert breakdown[0].con_mod == 2


def test_calculate_multiclass_hp_two_classes():
    """Test HP calculation for two classes."""
    # Level 3 wizard (d6) + Level 2 fighter (d10), +2 CON mod
    classes = {"wizard": 3, "fighter": 2}
    con_mod = 2

    total_hp, breakdown = calculate_multiclass_hp(classes, con_mod)

    # Wizard: d6+2=8 (level 1) + 6*2=12 (levels 2-3) = 20
    # Fighter: d10+2=12 (level 1) + 7*1=7 (level 2) = 19
    # Total: 20 + 19 = 39
    assert total_hp == 39
    assert len(breakdown) == 2

    wizard_hp = [b for b in breakdown if b.class_name == "wizard"][0]
    fighter_hp = [b for b in breakdown if b.class_name == "fighter"][0]

    assert wizard_hp.total_hp_gained == 20
    assert fighter_hp.total_hp_gained == 19


def test_calculate_multiclass_hp_negative_con():
    """Test HP calculation with negative CON mod."""
    # Level 1 wizard, -1 CON mod
    classes = {"wizard": 1}
    con_mod = -1

    total_hp, breakdown = calculate_multiclass_hp(classes, con_mod)

    # Level 1: d6 + (-1) = 5, but minimum is 1
    assert total_hp >= 1
    assert breakdown[0].total_hp_gained >= 1


def test_calculate_multiclass_asi_status_single_class():
    """Test ASI status for single class."""
    # Level 4 fighter earns ASI at level 4
    classes = {"fighter": 4}
    asi_used = 0

    status = calculate_multiclass_asi_status(classes, asi_used)

    assert status.earned == 1  # Fighter gets ASI at 4
    assert status.used == 0
    assert status.available == 1
    assert status.next_asi_level == 6  # Fighter's next ASI


def test_calculate_multiclass_asi_status_two_classes():
    """Test ASI status for two classes."""
    # Level 4 fighter (1 ASI) + Level 4 wizard (1 ASI) = 2 total
    classes = {"fighter": 4, "wizard": 4}
    asi_used = 1

    status = calculate_multiclass_asi_status(classes, asi_used)

    assert status.earned == 2
    assert status.used == 1
    assert status.available == 1


def test_calculate_multiclass_asi_status_all_asi_used():
    """Test ASI status when all ASIs are spent."""
    classes = {"fighter": 8}  # ASIs at 4, 6, 8 = 3 total
    asi_used = 3

    status = calculate_multiclass_asi_status(classes, asi_used)

    assert status.earned == 3
    assert status.used == 3
    assert status.available == 0


def test_build_multiclass_summary():
    """Test building complete multiclass summary."""
    classes = {"wizard": 5, "fighter": 3}
    con_mod = 2
    asi_used = 1

    summary = build_multiclass_summary(classes, con_mod, asi_used)

    assert summary.classes == classes
    assert summary.total_level == 8
    assert summary.proficiency_bonus == 3  # Level 8 = +3 proficiency
    assert summary.total_hp > 0
    assert len(summary.hp_breakdown) == 2
    assert summary.primary_class == "wizard"  # Higher level
    assert summary.asi_status.earned >= 0
    assert summary.asi_status.used == 1


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

def test_create_character_with_classes():
    """Test creating a character sets up the classes field."""
    response = client.post(
        "/api/characters/",
        json={
            "name": "Test Character",
            "race": "Human",
            "char_class": "Wizard",
            "level": 3,
            "strength": 10,
            "dexterity": 14,
            "constitution": 12,
            "intelligence": 16,
            "wisdom": 12,
            "charisma": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["classes"] == {"wizard": 3}
    assert data["primary_class"] == "wizard"
    assert data["level"] == 3


def test_get_character_includes_classes():
    """Test that getting a character returns classes and primary_class."""
    # First create a character
    create_response = client.post(
        "/api/characters/",
        json={
            "name": "Test Char 2",
            "race": "Elf",
            "char_class": "Rogue",
            "level": 2,
            "strength": 10,
            "dexterity": 16,
            "constitution": 12,
            "intelligence": 10,
            "wisdom": 12,
            "charisma": 10,
        },
    )

    char_id = create_response.json()["id"]

    # Get the character
    response = client.get(f"/api/characters/{char_id}")

    assert response.status_code == 200
    data = response.json()
    assert "classes" in data
    assert "primary_class" in data
    assert data["classes"] == {"rogue": 2}
    assert data["primary_class"] == "rogue"


def test_add_class_success():
    """Test successfully adding a second class."""
    # Create a character with good stats for multiclassing
    create_response = client.post(
        "/api/characters/",
        json={
            "name": "Multiclass Test",
            "race": "Human",
            "char_class": "Wizard",
            "level": 1,
            "strength": 13,  # Good for fighter multiclass
            "dexterity": 14,  # Good for fighter multiclass
            "constitution": 12,
            "intelligence": 16,
            "wisdom": 12,
            "charisma": 10,
        },
    )

    char_id = create_response.json()["id"]

    # Add fighter class
    response = client.post(
        f"/api/characters/{char_id}/classes",
        json={"new_class": "fighter"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "fighter" in data["classes"]
    assert "wizard" in data["classes"]
    assert data["classes"]["fighter"] == 1
    assert data["classes"]["wizard"] == 1
    assert data["total_level"] == 2
    assert data["hp_gained"] > 0


def test_add_class_prerequisite_failure():
    """Test that adding a class without meeting prerequisites fails."""
    # Create a character with poor stats
    create_response = client.post(
        "/api/characters/",
        json={
            "name": "Poor Stats",
            "race": "Human",
            "char_class": "Wizard",
            "level": 1,
            "strength": 8,  # Too low for fighter (needs 13)
            "dexterity": 10,  # Too low for fighter (needs 13)
            "constitution": 10,
            "intelligence": 16,
            "wisdom": 12,
            "charisma": 10,
        },
    )

    char_id = create_response.json()["id"]

    # Try to add fighter (needs Str 13 AND Dex 13)
    response = client.post(
        f"/api/characters/{char_id}/classes",
        json={"new_class": "fighter"},
    )

    assert response.status_code == 400
    assert "requires" in response.json()["detail"].lower()


def test_add_class_duplicate():
    """Test that adding an existing class fails."""
    create_response = client.post(
        "/api/characters/",
        json={
            "name": "Wizard Duplicate",
            "race": "Human",
            "char_class": "Wizard",
            "level": 1,
            "strength": 10,
            "dexterity": 14,
            "constitution": 12,
            "intelligence": 16,
            "wisdom": 12,
            "charisma": 10,
        },
    )

    char_id = create_response.json()["id"]

    # Try to add wizard again
    response = client.post(
        f"/api/characters/{char_id}/classes",
        json={"new_class": "wizard"},
    )

    assert response.status_code == 400
    assert "already" in response.json()["detail"].lower()


def test_add_class_limit_two_classes():
    """Test that adding a third class is blocked."""
    # Create a character with two classes
    create_response = client.post(
        "/api/characters/",
        json={
            "name": "Two Classes",
            "race": "Human",
            "char_class": "Wizard",
            "level": 1,
            "strength": 13,
            "dexterity": 14,
            "constitution": 12,
            "intelligence": 16,
            "wisdom": 13,
            "charisma": 10,
        },
    )

    char_id = create_response.json()["id"]

    # Add first multiclass (fighter)
    client.post(f"/api/characters/{char_id}/classes", json={"new_class": "fighter"})

    # Try to add a third class (rogue)
    response = client.post(
        f"/api/characters/{char_id}/classes",
        json={"new_class": "rogue"},
    )

    assert response.status_code == 400
    assert "two classes" in response.json()["detail"].lower()


def test_leveling_with_multiclass():
    """Test awarding XP to a multiclass character."""
    # Create a wizard
    create_response = client.post(
        "/api/characters/",
        json={
            "name": "Multiclass Leveler",
            "race": "Human",
            "char_class": "Wizard",
            "level": 1,
            "strength": 13,
            "dexterity": 14,
            "constitution": 12,
            "intelligence": 16,
            "wisdom": 12,
            "charisma": 10,
        },
    )

    char_id = create_response.json()["id"]

    # Add fighter
    client.post(f"/api/characters/{char_id}/classes", json={"new_class": "fighter"})

    # Award enough XP to level up (300 XP for level 2)
    response = client.post(
        f"/api/characters/{char_id}/leveling/award-xp",
        json={"xp": 300, "target_class": "wizard"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["leveled_up"] is True
    assert data["to_level"] == 2
    # Should level up wizard since that's the target class
    assert data["classes"]["wizard"] == 2
    assert data["classes"]["fighter"] == 1
    assert data["hp_gained"] > 0


def test_leveling_progress_includes_classes():
    """Test that leveling progress endpoint returns multiclass info."""
    # Create a wizard
    create_response = client.post(
        "/api/characters/",
        json={
            "name": "Progress Test",
            "race": "Human",
            "char_class": "Wizard",
            "level": 1,
            "strength": 13,
            "dexterity": 14,
            "constitution": 12,
            "intelligence": 16,
            "wisdom": 12,
            "charisma": 10,
        },
    )

    char_id = create_response.json()["id"]

    # Add fighter
    client.post(f"/api/characters/{char_id}/classes", json={"new_class": "fighter"})

    # Get leveling progress
    response = client.get(f"/api/characters/{char_id}/leveling")

    assert response.status_code == 200
    data = response.json()
    assert "classes" in data
    assert "primary_class" in data
    assert data["classes"]["wizard"] == 1
    assert data["classes"]["fighter"] == 1
    assert data["total_level"] == 2
    assert data["proficiency_bonus"] == 2


def test_apply_asi_multiclass():
    """Test applying ASI with multiclass character."""
    # Create a character at level 4 (earns ASI)
    create_response = client.post(
        "/api/characters/",
        json={
            "name": "ASI Test",
            "race": "Human",
            "char_class": "Fighter",
            "level": 4,
            "strength": 14,
            "dexterity": 14,
            "constitution": 14,
            "intelligence": 10,
            "wisdom": 10,
            "charisma": 10,
        },
    )

    char_id = create_response.json()["id"]

    # Apply ASI
    response = client.post(
        f"/api/characters/{char_id}/leveling/apply-asi",
        json={"choices": [{"ability": "strength", "amount": 2}]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["abilities"]["strength"] == 16
    assert data["asi_used"] == 1


def test_features_multiclass():
    """Test getting features for multiclass character."""
    # Create a character with two classes
    create_response = client.post(
        "/api/characters/",
        json={
            "name": "Features Test",
            "race": "Human",
            "char_class": "Wizard",
            "level": 2,
            "strength": 13,
            "dexterity": 14,
            "constitution": 12,
            "intelligence": 16,
            "wisdom": 13,
            "charisma": 10,
        },
    )

    char_id = create_response.json()["id"]

    # Add fighter
    client.post(f"/api/characters/{char_id}/classes", json={"new_class": "fighter"})

    # Get features
    response = client.get(f"/api/characters/{char_id}/leveling/features")

    assert response.status_code == 200
    data = response.json()
    assert "classes" in data
    assert "features" in data
    assert "wizard" in data["features"]
    assert "fighter" in data["features"]
    # Each class should have at least level 1 features
    assert len(data["features"]["wizard"]) >= 1
    assert len(data["features"]["fighter"]) >= 1


# ---------------------------------------------------------------------------
# Edge cases and backward compatibility
# ---------------------------------------------------------------------------

def test_backward_compat_single_class():
    """Test that single-class characters work with new multiclass system."""
    # Create a single-class character
    create_response = client.post(
        "/api/characters/",
        json={
            "name": "Old School",
            "race": "Human",
            "char_class": "Fighter",
            "level": 5,
            "strength": 16,
            "dexterity": 14,
            "constitution": 14,
            "intelligence": 10,
            "wisdom": 10,
            "charisma": 10,
        },
    )

    assert create_response.status_code == 200
    data = create_response.json()
    assert data["classes"] == {"fighter": 5}
    assert data["level"] == 5
    assert data["primary_class"] == "fighter"


def test_empty_classes_json():
    """Test handling of empty classes JSON in database."""
    # This simulates a character with empty classes column
    # (which should fall back to char_class/level)
    from app.models.models import Character

    db = TestingSessionLocal()
    char = Character(
        name="Empty Classes",
        race="Human",
        char_class="Wizard",
        level=3,
        classes="{}",  # Empty but valid JSON
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=16,
        wisdom=12,
        charisma=10,
    )

    # The properties should handle this gracefully
    classes_dict = char.classes_dict
    assert classes_dict == {"wizard": 3}
    assert char.primary_class == "wizard"

    db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])