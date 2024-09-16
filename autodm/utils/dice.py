import random
from typing import List

def roll_dice(dice_string: str) -> List[int]:
    """
    Roll a number of dice of a given type.

    Args:
        dice_string (str): A string representing the number of dice and the type of dice to roll.
            For example, "2d6" means roll two six-sided dice.

    Returns:
        List[int]: A list of integers representing the results of the dice rolls.
    """
    num_dice, dice_type = map(int, dice_string.split('d'))
    return [random.randint(1, dice_type) for _ in range(num_dice)]

def roll_attribute():
    """
    Roll four six-sided dice and return the sum of the three highest rolls.

    Returns:
        int: The result of the attribute roll.
    """
    return sum(sorted([random.randint(1, 6) for _ in range(4)])[1:])

def apply_modifier(roll: int, modifier: int) -> int:
    """
    Apply a modifier to a roll.

    Args:
        roll (int): The result of the dice roll.
        modifier (int): The modifier to apply to the roll.

    Returns:
        int: The result of the roll after applying the modifier.
    """
    return roll + modifier