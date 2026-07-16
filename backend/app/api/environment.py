"""
Environment API — exposes the environmental-conditions engine via REST.

Each game carries an ``Environment`` snapshot inside ``game_state["environment"]``.
The endpoints let a DM (or the player) inspect the current scene, set its
conditions, view the derived mechanical effects, and roll procedural weather.

Routes (mounted under ``/api/game``):

    GET  /environment/registry              — all light/weather/terrain/temp/time options
    GET  /{game_id}/environment             — the current environment + effects
    PUT  /{game_id}/environment             — set the environment (partial updates allowed)
    POST /{game_id}/environment/effects     — compute effects for a candidate environment
    POST /{game_id}/environment/roll        — roll procedural weather/temperature
"""
import json
import random
from app.utils.time_utils import utcnow
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine import environment as env_engine

router = APIRouter()


# --------------------------------------------------------------------------- #
# Request / response models.
# --------------------------------------------------------------------------- #

class EnvironmentUpdate(BaseModel):
    """A partial environment update. Any omitted field is left unchanged."""

    light: Optional[str] = None
    weather: Optional[str] = None
    terrain: Optional[str] = None
    temperature: Optional[str] = None
    time_of_day: Optional[str] = None
    notes: Optional[str] = None


class EnvironmentProbe(BaseModel):
    """A candidate environment to evaluate (no persistence)."""

    light: str = "bright"
    weather: str = "clear"
    terrain: str = "normal"
    temperature: str = "normal"
    time_of_day: str = "day"


class EnvironmentRoll(BaseModel):
    """Roll procedural weather for a climate/season."""

    climate: str = "temperate"
    season: str = "summer"
    time_of_day: str = "day"
    seed: Optional[int] = None


def _validate_choice(value: str, valid: tuple[str, ...], field_name: str) -> str:
    if value not in valid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {field_name} {value!r}; must be one of {list(valid)}",
        )
    return value


def _load_environment(game_state: dict) -> env_engine.Environment:
    raw = game_state.get("environment")
    return env_engine.Environment.from_dict(raw)


def _store_environment(game_state: dict, env: env_engine.Environment) -> None:
    game_state["environment"] = env.to_dict()


def _get_game_or_404(db: Session, game_id: int) -> GameSave:
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")
    return save


def _env_response(env: env_engine.Environment) -> dict:
    return {
        "environment": env.to_dict(),
        "effects": env_engine.compute_effects(env).to_dict(),
    }


# --------------------------------------------------------------------------- #
# Discovery.
# --------------------------------------------------------------------------- #

@router.get("/environment/registry")
def registry() -> dict:
    """Return every light/weather/terrain/temperature/time option for the UI."""
    return {
        "light_levels": env_engine.list_light_levels(),
        "weather": env_engine.list_weather(),
        "terrain": env_engine.list_terrain(),
        "temperature": env_engine.list_temperatures(),
        "time_of_day": env_engine.list_times_of_day(),
        "climates": list(env_engine.CLIMATES),
        "seasons": list(env_engine.SEASONS),
    }


# --------------------------------------------------------------------------- #
# Per-game environment.
# --------------------------------------------------------------------------- #

@router.get("/{game_id}/environment")
def get_environment(game_id: int, db: Session = Depends(get_db)) -> dict:
    """Return the current environment and its derived effects."""
    save = _get_game_or_404(db, game_id)
    game_state = json.loads(save.game_state or "{}")
    env = _load_environment(game_state)
    return _env_response(env)


