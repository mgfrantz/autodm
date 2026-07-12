"""
Starter adventures API — browse curated adventures and launch one.

Curated adventures are hand-authored worlds that work without an LLM key.
The ``/start`` endpoint creates a :class:`World` row (identical schema to
an LLM-generated world) so the rest of the game pipeline — ``/game/create``,
``/game/{id}/start``, combat, navigation — is completely unchanged.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import World
from app.engine.adventures import (
    list_adventures,
    get_adventure,
    world_data_for,
)

router = APIRouter()


class AdventureSummary(BaseModel):
    id: str
    name: str
    tagline: str
    blurb: str
    tone: str
    recommended_level: int
    tags: list[str]


class AdventureDetail(AdventureSummary):
    world_data: dict


class StartAdventureRequest(BaseModel):
    adventure_id: str
    name: str | None = None  # Optional override for the World name


@router.get("/", response_model=list[AdventureSummary])
def list_all_adventures():
    """List all curated starter adventures (lightweight, no world payload)."""
    return [AdventureSummary(**a.to_dict(include_world_data=False)) for a in list_adventures()]


@router.get("/{adventure_id}", response_model=AdventureDetail)
def get_adventure_detail(adventure_id: str):
    """Get full details for a single adventure including the world payload."""
    adv = get_adventure(adventure_id)
    if adv is None:
        raise HTTPException(status_code=404, detail="Starter adventure not found")
    return AdventureDetail(**adv.to_dict(include_world_data=True))


@router.post("/start")
def start_starter_adventure(
    request: StartAdventureRequest, db: Session = Depends(get_db)
):
    """Create a :class:`World` row from a curated adventure.

    Returns ``{"world_id": int}`` which the frontend passes to
    ``POST /game/create`` — identical to the LLM-generated flow. This makes
    curated adventures a drop-in alternative to ``POST /world/generate``.
    """
    adv = get_adventure(request.adventure_id)
    if adv is None:
        raise HTTPException(status_code=404, detail="Starter adventure not found")

    world_data = world_data_for(request.adventure_id)
    # world_data_for never returns None here (adv was found), but be safe.
    if world_data is None:
        raise HTTPException(status_code=500, detail="Adventure world data missing")

    import json

    world = World(
        name=request.name or world_data.get("name", adv.name),
        description=world_data.get("description", ""),
        world_data=json.dumps(world_data),
        tone=world_data.get("tone", adv.tone),
    )
    db.add(world)
    db.commit()
    db.refresh(world)
    return {"world_id": world.id}
