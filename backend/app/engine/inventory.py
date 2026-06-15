"""
Inventory engine — items, equipment, loot management.

Implements DnD-style inventory with:
- Item types: Weapon, Armor, Potion, Scroll, Misc
- Equipment slots (for armor and main hand)
- Value (in gold pieces), weight, rarity
- JSON serialization for persistence
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import uuid


class ItemType(str, Enum):
    """Types of items in the game."""
    WEAPON = "weapon"
    ARMOR = "armor"
    POTION = "potion"
    SCROLL = "scroll"
    MISC = "misc"
    QUEST = "quest"


class Rarity(str, Enum):
    """Item rarity tiers."""
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    VERY_RARE = "very_rare"
    LEGENDARY = "legendary"


class ArmorType(str, Enum):
    """Armor types with base AC values."""
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"
    SHIELD = "shield"


# Base AC values by armor type
ARMOR_BASE_AC = {
    ArmorType.LIGHT: 11,
    ArmorType.MEDIUM: 14,
    ArmorType.HEAVY: 16,
    ArmorType.SHIELD: 2,  # Additive bonus
}


@dataclass
class Item:
    """An item that can be held in inventory or equipped."""
    
    id: str
    name: str
    item_type: ItemType
    description: str = ""
    rarity: Rarity = Rarity.COMMON
    value: int = 0  # Gold pieces
    weight: float = 1.0  # Pounds
    
    # Weapon/Armor specific
    damage_dice_count: int = 0
    damage_dice_sides: int = 0
    damage_bonus: int = 0
    damage_type: str = ""
    attack_bonus: int = 0
    armor_type: Optional[ArmorType] = None
    armor_bonus: int = 0  # AC bonus
    dex_limit: Optional[int] = None  # Max Dex modifier for medium/heavy armor
    
    # Consumables
    uses: int = 1
    max_uses: int = 1
    
    quantity: int = 1  # Stackable items
    
    def __post_init__(self):
        # Generate UUID if no ID provided
        if not self.id:
            object.__setattr__(self, "id", str(uuid.uuid4()))
        
        # Set max_uses to uses if not set
        if self.max_uses < self.uses:
            object.__setattr__(self, "max_uses", self.uses)
    
    @property
    def is_equippable(self) -> bool:
        """Whether this item can be equipped to a slot."""
        return self.item_type in (ItemType.WEAPON, ItemType.ARMOR)
    
    @property
    def is_consumable(self) -> bool:
        """Whether this item is consumed on use."""
        return self.item_type in (ItemType.POTION, ItemType.SCROLL)
    
    @property
    def is_stackable(self) -> bool:
        """Whether multiple instances stack in one slot."""
        return self.item_type in (ItemType.POTION, ItemType.SCROLL, ItemType.MISC, ItemType.QUEST)
    
    @property
    def is_depleted(self) -> bool:
        """Whether a consumable has no uses left."""
        return self.uses <= 0
    
    def use(self) -> bool:
        """Use one charge of a consumable. Returns True if still has uses."""
        if not self.is_consumable or self.is_depleted:
            return False
        self.uses -= 1
        return self.uses > 0
    
    def get_ac_bonus(self, dex_mod: int) -> int:
        """Calculate AC bonus for armor, considering Dex limits."""
        if self.item_type != ItemType.ARMOR:
            return 0
        
        base = ARMOR_BASE_AC.get(self.armor_type, 0) if self.armor_type else 0
        bonus = self.armor_bonus
        
        if self.armor_type == ArmorType.LIGHT:
            return base + bonus + dex_mod
        elif self.armor_type == ArmorType.MEDIUM:
            applicable_dex = min(dex_mod, self.dex_limit or 2)
            return base + bonus + applicable_dex
        elif self.armor_type == ArmorType.HEAVY:
            # Heavy armor: no Dex bonus
            return base + bonus
        elif self.armor_type == ArmorType.SHIELD:
            # Shield is additive
            return bonus
        return base + bonus
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage."""
        data = {
            "id": self.id,
            "name": self.name,
            "item_type": self.item_type.value,
            "description": self.description,
            "rarity": self.rarity.value,
            "value": self.value,
            "weight": self.weight,
            "damage_dice_count": self.damage_dice_count,
            "damage_dice_sides": self.damage_dice_sides,
            "damage_bonus": self.damage_bonus,
            "damage_type": self.damage_type,
            "attack_bonus": self.attack_bonus,
            "armor_type": self.armor_type.value if self.armor_type else None,
            "armor_bonus": self.armor_bonus,
            "dex_limit": self.dex_limit,
            "uses": self.uses,
            "max_uses": self.max_uses,
            "quantity": self.quantity,
        }
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "Item":
        """Deserialize from dictionary."""
        armor_type = None
        if data.get("armor_type"):
            armor_type = ArmorType(data["armor_type"])
        
        return cls(
            id=data.get("id", ""),
            name=data["name"],
            item_type=ItemType(data["item_type"]),
            description=data.get("description", ""),
            rarity=Rarity(data.get("rarity", "common")),
            value=data.get("value", 0),
            weight=data.get("weight", 1.0),
            damage_dice_count=data.get("damage_dice_count", 0),
            damage_dice_sides=data.get("damage_dice_sides", 0),
            damage_bonus=data.get("damage_bonus", 0),
            damage_type=data.get("damage_type", ""),
            attack_bonus=data.get("attack_bonus", 0),
            armor_type=armor_type,
            armor_bonus=data.get("armor_bonus", 0),
            dex_limit=data.get("dex_limit"),
            uses=data.get("uses", 1),
            max_uses=data.get("max_uses", data.get("uses", 1)),
            quantity=data.get("quantity", 1),
        )


