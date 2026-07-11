"""
Tests for world generation — DSPy-mediated world creation API.

Covers the POST /api/world/generate endpoint, the WorldGenerationModule
singleton, to_world_dict assembly, and character-tailoring context.
"""
from unittest.mock import patch

import dspy
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.database import get_db, engine, SessionLocal
from app.models.models import Base, Character, World
from app.llm.dspy_modules import (
    WorldGenerationModule,
    get_world_generation_module,
)

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_db():
    """Use an isolated DB session so generated worlds don't leak between tests."""
    Base.metadata.create_all(bind=engine)

    def _override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.clear()
    with SessionLocal() as db:
        db.query(Character).delete()
        db.query(World).delete()
        db.commit()


def _mock_world_result():
    """A realistic DSPy Prediction resembling world-gen output."""
    return dspy.Prediction(
        name="The Shattered Realm",
        description="A land torn by ancient wars.",
        world_tone="epic fantasy",
        regions=[
            {"name": "Northgate", "description": "Frozen wastes", "terrain": "tundra",
             "settlements": ["Frosthold"], "dangers": ["yetis"],
             "coordinates": [0.5, 0.9], "connections": ["Midlands"]},
            {"name": "Midlands", "description": "Rolling hills", "terrain": "plains",
             "settlements": ["Oakhaven"], "dangers": ["bandits"],
             "coordinates": [0.5, 0.5], "connections": ["Northgate", "Southreach"]},
        ],
        campaign_arc={
            "central_conflict": "The Dragon Lord rises",
            "act_1": "Discover the threat",
            "act_2": "Gather allies",
            "act_3": "Final confrontation",
        },
        starting_settlement={
            "name": "Oakhaven",
            "description": "A peaceful village",
            "notable_locations": ["The Rusty Anchor inn", "Temple of Dawn"],
        },
        npcs=[
            {"name": "Mayor Bram", "role": "village leader", "motivation": "protect his people"},
            {"name": "Sister Mira", "role": "cleric", "motivation": "find a lost relic"},
        ],
        factions=[
            {"name": "The Iron Legion", "goal": "conquer the realm", "alignment": "lawful evil"},
            {"name": "The Forest Guard", "goal": "protect nature", "alignment": "neutral good"},
        ],
        hook="A mysterious stranger collapses at the village gate, clutching a dragon scale.",
    )


def _empty_result():
    """An empty/failure Prediction."""
    return dspy.Prediction(
        name="", description="", world_tone="",
        regions=[], campaign_arc={}, starting_settlement={},
        npcs=[], factions=[], hook="",
    )


# ---------------------------------------------------------------------------
# Module-level tests
# ---------------------------------------------------------------------------

