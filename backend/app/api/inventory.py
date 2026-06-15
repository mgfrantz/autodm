"""
Inventory API — manage character inventory, equipment, and loot.

Provides endpoints for:
- Getting character inventory
- Adding/removing items
- Equipping/unequipping equipment
- Using consumable items
- Managing loot from enemies
"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import Character
from app.engine.inventory import (
    Item,
    Inventory,
    InventorySlot,
    ItemType,
    create_weapon,
    create_armor,
    create_potion,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class ItemCreate(BaseModel):
    """Request to create/add an item."""
    name: str
    item_type: ItemType
    description: str = ""
    rarity: str = "common"
    value: int = 0
    weight: float = 1.0
    
    # Weapon/Armor specific
    damage_dice: str = ""  # e.g., "1d8"
    damage_type: str = ""
    attack_bonus: int = 0
    armor_type: str = ""
    armor_bonus: int = 0
    dex_limit: int | None = None
    
    # Consumables
    uses: int = 1
    
    quantity: int = 1


class ItemResponse(BaseModel):
    """Response model for an item."""
    id: str
    name: str
    item_type: str
    description: str
    rarity: str
    value: int
    weight: float
    damage_dice_count: int
    damage_dice_sides: int
    damage_bonus: int
    damage_type: str
    attack_bonus: int
    armor_type: str | None
    armor_bonus: int
    dex_limit: int | None
    uses: int
    max_uses: int
    quantity: int
    
    class Config:
        from_attributes = True


class InventorySlotResponse(BaseModel):
    """Response model for an inventory slot."""
    item: ItemResponse
    equipped: bool


class InventoryResponse(BaseModel):
    """Response model for full inventory."""
    slots: list[InventorySlotResponse]
    total_weight: float
    total_value: int
    equipped_armor: ItemResponse | None
    equipped_weapon: ItemResponse | None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _load_inventory(character: Character) -> Inventory:
    """Load inventory from character's JSON storage."""
    try:
        data = json.loads(character.inventory)
    except (json.JSONDecodeError, TypeError):
        data = {"slots": []}
    return Inventory.from_dict(data)


def _save_inventory(character: Character, inventory: Inventory) -> None:
    """Save inventory to character's JSON storage."""
    character.inventory = json.dumps(inventory.to_dict())


def _item_to_response(item: Item) -> ItemResponse:
    """Convert Item to ItemResponse."""
    return ItemResponse(
        id=item.id,
        name=item.name,
        item_type=item.item_type.value,
        description=item.description,
        rarity=item.rarity.value,
        value=item.value,
        weight=item.weight,
        damage_dice_count=item.damage_dice_count,
        damage_dice_sides=item.damage_dice_sides,
        damage_bonus=item.damage_bonus,
        damage_type=item.damage_type,
        attack_bonus=item.attack_bonus,
        armor_type=item.armor_type.value if item.armor_type else None,
        armor_bonus=item.armor_bonus,
        dex_limit=item.dex_limit,
        uses=item.uses,
        max_uses=item.max_uses,
        quantity=item.quantity,
    )


def _slot_to_response(slot: InventorySlot) -> InventorySlotResponse:
    """Convert InventorySlot to InventorySlotResponse."""
    return InventorySlotResponse(
        item=_item_to_response(slot.item),
        equipped=slot.equipped,
    )


def _inventory_to_response(inventory: Inventory) -> InventoryResponse:
    """Convert Inventory to InventoryResponse."""
    return InventoryResponse(
        slots=[_slot_to_response(s) for s in inventory.slots],
        total_weight=inventory.total_weight,
        total_value=inventory.total_value,
        equipped_armor=_item_to_response(inventory.equipped_armor) if inventory.equipped_armor else None,
        equipped_weapon=_item_to_response(inventory.equipped_weapon) if inventory.equipped_weapon else None,
    )


