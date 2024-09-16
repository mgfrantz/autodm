from .character_agent import CharacterAgent
from pydantic import Field

class PlayerAgent(CharacterAgent):
    is_npc: bool = Field(default=False)

    class Config:
        arbitrary_types_allowed = True

    def interpret_action(self, user_input: str) -> str:
        """
        Interpret and execute a user action for a player character.

        Args:
            user_input (str): The input string from the user describing the action.

        Returns:
            str: The result of the interpreted action.
        """
        # For now, we'll just use the chat method from the base class
        return self.chat(user_input)

if __name__ == "__main__":
    from autodm.core.character import Character

    character = Character.generate()
    player_agent = PlayerAgent(character=character)
    print(player_agent.chat("What is your name?"))