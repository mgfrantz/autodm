from typing import Optional, Dict, TYPE_CHECKING, Any, List
from .character import Character, Attributes, Position
from .llm import get_llm, complete
from .items import EquipmentItem
import random
import json
from pydantic import Field

if TYPE_CHECKING:
    from .battle import Battle

class NPC(Character):
    backstory: str = Field(default="")
    battle: Optional[Any] = Field(default=None)

    def set_battle(self, battle: 'Battle'):
        self.battle = battle

    def get_battle_context(self) -> str:
        if not self.battle:
            return ""

        battle_state = self.battle.get_battle_state()
        
        allies_info = "\n".join([
            f"- {ally['name']} (Level {ally['level']} {ally['class']}): {ally['hp']}/{ally['max_hp']} HP, Position: ({ally.get('position', Position(0, 0)).x}, {ally.get('position', Position(0, 0)).y})"
            for ally in battle_state['enemies']  # NPCs are enemies of players
        ])
        enemies_info = "\n".join([
            f"- {enemy['name']} (Level {enemy['level']} {enemy['class']}): {enemy['hp']}/{enemy['max_hp']} HP, Position: ({enemy.get('position', Position(0, 0)).x}, {enemy.get('position', Position(0, 0)).y})"
            for enemy in battle_state['allies']  # Players are enemies of NPCs
        ])
        
        return f"""
Current battle situation:
Your position: ({self.position.x}, {self.position.y})

Your allies:
{allies_info}

Your enemies:
{enemies_info}

Map size: {self.battle.map_size[0]}x{self.battle.map_size[1]}

Consider the battle situation and positions when making decisions.
"""

    @classmethod
    def generate(cls, name: str, chr_class: str, chr_race: str, level: int = 1):
        attributes = Attributes(
            strength=random.randint(8, 18),
            dexterity=random.randint(8, 18),
            constitution=random.randint(8, 18),
            intelligence=random.randint(8, 18),
            wisdom=random.randint(8, 18),
            charisma=random.randint(8, 18)
        )
        
        backstory_prompt = f"Generate a brief backstory for {name}, a level {level} {chr_race} {chr_class}."
        backstory = complete(backstory_prompt)
        
        character = super().generate(name, chr_class=chr_class, chr_race=chr_race, level=level)
        character.backstory = backstory
        return character

    def get_equipped_weapon(self) -> Optional[EquipmentItem]:
        weapons = self.get_equipped_weapons()
        return weapons[0] if weapons else None

    def decide_action(self) -> Dict[str, Any]:
        battle_context = self.get_battle_context()
        
        context = f"""
You are {self.name}, a level {self.level} {self.chr_race} {self.chr_class}.
Backstory: {self.backstory}

{battle_context}

Your equipped weapon: {self.get_equipped_weapon().name if self.get_equipped_weapon() else "None"}
Your known spells: {', '.join([spell.name for spell in self.spells])}

Decide on the most appropriate action to take in this battle situation. 
Your options include:
- Attack a specific enemy with your weapon (range: {self.get_equipped_weapon().effects.get('range', 5) if self.get_equipped_weapon() else 5} feet)
- Cast a spell at a specific enemy (if you know any spells)
- Use an item from your inventory
- Move to a strategic position
- Attempt to intimidate, persuade, or deceive an enemy

Consider the positions of allies and enemies when making your decision.

Respond with a JSON object containing the following fields:
- action_type: The type of action (attack, cast_spell, use_item, move, skill_check)
- target: The name of the target (if applicable)
- spell_name: The name of the spell to cast (if casting a spell)
- item_name: The name of the item to use (if using an item)
- skill: The name of the skill to use (if performing a skill check)
- description: A brief description of the action, including any strategic considerations based on positions

Example:
{{
    "action_type": "attack",
    "target": "Aric",
    "description": "Zira moves closer to Aric and attacks him with her shortsword, taking advantage of her position near cover."
}}
"""
        response = complete(context)
        try:
            action_dict = json.loads(response)
            if 'target' not in action_dict and action_dict['action_type'] in ['attack', 'cast_spell']:
                # If no target is specified for an attack or spell, choose a random enemy
                random_enemy = self.battle.get_random_enemy(self)
                action_dict['target'] = self.battle.get_name(random_enemy) if random_enemy else "Unknown"
            return action_dict
        except json.JSONDecodeError:
            # If JSON parsing fails, return a default action with a random enemy target
            random_enemy = self.battle.get_random_enemy(self)
            target_name = self.battle.get_name(random_enemy) if random_enemy else "Unknown"
            return {
                "action_type": "attack",
                "target": target_name,
                "description": f"{self.name} attacks {target_name}, moving into a better position if necessary."
            }

    def decide_movement(self) -> Dict[str, Any]:
        battle_context = self.get_battle_context()
        
        context = f"""
You are {self.name}, a level {self.level} {self.chr_race} {self.chr_class}.
Backstory: {self.backstory}

{battle_context}

Decide on the most appropriate movement to take in this battle situation. 
Your movement speed is {self.speed} feet.
Your current position is ({self.position.x}, {self.position.y}).

Consider the following factors:
- Proximity to enemies and allies
- Tactical advantages (e.g., cover, high ground)
- Your class abilities and fighting style

Respond with a JSON object containing the following fields:
- direction: The direction to move (north, south, east, west, northeast, southeast, southwest, northwest)
- distance: The distance to move in feet (should be less than or equal to your movement speed)
- description: A brief description of the movement and its tactical purpose

Example:
{{
    "direction": "northeast",
    "distance": 20,
    "description": "Zira moves 20 feet northeast to flank Aric and gain a tactical advantage."
}}
"""
        response = complete(context)
        try:
            movement_dict = json.loads(response)
            return movement_dict
        except json.JSONDecodeError:
            # If JSON parsing fails, return a default movement
            return {
                "direction": "north",
                "distance": min(20, self.speed),
                "description": f"{self.name} moves cautiously, seeking a better position."
            }

    def converse(self, message: str) -> str:
        context = (
            f"You are narrating the actions and speech of {self.name}, a {self.chr_race} {self.chr_class}. "
            f"Backstory: {self.backstory}\n\n"
            f"Someone says to {self.name}: '{message}'\n\n"
            f"Describe {self.name}'s response and actions in third person, as if narrating a story. "
            f"Use {self.name} or appropriate pronouns instead of 'I' or 'me'. "
            f"Incorporate {self.name}'s race, class, and personality into the response."
        )
        return complete(context)

    def react_to_social_action(self, action: str, actor: str) -> str:
        context = (
            f"You are narrating the actions and speech of {self.name}, a {self.chr_race} {self.chr_class}. "
            f"Backstory: {self.backstory}\n\n"
            f"{actor} attempts to {action} {self.name}.\n\n"
            f"Describe {self.name}'s reaction in third person, as if narrating a story. "
            f"Use {self.name} or appropriate pronouns instead of 'I' or 'me'. "
            f"Incorporate {self.name}'s race, class, and personality into the response."
        )
        return complete(context)

# Interactive conversation loop
def interactive_conversation(npc: NPC):
    print(f"You are now interacting with {npc.name}, a level {npc.level} {npc.chr_race} {npc.chr_class}.")
    print(f"Backstory: {npc.backstory}")
    print(f"Attributes: {npc.attributes}")
    print("\nType 'exit' to end the conversation.")
    
    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() == 'exit':
            print("Ending conversation. Goodbye!")
            break
        
        response = npc.converse(user_input)
        print(f"\nNarrator: {response}")

# Example usage
if __name__ == "__main__":
    npc = NPC.generate("Groknak", "Barbarian", "Half-Orc", level=3)
    interactive_conversation(npc)