"""
Loot API — randomized treasure drops, hoards, and pending-loot collection.

When an enemy with a Challenge Rating dies in combat, individual treasure is
rolled automatically and staged in the game's ``pending_loot`` ledger (see
``app/api/combat.py``). This router exposes:

* ``GET  /{game_id}/loot/tables``        — inspect the loot tables (DM info)
* ``GET  /{game_id}/loot/pending``       — view staged loot awaiting collection
* ``POST /{game_id}/loot/collect``       — claim pending loot into inventory+gold
* ``POST /{game_id}/loot/individual``    — roll individual treasure for a CR
* ``POST /{game_id}/loot/hoard``         — roll a hoard (boss/chest) for a CR
* ``POST /{game_id}/loot/chest``         — roll a treasure chest by tier

Collecting loot converts coins to gold pieces on the character and adds items
to the character's inventory, then logs the haul to the story.
"""
from __future__ import annotations

import json
from app.utils.time_utils import utcnow

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine import loot as loot_engine
from app.engine.inventory import Inventory
from app.api.inventory import (
    _load_inventory,
    _save_inventory,
    _item_to_response,
    _inventory_to_response,
)

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


def _log(save: GameSave, role: str, content: str) -> None:
    """Append a narration entry to the game's story log."""
    try:
        story_log = json.loads(save.story_log)
    except (json.JSONDecodeError, TypeError):
        story_log = []
    story_log.append({
        "role": role,
        "content": content,
        "timestamp": utcnow().isoformat(),
    })
    save.story_log = json.dumps(story_log)


def _pending_loot(state: dict) -> dict:
    """Return the pending-loot ledger (coins + items), creating it if absent."""
    pending = state.get("pending_loot")
    if not isinstance(pending, dict):
        pending = {
            "coins": {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0},
            "items": [],
        }
        state["pending_loot"] = pending
    return pending


def _loot_narration(result: loot_engine.LootResult, action: str) -> str:
    """Build a story-log line describing a loot haul."""
    parts: list[str] = []
    gold = result.gold_total
    if gold:
        parts.append(f"{gold:g} gp in coins")
    if result.items:
        item_names: list[str] = []
        for item in result.items:
            label = item.name
            if item.quantity > 1:
                label = f"{item.quantity}x {label}"
            item_names.append(label)
        parts.append(", ".join(item_names))
    summary = " and ".join(parts) if parts else "nothing of value"
    return f"{action}: {summary}."


def _apply_loot_to_character(
    save: GameSave,
    state: dict,
    result: loot_engine.LootResult,
    db: Session,
) -> dict:
    """Add a loot result's coins + items to the character, persist, and log.

    Returns a dict describing what was gained (for the API response).
    """
    character = save.character
    inventory = _load_inventory(character)
    if inventory is None:
        inventory = Inventory()

    gold_gained = 0.0
    if not result.coins.is_empty():
        # Convert coins to whole gold pieces (floor), rounding per DMG rates.
        gold_gained = result.coins.total_gp()
        whole_gold = int(gold_gained)
        if whole_gold > 0:
            character.gold = (character.gold or 0) + whole_gold

    for item in result.items:
        inventory.add_item(item)

    _save_inventory(character, inventory)
    save.game_state = json.dumps(state)
    _log(save, "system", _loot_narration(result, "You found"))
    character.updated_at = utcnow()
    save.updated_at = utcnow()
    db.commit()
    db.refresh(character)

    return {
        "gold_gained": gold_gained,
        "gold_total": character.gold or 0,
        "items": [_item_to_response(item).model_dump() for item in result.items],
        "inventory": _inventory_to_response(inventory).model_dump(),
    }


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #

class CRLootRequest(BaseModel):
    """Roll loot for a Challenge Rating."""
    cr: float
    seed: int | None = None  # optional, for deterministic rolls


class ChestLootRequest(BaseModel):
    """Roll a treasure chest by tier."""
    tier: str = "common"  # common | uncommon | rare | legendary
    seed: int | None = None


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("/loot/tables")
def get_loot_tables():
    """Inspect the loot tables (CR tiers, coin rolls, chest tiers, magic tables)."""
    return loot_engine.loot_table_overview()


