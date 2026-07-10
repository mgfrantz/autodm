"""
Images API — AI-generated scene & NPC portrait images.

This router provides a provider-agnostic image-generation layer over the
``ImageClient`` (which mirrors the LLM orchestrator pattern). When no image
provider key is configured, endpoints return HTTP 503 so the frontend can show
a graceful "not configured" state instead of an error.

Generated images are cached in ``game_state["images"]`` so they survive
save/load and can be browsed in an in-game gallery.

Endpoints (mounted under /api/game):
- GET  /{game_id}/images/status
      Whether image generation is configured + model/size info.
- POST /{game_id}/images/scene
      Generate a scene illustration from the latest DM narration.
- POST /{game_id}/images/portrait
      Generate an NPC/character portrait from a name + description.
- GET  /{game_id}/images
      List all cached images for this game.
- DELETE /{game_id}/images/{image_index}
      Remove a cached image from the gallery.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.llm.image_client import (
    ImageNotConfiguredError,
    ImageResult,
    build_portrait_prompt,
    build_scene_prompt,
    get_image_client,
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


def _images(game_state: dict) -> list[dict[str, Any]]:
    """Get (or init) the cached images list from game_state."""
    images = game_state.get("images")
    if not isinstance(images, list):
        images = []
    return images


def _cache_image(
    game_state: dict,
    result: ImageResult,
    *,
    image_type: str,
    label: str,
) -> dict[str, Any]:
    """Append a generated image to the game_state cache and return the entry."""
    entry: dict[str, Any] = {
        "type": image_type,
        "label": label,
        "prompt": result.prompt,
        "revised_prompt": result.revised_prompt,
        "url": result.url,
        "model": result.model,
        "size": result.size,
        "quality": result.quality,
        "timestamp": datetime.utcnow().isoformat(),
    }
    images = _images(game_state)
    images.append(entry)
    game_state["images"] = images
    return entry


def _not_configured() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            "Image generation is not configured. Set IMAGE_API_KEY in your "
            ".env (or IMAGE_PROVIDER=none to suppress this)."
        ),
    )


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #

class PortraitRequest(BaseModel):
    """Generate an NPC or character portrait."""
    name: str = Field(..., description="The character/NPC name.")
    description: str = Field(
        default="",
        description="Visual description — appearance, clothing, expression.",
    )
    race: str = Field(default="", description="Optional race for context.")
    char_class: str = Field(default="", description="Optional class for context.")


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("/{game_id}/images/status")
def get_image_status(game_id: int, db: Session = Depends(get_db)):
    """Report whether image generation is available and with what settings."""
    _load_game(db, game_id)  # validate game exists
    client = get_image_client()
    cfg = client.config
    return {
        "configured": client.is_configured,
        "provider": cfg.provider,
        "model": cfg.model,
        "size": cfg.size,
        "quality": cfg.quality,
    }


@router.post("/{game_id}/images/scene")
async def generate_scene_image(game_id: int, db: Session = Depends(get_db)):
    """Generate a scene illustration from the latest DM narration.

    Builds a visual prompt from the most recent DM narration + character/location
    context, calls the image provider, and caches the result in game_state.
    """
    save = _load_game(db, game_id)
    client = get_image_client()
    if not client.is_configured:
        raise _not_configured()

    game_state = _game_state(save)
    story_log = _story_log(save)
    narration = _latest_dm_narration(story_log)
    char = save.character

    prompt = build_scene_prompt(
        narration,
        location=game_state.get("location", ""),
        character_name=char.name,
        character_race=char.race,
        character_class=char.char_class,
    )

    try:
        result = await client.generate_image(prompt)
    except ImageNotConfiguredError:
        raise _not_configured()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Image generation failed: {exc}",
        )

    label = game_state.get("location") or "Current Scene"
    entry = _cache_image(game_state, result, image_type="scene", label=label)
    _persist(save, game_state, db)
    return {"image": entry, "cached_count": len(_images(game_state))}


@router.post("/{game_id}/images/portrait")
async def generate_portrait(
    game_id: int,
    request: PortraitRequest,
    db: Session = Depends(get_db),
):
    """Generate an NPC or character portrait from a name + description."""
    _load_game(db, game_id)
    client = get_image_client()
    if not client.is_configured:
        raise _not_configured()

    prompt = build_portrait_prompt(
        request.name,
        request.description,
        race=request.race,
        char_class=request.char_class,
    )

    try:
        result = await client.generate_image(prompt)
    except ImageNotConfiguredError:
        raise _not_configured()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Image generation failed: {exc}",
        )

    # Persist to game_state
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    entry = _cache_image(
        game_state, result, image_type="portrait", label=request.name
    )
    _persist(save, game_state, db)
    return {"image": entry, "cached_count": len(_images(game_state))}


@router.get("/{game_id}/images")
def list_images(game_id: int, db: Session = Depends(get_db)):
    """List all cached images for this game (gallery)."""
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    images = _images(game_state)
    return {
        "images": images,
        "count": len(images),
        "configured": get_image_client().is_configured,
    }


@router.delete("/{game_id}/images/{image_index}")
def delete_image(
    game_id: int,
    image_index: int,
    db: Session = Depends(get_db),
):
    """Remove a cached image from the gallery by its 0-based index."""
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    images = _images(game_state)
    if image_index < 0 or image_index >= len(images):
        raise HTTPException(status_code=404, detail="Image index out of range")
    removed = images.pop(image_index)
    game_state["images"] = images
    _persist(save, game_state, db)
    return {"removed": removed, "remaining_count": len(images)}
