from typing import Optional, Dict, TYPE_CHECKING, Any
from .character import Character, Attributes
from .llm import get_llm, complete
import random
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
        
        allies_info = "\n".join([f"- {ally['name']} (Level {ally['level']} {ally['class']}): {ally['hp']}/{ally['max_hp']} HP" for ally in battle_state['enemies']])  # NPCs are enemies of players
        enemies_info = "\n".join([f"- {enemy['name']} (Level {enemy['level']} {enemy['class']}): {enemy['hp']}/{enemy['max_hp']} HP" for enemy in battle_state['allies']])  # Players are enemies of NPCs
        
        return f"""
You are currently in a battle.
Your allies:
{allies_info}

Your enemies:
{enemies_info}

Consider the battle situation when making decisions.
"""

    def __init__(
        self,
        name: str,
        chr_class: str,
        level: int,
        chr_race: str,
        attributes: Attributes,
        backstory: str,
    ):
        super().__init__(
            name=name,
            chr_class=chr_class,
            level=level,
            chr_race=chr_race,
            background="Custom",
            alignment="Neutral",
            experience_points=0,
            attributes=attributes,
            proficiency_bonus=2,
            armor_class=10,
            initiative=0,
            speed=30,
            max_hp=10,
            current_hp=10,
        )
        self.backstory = backstory

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
        
        return cls(name, chr_class, level, chr_race, attributes, backstory)

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

    def decide_action(self) -> str:
        battle_context = self.get_battle_context()
        
        context = f"""
You are {self.name}, a level {self.level} {self.chr_race} {self.chr_class}.
Backstory: {self.backstory}

{battle_context}

Decide on the most appropriate action to take in this battle situation. 
Your options include:
- Attack a specific enemy
- Cast a spell (if you know any)
- Use an item from your inventory
- Move to a strategic position
- Attempt to intimidate, persuade, or deceive an enemy

Respond with a brief description of your chosen action.
"""
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