class TestWorldGenerationModule:
    """Test the WorldGenerationModule singleton + to_world_dict assembly."""

    def test_singleton_is_cached(self):
        """The module singleton is created once and reused."""
        first = get_world_generation_module()
        assert get_world_generation_module() is first

    def test_to_world_dict_assembles_schema_fields(self):
        """to_world_dict maps every Prediction field into the WORLD_SCHEMA dict."""
        mod = WorldGenerationModule()
        data = mod.to_world_dict(_mock_world_result(), fallback_tone="heroic fantasy")

        assert data["name"] == "The Shattered Realm"
        assert data["description"] == "A land torn by ancient wars."
        assert data["tone"] == "epic fantasy"
        assert len(data["regions"]) == 2
        assert data["regions"][0]["coordinates"] == [0.5, 0.9]
        assert data["campaign_arc"]["central_conflict"] == "The Dragon Lord rises"
        assert data["starting_settlement"]["name"] == "Oakhaven"
        assert len(data["npcs"]) == 2
        assert len(data["factions"]) == 2
        assert "dragon scale" in data["hook"]

    def test_to_world_dict_fallback_tone(self):
        """When the prediction has no world_tone, the fallback is used."""
        mod = WorldGenerationModule()
        data = mod.to_world_dict(_empty_result(), fallback_tone="dark grimdark")
        assert data["tone"] == "dark grimdark"

    def test_to_world_dict_defaults_on_none(self):
        """None fields fall back to safe defaults."""
        mod = WorldGenerationModule()
        result = dspy.Prediction(
            name=None, description=None, world_tone=None,
            regions=None, campaign_arc=None, starting_settlement=None,
            npcs=None, factions=None, hook=None,
        )
        data = mod.to_world_dict(result, fallback_tone="heroic")
        assert data["name"] == "Unnamed World"
        assert data["regions"] == []
        assert data["npcs"] == []
        assert data["campaign_arc"] == {}

    def test_forward_failure_returns_empty_prediction(self):
        """A failure inside the DSPy call yields a graceful empty Prediction."""
        mod = WorldGenerationModule()
        with patch.object(mod, "generate", side_effect=RuntimeError("boom")):
            result = mod(tone="heroic fantasy")
        assert result.name == ""
        assert result.regions == []


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class TestWorldGenerateAPI:
    """Test the POST /api/world/generate endpoint."""

    def test_generate_world_success(self):
        """A successful generation persists the world and returns WorldResponse."""
        mod = WorldGenerationModule()
        with patch("app.api.world.get_world_generation_module", return_value=mod), \
             patch.object(mod, "generate", return_value=_mock_world_result()), \
             patch("app.api.world.ensure_dspy_configured"):
            response = client.post("/api/world/generate", json={"tone": "epic fantasy"})

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "The Shattered Realm"
        assert data["tone"] == "epic fantasy"
        assert data["id"] > 0

    def test_generate_world_empty_returns_503(self):
        """An empty generation result returns 503."""
        mod = WorldGenerationModule()
        with patch("app.api.world.get_world_generation_module", return_value=mod), \
             patch.object(mod, "generate", return_value=_empty_result()), \
             patch("app.api.world.ensure_dspy_configured"):
            response = client.post("/api/world/generate", json={"tone": "heroic fantasy"})
        assert response.status_code == 503

    def test_generate_world_failure_returns_503(self):
        """A DSPy exception surfaces as a 503."""
        mod = WorldGenerationModule()
        with patch("app.api.world.get_world_generation_module", return_value=mod), \
             patch.object(mod, "generate", side_effect=RuntimeError("LLM down")), \
             patch("app.api.world.ensure_dspy_configured"):
            response = client.post("/api/world/generate", json={"tone": "heroic fantasy"})
        assert response.status_code == 503

    def test_generate_world_with_character_tailoring(self):
        """When a character_id is given, character_context is built and passed."""
        char = Character(
            name="Thalia", race="Elf", char_class="Ranger", level=3,
            strength=12, dexterity=16, constitution=14, intelligence=10,
            wisdom=14, charisma=8, max_hp=30, current_hp=30,
            armor_class=14, speed=35, background="Outlander",
        )
        with SessionLocal() as db:
            db.add(char)
            db.commit()
            db.refresh(char)
            char_id = char.id

        captured = {}

        mod = WorldGenerationModule()

        def spy_forward(*, tone, character_context=""):
            captured["tone"] = tone
            captured["ctx"] = character_context
            return _mock_world_result()

        with patch("app.api.world.get_world_generation_module", return_value=mod), \
             patch.object(mod, "forward", spy_forward), \
             patch("app.api.world.ensure_dspy_configured"):
            response = client.post(
                "/api/world/generate",
                json={"tone": "epic fantasy", "character_id": char_id},
            )

        assert response.status_code == 200
        assert response.json()["name"] == "The Shattered Realm"
        assert "Thalia" in captured["ctx"]
        assert "Ranger" in captured["ctx"]
        assert captured["tone"] == "epic fantasy"

    def test_generate_world_default_tone(self):
        """Omitting tone uses the 'heroic fantasy' default."""
        mod = WorldGenerationModule()
        with patch("app.api.world.get_world_generation_module", return_value=mod), \
             patch.object(mod, "generate", return_value=_mock_world_result()), \
             patch("app.api.world.ensure_dspy_configured"):
            response = client.post("/api/world/generate", json={})
        assert response.status_code == 200

    def test_generate_world_list_and_detail(self):
        """After generating, the world appears in list and detail endpoints."""
        mod = WorldGenerationModule()
        with patch("app.api.world.get_world_generation_module", return_value=mod), \
             patch.object(mod, "generate", return_value=_mock_world_result()), \
             patch("app.api.world.ensure_dspy_configured"):
            gen_response = client.post("/api/world/generate", json={"tone": "epic fantasy"})
        world_id = gen_response.json()["id"]

        list_response = client.get("/api/world/")
        assert list_response.status_code == 200
        assert any(w["id"] == world_id for w in list_response.json())

        detail_response = client.get(f"/api/world/{world_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert detail["name"] == "The Shattered Realm"
        assert detail["world_data"]["regions"][0]["name"] == "Northgate"
        assert detail["world_data"]["hook"].startswith("A mysterious stranger")

    def test_generate_world_detail_not_found(self):
        """A non-existent world id returns 404."""
        response = client.get("/api/world/99999")
        assert response.status_code == 404
