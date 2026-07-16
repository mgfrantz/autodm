"""
Downtime Activities REST API — PHB ch.8 + XGE ch.2 between-adventures system.

Mounts under ``/api/game``. Turns the pure :mod:`app.engine.downtime` rules into
game-scoped endpoints that:

- derive sensible default check/save modifiers from the character's real
  ability scores + proficiency (the caller can override every die/modifier for
  full DM adjudication),
- apply the activity's **gold delta** to the character's purse (402 if a spend
  would bankrupt them),
- apply **exhaustion** changes (Relaxation / Religion ease a level) to
  ``game_state['exhaustion']``,
- grant a **language or tool proficiency** when Training completes,
- and log the narration (+ any complication) to the story log.

Endpoints:
- GET  /{game_id}/downtime/activities
      All available downtime activities (id/name/source/category/description).
- GET  /{game_id}/downtime/activities/{activity_id}
      A single activity's detail (404 if unknown).
- POST /{game_id}/downtime/resolve
      Resolve one downtime activity, persisting all side effects. Returns the
      full DowntimeResult plus the character's new gold / exhaustion.
"""
from __future__ import annotations

import json
from app.utils.time_utils import utcnow
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine import downtime as dt
from app.engine import dice
from app.engine import skills as skills_engine

router = APIRouter()


# --------------------------------------------------------------------------- #
# Persistence helpers (mirror the social / starvation routers)
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


# --------------------------------------------------------------------------- #
# Character-derived defaults
# --------------------------------------------------------------------------- #

_ABILITY_ATTRS = {
    "strength": "strength",
    "dexterity": "dexterity",
    "constitution": "constitution",
    "intelligence": "intelligence",
    "wisdom": "wisdom",
    "charisma": "charisma",
}


def _ability_mod(save: GameSave, ability: str) -> int:
    attr = _ABILITY_ATTRS.get((ability or "").strip().lower())
    if not attr:
        return 0
    try:
        return dice.ability_modifier(int(getattr(save.character, attr, 10) or 10))
    except (TypeError, ValueError):
        return 0


def _all_ability_mods(save: GameSave) -> dict[str, int]:
    return {ab: _ability_mod(save, ab) for ab in _ABILITY_ATTRS}


def _proficiency(save: GameSave) -> int:
    try:
        level = int(save.character.level or 1)
    except (TypeError, ValueError):
        level = 1
    return dice.proficiency_bonus(max(1, level))


def _skill_mod(save: GameSave, skill: str) -> int:
    """The character's full skill modifier, falling back to the raw ability."""
    try:
        return int(skills_engine.calculate_skill_modifier(skill, save.character))
    except (ValueError, AttributeError, TypeError):
        return 0


def _exhaustion(game_state: dict) -> int:
    val = game_state.get("exhaustion")
    try:
        return max(0, min(6, int(val)))
    except (TypeError, ValueError):
        return 0


# --------------------------------------------------------------------------- #
# Response schemas
# --------------------------------------------------------------------------- #

class ActivitySummary(BaseModel):
    id: str
    name: str
    source: str
    category: str
    description: str
    min_days: int
    gold_per_day: int
    requires_tool: Optional[str] = None
    requires_profession_tool: bool = False


class ActivityListResponse(BaseModel):
    activities: list[ActivitySummary]


class DowntimeResolveRequest(BaseModel):
    activity: str = Field(..., description="Downtime activity id (carousing, crime, ...).")
    # Shared knobs
    modifier: Optional[int] = Field(
        default=None, description="Override the check modifier; defaults to character-derived."
    )
    dc: Optional[int] = Field(default=None, ge=1, description="Override the DC.")
    days: Optional[int] = Field(default=None, ge=0)
    workweeks: Optional[int] = Field(default=None, ge=1)
    # Dice overrides (DM adjudication / determinism)
    roll: Optional[int] = Field(default=None, ge=1, le=20)
    rolls: Optional[list[int]] = Field(
        default=None, description="Explicit check dice (heist/games/pit/research)."
    )
    d6: Optional[int] = Field(default=None, ge=1, le=6, description="Complication trigger die.")
    complication_d20: Optional[int] = Field(default=None, ge=1, le=20)
    save_roll: Optional[int] = Field(default=None, ge=1, le=20)
    save_modifiers: Optional[dict[str, int]] = Field(default=None)
    # Per-activity params
    tier: Optional[str] = Field(default=None, description="Carousing tier: lower/middle/upper.")
    wager: Optional[int] = Field(default=None, ge=0, description="Gambling wager in gp.")
    games: Optional[int] = Field(default=None, ge=1, description="Number of gambling games.")
    max_payout: Optional[int] = Field(default=None, ge=0)
    casing_dc: Optional[int] = Field(default=None, ge=1)
    heist_dc: Optional[int] = Field(default=None, ge=1)
    heist_checks: Optional[int] = Field(default=None, ge=1)
    casing_modifier: Optional[int] = Field(default=None)
    heist_modifier: Optional[int] = Field(default=None)
    casing_roll: Optional[int] = Field(default=None, ge=1, le=20)
    heist_rolls: Optional[list[int]] = Field(
        default=None, description="Explicit heist check dice."
    )
    item_value: Optional[int] = Field(default=None, ge=0, description="Crafting item value gp.")
    progress_before: Optional[int] = Field(default=None, ge=0)
    has_proficiency: Optional[bool] = None
    proficiency_required: Optional[bool] = None
    target: Optional[str] = Field(default=None, description="Training target (tool/language id).")
    target_kind: Optional[str] = Field(default=None, description="tool | language")
    tool_proficiency: Optional[bool] = None
    conditions: Optional[list[str]] = None


