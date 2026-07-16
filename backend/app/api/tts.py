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
from app.utils.time_utils import utcnow
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.llm.tts_client import (
    TTSNotConfiguredError,
    SpeechResult,
    clean_text_for_speech,
    chunk_text_for_speech,
    get_tts_client,
)
from app.llm.tts_config import (
    DEFAULT_VOICE,
    is_valid_voice,
    voices_as_dicts,
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
    save.updated_at = utcnow()
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
    cache_enabled: bool = True,
) -> Optional[dict[str, Any]]:
    """Append a synthesized narration to the game_state cache (if enabled) and return it.

    When caching is disabled, returns None (no entry added to game_state).
    """
    if not cache_enabled:
        return None

    entry: dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "label": label,
        "text": result.text,
        "voice": voice,
        "model": result.model,
        "format": result.response_format,
        "speed": result.speed,
        "size_bytes": result.size_bytes,
        "timestamp": utcnow().isoformat(),
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
            "Voice narration (TTS) is not configured. "
            "Set TTS_API_KEY (cloud), TTS_PROVIDER=mlx (local, Apple Silicon), "
            "or TTS_PROVIDER=none to disable."
        ),
    )


# --------------------------------------------------------------------------- #
# NPC voice-mapping helpers
# --------------------------------------------------------------------------- #

def _npc_voices(game_state: dict) -> dict[str, str]:
    """Get (or init) the NPC→voice map stored in game_state.

    Stored as ``game_state["npc_voices"]`` — a ``{npc_name: voice_id}`` dict.
    Keys are stored with a canonical (stripped, title-cased) form so lookups
    are case-insensitive against the DM's narration.
    """
    voices = game_state.get("npc_voices")
    if not isinstance(voices, dict):
        voices = {}
    return voices


def _canonical_npc(name: str) -> str:
    """Normalise an NPC name for storage/lookup (strip + title case)."""
    return (name or "").strip().title()


