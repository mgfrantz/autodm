"""
Starvation & dehydration REST API — daily food/water survival tracking.

Mounts under ``/api/game``. The survival *drivers* (consecutive days of
inadequate food/water) and the resulting exhaustion are persisted inside
``game_state`` so they round-trip through save/load.

Endpoints:
- GET  /{game_id}/survival
      Current survival state, deficit summary, and exhaustion level.
- POST /{game_id}/survival/advance
      Resolve one day of food/water intake. Applies any exhaustion inflicted
      (clamped to 0–6; reaching 6 is fatal, HP → 0). Optionally auto-detects
      'hot' weather from the stored environment.
- POST /{game_id}/survival/reset
      Reset the deprivation counters to zero (the character has restocked).
"""
from __future__ import annotations

import json
from app.utils.time_utils import utcnow

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine import starvation as surv
from app.engine import exhaustion as exhaust
from app.engine.dice import ability_modifier, proficiency_bonus
from app.engine import saving_throws

router = APIRouter()


# --------------------------------------------------------------------------- #
# Helpers (mirror the exhaustion router's persistence pattern)
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


def _survival_state(game_state: dict) -> surv.SurvivalState:
    return surv.SurvivalState.from_dict(game_state.get("survival"))


def _con_modifier(save: GameSave) -> int:
    return ability_modifier(int(getattr(save.character, "constitution", 10) or 10))


def _con_save_bonus(save: GameSave) -> int:
    """CON modifier + proficiency bonus if the character is a proficient CON saver."""
    bonus = _con_modifier(save)
    char = save.character
    profs = saving_throws.get_saving_throw_proficiencies(char)
    if "constitution" in profs:
        level = getattr(char, "level", 1) or 1
        bonus += proficiency_bonus(level)
    return bonus


def _environment_temperature(game_state: dict) -> str:
    env = game_state.get("environment")
    if isinstance(env, dict):
        return env.get("temperature", "normal") or "normal"
    return "normal"


# --------------------------------------------------------------------------- #
# Response schemas
# --------------------------------------------------------------------------- #

class SurvivalResponse(BaseModel):
    character_id: int
    exhaustion: int
    state: dict
    deficit: dict
    daily_needs: dict


class AdvanceRequest(BaseModel):
    food_lbs: float = Field(
        default=surv.DAILY_FOOD_LBS, ge=0, description="Pounds of food consumed today."
    )
    water_gal: float = Field(
        default=surv.DAILY_WATER_GAL, ge=0, description="Gallons of water consumed today."
    )
    hot: bool | None = Field(
        default=None,
        description="Whether weather is hot (doubles water need). Auto-detected from "
        "the stored environment when omitted.",
    )
    save_roll: int | None = Field(
        default=None, ge=1, le=20,
        description="An explicit d20 result for the dehydration save (DM-adjudicated). "
        "Rolled automatically when omitted.",
    )


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("/{game_id}/survival")
def get_survival(game_id: int, db: Session = Depends(get_db)):
    """Current survival state, deficit summary, and exhaustion level."""
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    state = _survival_state(game_state)
    con_mod = _con_modifier(save)
    hot = surv.is_hot(_environment_temperature(game_state))
    level = int(game_state.get("exhaustion", 0) or 0)
    return SurvivalResponse(
        character_id=save.character_id,
        exhaustion=level,
        state=state.to_dict(),
        deficit=surv.deficit_summary(state, con_mod, hot),
        daily_needs=surv.daily_needs(hot),
    )


@router.post("/{game_id}/survival/advance")
def advance_survival(
    game_id: int,
    request: AdvanceRequest,
    db: Session = Depends(get_db),
):
    """Resolve one day of food/water intake and apply any exhaustion inflicted.

    The dehydration save uses the character's full Constitution save bonus
    (CON modifier + proficiency bonus when proficient). Reaching exhaustion
    level 6 is fatal: the character's HP drops to 0.
    """
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    state = _survival_state(game_state)
    con_mod = _con_modifier(save)

    hot = request.hot
    if hot is None:
        hot = surv.is_hot(_environment_temperature(game_state))

    current_exhaustion = int(game_state.get("exhaustion", 0) or 0)
    result = surv.advance_day(
        state,
        food_lbs=request.food_lbs,
        water_gal=request.water_gal,
        hot=hot,
        con_modifier=con_mod,
        save_bonus=_con_save_bonus(save),
        save_roll=request.save_roll,
        current_exhaustion=current_exhaustion,
    )

    # Persist the updated drivers.
    game_state["survival"] = result.state.to_dict()

    # Apply the exhaustion delta (clamp + death handling), mirroring the
    # exhaustion router so the two systems stay in sync.
    before = current_exhaustion
    game_state["exhaustion"] = result.new_exhaustion
    died = result.died
    if died:
        save.character.current_hp = 0
        save.character.updated_at = utcnow()

    # Narrate the day.
    name = save.character.name
    if result.exhaustion_added > 0:
        summary = (
            f"{name} endures a day of deprivation "
            f"(food: {request.food_lbs} lb, water: {request.water_gal} gal) "
            f"and suffers {result.exhaustion_added} level(s) of exhaustion "
            f"— now level {result.new_exhaustion}."
        )
    else:
        summary = (
            f"{name} gets by for a day "
            f"(food: {request.food_lbs} lb, water: {request.water_gal} gal) "
            f"without ill effect."
        )
    _log(save, summary)
    for msg in result.messages:
        _log(save, msg)
    if died:
        _log(save, f"{name} succumbs to deprivation (exhaustion level 6) and dies.")

    _persist(save, game_state, db)
    db.refresh(save.character)

    body = result.to_dict()
    body.update({
        "character_id": save.character_id,
        "exhaustion_before": before,
        "exhaustion_after": result.new_exhaustion,
        "changed": result.exhaustion_added > 0,
        "hot": hot,
        "deficit": surv.deficit_summary(result.state, con_mod, hot),
        "character": {
            "current_hp": save.character.current_hp,
            "max_hp": save.character.max_hp,
        },
        **exhaust.level_effects(result.new_exhaustion),
    })
    return body


@router.post("/{game_id}/survival/reset")
def reset_survival(game_id: int, db: Session = Depends(get_db)):
    """Reset the food/water deprivation counters to zero.

    Use this when the character has restocked provisions and resumes normal
    rations (the underlying exhaustion must still be recovered by resting).
    """
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    fresh = surv.SurvivalState()
    game_state["survival"] = fresh.to_dict()
    _persist(save, game_state, db)
    con_mod = _con_modifier(save)
    hot = surv.is_hot(_environment_temperature(game_state))
    return SurvivalResponse(
        character_id=save.character_id,
        exhaustion=int(game_state.get("exhaustion", 0) or 0),
        state=fresh.to_dict(),
        deficit=surv.deficit_summary(fresh, con_mod, hot),
        daily_needs=surv.daily_needs(hot),
    )