@router.get("/{game_id}/loot/pending")
def get_pending_loot(game_id: int, db: Session = Depends(get_db)):
    """View loot staged from combat kills, awaiting collection."""
    save = _load_game(db, game_id)
    state = _game_state(save)
    pending = _pending_loot(state)
    coins = pending.get("coins", {})
    items = pending.get("items", [])

    # Compute gold-equivalent value of the pending coins.
    purse = loot_engine.CoinPurse(
        cp=coins.get("cp", 0),
        sp=coins.get("sp", 0),
        ep=coins.get("ep", 0),
        gp=coins.get("gp", 0),
        pp=coins.get("pp", 0),
    )
    return {
        "has_loot": purse.total_gp() > 0 or bool(items),
        "coins": purse.to_dict(),
        "items": items,
        "item_count": len(items),
    }


@router.post("/{game_id}/loot/collect")
def collect_pending_loot(game_id: int, db: Session = Depends(get_db)):
    """Collect all staged (pending) loot into the character's inventory + gold.

    Clears the pending ledger afterwards. Returns the haul details.
    """
    save = _load_game(db, game_id)
    state = _game_state(save)
    if state.get("in_combat", False):
        raise HTTPException(status_code=400, detail="Collect loot after combat ends")

    pending = _pending_loot(state)
    coins = pending.get("coins", {})
    purse = loot_engine.CoinPurse(
        cp=coins.get("cp", 0),
        sp=coins.get("sp", 0),
        ep=coins.get("ep", 0),
        gp=coins.get("gp", 0),
        pp=coins.get("pp", 0),
    )
    items = []
    for raw in pending.get("items", []):
        try:
            from app.engine.inventory import Item
            items.append(Item.from_dict(raw))
        except Exception:
            # Skip malformed item entries rather than failing the collection.
            continue

    result = loot_engine.LootResult(coins=purse, items=items, source="pending")

    if result.is_empty:
        return {
            "message": "No loot to collect",
            "has_loot": False,
            "gold_gained": 0,
            "gold_total": save.character.gold or 0,
            "items": [],
        }

    applied = _apply_loot_to_character(save, state, result, db)

    # Clear the pending ledger now that it has been collected.
    state = _game_state(save)
    state["pending_loot"] = {
        "coins": {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0},
        "items": [],
    }
    save.game_state = json.dumps(state)
    save.updated_at = utcnow()
    db.commit()

    return {
        "message": "Loot collected",
        "has_loot": False,
        "loot": result.to_dict(),
        **applied,
    }


@router.post("/{game_id}/loot/individual")
def roll_individual(game_id: int, request: CRLootRequest, db: Session = Depends(get_db)):
    """Roll individual treasure for a CR and immediately add it to the character.

    Useful as a DM tool (e.g. a creature that drops coins outside combat) or
    for ad-hoc treasure. For in-combat kills, loot is staged automatically.
    """
    save = _load_game(db, game_id)
    state = _game_state(save)
    rng = loot_engine.random.Random(request.seed) if request.seed is not None else None
    result = loot_engine.roll_individual_loot(request.cr, rng)
    if result.is_empty:
        return {"message": "No treasure found", "loot": result.to_dict()}
    applied = _apply_loot_to_character(save, state, result, db)
    return {"loot": result.to_dict(), **applied}


@router.post("/{game_id}/loot/hoard")
def roll_hoard(game_id: int, request: CRLootRequest, db: Session = Depends(get_db)):
    """Roll a treasure hoard for a CR and add it to the character.

    A hoard combines coins, gems/art objects, and magic items — ideal for
    cleared encounters, bosses, and treasure rooms.
    """
    save = _load_game(db, game_id)
    state = _game_state(save)
    rng = loot_engine.random.Random(request.seed) if request.seed is not None else None
    result = loot_engine.roll_hoard_loot(request.cr, rng)
    if result.is_empty:
        return {"message": "The hoard is empty", "loot": result.to_dict()}
    applied = _apply_loot_to_character(save, state, result, db)
    return {"loot": result.to_dict(), **applied}


@router.post("/{game_id}/loot/chest")
def roll_chest(game_id: int, request: ChestLootRequest, db: Session = Depends(get_db)):
    """Roll a standalone treasure chest by difficulty tier and add it to the character."""
    save = _load_game(db, game_id)
    state = _game_state(save)
    if request.tier.lower() not in loot_engine.CHEST_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown chest tier '{request.tier}'. "
                   f"Choose from: {', '.join(loot_engine.CHEST_TIERS)}",
        )
    rng = loot_engine.random.Random(request.seed) if request.seed is not None else None
    result = loot_engine.roll_chest_loot(request.tier, rng)
    applied = _apply_loot_to_character(save, state, result, db)
    return {"loot": result.to_dict(), **applied}
