"""
Tests for the feat API endpoints.
"""
import pytest
from sqlalchemy.orm import Session

from app.models.models import Character


@pytest.fixture
def character(db_session: Session):
    """Create a level 4 fighter with one ASI available."""
    char = Character(
        name="Test Character",
        race="Human",
        char_class="fighter",
        level=4,
        classes='{"fighter": 4}',
        strength=16,
        dexterity=14,
        constitution=14,
        intelligence=10,
        wisdom=12,
        charisma=10,
        max_hp=30,
        current_hp=30,
        armor_class=16,
        speed=30,
        xp=6500,
        asi_used=0,  # Fighter gets ASI at 4, so 1 is available
        feats="[]",
    )
    db_session.add(char)
    db_session.commit()
    db_session.refresh(char)
    return char


def test_list_all_feats(client):
    """Test GET /api/characters/feats/list returns all feats."""
    response = client.get("/api/characters/feats/list")
    assert response.status_code == 200

    feats = response.json()
    assert len(feats) >= 23  # We added Heavy Armor Master

    names = [f["name"] for f in feats]
    assert "Alert" in names
    assert "Sharpshooter" in names
    assert "Tough" in names
    assert "Heavy Armor Master" in names


def test_get_feat_by_name(client):
    """Test GET /api/characters/feats/list/{name} returns a specific feat."""
    response = client.get("/api/characters/feats/list/Alert")
    assert response.status_code == 200

    feat = response.json()
    assert feat["name"] == "Alert"
    assert feat["initiative_bonus"] == 5
    assert feat["ability_bonus"] == {}
    assert feat["ability_bonus_choices"] == []

    # Case-insensitive
    response = client.get("/api/characters/feats/list/alert")
    assert response.status_code == 200
    assert response.json()["name"] == "Alert"

    # Unknown feat
    response = client.get("/api/characters/feats/list/NonExistent")
    assert response.status_code == 404


def test_get_character_feats(character, client):
    """Test GET /api/characters/feats/{id} returns learned feats."""
    response = client.get(f"/api/characters/feats/{character.id}")
    assert response.status_code == 200

    data = response.json()
    assert data["character_id"] == character.id
    assert data["character_name"] == character.name
    assert data["level"] == 4
    assert data["asi_available"] == 1  # Fighter has ASI at 4
    assert data["asi_used"] == 0
    assert data["asi_earned"] == 1
    assert data["feats"] == []  # None learned yet


def test_get_available_feats(character, client):
    """Test GET /api/characters/feats/{id}/available filters by prereqs."""
    response = client.get(f"/api/characters/feats/{character.id}/available")
    assert response.status_code == 200

    available = response.json()
    names = [f["name"] for f in available]

    # Alert should be available (no prereqs)
    assert "Alert" in names

    # War Caster should NOT be available (fighter is not a caster)
    assert "War Caster" not in names

    # Heavy Armor Master should be available (fighter has heavy armor)
    assert "Heavy Armor Master" in names


def test_learn_feat_choice_required(character, client):
    """Test POST /api/characters/{id}/feats/learn requires choice for choice feats."""
    # Try to learn Resilient without choosing an ability
    response = client.post(
        f"/api/characters/feats/{character.id}/learn",
        json={"feat_name": "Resilient", "chosen_ability": None}
    )
    assert response.status_code == 400
    assert "requires choosing an ability" in response.json()["detail"].lower()


def test_learn_feat_invalid_choice(character, db_session: Session, client):
    """Test POST /api/characters/{id}/feats/learn validates choice."""
    # Create a fresh character for this test
    fresh_char = Character(
        name="Fresh Character",
        race="Human",
        char_class="fighter",
        level=4,
        classes='{"fighter": 4}',
        strength=16,
        dexterity=14,
        constitution=14,
        intelligence=10,
        wisdom=12,
        charisma=10,
        max_hp=30,
        current_hp=30,
        armor_class=16,
        speed=30,
        xp=6500,
        asi_used=0,
        feats="[]",
    )
    db_session.add(fresh_char)
    db_session.commit()
    db_session.refresh(fresh_char)

    # Try to learn with invalid choice
    response = client.post(
        f"/api/characters/feats/{fresh_char.id}/learn",
        json={"feat_name": "Athlete", "chosen_ability": "intelligence"}
    )
    assert response.status_code == 400
    assert "not a valid choice" in response.json()["detail"].lower()


