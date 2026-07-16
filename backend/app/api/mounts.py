"""
Mounts & vehicles REST API — mounted travel and mounted combat.

Mounts under ``/api/game``. The active mount + its live HP + whether the rider
is currently astride it are persisted inside ``game_state["mount"]`` so they
round-trip through save/load automatically. Mount *definitions* (speed, size,
carrying capacity, attacks, …) live in the engine registry and are not stored.

Endpoints:
- GET  /{game_id}/mounts/registry            List all mounts (optional ?type=).
- GET  /{game_id}/mounts/{mount_id}          Get a single mount definition.
- GET  /{game_id}/mount                       Current mount state + summary.
- POST /{game_id}/mount/acquire               Acquire a fresh, healthy, mounted
                                             mount (optionally paying its cost).
- POST /{game_id}/mount/mount-up              Climb into the saddle (mounted=True).
- POST /{game_id}/mount/dismount              Dismount (keep leading the mount).
- POST /{game_id}/mount/pace                  Set travel pace (slow/normal/fast)
                                             and the gallop-burst toggle.
- POST /{game_id}/mount/damage                Damage the mount (may throw the rider).
- POST /{game_id}/mount/heal                  Heal the mount (clamped to max HP).
- POST /{game_id}/mount/combat                Mounted-combat modifiers for the rider,
                                             auto-detecting the Mounted Combatant feat.
- POST /{game_id}/mount/travel                Preview adjusted travel hours for a trip.
"""
from __future__ import annotations

import json
from app.utils.time_utils import utcnow

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine import mounts

router = APIRouter()


# --------------------------------------------------------------------------- #
# Persistence helpers (mirror the starvation router's pattern)
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


def _log(save: GameSave, content: str) -> None:
    try:
        story_log = json.loads(save.story_log)
    except (json.JSONDecodeError, TypeError):
        story_log = []
    story_log.append({
        "role": "system",
        "content": content,
        "timestamp": utcnow().isoformat(),
    })
    save.story_log = json.dumps(story_log)


def _mount_state(game_state: dict) -> mounts.MountState:
    return mounts.MountState.from_dict(game_state.get("mount"))


def _character_feat_names(save: GameSave) -> set[str]:
    """The set of feat names a character has learned (for Mounted Combatant)."""
    try:
        feats = json.loads(save.character.feats or "[]")
    except (json.JSONDecodeError, TypeError):
        feats = []
    return {str(f.get("name", "")).lower() for f in feats if isinstance(f, dict)}


def has_mounted_combatant(save: GameSave) -> bool:
    return mounts.MOUNTED_COMBATANT_FEAT.lower() in _character_feat_names(save)


# --------------------------------------------------------------------------- #
# Request / response schemas
# --------------------------------------------------------------------------- #

class AcquireRequest(BaseModel):
    mount_id: str
    mounted: bool = Field(default=True, description="Whether the rider is astride it.")
    pay: bool = Field(
        default=False,
        description="If true, deduct the mount's cost from the character's gold "
                    "(and fail if they can't afford it).",
    )


class PaceRequest(BaseModel):
    pace: str = Field(default="normal", description="slow / normal / fast")
    galloping: bool = False


class DamageRequest(BaseModel):
    amount: int = Field(..., ge=0, description="Damage to apply to the mount.")
    save_total: int | None = Field(
        default=None, ge=0,
        description="An explicit Dexterity save total for a prone-mount fall "
                    "(DM-adjudicated). The DC is 10.",
    )


class HealRequest(BaseModel):
    amount: int = Field(..., ge=0, description="HP to restore to the mount.")


class CombatModifiersRequest(BaseModel):
    has_feat: bool | None = Field(
        default=None,
        description="Override Mounted Combatant detection. Auto-detected when omitted.",
    )
    target_size: str = Field(default="medium", description="Size of the attack target.")
    target_mounted: bool = Field(
        default=False, description="Whether the target is itself mounted."
    )


class TravelRequest(BaseModel):
    base_hours: float = Field(..., ge=0, description="Walking travel time on foot.")
    pace: str | None = None
    galloping: bool | None = None


# --------------------------------------------------------------------------- #
# Registry endpoints
# --------------------------------------------------------------------------- #

