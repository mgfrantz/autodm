"""
Pytest configuration for DnD LLM Game backend tests.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models.database import get_db, get_session_factory
from app.models.models import Base, Character, World, GameSave

# Add the backend directory to Python path so app module can be imported
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Create test database file
import tempfile
TEST_DB_FILE = tempfile.NamedTemporaryFile(delete=False, suffix=".db").name
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_FILE}"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session")
def test_db_setup():
    """Set up test database tables once per session."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def db_session(test_db_setup):
    """Create a fresh database session for each test."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Clean up all data after each test
        db.rollback()
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()


@pytest.fixture(scope="function")
def client(db_session):
    """Create a test client with database dependency override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_session_factory():
        # Return the test session factory so routes that manage their own
        # sessions (e.g. streaming endpoints) hit the test database.
        return TestingSessionLocal

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = override_session_factory
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def character(db_session):
    """Create a test character."""
    char = Character(
        name="Test Character",
        race="Human",
        char_class="fighter",
        level=5,
        classes='{"fighter": 5}',
        strength=16,
        dexterity=14,
        constitution=14,
        intelligence=10,
        wisdom=12,
        charisma=10,
        max_hp=45,
        current_hp=45,
        armor_class=16,
        speed=30,
        xp=6500,
        inventory='[]',
        spells='{}',
    )
    db_session.add(char)
    db_session.commit()
    db_session.refresh(char)
    return char


@pytest.fixture(scope="function")
def world(db_session):
    """Create a test world."""
    w = World(
        name="Test World",
        description="A test world for testing.",
        world_data='{"regions": [{"name": "Test Region", "description": "A test region."}]}',
        tone="heroic fantasy",
    )
    db_session.add(w)
    db_session.commit()
    db_session.refresh(w)
    return w