@dataclass
class InventorySlot:
    """A slot in inventory containing an item."""
    item: Item
    equipped: bool = False
    
    def to_dict(self) -> dict:
        return {
            "item": self.item.to_dict(),
            "equipped": self.equipped,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "InventorySlot":
        return cls(
            item=Item.from_dict(data["item"]),
            equipped=data.get("equipped", False),
        )


class Inventory:
    """A character's inventory with equipment management."""
    
    def __init__(self, items: Optional[list[InventorySlot]] = None) -> None:
        self.slots: list[InventorySlot] = list(items) if items else []
    
    @property
    def total_weight(self) -> float:
        """Calculate total weight of all items."""
        return sum(slot.item.weight * slot.item.quantity for slot in self.slots)
    
    @property
    def total_value(self) -> int:
        """Calculate total value of all items (in gold pieces)."""
        return sum(slot.item.value * slot.item.quantity for slot in self.slots)
    
    @property
    def equipped_armor(self) -> Optional[Item]:
        """Get the currently equipped armor."""
        for slot in self.slots:
            if slot.equipped and slot.item.item_type == ItemType.ARMOR:
                return slot.item
        return None
    
    @property
    def equipped_weapon(self) -> Optional[Item]:
        """Get the currently equipped weapon."""
        for slot in self.slots:
            if slot.equipped and slot.item.item_type == ItemType.WEAPON:
                return slot.item
        return None
    
    @property
    def equipped_items(self) -> list[Item]:
        """Get all equipped items."""
        return [slot.item for slot in self.slots if slot.equipped]
    
    def add_item(self, item: Item) -> InventorySlot:
        """Add an item to inventory. Try to stack if possible."""
        if item.is_stackable:
            # Try to stack with existing items of same type and name
            for slot in self.slots:
                if (slot.item.item_type == item.item_type and 
                    slot.item.name == item.name and
                    not slot.equipped):
                    slot.item.quantity += item.quantity
                    return slot
        
        # Create new slot
        slot = InventorySlot(item=item, equipped=False)
        self.slots.append(slot)
        return slot
    
    def remove_item(self, item_id: str, quantity: int = 1) -> bool:
        """Remove an item (or quantity) from inventory. Returns True if removed."""
        for i, slot in enumerate(self.slots):
            if slot.item.id == item_id:
                if slot.item.quantity > quantity:
                    slot.item.quantity -= quantity
                    return True
                elif slot.item.quantity == quantity:
                    self.slots.pop(i)
                    return True
                else:
                    # Not enough quantity
                    return False
        return False
    
    def get_item(self, item_id: str) -> Optional[Item]:
        """Get an item by ID."""
        for slot in self.slots:
            if slot.item.id == item_id:
                return slot.item
        return None
    
    def equip_item(self, item_id: str) -> Optional[Item]:
        """Equip an item. Unequip conflicting items. Returns the equipped item."""
        slot = next((s for s in self.slots if s.item.id == item_id), None)
        if not slot or not slot.item.is_equippable:
            return None
        
        item = slot.item
        
        # Unequip existing items of the same type
        if item.item_type == ItemType.WEAPON:
            for s in self.slots:
                if s.equipped and s.item.item_type == ItemType.WEAPON:
                    s.equipped = False
        elif item.item_type == ItemType.ARMOR:
            for s in self.slots:
                if s.equipped and s.item.item_type == ItemType.ARMOR:
                    s.equipped = False
        
        slot.equipped = True
        return item
    
    def unequip_item(self, item_id: str) -> bool:
        """Unequip an item. Returns True if successful."""
        slot = next((s for s in self.slots if s.item.id == item_id), None)
        if not slot:
            return False
        slot.equipped = False
        return True
    
    def use_item(self, item_id: str) -> tuple[bool, str]:
        """Use a consumable item. Returns (success, message)."""
        slot = next((s for s in self.slots if s.item.id == item_id), None)
        if not slot:
            return False, "Item not found"
        
        item = slot.item
        if not item.is_consumable:
            return False, "Item is not consumable"
        
        if item.is_depleted:
            # Remove depleted item
            self.remove_item(item_id)
            return False, "Item has no uses left"
        
        still_has_uses = item.use()
        message = f"Used {item.name}"
        
        if not still_has_uses:
            # Remove depleted item
            self.remove_item(item_id)
            message += f" (consumed)"
        
        return True, message
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage."""
        return {
            "slots": [slot.to_dict() for slot in self.slots],
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Inventory":
        """Deserialize from dictionary."""
        slots = [InventorySlot.from_dict(s) for s in data.get("slots", [])]
        return cls(items=slots)


# ---------------------------------------------------------------------------
# Helper: create common items
# ---------------------------------------------------------------------------

def create_weapon(
    name: str,
    damage_dice: str,  # e.g., "1d8", "2d6"
    damage_type: str = "slashing",
    attack_bonus: int = 0,
    rarity: Rarity = Rarity.COMMON,
    value: int = 10,
    weight: float = 3.0,
) -> Item:
    """Create a weapon item."""
    # Parse damage dice (e.g., "1d8" -> count=1, sides=8)
    parts = damage_dice.lower().split("d")
    count = int(parts[0]) if len(parts) > 0 else 1
    sides = int(parts[1]) if len(parts) > 1 else 6
    
    return Item(
        id="",  # Will be auto-generated
        name=name,
        item_type=ItemType.WEAPON,
        description=f"A {name.lower()}.",
        rarity=rarity,
        value=value,
        weight=weight,
        damage_dice_count=count,
        damage_dice_sides=sides,
        damage_bonus=0,
        damage_type=damage_type,
        attack_bonus=attack_bonus,
    )


def create_armor(
    name: str,
    armor_type: ArmorType,
    armor_bonus: int = 0,
    dex_limit: Optional[int] = None,
    rarity: Rarity = Rarity.COMMON,
    value: int = 10,
    weight: float = 10.0,
) -> Item:
    """Create an armor item."""
    return Item(
        id="",  # Will be auto-generated
        name=name,
        item_type=ItemType.ARMOR,
        description=f"A {name.lower()}.",
        rarity=rarity,
        value=value,
        weight=weight,
        armor_type=armor_type,
        armor_bonus=armor_bonus,
        dex_limit=dex_limit,
    )


def create_potion(
    name: str,
    effect: str,
    uses: int = 1,
    rarity: Rarity = Rarity.COMMON,
    value: int = 50,
    quantity: int = 1,
) -> Item:
    """Create a potion item."""
    return Item(
        id="",  # Will be auto-generated
        name=name,
        item_type=ItemType.POTION,
        description=effect,
        rarity=rarity,
        value=value,
        weight=0.5,
        uses=uses,
        max_uses=uses,
        quantity=quantity,
    )


# ---------------------------------------------------------------------------
# Default starting equipment by class
# ---------------------------------------------------------------------------

STARTING_EQUIPMENT = {
    "fighter": [
        create_weapon("Longsword", "1d8", "slashing", 2, Rarity.COMMON, 15, 3),
        create_armor("Chain Mail", ArmorType.HEAVY, 0, None, Rarity.COMMON, 75, 55),
        create_potion("Potion of Healing", "Restores 2d4+2 HP", 1, Rarity.COMMON, 50),
    ],
    "wizard": [
        create_weapon("Quarterstaff", "1d6", "bludgeoning", 0, Rarity.COMMON, 2, 4),
        create_weapon("Dagger", "1d4", "piercing", 2, Rarity.COMMON, 2, 1),
        create_potion("Potion of Healing", "Restores 2d4+2 HP", 1, Rarity.COMMON, 50),
    ],
    "rogue": [
        create_weapon("Rapier", "1d8", "piercing", 3, Rarity.COMMON, 25, 2),
        create_armor("Leather Armor", ArmorType.LIGHT, 0, None, Rarity.COMMON, 10, 10),
        create_weapon("Dagger", "1d4", "piercing", 2, Rarity.COMMON, 2, 1),
        create_potion("Potion of Healing", "Restores 2d4+2 HP", 1, Rarity.COMMON, 50),
    ],
    "cleric": [
        create_weapon("Mace", "1d6", "bludgeoning", 2, Rarity.COMMON, 5, 4),
        create_armor("Scale Mail", ArmorType.MEDIUM, 0, 2, Rarity.COMMON, 50, 45),
        create_potion("Potion of Healing", "Restores 2d4+2 HP", 1, Rarity.COMMON, 50),
    ],
    "ranger": [
        create_weapon("Longbow", "1d8", "piercing", 2, Rarity.COMMON, 50, 2),
        create_weapon("Shortsword", "1d6", "piercing", 2, Rarity.COMMON, 10, 2),
        create_armor("Leather Armor", ArmorType.LIGHT, 0, None, Rarity.COMMON, 10, 10),
        create_potion("Potion of Healing", "Restores 2d4+2 HP", 1, Rarity.COMMON, 50),
    ],
    "paladin": [
        create_weapon("Longsword", "1d8", "slashing", 3, Rarity.COMMON, 15, 3),
        create_armor("Chain Mail", ArmorType.HEAVY, 0, None, Rarity.COMMON, 75, 55),
        create_potion("Potion of Healing", "Restores 2d4+2 HP", 1, Rarity.COMMON, 50),
    ],
    "barbarian": [
        create_weapon("Greataxe", "1d12", "slashing", 3, Rarity.COMMON, 30, 7),
        create_potion("Potion of Healing", "Restores 2d4+2 HP", 1, Rarity.COMMON, 50),
    ],
    "bard": [
        create_weapon("Rapier", "1d8", "piercing", 2, Rarity.COMMON, 25, 2),
        create_armor("Leather Armor", ArmorType.LIGHT, 0, None, Rarity.COMMON, 10, 10),
        create_potion("Potion of Healing", "Restores 2d4+2 HP", 1, Rarity.COMMON, 50),
    ],
    "druid": [
        create_weapon("Scimitar", "1d6", "slashing", 2, Rarity.COMMON, 25, 3),
        create_armor("Leather Armor", ArmorType.LIGHT, 0, None, Rarity.COMMON, 10, 10),
        create_potion("Potion of Healing", "Restores 2d4+2 HP", 1, Rarity.COMMON, 50),
    ],
    "monk": [
        create_weapon("Shortsword", "1d6", "piercing", 2, Rarity.COMMON, 10, 2),
        create_weapon("Dart", "1d4", "piercing", 2, Rarity.COMMON, 5, 0.25),
        create_potion("Potion of Healing", "Restores 2d4+2 HP", 1, Rarity.COMMON, 50),
    ],
    "sorcerer": [
        create_weapon("Dagger", "1d4", "piercing", 2, Rarity.COMMON, 2, 1),
        create_potion("Potion of Healing", "Restores 2d4+2 HP", 1, Rarity.COMMON, 50),
    ],
    "warlock": [
        create_weapon("Dagger", "1d4", "piercing", 2, Rarity.COMMON, 2, 1),
        create_potion("Potion of Healing", "Restores 2d4+2 HP", 1, Rarity.COMMON, 50),
    ],
}


def get_starting_inventory(char_class: str) -> Inventory:
    """Get starting inventory for a character class."""
    items = STARTING_EQUIPMENT.get(char_class.lower(), [
        create_weapon("Club", "1d4", "bludgeoning", 0, Rarity.COMMON, 1, 2),
    ])
    
    inv = Inventory()
    for item in items:
        inv.add_item(item)
    
    # Auto-equip first weapon and armor
    for item in items:
        if item.item_type in (ItemType.WEAPON, ItemType.ARMOR):
            inv.equip_item(item.id)
    
    return inv