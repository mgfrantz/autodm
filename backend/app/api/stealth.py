"""
Stealth API — expose hide/detect mechanics.

Endpoints:
- POST /{game_id}/combat/stealth/hide — attempt to hide
- GET /{game_id}/combat/stealth/status — get stealth status
- GET /{game_id}/combat/stealth/visible — get visible enemies
- POST /{game_id}/combat/stealth/reveal/{id} — reveal a combatant (manual)
"""
from app.utils.time_utils import utcnow

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import Character, GameSave
from app.engine.combat import Encounter
from app.engine import stealth as stealth_engine
from app.engine import skills

router = APIRouter()


class HideRequest(BaseModel):
    """Request to attempt a Hide action."""

    combatant_id: str
    rolls: list[int] | None = None  # for testing


class HideResponse(BaseModel):
    """Response from a Hide attempt."""

    combatant_id: str
    result: dict  # HideResult.to_dict()


class StealthStatusResponse(BaseModel):
    """Stealth status for a combatant."""

    combatant_id: str
    status: dict  # stealth_engine.get_stealth_status()


class VisibleEnemiesResponse(BaseModel):
    """Visible enemies for the player."""

    observer_passive_perception: int
    enemies: dict[str, dict]  # id -> StealthCheckResult.to_dict()


class RevealRequest(BaseModel):
    """Request to manually reveal a combatant."""

    reason: str = "manual"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
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
    save.updated_at = utcnow()
    db.commit()


def _get_combatant_or_404(encounter: Encounter, combatant_id: str):
    """Get a combatant by ID or raise 404."""
    for c in encounter.combatants:
        if c.id == combatant_id:
            return c
    raise HTTPException(status_code=404, detail=f"Combatant {combatant_id} not found")


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.post("/{game_id}/combat/stealth/hide")
def attempt_hide(
    game_id: int,
    request: HideRequest,
    db: Session = Depends(get_db),
):
    """Attempt the Hide action.

    Makes a Dexterity (Stealth) check. On success, the combatant becomes hidden.
    The stealth DC is set to the roll total (for detection via passive Perception).
    """
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state, encounter = _load_active_encounter(save)

    actor = _get_combatant_or_404(encounter, request.combatant_id)

    # Get character for skill modifier (only applies to player)
    character = None
    if actor.id == "player":
        character = save.character

    try:
        result = stealth_engine.attempt_hide(
            combatant=actor,
            character=character,
            rolls=request.rolls,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    encounter.log.append(result.description)
    _persist_encounter(save, game_state, encounter, db)

    return HideResponse(
        combatant_id=request.combatant_id,
        result=result.to_dict(),
    )


@router.get("/{game_id}/combat/stealth/status/{combatant_id}")
def get_stealth_status(
    game_id: int,
    combatant_id: str,
    db: Session = Depends(get_db),
):
    """Get the stealth status of a combatant."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    _, encounter = _load_active_encounter(save)
    combatant = _get_combatant_or_404(encounter, combatant_id)

    status = stealth_engine.get_stealth_status(combatant)

    return StealthStatusResponse(
        combatant_id=combatant_id,
        status=status,
    )


@router.get("/{game_id}/combat/stealth/visible")
def get_visible_enemies(
    game_id: int,
    db: Session = Depends(get_db),
):
    """Get which enemies are visible to the player (detected by passive Perception).

    Returns all enemies with their detection status.
    """
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    _, encounter = _load_active_encounter(save)

    # Get player's passive Perception
    passive_perception = skills.calculate_passive_score("perception", save.character)

    # Check visibility of all enemies
    visible_enemies = stealth_engine.list_visible_enemies(
        combatants=encounter.combatants,
        observer_passive_perception=passive_perception,
        enemy_side="enemy",
    )

    return VisibleEnemiesResponse(
        observer_passive_perception=passive_perception,
        enemies={k: v.to_dict() for k, v in visible_enemies.items()},
    )


@router.post("/{game_id}/combat/stealth/reveal/{combatant_id}")
def reveal_combatant(
    game_id: int,
    combatant_id: str,
    request: RevealRequest | None = None,
    db: Session = Depends(get_db),
):
    """Manually reveal a combatant (clear hidden state).

    Typically called when a hidden combatant takes an action that reveals them
    (though attacks auto-reveal via the combat engine).
    """
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state, encounter = _load_active_encounter(save)
    combatant = _get_combatant_or_404(encounter, combatant_id)

    if not stealth_engine.is_hidden(combatant):
        raise HTTPException(status_code=400, detail=f"Combatant {combatant_id} is not hidden")

    stealth_engine.reveal(combatant)
    reason = request.reason if request else "manual"
    encounter.log.append(f"{combatant.name} reveals themselves ({reason}).")

    _persist_encounter(save, game_state, encounter, db)

    return {
        "combatant_id": combatant_id,
        "hidden": False,
        "message": f"{combatant.name} is no longer hidden.",
    }