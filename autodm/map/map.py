"""Main map module for handling game map operations."""
from __future__ import annotations
from typing import List, Optional

# Local application imports
from ..character.models import Character
from .enums import SizeEnum, FEET_PER_SQUARE
from .models import MapEntry, MapGrid, Position
from .renderer import MapRenderer
from .utils import get_characters_per_square, get_occupied_squares


class GameMap:
    """Represents the game map with all its entities and operations."""
    def __init__(self, size_x: int = 50, size_y: int = 50):
        self.grid = MapGrid(size_x=size_x, size_y=size_y)
        self.grid.initialize_grid()
        self.renderer = MapRenderer()

    def add_character(self, character: Character, x: int, y: int, size: SizeEnum = SizeEnum.MEDIUM):
        """Adds a character to the map."""
        if not self.grid.is_valid_location(x, y):
            raise ValueError("Invalid map coordinates.")

        # Get all squares that will be occupied
        occupied_squares = get_occupied_squares(x, y, size)
        chars_per_square = get_characters_per_square(size)

        # Validate all squares
        for square_x, square_y in occupied_squares:
            if not self.grid.is_valid_location(square_x, square_y):
                raise ValueError("Not enough space at the specified coordinates for this size.")
            if len(self.grid.get_entries(square_x, square_y)) >= chars_per_square:
                raise ValueError("Not enough space at the specified coordinates for this size.")

        # Assign a symbol to the character
        symbol = self.grid.assign_symbol(character)

        # Add character to all required squares
        entry = MapEntry(character=character, size=size, symbol=symbol)
        for square_x, square_y in occupied_squares:
            entries = self.grid.get_entries(square_x, square_y)
            entries.append(entry)

    def remove_character(self, character: Character):
        """Removes a character from the map."""
        for x in range(self.grid.size_x):
            for y in range(self.grid.size_y):
                entries = self.grid.get_entries(x, y)
                self.grid.set_entries(x, y, [entry for entry in entries if entry.character != character])
        self.grid.remove_symbol(character)

    def find_character(self, character: Character) -> Optional[Position]:
        """Finds a character on the map and returns its position."""
        for x in range(self.grid.size_x):
            for y in range(self.grid.size_y):
                entries = self.grid.get_entries(x, y)
                if any(entry.character == character for entry in entries):
                    return Position(x=x, y=y)
        return None

    def get_characters_at_location(self, x: int, y: int) -> List[Character]:
        """Returns a list of characters at the specified location."""
        entries = self.grid.get_entries(x, y)
        return [entry.character for entry in entries if entry.character]

    def can_move(self, character: Character, new_x: int, new_y: int) -> bool:
        """Checks if a character can move to a new position."""
        current_pos = self.find_character(character)
        if not current_pos:
            return False  # Character is not on the map

        # Calculate movement distance and check against speed
        new_pos = Position(x=new_x, y=new_y)
        distance = current_pos.distance_to(new_pos)
        if distance > character.speed / FEET_PER_SQUARE:  # Convert speed to squares per round
            return False

        # Find the character's entry to get its size
        current_entries = self.grid.get_entries(current_pos.x, current_pos.y)
        entry = next((e for e in current_entries if e.character == character), None)
        if not entry:
            return False

        # Check space at new location
        occupied_squares = get_occupied_squares(new_x, new_y, entry.size)
        chars_per_square = get_characters_per_square(entry.size)

        for square_x, square_y in occupied_squares:
            if not self.grid.is_valid_location(square_x, square_y):
                return False
            if len(self.grid.get_entries(square_x, square_y)) >= chars_per_square:
                return False

        return True

    def move_character(self, character: Character, new_x: int, new_y: int):
        """Moves a character to a new position on the map."""
        if not self.can_move(character, new_x, new_y):
            raise ValueError("Invalid move.")

        current_pos = self.find_character(character)
        if current_pos:
            current_entries = self.grid.get_entries(current_pos.x, current_pos.y)
            entry = next((e for e in current_entries if e.character == character), None)
            if entry:
                # Store the symbol and size before removing
                symbol = entry.symbol
                size = entry.size
                
                # Remove the character from its old position
                self.remove_character(character)
                
                # Add the character to the new position with the same symbol and size
                entry = MapEntry(character=character, size=size, symbol=symbol)
                occupied_squares = get_occupied_squares(new_x, new_y, size)
                for square_x, square_y in occupied_squares:
                    entries = self.grid.get_entries(square_x, square_y)
                    entries.append(entry)
            else:
                raise ValueError("Character entry not found at its supposed location.")
        else:
            raise ValueError("Character not found on the map.")

    def render(self) -> str:
        """Renders a text representation of the map."""
        return self.renderer.render_as_text(self.grid)