@router.put("/{game_id}/environment")
def set_environment(
    game_id: int,
    update: EnvironmentUpdate,
    db: Session = Depends(get_db),
) -> dict:
    """Set or partially update the game's environment."""
    save = _get_game_or_404(db, game_id)
    game_state = json.loads(save.game_state or "{}")
    env = _load_environment(game_state)

    if update.light is not None:
        env.light = _validate_choice(update.light, env_engine.LIGHT_LEVELS, "light")
    if update.weather is not None:
        env.weather = _validate_choice(update.weather, env_engine.WEATHER_TYPES, "weather")
    if update.terrain is not None:
        env.terrain = _validate_choice(update.terrain, env_engine.TERRAIN_TYPES, "terrain")
    if update.temperature is not None:
        env.temperature = _validate_choice(
            update.temperature, env_engine.TEMPERATURE_LEVELS, "temperature"
        )
    if update.time_of_day is not None:
        env.time_of_day = _validate_choice(
            update.time_of_day, env_engine.TIME_OF_DAY, "time_of_day"
        )
    if update.notes is not None:
        env.notes = update.notes

    _store_environment(game_state, env)
    save.game_state = json.dumps(game_state)
    save.updated_at = utcnow()
    db.commit()

    return _env_response(env)


@router.post("/{game_id}/environment/effects")
def compute_effects_endpoint(
    game_id: int,
    probe: EnvironmentProbe,
    db: Session = Depends(get_db),
) -> dict:
    """Compute the effects of a candidate environment without persisting it.

    Useful for the DM/UI to preview what a change would do before applying it.
    """
    # Confirm the game exists.
    _get_game_or_404(db, game_id)
    env = env_engine.Environment(
        light=_validate_choice(probe.light, env_engine.LIGHT_LEVELS, "light"),
        weather=_validate_choice(probe.weather, env_engine.WEATHER_TYPES, "weather"),
        terrain=_validate_choice(probe.terrain, env_engine.TERRAIN_TYPES, "terrain"),
        temperature=_validate_choice(
            probe.temperature, env_engine.TEMPERATURE_LEVELS, "temperature"
        ),
        time_of_day=_validate_choice(
            probe.time_of_day, env_engine.TIME_OF_DAY, "time_of_day"
        ),
    )
    return {
        "environment": env.to_dict(),
        "effects": env_engine.compute_effects(env).to_dict(),
    }


@router.post("/{game_id}/environment/roll")
def roll_environment(
    game_id: int,
    request: EnvironmentRoll,
    db: Session = Depends(get_db),
) -> dict:
    """Roll procedural weather and temperature for a climate/season.

    Persists the result (weather + temperature + ambient light) as the game's
    environment, preserving the existing terrain and notes.
    """
    if request.climate not in env_engine.CLIMATES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid climate {request.climate!r}; must be one of {list(env_engine.CLIMATES)}",
        )
    if request.season not in env_engine.SEASONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid season {request.season!r}; must be one of {list(env_engine.SEASONS)}",
        )
    if request.time_of_day not in env_engine.TIME_OF_DAY:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid time_of_day {request.time_of_day!r}; must be one of {list(env_engine.TIME_OF_DAY)}",
        )

    save = _get_game_or_404(db, game_id)
    game_state = json.loads(save.game_state or "{}")
    existing = _load_environment(game_state)

    rng = random.Random(request.seed) if request.seed is not None else random
    env = env_engine.roll_environment(
        climate=request.climate,
        season=request.season,
        time_of_day=request.time_of_day,
        rng=rng,
    )
    # Preserve terrain and notes from the existing scene.
    env.terrain = existing.terrain
    env.notes = existing.notes

    _store_environment(game_state, env)
    save.game_state = json.dumps(game_state)
    save.updated_at = utcnow()
    db.commit()

    return {
        "message": (
            f"Rolled weather for {request.climate} {request.season}: "
            f"{env.weather}, {env.temperature}."
        ),
        "environment": env.to_dict(),
        "effects": env_engine.compute_effects(env).to_dict(),
    }


# --------------------------------------------------------------------------- #
# Combat-modifier convenience (pure, no persistence).
# --------------------------------------------------------------------------- #

@router.post("/{game_id}/environment/combat-modifiers")
def combat_modifiers_endpoint(
    game_id: int,
    attack_is_ranged: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    """Return the environment's situational modifiers for a single attack."""
    save = _get_game_or_404(db, game_id)
    game_state = json.loads(save.game_state or "{}")
    env = _load_environment(game_state)
    mods = env_engine.combat_modifiers(env, attack_is_ranged=attack_is_ranged)
    return {"modifiers": mods.to_dict(), "environment": env.to_dict()}
