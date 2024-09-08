from typing import List, Optional
from llama_index.core.tools import BaseTool, FunctionTool
from llama_index.core.agent import ReActAgent
from .character import Character, Attributes
from .actions import Action, AttackAction, CastSpellAction
from .spells import Spell
from pydantic import Field
from .llm import get_llm, complete

class PlayerAgent:
    character: Character
    tools: List[BaseTool]
    agent: ReActAgent

    def __init__(self, character: Character):
        self.character = character
        self.tools = [
            FunctionTool.from_defaults(fn=self.move, name="move"),
            FunctionTool.from_defaults(fn=self.attack, name="attack"),
            FunctionTool.from_defaults(fn=self.cast_spell, name="cast_spell"),
            FunctionTool.from_defaults(fn=self.use_item, name="use_item"),
            FunctionTool.from_defaults(fn=self.check_inventory, name="check_inventory"),
            FunctionTool.from_defaults(fn=self.check_status, name="check_status"),
            FunctionTool.from_defaults(fn=self.intimidate, name="intimidate"),
            FunctionTool.from_defaults(fn=self.persuade, name="persuade"),
            FunctionTool.from_defaults(fn=self.deceive, name="deceive"),
            FunctionTool.from_defaults(fn=self.say, name="say"),
            FunctionTool.from_defaults(fn=self.check_spells, name="check_spells"),
            FunctionTool.from_defaults(fn=self.check_attributes, name="check_attributes"),
            FunctionTool.from_defaults(fn=self.check_equipment, name="check_equipment"),
            FunctionTool.from_defaults(fn=self.check_hp, name="check_hp"),
            FunctionTool.from_defaults(fn=self.check_skills, name="check_skills"),
        ]
        self.agent = ReActAgent.from_tools(self.tools, llm=get_llm(), verbose=True)

    def interpret_action(self, user_input: str) -> str:
        context = f"""
You are an interpreter for {self.character.name}, a level {self.character.level} 
{self.character.chr_race} {self.character.chr_class}. 
Based on the user's input, determine the most appropriate action to take then take that action.
For example, if the user wants tocast a spell, first check if the character knows the spell using the check_spells function.
Then, if the spell is known, use the cast_spell function with the appropriate parameters.
For other actions, use the appropriate function from the available tools.
Respond with the result of the action taken.
If you cannot determine the action to take, respond with "The narrator is confused by these strange words, can you try again?"
If you do not call a functon, the action will not be taken.

User input: {user_input}
"""
        response = self.agent.chat(context)
        return str(response)

    def move(self, direction: str) -> str:
        return f"{self.character.name} moves {direction}."

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

    def use_item(self, item_name: str) -> str:
        item = next((i for i in self.character.inventory if i.name.lower() == item_name.lower()), None)
        if not item:
            return f"{self.character.name} doesn't have {item_name} in their inventory."
        return f"{self.character.name} uses {item_name}."

    def check_inventory(self) -> str:
        inventory = ", ".join([item.name for item in self.character.inventory]) if self.character.inventory else "Empty"
        return f"{self.character.name}'s inventory: {inventory}"

    def check_status(self) -> str:
        status = (
            f"{self.character.name}'s status:\n"
            f"HP: {self.character.current_hp}/{self.character.max_hp}\n"
            f"Level: {self.character.level}\n"
            f"Class: {self.character.chr_class}\n"
            f"Race: {self.character.chr_race}\n"
            f"Armor Class: {self.character.armor_class}\n"
            f"Initiative: {self.character.initiative}\n"
            f"Speed: {self.character.speed}\n"
            f"Experience Points: {self.character.experience_points}\n"
            f"Proficiency Bonus: {self.character.proficiency_bonus}\n"
        )
        return status

    def intimidate(self, target: str) -> str:
        return f"{self.character.name} attempts to intimidate {target}."

    def persuade(self, target: str) -> str:
        return f"{self.character.name} attempts to persuade {target}."

    def deceive(self, target: str) -> str:
        return f"{self.character.name} attempts to deceive {target}."

    def say(self, message: str) -> str:
        return f"{self.character.name} says: '{message}'"

    def check_spells(self) -> str:
        spells = ", ".join([spell.name for spell in self.character.spells]) if self.character.spells else "No spells known"
        spell_slots = ", ".join([f"Level {level}: {slots}" for level, slots in self.character.spell_slots.items() if slots > 0])
        return f"{self.character.name}'s known spells: {spells}\nAvailable spell slots: {spell_slots}"

    def check_attributes(self) -> str:
        return str(self.character.attributes)

    def check_equipment(self) -> str:
        equipped_items = []
        for slot, items in self.character.equipped_items.items():
            for item in items:
                if item:
                    equipped_items.append(f"{slot.capitalize()}: {item.name}")
        equipped_str = "\n".join(equipped_items) if equipped_items else "No items equipped"
        return f"{self.character.name}'s equipped items:\n{equipped_str}"

    def check_hp(self) -> str:
        return f"{self.character.name}'s HP: {self.character.current_hp}/{self.character.max_hp}"

    def check_skills(self) -> str:
        skills_str = "\n".join([f"{skill}: {modifier}" for skill, modifier in self.character.skills.items()]) if self.character.skills else "No skills"
        return f"{self.character.name}'s skills:\n{skills_str}"