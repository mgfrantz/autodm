from typing import Optional
from llama_index.llms.ollama import Ollama
from .character import Character, Attributes
import random
from pydantic import Field

class NPC(Character):
    backstory: str = Field(default="")
    llm: Optional[Ollama] = Field(default=None)
    
    def __init__(
        self,
        name: str,
        chr_class: str,
        level: int,
        chr_race: str,
        attributes: Attributes,
        backstory: str,
        llm: Optional[Ollama] = None,
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
        self.llm = llm or Ollama(model="llama3.1")

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
        
        llm = Ollama(model="llama3.1")
        backstory_prompt = f"Generate a brief backstory for {name}, a level {level} {chr_race} {chr_class}."
        backstory = llm.complete(backstory_prompt).text
        
        return cls(name, chr_class, level, chr_race, attributes, backstory, llm=llm)

    def converse(self, message: str) -> str:
        context = (
            f"You are narrating the actions and speech of {self.name}, a {self.chr_race} {self.chr_class}. "
            f"Backstory: {self.backstory}\n\n"
            f"Someone says to {self.name}: '{message}'\n\n"
            f"Describe {self.name}'s response and actions in third person, as if narrating a story. "
            f"Use {self.name} or appropriate pronouns instead of 'I' or 'me'. "
            f"Incorporate {self.name}'s race, class, and personality into the response."
        )
        response = self.llm.complete(context).text
        return response

    def react_to_social_action(self, action: str, actor: str) -> str:
        context = (
            f"You are narrating the actions and speech of {self.name}, a {self.chr_race} {self.chr_class}. "
            f"Backstory: {self.backstory}\n\n"
            f"{actor} attempts to {action} {self.name}.\n\n"
            f"Describe {self.name}'s reaction in third person, as if narrating a story. "
            f"Use {self.name} or appropriate pronouns instead of 'I' or 'me'. "
            f"Incorporate {self.name}'s race, class, and personality into the response."
        )
        response = self.llm.complete(context).text
        return response

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