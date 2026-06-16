"""
Navigation API — region map exploration and overland travel.

Exposes the navigation engine over REST. The map layout (coordinates,
connections, terrain) is derived deterministically from the world data, so only
the player's position is persisted in the game state.
"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine.navigation import WorldMap

router = APIRouter()


class TravelRequest(BaseModel):
    """Request to travel to a connected region."""
    region_id: str


def _load_map(db: Session, game_id: int) -> tuple[GameSave, WorldMap]:
    """Load a game save and build its current world map."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    world_data = json.loads(save.world.world_data)
    game_state = json.loads(save.game_state)
    world_map = WorldMap.from_world_data(world_data, game_state)
    return save, world_map


@router.get("/{game_id}/map")
def get_map(game_id: int, db: Session = Depends(get_db)):
    """Return the full world map: regions, connections, and player position."""
    _, world_map = _load_map(db, game_id)
    return world_map.to_dict()


@router.get("/{game_id}/regions")
def list_regions(game_id: int, db: Session = Depends(get_db)):
    """Return the regions of this game's world with visitation status."""
    _, world_map = _load_map(db, game_id)
    reachable = set(world_map.reachable_region_ids())
    discovered = set(world_map.discovered_region_ids())
    return {
        "current_region_id": world_map.current_region_id,
        "discovered_region_ids": world_map.discovered_region_ids(),
        "regions": [
            {
                **node.to_dict(),
                "visited": world_map.is_visited(node.id),
                "reachable": node.id in reachable,
                "discovered": node.id in discovered,
                "current": node.id == world_map.current_region_id,
            }
            for node in world_map.regions.values()
        ],
    }


@router.post("/{game_id}/travel")
def travel(game_id: int, request: TravelRequest, db: Session = Depends(get_db)):
    """Travel from the current region to a connected one.

    Updates the saved game state (current region, visited regions, and the
    human-readable ``location`` used elsewhere in the UI). Returns the travel
    outcome including any random encounter that occurred en route.
    """
    save, world_map = _load_map(db, game_id)

    if request.region_id not in world_map.regions:
        raise HTTPException(status_code=404, detail=f"Region '{request.region_id}' not found")

    result = world_map.travel(request.region_id)

    # Persist updated position regardless of success (a failed move doesn't
    # change state, but we keep the write cheap and consistent).
    if result.success:
        game_state = json.loads(save.game_state)
        game_state.update(world_map.to_game_state())
        game_state["location"] = result.to_region.name if result.to_region else game_state.get("location")
        visited_locations = set(game_state.get("visited_locations", []))
        if result.to_region:
            visited_locations.add(result.to_region.name)
            for settlement in result.to_region.settlements:
                visited_locations.add(settlement)
        game_state["visited_locations"] = sorted(visited_locations)
        save.game_state = json.dumps(game_state)
        save.updated_at = datetime.utcnow()
        db.commit()

    return result.to_dict()
