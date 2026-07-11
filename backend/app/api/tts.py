"""
TTS API — AI-generated voice narration for the DM.

This router provides a provider-agnostic text-to-speech layer over the
``TTSClient``. When no TTS provider key is configured, endpoints return
HTTP 503 so the frontend can show a graceful "not configured" state instead
of an error.

Generated audio is cached (base64-encoded) in ``game_state["audio"]`` so it
survives save/load and can be replayed from an in-game voice panel.

Endpoints (mounted under /api/game):
- GET  /{game_id}/tts/status
      Whether TTS is configured + model/voice/format info.
- POST /{game_id}/tts/synthesize
      Synthesize arbitrary text → raw audio bytes (audio/mpeg response).
- POST /{game_id}/tts/narrate
      Synthesize the latest DM narration, cache it, return metadata.
- GET  /{game_id}/tts/audio/{audio_id}
      Serve a cached narration's raw audio bytes.
- GET  /{game_id}/tts
      List cached narrations for this game (metadata only — no audio bytes).
- DELETE /{game_id}/tts/{audio_id}
      Remove a cached narration.
"""
from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.llm.tts_client import (
    TTSNotConfiguredError,
    SpeechResult,
    clean_text_for_speech,
    get_tts_client,
)

router = APIRouter()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _load_game(db: Session, game_id: int) -> GameSave:
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")
    return save


def _game_state(save: GameSave) -> dict:
    try:
        return json.loads(save.game_state)
    except (json.JSONDecodeError, TypeError):
        return {}


def _persist(save: GameSave, game_state: dict, db: Session) -> None:
    save.game_state = json.dumps(game_state)
    save.updated_at = datetime.utcnow()
    db.commit()


def _story_log(save: GameSave) -> list[dict]:
    try:
        return json.loads(save.story_log)
    except (json.JSONDecodeError, TypeError):
        return []


def _latest_dm_narration(story_log: list[dict]) -> str:
    """Return the most recent DM narration entry, or empty string."""
    for entry in reversed(story_log):
        if entry.get("role") in ("dm", "assistant") and entry.get("content"):
            return entry["content"]
    return ""


def _audio_list(game_state: dict) -> list[dict[str, Any]]:
    """Get (or init) the cached audio list from game_state."""
    audio = game_state.get("audio")
    if not isinstance(audio, list):
        audio = []
    return audio


