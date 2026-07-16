"""
REST API for affliction management (diseases and poisons).

Provides endpoints for managing lingering afflictions with staged effects,
distinct from the one-shot "poisoned" condition.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine.afflictions import (
    Affliction, AfflictionStatus, ActiveAffliction,
    AfflictionAdvanceResult, AfflictionSaveResult,
    get_affliction, list_afflictions,
    affliction_summary, get_affliction_effects_for_combat,
    affliction_effects_breakdown,
    AfflictionType
)

router = APIRouter(prefix="/game", tags=["afflictions"])


# ============================================================================
# SCHEMAS
# ============================================================================

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class AfflictionEffectSchema(BaseModel):
    type: str
    value: Optional[Any] = None
    description: str = ""


class AfflictionStageSchema(BaseModel):
    name: str
    effects: List[AfflictionEffectSchema] = []
    duration_days: Optional[int] = None
    save_dc: Optional[int] = None


class AfflictionSchema(BaseModel):
    id: str
    name: str
    type: str
    description: str
    stages: List[AfflictionStageSchema] = []
    onset_days: int = 0
    save_ability: str = "constitution"


class ActiveAfflictionSchema(BaseModel):
    affliction_id: str
    affliction: AfflictionSchema
    stage_index: int = 0
    days_in_stage: int = 0
    days_since_onset: int = 0
    cured: bool = False
    
    @property
    def is_onset(self) -> bool:
        return self.stage_index < 0 or self.days_since_onset < self.affliction.onset_days


class AfflictionStatusSchema(BaseModel):
    active: List[ActiveAfflictionSchema] = []


class AfflictionAdvanceResultSchema(BaseModel):
    changed: bool
    previous_stage: int
    new_stage: int
    effects_applied: List[AfflictionEffectSchema] = []
    narrative: str = ""


class AfflictionSaveResultSchema(BaseModel):
    success: bool
    dc: int
    roll: int
    modifier: int
    total: int
    treated: bool
    narrative: str = ""


class ContractAfflictionRequest(BaseModel):
    affliction_id: str


class SaveAfflictionRequest(BaseModel):
    affliction_id: str
    roll: int = Field(ge=1, le=20, description="The d20 roll")
    modifier: int = Field(description="Ability modifier")
    treat: bool = False


class AdvanceAfflictionsRequest(BaseModel):
    days: int = Field(default=1, ge=1, le=30, description="Number of days to advance")


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/afflictions/registry")
def get_affliction_registry() -> List[AfflictionSchema]:
    """Get the full registry of available diseases and poisons."""
    afflictions = list_afflictions()
    return [_affliction_to_schema(a) for a in afflictions]


@router.get("/afflictions/registry/diseases")
def get_diseases() -> List[AfflictionSchema]:
    """Get all diseases."""
    diseases = list_afflictions(AfflictionType.DISEASE)
    return [_affliction_to_schema(d) for d in diseases]


@router.get("/afflictions/registry/poisons")
def get_poisons() -> List[AfflictionSchema]:
    """Get all poisons."""
    poisons = list_afflictions(AfflictionType.POISON)
    return [_affliction_to_schema(p) for p in poisons]


@router.get("/afflictions/registry/{affliction_id}")
def get_affliction_detail(affliction_id: str) -> AfflictionSchema:
    """Get details for a specific affliction."""
    affliction = get_affliction(affliction_id)
    if not affliction:
        raise HTTPException(status_code=404, detail=f"Affliction '{affliction_id}' not found")
    return _affliction_to_schema(affliction)


@router.get("/{game_id}/afflictions")
def get_affliction_status(game_id: int, db: Session = Depends(get_db)) -> AfflictionStatusSchema:
    """Get the current affliction status for a game."""
    game = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    
    affliction_status = _load_affliction_status(game)
    return _status_to_schema(affliction_status)


@router.post("/{game_id}/afflictions/contract")
def contract_affliction(
    game_id: int,
    request: ContractAfflictionRequest,
    db: Session = Depends(get_db)
) -> ActiveAfflictionSchema:
    """Contract a disease or poison."""
    game = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    
    affliction = get_affliction(request.affliction_id)
    if not affliction:
        raise HTTPException(status_code=404, detail=f"Affliction '{request.affliction_id}' not found")
    
    affliction_status = _load_affliction_status(game)
    
    # Check if already has this affliction
    existing = affliction_status.get_by_id(request.affliction_id)
    if existing:
        if not existing.cured:
            raise HTTPException(
                status_code=400,
                detail=f"Already afflicted with {affliction.name}"
            )
        # Affliction was cured previously — remove the stale entry so we can
        # re-contract a fresh instance without leaving duplicates.
        affliction_status.active = [
            a for a in affliction_status.active
            if a.affliction_id != request.affliction_id
        ]

    # Add the affliction
    active = affliction_status.add_affliction(affliction)
    
    # Persist (log before commit so the story entry is saved in the same tx)
    _save_affliction_status(game, affliction_status)
    _log_to_story(game, f"Contracted {affliction.name}: {affliction.description}")
    db.commit()
    
    return _active_to_schema(active)


@router.post("/{game_id}/afflictions/save")
def save_against_affliction(
    game_id: int,
    request: SaveAfflictionRequest,
    db: Session = Depends(get_db)
) -> AfflictionSaveResultSchema:
    """Attempt a save to cure an affliction."""
    game = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    
    affliction_status = _load_affliction_status(game)
    active = affliction_status.get_by_id(request.affliction_id)
    
    if not active:
        raise HTTPException(status_code=404, detail=f"Active affliction '{request.affliction_id}' not found")
    
    if active.cured:
        raise HTTPException(status_code=400, detail="Affliction already cured")
    
    # Attempt the save
    result = active.attempt_save(request.roll, request.modifier, request.treat)
    
    # Persist. Cured afflictions are kept (filtered by active_afflictions and
    # cleaned up on advance) so a repeat save returns 400 "already cured".
    _save_affliction_status(game, affliction_status)
    _log_to_story(game, result.narrative)
    db.commit()
    
    return _save_result_to_schema(result)


@router.post("/{game_id}/afflictions/advance")
def advance_afflictions(
    game_id: int,
    request: AdvanceAfflictionsRequest = AdvanceAfflictionsRequest(days=1),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Advance afflictions by the given number of days (default 1)."""
    
    game = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    
    affliction_status = _load_affliction_status(game)
    
    # Advance
    results = affliction_status.advance_days(request.days)
    
    # Remove cured
    affliction_status.remove_cured()
    
    # Persist (log before commit)
    _save_affliction_status(game, affliction_status)
    for result in results:
        if result.narrative:
            _log_to_story(game, result.narrative)
    db.commit()
    
    # Get current status for response
    effects_breakdown = affliction_effects_breakdown(affliction_status)
    combat_effects = get_affliction_effects_for_combat(affliction_status)
    
    return {
        "days_advanced": request.days,
        "advancements": [_advance_result_to_schema(r) for r in results],
        "current_status": _status_to_schema(affliction_status),
        "effects_breakdown": effects_breakdown,
        "combat_effects": combat_effects,
        "has_afflictions": affliction_status.has_afflictions
    }


