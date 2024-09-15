from .character_agent import CharacterAgent
from .character import Character
from .llm import complete
from pydantic import Field
from typing import Union, Dict, Any
import json

class NPC(CharacterAgent):
    is_npc: bool = Field(default=True)

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, character: Union[Character, None] = None):
        if character is None:
            character = Character.generate()
        super().__init__(character=character, is_npc=True)

    def decide_action(self, has_taken_action:bool, has_taken_movement:bool) -> str:
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

Response: \
"""
        response = self.chat(context)
        return response

    def decide_movement(self) -> Dict[str, Any]:
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

# Test scenario (optional)
if __name__ == "__main__":
    npc = NPC.generate("Groknak", "Barbarian", "Half-Orc", level=3)
    print(f"Generated NPC: {npc.character.name}")
    print(f"Backstory: {npc.backstory}")
    print(f"Attributes: {npc.character.attributes}")
