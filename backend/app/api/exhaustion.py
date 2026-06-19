"""
Exhaustion API — manage the DnD 5e Exhaustion special state.

Exhaustion is a stacking 0–6 affliction (6 = death) driven by hazards such as
extreme heat/cold, starvation, forced marches, and certain monster abilities.
Unlike the 14 conditions, it has *levels* and recovers by one level per long
rest. This router exposes both the out-of-combat character state (persisted in
``game_state``) and the in-combat combatant state (on the active encounter).

Endpoints (mounted under /api/game):
- GET  /{game_id}/exhaustion
      Current character exhaustion level + a full cumulative-effects breakdown.
- POST /{game_id}/exhaustion
      Modify the character's exhaustion (``set`` / ``add`` / ``reduce``).
      Out-of-combat only. ``add`` to 6 marks the character as dead (0 HP).
- GET  /{game_id}/combat/exhaustion/{combatant_id}
      A combatant's exhaustion during the active encounter.
- POST /{game_id}/combat/exhaustion/{combatant_id}
      Modify a combatant's exhaustion mid-combat (e.g. a monster ability forces
      a level on the player). Reaching 6 slays the combatant immediately.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine import exhaustion as exhaust
from app.engine.combat import Encounter

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


def _log(save: GameSave, content: str) -> None:
    """Append a narration entry to the game's story log."""
    try:
        story_log = json.loads(save.story_log)
    except (json.JSONDecodeError, TypeError):
        story_log = []
    story_log.append({
        "role": "system",
        "content": content,
        "timestamp": datetime.utcnow().isoformat(),
    })
    save.story_log = json.dumps(story_log)


def _clamp_levels(value: int | None, default: int = 1) -> int:
    if value is None:
        return default
    return max(0, min(exhaust.MAX_EXHAUSTION, int(value)))


# --------------------------------------------------------------------------- #
# Out-of-combat (character) exhaustion
# --------------------------------------------------------------------------- #

class ExhaustionModifyRequest(BaseModel):
    """Modify the character's exhaustion level."""

    mode: str = Field(
        ..., description="'set' (absolute), 'add' (stack levels), or 'reduce'."
    )
    levels: int | None = Field(
        default=1,
        ge=0,
        le=exhaust.MAX_EXHAUSTION,
        description="How many levels to add/reduce, or the absolute level to set.",
    )


@router.get("/{game_id}/exhaustion")
def get_exhaustion(game_id: int, db: Session = Depends(get_db)):
    """The character's current exhaustion level and cumulative effects."""
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    level = int(game_state.get("exhaustion", 0) or 0)
    return {
        "character_id": save.character_id,
        "in_combat": bool(game_state.get("in_combat", False)),
        "exhaustion": level,
        **exhaust.level_effects(level),
    }


@router.post("/{game_id}/exhaustion")
def modify_exhaustion(
    game_id: int,
    request: ExhaustionModifyRequest,
    db: Session = Depends(get_db),
):
    """Modify the character's out-of-combat exhaustion.

    ``add`` increases the level (a hazard takes effect); ``reduce`` lowers it
    (e.g. Greater Restoration); ``set`` makes it absolute. Reaching level 6 is
    fatal: the character's HP drops to 0. Cannot be used mid-combat (use the
    combat exhaustion endpoint instead so the encounter stays in sync).
    """
    save = _load_game(db, game_id)
    game_state = _game_state(save)

    if game_state.get("in_combat", False):
        raise HTTPException(
            status_code=400,
            detail="Cannot modify character exhaustion mid-combat; use the combat exhaustion endpoint.",
        )

    mode = request.mode.lower()
    if mode not in {"set", "add", "reduce"}:
        raise HTTPException(
            status_code=400,
            detail="mode must be 'set', 'add', or 'reduce'",
        )

    before = int(game_state.get("exhaustion", 0) or 0)
    amount = _clamp_levels(request.levels, default=1)

    if mode == "set":
        after = amount
    elif mode == "add":
        after = before + amount
    else:  # reduce
        after = before - amount
    after = max(0, min(exhaust.MAX_EXHAUSTION, after))
    game_state["exhaustion"] = after

    died = after >= exhaust.MAX_EXHAUSTION
    if died:
        save.character.current_hp = 0
        save.character.updated_at = datetime.utcnow()

    # Narrate the change so the DM/story log reflects the hazard or recovery.
    if mode == "add" and after > before:
        _log(save, f"{save.character.name} gains exhaustion — now level {after}.")
    elif mode == "reduce" and after < before:
        _log(save, f"{save.character.name} recovers exhaustion — now level {after}.")
    elif mode == "set":
        _log(save, f"{save.character.name}'s exhaustion set to level {after}.")
    if died:
        _log(save, f"{save.character.name} succumbs to exhaustion (level 6) and dies.")

    _persist(save, game_state, db)
    db.refresh(save.character)

    return {
        "character_id": save.character_id,
        "before": before,
        "after": after,
        "changed": after != before,
        "died": died,
        "exhaustion": after,
        **exhaust.level_effects(after),
        "character": {
            "current_hp": save.character.current_hp,
            "max_hp": save.character.max_hp,
        },
    }


