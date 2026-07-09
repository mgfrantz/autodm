"""
REST API for trap/hazard management (DMG ch.5: "Traps").

Provides endpoints for the trap registry (static templates) and for placing,
detecting, disarming, and triggering traps within a specific game.

Trap instances are persisted in ``game_state["traps"]`` as a JSON list.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine.traps import (
    Trap, TrapInstance, TrapEffect, TrapType, TrapSeverity, TrapEffectType,
    DetectionResult, DisarmResult, TriggerResult,
    get_trap, list_traps, list_trap_ids, traps_by_severity,
    attempt_detection, check_passive_perception, attempt_disarm,
    trigger_trap, failed_disarm_triggers,
    trap_summary_for_dm, severity_guidelines,
    roll_dice,
)

router = APIRouter(prefix="/game", tags=["traps"])


# ============================================================================
# Schemas
# ============================================================================

class TrapEffectSchema(BaseModel):
    type: str = "damage"
    damage_dice: str = ""
    damage_type: str = ""
    save_ability: str = ""
    save_dc: int = 0
    save_result: str = "half"
    condition: str = ""
    condition_duration: int = 0
    description: str = ""


class TrapSchema(BaseModel):
    id: str
    name: str
    description: str
    trap_type: str = "mechanical"
    severity: str = "dangerous"
    detection_dc: int = 12
    disarm_dc: int = 12
    trigger: str = ""
    effects: List[TrapEffectSchema] = []
    countermeasure: str = ""
    area: str = ""


class TrapInstanceSchema(BaseModel):
    trap_id: str
    trap: TrapSchema
    location: str = ""
    discovered: bool = False
    disarmed: bool = False
    triggered: bool = False
    trigger_count: int = 0


class PlaceTrapRequest(BaseModel):
    trap_id: str
    location: str = ""


class DetectRequest(BaseModel):
    perception_total: int = Field(ge=1, description="Full Perception check (roll + WIS mod + prof)")
    roll: int = Field(default=0, ge=0, le=20, description="Raw d20 roll for narration")


class PassiveDetectRequest(BaseModel):
    passive_perception: int = Field(ge=1)


class DisarmRequest(BaseModel):
    check_total: int = Field(ge=1, description="Full check result (roll + modifier)")
    roll: int = Field(default=0, ge=0, le=20, description="Raw d20 roll")
    method: str = Field(default="thieves_tools", description="thieves_tools, strength, arcana, etc.")


class TriggerRequest(BaseModel):
    save_roll: Optional[int] = Field(default=None, ge=1, le=20, description="Raw d20 save roll (if trap has a save)")
    save_modifier: int = Field(default=0, description="Save modifier (ability mod + proficiency)")


# ============================================================================
# Registry endpoints (no game_id needed)
# ============================================================================

@router.get("/traps/registry")
def get_trap_registry(
    trap_type: Optional[str] = None,
    severity: Optional[str] = None,
) -> List[TrapSchema]:
    """List all trap templates, optionally filtered by type and/or severity."""
    tt = TrapType(trap_type) if trap_type else None
    sv = TrapSeverity(severity) if severity else None
    traps = list_traps(trap_type=tt, severity=sv)
    return [_trap_to_schema(t) for t in traps]


@router.get("/traps/registry/ids")
def get_trap_ids() -> List[str]:
    """List all trap IDs (lightweight)."""
    return list_trap_ids()


@router.get("/traps/registry/type/{trap_type}")
def get_traps_by_type(trap_type: str) -> List[TrapSchema]:
    """Get all traps of a given type (mechanical or magical)."""
    try:
        tt = TrapType(trap_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid trap type: {trap_type}")
    traps = list_traps(trap_type=tt)
    return [_trap_to_schema(t) for t in traps]


@router.get("/traps/registry/severity/{severity}")
def get_traps_by_severity(severity: str) -> List[TrapSchema]:
    """Get all traps of a given severity (setback, dangerous, deadly)."""
    try:
        sv = TrapSeverity(severity)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")
    traps = traps_by_severity(sv)
    return [_trap_to_schema(t) for t in traps]


@router.get("/traps/guidelines")
def get_severity_guidelines() -> Dict[str, Any]:
    """Get DMG trap severity guidelines (DCs and damage by severity)."""
    return severity_guidelines()


@router.get("/traps/registry/{trap_id}")
def get_trap_detail(trap_id: str) -> TrapSchema:
    """Get details for a specific trap template."""
    trap = get_trap(trap_id)
    if not trap:
        raise HTTPException(status_code=404, detail=f"Trap '{trap_id}' not found")
    return _trap_to_schema(trap)


# ============================================================================
# Game-specific endpoints (trap instances)
# ============================================================================

@router.get("/{game_id}/traps")
def get_game_traps(game_id: int, db: Session = Depends(get_db)) -> List[TrapInstanceSchema]:
    """List all trap instances placed in a game."""
    game = _get_game(db, game_id)
    instances = _load_traps(game)
    return [_instance_to_schema(i) for i in instances]


@router.post("/{game_id}/traps")
def place_trap(
    game_id: int,
    request: PlaceTrapRequest,
    db: Session = Depends(get_db),
) -> TrapInstanceSchema:
    """Place a trap in the game world."""
    game = _get_game(db, game_id)
    trap = get_trap(request.trap_id)
    if not trap:
        raise HTTPException(status_code=404, detail=f"Trap '{request.trap_id}' not found")

    instances = _load_traps(game)
    instance = TrapInstance.from_trap(trap, location=request.location)
    instances.append(instance)
    _save_traps(game, instances)

    _log_to_story(game, f"A {trap.name} is placed{' at ' + request.location if request.location else ''}.")
    db.commit()

    return _instance_to_schema(instance)


@router.post("/{game_id}/traps/{trap_index}/detect")
def detect_trap(
    game_id: int,
    trap_index: int,
    request: DetectRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Attempt to detect a specific trap (active Perception check)."""
    game = _get_game(db, game_id)
    instances = _load_traps(game)
    instance = _get_instance(instances, trap_index)

    result = attempt_detection(instance, request.perception_total, request.roll)
    _save_traps(game, instances)
    _log_to_story(game, result.narrative)
    db.commit()

    return result.to_dict()


