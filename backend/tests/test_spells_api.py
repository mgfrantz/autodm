"""
Tests for the spells API endpoints.

These tests verify that spellbooks can be retrieved, initialized, and
manipulated via the REST API.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.models.models import Character, World, GameSave


class TestGetSpellbook:
    def test_get_empty_spellbook(self, client: TestClient, db_session):
        """Test getting a character's spellbook when uninitialized."""
        char = Character(
            name="Test Wizard",
            race="Human",
            char_class="Wizard",
            level=1,
            strength=10,
            dexterity=14,
            constitution=12,
            intelligence=16,
            wisdom=10,
            charisma=10,
            max_hp=8,
            current_hp=8,
            armor_class=12,
            speed=30,
        )
        db_session.add(char)
        db_session.commit()

        response = client.get(f"/api/characters/{char.id}/spells")
        assert response.status_code == 200
        data = response.json()
        assert data["char_class"] == "wizard"
        assert data["level"] == 1
        assert data["caster_type"] == "full"
        assert data["casting_style"] == "prepared"
        assert data["known_spells"] == []

    def test_get_spellbook_fighter(self, client: TestClient, db_session):
        """Test that non-casters show 'none' caster type."""
        char = Character(
            name="Test Fighter",
            race="Human",
            char_class="Fighter",
            level=1,
            strength=16,
            dexterity=12,
            constitution=14,
            intelligence=10,
            wisdom=10,
            charisma=10,
            max_hp=12,
            current_hp=12,
            armor_class=16,
            speed=30,
        )
        db_session.add(char)
        db_session.commit()

        response = client.get(f"/api/characters/{char.id}/spells")
        assert response.status_code == 200
        data = response.json()
        assert data["char_class"] == "fighter"
        assert data["caster_type"] == "none"
        assert data["casting_style"] == "none"


class TestInitializeSpellbook:
    def test_initialize_wizard_spellbook(self, client: TestClient, db_session):
        """Test initializing a wizard's starting spells."""
        char = Character(
            name="Test Wizard",
            race="Human",
            char_class="Wizard",
            level=1,
            strength=10,
            dexterity=14,
            constitution=12,
            intelligence=16,
            wisdom=10,
            charisma=10,
            max_hp=8,
            current_hp=8,
            armor_class=12,
            speed=30,
        )
        db_session.add(char)
        db_session.commit()

        response = client.post(f"/api/characters/{char.id}/spells/initialize")
        assert response.status_code == 200
        data = response.json()

        assert "fire_bolt" in data["known_spells"]
        assert "magic_missile" in data["known_spells"]
        assert "burning_hands" in data["prepared_spells"]  # Prepared caster

    def test_initialize_sorcerer_spellbook(self, client: TestClient, db_session):
        """Test initializing a sorcerer's starting spells (known caster)."""
        char = Character(
            name="Test Sorcerer",
            race="Human",
            char_class="Sorcerer",
            level=1,
            strength=10,
            dexterity=14,
            constitution=12,
            intelligence=10,
            wisdom=10,
            charisma=16,
            max_hp=8,
            current_hp=8,
            armor_class=12,
            speed=30,
        )
        db_session.add(char)
        db_session.commit()

        response = client.post(f"/api/characters/{char.id}/spells/initialize")
        assert response.status_code == 200
        data = response.json()

        assert "fire_bolt" in data["known_spells"]
        assert "magic_missile" in data["known_spells"]
        assert data["casting_style"] == "known"

    def test_initialize_fighter_spellbook(self, client: TestClient, db_session):
        """Test initializing a non-caster's spellbook (should be empty)."""
        char = Character(
            name="Test Fighter",
            race="Human",
            char_class="Fighter",
            level=1,
            strength=16,
            dexterity=12,
            constitution=14,
            intelligence=10,
            wisdom=10,
            charisma=10,
            max_hp=12,
            current_hp=12,
            armor_class=16,
            speed=30,
        )
        db_session.add(char)
        db_session.commit()

        response = client.post(f"/api/characters/{char.id}/spells/initialize")
        assert response.status_code == 200
        data = response.json()

        assert data["known_spells"] == []
        assert data["caster_type"] == "none"


