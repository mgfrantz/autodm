from typing import Tuple
from ..core.character import Character
from ..utils.dice import roll_dice

def perform_skill_check(character: Character, skill: str, difficulty_class: int) -> Tuple[bool, int]:
    """
    Perform a skill check for a character.

    Args:
    character (Character): The character performing the skill check.
    skill (str): The skill being checked.
    difficulty_class (int): The Difficulty Class (DC) of the check.

    Returns:
    Tuple[bool, int]: A tuple containing a boolean indicating success or failure,
                      and the total value of the roll.
    """
    skill_modifier = character.get_skill_modifier(skill)
    roll = roll_dice("1d20")[0]
    total = roll + skill_modifier

    success = total >= difficulty_class
    return success, total

def perform_ability_check(character: Character, ability: str, difficulty_class: int) -> Tuple[bool, int]:
    """
    Perform an ability check for a character.

    Args:
    character (Character): The character performing the ability check.
    ability (str): The ability being checked (e.g., 'strength', 'dexterity', etc.).
    difficulty_class (int): The Difficulty Class (DC) of the check.

    Returns:
    Tuple[bool, int]: A tuple containing a boolean indicating success or failure,
                      and the total value of the roll.
    """
    ability_modifier = character.attributes.get_modifier(ability)
    roll = roll_dice("1d20")[0]
    total = roll + ability_modifier

    success = total >= difficulty_class
    return success, total