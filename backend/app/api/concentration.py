"""
Concentration API — exposes concentration management via REST endpoints.

Allows starting and stopping concentration on spells during combat.
"""
import json
from app.utils.time_utils import utcnow

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine.combat import Encounter

router = APIRouter()


class StartConcentrationRequest(BaseModel):
    """Request to start concentrating on a spell."""
    combatant_id: str
    spell_name: str
    spell_id: str


@router.post("/{game_id}/combat/concentration/start")
def start_concentration(game_id: int, request: StartConcentrationRequest, db: Session = Depends(get_db)):
    """Start concentrating on a spell."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state = json.loads(save.game_state)

    if not game_state.get("in_combat", False):
        raise HTTPException(status_code=400, detail="Not in combat")

    encounter = Encounter.from_dict(game_state.get("combat", {}))

    success = encounter.start_concentration(
        request.combatant_id,
        request.spell_name,
        request.spell_id,
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Already concentrating on a spell"
        )

    # Save updated encounter
    game_state["combat"] = encounter.to_dict()
    save.game_state = json.dumps(game_state)
    save.updated_at = utcnow()
    db.commit()

    return {
        "message": f"Started concentrating on {request.spell_name}",
        "encounter": encounter.to_dict(),
    }


@router.post("/{game_id}/combat/concentration/end")
def end_concentration(game_id: int, combatant_id: str, db: Session = Depends(get_db)):
    """Stop concentrating."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state = json.loads(save.game_state)

    if not game_state.get("in_combat", False):
        raise HTTPException(status_code=400, detail="Not in combat")

    encounter = Encounter.from_dict(game_state.get("combat", {}))

    success = encounter.end_concentration(combatant_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Combatant not found or not concentrating"
        )

    # Save updated encounter
    game_state["combat"] = encounter.to_dict()
    save.game_state = json.dumps(game_state)
    save.updated_at = utcnow()
    db.commit()

    return {
        "message": f"Stopped concentrating",
        "encounter": encounter.to_dict(),
    }