@router.get("/{game_id}/mounts/registry")
def list_registry(
    game_id: int,
    type: str | None = Query(default=None, description="Filter by land/flying/aquatic/vehicle."),
    db: Session = Depends(get_db),
):
    """List all registered mounts (definitions), optionally filtered by type."""
    _load_game(db, game_id)  # confirm the game exists
    return [m.to_dict() for m in mounts.list_mounts(type)]


@router.get("/{game_id}/mounts/{mount_id}")
def get_registry_mount(game_id: int, mount_id: str, db: Session = Depends(get_db)):
    """Get a single mount definition from the registry."""
    _load_game(db, game_id)
    mount = mounts.get_mount(mount_id)
    if mount is None:
        raise HTTPException(status_code=404, detail=f"Mount '{mount_id}' not found")
    return mount.to_dict()


# --------------------------------------------------------------------------- #
# Active-mount state
# --------------------------------------------------------------------------- #

@router.get("/{game_id}/mount")
def get_mount_state(game_id: int, db: Session = Depends(get_db)):
    """Current mount state + a readable summary (HP, pace, speed multiplier)."""
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    state = _mount_state(game_state)
    return {
        "character_id": save.character_id,
        "has_mounted_combatant": has_mounted_combatant(save),
        "state": state.to_dict(),
        "summary": mounts.mount_summary(state),
    }


@router.post("/{game_id}/mount/acquire")
def acquire_mount(game_id: int, request: AcquireRequest, db: Session = Depends(get_db)):
    """Acquire a fresh, fully-healthy mount.

    Replaces any mount the character currently leads. When ``pay`` is set, the
    mount's ``cost_gp`` is deducted from the character's gold and the request
    fails (402) if they can't afford it. The mount begins mounted by default.
    """
    save = _load_game(db, game_id)
    mount = mounts.get_mount(request.mount_id)
    if mount is None:
        raise HTTPException(status_code=404, detail=f"Mount '{request.mount_id}' not found")

    paid = 0.0
    insufficient = False
    if request.pay:
        gold = int(getattr(save.character, "gold", 0) or 0)
        cost = float(mount.cost_gp or 0)
        if cost > 0 and gold < cost:
            insufficient = True
        elif cost > 0:
            save.character.gold = gold - int(cost)
            paid = cost

    if insufficient:
        raise HTTPException(
            status_code=402,
            detail=f"Cannot afford {mount.name} ({mount.cost_gp} gp); have "
                   f"{getattr(save.character, 'gold', 0)} gp.",
        )

    state = mounts.fresh_state(mount)
    state.mounted = request.mounted

    game_state = _game_state(save)
    game_state["mount"] = state.to_dict()
    _log(save, f"{save.character.name} acquires a {mount.name}"
               + (f" (paid {paid} gp)" if paid else "") + ".")
    _persist(save, game_state, db)
    db.refresh(save.character)
    return {
        "character_id": save.character_id,
        "state": state.to_dict(),
        "mount": mount.to_dict(),
        "paid_gp": paid,
        "character_gold": getattr(save.character, "gold", 0),
        "summary": mounts.mount_summary(state),
    }


@router.post("/{game_id}/mount/mount-up")
def mount_up(game_id: int, db: Session = Depends(get_db)):
    """Climb into the saddle (costs half your movement in combat)."""
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    state = _mount_state(game_state)
    if not state.has_mount:
        raise HTTPException(status_code=400, detail="No mount to ride.")
    if not state.is_conscious():
        raise HTTPException(status_code=400, detail="Your mount is downed and cannot bear you.")
    state.mounted = True
    game_state["mount"] = state.to_dict()
    _persist(save, game_state, db)
    return {
        "character_id": save.character_id,
        "state": state.to_dict(),
        "summary": mounts.mount_summary(state),
    }


@router.post("/{game_id}/mount/dismount")
def dismount(game_id: int, db: Session = Depends(get_db)):
    """Dismount but keep leading the mount."""
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    state = _mount_state(game_state)
    if not state.has_mount:
        raise HTTPException(status_code=400, detail="No mount to dismount from.")
    state.mounted = False
    game_state["mount"] = state.to_dict()
    _persist(save, game_state, db)
    return {
        "character_id": save.character_id,
        "state": state.to_dict(),
        "summary": mounts.mount_summary(state),
    }


