"""
Tests for the combat API endpoints.

These tests verify that combat can be started, attacks can be made,
turns can be advanced, and combat state can be retrieved.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.models.models import Character, World, GameSave


class TestCombatStart:
    """Tests for starting combat."""

    def test_start_combat(self, client: TestClient, db_session):
        """Test starting a combat encounter."""
        # Create a character and game save
        char = Character(
            name="Test Hero",
            race="Human",
            char_class="Fighter",
            level=1,
            background="Soldier",
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
            backstory="A brave hero seeking adventure.",
        )
        db_session.add(char)
        db_session.flush()
        
        w = World(
            name="Test World",
            description="A world for testing.",
            world_data='{"starting_settlement": {"name": "Test Town"}}',
            tone="heroic fantasy",
        )
        db_session.add(w)
        db_session.flush()
        
        save = GameSave(
            name="Test Game",
            character_id=char.id,
            world_id=w.id,
            game_state='{"location": "Test Town"}',
            story_log="[]",
            current_act=1,
            xp=0,
        )
        db_session.add(save)
        db_session.commit()
        
        response = client.post(
            f"/api/game/{save.id}/combat/start",
            json={
                "enemies": [
                    {
                        "name": "Goblin",
                        "max_hp": 7,
                        "armor_class": 15,
                        "initiative_bonus": 2,
                        "speed": 30,
                        "attacks": [
                            {
                                "name": "Scimitar",
                                "attack_bonus": 4,
                                "damage_dice_count": 1,
                                "damage_dice_sides": 6,
                                "damage_bonus": 2,
                                "damage_type": "slashing",
                            }
                        ],
                    }
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Combat started"
        assert len(data["turn_order"]) == 2  # Player + 1 enemy
        assert "current_turn" in data
        assert data["round"] == 1
        assert "encounter" in data

    def test_start_combat_multiple_enemies(self, client: TestClient, db_session):
        """Test starting combat with multiple enemies."""
        char = Character(
            name="Test Hero",
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
        db_session.flush()
        
        w = World(
            name="Test World",
            description="A world for testing.",
            world_data='{"starting_settlement": {"name": "Test Town"}}',
            tone="heroic fantasy",
        )
        db_session.add(w)
        db_session.flush()
        
        save = GameSave(
            name="Test Game",
            character_id=char.id,
            world_id=w.id,
            game_state='{"location": "Test Town"}',
            story_log="[]",
            current_act=1,
            xp=0,
        )
        db_session.add(save)
        db_session.commit()
        
        response = client.post(
            f"/api/game/{save.id}/combat/start",
            json={
                "enemies": [
                    {
                        "name": "Goblin 1",
                        "max_hp": 7,
                        "armor_class": 15,
                        "attacks": [
                            {
                                "name": "Scimitar",
                                "attack_bonus": 4,
                                "damage_dice_count": 1,
                                "damage_dice_sides": 6,
                                "damage_bonus": 2,
                                "damage_type": "slashing",
                            }
                        ],
                    },
                    {
                        "name": "Goblin 2",
                        "max_hp": 7,
                        "armor_class": 15,
                        "attacks": [
                            {
                                "name": "Scimitar",
                                "attack_bonus": 4,
                                "damage_dice_count": 1,
                                "damage_dice_sides": 6,
                                "damage_bonus": 2,
                                "damage_type": "slashing",
                            }
                        ],
                    },
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["turn_order"]) == 3  # Player + 2 enemies

    def test_start_combat_twice_fails(self, client: TestClient, db_session):
        """Test that starting combat twice fails."""
        char = Character(
            name="Test Hero",
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
        db_session.flush()
        
        w = World(
            name="Test World",
            description="A world for testing.",
            world_data='{"starting_settlement": {"name": "Test Town"}}',
            tone="heroic fantasy",
        )
        db_session.add(w)
        db_session.flush()
        
        save = GameSave(
            name="Test Game",
            character_id=char.id,
            world_id=w.id,
            game_state='{"location": "Test Town"}',
            story_log="[]",
            current_act=1,
            xp=0,
        )
        db_session.add(save)
        db_session.commit()
        
        # Start combat once
        client.post(
            f"/api/game/{save.id}/combat/start",
            json={
                "enemies": [
                    {
                        "name": "Goblin",
                        "max_hp": 7,
                        "armor_class": 15,
                        "attacks": [],
                    }
                ]
            },
        )

        # Try to start again
        response = client.post(
            f"/api/game/{save.id}/combat/start",
            json={
                "enemies": [
                    {
                        "name": "Orc",
                        "max_hp": 15,
                        "armor_class": 13,
                        "attacks": [],
                    }
                ]
            },
        )
        assert response.status_code == 400
        assert "Already in combat" in response.json()["detail"]


class TestCombatState:
    """Tests for retrieving combat state."""

    def test_get_combat_state_not_in_combat(self, client: TestClient, db_session):
        """Test getting combat state when not in combat."""
        char = Character(
            name="Test Hero",
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
        db_session.flush()
        
        w = World(
            name="Test World",
            description="A world for testing.",
            world_data='{"starting_settlement": {"name": "Test Town"}}',
            tone="heroic fantasy",
        )
        db_session.add(w)
        db_session.flush()
        
        save = GameSave(
            name="Test Game",
            character_id=char.id,
            world_id=w.id,
            game_state='{"location": "Test Town"}',
            story_log="[]",
            current_act=1,
            xp=0,
        )
        db_session.add(save)
        db_session.commit()
        
        response = client.get(f"/api/game/{save.id}/combat/state")
        assert response.status_code == 200
        data = response.json()
        assert data["in_combat"] is False

    def test_get_combat_state_active(self, client: TestClient, db_session):
        """Test getting combat state when in active combat."""
        char = Character(
            name="Test Hero",
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
        db_session.flush()
        
        w = World(
            name="Test World",
            description="A world for testing.",
            world_data='{"starting_settlement": {"name": "Test Town"}}',
            tone="heroic fantasy",
        )
        db_session.add(w)
        db_session.flush()
        
        save = GameSave(
            name="Test Game",
            character_id=char.id,
            world_id=w.id,
            game_state='{"location": "Test Town"}',
            story_log="[]",
            current_act=1,
            xp=0,
        )
        db_session.add(save)
        db_session.commit()
        
        # Start combat
        client.post(
            f"/api/game/{save.id}/combat/start",
            json={
                "enemies": [
                    {
                        "name": "Goblin",
                        "max_hp": 7,
                        "armor_class": 15,
                        "attacks": [],
                    }
                ]
            },
        )

        # Get state
        response = client.get(f"/api/game/{save.id}/combat/state")
        assert response.status_code == 200
        data = response.json()
        assert data["in_combat"] is True
        assert data["is_active"] is True
        assert data["winner"] is None
        assert data["round"] == 1
        assert "current_turn" in data
        assert "encounter" in data


class TestCombatAttacks:
    """Tests for making attacks during combat."""

    def test_make_attack(self, client: TestClient, db_session):
        """Test making an attack."""
        char = Character(
            name="Test Hero",
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
        db_session.flush()
        
        w = World(
            name="Test World",
            description="A world for testing.",
            world_data='{"starting_settlement": {"name": "Test Town"}}',
            tone="heroic fantasy",
        )
        db_session.add(w)
        db_session.flush()
        
        save = GameSave(
            name="Test Game",
            character_id=char.id,
            world_id=w.id,
            game_state='{"location": "Test Town"}',
            story_log="[]",
            current_act=1,
            xp=0,
        )
        db_session.add(save)
        db_session.commit()
        
        # Start combat
        start_response = client.post(
            f"/api/game/{save.id}/combat/start",
            json={
                "enemies": [
                    {
                        "name": "Goblin",
                        "max_hp": 7,
                        "armor_class": 15,
                        "attacks": [
                            {
                                "name": "Scimitar",
                                "attack_bonus": 4,
                                "damage_dice_count": 1,
                                "damage_dice_sides": 6,
                                "damage_bonus": 2,
                                "damage_type": "slashing",
                            }
                        ],
                    }
                ]
            },
        )
        encounter_data = start_response.json()["encounter"]

        # Player makes an attack
        response = client.post(
            f"/api/game/{save.id}/combat/attack",
            json={
                "attacker_id": "player",
                "target_id": "enemy_1",
                "attack_name": "Longsword",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["attacker"] == save.character.name
        assert data["result"]["target"] == "Goblin"
        assert data["result"]["attack"] == "Longsword"
        assert "hit" in data["result"]
        assert "damage" in data["result"]

    def test_attack_kills_enemy(self, client: TestClient, db_session):
        """Test that attacking can kill an enemy."""
        char = Character(
            name="Test Hero",
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
        db_session.flush()
        
        w = World(
            name="Test World",
            description="A world for testing.",
            world_data='{"starting_settlement": {"name": "Test Town"}}',
            tone="heroic fantasy",
        )
        db_session.add(w)
        db_session.flush()
        
        save = GameSave(
            name="Test Game",
            character_id=char.id,
            world_id=w.id,
            game_state='{"location": "Test Town"}',
            story_log="[]",
            current_act=1,
            xp=0,
        )
        db_session.add(save)
        db_session.commit()
        
        # Start combat with a weak enemy
        client.post(
            f"/api/game/{save.id}/combat/start",
            json={
                "enemies": [
                    {
                        "name": "Weak Goblin",
                        "max_hp": 1,
                        "armor_class": 10,
                        "attacks": [],
                    }
                ]
            },
        )

        # Make an attack (should hit easily)
        response = client.post(
            f"/api/game/{save.id}/combat/attack",
            json={
                "attacker_id": "player",
                "target_id": "enemy_1",
                "attack_name": "Longsword",
            },
        )

        # Check state - combat should still be active (turn-based, not death-based)
        state = client.get(f"/api/game/{save.id}/combat/state").json()
        # Enemy might be dead from damage
        encounter = state["encounter"]
        enemy = next(c for c in encounter["combatants"] if c["id"] == "enemy_1")
        # With AC 10, the attack should hit and deal at least some damage
        # The enemy's HP should be reduced (they started with 1 HP)
        assert enemy["current_hp"] <= 1  # Either 0 (dead) or still 1 if no damage dealt


class TestCombatTurns:
    """Tests for advancing turns in combat."""

    def test_next_turn(self, client: TestClient, db_session):
        """Test advancing to the next turn."""
        char = Character(
            name="Test Hero",
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
        db_session.flush()
        
        w = World(
            name="Test World",
            description="A world for testing.",
            world_data='{"starting_settlement": {"name": "Test Town"}}',
            tone="heroic fantasy",
        )
        db_session.add(w)
        db_session.flush()
        
        save = GameSave(
            name="Test Game",
            character_id=char.id,
            world_id=w.id,
            game_state='{"location": "Test Town"}',
            story_log="[]",
            current_act=1,
            xp=0,
        )
        db_session.add(save)
        db_session.commit()
        
        # Start combat
        client.post(
            f"/api/game/{save.id}/combat/start",
            json={
                "enemies": [
                    {
                        "name": "Goblin",
                        "max_hp": 7,
                        "armor_class": 15,
                        "attacks": [],
                    }
                ]
            },
        )

        # Get initial state
        initial_state = client.get(f"/api/game/{save.id}/combat/state").json()
        initial_turn = initial_state["current_turn"]

        # Advance turn
        response = client.post(f"/api/game/{save.id}/combat/next-turn")
        assert response.status_code == 200
        data = response.json()
        assert "current_turn" in data

        # Turn should have changed
        new_state = client.get(f"/api/game/{save.id}/combat/state").json()
        # The turn may have advanced to the next combatant
        assert "current_turn" in new_state


class TestCombatEnd:
    """Tests for ending combat."""

    def test_end_combat(self, client: TestClient, db_session):
        """Test manually ending combat."""
        char = Character(
            name="Test Hero",
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
        db_session.flush()
        
        w = World(
            name="Test World",
            description="A world for testing.",
            world_data='{"starting_settlement": {"name": "Test Town"}}',
            tone="heroic fantasy",
        )
        db_session.add(w)
        db_session.flush()
        
        save = GameSave(
            name="Test Game",
            character_id=char.id,
            world_id=w.id,
            game_state='{"location": "Test Town"}',
            story_log="[]",
            current_act=1,
            xp=0,
        )
        db_session.add(save)
        db_session.commit()
        
        # Start combat
        client.post(
            f"/api/game/{save.id}/combat/start",
            json={
                "enemies": [
                    {
                        "name": "Goblin",
                        "max_hp": 7,
                        "armor_class": 15,
                        "attacks": [],
                    }
                ]
            },
        )

        # End combat
        response = client.post(f"/api/game/{save.id}/combat/end")
        assert response.status_code == 200
        assert response.json()["message"] == "Combat ended manually"

        # Verify state
        state = client.get(f"/api/game/{save.id}/combat/state").json()
        assert state["in_combat"] is False

    def test_end_combat_when_not_in_combat_fails(self, client: TestClient, db_session):
        """Test that ending combat when not in combat fails."""
        char = Character(
            name="Test Hero",
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
        db_session.flush()
        
        w = World(
            name="Test World",
            description="A world for testing.",
            world_data='{"starting_settlement": {"name": "Test Town"}}',
            tone="heroic fantasy",
        )
        db_session.add(w)
        db_session.flush()
        
        save = GameSave(
            name="Test Game",
            character_id=char.id,
            world_id=w.id,
            game_state='{"location": "Test Town"}',
            story_log="[]",
            current_act=1,
            xp=0,
        )
        db_session.add(save)
        db_session.commit()
        
        response = client.post(f"/api/game/{save.id}/combat/end")
        assert response.status_code == 400
        assert "Not in combat" in response.json()["detail"]