import random
import re
from typing import Union, Tuple

def roll_dice(dice_notation: str) -> Tuple[Union[int, list[int]], int]:
    """
    Roll dice based on standard dice notation (e.g., '3d6', '1d20+2').
    
    Args:
    dice_notation (str): A string representing the dice roll (e.g., '3d6', '1d20+2')
    
    Returns:
    Tuple[Union[int, list[int]], int]: A tuple containing the result of the roll and the modifier.
                                       The first element is either a single int for simple rolls,
                                       or a list of ints for multiple dice.
                                       The second element is the modifier (which may be 0).
    
    Examples:
    >>> roll_dice("3d6")
    ([4, 2, 6], 0)
    >>> roll_dice("1d20+5")
    (15, 5)
    >>> roll_dice("2d4-1")
    ([2, 3], -1)
    """
    # Use regex to parse the dice notation
    match = re.match(r'(\d+)d(\d+)([+-]\d+)?', dice_notation.lower())
    if not match:
        raise ValueError(f"Invalid dice notation: {dice_notation}")

    count, sides = map(int, match.group(1, 2))
    modifier = int(match.group(3) or 0)

    rolls = [random.randint(1, sides) for _ in range(count)]

    if len(rolls) == 1:
        return rolls[0], modifier
    else:
        return rolls, modifier

def apply_modifier(roll_result: Union[int, list[int]], modifier: int) -> Union[int, list[int]]:
    """
    Apply a modifier to a roll result.

    Args:
    roll_result (Union[int, list[int]]): The result of a dice roll.
    modifier (int): The modifier to apply.

    Returns:
    Union[int, list[int]]: The modified roll result.

    Examples:
    >>> apply_modifier(15, 5)
    20
    >>> apply_modifier([4, 2, 6], -1)
    [4, 2, 6, -1]
    """
    if isinstance(roll_result, int):
        return roll_result + modifier
    elif isinstance(roll_result, list):
        return roll_result + [modifier] if modifier != 0 else roll_result
    else:
        raise ValueError("Invalid roll result type")

# Example usage
if __name__ == "__main__":
    roll, mod = roll_dice("3d6+2")
    print(f"Rolled: {roll}, Modifier: {mod}")
    final_result = apply_modifier(roll, mod)
    print(f"Final result: {final_result}")

    roll, mod = roll_dice("1d20-1")
    print(f"Rolled: {roll}, Modifier: {mod}")
    final_result = apply_modifier(roll, mod)
    print(f"Final result: {final_result}")