class DowntimeResolveResponse(BaseModel):
    activity: str
    days: int
    gold_delta: int
    narration: str
    complication: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)
    character_gold: int
    exhaustion: Optional[int] = None
    proficiency_granted: Optional[str] = None


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

def _to_summary(a: dt.DowntimeActivityDef) -> ActivitySummary:
    return ActivitySummary(
        id=a.id, name=a.name, source=a.source, category=a.category,
        description=a.description, min_days=a.min_days,
        gold_per_day=a.gold_per_day, requires_tool=a.requires_tool,
        requires_profession_tool=a.requires_profession_tool,
    )


@router.get("/{game_id}/downtime/activities", response_model=ActivityListResponse)
def list_activities(game_id: int, db: Session = Depends(get_db)):
    """All available downtime activities."""
    _load_game(db, game_id)  # validate game exists
    return ActivityListResponse(activities=[_to_summary(a) for a in dt.list_activities()])


@router.get(
    "/{game_id}/downtime/activities/{activity_id}",
    response_model=ActivitySummary,
)
def get_activity(game_id: int, activity_id: str, db: Session = Depends(get_db)):
    """A single downtime activity's detail."""
    _load_game(db, game_id)
    a = dt.get_activity(activity_id)
    if not a:
        raise HTTPException(status_code=404, detail=f"Unknown activity: {activity_id}")
    return _to_summary(a)


# ---- per-activity default-modifier derivation ----------------------------- #

def _default_modifier(save: GameSave, activity: str, request: DowntimeResolveRequest) -> int:
    """Compute a sensible default check modifier per activity.

    Uses the character's relevant skill where one maps, else the ability +
    proficiency. The request's explicit ``modifier`` (or per-activity overrides)
    always win — this is only the fallback.
    """
    if request.modifier is not None:
        return request.modifier
    prof = _proficiency(save)
    mods = _all_ability_mods(save)
    if activity == "crime":
        return mods["dexterity"] + prof
    if activity == "gambling":
        # Insight/Perception-style; Wisdom + proficiency.
        return mods["wisdom"] + prof
    if activity == "pit_fighting":
        # Athletics (Str) + proficiency.
        return mods["strength"] + prof
    if activity == "research":
        # Arcana/Investigation → Intelligence + proficiency.
        return mods["intelligence"] + prof
    if activity == "religion":
        return mods["wisdom"] + prof
    return 0


