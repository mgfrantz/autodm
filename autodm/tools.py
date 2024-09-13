import random
import re
from typing import Union, Tuple, List

def roll_dice(dice_string: str) -> List[int]:
    """
    Roll dice based on the input string (e.g., "3d6+2").
    
    Returns a list of individual rolls.
    """
    num_dice, dice_type = map(int, dice_string.split('d'))
    return [random.randint(1, dice_type) for _ in range(num_dice)]

def apply_modifier(roll: int, modifier: int) -> int:
    """Apply a modifier to a roll."""
    return roll + modifier

# Example usage
if __name__ == "__main__":
    roll, rolls = roll_dice("3d6+2")
    print(f"Rolled: {roll}, Individual rolls: {rolls}")

    roll, rolls = roll_dice("1d20-1")
    print(f"Rolled: {roll}, Individual rolls: {rolls}")