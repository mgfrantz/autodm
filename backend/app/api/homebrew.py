"""
Homebrew content API — create, list, and manage custom items.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, ConfigDict

from app.models.database import get_db
from app.models.models import HomebrewItem
from app.engine.inventory import Item, ItemType, Rarity, ArmorType

router = APIRouter(tags=["homebrew"])


# Pydantic models for API
class HomebrewItemCreate(BaseModel):
    """Schema for creating a new homebrew item."""
    name: str = Field(..., min_length=1, max_length=100)
    item_type: str = Field(..., description="Item type: weapon, armor, potion, scroll, misc, quest")
    description: str = Field(default="", max_length=2000)
    rarity: str = Field(default="common", description="Rarity: common, uncommon, rare, very_rare, legendary")
    value: int = Field(default=0, ge=0)
    weight: float = Field(default=1.0, ge=0)
    # Weapon/Armor stats
    damage_dice_count: int = Field(default=0, ge=0)
    damage_dice_sides: int = Field(default=0, ge=0)
    damage_bonus: int = Field(default=0)
    damage_type: str = Field(default="")
    attack_bonus: int = Field(default=0)
    armor_type: Optional[str] = Field(default=None)
    armor_bonus: int = Field(default=0)
    dex_limit: Optional[int] = Field(default=None)
    # Consumable stats
    uses: int = Field(default=1, ge=1)
    max_uses: int = Field(default=1, ge=1)
    quantity: int = Field(default=1, ge=1)
    # Metadata
    creator_name: Optional[str] = Field(default=None, max_length=100)

    def to_item_dict(self) -> dict:
        """Convert to Item-compatible dictionary."""
        return {
            "id": "",  # Will be generated
            "name": self.name,
            "item_type": ItemType(self.item_type),
            "description": self.description,
            "rarity": Rarity(self.rarity),
            "value": self.value,
            "weight": self.weight,
            "damage_dice_count": self.damage_dice_count,
            "damage_dice_sides": self.damage_dice_sides,
            "damage_bonus": self.damage_bonus,
            "damage_type": self.damage_type,
            "attack_bonus": self.attack_bonus,
            "armor_type": ArmorType(self.armor_type) if self.armor_type else None,
            "armor_bonus": self.armor_bonus,
            "dex_limit": self.dex_limit,
            "uses": self.uses,
            "max_uses": self.max_uses,
            "quantity": self.quantity,
        }


class HomebrewItemResponse(BaseModel):
    """Schema for homebrew item responses."""
    id: int
    name: str
    item_type: str
    description: str
    rarity: str
    stats: dict
    creator_name: Optional[str]
    created_at: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class HomebrewItemUpdate(BaseModel):
    """Schema for updating a homebrew item."""
    description: Optional[str] = Field(None, max_length=2000)
    rarity: Optional[str] = Field(None)
    value: Optional[int] = Field(None, ge=0)
    weight: Optional[float] = Field(None, ge=0)
    damage_dice_count: Optional[int] = Field(None, ge=0)
    damage_dice_sides: Optional[int] = Field(None, ge=0)
    damage_bonus: Optional[int] = Field(None)
    damage_type: Optional[str] = Field(None)
    attack_bonus: Optional[int] = Field(None)
    armor_type: Optional[str] = Field(None)
    armor_bonus: Optional[int] = Field(None)
    dex_limit: Optional[int] = Field(None)
    uses: Optional[int] = Field(None, ge=1)
    max_uses: Optional[int] = Field(None, ge=1)
    quantity: Optional[int] = Field(None, ge=1)


@router.post("/items", response_model=HomebrewItemResponse, status_code=201)
def create_homebrew_item(item: HomebrewItemCreate, db: Session = Depends(get_db)):
    """Create a new homebrew item."""
    # Validate item type and rarity
    try:
        ItemType(item.item_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid item_type: {item.item_type}")

    try:
        Rarity(item.rarity)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid rarity: {item.rarity}")

    # Validate armor type if provided
    if item.armor_type:
        try:
            ArmorType(item.armor_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid armor_type: {item.armor_type}")

    # Convert to Item to validate stats
    item_dict = item.to_item_dict()
    try:
        validated_item = Item(**item_dict)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid item configuration: {str(e)}")

    # Create database record
    homebrew_item = HomebrewItem.from_item_dict(item_dict, item.creator_name)
    db.add(homebrew_item)
    db.commit()
    db.refresh(homebrew_item)

    return homebrew_item.to_dict()


@router.get("/items", response_model=List[HomebrewItemResponse])
def list_homebrew_items(
    item_type: Optional[str] = None,
    rarity: Optional[str] = None,
    creator: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all homebrew items, optionally filtered by type, rarity, or creator."""
    query = db.query(HomebrewItem)

    if item_type:
        try:
            ItemType(item_type)
            query = query.filter(HomebrewItem.item_type == item_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid item_type: {item_type}")

    if rarity:
        try:
            Rarity(rarity)
            query = query.filter(HomebrewItem.rarity == rarity)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid rarity: {rarity}")

    if creator:
        query = query.filter(HomebrewItem.creator_name == creator)

    items = query.order_by(HomebrewItem.created_at.desc()).all()
    return [item.to_dict() for item in items]


@router.get("/items/{item_id}", response_model=HomebrewItemResponse)
def get_homebrew_item(item_id: int, db: Session = Depends(get_db)):
    """Get a specific homebrew item by ID."""
    item = db.query(HomebrewItem).filter(HomebrewItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Homebrew item not found")

    return item.to_dict()


@router.put("/items/{item_id}", response_model=HomebrewItemResponse)
def update_homebrew_item(item_id: int, update: HomebrewItemUpdate, db: Session = Depends(get_db)):
    """Update a homebrew item (non-mutable fields like name/type cannot be changed)."""
    item = db.query(HomebrewItem).filter(HomebrewItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Homebrew item not found")

    import json

    # Parse existing stats
    stats_data = json.loads(item.stats)

    # Update provided fields
    if update.description is not None:
        item.description = update.description
        stats_data["description"] = update.description
    if update.rarity is not None:
        try:
            Rarity(update.rarity)
            item.rarity = update.rarity
            stats_data["rarity"] = update.rarity
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid rarity: {update.rarity}")
    if update.value is not None:
        stats_data["value"] = update.value
    if update.weight is not None:
        stats_data["weight"] = update.weight
    if update.damage_dice_count is not None:
        stats_data["damage_dice_count"] = update.damage_dice_count
    if update.damage_dice_sides is not None:
        stats_data["damage_dice_sides"] = update.damage_dice_sides
    if update.damage_bonus is not None:
        stats_data["damage_bonus"] = update.damage_bonus
    if update.damage_type is not None:
        stats_data["damage_type"] = update.damage_type
    if update.attack_bonus is not None:
        stats_data["attack_bonus"] = update.attack_bonus
    if update.armor_type is not None:
        try:
            if update.armor_type:
                ArmorType(update.armor_type)
            stats_data["armor_type"] = update.armor_type
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid armor_type: {update.armor_type}")
    if update.armor_bonus is not None:
        stats_data["armor_bonus"] = update.armor_bonus
    if update.dex_limit is not None:
        stats_data["dex_limit"] = update.dex_limit
    if update.uses is not None:
        stats_data["uses"] = update.uses
    if update.max_uses is not None:
        stats_data["max_uses"] = update.max_uses
    if update.quantity is not None:
        stats_data["quantity"] = update.quantity

    # Validate updated item
    try:
        Item(**stats_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid item configuration: {str(e)}")

    # Save updated stats
    item.stats = json.dumps(stats_data)
    db.commit()
    db.refresh(item)

    return item.to_dict()


@router.delete("/items/{item_id}", status_code=204)
def delete_homebrew_item(item_id: int, db: Session = Depends(get_db)):
    """Delete a homebrew item."""
    item = db.query(HomebrewItem).filter(HomebrewItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Homebrew item not found")

    db.delete(item)
    db.commit()

    return None