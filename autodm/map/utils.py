"""Map-related utility functions."""
import math
from typing import List, Tuple

from .enums import SizeEnum, SIZE_SQUARES, CHARACTERS_PER_SQUARE


def calculate_distance(x1: int, y1: int, x2: int, y2: int) -> int:
    """Calculates the distance between two points on the grid (using 5ft squares)."""
    delta_x = abs(x2 - x1)
    delta_y = abs(y2 - y1)
    
    # Calculate diagonal distance
    if delta_x > delta_y:
        diagonal_distance = delta_y
        straight_distance = delta_x - delta_y
    else:
        diagonal_distance = delta_x
        straight_distance = delta_y - delta_x

    total_distance = diagonal_distance * 1.5 + straight_distance

    return int(total_distance)


def get_size_dimensions(size: SizeEnum) -> Tuple[int, int]:
    """Get the dimensions (width, height) needed for a given size."""
    squares = SIZE_SQUARES[size]
    dimension = int(math.sqrt(squares))
    return dimension, dimension


def get_characters_per_square(size: SizeEnum) -> float:
    """Get the number of characters that can occupy a single square for a given size."""
    return CHARACTERS_PER_SQUARE[size]


def get_occupied_squares(x: int, y: int, size: SizeEnum) -> List[Tuple[int, int]]:
    """Get all squares occupied by an entity of given size at position (x,y)."""
    width, height = get_size_dimensions(size)
    squares = []
    for i in range(width):
        for j in range(height):
            squares.append((x + i, y + j))
    return squares