def test_learn_feat_tough(character, client):
    """Test learning Tough feat (HP increase)."""
    response = client.post(
        f"/api/characters/feats/{character.id}/learn",
        json={"feat_name": "Tough"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["feat_name"] == "Tough"
    assert data["ability_changes"] == {}
    # Tough grants +2 HP per level × 4 levels = +8 HP
    assert data["max_hp_change"] == 8
    assert data["current_hp_change"] == 8
    assert data["max_hp"] == 38  # 30 + 8
    assert data["current_hp"] == 38
    assert data["asi_available"] == 0  # ASI was consumed

    # Verify the feat was saved
    response = client.get(f"/api/characters/feats/{character.id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["feats"]) == 1
    assert data["feats"][0]["name"] == "Tough"


def test_learn_feat_alert(character, client):
    """Test learning Alert feat (initiative bonus)."""
    response = client.post(
        f"/api/characters/feats/{character.id}/learn",
        json={"feat_name": "Alert"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["feat_name"] == "Alert"
    assert data["ability_changes"] == {}
    assert data["max_hp_change"] == 0
    assert "initiative_bonus" in data["effects_applied"]
    assert data["effects_applied"]["initiative_bonus"] == 5


def test_learn_feat_athlete_with_choice(character, client):
    """Test learning Athlete feat with ability choice."""
    response = client.post(
        f"/api/characters/feats/{character.id}/learn",
        json={"feat_name": "Athlete", "chosen_ability": "strength"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["ability_changes"] == {"strength": 1}
    assert data["asi_available"] == 0  # Consumed

    # Verify character stats updated
    response = client.get(f"/api/characters/{character.id}")
    assert response.status_code == 200
    char_data = response.json()
    assert char_data["strength"] == 17  # 16 + 1


def test_learn_feat_resilient_with_save_prof(character, client):
    """Test learning Resilient feat gives saving throw proficiency."""
    response = client.post(
        f"/api/characters/feats/{character.id}/learn",
        json={"feat_name": "Resilient", "chosen_ability": "constitution"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["ability_changes"] == {"constitution": 1}
    # Check the effects_applied for the save proficiency
    assert "saving_throw_proficiency" in data["effects_applied"]
    assert data["effects_applied"]["saving_throw_proficiency"] == "constitution"

    # Verify character stats updated
    response = client.get(f"/api/characters/{character.id}")
    assert response.status_code == 200
    char_data = response.json()
    assert char_data["constitution"] == 15  # 14 + 1


def test_learn_feat_no_asi_available(character, client):
    """Test learning a feat when no ASI is available."""
    # Use the one ASI
    client.post(
        f"/api/characters/feats/{character.id}/learn",
        json={"feat_name": "Alert"}
    )

    # Try to learn another
    response = client.post(
        f"/api/characters/feats/{character.id}/learn",
        json={"feat_name": "Tough"}
    )
    assert response.status_code == 400
    assert "No ASI instances available" in response.json()["detail"]


def test_learn_feat_already_known(character, db_session: Session, client):
    """Test can't learn the same feat twice."""
    from app.models.database import get_db
    # Learn Alert
    client.post(
        f"/api/characters/feats/{character.id}/learn",
        json={"feat_name": "Alert"}
    )

    # Try to learn it again (need to give the character another ASI)
    # First cheat by setting asi_used back
    char = db_session.query(Character).filter(Character.id == character.id).first()
    char.asi_used = 0  # Reset to have an ASI available
    db_session.commit()

    response = client.post(
        f"/api/characters/feats/{character.id}/learn",
        json={"feat_name": "Alert"}
    )
    assert response.status_code == 400
    assert "already knows" in response.json()["detail"].lower()


def test_learn_feat_prerequisite_not_met(db_session: Session, client):
    """Test can't learn a feat when prerequisites aren't met."""
    # Create a level 4 rogue (not a caster)
    char = Character(
        name="Rogue Character",
        race="Elf",
        char_class="rogue",
        level=4,
        classes='{"rogue": 4}',
        strength=10,
        dexterity=16,
        constitution=12,
        intelligence=12,
        wisdom=14,
        charisma=10,
        max_hp=25,
        current_hp=25,
        armor_class=13,
        speed=30,
        xp=6500,
        asi_used=0,
        feats="[]",
    )
    db_session.add(char)
    db_session.commit()
    db_session.refresh(char)

    # Try to learn War Caster (requires spellcasting)
    response = client.post(
        f"/api/characters/feats/{char.id}/learn",
        json={"feat_name": "War Caster"}
    )
    assert response.status_code == 400
    assert "spellcasting" in response.json()["detail"].lower()


def test_learn_feat_con_increases_hp(character, client):
    """Test that learning a CON-increasing feat retroactively increases HP."""
    # Learn Resilient with +1 CON
    response = client.post(
        f"/api/characters/feats/{character.id}/learn",
        json={"feat_name": "Resilient", "chosen_ability": "constitution"}
    )
    assert response.status_code == 200

    data = response.json()
    # CON 14 -> 15, modifier stays at +2 (no change in mod)
    # But the HP recalculation fixes the character to the correct HP
    assert data["ability_changes"]["constitution"] == 1

    # Verify character HP
    response = client.get(f"/api/characters/{character.id}")
    assert response.status_code == 200
    char_data = response.json()
    assert char_data["constitution"] == 15

    # HP is correctly calculated:
    # Fighter d10, CON 14 (+2): Level 1: 12 HP, Levels 2-4: 3 × 8 = 24 HP, Total: 36 HP
    # CON 15 (+2): Same mod, so HP stays at 36
    assert char_data["max_hp"] == 36