"""
Attunement API — manage magic item attunement.

Endpoints (mounted under /api/game):
- POST /{game_id}/attune/{item_id}      — attune to an item (during short rest)
- POST /{game_id}/break-attunement/{item_id} — break attunement to an item
- GET  /{game_id}/attuned-items         — list all attuned items
- GET  /{game_id}/attunement-info/{item_id} — get attunement info for an item
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine.multiclassing import parse_classes
from app.engine.inventory import Inventory, InventorySlot
from app.engine.attunement import (
    attune_item,
    break_attunement,
    get_attunement_info,
    AttunementSlot,
    AttunementInfo,
    AttunementResult,
)

router = APIRouter()


# --------------------------------------------------------------------------- #
# Request / response models
# --------------------------------------------------------------------------- #

class AttunedItemResponse(BaseModel):
    item_id: str
    item_name: str
    attuned_at_round: int
    requires_specific_class: str | None


class AttunementInfoResponse(BaseModel):
    status: str
    requires_attunement: bool
    is_attuned: bool
    attunement_slots_used: int
    attunement_slots_max: int
    can_attune: bool
    attunement_reason: str


class AttunementResultResponse(BaseModel):
    success: bool
    message: str
    item_id: str
    item_name: str
    attunement_slots_used: int
    attunement_slots_max: int
    attuned_items: list[AttunedItemResponse]


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


def _load_inventory(character) -> Inventory:
    try:
        inventory_data = json.loads(character.inventory or "[]")
        return Inventory(items=[InventorySlot.from_dict(s) for s in inventory_data])
    except (json.JSONDecodeError, TypeError):
        return Inventory()


def _save_inventory(character, inventory: Inventory) -> None:
    character.inventory = json.dumps(inventory.to_dict())


def _load_attuned_items(game_state: dict) -> list[AttunementSlot]:
    """Load attuned items from game state."""
    try:
        attuned_data = game_state.get("attuned_items", [])
        return [AttunementSlot.from_dict(d) for d in attuned_data]
    except (json.JSONDecodeError, TypeError, KeyError):
        return []


def _save_attuned_items(game_state: dict, attuned_items: list[AttunementSlot]) -> None:
    """Save attuned items to game state."""
    game_state["attuned_items"] = [slot.to_dict() for slot in attuned_items]


def _log(save: GameSave, role: str, content: str) -> None:
    """Append a narration entry to the game's story log."""
    try:
        story_log = json.loads(save.story_log)
    except (json.JSONDecodeError, TypeError):
        story_log = []
    story_log.append({
        "role": role,
        "content": content,
    })
    save.story_log = json.dumps(story_log)


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.post("/{game_id}/attune/{item_id}", response_model=AttunementResultResponse)
def attune_to_item(game_id: int, item_id: str, db: Session = Depends(get_db)):
    """Attune to a magic item during a short rest."""
    save = _load_game(db, game_id)
    character = save.character
    game_state = json.loads(save.game_state)

    # Check if in combat
    if game_state.get("in_combat", False):
        raise HTTPException(status_code=400, detail="Cannot attune while in combat")

    # Load inventory
    inventory = _load_inventory(character)
    item = inventory.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found in inventory")

    # Load current attuned items
    attuned_items = _load_attuned_items(game_state)

    # Attempt attunement
    result: AttunementResult = attune_item(
        item=item.to_dict(),
        attuned_items=attuned_items,
        level=_total_level(save),
        primary_class=_primary_class(save),
        current_round=game_state.get("current_round", 0),
    )

    if result.success:
        # Save updated attuned items
        _save_attuned_items(game_state, result.attuned_items)
        save.game_state = json.dumps(game_state)
        _log(save, "system", result.message)
        save.updated_at = save.updated_at  # SQLAlchemy will update timestamp
        db.commit()

    return AttunementResultResponse(
        success=result.success,
        message=result.message,
        item_id=result.item_id,
        item_name=result.item_name,
        attunement_slots_used=result.attunement_slots_used,
        attunement_slots_max=result.attunement_slots_max,
        attuned_items=[
            AttunedItemResponse(
                item_id=slot.item_id,
                item_name=slot.item_name,
                attuned_at_round=slot.attuned_at_round,
                requires_specific_class=slot.requires_specific_class,
            )
            for slot in result.attuned_items
        ],
    )


@router.post("/{game_id}/break-attunement/{item_id}", response_model=AttunementResultResponse)
def break_item_attunement(game_id: int, item_id: str, db: Session = Depends(get_db)):
    """Break attunement to an item (can be done during a short rest)."""
    save = _load_game(db, game_id)
    game_state = json.loads(save.game_state)

    # Check if in combat
    if game_state.get("in_combat", False):
        raise HTTPException(status_code=400, detail="Cannot break attunement while in combat")

    # Load current attuned items
    attuned_items = _load_attuned_items(game_state)

    # Break attunement
    result: AttunementResult = break_attunement(item_id, attuned_items)

    if result.success:
        # Update max slots with current level
        result.attunement_slots_max = max_attunement_slots = len(result.attuned_items) + max(0, 3 - len(result.attuned_items))

        # Save updated attuned items
        _save_attuned_items(game_state, result.attuned_items)
        save.game_state = json.dumps(game_state)
        _log(save, "system", result.message)
        save.updated_at = save.updated_at
        db.commit()

        # Update result with correct max slots
        from app.engine.attunement import max_attunement_slots as calc_max_slots
        result.attunement_slots_max = calc_max_slots(_total_level(save), _primary_class(save))

    return AttunementResultResponse(
        success=result.success,
        message=result.message,
        item_id=result.item_id,
        item_name=result.item_name,
        attunement_slots_used=result.attunement_slots_used,
        attunement_slots_max=result.attunement_slots_max,
        attuned_items=[
            AttunedItemResponse(
                item_id=slot.item_id,
                item_name=slot.item_name,
                attuned_at_round=slot.attuned_at_round,
                requires_specific_class=slot.requires_specific_class,
            )
            for slot in result.attuned_items
        ],
    )


@router.get("/{game_id}/attuned-items", response_model=list[AttunedItemResponse])
def get_attuned_items(game_id: int, db: Session = Depends(get_db)):
    """List all currently attuned items."""
    save = _load_game(db, game_id)
    game_state = json.loads(save.game_state)

    attuned_items = _load_attuned_items(game_state)

    return [
        AttunedItemResponse(
            item_id=slot.item_id,
            item_name=slot.item_name,
            attuned_at_round=slot.attuned_at_round,
            requires_specific_class=slot.requires_specific_class,
        )
        for slot in attuned_items
    ]


@router.get("/{game_id}/attunement-info/{item_id}", response_model=AttunementInfoResponse)
def get_item_attunement_info(game_id: int, item_id: str, db: Session = Depends(get_db)):
    """Get detailed attunement information for a specific item."""
    save = _load_game(db, game_id)
    character = save.character
    game_state = json.loads(save.game_state)

    # Load inventory
    inventory = _load_inventory(character)
    item = inventory.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found in inventory")

    # Load current attuned items
    attuned_items = _load_attuned_items(game_state)

    # Get attunement info
    info: AttunementInfo = get_attunement_info(
        item=item.to_dict(),
        attuned_items=attuned_items,
        level=_total_level(save),
        primary_class=_primary_class(save),
    )

    return AttunementInfoResponse(
        status=info.status.value,
        requires_attunement=info.requires_attunement,
        is_attuned=info.is_attuned,
        attunement_slots_used=info.attunement_slots_used,
        attunement_slots_max=info.attunement_slots_max,
        can_attune=info.can_attune,
        attunement_reason=info.attunement_reason,
    )