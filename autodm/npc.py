from .character_agent import CharacterAgent
from .character import Character, Attributes
from .llm import complete
from pydantic import Field
from typing import Union, Dict, Any
import json

class NPC(CharacterAgent):
    def __init__(self, character: Union[Character, None] = None):
        if character is None:
            character = Character.generate()
        super().__init__(character, is_npc=True)
        self.is_npc = True

    def decide_action(self) -> Dict[str, Any]:
        battle_context = self.get_battle_context()
        
        context = f"""
You are {self.character.name}, a level {self.character.level} {self.character.chr_race} {self.character.chr_class}.

Based on the following information, decide on the most appropriate action to take in this battle situation. \
In each turn, you can take a movement and an action.

Weapons: {self.character.get_equipped_weapons()}
Spells: {self.character.spells}
Inventory: {self.character.inventory}


Here is current information about the battle, including the names and location of allies and enemies:
{battle_context}

Use plain text to respond. \
If you intend to use an attack, make sure you are in range of the target. \
If you are in range of an enemy, you should attack, otherwise you should move closer to the intended target. \
If you have ranged spells, you should cast them if you are in range of an enemy, otherwise you should move closer to the intended target. \
Locations are given in the battle context above, so there's no need to clarify where certain characters are.

Response: \
"""
        try:
            response = self.chat(self.get_battle_context())
            action_dict = json.loads(str(response))
            return action_dict
        except json.JSONDecodeError:
            # If the AI response is not valid JSON, fall back to a random action
            random_enemy = self.battle.get_random_target(self)  # Changed from get_random_enemy to get_random_target
            return {
                "action_type": "attack",
                "target": random_enemy.name,
                "description": f"{self.character.name} attacks {random_enemy.name} with their weapon."
            }

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

Your options for movement include:
- Move to a specific coordinate (e.g., "move to (5, 3)")
- Stay in your current position

Consider the following factors:
- Proximity to enemies and allies
- Tactical advantages (e.g., cover, high ground)
- Your class abilities and fighting style

Respond with a JSON object containing the following fields:
- action_type: "move"
- target: The coordinate to move to (e.g., "(5, 3)")
- description: A brief description of the movement and its purpose
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
