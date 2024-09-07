from typing import List, Optional
from llama_index.llms.ollama import Ollama
from llama_index.core.tools import FunctionTool
from .character import Character, Attributes
from .actions import Action, AttackAction, CastSpellAction
from .spells import Spell
from pydantic import Field

class PlayerAgent:
    character: Character
    llm: Ollama
    tools: List[FunctionTool]

    def __init__(self, character: Character):
        self.character = character
        self.llm = Ollama(model="llama3.1")
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

    def interpret_action(self, user_input: str) -> str:
        # Direct mapping for specific queries
        if user_input.lower() in ["what spells do i have?", "check spells"]:
            return self.check_spells()
        elif user_input.lower() in ["what weapons do i have?", "check weapons", "check equipment"]:
            return self.check_equipment()
        elif user_input.lower().startswith("i hit") or user_input.lower().startswith("i attack"):
            return self.attack(user_input.split(maxsplit=2)[-1])
        elif user_input.lower().startswith("i say") or user_input.lower().startswith("say"):
            return self.say(user_input.split(maxsplit=1)[-1])
        elif user_input.lower().startswith("cast") or "cast" in user_input.lower():
            words = user_input.lower().split()
            spell_name = next((word for word in words if word not in ["cast", "i", "spell", "on", "at"]), None)
            target = next((word for word in reversed(words) if word not in ["cast", "i", "spell", "on", "at", spell_name]), None) if spell_name else None
            return self.cast_spell(spell_name, target)

        # For more complex queries, use the LLM
        context = (
            f"You are an interpreter for {self.character.name}, a level {self.character.level} "
            f"{self.character.chr_race} {self.character.chr_class}. "
            f"Based on the user's input, determine the most appropriate action to take. "
            f"Available actions are: move, attack, cast_spell, use_item, check_inventory, check_status, "
            f"intimidate, persuade, deceive, say, check_spells, check_attributes, check_equipment, "
            f"check_hp, check_skills. "
            f"If the user is trying to speak or say something, use the 'say' action. "
            f"If the user is trying to cast a spell, use the 'cast_spell' action. "
            f"Respond with the action name followed by any necessary parameters.\n\n"
            f"User input: {user_input}\n\n"
            f"Action interpretation:"
        )
        interpretation = self.llm.complete(context).text.strip()
        return self.execute_action(interpretation)

    def execute_action(self, interpretation: str) -> str:
        parts = interpretation.split(maxsplit=1)
        action_name = parts[0].lower()
        params = parts[1] if len(parts) > 1 else ""

        action_map = {
            "move": self.move,
            "attack": self.attack,
            "cast_spell": self.cast_spell,
            "use_item": self.use_item,
            "check_inventory": self.check_inventory,
            "check_status": self.check_status,
            "intimidate": self.intimidate,
            "persuade": self.persuade,
            "deceive": self.deceive,
            "say": self.say,
            "check_spells": self.check_spells,
            "check_attributes": self.check_attributes,
            "check_equipment": self.check_equipment,
            "check_hp": self.check_hp,
            "check_skills": self.check_skills,
        }

        if action_name in action_map:
            return action_map[action_name](params)
        else:
            return f"Unknown action: {action_name}"

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

    def check_inventory(self, params: str = "") -> str:
        inventory = ", ".join([item.name for item in self.character.inventory]) if self.character.inventory else "Empty"
        return f"{self.character.name}'s inventory: {inventory}"

    def check_status(self, params: str = "") -> str:
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

    def check_spells(self, params: str = "") -> str:
        spells = ", ".join([spell.name for spell in self.character.spells]) if self.character.spells else "No spells known"
        return f"{self.character.name}'s known spells: {spells}"

    def check_attributes(self, params: str = "") -> str:
        return str(self.character.attributes)

    def check_equipment(self, params: str = "") -> str:
        equipped_items = []
        for slot, items in self.character.equipped_items.items():
            for item in items:
                if item:
                    equipped_items.append(f"{slot.capitalize()}: {item.name}")
        equipped_str = "\n".join(equipped_items) if equipped_items else "No items equipped"
        return f"{self.character.name}'s equipped items:\n{equipped_str}"

    def check_hp(self, params: str = "") -> str:
        return f"{self.character.name}'s HP: {self.character.current_hp}/{self.character.max_hp}"

    def check_skills(self, params: str = "") -> str:
        skills_str = "\n".join([f"{skill}: {modifier}" for skill, modifier in self.character.skills.items()]) if self.character.skills else "No skills"
        return f"{self.character.name}'s skills:\n{skills_str}"

# Example usage remains the same