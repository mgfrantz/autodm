from typing import Dict, Union, Optional
from pydantic import BaseModel, Field
from autodm.core.enums import ItemType

class Item(BaseModel):
    name: str = Field(..., description="The name of the item")
    description: Optional[str] = Field(None, description="The description of the item")
    item_type: ItemType = Field(..., description="The type of item")
    equippable: bool = Field(default=False, description="Whether the item can be equipped")
    effects: Dict[str, Union[int, str]] = Field(default_factory=dict, description="The effects of the item")
    quantity: int = Field(default=1, description="The quantity of the item")

    def __str__(self):
        return f"{self.name} (x{self.quantity})"

class EquipmentItem(Item):
    weight: float = Field(..., description="The weight of the item")
    equippable: bool = Field(default=True, description="Whether the item can be equipped")

    def __str__(self):
        return f"{self.name} (x{self.quantity})"