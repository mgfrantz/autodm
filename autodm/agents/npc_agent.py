from .character_agent import CharacterAgent, Character
from pydantic import Field
from typing import Union, Dict, Any
from ..battle.turn_state import TurnState
from ..core.enums import ActionType
import json

class NPC(CharacterAgent):
    """
    Represents a Non-Player Character (NPC) in the game.

    This class extends the CharacterAgent class and provides additional
    functionality specific to NPCs, such as decision-making and action generation.
    """

    is_npc: bool = Field(default=True)

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, character: Union[None, Character] = None, ignore_spell_slots: bool = False):
        """
        Initialize an NPC.

        Args:
            character (Union[None, Character], optional): The character associated with this NPC. 
                If None, a new character will be generated. Defaults to None.
            ignore_spell_slots (bool): Whether to ignore spell slot restrictions. Defaults to False.
        """
        if character is None:
            from autodm.core.character import Character
            character = Character.generate()
        super().__init__(character=character, is_npc=True, ignore_spell_slots=ignore_spell_slots)

    def decide_action(self, turn_state: TurnState) -> Dict[str, Any]:
        """
        Decide on the most appropriate action to take in this battle situation.

        Args:
            turn_state (TurnState): The current state of the turn.

        Returns:
            Dict[str, Any]: A dictionary containing the decided action.
        """
        if not self.battle:
            return {"action_type": "pass", "reason": "Not in battle"}

        available_actions = []
        if turn_state.can_take_action(ActionType.STANDARD):
            available_actions.extend(["attack", "cast_spell", "use_item"])
        if turn_state.can_take_action(ActionType.MOVEMENT):
            available_actions.append("move")
        if turn_state.can_take_action(ActionType.BONUS):
            available_actions.append("bonus_action")
        available_actions.append("pass")
        
        context = f"""
You are {self.character.name}, a level {self.character.level} {self.character.chr_race} {self.character.chr_class}.

Based on the following information, decide on the most appropriate action to take in this battle situation.
Available actions: {', '.join(available_actions)}

Your current position: {self.character.position}
Your current HP: {self.character.current_hp}/{self.character.max_hp}
Your equipped weapons: {self.get_equipped_weapons()}
Your known spells: {', '.join([spell.name for spell in self.character.spells])}

Here are your options for your location:
{self.get_characters_in_range()}

Respond by describing what you want to do given the existing tools and the current battle situation. \
Make a strategic decision based on your character's abilities, the current battle situation, and the available actions.
"""
        response = self.chat(context)
        return response

    def decide_movement(self) -> Dict[str, Any]:
        """
        Decide on the most appropriate movement to take in this battle situation.

        Returns:
            Dict[str, Any]: A dictionary containing the movement decision.
        """
        battle_context = self.get_battle_context()
        
        context = f"""
You are {self.character.name}, a level {self.character.level} {self.character.chr_race} {self.character.chr_class}.

Here are your options for your location:
{self.battle.get_characters_in_range()}

If you are in range of an enemy, attack or cast a spell. \
Otherwise, move towards the intended target so you may be able to execute the action this turn or the next.\
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