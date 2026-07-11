"""
Tests for the text-to-speech (voice narration) system — config, text
cleaning, client, and API. The TTS client is mocked (no real API calls) so
tests are fully deterministic.
"""
from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.llm.tts_config import TTSConfig, load_config
from app.llm.tts_client import (
    SpeechResult,
    TTSClient,
    TTSNotConfiguredError,
    clean_text_for_speech,
    get_tts_client,
    reset_tts_client,
)
from app.models.models import Character, World, GameSave


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _make_game(db_session, *, narration="The dragon swoops over the burning village. What do you do?"):
    char = Character(
        name="Soren", race="Human", char_class="Fighter", level=5,
        classes=json.dumps({"fighter": 5}),
        strength=16, dexterity=12, constitution=14, intelligence=10,
        wisdom=10, charisma=10,
        max_hp=45, current_hp=45, armor_class=16, speed=30, gold=500,
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


def _mock_speech_result(text="The dragon roars.") -> SpeechResult:
    return SpeechResult(
        audio=b"FAKE-MP3-BYTES",
        model="tts-1",
        voice="alloy",
        text=text,
        response_format="mp3",
        speed=1.0,
    )


def _mock_client(configured=True):
    """A mock TTS client that returns canned results without API calls."""
    client = MagicMock()
    client.is_configured = configured
    client.config = TTSConfig(
        provider="openai" if configured else "none",
        model="tts-1",
        api_key="test-key" if configured else "",
        voice="alloy",
        response_format="mp3",
        speed=1.0,
    )
    client.synthesize = AsyncMock(return_value=_mock_speech_result())
    return client


@pytest.fixture(autouse=True)
def _reset_client():
    """Reset the TTS client singleton between tests."""
    reset_tts_client()
    yield
    reset_tts_client()


# --------------------------------------------------------------------------- #
# Config tests
# --------------------------------------------------------------------------- #

class TestTTSConfig:
    def test_defaults(self):
        with patch.dict("os.environ", {}, clear=False):
            cfg = load_config()
            assert cfg.provider == "openai"
            assert cfg.model == "tts-1"
            assert cfg.voice == "alloy"
            assert cfg.response_format == "mp3"
            assert cfg.speed == 1.0

    def test_env_override(self):
        env = {
            "TTS_PROVIDER": "openai",
            "TTS_API_KEY": "sk-test-123",
            "TTS_MODEL": "tts-1-hd",
            "TTS_VOICE": "nova",
            "TTS_FORMAT": "opus",
            "TTS_SPEED": "1.5",
        }
        with patch.dict("os.environ", env, clear=False):
            cfg = load_config()
            assert cfg.api_key == "sk-test-123"
            assert cfg.model == "tts-1-hd"
            assert cfg.voice == "nova"
            assert cfg.response_format == "opus"
            assert cfg.speed == 1.5

    def test_fallback_to_llm_key(self):
        env = {"TTS_PROVIDER": "openai", "LLM_API_KEY": "sk-llm-key"}
        with patch.dict("os.environ", env, clear=True):
            cfg = load_config()
            assert cfg.api_key == "sk-llm-key"

    def test_speed_clamped_low(self):
        with patch.dict("os.environ", {"TTS_SPEED": "0.1"}, clear=False):
            assert load_config().speed == 0.25

    def test_speed_clamped_high(self):
        with patch.dict("os.environ", {"TTS_SPEED": "10"}, clear=False):
            assert load_config().speed == 4.0

    def test_speed_invalid_falls_back(self):
        with patch.dict("os.environ", {"TTS_SPEED": "not-a-number"}, clear=False):
            assert load_config().speed == 1.0

    def test_is_configured(self):
        assert TTSConfig(provider="openai", model="tts-1", api_key="key").is_configured is True

    def test_not_configured_no_key(self):
        assert TTSConfig(provider="openai", model="tts-1", api_key="").is_configured is False

    def test_not_configured_disabled(self):
        assert TTSConfig(provider="none", model="tts-1", api_key="key").is_configured is False


# --------------------------------------------------------------------------- #
# Text cleaning tests
# --------------------------------------------------------------------------- #

class TestCleanTextForSpeech:
    def test_strips_markdown(self):
        out = clean_text_for_speech("**Bold** and _italic_ and # heading.")
        assert "**" not in out
        assert "_" not in out
        assert "#" not in out
        assert "Bold" in out and "italic" in out

    def test_strips_dice_annotations(self):
        out = clean_text_for_speech("You swing [dex check: 14] and hit for [dmg: 8].")
        assert "dex check" not in out
        assert "dmg" not in out
        assert "You swing" in out and "hit" in out

    def test_strips_choice_lists(self):
        out = clean_text_for_speech(
            "You may:\n1. Attack the goblin\n2. Flee\n- Hide\n"
        )
        assert "1." not in out
        assert "2." not in out
        # the choice content is still readable, just the list markers removed
        assert "Attack the goblin" in out

    def test_strips_what_do_you_do(self):
        out = clean_text_for_speech("The door creaks open. What do you do?")
        assert "what do you do" not in out.lower()
        assert "door creaks open" in out

    def test_collapses_whitespace(self):
        out = clean_text_for_speech("The   fire\n\n  crackles .")
        assert "  " not in out
        assert "The fire crackles ." in out

    def test_truncates_long_text(self):
        out = clean_text_for_speech("A " * 5000)
        assert len(out) <= 4001  # margin for the ellipsis

    def test_empty_input(self):
        assert clean_text_for_speech("") == ""
        assert clean_text_for_speech("   ") == ""


# --------------------------------------------------------------------------- #
# TTSClient tests
# --------------------------------------------------------------------------- #

class TestTTSClient:
    def test_not_configured_raises(self):
        cfg = TTSConfig(provider="none", model="tts-1", api_key="")
        client = TTSClient(cfg)
        assert client.is_configured is False
        import asyncio
        with pytest.raises(TTSNotConfiguredError):
            asyncio.run(client.synthesize("hello"))

    def test_singleton(self):
        c1 = get_tts_client()
        c2 = get_tts_client()
        assert c1 is c2

    def test_reset(self):
        c1 = get_tts_client()
        reset_tts_client()
        c2 = get_tts_client()
        assert c1 is not c2

    def test_speech_result_audio_b64_roundtrip(self):
        result = SpeechResult(
            audio=b"abc", model="tts-1", voice="alloy", text="hi",
        )
        assert result.size_bytes == 3
        assert base64.b64decode(result.audio_b64) == b"abc"
        d = result.to_dict()
        assert d["audio_b64"] == result.audio_b64
        assert d["size_bytes"] == 3
        assert d["voice"] == "alloy"
        assert d["format"] == "mp3"

    @pytest.mark.asyncio
    async def test_synthesize_success(self):
        cfg = TTSConfig(provider="openai", model="tts-1", api_key="test-key")
        client = TTSClient(cfg)

        mock_openai = MagicMock()
        mock_response = MagicMock()
        mock_response.content = b"AUDIO-BYTES"
        mock_openai.audio.speech.create = AsyncMock(return_value=mock_response)
        client._client = mock_openai  # bypass lazy init

        result = await client.synthesize("The dragon **roars**.")
        assert result.audio == b"AUDIO-BYTES"
        assert result.model == "tts-1"
        assert result.voice == "alloy"
        assert result.response_format == "mp3"
        # markdown stripped in the cleaned text
        assert "**" not in result.text
        assert "roars" in result.text

        mock_openai.audio.speech.create.assert_called_once()
        call_kwargs = mock_openai.audio.speech.create.call_args.kwargs
        assert call_kwargs["model"] == "tts-1"
        assert call_kwargs["voice"] == "alloy"
        assert call_kwargs["response_format"] == "mp3"

    @pytest.mark.asyncio
    async def test_synthesize_custom_voice_and_format(self):
        cfg = TTSConfig(provider="openai", model="tts-1", api_key="key")
        client = TTSClient(cfg)

        mock_openai = MagicMock()
        mock_response = MagicMock()
        mock_response.content = b"X"
        mock_openai.audio.speech.create = AsyncMock(return_value=mock_response)
        client._client = mock_openai

        result = await client.synthesize("hi", voice="nova", response_format="opus", speed=1.25)
        assert result.voice == "nova"
        assert result.response_format == "opus"
        assert result.speed == 1.25
        call_kwargs = mock_openai.audio.speech.create.call_args.kwargs
        assert call_kwargs["voice"] == "nova"
        assert call_kwargs["response_format"] == "opus"
        assert call_kwargs["speed"] == 1.25

    @pytest.mark.asyncio
    async def test_synthesize_empty_after_cleaning_raises(self):
        cfg = TTSConfig(provider="openai", model="tts-1", api_key="key")
        client = TTSClient(cfg)
        with pytest.raises(ValueError):
            await client.synthesize("   ")


# --------------------------------------------------------------------------- #
# API tests
# --------------------------------------------------------------------------- #

class TestTTSAPI:
    def test_status_configured(self, client, game):
        mock = _mock_client(configured=True)
        with patch("app.api.tts.get_tts_client", return_value=mock):
            r = client.get(f"/api/game/{game.id}/tts/status")
        assert r.status_code == 200
        body = r.json()
        assert body["configured"] is True
        assert body["model"] == "tts-1"
        assert body["voice"] == "alloy"

    def test_status_not_configured(self, client, game):
        mock = _mock_client(configured=False)
        with patch("app.api.tts.get_tts_client", return_value=mock):
            r = client.get(f"/api/game/{game.id}/tts/status")
        assert r.status_code == 200
        assert r.json()["configured"] is False

    def test_status_game_not_found(self, client):
        r = client.get("/api/game/99999/tts/status")
        assert r.status_code == 404

    def test_synthesize_returns_audio_bytes(self, client, game):
        mock = _mock_client(configured=True)
        with patch("app.api.tts.get_tts_client", return_value=mock):
            r = client.post(
                f"/api/game/{game.id}/tts/synthesize",
                json={"text": "Hello world."},
            )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("audio/")
        assert r.content == b"FAKE-MP3-BYTES"
        mock.synthesize.assert_called_once()

    def test_synthesize_not_configured(self, client, game):
        mock = _mock_client(configured=False)
        with patch("app.api.tts.get_tts_client", return_value=mock):
            r = client.post(
                f"/api/game/{game.id}/tts/synthesize",
                json={"text": "hi"},
            )
        assert r.status_code == 503

    def test_synthesize_provider_error(self, client, game):
        mock = _mock_client(configured=True)
        mock.synthesize = AsyncMock(side_effect=RuntimeError("provider down"))
        with patch("app.api.tts.get_tts_client", return_value=mock):
            r = client.post(
                f"/api/game/{game.id}/tts/synthesize",
                json={"text": "hi"},
            )
        assert r.status_code == 502
        assert "provider down" in r.json()["detail"]

    def test_narrate_success_caches(self, client, game):
        mock = _mock_client(configured=True)
        with patch("app.api.tts.get_tts_client", return_value=mock):
            r = client.post(f"/api/game/{game.id}/tts/narrate", json={})
        assert r.status_code == 200
        body = r.json()
        assert body["cached_count"] == 1
        entry = body["audio"]
        assert entry["label"] == "Latest Narration"
        assert entry["voice"] == "alloy"
        assert "audio_b64" not in entry  # public entry omits bytes
        assert "id" in entry
        # synthesize was called with the cleaned narration (markdown/choices stripped)
        mock.synthesize.assert_called_once()
        text_arg = mock.synthesize.call_args.args[0]
        assert "dragon" in text_arg.lower()
        assert "what do you do" not in text_arg.lower()

    def test_narrate_with_explicit_text(self, client, game):
        mock = _mock_client(configured=True)
        with patch("app.api.tts.get_tts_client", return_value=mock):
            r = client.post(
                f"/api/game/{game.id}/tts/narrate",
                json={"text": "A custom line to speak."},
            )
        assert r.status_code == 200
        text_arg = mock.synthesize.call_args.args[0]
        assert "custom line" in text_arg

    def test_narrate_no_narration(self, client, db_session):
        game = _make_game(db_session, narration="")
        from app.models.models import GameSave as GS
        save = db_session.query(GS).filter(GS.id == game.id).first()
        save.story_log = "[]"
        db_session.commit()

        mock = _mock_client(configured=True)
        with patch("app.api.tts.get_tts_client", return_value=mock):
            r = client.post(f"/api/game/{game.id}/tts/narrate", json={})
        assert r.status_code == 422

    def test_narrate_not_configured(self, client, game):
        mock = _mock_client(configured=False)
        with patch("app.api.tts.get_tts_client", return_value=mock):
            r = client.post(f"/api/game/{game.id}/tts/narrate", json={})
        assert r.status_code == 503

    def test_get_audio_bytes(self, client, game):
        mock = _mock_client(configured=True)
        with patch("app.api.tts.get_tts_client", return_value=mock):
            narrate = client.post(f"/api/game/{game.id}/tts/narrate", json={}).json()
            audio_id = narrate["audio"]["id"]
            r = client.get(f"/api/game/{game.id}/tts/audio/{audio_id}")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("audio/")
        assert r.content == b"FAKE-MP3-BYTES"

    def test_get_audio_not_found(self, client, game):
        r = client.get(f"/api/game/{game.id}/tts/audio/does-not-exist")
        assert r.status_code == 404

    def test_list_audio_empty(self, client, game):
        mock = _mock_client(configured=True)
        with patch("app.api.tts.get_tts_client", return_value=mock):
            r = client.get(f"/api/game/{game.id}/tts")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 0
        assert body["audio"] == []

    def test_list_audio_after_narration(self, client, game):
        mock = _mock_client(configured=True)
        with patch("app.api.tts.get_tts_client", return_value=mock):
            client.post(f"/api/game/{game.id}/tts/narrate", json={})
            client.post(f"/api/game/{game.id}/tts/narrate", json={})
            r = client.get(f"/api/game/{game.id}/tts")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 2
        # No audio bytes in listing
        for entry in body["audio"]:
            assert "audio_b64" not in entry

    def test_delete_audio(self, client, game):
        mock = _mock_client(configured=True)
        with patch("app.api.tts.get_tts_client", return_value=mock):
            narrate = client.post(f"/api/game/{game.id}/tts/narrate", json={}).json()
            audio_id = narrate["audio"]["id"]
            r = client.delete(f"/api/game/{game.id}/tts/{audio_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["remaining_count"] == 0
        assert "audio_b64" not in body["removed"]

    def test_delete_audio_not_found(self, client, game):
        r = client.delete(f"/api/game/{game.id}/tts/missing-id")
        assert r.status_code == 404

    def test_audio_survives_in_game_state(self, client, game):
        mock = _mock_client(configured=True)
        with patch("app.api.tts.get_tts_client", return_value=mock):
            client.post(f"/api/game/{game.id}/tts/narrate", json={})
            listing = client.get(f"/api/game/{game.id}/tts").json()
        assert listing["count"] == 1
        entry = listing["audio"][0]
        assert entry["voice"] == "alloy"
        assert entry["label"] == "Latest Narration"
        assert "timestamp" in entry
