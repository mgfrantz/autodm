from typing import Dict, Optional, Union
from pydantic import BaseModel, Field

class Item(BaseModel):
    """
    Represents an item in the game.

    Attributes:
        name (str): The name of the item.
        description (str): A brief description of the item.
        item_type (str): The type of item (e.g., "weapon", "armor", "accessory").
        equippable (bool): Whether the item can be equipped.
        effects (Dict[str, int]): The effects the item has when equipped.

    Example:
        >>> longsword = Item(
        ...     name="Longsword",
        ...     description="A versatile melee weapon",
        ...     item_type="weapon",
        ...     equippable=True,
        ...     effects={"damage": 8}  # 1d8 damage
        ... )
        >>> print(longsword)
        Longsword (weapon)
    """
    name: str
    description: str
    item_type: str  # e.g., "weapon", "armor", "potion"
    equippable: bool = False
    effects: Dict[str, Union[int, str]] = Field(default_factory=dict)
    quantity: int = 1

    def __str__(self):
        return f"{self.name} (x{self.quantity})"

class WeaponAttack(BaseModel):
    name: str
    hit_bonus: int
    damage: str

    class Config:
        arbitrary_types_allowed = True

class EquipmentItem(BaseModel):
    name: str
    quantity: int
    weight: float
    item_type: str
    description: Optional[str] = None
    equippable: bool = False
    effects: Dict[str, Union[int, str]] = {}  # Allow both int and str values

    def __str__(self):
        return f"{self.name} (x{self.quantity})"

# Add this at the end of the file
healing_potion = Item(
    name="Healing Potion",
    description="A small vial of red liquid that restores 2 HP when consumed.",
    item_type="potion",
    effects={"heal": 2}
)