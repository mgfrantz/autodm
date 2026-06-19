"""
Rest API — short rests and long rests during an active game.

Endpoints (mounted under /api/game):
- GET  /{game_id}/rest            — Hit-Dice pool, HP, and caster status overview
- POST /{game_id}/short-rest      — spend Hit Dice to heal on a short rest
- POST /{game_id}/long-rest       — full HP, recover Hit Dice + spell slots, clear restable conditions
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine.dice import ability_modifier
from app.engine.multiclassing import parse_classes
from app.engine import rest as rest_engine
from app.engine.rest import ShortRestResult, LongRestResult
from app.api.spells import _load_spellbook, _save_spellbook

router = APIRouter()


# --------------------------------------------------------------------------- #
# Request / response models
# --------------------------------------------------------------------------- #

class ShortRestRequest(BaseModel):
    num_dice: int | None = None  # how many Hit Dice to spend (default: until full or exhausted)


class RestInfoResponse(BaseModel):
    character_id: int
    character_name: str
    level: int
    primary_class: str
    constitution_modifier: int
    current_hp: int
    max_hp: int
    hit_dice_total: int
    hit_dice_available: int
    hit_dice_used: int
    hit_die_size: int
    is_caster: bool


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _load_game(db: Session, game_id: int) -> GameSave:
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")
    return save


def _total_level(save: GameSave) -> int:
    classes = parse_classes(save.character.classes or "{}")
    if classes:
        return sum(classes.values())
    return save.character.level or 1


def _primary_class(save: GameSave) -> str:
    return save.character.primary_class or (save.character.char_class or "fighter").lower()


def _con_mod(save: GameSave) -> int:
    return ability_modifier(save.character.constitution or 10)


def _is_caster(save: GameSave) -> bool:
    try:
        return _load_spellbook(save.character).is_caster
    except Exception:  # noqa: BLE001 — non-caster / uninitialised spellbook
        return False


def _log(save: GameSave, role: str, content: str) -> None:
    """Append a narration entry to the game's story log."""
    try:
        story_log = json.loads(save.story_log)
    except (json.JSONDecodeError, TypeError):
        story_log = []
    story_log.append({
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat(),
    })
    save.story_log = json.dumps(story_log)


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("/{game_id}/rest", response_model=RestInfoResponse)
def get_rest_info(game_id: int, db: Session = Depends(get_db)):
    """Overview of the character's rest-relevant resources."""
    save = _load_game(db, game_id)
    character = save.character
    level = _total_level(save)
    return RestInfoResponse(
        character_id=character.id,
        character_name=character.name,
        level=level,
        primary_class=_primary_class(save),
        constitution_modifier=_con_mod(save),
        current_hp=character.current_hp or 0,
        max_hp=character.max_hp or 0,
        hit_dice_total=rest_engine.total_hit_dice(level),
        hit_dice_available=rest_engine.available_hit_dice(level, character.hit_dice_used or 0),
        hit_dice_used=character.hit_dice_used or 0,
        hit_die_size=rest_engine.hit_die_size(_primary_class(save)),
        is_caster=_is_caster(save),
    )


@router.post("/{game_id}/short-rest")
def short_rest(game_id: int, request: ShortRestRequest | None = None, db: Session = Depends(get_db)):
    """Take a short rest: spend Hit Dice to regain HP.

    Body ``num_dice`` (optional) chooses how many dice to spend; omit it to
    spend dice until HP is full or the pool is exhausted. Spent dice are added
    to the character's ``hit_dice_used`` tally and recovered on a long rest.
    """
    save = _load_game(db, game_id)
    character = save.character
    game_state = json.loads(save.game_state)

    if game_state.get("in_combat", False):
        raise HTTPException(status_code=400, detail="Cannot rest while in combat")

    num_dice = request.num_dice if request is not None else None

    result: ShortRestResult = rest_engine.short_rest(
        char_class=_primary_class(save),
        level=_total_level(save),
        current_hp=character.current_hp or 0,
        max_hp=character.max_hp or 0,
        hit_dice_used=character.hit_dice_used or 0,
        con_mod=_con_mod(save),
        num_dice=num_dice,
    )

    if result.success:
        character.current_hp = result.hp_after
        character.hit_dice_used = (character.hit_dice_used or 0) + result.hit_dice_spent
        character.updated_at = datetime.utcnow()
        _log(save, "system", f"Short rest: {result.message}")
        save.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(character)

    return {
        "type": "short_rest",
        **result.to_dict(),
        "character": {
            "current_hp": character.current_hp,
            "max_hp": character.max_hp,
            "hit_dice_used": character.hit_dice_used,
        },
    }


@router.post("/{game_id}/long-rest")
def long_rest(game_id: int, db: Session = Depends(get_db)):
    """Take a long rest: full HP, recover Hit Dice + spell slots, clear conditions."""
    save = _load_game(db, game_id)
    character = save.character
    game_state = json.loads(save.game_state)

    if game_state.get("in_combat", False):
        raise HTTPException(status_code=400, detail="Cannot rest while in combat")

    is_caster = _is_caster(save)
    current_conditions = list(game_state.get("conditions", []) or [])
    current_exhaustion = int(game_state.get("exhaustion", 0) or 0)

    result: LongRestResult = rest_engine.long_rest(
        char_class=_primary_class(save),
        level=_total_level(save),
        current_hp=character.current_hp or 0,
        max_hp=character.max_hp or 0,
        hit_dice_used=character.hit_dice_used or 0,
        is_caster=is_caster,
        conditions=current_conditions,
        exhaustion=current_exhaustion,
    )

    # --- Apply HP ---------------------------------------------------------
    character.current_hp = result.hp_after
    character.hit_dice_used = result.hit_dice_used_after

    # --- Recover spell slots ---------------------------------------------
    slots_overview = None
    if is_caster:
        spellbook = _load_spellbook(character)
        spellbook.long_rest()
        _save_spellbook(character, spellbook)
        slots_overview = spellbook.slots_overview()

    # --- Clear restable conditions ---------------------------------------
    if result.conditions_cleared:
        remaining = [c for c in current_conditions if c not in result.conditions_cleared]
        game_state["conditions"] = remaining

    # --- Reduce exhaustion by one level (PHB long-rest recovery) ---------
    if result.exhaustion_reduced:
        game_state["exhaustion"] = result.exhaustion_after

    if result.conditions_cleared or result.exhaustion_reduced:
        save.game_state = json.dumps(game_state)

    character.updated_at = datetime.utcnow()
    _log(save, "system", result.message)
    save.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(character)

    return {
        "type": "long_rest",
        **result.to_dict(),
        "character": {
            "current_hp": character.current_hp,
            "max_hp": character.max_hp,
            "hit_dice_used": character.hit_dice_used,
        },
        "conditions": game_state.get("conditions", []),
        "exhaustion": game_state.get("exhaustion", 0),
        "spell_slots": slots_overview,
    }
