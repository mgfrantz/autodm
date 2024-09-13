from .character_agent import Agent
from .character import Character, Attributes
from .llm import complete
from pydantic import Field
from typing import Union, Dict, Any
import json

class NPC(Agent):
    def __init__(self, character: Union[Character, None] = None):
        if character is None:
            character = Character.generate()
        super().__init__(character, is_npc=True)
        self.is_npc = True

    def handle_action(self) -> Dict[str, Any]:
        battle_context = self.get_battle_context()
        
        context = f"""
You are {self.character.name}, a level {self.character.level} {self.character.chr_race} {self.character.chr_class}.
Backstory: {self.character.backstory}

{battle_context}

You have the ability to take an action or a movement.
Decide on the most appropriate action or movement to take in the current situation. \
Your movement range is {self.character.speed} feet. \
Your current position is ({self.character.position.x}, {self.character.position.y}).
You have {self.character.movement_remaining} feet of movement remaining.
Your options for movement include:
- Move to a specific coordinate (e.g., "move to A5")
- Stay in your current position

"Battle state:"
{self.battle.get_battle_state() if self.battle else "Not in battle"}

Consider the following factors:
- Proximity to enemies and allies (you will not be able to attack or cast spells on enemies that are out of range)
- Your class abilities and fighting style.

Please use the available functions to gather information and make a decision.
Once you have taken an action or made a move, you should have enough information to respond without any more tools.
"""
        response = self.agent.chat(context)
        return response.text

    # Delegate attribute access to the character object
    def __getattr__(self, name):
        return getattr(self.character, name)

    def attack(self, target: str) -> str:
        weapon = self.character.get_equipped_weapons()[0] if self.character.get_equipped_weapons() else None
        weapon_name = weapon.name if weapon else "an unarmed strike"
        return f"{self.character.name} attacks {target} with {weapon_name}."

    def cast_spell(self, spell_name: str, target: str = "") -> str:
        spell = next((s for s in self.character.spells if s.name.lower() == spell_name.lower()), None)
        if not spell:
            return f"{self.character.name} doesn't know the spell {spell_name}."
        if not self.character.can_cast_spell(spell):
            return f"{self.character.name} cannot cast {spell_name} at this time (no available spell slots)."
        try:
            self.character.cast_spell(spell)
            if spell.name.lower() == "shield" or spell.range.lower() == "self":
                return f"{self.character.name} casts {spell.name} on themselves."
            elif target:
                return f"{self.character.name} casts {spell.name} at {target}."
            else:
                return f"{self.character.name} casts {spell.name}."
        except ValueError as e:
            return str(e)

    def use_item(self, item_name: str, target: str = "") -> str:
        item = next((i for i in self.character.inventory if i.name.lower() == item_name.lower()), None)
        if not item:
            return f"{self.character.name} doesn't have {item_name} in their inventory."
        
        if item.item_type == "potion" and "heal" in item.effects:
            target_char = self.battle.get_target(target) if target else self.character
            if not target_char:
                return f"Invalid target: {target}"
            
            heal_amount = item.effects["heal"]
            old_hp = target_char.hp
            target_char.hp += heal_amount
            actual_heal = target_char.hp - old_hp
            
            self.character.inventory.remove(item)
            
            return f"{self.character.name} uses {item_name} on {target_char.name}. {target_char.name} heals for {actual_heal} HP."
        
        return f"{self.character.name} uses {item_name}."

    # Add other missing methods as needed

# Test scenario (optional)
if __name__ == "__main__":
    npc = NPC.generate("Groknak", "Barbarian", "Half-Orc", level=3)
    print(f"Generated NPC: {npc.character.name}")
    print(f"Backstory: {npc.backstory}")
    print(f"Attributes: {npc.character.attributes}")
