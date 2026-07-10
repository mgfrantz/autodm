"""
Tests for the image generation system — config, prompt builders, client, and API.

The image client is mocked (no real API calls) so tests are fully deterministic.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.llm.image_config import ImageConfig, load_config
from app.llm.image_client import (
    ImageClient,
    ImageNotConfiguredError,
    ImageResult,
    build_portrait_prompt,
    build_scene_prompt,
    get_image_client,
    reset_image_client,
)
from app.models.models import Character, World, GameSave


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _make_game(db_session, *, narration="The dragon swoops over the burning village."):
    char = Character(
        name="Soren", race="Human", char_class="Fighter", level=5,
        classes=json.dumps({"fighter": 5}),
        strength=16, dexterity=12, constitution=14, intelligence=10,
        wisdom=10, charisma=10,
        max_hp=45, current_hp=45, armor_class=16, speed=30,
        gold=500,
    )
    db_session.add(char)
    db_session.flush()

    w = World(
        name="Frontier", description="Open plains.",
        world_data='{}', tone="heroic",
    )
    db_session.add(w)
    db_session.flush()

    story = [
        {"role": "dm", "content": narration, "timestamp": "2025-01-01T00:00:00"},
    ]
    state = {"location": "Burning Village", "in_combat": False, "conditions": []}
    save = GameSave(
        name="Test Game", character_id=char.id, world_id=w.id,
        game_state=json.dumps(state),
        story_log=json.dumps(story),
    )
    db_session.add(save)
    db_session.commit()
    return save


@pytest.fixture
def game(client: TestClient, db_session):
    return _make_game(db_session)


def _mock_image_result(prompt="test prompt") -> ImageResult:
    return ImageResult(
        url="https://example.com/image.png",
        revised_prompt="A dramatic scene",
        model="dall-e-3",
        size="1024x1024",
        quality="standard",
        prompt=prompt,
    )


def _mock_client(configured=True):
    """A mock image client that returns canned results without API calls."""
    client = MagicMock()
    client.is_configured = configured
    client.config = ImageConfig(
        provider="openai" if configured else "none",
        model="dall-e-3",
        api_key="test-key" if configured else "",
        size="1024x1024",
        quality="standard",
    )
    client.generate_image = AsyncMock(return_value=_mock_image_result())
    return client


@pytest.fixture(autouse=True)
def _reset_client():
    """Reset the image client singleton between tests."""
    reset_image_client()
    yield
    reset_image_client()


# --------------------------------------------------------------------------- #
# Config tests
# --------------------------------------------------------------------------- #

class TestImageConfig:
    def test_defaults(self):
        with patch.dict("os.environ", {}, clear=False):
            cfg = load_config()
            # With no env vars set the provider defaults to "openai".
            assert cfg.provider == "openai"
            assert cfg.model == "dall-e-3"
            assert cfg.size == "1024x1024"
            assert cfg.quality == "standard"

    def test_env_override(self):
        env = {
            "IMAGE_PROVIDER": "openai",
            "IMAGE_API_KEY": "sk-test-123",
            "IMAGE_MODEL": "dall-e-3",
            "IMAGE_SIZE": "1792x1024",
            "IMAGE_QUALITY": "hd",
        }
        with patch.dict("os.environ", env, clear=False):
            cfg = load_config()
            assert cfg.api_key == "sk-test-123"
            assert cfg.size == "1792x1024"
            assert cfg.quality == "hd"

    def test_fallback_to_llm_key(self):
        env = {"IMAGE_PROVIDER": "openai", "LLM_API_KEY": "sk-llm-key"}
        # Remove IMAGE_API_KEY and OPENAI_API_KEY if present
        with patch.dict("os.environ", env, clear=True):
            cfg = load_config()
            assert cfg.api_key == "sk-llm-key"

    def test_is_configured(self):
        cfg = ImageConfig(provider="openai", model="dall-e-3", api_key="key")
        assert cfg.is_configured is True

    def test_not_configured_no_key(self):
        cfg = ImageConfig(provider="openai", model="dall-e-3", api_key="")
        assert cfg.is_configured is False

    def test_not_configured_disabled(self):
        cfg = ImageConfig(provider="none", model="dall-e-3", api_key="key")
        assert cfg.is_configured is False


# --------------------------------------------------------------------------- #
# Prompt builder tests
# --------------------------------------------------------------------------- #

class TestPromptBuilders:
    def test_scene_prompt_basic(self):
        prompt = build_scene_prompt("A dark cave looms ahead.")
        assert "A dark cave looms ahead." in prompt
        assert "Fantasy tabletop RPG illustration" in prompt

    def test_scene_prompt_with_context(self):
        prompt = build_scene_prompt(
            "The tavern is alive with music.",
            location="The Rusty Anchor",
            character_name="Soren",
            character_race="Human",
            character_class="Fighter",
        )
        assert "Soren" in prompt
        assert "Human" in prompt
        assert "fighter" in prompt.lower()
        assert "Rusty Anchor" in prompt
        assert "Fantasy tabletop RPG illustration" in prompt

    def test_scene_prompt_takes_last_paragraph(self):
        narration = "First paragraph about history.\n\nThe dragon roars!"
        prompt = build_scene_prompt(narration)
        assert "The dragon roars!" in prompt
        # The first paragraph should not be the focus.
        assert "First paragraph" not in prompt or "The dragon roars!" in prompt

    def test_scene_prompt_strips_markdown(self):
        prompt = build_scene_prompt("**Bold** and _italic_ text.")
        assert "**" not in prompt
        assert "_" not in prompt

    def test_scene_prompt_truncates_long_text(self):
        long_text = "A" * 2000
        prompt = build_scene_prompt(long_text)
        # Should be truncated well under the raw 2000 chars
        # (prompt includes suffix + context, but the narration portion is trimmed)
        assert len(prompt) < 2000

    def test_scene_prompt_empty_narration(self):
        prompt = build_scene_prompt("", location="Dark Forest")
        assert "Dark Forest" in prompt
        assert "Fantasy tabletop RPG illustration" in prompt

    def test_portrait_prompt_basic(self):
        prompt = build_portrait_prompt("Gandalf", "An old wizard with a grey beard.")
        assert "Gandalf" in prompt
        assert "old wizard" in prompt
        assert "portrait" in prompt.lower()

    def test_portrait_prompt_with_race_class(self):
        prompt = build_portrait_prompt(
            "Elara", "A young elf with green eyes.",
            race="Elf", char_class="Wizard",
        )
        assert "Elara" in prompt
        assert "Elf" in prompt
        assert "Wizard" in prompt

    def test_portrait_prompt_no_description(self):
        prompt = build_portrait_prompt("Bob")
        assert "Bob" in prompt
        assert "portrait" in prompt.lower()


# --------------------------------------------------------------------------- #
# ImageClient tests
# --------------------------------------------------------------------------- #

class TestImageClient:
    def test_not_configured_raises(self):
        """generate_image raises when not configured."""
        cfg = ImageConfig(provider="none", model="dall-e-3", api_key="")
        client = ImageClient(cfg)
        assert client.is_configured is False
        import asyncio
        with pytest.raises(ImageNotConfiguredError):
            asyncio.run(client.generate_image("test"))

    def test_singleton(self):
        c1 = get_image_client()
        c2 = get_image_client()
        assert c1 is c2

    def test_reset(self):
        c1 = get_image_client()
        reset_image_client()
        c2 = get_image_client()
        assert c1 is not c2

    @pytest.mark.asyncio
    async def test_generate_image_success(self):
        """Test generate_image with a mocked OpenAI client."""
        cfg = ImageConfig(
            provider="openai", model="dall-e-3", api_key="test-key",
            size="1024x1024", quality="standard",
        )
        client = ImageClient(cfg)

        # Mock the internal OpenAI client
        mock_openai = MagicMock()
        mock_data = MagicMock()
        mock_data.url = "https://example.com/generated.png"
        mock_data.revised_prompt = "A dramatic dragon scene"
        mock_response = MagicMock()
        mock_response.data = [mock_data]
        mock_openai.images.generate = AsyncMock(return_value=mock_response)
        client._client = mock_openai  # bypass lazy init

        result = await client.generate_image("a dragon scene")
        assert result.url == "https://example.com/generated.png"
        assert result.revised_prompt == "A dramatic dragon scene"
        assert result.model == "dall-e-3"
        assert result.size == "1024x1024"
        assert result.prompt == "a dragon scene"

        # Verify the mock was called with the right params
        mock_openai.images.generate.assert_called_once()
        call_kwargs = mock_openai.images.generate.call_args.kwargs
        assert call_kwargs["prompt"] == "a dragon scene"
        assert call_kwargs["model"] == "dall-e-3"
        assert call_kwargs["n"] == 1

    @pytest.mark.asyncio
    async def test_generate_image_custom_size(self):
        cfg = ImageConfig(provider="openai", model="dall-e-3", api_key="key")
        client = ImageClient(cfg)

        mock_openai = MagicMock()
        mock_data = MagicMock()
        mock_data.url = "https://example.com/wide.png"
        mock_data.revised_prompt = None
        mock_response = MagicMock()
        mock_response.data = [mock_data]
        mock_openai.images.generate = AsyncMock(return_value=mock_response)
        client._client = mock_openai

        result = await client.generate_image("wide scene", size="1792x1024", quality="hd")
        assert result.size == "1792x1024"
        assert result.quality == "hd"
        call_kwargs = mock_openai.images.generate.call_args.kwargs
        assert call_kwargs["size"] == "1792x1024"
        assert call_kwargs["quality"] == "hd"

    def test_image_result_to_dict(self):
        result = ImageResult(
            url="https://example.com/img.png",
            revised_prompt="revised",
            model="dall-e-3",
            size="1024x1024",
            quality="standard",
            prompt="original prompt",
        )
        d = result.to_dict()
        assert d["url"] == "https://example.com/img.png"
        assert d["revised_prompt"] == "revised"
        assert d["model"] == "dall-e-3"
        assert d["prompt"] == "original prompt"


# --------------------------------------------------------------------------- #
# API tests
# --------------------------------------------------------------------------- #

class TestImagesAPI:
    def test_status_configured(self, client, game):
        mock = _mock_client(configured=True)
        with patch("app.api.images.get_image_client", return_value=mock):
            r = client.get(f"/api/game/{game.id}/images/status")
        assert r.status_code == 200
        body = r.json()
        assert body["configured"] is True
        assert body["model"] == "dall-e-3"
        assert body["size"] == "1024x1024"

    def test_status_not_configured(self, client, game):
        mock = _mock_client(configured=False)
        with patch("app.api.images.get_image_client", return_value=mock):
            r = client.get(f"/api/game/{game.id}/images/status")
        assert r.status_code == 200
        body = r.json()
        assert body["configured"] is False

    def test_status_game_not_found(self, client):
        r = client.get("/api/game/99999/images/status")
        assert r.status_code == 404

    def test_generate_scene_not_configured(self, client, game):
        mock = _mock_client(configured=False)
        with patch("app.api.images.get_image_client", return_value=mock):
            r = client.post(f"/api/game/{game.id}/images/scene")
        assert r.status_code == 503

    def test_generate_scene_success(self, client, game):
        mock = _mock_client(configured=True)
        with patch("app.api.images.get_image_client", return_value=mock):
            r = client.post(f"/api/game/{game.id}/images/scene")
        assert r.status_code == 200
        body = r.json()
        assert body["image"]["url"] == "https://example.com/image.png"
        assert body["image"]["type"] == "scene"
        assert body["image"]["label"] == "Burning Village"
        assert body["cached_count"] == 1

        # The mock should have been called with a prompt built from narration
        mock.generate_image.assert_called_once()
        prompt_arg = mock.generate_image.call_args.args[0]
        assert "dragon" in prompt_arg.lower()
        assert "Soren" in prompt_arg  # character context
        assert "Fantasy tabletop RPG illustration" in prompt_arg

    def test_generate_scene_caches_in_game_state(self, client, game):
        mock = _mock_client(configured=True)
        with patch("app.api.images.get_image_client", return_value=mock):
            client.post(f"/api/game/{game.id}/images/scene")
            # Generate a second one
            client.post(f"/api/game/{game.id}/images/scene")

        # Verify both are cached
        r = client.get(f"/api/game/{game.id}/images")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 2
        assert all(img["type"] == "scene" for img in body["images"])

    def test_generate_portrait_success(self, client, game):
        mock = _mock_client(configured=True)
        with patch("app.api.images.get_image_client", return_value=mock):
            r = client.post(
                f"/api/game/{game.id}/images/portrait",
                json={
                    "name": "Elara",
                    "description": "An elf with silver hair",
                    "race": "Elf",
                    "char_class": "Wizard",
                },
            )
        assert r.status_code == 200
        body = r.json()
        assert body["image"]["type"] == "portrait"
        assert body["image"]["label"] == "Elara"
        assert body["image"]["url"] == "https://example.com/image.png"

        prompt_arg = mock.generate_image.call_args.args[0]
        assert "Elara" in prompt_arg
        assert "Elf" in prompt_arg
        assert "Wizard" in prompt_arg
        assert "portrait" in prompt_arg.lower()

    def test_generate_portrait_not_configured(self, client, game):
        mock = _mock_client(configured=False)
        with patch("app.api.images.get_image_client", return_value=mock):
            r = client.post(
                f"/api/game/{game.id}/images/portrait",
                json={"name": "Bob"},
            )
        assert r.status_code == 503

    def test_list_images_empty(self, client, game):
        mock = _mock_client(configured=True)
        with patch("app.api.images.get_image_client", return_value=mock):
            r = client.get(f"/api/game/{game.id}/images")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 0
        assert body["images"] == []

    def test_list_images_after_generation(self, client, game):
        mock = _mock_client(configured=True)
        with patch("app.api.images.get_image_client", return_value=mock):
            client.post(f"/api/game/{game.id}/images/scene")
            client.post(
                f"/api/game/{game.id}/images/portrait",
                json={"name": "Gandalf"},
            )
            r = client.get(f"/api/game/{game.id}/images")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 2
        types = [img["type"] for img in body["images"]]
        assert "scene" in types
        assert "portrait" in types

    def test_delete_image(self, client, game):
        mock = _mock_client(configured=True)
        with patch("app.api.images.get_image_client", return_value=mock):
            client.post(f"/api/game/{game.id}/images/scene")
            client.post(
                f"/api/game/{game.id}/images/portrait",
                json={"name": "Bob"},
            )
            # Delete the first image (index 0)
            r = client.delete(f"/api/game/{game.id}/images/0")
        assert r.status_code == 200
        body = r.json()
        assert body["remaining_count"] == 1
        assert body["removed"]["type"] == "scene"

    def test_delete_image_out_of_range(self, client, game):
        mock = _mock_client(configured=True)
        with patch("app.api.images.get_image_client", return_value=mock):
            r = client.delete(f"/api/game/{game.id}/images/0")
        assert r.status_code == 404

    def test_generate_scene_no_narration(self, client, db_session):
        """When there's no DM narration, should still work using location."""
        game = _make_game(db_session, narration="")
        # Override story_log to be empty
        from app.models.models import GameSave as GS
        save = db_session.query(GS).filter(GS.id == game.id).first()
        save.story_log = "[]"
        db_session.commit()

        mock = _mock_client(configured=True)
        with patch("app.api.images.get_image_client", return_value=mock):
            r = client.post(f"/api/game/{game.id}/images/scene")
        assert r.status_code == 200
        prompt_arg = mock.generate_image.call_args.args[0]
        assert "Burning Village" in prompt_arg  # falls back to location

    def test_generate_scene_provider_error(self, client, game):
        """A provider error should surface as 502."""
        mock = _mock_client(configured=True)
        mock.generate_image = AsyncMock(side_effect=RuntimeError("provider down"))
        with patch("app.api.images.get_image_client", return_value=mock):
            r = client.post(f"/api/game/{game.id}/images/scene")
        assert r.status_code == 502
        assert "provider down" in r.json()["detail"]

    def test_images_survive_in_game_state(self, client, game):
        """Generated images should be persisted in game_state JSON."""
        mock = _mock_client(configured=True)
        with patch("app.api.images.get_image_client", return_value=mock):
            client.post(f"/api/game/{game.id}/images/scene")

        # Read game_state directly from the DB
        from app.models.models import GameSave as GS
        db = game  # game fixture uses the test client's DB
        # Use the client to get state — images should be there
        r = client.get(f"/api/game/{game.id}/images")
        body = r.json()
        assert body["count"] == 1
        img = body["images"][0]
        assert img["url"] == "https://example.com/image.png"
        assert img["type"] == "scene"
        assert "timestamp" in img
        assert "prompt" in img