@router.get("/{game_id}/afflictions/effects")
def get_affliction_effects(game_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get the current active affliction effects for a game."""
    game = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    
    affliction_status = _load_affliction_status(game)
    
    return {
        "effects_breakdown": affliction_effects_breakdown(affliction_status),
        "combat_effects": get_affliction_effects_for_combat(affliction_status),
        "has_afflictions": affliction_status.has_afflictions,
        "active_count": len(affliction_status.active_afflictions)
    }


@router.delete("/{game_id}/afflictions/{affliction_id}")
def remove_affliction(
    game_id: int,
    affliction_id: str,
    db: Session = Depends(get_db)
) -> Dict[str, str]:
    """Remove an affliction (GM/admin use only - bypasses save)."""
    game = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    
    affliction_status = _load_affliction_status(game)
    active = affliction_status.get_by_id(affliction_id)
    
    if not active:
        raise HTTPException(status_code=404, detail=f"Affliction '{affliction_id}' not found")
    
    # Mark as cured
    active.cured = True
    affliction_status.remove_cured()
    
    # Persist (log before commit)
    _save_affliction_status(game, affliction_status)
    affliction_name = active.affliction.name
    _log_to_story(game, f"{affliction_name} has been removed (GM action)")
    db.commit()
    
    return {"status": "removed", "affliction_id": affliction_id}


# ============================================================================
# HELPERS
# ============================================================================

def _load_affliction_status(game: GameSave) -> AfflictionStatus:
    """Load affliction status from game_state."""
    import json

    try:
        game_state = json.loads(game.game_state or "{}")
    except (TypeError, json.JSONDecodeError):
        game_state = {}

    affliction_data = game_state.get("afflictions", {})

    if not affliction_data:
        return AfflictionStatus()

    try:
        return AfflictionStatus.from_dict(affliction_data)
    except Exception:
        # If deserialization fails, return empty status
        return AfflictionStatus()


def _save_affliction_status(game: GameSave, status: AfflictionStatus) -> None:
    """Save affliction status to game_state."""
    import json

    try:
        game_state = json.loads(game.game_state or "{}")
    except (TypeError, json.JSONDecodeError):
        game_state = {}

    game_state["afflictions"] = status.to_dict()
    game.game_state = json.dumps(game_state)


def _log_to_story(game: GameSave, message: str) -> None:
    """Add a message to the story log."""
    import json
    from app.utils.time_utils import utcnow

    try:
        story = json.loads(game.story_log or "[]")
    except (TypeError, json.JSONDecodeError):
        story = []

    entry = {
        "type": "system",
        "content": message,
        "timestamp": utcnow().isoformat()
    }
    story.append(entry)
    game.story_log = json.dumps(story)


# Schema conversion helpers

def _affliction_to_schema(affliction: Affliction) -> AfflictionSchema:
    return AfflictionSchema(
        id=affliction.id,
        name=affliction.name,
        type=affliction.type.value,
        description=affliction.description,
        stages=[_stage_to_schema(s) for s in affliction.stages],
        onset_days=affliction.onset_days,
        save_ability=affliction.save_ability
    )


def _stage_to_schema(stage) -> AfflictionStageSchema:
    from app.engine.afflictions import AfflictionStage
    return AfflictionStageSchema(
        name=stage.name,
        effects=[_effect_to_schema(e) for e in stage.effects],
        duration_days=stage.duration_days,
        save_dc=stage.save_dc
    )


def _effect_to_schema(effect) -> AfflictionEffectSchema:
    from app.engine.afflictions import AfflictionEffect
    return AfflictionEffectSchema(
        type=effect.type.value,
        value=effect.value,
        description=effect.description
    )


def _status_to_schema(status: AfflictionStatus) -> AfflictionStatusSchema:
    return AfflictionStatusSchema(
        active=[_active_to_schema(a) for a in status.active]
    )


def _active_to_schema(active: ActiveAffliction) -> ActiveAfflictionSchema:
    return ActiveAfflictionSchema(
        affliction_id=active.affliction_id,
        affliction=_affliction_to_schema(active.affliction),
        stage_index=active.stage_index,
        days_in_stage=active.days_in_stage,
        days_since_onset=active.days_since_onset,
        cured=active.cured
    )


def _advance_result_to_schema(result: AfflictionAdvanceResult) -> AfflictionAdvanceResultSchema:
    return AfflictionAdvanceResultSchema(
        changed=result.changed,
        previous_stage=result.previous_stage,
        new_stage=result.new_stage,
        effects_applied=[_effect_to_schema(e) for e in result.effects_applied],
        narrative=result.narrative
    )


def _save_result_to_schema(result: AfflictionSaveResult) -> AfflictionSaveResultSchema:
    return AfflictionSaveResultSchema(
        success=result.success,
        dc=result.dc,
        roll=result.roll,
        modifier=result.modifier,
        total=result.total,
        treated=result.treated,
        narrative=result.narrative
    )