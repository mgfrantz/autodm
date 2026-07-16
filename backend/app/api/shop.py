"""
Shop / economy API — merchants, buying, and selling during an active game.

Merchants are generated lazily on first visit and their state (stock levels +
remaining gold) is persisted in the game's ``game_state`` JSON under the
``merchants`` key so the economy stays consistent across turns and saves.

Endpoints (mounted under /api/game):
* ``GET  /{game_id}/shop``                        — overview: gold + available merchants
* ``GET  /{game_id}/shop/{merchant_type}``        — a merchant's catalogue with buy prices
* ``POST /{game_id}/shop/{merchant_type}/buy``    — buy an item from the merchant
* ``POST /{game_id}/shop/{merchant_type}/sell``   — sell an owned item to the merchant
* ``POST /{game_id}/shop/{merchant_type}/restock`` — restock a merchant (stock + gold)
"""
from __future__ import annotations

import json
from app.utils.time_utils import utcnow

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine import shop as shop_engine
from app.engine.shop import (
    Merchant,
    TransactionResult,
    MERCHANT_TYPES,
    create_merchant,
    resolve_archetype,
)
from app.api.inventory import (
    _load_inventory,
    _save_inventory,
    _item_to_response,
    _inventory_to_response,
)

router = APIRouter()


# --------------------------------------------------------------------------- #
# Request / response models
# --------------------------------------------------------------------------- #

class TradeRequest(BaseModel):
    item_id: str
    quantity: int = 1


class StockEntryResponse(BaseModel):
    item: dict
    quantity: int
    buy_price: int  # gold the player must pay per unit


class MerchantResponse(BaseModel):
    name: str
    merchant_type: str
    label: str
    description: str
    settlement_tier: str
    gold: int
    stock: list[StockEntryResponse]


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


def _get_merchants_state(state: dict) -> dict:
    """Return the (mutable) merchants dict from game state, creating it if absent."""
    merchants = state.get("merchants")
    if not isinstance(merchants, dict):
        merchants = {}
        state["merchants"] = merchants
    return merchants


def _settlement_tier(state: dict) -> str:
    tier = state.get("settlement_tier")
    if isinstance(tier, str) and tier:
        return tier.lower()
    return shop_engine.DEFAULT_TIER


def _get_or_create_merchant(save: GameSave, state: dict, merchant_type: str) -> Merchant:
    """Load a merchant from game state, or generate it on first visit."""
    merchants = _get_merchants_state(state)
    archetype = resolve_archetype(merchant_type)
    key = archetype.key  # normalize (e.g. typo'd/unknown -> "general")

    if key in merchants and isinstance(merchants[key], dict):
        return Merchant.from_dict(merchants[key])

    merchant = create_merchant(key, settlement_tier=_settlement_tier(state))
    merchants[key] = merchant.to_dict()
    save.game_state = json.dumps(state)
    return merchant


def _persist_merchant(save: GameSave, state: dict, merchant: Merchant) -> None:
    merchants = _get_merchants_state(state)
    merchants[merchant.merchant_type] = merchant.to_dict()
    save.game_state = json.dumps(state)


def _stock_response(merchant: Merchant) -> list[StockEntryResponse]:
    out: list[StockEntryResponse] = []
    for entry in merchant.stock:
        out.append(StockEntryResponse(
            item=_item_to_response(entry.item).model_dump(),
            quantity=entry.quantity,
            buy_price=shop_engine.buy_price(entry.item, merchant.archetype),
        ))
    return out


def _merchant_response(merchant: Merchant) -> MerchantResponse:
    return MerchantResponse(
        name=merchant.name,
        merchant_type=merchant.merchant_type,
        label=merchant.archetype.label,
        description=merchant.archetype.description,
        settlement_tier=merchant.settlement_tier,
        gold=merchant.gold,
        stock=_stock_response(merchant),
    )


def _player_sellables(merchant: Merchant, inventory) -> list[dict]:
    """The player's inventory items with the price THIS merchant would pay.

    Items the merchant doesn't deal in are flagged ``merchant_buys=False`` with a
    sell price of 0 so the UI can grey them out.
    """
    out: list[dict] = []
    for slot in inventory.slots:
        item = slot.item
        buys = merchant.archetype.buys_type(item.item_type)
        out.append({
            "item": _item_to_response(item).model_dump(),
            "quantity": item.quantity,
            "equipped": slot.equipped,
            "merchant_buys": buys,
            "sell_price": shop_engine.sell_price(item, merchant.archetype) if buys else 0,
        })
    return out


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("/{game_id}/shop")
def get_shop_overview(game_id: int, db: Session = Depends(get_db)):
    """Overview: the character's gold and the merchants available here."""
    save = _load_game(db, game_id)
    state = _game_state(save)
    character = save.character
    tier = _settlement_tier(state)
    merchants_present = _get_merchants_state(state)

    available = []
    for key, arch in MERCHANT_TYPES.items():
        available.append({
            "merchant_type": key,
            "label": arch.label,
            "description": arch.description,
            "visited": key in merchants_present,
        })

    return {
        "character_id": character.id,
        "character_name": character.name,
        "gold": character.gold or 0,
        "settlement_tier": tier,
        "merchants": available,
    }