def resolve_voice_for_npc(
    game_state: dict, npc: Optional[str], explicit: Optional[str]
) -> str:
    """Resolve which voice to use when narrating for an NPC.

    Precedence: an explicit ``explicit`` override > the NPC's mapped voice >
    the configured default voice.
    """
    if explicit:
        return explicit
    if npc:
        voices = _npc_voices(game_state)
        mapped = voices.get(_canonical_npc(npc))
        if mapped:
            return mapped
    return get_tts_client().config.voice or DEFAULT_VOICE


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
    npc: Optional[str] = Field(
        default=None,
        description=(
            "An NPC name whose mapped voice should be used (ignored when "
            "`voice` is also given). Resolved from the NPC voice map."
        ),
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
        "cache_audio": cfg.cache_audio,
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
        game_state = _game_state(save)
        # Resolve the voice: explicit override > NPC's mapped voice > default.
        voice = resolve_voice_for_npc(game_state, request.npc, request.voice)
        result = await client.synthesize(cleaned, voice=voice)
    except TTSNotConfiguredError:
        raise _not_configured()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Speech synthesis failed: {exc}")

    label = f"{request.npc.strip().title()} Speaks" if request.npc else "Latest Narration"
    entry = _cache_speech(
        game_state,
        result,
        label=label,
        voice=voice,
        cache_enabled=client.config.cache_audio,
    )

    if entry:
        # Caching enabled: persist and return metadata
        _persist(save, game_state, db)
        return {
            "audio": _public_entry(entry),
            "cached_count": len(_audio_list(game_state)),
            "cached": True,
        }
    else:
        # Caching disabled: return audio bytes directly
        media_type = f"audio/{result.response_format}"
        return Response(content=result.audio, media_type=media_type)


@router.post("/{game_id}/tts/narrate/stream")
async def narrate_latest_stream(
    game_id: int,
    request: NarrateRequest,
    db: Session = Depends(get_db),
):
    """Stream the latest DM narration in audio chunks (SSE).

    Like ``/tts/narrate``, but streams audio chunks as they're synthesized
    so playback can start before the full narration is complete. The text is
    split into sentence-ish chunks (max ~800 chars each), each synthesized
    independently, and emitted as Server-Sent Events.

    SSE event format:
      - ``data: {"index": 0, "audio_b64": "...", "text": "..."}`` for each chunk
      - ``event: done data: {"audio_id": "...", "total_chunks": N, ...}`` when complete
      - ``event: error data: {"message": "..."}`` on failure

    The full audio is cached (concatenating all chunks) at the end, so the
    narration can be replayed from the cache.
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

    async def event_stream():
        try:
            game_state = _game_state(save)
            voice = resolve_voice_for_npc(game_state, request.npc, request.voice)
            chunks = chunk_text_for_speech(cleaned)

            if not chunks:
                err_msg = json.dumps({"message": "No speech chunks generated."})
                yield f"event: error\ndata: {err_msg}\n\n"
                return

            # Synthesize each chunk and stream it
            all_audio_parts = []
            async for idx, result in client.synthesize_chunks(chunks, voice=voice):
                all_audio_parts.append(result.audio)
                chunk_event = {
                    "index": idx,
                    "audio_b64": result.audio_b64,
                    "text": result.text,
                }
                yield f"data: {json.dumps(chunk_event)}\n\n"

            # Concatenate all chunks into full audio
            full_audio = b"".join(all_audio_parts)
            full_result = SpeechResult(
                audio=full_audio,
                model=client.config.model,
                voice=voice,
                text=cleaned,
                response_format=client.config.response_format,  # Use the actual format (wav for mlx)
                speed=client.config.speed,
            )

            # Cache the full audio (if enabled)
            label = f"{request.npc.strip().title()} Speaks" if request.npc else "Latest Narration"
            entry = _cache_speech(
                game_state,
                full_result,
                label=label,
                voice=voice,
                cache_enabled=client.config.cache_audio,
            )

            if entry:
                _persist(save, game_state, db)
                # Emit completion event with cached metadata
                done_event = {
                    "audio_id": entry["id"],
                    "total_chunks": len(chunks),
                    "label": entry["label"],
                    "size_bytes": entry["size_bytes"],
                    "voice": entry["voice"],
                    "cached": True,
                }
            else:
                # Emit completion event without cache metadata
                done_event = {
                    "total_chunks": len(chunks),
                    "cached": False,
                }
            yield f"event: done\ndata: {json.dumps(done_event)}\n\n"

        except TTSNotConfiguredError:
            err_msg = json.dumps({"message": "Voice narration not configured."})
            yield f"event: error\ndata: {err_msg}\n\n"
        except ValueError as exc:
            err_msg = json.dumps({"message": str(exc)})
            yield f"event: error\ndata: {err_msg}\n\n"
        except Exception as exc:
            err_msg = json.dumps({"message": f"Speech synthesis failed: {str(exc)}"})
            yield f"event: error\ndata: {err_msg}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")



@router.get("/{game_id}/tts/audio/{audio_id}")
def get_audio_bytes(game_id: int, audio_id: str, db: Session = Depends(get_db)):
    """Serve the raw audio bytes for a cached narration by its id.

    Returns 404 when caching is disabled or the audio_id is not found.
    """
    client = get_tts_client()
    if not client.config.cache_audio:
        raise HTTPException(
            status_code=404,
            detail="Audio caching is disabled for this TTS provider.",
        )

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
    """List cached narrations for this game (metadata only — no audio bytes).

    Returns empty list when caching is disabled.
    """
    client = get_tts_client()
    if not client.config.cache_audio:
        return {
            "audio": [],
            "count": 0,
            "configured": client.is_configured,
            "cached": False,
        }

    save = _load_game(db, game_id)
    game_state = _game_state(save)
    audio = _audio_list(game_state)
    return {
        "audio": [_public_entry(e) for e in audio],
        "count": len(audio),
        "configured": client.is_configured,
        "cached": True,
    }


@router.delete("/{game_id}/tts/{audio_id}")
def delete_audio(game_id: int, audio_id: str, db: Session = Depends(get_db)):
    """Remove a cached narration by its id.

    Returns 404 when caching is disabled or the audio_id is not found.
    """
    client = get_tts_client()
    if not client.config.cache_audio:
        raise HTTPException(
            status_code=404,
            detail="Audio caching is disabled for this TTS provider.",
        )

    save = _load_game(db, game_id)
    game_state = _game_state(save)
    audio = _audio_list(game_state)
    for i, entry in enumerate(audio):
        if entry.get("id") == audio_id:
            removed = audio.pop(i)
            game_state["audio"] = audio
            _persist(save, game_state, db)
            return {
                "removed": _public_entry(removed),
                "remaining_count": len(audio),
            }
    raise HTTPException(status_code=404, detail="Cached narration not found")


# --------------------------------------------------------------------------- #
# Voice registry + per-NPC voice mapping
# --------------------------------------------------------------------------- #
#
# Lets the player assign a distinct TTS voice to named NPCs so dialogue is
# spoken in-character. The map is stored in ``game_state["npc_voices"]`` as a
# ``{canonical_npc_name: voice_id}`` dict, so it survives save/load.

@router.get("/{game_id}/tts/voices")
def list_voices(game_id: int, db: Session = Depends(get_db)):
    """List the available TTS voices plus the configured default.

    Works whether or not TTS is configured — the voice list is static and
    useful for the UI even before a key is set. ``configured`` tells the
    client whether synthesis will actually work. Voices are provider-specific.
    """
    _load_game(db, game_id)  # validate game exists
    client = get_tts_client()
    return {
        "voices": voices_as_dicts(provider=client.config.provider),
        "default": client.config.voice or DEFAULT_VOICE,
        "configured": client.is_configured,
        "provider": client.config.provider,
    }


@router.get("/{game_id}/tts/npc-voices")
def get_npc_voices(game_id: int, db: Session = Depends(get_db)):
    """Return the per-NPC voice assignments for this game."""
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    voices = _npc_voices(game_state)
    return {
        "npc_voices": voices,
        "count": len(voices),
        "default_voice": get_tts_client().config.voice or DEFAULT_VOICE,
    }


class NPCVoiceRequest(BaseModel):
    """Assign (or update) a voice for a named NPC."""
    npc: str = Field(..., description="The NPC name (case-insensitive).")
    voice: str = Field(..., description="A voice id from the available voices.")


@router.post("/{game_id}/tts/npc-voices")
def set_npc_voice(
    game_id: int, request: NPCVoiceRequest, db: Session = Depends(get_db)
):
    """Assign or update a voice for an NPC. Persists to game_state."""
    npc = _canonical_npc(request.npc)
    if not npc:
        raise HTTPException(status_code=422, detail="NPC name is required.")

    client = get_tts_client()
    if not is_valid_voice(request.voice, provider=client.config.provider):
        raise HTTPException(
            status_code=422,
            detail=f"Unknown voice '{request.voice}'. Use GET /tts/voices.",
        )

    save = _load_game(db, game_id)
    game_state = _game_state(save)
    voices = _npc_voices(game_state)
    voices[npc] = request.voice
    game_state["npc_voices"] = voices
    _persist(save, game_state, db)
    return {
        "npc": npc,
        "voice": request.voice,
        "npc_voices": voices,
        "count": len(voices),
    }


@router.delete("/{game_id}/tts/npc-voices/{npc}")
def delete_npc_voice(game_id: int, npc: str, db: Session = Depends(get_db)):
    """Remove an NPC's voice assignment (falls back to the default voice)."""
    canonical = _canonical_npc(npc)
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    voices = _npc_voices(game_state)
    if canonical not in voices:
        raise HTTPException(
            status_code=404,
            detail=f"No voice assigned to '{canonical}'.",
        )
    removed = voices.pop(canonical)
    game_state["npc_voices"] = voices
    _persist(save, game_state, db)
    return {
        "npc": canonical,
        "removed_voice": removed,
        "npc_voices": voices,
        "count": len(voices),
    }
