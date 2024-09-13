from typing import Optional, Dict, TYPE_CHECKING, Any, List, Union
from .character import Character, Attributes, Position
from .llm import get_llm, complete
from .items import EquipmentItem
from llama_index.core.tools import BaseTool, FunctionTool
from llama_index.core.agent import ReActAgent
import random
import json
from pydantic import Field

if TYPE_CHECKING:
    from .battle import Battle

class CharacterAgent:
    character: Character
    battle: Optional['Battle'] = None
    agent: ReActAgent
    is_npc: bool = False

    def __init__(self, character: Character, is_npc: bool = False):
        self.character = character
        self.is_npc = is_npc
        self.tools = [
            FunctionTool.from_defaults(fn=self.move_to, name="move_to"),
            FunctionTool.from_defaults(fn=self.attack, name="attack"),
            FunctionTool.from_defaults(fn=self.cast_spell, name="cast_spell"),
            FunctionTool.from_defaults(fn=self.use_item, name="use_item"),
            FunctionTool.from_defaults(fn=self.check_inventory, name="check_inventory"),
            FunctionTool.from_defaults(fn=self.check_status, name="check_status"),
            FunctionTool.from_defaults(fn=self.check_spells, name="check_spells"),
            FunctionTool.from_defaults(fn=self.check_attributes, name="check_attributes"),
            FunctionTool.from_defaults(fn=self.check_equipment, name="check_equipment"),
            FunctionTool.from_defaults(fn=self.check_hp, name="check_hp"),
            FunctionTool.from_defaults(fn=self.check_skills, name="check_skills"),
            FunctionTool.from_defaults(fn=self.get_position, name="get_position"),
            FunctionTool.from_defaults(fn=self.get_characters_in_range, name="get_characters_in_range"),
            FunctionTool.from_defaults(fn=self.intimidate, name="intimidate"),
            FunctionTool.from_defaults(fn=self.persuade, name="persuade"),
            FunctionTool.from_defaults(fn=self.deceive, name="deceive"),
            FunctionTool.from_defaults(fn=self.say, name="say"),
            FunctionTool.from_defaults(fn=self.observe_battle, name="observe_battle"),
            FunctionTool.from_defaults(fn=self.perform_skill_check, name="perform_skill_check"),
            FunctionTool.from_defaults(fn=self.perform_ability_check, name="perform_ability_check"),
            FunctionTool.from_defaults(fn=self.show_map, name="show_map"),
        ]
        self.agent = ReActAgent.from_tools(self.tools, llm=get_llm(), verbose=True)

    def set_battle(self, battle: 'Battle'):
        self.battle = battle

    def move_to(self, x: int, y: int) -> str:
        """
        Move the character to a specific location on the battle map using numerical coordinates.
        Once this function is called, you should have enough information to respond without any more tools.

        Args:
            x (int): The x-coordinate of the destination (0-9 for columns).
            y (int): The y-coordinate of the destination (0-9 for rows).

        Returns:
            str: A message describing the movement action or any errors.

        Note: You should be able to answer the question without any more tools after calling this function.
        """
        if self.battle:
            if 0 <= x < self.battle.map_size[0] and 0 <= y < self.battle.map_size[1]:
                success, message = self.battle.move_to(self.character, (x, y))
                return message
            else:
                return f"Invalid coordinates ({x}, {y}). Map size is {self.battle.map_size[0]}x{self.battle.map_size[1]}."
        return f"{self.character.name} is not in a battle and cannot move."

    def attack(self, target: str) -> str:
        """
        Perform an attack action against a specified target.
        Once this function is called, you should have enough information to responds without any more tools.

        Args:
            target (str): The name of the target to attack.

        Returns:
            str: A message describing the attack action.

        Note: You should be able to answer the question without any more tools after calling this function.
        """
        weapon = self.character.get_equipped_weapons()[0] if self.character.get_equipped_weapons() else None
        weapon_name = weapon.name if weapon else "an unarmed strike"
        return f"{self.character.name} attacks {target} with {weapon_name}."

    def cast_spell(self, spell_name: str, target: str = "") -> str:
        """
        Cast a spell on a specified target.
        Once this function is called, you should have enough information to responds without any more tools.

        Args:
            spell_name (str): The name of the spell to cast.
            target (str, optional): The name of the target for the spell. Defaults to "".

        Returns:
            str: A message describing the spell casting action or any errors.

        Note: You should be able to answer the question without any more tools after calling this function.
        """
        spell = next((s for s in self.character.spells if s.name.lower() == spell_name.lower()), None)
        if not spell:
            return f"{self.character.name} doesn't know the spell {spell_name}."
        if not self.character.can_cast_spell(spell):
            return f"{self.character.name} cannot cast {spell_name} at this time (no available spell slots)."
        try:
            self.character.cast_spell(spell)
            if spell.range.lower() == "self":
                return f"{self.character.name} casts {spell.name} on themselves."
            elif target:
                return f"{self.character.name} casts {spell.name} at {target}."
            else:
                return f"{self.character.name} casts {spell.name}."
        except ValueError as e:
            return str(e)

    def use_item(self, item_name: str, target: str = "") -> str:
        """
        Use an item from the character's inventory.
        Once this function is called, you should have enough information to responds without any more tools.
        Args:
            item_name (str): The name of the item to use.
            target (str, optional): The name of the target for the item. Defaults to "".

        Returns:
            str: A message describing the item usage or any errors.
        """
        item = next((i for i in self.character.inventory if i.name.lower() == item_name.lower()), None)
        if not item:
            return f"{self.character.name} doesn't have {item_name} in their inventory."
        
        if item.item_type == "potion" and "heal" in item.effects:
            target_char = self.battle.get_target(target) if target else self.character
            if not target_char:
                return f"Invalid target: {target}"
            
            heal_amount = item.effects["heal"]
            old_hp = target_char.hp
            target_char.hp += heal_amount
            actual_heal = target_char.hp - old_hp
            
            self.character.inventory.remove(item)
            
            return f"{self.character.name} uses {item_name} on {target_char.name}. {target_char.name} heals for {actual_heal} HP."
        
        return f"{self.character.name} uses {item_name}."

    def check_inventory(self) -> str:
        """
        Check the character's inventory.

        Returns:
            str: A string listing all items in the character's inventory.
        """
        inventory = ", ".join([item.name for item in self.character.inventory]) if self.character.inventory else "Empty"
        return f"{self.character.name}'s inventory: {inventory}"

    def check_status(self) -> str:
        """
        Check the character's current status.

        Returns:
            str: A string describing the character's current status, including HP, level, class, etc.
        """
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

    def check_spells(self) -> str:
        """
        Check the character's known spells and available spell slots.

        Returns:
            str: A string listing known spells and available spell slots.
        """
        spells = ", ".join([spell.name for spell in self.character.spells]) if self.character.spells else "No spells known"
        spell_slots = ", ".join([f"Level {level}: {slots}" for level, slots in self.character.spell_slots.items() if slots > 0])
        return f"{self.character.name}'s known spells: {spells}\nAvailable spell slots: {spell_slots}"

    def check_attributes(self) -> str:
        """
        Check the character's attributes.

        Returns:
            str: A string representation of the character's attributes.
        """
        return str(self.character.attributes)

    def check_equipment(self) -> str:
        """
        Check the character's equipped items.

        Returns:
            str: A string listing all equipped items.
        """
        equipped_items = []
        for slot, items in self.character.equipped_items.items():
            for item in items:
                if item:
                    equipped_items.append(f"{slot.capitalize()}: {item.name}")
        equipped_str = "\n".join(equipped_items) if equipped_items else "No items equipped"
        return f"{self.character.name}'s equipped items:\n{equipped_str}"

    def check_hp(self) -> str:
        """
        Check the character's current and maximum HP.

        Returns:
            str: A string showing the character's current and maximum HP.
        """
        return f"{self.character.name}'s HP: {self.character.current_hp}/{self.character.max_hp}"

    def check_skills(self) -> str:
        """
        Check the character's skills and their modifiers.

        Returns:
            str: A string listing all of the character's skills and their modifiers.
        """
        skills_str = "\n".join([f"{skill}: {modifier}" for skill, modifier in self.character.skills.items()]) if self.character.skills else "No skills"
        return f"{self.character.name}'s skills:\n{skills_str}"

    def get_position(self) -> str:
        """
        Get the character's current position on the battle map.

        Returns:
            str: A string describing the character's current position.
        """
        if self.battle:
            return f"{self.character.name}'s position: ({self.character.position.x}, {self.character.position.y})"
        return f"{self.character.name} is not in a battle."

    def get_characters_in_range(self, action_type: str, action_name: str) -> str:
        """
        Get a list of characters within range of a specific action.

        Args:
            action_type (str): The type of action (e.g., "weapon" or "spell").
            action_name (str): The name of the action.

        Returns:
            str: A string listing characters within range of the action.
        """
        if not self.battle:
            return "You are not currently in a battle."

        range_feet = self.get_action_range(action_type, action_name)
        if range_feet is None:
            return f"Unknown {action_type}: {action_name}"

        in_range_characters = self.battle.get_characters_in_range(self.character, range_feet)
        
        if not in_range_characters:
            return f"No characters are within range of your {action_name}."
        
        result = f"Characters within range of your {action_name} ({range_feet} feet):\n"
        for character in in_range_characters:
            name = character.name if isinstance(character, type(self)) else character.character.name
            char_type = "Enemy" if isinstance(character, type(self)) else "Ally"
            result += f"- {name} ({char_type})\n"
        
        return result.strip()

    def intimidate(self, target: str) -> str:
        """
        Attempt to intimidate a target.
        Once this function is called, you should have enough information to responds without any more tools.

        Args:
            target (str): The name of the target to intimidate.

        Returns:
            str: A message describing the intimidation attempt.
        """
        return f"{self.character.name} attempts to intimidate {target}."

    def persuade(self, target: str) -> str:
        """
        Attempt to persuade a target.
        Once this function is called, you should have enough information to responds without any more tools.

        Args:
            target (str): The name of the target to persuade.

        Returns:
            str: A message describing the persuasion attempt.
        """
        return f"{self.character.name} attempts to persuade {target}."

    def deceive(self, target: str) -> str:
        """
        Attempt to deceive a target.
        Once this function is called, you should have enough information to responds without any more tools.

        Args:
            target (str): The name of the target to deceive.

        Returns:
            str: A message describing the deception attempt.
        """
        return f"{self.character.name} attempts to deceive {target}."

    def say(self, message: str) -> str:
        """
        Make the character say something.
        Once this function is called, you should have enough information to responds without any more tools.
        Args:
            message (str): The message for the character to say.

        Returns:
            str: A formatted string of the character's speech.
        """
        return f"{self.character.name} says: '{message}'"

    def observe_battle(self) -> str:
        """
        Observe the current state of the battle, including character positions.

        Returns:
            str: A description of the current battle state, including all characters, their HP, and positions.
        """
        if not self.battle:
            return "You are not currently in a battle."

        battle_state = self.battle.get_battle_state()
        
        def format_character_info(char):
            status = "alive" if char['is_alive'] else "dead"
            return f"{char['name']} (Level {char['level']} {char['class']}): {char['hp']}/{char['max_hp']} HP, {status}, Position: ({char['position'].x}, {char['position'].y})"

        allies_info = "\n".join([format_character_info(ally) for ally in battle_state['allies']])
        enemies_info = "\n".join([format_character_info(enemy) for enemy in battle_state['enemies']])

        battle_description = (
            f"Battle State:\n\n"
            f"Allies:\n" + allies_info + "\n\n"
            f"Enemies:\n" + enemies_info
        )
        return battle_description

    def perform_skill_check(self, skill: str, difficulty_class: int) -> str:
        from .skill_checks import perform_skill_check
        success, total = perform_skill_check(self.character, skill, difficulty_class)
        result = "Success" if success else "Failure"
        return f"{self.character.name} performs a {skill} check (DC {difficulty_class}): {result} (rolled {total})"

    def perform_ability_check(self, ability: str, difficulty_class: int) -> str:
        from .skill_checks import perform_ability_check
        success, total = perform_ability_check(self.character, ability, difficulty_class)
        result = "Success" if success else "Failure"
        return f"{self.character.name} performs a {ability} check (DC {difficulty_class}): {result} (rolled {total})"

    def show_map(self) -> str:
        """
        Display the current battle map.
        Once this function is called, you should have enough information to responds without any more tools.

        Returns:
            str: A message indicating whether the map was displayed or not.

        Note: You should be able to answer the question without any more tools after calling this function.
        """
        if self.battle:
            self.battle.display_map()
            return "Map displayed."
        return "No map available outside of battle."

    def get_battle_context(self) -> str:
        if not self.battle:
            return ""

        battle_state = self.battle.get_battle_state()
        
        # Determine which party the current character belongs to
        if any(agent.character.name == self.character.name for agent in self.battle.party1):
            allies = battle_state['party1']
            enemies = battle_state['party2']
        else:
            allies = battle_state['party2']
            enemies = battle_state['party1']

        allies_info = "\n".join([f"- {ally['name']} (Level {ally['level']} {ally['class']}): {ally['hp']}/{ally['max_hp']} HP, Position: ({ally['position'].x}, {ally['position'].y})" for ally in allies])
        enemies_info = "\n".join([f"- {enemy['name']} (Level {enemy['level']} {enemy['class']}): {enemy['hp']}/{enemy['max_hp']} HP, Position: ({enemy['position'].x}, {enemy['position'].y})" for enemy in enemies])
        
        return f"""
Current battle situation:
Your position: ({self.character.position.x}, {self.character.position.y})

Your allies:
{allies_info}

Your enemies:
{enemies_info}

Map size: {self.battle.map_size[0]}x{self.battle.map_size[1]}

Consider the battle situation and positions when making decisions.
"""

    def interpret_action(self, user_input: str) -> str:
        # This method should be implemented in the subclasses (PlayerAgent and NPC)
        raise NotImplementedError("This method should be implemented in the subclass.")

    def get_action_range(self, action_type: str, action_name: str) -> Optional[int]:
        """
        Get the range of the action.

        Args:
            action_type (str): The type of action (e.g., "weapon" or "spell").
            action_name (str): The name of the action.

        Returns:
            int: The range of the action in feet.
            None: If the range is not known.
        """
        if action_type == "weapon":
            weapon = next((w for w in self.character.get_equipped_weapons() if w.name.lower() == action_name.lower()), None)
            return 5 if weapon else None  # Assuming melee range for weapons
        elif action_type == "spell":
            spell = next((s for s in self.character.spells if s.name.lower() == action_name.lower()), None)
            if spell:
                range_str = spell.range.split()[0]
                return int(range_str) if range_str.isdigit() else None
        return None
    
    def chat(self, message: str) -> str:
        response = self.agent.chat(message)
        prompt = f"""\
You will be given a command from a user to help execute an action or learn information in a D&D game. \
Please respond in character. Once you have a response, you should have enough information to respond without any more tools. \
Do not rely on any implicit knowledge about the character, always call a function. \
Please return a what happened.

{message}

Response:"""
        response = self.agent.chat(prompt)
        return response
    
if __name__ == "__main__":
    character = Character.generate()
    agent = CharacterAgent(character)
    while (inp:=input("What would you like to do? ")) != "exit":
        print(agent.chat(inp))