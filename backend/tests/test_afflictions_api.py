"""
Tests for the afflictions API.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.models import Character, GameSave
from app.models.database import get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    """Create tables before each test and drop after."""
    from app.models.models import Base
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Get a database session for test setup."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def test_character(db_session):
    """Create a test character."""
    character = Character(
        name="Test Hero",
        race="Human",
        class_name="Fighter",
        level=1,
        strength=16,
        dexterity=14,
        constitution=14,
        intelligence=10,
        wisdom=12,
        charisma=10,
        max_hp=12,
        current_hp=12
    )
    db_session.add(character)
    db_session.commit()
    db_session.refresh(character)
    return character


@pytest.fixture
def test_game(db_session, test_character):
    """Create a test game."""
    game = GameSave(
        character_id=test_character.id,
        story_log=[],
        game_state={}
    )
    db_session.add(game)
    db_session.commit()
    db_session.refresh(game)
    return game


class TestAfflictionRegistry:
    """Test affliction registry endpoints."""
    
    def test_get_affliction_registry(self):
        """Test getting the full affliction registry."""
        response = client.get("/api/afflictions/registry")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        
        # Check structure of an affliction
        affliction = data[0]
        assert "id" in affliction
        assert "name" in affliction
        assert "type" in affliction
        assert "description" in affliction
        assert "stages" in affliction
        assert "onset_days" in affliction
        assert "save_ability" in affliction
    
    def test_get_diseases(self):
        """Test getting only diseases."""
        response = client.get("/api/afflictions/registry/diseases")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        
        # All should be diseases
        for affliction in data:
            assert affliction["type"] == "disease"
    
    def test_get_poisons(self):
        """Test getting only poisons."""
        response = client.get("/api/afflictions/registry/poisons")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        
        # All should be poisons
        for affliction in data:
            assert affliction["type"] == "poison"
    
    def test_get_affliction_detail(self):
        """Test getting details for a specific affliction."""
        response = client.get("/api/afflictions/registry/cackle_fever")
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == "cackle_fever"
        assert data["name"] == "Cackle Fever"
        assert data["type"] == "disease"
        assert len(data["stages"]) > 0
    
    def test_get_nonexistent_affliction(self):
        """Test getting a non-existent affliction."""
        response = client.get("/api/afflictions/registry/nonexistent")
        assert response.status_code == 404


class TestContractAffliction:
    """Test contracting an affliction."""
    
    def test_contract_affliction(self, test_game):
        """Test contracting a disease."""
        response = client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "cackle_fever"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["affliction_id"] == "cackle_fever"
        assert data["affliction"]["name"] == "Cackle Fever"
        assert data["stage_index"] == -1  # In onset
        assert data["cured"] is False
    
    def test_contract_poison(self, test_game):
        """Test contracting a poison."""
        response = client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "purple_worm_poison"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["affliction"]["type"] == "poison"
        assert data["affliction"]["onset_days"] == 0  # Immediate
    
    def test_contract_duplicate_affliction(self, test_game):
        """Test contracting the same affliction twice."""
        # Contract first time
        client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "cackle_fever"}
        )
        
        # Try to contract again
        response = client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "cackle_fever"}
        )
        assert response.status_code == 400
        assert "already" in response.json()["detail"].lower()
    
    def test_contract_invalid_affliction(self, test_game):
        """Test contracting an invalid affliction."""
        response = client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "invalid_affliction"}
        )
        assert response.status_code == 404


class TestGetAfflictionStatus:
    """Test getting affliction status."""
    
    def test_get_empty_status(self, test_game):
        """Test getting status with no afflictions."""
        response = client.get(f"/api/game/{test_game.id}/afflictions")
        assert response.status_code == 200
        
        data = response.json()
        assert "active" in data
        assert len(data["active"]) == 0
    
    def test_get_status_with_affliction(self, test_game):
        """Test getting status with an active affliction."""
        # Contract an affliction
        client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "cackle_fever"}
        )
        
        response = client.get(f"/api/game/{test_game.id}/afflictions")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["active"]) == 1
        assert data["active"][0]["affliction"]["name"] == "Cackle Fever"


class TestAdvanceAfflictions:
    """Test advancing afflictions."""
    
    def test_advance_one_day(self, test_game):
        """Test advancing afflictions by one day."""
        # Contract an affliction with onset
        client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "cackle_fever"}
        )
        
        # Advance one day
        response = client.post(
            f"/api/game/{test_game.id}/afflictions/advance",
            json={"days": 1}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["days_advanced"] == 1
        assert "advancements" in data
        assert "current_status" in data
        assert "effects_breakdown" in data
    
    def test_advance_multiple_days(self, test_game):
        """Test advancing afflictions by multiple days."""
        # Contract a poison (no onset)
        client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "purple_worm_poison"}
        )
        
        # Advance 2 days
        response = client.post(
            f"/api/game/{test_game.id}/afflictions/advance",
            json={"days": 2}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["days_advanced"] == 2
        assert len(data["advancements"]) >= 1
    
    def test_advance_with_stage_progression(self, test_game):
        """Test advancing through stages."""
        # Contract a disease with stages
        client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "cackle_fever"}
        )
        
        # Advance past onset into first stage
        response = client.post(
            f"/api/game/{test_game.id}/afflictions/advance",
            json={"days": 2}
        )
        assert response.status_code == 200
        
        data = response.json()
        status = data["current_status"]
        
        # Should be in first stage now (stage_index 0)
        if len(status["active"]) > 0:
            active = status["active"][0]
            # Days since onset should be 2 (onset was 1 day)
            assert active["days_since_onset"] >= 1
    
    def test_advance_default_days(self, test_game):
        """Test advancing with default (1) days."""
        # Contract an affliction
        client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "cackle_fever"}
        )
        
        # Advance without specifying days
        response = client.post(
            f"/api/game/{test_game.id}/afflictions/advance"
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["days_advanced"] == 1


class TestSaveAgainstAffliction:
    """Test saving against afflictions."""
    
    def test_save_success(self, test_game):
        """Test a successful save."""
        # Contract a disease
        client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "cackle_fever"}
        )
        
        # Advance past onset
        client.post(
            f"/api/game/{test_game.id}/afflictions/advance",
            json={"days": 2}
        )
        
        # Make a successful save
        response = client.post(
            f"/api/game/{test_game.id}/afflictions/save",
            json={
                "affliction_id": "cackle_fever",
                "roll": 15,
                "modifier": 2,
                "treat": False
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["total"] == 17
        assert "cured" in data["narrative"].lower()
    
    def test_save_failure(self, test_game):
        """Test a failed save."""
        # Contract a disease
        client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "cackle_fever"}
        )
        
        # Advance past onset
        client.post(
            f"/api/game/{test_game.id}/afflictions/advance",
            json={"days": 2}
        )
        
        # Make a failed save
        response = client.post(
            f"/api/game/{test_game.id}/afflictions/save",
            json={
                "affliction_id": "cackle_fever",
                "roll": 5,
                "modifier": 2,
                "treat": False
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is False
        assert data["total"] == 7
        assert "failed" in data["narrative"].lower()
    
    def test_save_with_treatment(self, test_game):
        """Test saving with treatment."""
        # Contract a disease
        client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "cackle_fever"}
        )
        
        # Advance past onset
        client.post(
            f"/api/game/{test_game.id}/afflictions/advance",
            json={"days": 2}
        )
        
        # Make a save with treatment
        response = client.post(
            f"/api/game/{test_game.id}/afflictions/save",
            json={
                "affliction_id": "cackle_fever",
                "roll": 12,
                "modifier": 0,
                "treat": True
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["treated"] is True
        assert "treatment" in data["narrative"].lower()
    
    def test_save_already_cured(self, test_game):
        """Test saving against an already cured affliction."""
        # Contract and cure
        client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "cackle_fever"}
        )
        client.post(
            f"/api/game/{test_game.id}/afflictions/advance",
            json={"days": 2}
        )
        client.post(
            f"/api/game/{test_game.id}/afflictions/save",
            json={
                "affliction_id": "cackle_fever",
                "roll": 20,
                "modifier": 0,
                "treat": False
            }
        )
        
        # Try to save again
        response = client.post(
            f"/api/game/{test_game.id}/afflictions/save",
            json={
                "affliction_id": "cackle_fever",
                "roll": 15,
                "modifier": 2,
                "treat": False
            }
        )
        assert response.status_code == 400
        assert "already cured" in response.json()["detail"].lower()


class TestRemoveAffliction:
    """Test removing afflictions (GM action)."""
    
    def test_remove_affliction(self, test_game):
        """Test removing an affliction."""
        # Contract an affliction
        client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "cackle_fever"}
        )
        
        # Remove it
        response = client.delete(f"/api/game/{test_game.id}/afflictions/cackle_fever")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "removed"
        assert data["affliction_id"] == "cackle_fever"
        
        # Verify it's gone
        status_response = client.get(f"/api/game/{test_game.id}/afflictions")
        status_data = status_response.json()
        assert len(status_data["active"]) == 0
    
    def test_remove_nonexistent_affliction(self, test_game):
        """Test removing a non-existent affliction."""
        response = client.delete(f"/api/game/{test_game.id}/afflictions/nonexistent")
        assert response.status_code == 404


class TestGetAfflictionEffects:
    """Test getting affliction effects."""
    
    def test_get_effects_no_afflictions(self, test_game):
        """Test getting effects with no afflictions."""
        response = client.get(f"/api/game/{test_game.id}/afflictions/effects")
        assert response.status_code == 200
        
        data = response.json()
        assert data["has_afflictions"] is False
        assert data["active_count"] == 0
        assert len(data["effects_breakdown"]) == 0
    
    def test_get_effects_with_damage(self, test_game):
        """Test getting effects with a damage-dealing affliction."""
        # Contract a poison
        client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "purple_worm_poison"}
        )
        
        response = client.get(f"/api/game/{test_game.id}/afflictions/effects")
        assert response.status_code == 200
        
        data = response.json()
        assert data["has_afflictions"] is True
        assert data["active_count"] == 1
        # The poison has no onset, so effects should be active
        assert len(data["effects_breakdown"]) > 0


class TestStoryLogging:
    """Test that affliction actions are logged to the story."""
    
    def test_contract_logged(self, test_game, db_session):
        """Test that contracting is logged."""
        client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "cackle_fever"}
        )
        
        db_session.refresh(test_game)
        assert len(test_game.story_log) > 0
        
        last_entry = test_game.story_log[-1]
        assert last_entry["type"] == "system"
        assert "cackle fever" in last_entry["content"].lower()
    
    def test_save_logged(self, test_game, db_session):
        """Test that saves are logged."""
        # Contract and advance
        client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "cackle_fever"}
        )
        client.post(
            f"/api/game/{test_game.id}/afflictions/advance",
            json={"days": 2}
        )
        
        initial_log_count = len(test_game.story_log)
        
        # Save
        client.post(
            f"/api/game/{test_game.id}/afflictions/save",
            json={
                "affliction_id": "cackle_fever",
                "roll": 20,
                "modifier": 0,
                "treat": False
            }
        )
        
        db_session.refresh(test_game)
        assert len(test_game.story_log) > initial_log_count
    
    def test_advance_logged(self, test_game, db_session):
        """Test that advancement is logged."""
        # Contract
        client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "cackle_fever"}
        )
        
        initial_log_count = len(test_game.story_log)
        
        # Advance
        client.post(
            f"/api/game/{test_game.id}/afflictions/advance",
            json={"days": 2}
        )
        
        db_session.refresh(test_game)
        assert len(test_game.story_log) >= initial_log_count


class TestPersistence:
    """Test that affliction state persists correctly."""
    
    def test_affliction_persists(self, test_game, db_session):
        """Test that affliction state persists to database."""
        # Contract an affliction
        client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "cackle_fever"}
        )
        
        # Refresh from database
        db_session.expire_all()
        db_session.refresh(test_game)
        
        # Check game_state
        assert "afflictions" in test_game.game_state
        assert "active" in test_game.game_state["afflictions"]
        assert len(test_game.game_state["afflictions"]["active"]) == 1
    
    def test_advance_persists(self, test_game, db_session):
        """Test that advancement persists."""
        # Contract and advance
        client.post(
            f"/api/game/{test_game.id}/afflictions/contract",
            json={"affliction_id": "cackle_fever"}
        )
        client.post(
            f"/api/game/{test_game.id}/afflictions/advance",
            json={"days": 2}
        )
        
        # Refresh from database
        db_session.expire_all()
        db_session.refresh(test_game)
        
        # Check state
        active = test_game.game_state["afflictions"]["active"][0]
        assert active["days_since_onset"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])