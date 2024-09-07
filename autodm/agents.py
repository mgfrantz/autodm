from typing import List, Dict, Any, Optional
from llama_index.llms.ollama import Ollama
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.tools import BaseTool, FunctionTool
from llama_index.core.llms import CompletionResponse
from .battle import Battle
from .actions import Action, CastSpellAction, AttackAction
from .character import Character
from .spells import Spell
import json

class BattleAgent:
    def __init__(
        self,
        battle: Battle,
        llm: Optional[Ollama] = None,
        memory: Optional[ChatMemoryBuffer] = None,
        verbose: bool = False
    ):
        self.battle = battle
        self.llm = llm or Ollama(
            model="llama3.1",
            request_timeout=60.0,
            temperature=0.7,
            context_window=2048,
            additional_kwargs={"num_predict": 50}
        )
        self.memory = memory or ChatMemoryBuffer.from_defaults(token_limit=1500)
        self.verbose = verbose
        
        self.tools = [
            FunctionTool.from_defaults(fn=self.get_battle_status, name="get_battle_status"),
            FunctionTool.from_defaults(fn=self.perform_action, name="perform_action"),
        ]

    def get_battle_status(self) -> str:
        """Get the current battle status."""
        return self.battle.get_battle_status()

    def perform_action(self, character_name: str, action_name: str, target_name: Optional[str] = None, spell_name: Optional[str] = None) -> Dict[str, Any]:
        """Execute the chosen action and return the result."""
        character = next((c for c in self.battle.all_characters if c.name == character_name), None)
        if not character:
            return {"result": f"Invalid character: {character_name}", "is_turn_ended": False}

        available_actions = self.battle.get_available_actions(character)
        chosen_action = next((action for name, action in available_actions.items() if name.lower() == action_name.lower()), None)
        if not chosen_action:
            return {"result": f"Invalid action: {action_name}", "is_turn_ended": False}

        target = next((c for c in self.battle.all_characters if c.name.lower() == target_name.lower()), None) if target_name else None

        if isinstance(chosen_action, CastSpellAction) and spell_name:
            spell = next((s for s in character.spells if s.name.lower() == spell_name.lower()), None)
            if spell:
                chosen_action.spell = spell
            else:
                return {"result": f"{character.name} doesn't know the spell {spell_name}.", "is_turn_ended": False}

        result = self.battle.execute_turn(character, chosen_action, target)
        new_state = self.battle.get_battle_status()
        return {"result": f"{result}\n\nNew battle state:\n{new_state}", "is_turn_ended": True}

    def handle_turn(self, character: Character, user_input: Optional[str] = None) -> str:
        """Handle a character's turn based on natural language input or AI decision."""
        prompt = (
            f"Current battle state:\n{self.battle.get_battle_status()}\n"
            f"It's {character.name}'s turn. "
            f"Available actions:\n{self.battle.get_available_actions(character)}\n"
            f"Available spells:\n{[spell.name for spell in character.spells if character.can_cast_spell(spell)]}\n"
        )

        if user_input:
            prompt += f"User input: {user_input}\n"
            prompt += (
                "Based on the user's input, determine the appropriate action for the character to take. "
                "You should infer the action, target, and spell (if applicable) from the user's natural language input. "
            )
        else:
            prompt += (
                "As an AI, determine the most appropriate action for this character to take in the current battle situation. "
                "Consider the character's available actions, spells, and the overall battle state. "
            )

        prompt += (
            "Use the available tools to gather information and perform actions. "
            "You can make multiple tool calls if necessary. "
            "Always end with the perform_action tool call to execute the chosen action. "
            "Respond with your reasoning and the tool calls you want to make."
        )

        response = self.llm.predict_and_call(
            self.tools,
            prompt,
            allow_parallel_tool_calls=False
        )

        if isinstance(response, str):
            return response
        elif hasattr(response, 'sources'):
            return "\n".join([source.raw_output for source in response.sources])
        else:
            return "Unexpected response from LLM"

    def run_battle(self):
        """Run the entire battle simulation."""
        round_count = 0
        while not self.battle.is_battle_over():
            print(f"\nRound {round_count}")
            for current_character in self.battle.initiative_order:
                print(f"{current_character.name}'s turn:")
                if current_character in self.battle.player_characters:
                    user_input = input(f"{current_character.name}, what would you like to do? ")
                    output = self.handle_turn(current_character, user_input)
                else:
                    output = self.handle_turn(current_character)
                print(output)
            
            round_count += 1
            if round_count > 10:  # Limit the number of rounds to prevent infinite loops
                print("Battle has gone on for too long. Ending simulation.")
                break

        print("Battle ended.")
        print(self.get_battle_status())

# Example usage
if __name__ == "__main__":
    from .character import Character
    from .spells import fireball, cure_wounds
    import sys
    import traceback

    try:
        print("Initializing battle...")
        player1 = Character.generate("Alice", chr_class="Wizard")
        player2 = Character.generate("Bob", chr_class="Sorcerer")
        enemy1 = Character.generate("Goblin 1")
        enemy2 = Character.generate("Goblin 2")

        player1.add_spell(fireball)
        player2.add_spell(cure_wounds)

        battle = Battle([player1, player2], [enemy1, enemy2])
        battle.start_battle()

        agent = BattleAgent(battle, verbose=True)
        agent.run_battle()

    except Exception as e:
        print(f"An error occurred: {str(e)}")
        print("Traceback:")
        traceback.print_exc()
        sys.exit(1)