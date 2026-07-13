"""
Quest Log API — manage player quests detected from DM narration.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine.quests import (
    Quest,
    QuestLog,
    extract_quest_log_from_game_state,
    merge_quest_log_into_game_state,
)

router = APIRouter()


class QuestResponse(BaseModel):
    """Response with quest data."""
    id: int
    title: str
    description: str
    status: str
    giver: str
    objective: str
    reward_hint: str
    created_at: str
    updated_at: str


class QuestListResponse(BaseModel):
    """Response with a list of quests."""
    quests: list[QuestResponse]


class UpdateQuestStatusRequest(BaseModel):
    """Request to update a quest's status."""
    status: str  # "active", "completed", or "failed"


def _quest_to_response(quest: Quest) -> QuestResponse:
    """Convert Quest to response model."""
    return QuestResponse(
        id=quest.id,
        title=quest.title,
        description=quest.description,
        status=quest.status,
        giver=quest.giver,
        objective=quest.objective,
        reward_hint=quest.reward_hint,
        created_at=quest.created_at,
        updated_at=quest.updated_at,
    )


@router.get("/{game_id}/quests", response_model=QuestListResponse)
def list_quests(
    game_id: int,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """Get the player's quest log, optionally filtered by status.

    Query params:
        status: Filter by status (e.g., "active", "completed", "failed")
    """
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state = json.loads(save.game_state)
    quest_log = extract_quest_log_from_game_state(game_state)

    quests = quest_log.quests
    if status:
        valid_statuses = {"active", "completed", "failed"}
        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
            )
        quests = quest_log.get_quests_by_status(status)

    return QuestListResponse(quests=[_quest_to_response(q) for q in quests])


@router.get("/{game_id}/quests/{quest_id}", response_model=QuestResponse)
def get_quest(game_id: int, quest_id: int, db: Session = Depends(get_db)):
    """Get a specific quest by ID."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state = json.loads(save.game_state)
    quest_log = extract_quest_log_from_game_state(game_state)
    quest = quest_log.get_quest(quest_id)

    if not quest:
        raise HTTPException(status_code=404, detail="Quest not found")

    return _quest_to_response(quest)


@router.patch("/{game_id}/quests/{quest_id}", response_model=QuestResponse)
def update_quest_status(
    game_id: int,
    quest_id: int,
    request: UpdateQuestStatusRequest,
    db: Session = Depends(get_db),
):
    """Update a quest's status (active/completed/failed)."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    # Validate status
    valid_statuses = {"active", "completed", "failed"}
    if request.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
        )

    game_state = json.loads(save.game_state)
    quest_log = extract_quest_log_from_game_state(game_state)
    updated_quest = quest_log.update_quest_status(quest_id, request.status)

    if not updated_quest:
        raise HTTPException(status_code=404, detail="Quest not found")

    # Merge back into game state
    game_state = merge_quest_log_into_game_state(game_state, quest_log)
    save.game_state = json.dumps(game_state)
    save.updated_at = save.updated_at  # Trigger update
    db.commit()

    return _quest_to_response(updated_quest)