@router.post("/{game_id}/downtime/resolve", response_model=DowntimeResolveResponse)
def resolve_downtime(
    game_id: int,
    request: DowntimeResolveRequest,
    db: Session = Depends(get_db),
):
    """Resolve one downtime activity, persisting all side effects.

    Applies the gold delta to the character (402 if a spend would bankrupt),
    exhaustion changes (Relaxation / Religion), and grants a language or tool
    proficiency when Training completes. All narration is logged to the story.
    """
    save = _load_game(db, game_id)
    activity = dt.get_activity(request.activity)
    if not activity:
        raise HTTPException(
            status_code=400, detail=f"Unknown downtime activity: {request.activity!r}"
        )

    game_state = _game_state(save)
    char = save.character
    mod = _default_modifier(save, activity.id, request)
    prof = _proficiency(save)
    current_exhaustion = _exhaustion(game_state)
    mods = _all_ability_mods(save)

    # Build the kwargs the resolver expects from the (sparse) request.
    a = activity.id
    result: dt.DowntimeResult

    if a == "carousing":
        save_mods = request.save_modifiers or {
            ab: mods[ab] for ab in ("constitution", "dexterity", "wisdom", "charisma")
        }
        result = dt.carouse(
            tier=request.tier or "middle",
            workweeks=request.workweeks or 1,
            save_modifier=mod,
            save_modifiers=save_mods,
            d6=request.d6,
            complication_d20=request.complication_d20,
            save_roll=request.save_roll,
        )

    elif a == "crime":
        result = dt.crime(
            casing_modifier=(
                request.casing_modifier if request.casing_modifier is not None
                else mod
            ),
            casing_dc=request.casing_dc or 15,
            heist_modifier=(
                request.heist_modifier if request.heist_modifier is not None
                else mod
            ),
            heist_dc=request.heist_dc or 15,
            heist_checks=request.heist_checks or 3,
            max_payout=request.max_payout if request.max_payout is not None else 1000,
            casing_roll=request.casing_roll,
            heist_rolls=request.heist_rolls,
            d6=request.d6,
            complication_d20=request.complication_d20,
        )

    elif a == "gambling":
        result = dt.gamble(
            wager=request.wager if request.wager is not None else 100,
            modifier=mod,
            dc=request.dc or 20,
            games=request.games or 3,
            rolls=request.rolls,
            d6=request.d6,
            complication_d20=request.complication_d20,
        )

    elif a == "pit_fighting":
        result = dt.pit_fight(
            modifier=mod,
            dc=request.dc or 15,
            rolls=request.rolls,
            d6=request.d6,
            complication_d20=request.complication_d20,
        )

    elif a == "research":
        result = dt.research(
            modifier=mod,
            dc=request.dc or 15,
            workweeks=request.workweeks or 1,
            cost_per_week=25,
            roll=request.roll,
        )

    elif a == "relaxation":
        result = dt.relax(
            days=request.days if request.days is not None else dt.WORKWEEK_DAYS,
            current_exhaustion=current_exhaustion,
            conditions=request.conditions,
        )

    elif a == "crafting":
        if request.item_value is None:
            raise HTTPException(
                status_code=400, detail="Crafting requires 'item_value' (gp)."
            )
        result = dt.craft(
            item_value=request.item_value,
            days=request.days if request.days is not None else 1,
            progress_before=request.progress_before or 0,
            proficiency_required=(
                request.proficiency_required if request.proficiency_required is not None
                else True
            ),
            has_proficiency=(
                request.has_proficiency if request.has_proficiency is not None
                else True
            ),
        )

    elif a == "profession":
        # Tool proficiency default: best guess from the character's tool list.
        tool_prof = request.tool_proficiency
        if tool_prof is None:
            try:
                tools = json.loads(char.tool_proficiencies or "[]")
                tool_prof = bool(tools)
            except (json.JSONDecodeError, TypeError):
                tool_prof = False
        result = dt.practice_profession(
            workweeks=request.workweeks or 1,
            tool_proficiency=tool_prof,
        )

    elif a == "work":
        result = dt.work(workweeks=request.workweeks or 1)

    elif a == "training":
        if not request.target:
            raise HTTPException(
                status_code=400, detail="Training requires a 'target' (tool/language id)."
            )
        result = dt.train(
            target=request.target,
            days=request.days if request.days is not None else dt.WORKWEEK_DAYS,
            progress_before=request.progress_before or 0,
            target_kind=request.target_kind or "tool",
        )

    elif a == "religion":
        result = dt.religion(
            modifier=mod,
            dc=request.dc or 15,
            current_exhaustion=current_exhaustion,
            roll=request.roll,
        )

    else:  # pragma: no cover — dispatch is exhaustive over the registry
        raise HTTPException(status_code=400, detail=f"Unsupported activity: {a}")

    # ---- apply side effects ----------------------------------------------- #

    # Gold: spend must not bankrupt the character.
    new_gold = int(char.gold or 0) + result.gold_delta
    if new_gold < 0:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Not enough gold for {activity.name}: have "
                f"{char.gold}, need {abs(result.gold_delta)}."
            ),
        )
    char.gold = new_gold

    # Exhaustion changes (Relaxation / Religion).
    exhaustion_after: Optional[int] = None
    if result.details.get("exhaustion_delta"):
        exhaustion_after = max(
            0, min(6, current_exhaustion + result.details["exhaustion_delta"])
        )
        game_state["exhaustion"] = exhaustion_after
        char.current_hp = char.current_hp  # death-at-6 left to the exhaustion API

    # Relaxation may clear transient conditions.
    if a == "relaxation" and result.details.get("remaining_conditions") is not None:
        game_state["conditions"] = result.details["remaining_conditions"]

    # Remember the last between-adventures activity for DM context + UI.
    game_state["downtime"] = {
        "activity": result.activity,
        "name": activity.name,
        "gold_after": new_gold,
        "when": utcnow().isoformat(),
    }

    # Training completion grants a language or tool proficiency.
    proficiency_granted: Optional[str] = None
    if a == "training" and result.details.get("complete"):
        target = result.details["target"]
        kind = result.details.get("target_kind", "tool")
        if kind == "language":
            langs = _load_json_list(char.languages)
            if target not in langs:
                langs.append(target)
            char.languages = json.dumps(langs)
        else:
            tools = _load_json_list(char.tool_proficiencies)
            if target not in tools:
                tools.append(target)
            char.tool_proficiencies = json.dumps(tools)
        proficiency_granted = target

    # Persist game_state + character.
    _persist(save, game_state, db)

    # Narration → story log (include the complication line, if any).
    story_lines = [result.narration]
    if result.complication:
        story_lines.append(f"Complication: {result.complication}")
    _log(save, " ".join(story_lines))
    db.commit()

    return DowntimeResolveResponse(
        activity=result.activity,
        days=result.days,
        gold_delta=result.gold_delta,
        narration=result.narration,
        complication=result.complication,
        details=result.details,
        character_gold=new_gold,
        exhaustion=exhaustion_after,
        proficiency_granted=proficiency_granted,
    )


def _load_json_list(raw: Optional[str]) -> list[str]:
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return [str(x) for x in data]
    except (json.JSONDecodeError, TypeError):
        pass
    return []
