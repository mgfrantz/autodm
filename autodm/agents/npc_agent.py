from .character_agent import CharacterAgent, Character
from pydantic import Field
from typing import Union, Dict, Any
import json

class NPC(CharacterAgent):
    """
    Represents a Non-Player Character (NPC) in the game.

    This class extends the CharacterAgent class and provides additional
    functionality specific to NPCs, such as decision-making and action generation.
    """

    is_npc: bool = Field(default=True)

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, character: Union[None, Character] = None):
        """
        Initialize an NPC.

        Args:
            character (Union[None, Character], optional): The character associated with this NPC. 
                If None, a new character will be generated. Defaults to None.
        """
        if character is None:
            from autodm.core.character import Character
            character = Character.generate()
        super().__init__(character=character, is_npc=True)

    def decide_action(self, has_taken_action: bool, has_taken_movement: bool) -> str:
        """
        Decide on the most appropriate action to take in this battle situation.

        Args:
            has_taken_action (bool): Whether the NPC has taken an action in the current turn.
            has_taken_movement (bool): Whether the NPC has taken a movement in the current turn.

        Returns:
            str: The action to take in the current turn.
        """
        battle_context = self.get_battle_context()
        
        context = f"""
You are {self.character.name}, a level {self.character.level} {self.character.chr_race} {self.character.chr_class}.

Based on the following information, decide on the most appropriate action to take in this battle situation. \
In each turn, you can take a movement and an action. \
This turn you have {"not " if not has_taken_action else ""}taken an action and {"not " if not has_taken_movement else ""}taken a movement.

Weapons: {self.character.get_equipped_weapons()}
Spells: {self.character.spells}
Inventory: {self.character.inventory}

Here is current information about the battle, including the names and location of allies and enemies:
{battle_context}

Use plain text to respond. \
For an intended action, first check if there are any targets in range of the action. \
If so, execute the action. \
Otherwise, move towards the intended target so you may be able to execute the action this turn or the next.
"""
        response = self.chat(context)
        return response

    def decide_movement(self) -> Dict[str, Any]:
        """
        Decide on the most appropriate movement to take in this battle situation.

        Returns:
            Dict[str, Any]: A dictionary containing the movement decision.
        """
        battle_context = self.get_battle_context()
        
        context = f"""
You are {self.character.name}, a level {self.character.level} {self.character.chr_race} {self.character.chr_class}.
Backstory: {self.character.backstory}

{battle_context}

Decide on the most appropriate movement to take in this battle situation. 
Your movement speed is {self.character.speed} feet.
Your current position is ({self.character.position.x}, {self.character.position.y}).
You have {self.character.movement_remaining} feet of movement remaining.

Response: \
"""
        response = self.agent.chat(context)
        try:
            movement_dict = json.loads(str(response))
            return movement_dict
        except json.JSONDecodeError:
            # If JSON parsing fails, return a default movement
            return {
                "action_type": "move",
                "target": f"({self.character.position.x}, {self.character.position.y})",
                "description": f"{self.character.name} stays in their current position."
            }

    # Delegate attribute access to the character object
    def __getattr__(self, name):
        return getattr(self.character, name)