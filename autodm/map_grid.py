from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Union, Any
from scipy.spatial.distance import chebyshev

class Position(BaseModel):
    """
    A position on the map.

    Args:
        x (int): The x-coordinate of the position.
        y (int): The y-coordinate of the position.
    """
    x: int
    y: int

    def to_tuple(self):
        """
        Convert the position to a tuple.

        Returns:
            tuple: The position as an (x, y) tuple.
        """
        return (self.x, self.y)
    
    def distance_to(self, other: 'Position') -> int:
        """
        Calculate the Chebyshev distance to another position.

        Args:
            other (Position): The other position.

        Returns:
            int: The Chebyshev distance to the other position.
        """
        return distance(self, other)
    
    def __str__(self):
        """
        Convert the position to a string.

        Returns:
            str: The position as a string.
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
    width: int = Field(default=10)
    height: int = Field(default=10)
    scale: int = Field(default=5)
    locations: Dict[str, Dict[str, Union[Position, Any]]] = {}
    grid: List[List[Optional[Any]]] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **data):
        super().__init__(**data)
        self.grid = [[None for _ in range(self.width)] for _ in range(self.height)]

    def add_or_update_player(self, x: int, y: int, player: Any):
        """
        Add or update a player on the map. If the player already has a position, the old position will be cleared.
        If the player does not have a position, the player will be added to the map.

        Args:
            x (int): The x-coordinate of the player.
            y (int): The y-coordinate of the player.
            player (Any): The player to add or update.
        """
        if player.character.position is not None:        
            old_player_x = player.character.position.x
            old_player_y = player.character.position.y
            self.grid[old_player_y][old_player_x] = None  # Fixed indexing
        player.character.position = Position(x=x, y=y)
        self.locations[player.character.name] = {
            "position": player.character.position,
            "player": player
        }
        self.grid[y][x] = player  # Fixed indexing

    @property
    def player_symbols(self):
        """
        Get the player symbols.

        Returns:
            dict: A dictionary with the player names as keys and the symbols as values.
        """
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        return {
            player_name: symbol
            for player_name, symbol in zip(self.locations.keys(), alphabet)
        }
    
    @property
    def positions(self):
        """
        Get the positions of the players.

        Returns:
            str: A string with the positions of the players.
        """
        d = {key: str(value["position"]) for key, value in self.locations.items()}
        return '\n'.join([f"{key}: {value}" for key, value in d.items()])
    
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
    
    def __str__(self):
        """
        Convert the map to a string.

        Returns:
            str: A string with the map.
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
        return "\n".join([xaxis_label,column_labels] + rows + [legend])

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