class TestLearnSpell:
    def test_learn_spell(self, client: TestClient, db_session):
        """Test learning a new spell."""
        char = Character(
            name="Test Wizard",
            race="Human",
            char_class="Wizard",
            level=1,
            strength=10,
            dexterity=14,
            constitution=12,
            intelligence=16,
            wisdom=10,
            charisma=10,
            max_hp=8,
            current_hp=8,
            armor_class=12,
            speed=30,
        )
        db_session.add(char)
        db_session.commit()

        # Initialize first
        client.post(f"/api/characters/{char.id}/spells/initialize")

        # Learn fireball
        response = client.post(
            f"/api/characters/{char.id}/spells/learn",
            json={"spell_id": "fireball"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "fireball" in data["known_spells"]

    def test_learn_unknown_spell_fails(self, client: TestClient, db_session):
        """Test that learning an unknown spell fails."""
        char = Character(
            name="Test Wizard",
            race="Human",
            char_class="Wizard",
            level=1,
            strength=10,
            dexterity=14,
            constitution=12,
            intelligence=16,
            wisdom=10,
            charisma=10,
            max_hp=8,
            current_hp=8,
            armor_class=12,
            speed=30,
        )
        db_session.add(char)
        db_session.commit()

        response = client.post(
            f"/api/characters/{char.id}/spells/learn",
            json={"spell_id": "nonexistent_spell"},
        )
        assert response.status_code == 400


class TestPrepareSpell:
    def test_prepare_spell(self, client: TestClient, db_session):
        """Test preparing a known spell (for prepared casters)."""
        char = Character(
            name="Test Wizard",
            race="Human",
            char_class="Wizard",
            level=1,
            strength=10,
            dexterity=14,
            constitution=12,
            intelligence=16,
            wisdom=10,
            charisma=10,
            max_hp=8,
            current_hp=8,
            armor_class=12,
            speed=30,
        )
        db_session.add(char)
        db_session.commit()

        # Initialize
        client.post(f"/api/characters/{char.id}/spells/initialize")

        # Learn a new spell (not initially prepared)
        client.post(f"/api/characters/{char.id}/spells/learn", json={"spell_id": "fireball"})

        # Prepare it
        response = client.post(
            f"/api/characters/{char.id}/spells/prepare",
            json={"spell_id": "fireball"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "fireball" in data["prepared_spells"]

    def test_prepare_unknown_fails(self, client: TestClient, db_session):
        """Test that preparing an unknown spell fails."""
        char = Character(
            name="Test Wizard",
            race="Human",
            char_class="Wizard",
            level=1,
            strength=10,
            dexterity=14,
            constitution=12,
            intelligence=16,
            wisdom=10,
            charisma=10,
            max_hp=8,
            current_hp=8,
            armor_class=12,
            speed=30,
        )
        db_session.add(char)
        db_session.commit()

        response = client.post(
            f"/api/characters/{char.id}/spells/prepare",
            json={"spell_id": "fireball"},
        )
        assert response.status_code == 400


class TestCastSpell:
    def test_cast_cantrip(self, client: TestClient, db_session):
        """Test casting a cantrip (no slot consumed)."""
        char = Character(
            name="Test Wizard",
            race="Human",
            char_class="Wizard",
            level=1,
            strength=10,
            dexterity=14,
            constitution=12,
            intelligence=16,
            wisdom=10,
            charisma=10,
            max_hp=8,
            current_hp=8,
            armor_class=12,
            speed=30,
        )
        db_session.add(char)
        db_session.commit()

        # Initialize
        client.post(f"/api/characters/{char.id}/spells/initialize")

        # Cast fire bolt (cantrip)
        response = client.post(
            f"/api/characters/{char.id}/spells/cast",
            json={
                "spell_id": "fire_bolt",
                "caster_mod": 3,  # INT +3
                "target_ac": 15,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["slot_level"] == 0  # No slot for cantrips

    def test_cast_leveled_spell(self, client: TestClient, db_session):
        """Test casting a leveled spell (slot consumed)."""
        char = Character(
            name="Test Wizard",
            race="Human",
            char_class="Wizard",
            level=1,
            strength=10,
            dexterity=14,
            constitution=12,
            intelligence=16,
            wisdom=10,
            charisma=10,
            max_hp=8,
            current_hp=8,
            armor_class=12,
            speed=30,
        )
        db_session.add(char)
        db_session.commit()

        # Initialize
        client.post(f"/api/characters/{char.id}/spells/initialize")

        # Cast magic missile
        response = client.post(
            f"/api/characters/{char.id}/spells/cast",
            json={"spell_id": "magic_missile", "caster_mod": 3},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["slot_level"] == 1
        assert data["damage"] > 0

        # Check that a slot was consumed
        spellbook_response = client.get(f"/api/characters/{char.id}/spells")
        spellbook = spellbook_response.json()
        assert spellbook["slots"][0]["used"] == 1  # Level 1 slot used

    def test_cast_without_slots_fails(self, client: TestClient, db_session):
        """Test that casting without available slots fails."""
        char = Character(
            name="Test Wizard",
            race="Human",
            char_class="Wizard",
            level=1,
            strength=10,
            dexterity=14,
            constitution=12,
            intelligence=16,
            wisdom=10,
            charisma=10,
            max_hp=8,
            current_hp=8,
            armor_class=12,
            speed=30,
        )
        db_session.add(char)
        db_session.commit()

        # Initialize
        client.post(f"/api/characters/{char.id}/spells/initialize")

        # Exhaust all level 1 slots (caster has 2 at level 1)
        client.post(f"/api/characters/{char.id}/spells/cast", json={"spell_id": "magic_missile", "caster_mod": 3})
        client.post(f"/api/characters/{char.id}/spells/cast", json={"spell_id": "burning_hands", "caster_mod": 3})

        # Try to cast again
        response = client.post(
            f"/api/characters/{char.id}/spells/cast",
            json={"spell_id": "magic_missile", "caster_mod": 3},
        )
        assert response.status_code == 400
        assert "No spell slots" in response.json()["detail"]


class TestLongRest:
    def test_long_rest_recovers_slots(self, client: TestClient, db_session):
        """Test that long rest recovers all spell slots."""
        char = Character(
            name="Test Wizard",
            race="Human",
            char_class="Wizard",
            level=1,
            strength=10,
            dexterity=14,
            constitution=12,
            intelligence=16,
            wisdom=10,
            charisma=10,
            max_hp=8,
            current_hp=8,
            armor_class=12,
            speed=30,
        )
        db_session.add(char)
        db_session.commit()

        # Initialize
        client.post(f"/api/characters/{char.id}/spells/initialize")

        # Exhaust slots
        client.post(f"/api/characters/{char.id}/spells/cast", json={"spell_id": "magic_missile", "caster_mod": 3})
        client.post(f"/api/characters/{char.id}/spells/cast", json={"spell_id": "magic_missile", "caster_mod": 3})

        # Long rest
        response = client.post(f"/api/characters/{char.id}/spells/rest")
        assert response.status_code == 200

        # Check slots recovered
        spellbook = response.json()
        assert spellbook["slots"][0]["used"] == 0
        assert spellbook["slots"][0]["available"] == 2


class TestSpellRegistry:
    def test_get_spell_registry(self, client: TestClient):
        """Test getting the full spell registry."""
        response = client.get("/api/characters/spells/registry")
        assert response.status_code == 200
        data = response.json()
        assert "spells" in data
        assert len(data["spells"]) > 0

        # Check some expected spells
        spell_ids = [s["id"] for s in data["spells"]]
        assert "fire_bolt" in spell_ids
        assert "magic_missile" in spell_ids
        assert "cure_wounds" in spell_ids

    def test_get_spell_by_id(self, client: TestClient):
        """Test getting a single spell by ID."""
        response = client.get("/api/characters/spells/registry/fire_bolt")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Fire Bolt"
        assert data["level"] == 0
        assert data["school"] == "evocation"

    def test_get_unknown_spell_404(self, client: TestClient):
        """Test that getting an unknown spell returns 404."""
        response = client.get("/api/characters/spells/registry/nonexistent")
        assert response.status_code == 404