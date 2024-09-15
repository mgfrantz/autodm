from typing import Optional, Dict, Any
from .character_agent import CharacterAgent, Battle
from .character import Character
from pydantic import Field

class PlayerAgent(CharacterAgent):
    is_npc: bool = Field(default=False)

    class Config:
        arbitrary_types_allowed = True


if __name__ == "__main__":
    from .character import Character

    character = Character.generate()
    player_agent = PlayerAgent(character=character)
    print(player_agent.character.name)
    while (inp:=input("What would you like to do? (exit to quit)")) != "exit":
        print(player_agent.chat(inp))