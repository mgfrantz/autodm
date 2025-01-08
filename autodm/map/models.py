"""Map-related models and data structures."""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple, Any

from pydantic import BaseModel, Field, field_validator, model_validator

from ..character.models import Character
from .enums import SizeEnum


class MapEntry(BaseModel):
    """Represents an entry on the map (character, obstacle, etc.)."""
    character: Optional[Character] = None
    size: SizeEnum = SizeEnum.MEDIUM  # Default size
    symbol: str = Field(default='?', description="Symbol to use when rendering this entry.")

    @field_validator('size', mode='before')
    def set_size_based_on_character(cls, v: Optional[SizeEnum], info: Any) -> SizeEnum:
        """Sets size based on character if not explicitly provided."""
        if not v and 'character' in info.data:
            character = info.data['character']
            if character and character.character_class and character.character_class.name == "Druid":
                return SizeEnum.MEDIUM  # Example: Druids might have different size options
            elif character:
                return SizeEnum.MEDIUM  # Default for most characters
        return v or SizeEnum.MEDIUM


class Position(BaseModel):
    """Represents a position on the map."""
    x: int = Field(..., description="X coordinate on the map grid")
    y: int = Field(..., description="Y coordinate on the map grid")

    def distance_to(self, other: Position) -> int:
        """Calculate the distance to another position in grid squares."""
        from .utils import calculate_distance
        return calculate_distance(self.x, self.y, other.x, other.y)


class MapGrid(BaseModel):
    """Represents the game map grid."""
    grid: Dict[Tuple[int, int], List[MapEntry]] = Field(default_factory=dict)
    size_x: int = Field(default=50, description="Map size in squares (x-axis).")
    size_y: int = Field(default=50, description="Map size in squares (y-axis).")
    character_symbols: Dict[str, Character] = Field(default_factory=dict)
    next_symbol: str = Field(default='A', description="Next available symbol for character assignment")

    @model_validator(mode='after')
    def initialize_grid_after_validation(self) -> 'MapGrid':
        """Initialize the grid after model validation."""
        self.initialize_grid()
        return self

    def initialize_grid(self):
        """Initializes the grid with empty lists for each coordinate."""
        for x in range(self.size_x):
            for y in range(self.size_y):
                self.grid[(x, y)] = []

    def is_valid_location(self, x: int, y: int) -> bool:
        """Checks if a location is within the map bounds."""
        return 0 <= x < self.size_x and 0 <= y < self.size_y

    def get_entries(self, x: int, y: int) -> List[MapEntry]:
        """Get all entries at a specific location."""
        return self.grid.get((x, y), [])

    def set_entries(self, x: int, y: int, entries: List[MapEntry]):
        """Set the entries at a specific location."""
        if not self.is_valid_location(x, y):
            raise ValueError(f"Invalid coordinates: ({x}, {y})")
        self.grid[(x, y)] = entries

    def assign_symbol(self, character: Character) -> str:
        """Assigns a symbol to a character if it doesn't have one."""
        if character not in self.character_symbols.values():
            self.character_symbols[self.next_symbol] = character
            symbol = self.next_symbol
            # Increment the next symbol (A -> B, B -> C, and so on)
            self.next_symbol = chr(ord(self.next_symbol) + 1)
            return symbol
        return next(sym for sym, char in self.character_symbols.items() if char == character)

    def remove_symbol(self, character: Character):
        """Removes a character's symbol assignment."""
        self.character_symbols = {
            sym: char for sym, char in self.character_symbols.items() 
            if char != character
        } 