def _create_item_from_request(request: ItemCreate) -> Item:
    """Create an Item from ItemCreate request."""
    # Parse damage dice if provided
    damage_dice_count = 0
    damage_dice_sides = 0
    if request.damage_dice:
        parts = request.damage_dice.lower().split("d")
        if len(parts) >= 2:
            damage_dice_count = int(parts[0]) if parts[0].isdigit() else 1
            damage_dice_sides = int(parts[1]) if parts[1].isdigit() else 6
    
    # Convert armor type string to enum if provided
    armor_type = None
    if request.armor_type:
        from app.engine.inventory import ArmorType
        try:
            armor_type = ArmorType(request.armor_type.lower())
        except ValueError:
            pass
    
    # Convert rarity string to enum
    from app.engine.inventory import Rarity
    rarity = Rarity(request.rarity.lower())
    
    return Item(
        id="",  # Auto-generated
        name=request.name,
        item_type=request.item_type,
        description=request.description,
        rarity=rarity,
        value=request.value,
        weight=request.weight,
        damage_dice_count=damage_dice_count,
        damage_dice_sides=damage_dice_sides,
        damage_bonus=0,
        damage_type=request.damage_type,
        attack_bonus=request.attack_bonus,
        armor_type=armor_type,
        armor_bonus=request.armor_bonus,
        dex_limit=request.dex_limit,
        uses=request.uses,
        max_uses=request.uses,
        quantity=request.quantity,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/{character_id}", response_model=InventoryResponse)
def get_inventory(character_id: int, db: Session = Depends(get_db)):
    """Get a character's full inventory."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    
    inventory = _load_inventory(character)
    return _inventory_to_response(inventory)


@router.post("/{character_id}/items", response_model=InventoryResponse)
def add_item(character_id: int, request: ItemCreate, db: Session = Depends(get_db)):
    """Add an item to a character's inventory."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    
    inventory = _load_inventory(character)
    item = _create_item_from_request(request)
    inventory.add_item(item)
    
    _save_inventory(character, inventory)
    character.updated_at = datetime.utcnow()
    db.commit()
    
    return _inventory_to_response(inventory)


@router.delete("/{character_id}/items/{item_id}", response_model=InventoryResponse)
def remove_item(character_id: int, item_id: str, quantity: int = 1, db: Session = Depends(get_db)):
    """Remove an item (or quantity) from inventory."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    
    inventory = _load_inventory(character)
    success = inventory.remove_item(item_id, quantity)
    
    if not success:
        raise HTTPException(status_code=400, detail="Item not found or insufficient quantity")
    
    _save_inventory(character, inventory)
    character.updated_at = datetime.utcnow()
    db.commit()
    
    return _inventory_to_response(inventory)


@router.post("/{character_id}/equip/{item_id}", response_model=InventoryResponse)
def equip_item(character_id: int, item_id: str, db: Session = Depends(get_db)):
    """Equip an item (weapon or armor)."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    
    inventory = _load_inventory(character)
    equipped = inventory.equip_item(item_id)
    
    if not equipped:
        raise HTTPException(status_code=400, detail="Item not found or not equippable")
    
    # Update character AC based on equipped armor
    equipped_armor = inventory.equipped_armor
    if equipped_armor:
        from app.engine.dice import ability_modifier
        dex_mod = ability_modifier(character.dexterity)
        new_ac = equipped_armor.get_ac_bonus(dex_mod)
        character.armor_class = new_ac
    
    _save_inventory(character, inventory)
    character.updated_at = datetime.utcnow()
    db.commit()
    
    return _inventory_to_response(inventory)


@router.post("/{character_id}/unequip/{item_id}", response_model=InventoryResponse)
def unequip_item(character_id: int, item_id: str, db: Session = Depends(get_db)):
    """Unequip an item."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    
    inventory = _load_inventory(character)
    success = inventory.unequip_item(item_id)
    
    if not success:
        raise HTTPException(status_code=400, detail="Item not found")
    
    # Recalculate AC without armor
    equipped_armor = inventory.equipped_armor
    if equipped_armor:
        from app.engine.dice import ability_modifier
        dex_mod = ability_modifier(character.dexterity)
        new_ac = equipped_armor.get_ac_bonus(dex_mod)
        character.armor_class = new_ac
    else:
        # No armor - base AC (10 + Dex mod, or unarmored defense for monks/barbarians)
        from app.engine.dice import ability_modifier
        dex_mod = ability_modifier(character.dexterity)
        char_class_lower = character.char_class.lower()
        if char_class_lower == "monk":
            # Unarmored defense: 10 + Dex + Wis
            wis_mod = ability_modifier(character.wisdom)
            character.armor_class = 10 + dex_mod + wis_mod
        elif char_class_lower == "barbarian":
            # Unarmored defense: 10 + Dex + Con
            con_mod = ability_modifier(character.constitution)
            character.armor_class = 10 + dex_mod + con_mod
        else:
            # Standard: 10 + Dex
            character.armor_class = 10 + dex_mod
    
    _save_inventory(character, inventory)
    character.updated_at = datetime.utcnow()
    db.commit()
    
    return _inventory_to_response(inventory)


@router.post("/{character_id}/use/{item_id}")
def use_item(character_id: int, item_id: str, db: Session = Depends(get_db)):
    """Use a consumable item (potion, scroll)."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    
    inventory = _load_inventory(character)
    success, message = inventory.use_item(item_id)
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    # Handle potion effects (simple MVP implementation)
    item = inventory.get_item(item_id)
    if item and "healing" in item.name.lower():
        # Apply healing: 2d4+2
        from app.engine.dice import roll_dice
        healing = roll_dice(2, 4, 2).total
        character.current_hp = min(character.max_hp, character.current_hp + healing)
        message += f" (Healed for {healing} HP)"
    
    _save_inventory(character, inventory)
    character.updated_at = datetime.utcnow()
    db.commit()
    
    return {
        "success": True,
        "message": message,
        "current_hp": character.current_hp,
        "max_hp": character.max_hp,
    }


@router.post("/{character_id}/initialize")
def initialize_inventory(character_id: int, db: Session = Depends(get_db)):
    """Initialize a character's inventory with starting equipment based on class."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    
    from app.engine.inventory import get_starting_inventory
    inventory = get_starting_inventory(character.char_class)
    
    # Update AC based on starting armor
    equipped_armor = inventory.equipped_armor
    if equipped_armor:
        from app.engine.dice import ability_modifier
        dex_mod = ability_modifier(character.dexterity)
        character.armor_class = equipped_armor.get_ac_bonus(dex_mod)
    
    _save_inventory(character, inventory)
    character.updated_at = datetime.utcnow()
    db.commit()
    
    return {
        "message": f"Initialized inventory for {character.char_class}",
        "items_count": len(inventory.slots),
        "inventory": _inventory_to_response(inventory),
    }