@router.post("/{game_id}/traps/{trap_index}/passive-detect")
def passive_detect_trap(
    game_id: int,
    trap_index: int,
    request: PassiveDetectRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Check passive Perception against a trap."""
    game = _get_game(db, game_id)
    instances = _load_traps(game)
    instance = _get_instance(instances, trap_index)

    noticed = check_passive_perception(instance, request.passive_perception)
    if noticed and not instance.disarmed:
        _save_traps(game, instances)
        narrative = f"Your keen senses notice a {instance.trap.name}!"
    else:
        narrative = "You don't notice anything unusual."

    _log_to_story(game, narrative)
    db.commit()

    return {
        "noticed": noticed,
        "discovered": instance.discovered,
        "narrative": narrative,
    }


@router.post("/{game_id}/traps/{trap_index}/disarm")
def disarm_trap(
    game_id: int,
    trap_index: int,
    request: DisarmRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Attempt to disarm a trap."""
    game = _get_game(db, game_id)
    instances = _load_traps(game)
    instance = _get_instance(instances, trap_index)

    result = attempt_disarm(instance, request.check_total, request.roll, request.method)

    # If disarm failed badly, there's a chance the trap triggers
    triggered_result = None
    if not result.success and failed_disarm_triggers(instance):
        # A failed disarm by 5+ triggers the trap (DMG guidance)
        margin = instance.trap.disarm_dc - request.check_total
        if margin >= 5:
            triggered_result = trigger_trap(instance, save_roll=None)
            _log_to_story(game, result.narrative + " " + triggered_result.narrative)
        else:
            _log_to_story(game, result.narrative)
    else:
        _log_to_story(game, result.narrative)

    _save_traps(game, instances)
    db.commit()

    response = result.to_dict()
    if triggered_result:
        response["triggered"] = triggered_result.to_dict()
    return response


@router.post("/{game_id}/traps/{trap_index}/trigger")
def trigger_game_trap(
    game_id: int,
    trap_index: int,
    request: TriggerRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Trigger a trap (e.g., by walking into it)."""
    game = _get_game(db, game_id)
    instances = _load_traps(game)
    instance = _get_instance(instances, trap_index)

    result = trigger_trap(
        instance,
        save_roll=request.save_roll,
        save_modifier=request.save_modifier,
    )
    _save_traps(game, instances)
    _log_to_story(game, result.narrative)
    db.commit()

    return result.to_dict()


@router.delete("/{game_id}/traps/{trap_index}")
def remove_trap(
    game_id: int,
    trap_index: int,
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Remove a placed trap from the game (GM/admin action)."""
    game = _get_game(db, game_id)
    instances = _load_traps(game)

    if trap_index < 0 or trap_index >= len(instances):
        raise HTTPException(status_code=404, detail=f"Trap index {trap_index} not found")

    removed = instances.pop(trap_index)
    _save_traps(game, instances)
    _log_to_story(game, f"{removed.trap.name} removed (GM action).")
    db.commit()

    return {"status": "removed", "trap_id": removed.trap_id}


@router.get("/{game_id}/traps/dm-summary")
def traps_dm_summary(game_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Get a DM-friendly summary of traps in the current area."""
    game = _get_game(db, game_id)
    instances = _load_traps(game)
    summary = trap_summary_for_dm(instances)
    return {
        "summary": summary,
        "total_traps": len(instances),
        "undiscovered": sum(1 for i in instances if not i.discovered),
        "discovered": sum(1 for i in instances if i.discovered and not i.disarmed),
        "disarmed": sum(1 for i in instances if i.disarmed),
    }


# ============================================================================
# Helpers
# ============================================================================

def _get_game(db: Session, game_id: int) -> GameSave:
    game = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    return game


def _get_instance(instances: List[TrapInstance], index: int) -> TrapInstance:
    if index < 0 or index >= len(instances):
        raise HTTPException(status_code=404, detail=f"Trap index {index} not found")
    return instances[index]


def _load_traps(game: GameSave) -> List[TrapInstance]:
    """Load trap instances from game_state JSON."""
    try:
        game_state = json.loads(game.game_state or "{}")
    except (TypeError, json.JSONDecodeError):
        game_state = {}

    traps_data = game_state.get("traps", [])
    if not traps_data:
        return []

    instances = []
    for td in traps_data:
        try:
            instances.append(TrapInstance.from_dict(td))
        except Exception:
            pass  # skip malformed entries
    return instances


def _save_traps(game: GameSave, instances: List[TrapInstance]) -> None:
    """Save trap instances to game_state JSON (preserving other keys)."""
    try:
        game_state = json.loads(game.game_state or "{}")
    except (TypeError, json.JSONDecodeError):
        game_state = {}

    game_state["traps"] = [i.to_dict() for i in instances]
    game.game_state = json.dumps(game_state)


def _log_to_story(game: GameSave, message: str) -> None:
    """Add a message to the story log."""
    try:
        story = json.loads(game.story_log or "[]")
    except (TypeError, json.JSONDecodeError):
        story = []

    entry = {
        "type": "system",
        "content": message,
        "timestamp": datetime.utcnow().isoformat(),
    }
    story.append(entry)
    game.story_log = json.dumps(story)


# ============================================================================
# Schema conversion
# ============================================================================

def _effect_to_schema(effect: TrapEffect) -> TrapEffectSchema:
    return TrapEffectSchema(
        type=effect.type.value,
        damage_dice=effect.damage_dice,
        damage_type=effect.damage_type,
        save_ability=effect.save_ability,
        save_dc=effect.save_dc,
        save_result=effect.save_result,
        condition=effect.condition,
        condition_duration=effect.condition_duration,
        description=effect.description,
    )


def _trap_to_schema(trap: Trap) -> TrapSchema:
    return TrapSchema(
        id=trap.id,
        name=trap.name,
        description=trap.description,
        trap_type=trap.trap_type.value,
        severity=trap.severity.value,
        detection_dc=trap.detection_dc,
        disarm_dc=trap.disarm_dc,
        trigger=trap.trigger,
        effects=[_effect_to_schema(e) for e in trap.effects],
        countermeasure=trap.countermeasure,
        area=trap.area,
    )


def _instance_to_schema(instance: TrapInstance) -> TrapInstanceSchema:
    return TrapInstanceSchema(
        trap_id=instance.trap_id,
        trap=_trap_to_schema(instance.trap),
        location=instance.location,
        discovered=instance.discovered,
        disarmed=instance.disarmed,
        triggered=instance.triggered,
        trigger_count=instance.trigger_count,
    )
