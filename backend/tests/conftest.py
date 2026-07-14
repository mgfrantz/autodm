"""
Pytest configuration for DnD LLM Game backend tests.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, AsyncMock, MagicMock

import dspy

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


async def _fake_stream(*_a, **_k):
    """Default fake async stream for tests (yields a short narration)."""
    for piece in ["The ", "tower ", "glows."]:
        yield piece


def _mock_module(prediction: dspy.Prediction) -> MagicMock:
    """Create a mock DSPy module whose call returns the given prediction."""
    return MagicMock(return_value=prediction)


@pytest.fixture(autouse=True)
def mock_game_llm_calls():
    """Auto-mock all DSPy-mediated LLM calls in game.py to prevent test hangs.

    In environments without a valid LLM API key, the DSPy module calls inside
    game.py helpers (quest detection, NPC mood, skill-check resolution, action
    suggestions, narration, etc.) can hang while litellm retries the failed
    request. This fixture patches the **module accessors** and
    ``ensure_dspy_configured`` so that the helper functions themselves still
    execute their real logic — they just get mock modules that return safe
    defaults instead of making real LLM calls.

    Individual tests can override specific module accessors with their own
    ``patch()`` calls — an inner patch takes precedence over this fixture's
    outer patch. Tests that exercise DSPy modules directly (e.g.
    ``test_dm_narration.py`` module tests) are unaffected because they patch
    the module, not game.py.
    """
    ctx_mgr = MagicMock()
    ctx_mgr.build_context.return_value = "Recent events."
    ctx_mgr.should_summarize.return_value = False

    # Mock modules that return safe default predictions.
    mock_dm_narration = _mock_module(dspy.Prediction(narration="The adventure begins."))
    mock_dm_actionable = _mock_module(
        dspy.Prediction(narration="The door creaks.", game_actions=[])
    )
    mock_quests = _mock_module(dspy.Prediction(
        quests_offered=[], quests_completed=[], quests_failed=[],
        information_revealed=[],
    ))
    mock_npc_mood = _mock_module(dspy.Prediction(npc_mood_changes=[]))
    mock_flags = _mock_module(dspy.Prediction(flags_to_set=[], flags_to_clear=[]))
    mock_suggestions = _mock_module(dspy.Prediction(action_suggestions=[]))
    mock_skill_check = _mock_module(dspy.Prediction(
        success=False, degree="failure", stat_changes={}, items_gained=[],
        experience_gained=0, narrative_notes="",
    ))

    with patch("app.api.game.ensure_dspy_configured"), \
         patch("app.api.game.get_dm_narration_module", return_value=mock_dm_narration), \
         patch("app.api.game.get_dm_actionable_narration_module", return_value=mock_dm_actionable), \
         patch("app.api.game.stream_narration_dspy", new=_fake_stream), \
         patch("app.api.game.get_quest_detection_module", return_value=mock_quests), \
         patch("app.api.game.get_npc_mood_detection_module", return_value=mock_npc_mood), \
         patch("app.api.game.get_game_flags_detection_module", return_value=mock_flags), \
         patch("app.api.game.get_action_suggestions_module", return_value=mock_suggestions), \
         patch("app.api.game.get_skill_check_resolver_module", return_value=mock_skill_check), \
         patch("app.api.game.get_context_manager", return_value=ctx_mgr):
        yield


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