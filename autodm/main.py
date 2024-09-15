from .character import Character
from .character_agent import CharacterAgent

if __name__ == "__main__":
    character = Character.generate()
    character_agent = CharacterAgent(character=character)
    print(character_agent.chat("What is your name?"))