@router.post("/{game_id}/mount/pace")
def set_pace(game_id: int, request: PaceRequest, db: Session = Depends(get_db)):
    """Set the overland travel pace (and gallop-burst toggle) for the active mount."""
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    state = _mount_state(game_state)
    state.pace = (request.pace or "normal").lower()
    state.galloping = bool(request.galloping)
    game_state["mount"] = state.to_dict()
    _persist(save, game_state, db)
    return {
        "character_id": save.character_id,
        "state": state.to_dict(),
        "summary": mounts.mount_summary(state),
        "pace_note": mounts.pace_notes(state.pace),
    }


@router.post("/{game_id}/mount/damage")
def damage_mount(game_id: int, request: DamageRequest, db: Session = Depends(get_db)):
    """Apply damage to the mount. If it drops to 0 HP the rider is thrown (prone)."""
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    state = _mount_state(game_state)
    if not state.has_mount:
        raise HTTPException(status_code=400, detail="No mount to damage.")

    new_state, outcome, overflow = mounts.damage_mount(state, request.amount)
    game_state["mount"] = new_state.to_dict()
    _log(save, outcome.message)

    # If the mount went down, the rider is on the ground.
    if outcome.forced_dismount and new_state.current_hp == 0:
        _log(save, f"{save.character.name}'s mount collapses — they are thrown and "
                   f"land prone.")

    _persist(save, game_state, db)
    return {
        "character_id": save.character_id,
        "state": new_state.to_dict(),
        "outcome": outcome.to_dict(),
        "overflow": overflow,
        "summary": mounts.mount_summary(new_state),
    }


@router.post("/{game_id}/mount/heal")
def heal_mount(game_id: int, request: HealRequest, db: Session = Depends(get_db)):
    """Heal the active mount (clamped to its max HP)."""
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    state = _mount_state(game_state)
    if not state.has_mount:
        raise HTTPException(status_code=400, detail="No mount to heal.")
    new_state, healed = mounts.heal_mount(state, request.amount)
    game_state["mount"] = new_state.to_dict()
    _persist(save, game_state, db)
    return {
        "character_id": save.character_id,
        "state": new_state.to_dict(),
        "healed": healed,
        "summary": mounts.mount_summary(new_state),
    }


@router.post("/{game_id}/mount/combat")
def combat_modifiers(game_id: int, request: CombatModifiersRequest, db: Session = Depends(get_db)):
    """Mounted-combat modifiers for the rider against a given target.

    Auto-detects the Mounted Combatant feat unless ``has_feat`` is overridden.
    Reports melee advantage, the feat benefits, and weapon-prone notes.
    """
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    state = _mount_state(game_state)
    has_feat = (has_mounted_combatant(save) if request.has_feat is None
                else bool(request.has_feat))
    mods = mounts.rider_combat_modifiers(state, has_feat)
    advantage = mounts.melee_advantage_applies(
        state, target_size=request.target_size, target_mounted=request.target_mounted,
    )
    return {
        "character_id": save.character_id,
        "has_mounted_combatant": has_feat,
        "modifiers": mods.to_dict(),
        "melee_advantage_vs_target": advantage,
        "target_size": request.target_size,
        "target_mounted": request.target_mounted,
        "weapon_rules": {
            "lance": mounts.weapon_mounted_rules("lance"),
        },
    }


@router.post("/{game_id}/mount/travel")
def travel_preview(game_id: int, request: TravelRequest, db: Session = Depends(get_db)):
    """Preview the adjusted travel hours for a trip given the current mount + pace.

    Does not move the player — use ``POST /api/navigation/{game_id}/travel`` for
    that. This endpoint is a planning aid (and is used internally by travel).
    """
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    state = _mount_state(game_state)
    speed = mounts.adjust_travel_hours(
        request.base_hours, state, pace=request.pace, galloping=request.galloping,
    )
    return {
        "character_id": save.character_id,
        "speed": speed.to_dict(),
        "state": state.to_dict(),
        "summary": mounts.mount_summary(state),
    }
