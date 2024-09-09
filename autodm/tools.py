import random
import re
from typing import Union, Tuple, List

def roll_dice(dice_string: str) -> List[int]:
    """
    Roll dice based on the input string (e.g., "3d6+2").
    
    Returns a list of individual rolls.
    """
    dice_pattern = re.compile(r'(\d+)d(\d+)([+-]\d+)?')
    match = dice_pattern.match(dice_string)
    
    if not match:
        raise ValueError(f"Invalid dice string format: {dice_string}")
    
    num_dice = int(match.group(1))
    dice_type = int(match.group(2))
    modifier = int(match.group(3) or 0)
    
    rolls = [random.randint(1, dice_type) for _ in range(num_dice)]
    
    if modifier != 0:
        rolls.append(modifier)
    
    return rolls

def apply_modifier(roll: int, modifier: int) -> int:
    """Apply a modifier to a roll."""
    return roll + modifier

# Example usage
if __name__ == "__main__":
    roll, rolls = roll_dice("3d6+2")
    print(f"Rolled: {roll}, Individual rolls: {rolls}")

    roll, rolls = roll_dice("1d20-1")
    print(f"Rolled: {roll}, Individual rolls: {rolls}")