@router.get("/{game_id}/shop/{merchant_type}")
def get_merchant(game_id: int, merchant_type: str, db: Session = Depends(get_db)):
    """Get a merchant's catalogue (generates the merchant on first visit).

    The response includes the merchant's stock (with buy prices) *and* the
    player's inventory priced for sale to this specific merchant, so the UI can
    render buy and sell tabs from a single fetch.
    """
    save = _load_game(db, game_id)
    state = _game_state(save)
    character = save.character
    merchant = _get_or_create_merchant(save, state, merchant_type)
    # Persist creation + commit (idempotent if already present).
    _persist_merchant(save, state, merchant)
    save.updated_at = utcnow()
    db.commit()

    inventory = _load_inventory(character)
    return {
        **_merchant_response(merchant).model_dump(),
        "player_inventory": _player_sellables(merchant, inventory),
    }


@router.post("/{game_id}/shop/{merchant_type}/buy")
def buy_item(
    game_id: int,
    merchant_type: str,
    request: TradeRequest,
    db: Session = Depends(get_db),
):
    """Buy an item from a merchant: player spends gold, gains the item."""
    save = _load_game(db, game_id)
    state = _game_state(save)

    if state.get("in_combat", False):
        raise HTTPException(status_code=400, detail="Cannot trade while in combat")

    character = save.character
    merchant = _get_or_create_merchant(save, state, merchant_type)
    inventory = _load_inventory(character)

    result, gold_after = shop_engine.execute_buy(
        merchant, inventory, character.gold or 0,
        item_id=request.item_id, quantity=request.quantity,
    )

    if result.success:
        character.gold = gold_after
        _save_inventory(character, inventory)
        _persist_merchant(save, state, merchant)
        _log(save, "system", result.message)
        character.updated_at = utcnow()
        save.updated_at = utcnow()
        db.commit()
        db.refresh(character)

    return {
        **result.to_dict(),
        "gold": character.gold or 0,
        "inventory": _inventory_to_response(inventory).model_dump(),
    }


@router.post("/{game_id}/shop/{merchant_type}/sell")
def sell_item(
    game_id: int,
    merchant_type: str,
    request: TradeRequest,
    db: Session = Depends(get_db),
):
    """Sell an owned item to a merchant: player gains gold, loses the item."""
    save = _load_game(db, game_id)
    state = _game_state(save)

    if state.get("in_combat", False):
        raise HTTPException(status_code=400, detail="Cannot trade while in combat")

    character = save.character
    merchant = _get_or_create_merchant(save, state, merchant_type)
    inventory = _load_inventory(character)

    result, gold_after = shop_engine.execute_sell(
        merchant, inventory, character.gold or 0,
        item_id=request.item_id, quantity=request.quantity,
    )

    if result.success:
        character.gold = gold_after
        _save_inventory(character, inventory)
        _persist_merchant(save, state, merchant)
        _log(save, "system", result.message)
        character.updated_at = utcnow()
        save.updated_at = utcnow()
        db.commit()
        db.refresh(character)

    return {
        **result.to_dict(),
        "gold": character.gold or 0,
        "inventory": _inventory_to_response(inventory).model_dump(),
    }


@router.post("/{game_id}/shop/{merchant_type}/restock")
def restock_merchant(
    game_id: int,
    merchant_type: str,
    db: Session = Depends(get_db),
):
    """Restock a merchant's catalogue and restore its gold (DM utility)."""
    save = _load_game(db, game_id)
    state = _game_state(save)
    merchant = _get_or_create_merchant(save, state, merchant_type)

    summary = shop_engine.restock(merchant, restore_gold=True)
    _persist_merchant(save, state, merchant)
    _log(save, "system",
         f"{merchant.name} restocked their shelves (gold: {merchant.gold} gp).")
    save.updated_at = utcnow()
    db.commit()

    return {
        **summary,
        "name": merchant.name,
        "merchant": _merchant_response(merchant).model_dump(),
    }