# --------------------------------------------------------------------------- #
# In-combat (combatant) exhaustion
# --------------------------------------------------------------------------- #

def _load_active_encounter(save: GameSave) -> tuple[dict, Encounter]:
    game_state = _game_state(save)
    if not game_state.get("in_combat", False):
        raise HTTPException(status_code=400, detail="Not in combat")
    return game_state, Encounter.from_dict(game_state.get("combat", {}))


def _persist_encounter(
    save: GameSave, game_state: dict, encounter: Encounter, db: Session
) -> None:
    game_state["combat"] = encounter.to_dict()
    player = next((c for c in encounter.combatants if c.id == "player"), None)
    if player is not None:
        save.character.current_hp = player.current_hp
    _persist(save, game_state, db)


@router.get("/{game_id}/combat/exhaustion/{combatant_id}")
def get_combatant_exhaustion(
    game_id: int,
    combatant_id: str,
    db: Session = Depends(get_db),
):
    """A combatant's exhaustion level during the active encounter."""
    save = _load_game(db, game_id)
    _, encounter = _load_active_encounter(save)
    combatant = next((c for c in encounter.combatants if c.id == combatant_id), None)
    if not combatant:
        raise HTTPException(status_code=404, detail=f"Combatant {combatant_id} not found")
    level = exhaust.get_exhaustion(combatant)
    return {
        "combatant_id": combatant.id,
        "combatant_name": combatant.name,
        "exhaustion": level,
        **exhaust.level_effects(level),
    }


@router.post("/{game_id}/combat/exhaustion/{combatant_id}")
def modify_combatant_exhaustion(
    game_id: int,
    combatant_id: str,
    request: ExhaustionModifyRequest,
    db: Session = Depends(get_db),
):
    """Modify a combatant's exhaustion mid-combat.

    Reaching level 6 slays the combatant immediately (HP → 0). The encounter is
    persisted so the death ripples through initiative, ``is_active``, and the
    winner check.
    """
    save = _load_game(db, game_id)
    game_state, encounter = _load_active_encounter(save)
    combatant = next((c for c in encounter.combatants if c.id == combatant_id), None)
    if not combatant:
        raise HTTPException(status_code=404, detail=f"Combatant {combatant_id} not found")

    mode = request.mode.lower()
    if mode not in {"set", "add", "reduce"}:
        raise HTTPException(
            status_code=400,
            detail="mode must be 'set', 'add', or 'reduce'",
        )

    before = exhaust.get_exhaustion(combatant)
    amount = _clamp_levels(request.levels, default=1)
    if mode == "set":
        exhaust.set_exhaustion(combatant, amount)
    elif mode == "add":
        exhaust.add_exhaustion(combatant, amount)
    else:  # reduce
        exhaust.reduce_exhaustion(combatant, amount)
    after = exhaust.get_exhaustion(combatant)

    died = False
    if exhaust.is_dead(combatant):
        died = True
        combatant.current_hp = 0
        encounter.log.append(
            f"{combatant.name} succumbs to exhaustion (level 6) and dies."
        )
    elif mode == "add" and after > before:
        encounter.log.append(f"{combatant.name} gains exhaustion — now level {after}.")

    _persist_encounter(save, game_state, encounter, db)

    # Report whether combat just ended as a result.
    return {
        "combatant_id": combatant.id,
        "combatant_name": combatant.name,
        "before": before,
        "after": after,
        "changed": after != before,
        "died": died,
        "combat_active": encounter.is_active,
        "winner": encounter.winner if not encounter.is_active else None,
        "exhaustion": after,
        **exhaust.level_effects(after),
        "combatant": {
            "current_hp": combatant.current_hp,
            "max_hp": combatant.max_hp,
            "effective_max_hp": combatant.effective_max_hp,
            "effective_speed": combatant.effective_speed,
            "is_alive": combatant.is_alive,
        },
    }
