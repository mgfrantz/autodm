"""
Tests for the character creation and management API.

Covers character CRUD operations, stat calculations, and validation.
"""
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.database import get_db
from app.models.models import Base, Character, World, GameSave


class TestCreateCharacter:
    """Test character creation API."""

    def test_create_character_basic(self, client):
        """Test creating a basic character with minimal data."""
        response = client.post("/api/characters/", json={
            "name": "Aragorn",
            "race": "Human",
            "char_class": "Fighter",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Aragorn"
        assert data["race"] == "Human"
        assert data["char_class"] == "Fighter"
        assert data["level"] == 1  # Default
        assert data["id"] > 0

    def test_create_character_with_custom_abilities(self, client):
        """Test creating a character with custom ability scores."""
        response = client.post("/api/characters/", json={
            "name": "Gandalf",
            "race": "Human",
            "char_class": "Wizard",
            "strength": 8,
            "dexterity": 12,
            "constitution": 14,
            "intelligence": 20,
            "wisdom": 16,
            "charisma": 10,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["strength"] == 8
        assert data["dexterity"] == 12
        assert data["constitution"] == 14
        assert data["intelligence"] == 20
        assert data["wisdom"] == 16
        assert data["charisma"] == 10

    def test_create_character_with_background(self, client):
        """Test creating a character with background and backstory."""
        response = client.post("/api/characters/", json={
            "name": "Legolas",
            "race": "Elf",
            "char_class": "Ranger",
            "background": "Outlander",
            "backstory": "A skilled archer from Mirkwood forest.",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["background"] == "Outlander"
        assert data["backstory"] == "A skilled archer from Mirkwood forest."

    def test_create_character_hp_calculation(self, client):
        """Test HP calculation: hit die + CON mod."""
        # Fighter has d10 hit die
        # CON 16 gives +3 modifier
        # Expected HP: 10 + 3 = 13
        response = client.post("/api/characters/", json={
            "name": "Conan",
            "race": "Human",
            "char_class": "Fighter",
            "constitution": 16,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["max_hp"] == 13
        assert data["current_hp"] == 13

    def test_create_character_hp_minimum_one(self, client):
        """Test that minimum HP is 1 even with negative CON mod."""
        # Wizard has d6 hit die
        # CON 1 gives -5 modifier
        # Raw HP: 6 + (-5) = 1 (minimum enforced)
        response = client.post("/api/characters/", json={
            "name": "Weakling",
            "race": "Human",
            "char_class": "Wizard",
            "constitution": 1,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["max_hp"] >= 1
        assert data["current_hp"] >= 1

    def test_create_character_hp_by_class(self, client):
        """Test HP calculation for different classes."""
        # Barbarian: d12 + CON mod
        response_barbarian = client.post("/api/characters/", json={
            "name": "Gruumsh",
            "race": "Orc",
            "char_class": "Barbarian",
            "constitution": 14,
        })
        assert response_barbarian.status_code == 200
        barbarian = response_barbarian.json()
        # 12 + 2 = 14
        assert barbarian["max_hp"] == 14

        # Wizard: d6 + CON mod
        response_wizard = client.post("/api/characters/", json={
            "name": "Merlin",
            "race": "Human",
            "char_class": "Wizard",
            "constitution": 10,
        })
        assert response_wizard.status_code == 200
        wizard = response_wizard.json()
        # 6 + 0 = 6
        assert wizard["max_hp"] == 6

    def test_create_character_ac_by_class(self, client):
        """Test AC calculation for different classes."""
        # Fighter: base AC 16
        response_fighter = client.post("/api/characters/", json={
            "name": "Knight",
            "race": "Human",
            "char_class": "Fighter",
        })
        assert response_fighter.status_code == 200
        assert response_fighter.json()["armor_class"] == 16

        # Rogue: base AC 13
        response_rogue = client.post("/api/characters/", json={
            "name": "Thief",
            "race": "Human",
            "char_class": "Rogue",
        })
        assert response_rogue.status_code == 200
        assert response_rogue.json()["armor_class"] == 13

        # Barbarian: base AC 12 (unarmored defense)
        response_barbarian = client.post("/api/characters/", json={
            "name": "Savage",
            "race": "Human",
            "char_class": "Barbarian",
        })
        assert response_barbarian.status_code == 200
        assert response_barbarian.json()["armor_class"] == 12

    def test_create_character_speed_by_race(self, client):
        """Test speed calculation for different races."""
        # Human: speed 30
        response_human = client.post("/api/characters/", json={
            "name": "Human",
            "race": "Human",
            "char_class": "Fighter",
        })
        assert response_human.status_code == 200
        assert response_human.json()["speed"] == 30

        # Dwarf: speed 25
        response_dwarf = client.post("/api/characters/", json={
            "name": "Dwarf",
            "race": "Dwarf",
            "char_class": "Fighter",
        })
        assert response_dwarf.status_code == 200
        assert response_dwarf.json()["speed"] == 25

        # Halfling: speed 25
        response_halfling = client.post("/api/characters/", json={
            "name": "Halfling",
            "race": "Halfling",
            "char_class": "Rogue",
        })
        assert response_halfling.status_code == 200
        assert response_halfling.json()["speed"] == 25

    def test_create_character_unknown_race_speed(self, client):
        """Test that unknown races get default speed 30."""
        response = client.post("/api/characters/", json={
            "name": "Alien",
            "race": "UnknownRace",
            "char_class": "Fighter",
        })
        assert response.status_code == 200
        assert response.json()["speed"] == 30

    def test_create_character_all_classes_have_hit_dice(self, client):
        """Test that all core classes have defined hit dice."""
        classes = [
            "Barbarian", "Bard", "Cleric", "Druid", "Fighter", "Monk",
            "Paladin", "Ranger", "Rogue", "Sorcerer", "Warlock", "Wizard",
        ]
        for char_class in classes:
            response = client.post("/api/characters/", json={
                "name": f"Test {char_class}",
                "race": "Human",
                "char_class": char_class,
            })
            assert response.status_code == 200, f"Failed for class: {char_class}"
            data = response.json()
            assert data["max_hp"] > 0, f"HP not calculated for class: {char_class}"

    def test_create_character_case_insensitive_class(self, client):
        """Test that class names are case-insensitive."""
        response_lower = client.post("/api/characters/", json={
            "name": "Fighter 1",
            "race": "Human",
            "char_class": "fighter",
        })
        assert response_lower.status_code == 200

        response_upper = client.post("/api/characters/", json={
            "name": "Fighter 2",
            "race": "Human",
            "char_class": "FIGHTER",
        })
        assert response_upper.status_code == 200

        # Both should have same base AC and hit die
        assert response_lower.json()["armor_class"] == response_upper.json()["armor_class"]
        assert response_lower.json()["max_hp"] == response_upper.json()["max_hp"]


class TestListCharacters:
    """Test character listing API."""

    def test_list_empty_characters(self, client):
        """Test listing characters when none exist."""
        response = client.get("/api/characters/")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_single_character(self, client):
        """Test listing one character."""
        client.post("/api/characters/", json={
            "name": "Hero",
            "race": "Human",
            "char_class": "Fighter",
        })
        response = client.get("/api/characters/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Hero"

    def test_list_multiple_characters(self, client):
        """Test listing multiple characters."""
        names = ["Aragorn", "Gimli", "Legolas"]
        for name in names:
            client.post("/api/characters/", json={
                "name": name,
                "race": "Human",
                "char_class": "Fighter",
            })
        response = client.get("/api/characters/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        returned_names = [c["name"] for c in data]
        assert all(name in returned_names for name in names)

    def test_list_characters_sorted_by_creation_time(self, client):
        """Test that characters are listed in reverse chronological order."""
        # Create characters with a small delay
        client.post("/api/characters/", json={"name": "First", "race": "Human", "char_class": "Fighter"})
        client.post("/api/characters/", json={"name": "Second", "race": "Human", "char_class": "Fighter"})
        client.post("/api/characters/", json={"name": "Third", "race": "Human", "char_class": "Fighter"})

        response = client.get("/api/characters/")
        assert response.status_code == 200
        data = response.json()
        # Most recent first
        assert data[0]["name"] == "Third"
        assert data[1]["name"] == "Second"
        assert data[2]["name"] == "First"


class TestGetCharacter:
    """Test getting a specific character by ID."""

    def test_get_character_by_id(self, client):
        """Test getting an existing character."""
        create_response = client.post("/api/characters/", json={
            "name": "Hercules",
            "race": "Human",
            "char_class": "Paladin",
        })
        char_id = create_response.json()["id"]

        get_response = client.get(f"/api/characters/{char_id}")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["id"] == char_id
        assert data["name"] == "Hercules"
        assert data["race"] == "Human"
        assert data["char_class"] == "Paladin"

    def test_get_character_not_found(self, client):
        """Test getting a non-existent character returns 404."""
        response = client.get("/api/characters/99999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_character_returns_all_fields(self, client):
        """Test that get returns all character fields."""
        create_response = client.post("/api/characters/", json={
            "name": "Full Character",
            "race": "Elf",
            "char_class": "Ranger",
            "background": "Outlander",
            "strength": 14,
            "dexterity": 18,
            "constitution": 12,
            "intelligence": 10,
            "wisdom": 14,
            "charisma": 8,
            "backstory": "A forest guardian."
        })
        char_id = create_response.json()["id"]

        response = client.get(f"/api/characters/{char_id}")
        assert response.status_code == 200
        data = response.json()
        expected_fields = [
            "id", "name", "race", "char_class", "level", "background",
            "strength", "dexterity", "constitution", "intelligence",
            "wisdom", "charisma", "max_hp", "current_hp", "armor_class",
            "speed", "backstory"
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"


class TestDeleteCharacter:
    """Test character deletion API."""

    def test_delete_character(self, client):
        """Test deleting a character."""
        create_response = client.post("/api/characters/", json={
            "name": "Doomed",
            "race": "Human",
            "char_class": "Fighter",
        })
        char_id = create_response.json()["id"]

        # Verify character exists
        get_response = client.get(f"/api/characters/{char_id}")
        assert get_response.status_code == 200

        # Delete character
        delete_response = client.delete(f"/api/characters/{char_id}")
        assert delete_response.status_code == 200
        assert delete_response.json() == {"status": "deleted", "id": char_id}

        # Verify character no longer exists
        get_response = client.get(f"/api/characters/{char_id}")
        assert get_response.status_code == 404

    def test_delete_character_not_found(self, client):
        """Test deleting a non-existent character returns 404."""
        response = client.delete("/api/characters/99999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_character_removes_from_list(self, client):
        """Test that deleted character is removed from character list."""
        client.post("/api/characters/", json={"name": "Keep Me", "race": "Human", "char_class": "Fighter"})
        create_response = client.post("/api/characters/", json={
            "name": "Delete Me",
            "race": "Human",
            "char_class": "Rogue",
        })
        char_id = create_response.json()["id"]

        # Initially 2 characters
        list_response = client.get("/api/characters/")
        assert len(list_response.json()) == 2

        # Delete one
        client.delete(f"/api/characters/{char_id}")

        # Now only 1 character
        list_response = client.get("/api/characters/")
        assert len(list_response.json()) == 1
        assert list_response.json()[0]["name"] == "Keep Me"


class TestCharacterValidation:
    """Test character data validation and edge cases."""

    def test_create_character_with_level(self, client):
        """Test creating a character at a specific level."""
        response = client.post("/api/characters/", json={
            "name": "Veteran",
            "race": "Human",
            "char_class": "Fighter",
            "level": 5,
        })
        assert response.status_code == 200
        assert response.json()["level"] == 5

    def test_create_character_name_required(self, client):
        """Test that name is required."""
        response = client.post("/api/characters/", json={
            "race": "Human",
            "char_class": "Fighter",
        })
        assert response.status_code == 422  # Validation error

    def test_create_character_race_required(self, client):
        """Test that race is required."""
        response = client.post("/api/characters/", json={
            "name": "Hero",
            "char_class": "Fighter",
        })
        assert response.status_code == 422  # Validation error

    def test_create_character_class_required(self, client):
        """Test that class is required."""
        response = client.post("/api/characters/", json={
            "name": "Hero",
            "race": "Human",
        })
        assert response.status_code == 422  # Validation error

    def test_ability_score_defaults_to_ten(self, client):
        """Test that unspecified ability scores default to 10."""
        response = client.post("/api/characters/", json={
            "name": "Average Joe",
            "race": "Human",
            "char_class": "Commoner",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["strength"] == 10
        assert data["dexterity"] == 10
        assert data["constitution"] == 10
        assert data["intelligence"] == 10
        assert data["wisdom"] == 10
        assert data["charisma"] == 10