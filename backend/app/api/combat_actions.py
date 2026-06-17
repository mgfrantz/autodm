"""
Combat actions API — exposes the DnD 5e "Actions in Combat" beyond basic attacks.

Single dispatch endpoint lets the client perform any action (Grapple, Shove,
Dash, Disengage, Dodge, Help, Unarmed Strike, Off-Hand Attack, Escape Grapple,
Opportunity Attack) by key, plus a discovery endpoint listing every available
action with its description and cost.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine.combat import Encounter
from app.engine import combat_actions

router = APIRouter()


class CombatActionRequest(BaseModel):
    """Request to perform a combat action."""

    combatant_id: str
    action: str  # one of the keys in combat_actions.ACTIONS
    target_id: str | None = None  # required for target-requiring actions
    option: str | None = None  # e.g. shove: "prone" or "push"


def _load_active_encounter(save: GameSave) -> tuple[dict, Encounter]:
    """Parse a game save's combat state into the raw dict and Encounter."""
    import json

    game_state = json.loads(save.game_state)
    if not game_state.get("in_combat", False):
        raise HTTPException(status_code=400, detail="Not in combat")
    encounter = Encounter.from_dict(game_state.get("combat", {}))
    return game_state, encounter


def _persist_encounter(save: GameSave, game_state: dict, encounter: Encounter, db: Session) -> None:
    """Write the encounter back to the save and mirror player HP to the character."""
    import json

    game_state["combat"] = encounter.to_dict()
    player = next((c for c in encounter.combatants if c.id == "player"), None)
    if player is not None:
        save.character.current_hp = player.current_hp
    save.game_state = json.dumps(game_state)
    save.updated_at = datetime.utcnow()
    db.commit()


@router.get("/{game_id}/combat/actions")
def list_actions(game_id: int, db: Session = Depends(get_db)):
    """List all available combat actions with their metadata."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")
    return {"actions": combat_actions.list_actions()}


@router.post("/{game_id}/combat/action")
def perform_action(
    game_id: int,
    request: CombatActionRequest,
    db: Session = Depends(get_db),
):
    """Perform a combat action (Grapple, Shove, Dash, Disengage, Dodge, Help,
    Unarmed Strike, Off-Hand Attack, Escape Grapple, or Opportunity Attack)."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state, encounter = _load_active_encounter(save)

    actor = next((c for c in encounter.combatants if c.id == request.combatant_id), None)
    if actor is None:
        raise HTTPException(
            status_code=404, detail=f"Combatant {request.combatant_id} not found"
        )

    target = None
    if request.target_id:
        target = next((c for c in encounter.combatants if c.id == request.target_id), None)
        if target is None:
            raise HTTPException(
                status_code=404, detail=f"Target {request.target_id} not found"
            )

    try:
        outcome = combat_actions.perform_action(
            encounter=encounter,
            combatant=actor,
            action=request.action,
            target=target,
            option=request.option,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    _persist_encounter(save, game_state, encounter, db)

    return {
        "result": outcome["action_result"],
        "attack_result": outcome.get("attack_result"),
        "encounter": encounter.to_dict(),
        "combat_active": encounter.is_active,
        "winner": encounter.winner if not encounter.is_active else None,
    }