def _public_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Strip the heavy base64 payload for listing/status responses."""
    return {k: v for k, v in entry.items() if k != "audio_b64"}


def _cache_speech(
    game_state: dict,
    result: SpeechResult,
    *,
    label: str,
    voice: str,
) -> dict[str, Any]:
    """Append a synthesized narration to the game_state cache and return it."""
    entry: dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "label": label,
        "text": result.text,
        "voice": voice,
        "model": result.model,
        "format": result.response_format,
        "speed": result.speed,
        "size_bytes": result.size_bytes,
        "timestamp": datetime.utcnow().isoformat(),
        "audio_b64": result.audio_b64,
    }
    audio = _audio_list(game_state)
    audio.append(entry)
    game_state["audio"] = audio
    return entry


def _not_configured() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            "Voice narration (TTS) is not configured. Set TTS_API_KEY in your "
            ".env (or TTS_PROVIDER=none to suppress this)."
        ),
    )


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #

class SynthesizeRequest(BaseModel):
    """Synthesize arbitrary text to speech (one-shot, not cached)."""
    text: str = Field(..., description="The text to speak aloud.")
    voice: Optional[str] = Field(
        default=None,
        description="Override the configured voice (e.g. alloy, nova, onyx).",
    )


class NarrateRequest(BaseModel):
    """Synthesize (and cache) the latest DM narration."""
    voice: Optional[str] = Field(
        default=None,
        description="Override the configured voice.",
    )
    text: Optional[str] = Field(
        default=None,
        description="Optional explicit text; defaults to the latest DM narration.",
    )


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("/{game_id}/tts/status")
def get_tts_status(game_id: int, db: Session = Depends(get_db)):
    """Report whether voice narration is available and with what settings."""
    _load_game(db, game_id)  # validate game exists
    client = get_tts_client()
    cfg = client.config
    return {
        "configured": client.is_configured,
        "provider": cfg.provider,
        "model": cfg.model,
        "voice": cfg.voice,
        "format": cfg.response_format,
        "speed": cfg.speed,
    }


@router.post("/{game_id}/tts/synthesize")
async def synthesize_speech(
    game_id: int,
    request: SynthesizeRequest,
    db: Session = Depends(get_db),
):
    """Synthesize arbitrary text to speech and return raw audio bytes.

    Returns an ``audio/mpeg`` (or configured format) binary response. This is a
    one-shot synthesis — the audio is NOT cached. Use ``/tts/narrate`` to cache.
    """
    _load_game(db, game_id)
    client = get_tts_client()
    if not client.is_configured:
        raise _not_configured()

    cleaned = clean_text_for_speech(request.text)
    if not cleaned:
        raise HTTPException(
            status_code=422,
            detail="No speakable text after cleaning.",
        )

    try:
        result = await client.synthesize(cleaned, voice=request.voice)
    except TTSNotConfiguredError:
        raise _not_configured()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Speech synthesis failed: {exc}")

    media_type = f"audio/{result.response_format}"
    return Response(content=result.audio, media_type=media_type)


@router.post("/{game_id}/tts/narrate")
async def narrate_latest(
    game_id: int,
    request: NarrateRequest,
    db: Session = Depends(get_db),
):
    """Synthesize the latest DM narration (or explicit text), cache it, and
    return metadata. The audio itself is served by ``GET /tts/audio/{id}``.
    """
    save = _load_game(db, game_id)
    client = get_tts_client()
    if not client.is_configured:
        raise _not_configured()

    text = request.text or ""
    if not text:
        story_log = _story_log(save)
        text = _latest_dm_narration(story_log)
    if not text:
        raise HTTPException(
            status_code=422,
            detail="No narration to speak. Take an action first, or pass text.",
        )

    cleaned = clean_text_for_speech(text)
    if not cleaned:
        raise HTTPException(
            status_code=422,
            detail="No speakable text after cleaning.",
        )

    try:
        result = await client.synthesize(cleaned, voice=request.voice)
    except TTSNotConfiguredError:
        raise _not_configured()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Speech synthesis failed: {exc}")

    game_state = _game_state(save)
    voice = request.voice or client.config.voice
    label = "Latest Narration"
    entry = _cache_speech(game_state, result, label=label, voice=voice)
    _persist(save, game_state, db)
    return {"audio": _public_entry(entry), "cached_count": len(_audio_list(game_state))}


@router.get("/{game_id}/tts/audio/{audio_id}")
def get_audio_bytes(game_id: int, audio_id: str, db: Session = Depends(get_db)):
    """Serve the raw audio bytes for a cached narration by its id."""
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    for entry in _audio_list(game_state):
        if entry.get("id") == audio_id:
            b64 = entry.get("audio_b64") or ""
            try:
                audio = base64.b64decode(b64) if b64 else b""
            except (ValueError, TypeError):
                audio = b""
            fmt = entry.get("format") or "mp3"
            return Response(content=audio, media_type=f"audio/{fmt}")
    raise HTTPException(status_code=404, detail="Cached narration not found")


@router.get("/{game_id}/tts")
def list_audio(game_id: int, db: Session = Depends(get_db)):
    """List cached narrations for this game (metadata only — no audio bytes)."""
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    audio = _audio_list(game_state)
    return {
        "audio": [_public_entry(e) for e in audio],
        "count": len(audio),
        "configured": get_tts_client().is_configured,
    }


@router.delete("/{game_id}/tts/{audio_id}")
def delete_audio(game_id: int, audio_id: str, db: Session = Depends(get_db)):
    """Remove a cached narration by its id."""
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    audio = _audio_list(game_state)
    for i, entry in enumerate(audio):
        if entry.get("id") == audio_id:
            removed = audio.pop(i)
            game_state["audio"] = audio
            _persist(save, game_state, db)
            return {"removed": _public_entry(removed), "remaining_count": len(audio)}
    raise HTTPException(status_code=404, detail="Cached narration not found")
