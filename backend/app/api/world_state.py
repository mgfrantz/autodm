"""
World State API — manage NPC relationships and faction reputation.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine.world_state import (
    WorldState,
    NPCRelationship,
    FactionReputation,
    extract_world_state_from_game_state,
    merge_world_state_into_game_state,
)

router = APIRouter()


class UpdateNPCRelationshipRequest(BaseModel):
    """Request to update an NPC relationship."""
    npc_name: str
    trust_change: int  # -100 to 100
    interaction_summary: str


class UpdateFactionReputationRequest(BaseModel):
    """Request to update faction reputation."""
    faction_name: str
    reputation_change: int  # -100 to 100


class CompleteQuestRequest(BaseModel):
    """Request to complete a faction quest."""
    faction_name: str


class FailQuestRequest(BaseModel):
    """Request to fail a faction quest."""
    faction_name: str


class NPCRelationshipResponse(BaseModel):
    """Response with NPC relationship data."""
    npc_name: str
    attitude: str
    trust: int
    last_interacted: str
    interactions: list[str]


class FactionReputationResponse(BaseModel):
    """Response with faction reputation data."""
    faction_name: str
    standing: str
    reputation: int
    quests_completed: int
    quests_failed: int


class WorldStateResponse(BaseModel):
    """Response with full world state."""
    npc_relationships: dict[str, NPCRelationshipResponse]
    faction_reputation: dict[str, FactionReputationResponse]


def _npc_to_response(npc: NPCRelationship) -> NPCRelationshipResponse:
    """Convert NPCRelationship to response model."""
    return NPCRelationshipResponse(
        npc_name=npc.npc_name,
        attitude=npc.attitude,
        trust=npc.trust,
        last_interacted=npc.last_interacted,
        interactions=npc.interactions,
    )


def _faction_to_response(faction: FactionReputation) -> FactionReputationResponse:
    """Convert FactionReputation to response model."""
    return FactionReputationResponse(
        faction_name=faction.faction_name,
        standing=faction.standing,
        reputation=faction.reputation,
        quests_completed=faction.quests_completed,
        quests_failed=faction.quests_failed,
    )


@router.get("/{game_id}/world-state", response_model=WorldStateResponse)
def get_world_state(game_id: int, db: Session = Depends(get_db)):
    """Get the current world state (NPCs and factions)."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state = json.loads(save.game_state)
    world_state = extract_world_state_from_game_state(game_state)

    return WorldStateResponse(
        npc_relationships={
            name: _npc_to_response(npc)
            for name, npc in world_state.npc_relationships.items()
        },
        faction_reputation={
            name: _faction_to_response(faction)
            for name, faction in world_state.faction_reputation.items()
        },
    )


@router.post("/{game_id}/npcs", response_model=NPCRelationshipResponse)
def update_npc_relationship(
    game_id: int, request: UpdateNPCRelationshipRequest, db: Session = Depends(get_db)
):
    """Update a player's relationship with an NPC."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    # Validate trust_change bounds
    if not -100 <= request.trust_change <= 100:
        raise HTTPException(
            status_code=400,
            detail="trust_change must be between -100 and 100",
        )

    game_state = json.loads(save.game_state)
    world_state = extract_world_state_from_game_state(game_state)

    # Update the relationship
    npc = world_state.update_npc_relationship(
        npc_name=request.npc_name,
        trust_change=request.trust_change,
        interaction_summary=request.interaction_summary,
    )

    # Merge back into game state
    game_state = merge_world_state_into_game_state(game_state, world_state)
    save.game_state = json.dumps(game_state)
    save.updated_at = save.updated_at  # Trigger update
    db.commit()

    return _npc_to_response(npc)


@router.get("/{game_id}/npcs/{npc_name}", response_model=NPCRelationshipResponse)
def get_npc_relationship(game_id: int, npc_name: str, db: Session = Depends(get_db)):
    """Get a specific NPC relationship."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state = json.loads(save.game_state)
    world_state = extract_world_state_from_game_state(game_state)

    if npc_name not in world_state.npc_relationships:
        raise HTTPException(status_code=404, detail="NPC relationship not found")

    npc = world_state.npc_relationships[npc_name]
    return _npc_to_response(npc)


@router.post("/{game_id}/factions", response_model=FactionReputationResponse)
def update_faction_reputation(
    game_id: int,
    request: UpdateFactionReputationRequest,
    db: Session = Depends(get_db),
):
    """Update reputation with a faction."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    # Validate reputation_change bounds
    if not -100 <= request.reputation_change <= 100:
        raise HTTPException(
            status_code=400,
            detail="reputation_change must be between -100 and 100",
        )

    game_state = json.loads(save.game_state)
    world_state = extract_world_state_from_game_state(game_state)

    # Update the reputation
    faction = world_state.update_faction_reputation(
        faction_name=request.faction_name,
        reputation_change=request.reputation_change,
    )

    # Merge back into game state
    game_state = merge_world_state_into_game_state(game_state, world_state)
    save.game_state = json.dumps(game_state)
    save.updated_at = save.updated_at
    db.commit()

    return _faction_to_response(faction)


@router.get("/{game_id}/factions/{faction_name}", response_model=FactionReputationResponse)
def get_faction_reputation(game_id: int, faction_name: str, db: Session = Depends(get_db)):
    """Get a specific faction reputation."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state = json.loads(save.game_state)
    world_state = extract_world_state_from_game_state(game_state)

    if faction_name not in world_state.faction_reputation:
        raise HTTPException(status_code=404, detail="Faction reputation not found")

    faction = world_state.faction_reputation[faction_name]
    return _faction_to_response(faction)


@router.post("/{game_id}/quests/complete", response_model=FactionReputationResponse)
def complete_faction_quest(
    game_id: int, request: CompleteQuestRequest, db: Session = Depends(get_db)
):
    """Mark a faction quest as completed and adjust reputation."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state = json.loads(save.game_state)
    world_state = extract_world_state_from_game_state(game_state)

    faction = world_state.complete_faction_quest(request.faction_name)

    # Merge back into game state
    game_state = merge_world_state_into_game_state(game_state, world_state)
    save.game_state = json.dumps(game_state)
    save.updated_at = save.updated_at
    db.commit()

    return _faction_to_response(faction)


@router.post("/{game_id}/quests/fail", response_model=FactionReputationResponse)
def fail_faction_quest(
    game_id: int, request: FailQuestRequest, db: Session = Depends(get_db)
):
    """Mark a faction quest as failed and adjust reputation."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state = json.loads(save.game_state)
    world_state = extract_world_state_from_game_state(game_state)

    faction = world_state.fail_faction_quest(request.faction_name)

    # Merge back into game state
    game_state = merge_world_state_into_game_state(game_state, world_state)
    save.game_state = json.dumps(game_state)
    save.updated_at = save.updated_at
    db.commit()

    return _faction_to_response(faction)


@router.get("/{game_id}/world-state/summary")
def get_world_state_summary(game_id: int, db: Session = Depends(get_db)):
    """Get a text summary of world state for DM context."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state = json.loads(save.game_state)
    world_state = extract_world_state_from_game_state(game_state)

    npc_summary = world_state.get_npc_summary_for_context()
    faction_summary = world_state.get_faction_summary_for_context()
    flag_summary = world_state.get_flag_summary_for_context()

    return {
        "npc_summary": npc_summary,
        "faction_summary": faction_summary,
        "flag_summary": flag_summary,
    }