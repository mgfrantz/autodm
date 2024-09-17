from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Union, Any
from autodm.core.position import Position

def distance(pos1: Position, pos2: Position, scale: int = 1) -> int:
    """
    Calculate the Chebyshev distance between two positions.

    Args:
        pos1 (Position): The first position.
        pos2 (Position): The second position.
        scale (int): The scale factor for the distance. Defaults to 1.

    Returns:
        int: The scaled Chebyshev distance between the two positions.
    """
    return int(max(abs(pos1.x - pos2.x), abs(pos1.y - pos2.y)) * scale)

class Map(BaseModel):
    """
    Represents a battle map with players and their positions.

    Attributes:
        width (int): The width of the map.
        height (int): The height of the map.
        scale (int): The scale of the map (e.g., how many feet each grid square represents).
        locations (Dict[str, Dict[str, Union[Position, Any]]]): A dictionary of player locations.
        grid (List[List[Optional[Any]]]): A 2D grid representing the map.
    """
    width: int = Field(default=10, description="The width of the map")
    height: int = Field(default=10, description="The height of the map")
    scale: int = Field(default=5, description="The scale of the map (e.g., how many feet each grid square represents)")
    locations: Dict[str, Dict[str, Union[Position, Any]]] = Field(default_factory=dict, description="A dictionary of player locations")
    grid: List[List[Optional[Any]]] = Field(default_factory=list, description="A 2D grid representing the map")

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **data):
        """
        Initialize the Map object.

        Args:
            **data: Keyword arguments for map attributes.
        """
        super().__init__(**data)
        self.grid = [[None for _ in range(self.width)] for _ in range(self.height)]

    def add_or_update_player(self, x: int, y: int, player: Any) -> None:
        """
        Add a new player to the map or update an existing player's position.

        Args:
            x (int): The x-coordinate of the player's new position.
            y (int): The y-coordinate of the player's new position.
            player (Any): The player object to add or update.
        """
        old_player_x = player.character.position.x
        old_player_y = player.character.position.y
        self.grid[old_player_y][old_player_x] = None  # Clear old position
        player.character.position = Position(x=x, y=y)
        self.locations[player.character.name] = {
            "position": player.character.position,
            "player": player
        }
        self.grid[y][x] = player  # Update new position

    @property
    def player_symbols(self) -> Dict[str, str]:
        """
        Generate symbols for players on the map.

        Returns:
            Dict[str, str]: A dictionary mapping player names to their symbols.
        """
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        return {
            player_name: symbol
            for player_name, symbol in zip(self.locations.keys(), alphabet)
        }
    
    @property
    def positions(self) -> str:
        """
        Get a string representation of all player positions.

        Returns:
            str: A string containing all player names and their positions.
        """
        d = {key: str(value["position"]) for key, value in self.locations.items()}
        return '\n'.join([f"{key}: {value}" for key, value in d.items()])
    
    def __str__(self) -> str:
        """
        Generate a string representation of the map.

        Returns:
            str: A string representation of the map, including player positions and a legend.
        """
        column_labels = "      " + " ".join(str(i) for i in range(self.width))
        xaxis_label = list(' ' * len(column_labels))
        xaxis_label[(len(column_labels)//2) + 2] = 'X'
        xaxis_label = ''.join(xaxis_label)
        rows = []
        for i, row in enumerate(self.grid):
            row_label = f"{'Y' if i == (self.height//2) - 1 else ' '} {i} |"
            row_str = " ".join(self.player_symbols.get(cell.character.name if cell else None, ".") for cell in row)
            rows.append(row_label + " " + row_str)

        legend = "Legend:\n" + "\n".join(f"- {symbol}: {player_name}" for player_name, symbol in self.player_symbols.items())
        return "\n".join([xaxis_label, column_labels] + rows + [legend])

    def distance_between_players(self, player1_name: str, player2_name: str) -> int:
        """
        Calculate the Chebyshev distance between two players.

        Args:
            player1_name (str): The name of the first player.
            player2_name (str): The name of the second player.

        Returns:
            int: The Chebyshev distance between the two players.
        """
        pos1 = self.locations[player1_name]["position"]
        pos2 = self.locations[player2_name]["position"]
        return distance(pos1, pos2, scale=self.scale)
