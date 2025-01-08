"""Map rendering functionality."""
from typing import Dict

from ..character.models import Character
from .models import MapGrid


class MapRenderer:
    """Handles rendering of map representations."""

    @staticmethod
    def render_as_text(grid: MapGrid) -> str:
        """Renders a text-based representation of the map with a legend."""
        max_name_length = (
            max(len(character.name) for character in grid.character_symbols.values())
            if grid.character_symbols else 0
        )
        legend_width = max_name_length + 4  # Add some padding

        # Render the map grid
        grid_output = ""
        for y in range(grid.size_y):
            for x in range(grid.size_x):
                entries = grid.get_entries(x, y)
                if entries:
                    # Display the symbol of the first entry in the square
                    grid_output += f"{entries[0].symbol} "
                else:
                    grid_output += ". "  # Empty square

            # Add legend on the right side of each row
            if y < len(grid.character_symbols):
                symbol, character = list(grid.character_symbols.items())[y]
                grid_output += f"  | {symbol}: {character.name.ljust(max_name_length)}"
            
            grid_output += "\n"

        return grid_output 