from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Union, Any, Tuple
from scipy.spatial.distance import chebyshev

class Position(BaseModel):
    """
    Represents a position on the battle map.

    Attributes:
        x (int): The x-coordinate of the position.
        y (int): The y-coordinate of the position.
    """
    x: int
    y: int

    def to_tuple(self) -> Tuple[int, int]:
        """
        Convert the position to a tuple.

        Returns:
            Tuple[int, int]: A tuple representation of the position (x, y).
        """
        return (self.x, self.y)
    
    def __str__(self) -> str:
        """
        String representation of the position.

        Returns:
            str: A string representation of the position in the format "x=X, y=Y".
        """
        return f"x={self.x}, y={self.y}"

def distance(
        pos1: Position,
        pos2: Position,
        scale: int = 1
    ) -> int:
    """
    Calculate the Chebyshev distance between two positions.
    The Chebyshev distance is the maximum of the absolute differences of their coordinates.

    Args:
        pos1 (Position): The first position.
        pos2 (Position): The second position.
        scale (int, optional): The scale of the distance. Defaults to 1.

    Returns:
        int: The Chebyshev distance between the two positions.
    """
    return int(chebyshev(pos1.to_tuple(), pos2.to_tuple()) * scale)

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
        column_labels = "    " + " ".join(str(i) for i in range(self.width))
        rows = []
        for i, row in enumerate(self.grid):
            row_label = f"{i} |"
            row_str = " ".join(self.player_symbols.get(cell.character.name if cell else None, ".") for cell in row)
            rows.append(row_label + " " + row_str)

        legend = "Legend:\n" + "\n".join(f"- {symbol}: {player_name}" for player_name, symbol in self.player_symbols.items())
        return "\n".join([column_labels] + rows + [legend])

if __name__ == "__main__":
    from .player_agent import PlayerAgent
    from .character import Character

    # Test distance
    pos1 = Position(x=1, y=1)
    pos2 = Position(x=2, y=2)
    print(distance(pos1, pos2))
    print(distance(pos1, pos2, scale=2))
    print(distance(pos1, pos2, scale=5))

    # Test Map
    battle_map = Map()
    player = PlayerAgent(
        character=Character.generate()
    )
    battle_map.add_or_update_player(x=0, y=0, player=player)
    print(battle_map)
    print(battle_map.positions)

    print("Updating location to (3,3)")
    battle_map.add_or_update_player(x=3, y=3, player=player)
    print(battle_map)
    print(battle_map.positions)