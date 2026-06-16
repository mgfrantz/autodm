"""
Tests for homebrew content API.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


@pytest.fixture
def db_session():
    """Get database session."""
    from app.models.database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_create_homebrew_weapon(db_session):
    """Test creating a homebrew weapon."""
    response = client.post(
        "/api/homebrew/items",
        json={
            "name": "Flamebrand Sword",
            "item_type": "weapon",
            "description": "A sword wreathed in eternal flames",
            "rarity": "rare",
            "value": 500,
            "weight": 3.0,
            "damage_dice_count": 1,
            "damage_dice_sides": 8,
            "damage_bonus": 2,
            "damage_type": "fire",
            "attack_bonus": 1,
            "creator_name": "TestPlayer"
        }
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Flamebrand Sword"
    assert data["item_type"] == "weapon"
    assert data["rarity"] == "rare"
    assert data["stats"]["damage_dice_sides"] == 8
    assert data["stats"]["damage_type"] == "fire"
    assert data["creator_name"] == "TestPlayer"


def test_create_homebrew_armor(db_session):
    """Test creating homebrew armor."""
    response = client.post(
        "/api/homebrew/items",
        json={
            "name": "Dragon Scale Mail",
            "item_type": "armor",
            "description": "Armor forged from dragon scales",
            "rarity": "very_rare",
            "value": 2000,
            "weight": 25.0,
            "armor_type": "heavy",
            "armor_bonus": 18,
            "dex_limit": 2,
            "creator_name": "DwarfSmith"
        }
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Dragon Scale Mail"
    assert data["item_type"] == "armor"
    assert data["stats"]["armor_type"] == "heavy"
    assert data["stats"]["armor_bonus"] == 18
    assert data["stats"]["dex_limit"] == 2


def test_create_homebrew_potion(db_session):
    """Test creating a homebrew potion."""
    response = client.post(
        "/api/homebrew/items",
        json={
            "name": "Elixir of Giant Strength",
            "item_type": "potion",
            "description": "Grants immense strength for 1 hour",
            "rarity": "uncommon",
            "value": 100,
            "weight": 0.5,
            "uses": 1,
            "max_uses": 1,
            "quantity": 3,
            "creator_name": "AlchemistBob"
        }
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Elixir of Giant Strength"
    assert data["item_type"] == "potion"
    assert data["stats"]["quantity"] == 3
    assert data["stats"]["uses"] == 1


def test_create_homebrew_item_invalid_type(db_session):
    """Test creating homebrew item with invalid type."""
    response = client.post(
        "/api/homebrew/items",
        json={
            "name": "Invalid Item",
            "item_type": "invalid_type",
            "description": "Should fail"
        }
    )

    assert response.status_code == 400
    assert "Invalid item_type" in response.json()["detail"]


def test_create_homebrew_item_invalid_rarity(db_session):
    """Test creating homebrew item with invalid rarity."""
    response = client.post(
        "/api/homebrew/items",
        json={
            "name": "Invalid Item",
            "item_type": "weapon",
            "description": "Should fail",
            "rarity": "mythic"
        }
    )

    assert response.status_code == 400
    assert "Invalid rarity" in response.json()["detail"]


def test_list_homebrew_items(db_session):
    """Test listing all homebrew items."""
    # Create some items
    client.post("/api/homebrew/items", json={
        "name": "Test Sword 1",
        "item_type": "weapon",
        "description": "Test weapon",
        "creator_name": "Player1"
    })
    client.post("/api/homebrew/items", json={
        "name": "Test Potion",
        "item_type": "potion",
        "description": "Test potion",
        "creator_name": "Player1"
    })

    response = client.get("/api/homebrew/items")
    assert response.status_code == 200
    items = response.json()
    assert len(items) >= 2

    # Check filtering by type
    response = client.get("/api/homebrew/items?item_type=weapon")
    assert response.status_code == 200
    items = response.json()
    assert all(item["item_type"] == "weapon" for item in items)


def test_get_homebrew_item(db_session):
    """Test getting a specific homebrew item."""
    # Create item
    create_response = client.post(
        "/api/homebrew/items",
        json={
            "name": "Legendary Axe",
            "item_type": "weapon",
            "description": "Axe of legend",
            "rarity": "legendary",
            "damage_dice_count": 1,
            "damage_dice_sides": 12,
            "creator_name": "Hero"
        }
    )
    item_id = create_response.json()["id"]

    # Get item
    response = client.get(f"/api/homebrew/items/{item_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == item_id
    assert data["name"] == "Legendary Axe"
    assert data["rarity"] == "legendary"


def test_get_homebrew_item_not_found(db_session):
    """Test getting a non-existent item."""
    response = client.get("/api/homebrew/items/99999")
    assert response.status_code == 404


def test_update_homebrew_item(db_session):
    """Test updating a homebrew item."""
    # Create item
    create_response = client.post(
        "/api/homebrew/items",
        json={
            "name": "Modifiable Sword",
            "item_type": "weapon",
            "description": "Original description",
            "value": 100,
            "damage_dice_sides": 6,
            "creator_name": "Smith"
        }
    )
    item_id = create_response.json()["id"]

    # Update item
    response = client.put(
        f"/api/homebrew/items/{item_id}",
        json={
            "description": "Updated description",
            "value": 200,
            "damage_dice_sides": 8
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == "Updated description"
    assert data["stats"]["value"] == 200
    assert data["stats"]["damage_dice_sides"] == 8


def test_delete_homebrew_item(db_session):
    """Test deleting a homebrew item."""
    # Create item
    create_response = client.post(
        "/api/homebrew/items",
        json={
            "name": "Temporary Item",
            "item_type": "misc",
            "description": "Will be deleted",
            "creator_name": "TestUser"
        }
    )
    item_id = create_response.json()["id"]

    # Delete item
    response = client.delete(f"/api/homebrew/items/{item_id}")
    assert response.status_code == 204

    # Verify deletion
    response = client.get(f"/api/homebrew/items/{item_id}")
    assert response.status_code == 404


def test_homebrew_item_to_item_conversion(db_session):
    """Test that homebrew items can be converted to Item objects."""
    from app.engine.inventory import Item

    # Create item
    create_response = client.post(
        "/api/homebrew/items",
        json={
            "name": "Convertible Weapon",
            "item_type": "weapon",
            "description": "Test conversion",
            "damage_dice_count": 2,
            "damage_dice_sides": 6,
            "attack_bonus": 1,
            "creator_name": "Tester"
        }
    )
    homebrew_data = create_response.json()

    # Convert stats to Item
    item = Item(**homebrew_data["stats"])
    assert item.name == "Convertible Weapon"
    assert item.damage_dice_count == 2
    assert item.damage_dice_sides == 6
    assert item.attack_bonus == 1