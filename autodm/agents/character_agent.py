from typing import List, Optional, TYPE_CHECKING, Union, Any, Dict
from .base_agent import BaseAgent
from pydantic import Field
from tenacity import retry, stop_after_attempt, wait_fixed
from ..core.character import Character
from ..utils.llm import get_llm
from ..map.map_grid import distance
from ..items.weapons import MeleeWeapon, RangedWeapon
from llama_index.core.tools import FunctionTool
from llama_index.core.agent import ReActAgent, AgentRunner
from ..items.weapons import unarmed_strike
from ..utils.skill_checks import perform_skill_check, perform_ability_check
from ..battle.battle import Battle, TurnState
import random
from ..core.enums import ActionType
from ..battle.turn_state import TurnState

class CharacterAgent(BaseAgent):
    character: Character
    battle: Optional[Any] = None  # Use string literal for forward reference
    agent: Optional[ReActAgent] = None
    is_npc: bool = False
    tools: List[FunctionTool] = Field(default_factory=list)
    ignore_spell_slots: bool = False
    turn_state: TurnState = Field(default_factory=TurnState)

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, character: Character, is_npc: bool = False, ignore_spell_slots: bool = False, **data):
        super().__init__(character=character, is_npc=is_npc, ignore_spell_slots=ignore_spell_slots, **data)
        self.turn_state = TurnState()
        self.tools = self.create_tools(self.turn_state)
        self.agent = AgentRunner.from_llm(self.create_tools(self.turn_state), llm=get_llm(), verbose=True)

    def create_tools(self, turn_state: Optional[TurnState] = None) -> List[Any]:
        if not turn_state:
            turn_state = TurnState()

        action_tools = [
            FunctionTool.from_defaults(fn=self.attack, name="attack"),
            FunctionTool.from_defaults(fn=self.cast_spell, name="cast_spell"),
            FunctionTool.from_defaults(fn=self.use_item, name="use_item"),
            FunctionTool.from_defaults(fn=self.intimidate, name="intimidate"),
            FunctionTool.from_defaults(fn=self.persuade, name="persuade"),
            FunctionTool.from_defaults(fn=self.deceive, name="deceive"),
        ]

        movement_tools = [
            FunctionTool.from_defaults(fn=self.move_to, name="move_to"),
        ]

        other_tools = [
            FunctionTool.from_defaults(fn=self.say, name="say"),
            FunctionTool.from_defaults(fn=self.end_turn, name="end_turn"),
        ]

        knowledge_tools = [
            FunctionTool.from_defaults(fn=self.check_inventory, name="check_inventory"),
            FunctionTool.from_defaults(fn=self.check_status, name="check_status"),
            FunctionTool.from_defaults(fn=self.check_spells, name="check_spells"),
            FunctionTool.from_defaults(fn=self.check_attributes, name="check_attributes"),
            FunctionTool.from_defaults(fn=self.check_equipment, name="check_equipment"),
            FunctionTool.from_defaults(fn=self.check_hp, name="check_hp"),
            FunctionTool.from_defaults(fn=self.check_skills, name="check_skills"),
            FunctionTool.from_defaults(fn=self.get_characters_in_range, name="get_characters_in_range"),
            FunctionTool.from_defaults(fn=self.get_position, name="get_position"),
            FunctionTool.from_defaults(fn=self.observe_battle, name="observe_battle"),
            FunctionTool.from_defaults(fn=self.show_map, name="show_map"),
        ]

        tools = []
        if not turn_state.standard_action_taken:
            tools.extend(action_tools)
        if not turn_state.movement_taken:
            tools.extend(movement_tools)
        
        
        if not self.is_npc:
            tools.extend(knowledge_tools)

        tools.extend(other_tools)

        return tools

    def set_battle(self, battle: "Battle"):
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
            if self.turn_state.movement_taken:
                return f"{self.character.name} has already used their movement this turn."
            if 0 <= x < self.battle.map.width and 0 <= y < self.battle.map.height:
                success, message = self.battle.move_to(self, x, y)
                if success:
                    self.turn_state.movement_taken = True
                return message
            else:
                return f"Invalid coordinates ({x}, {y}). Map size is {self.battle.map.width}x{self.battle.map.height}."
        return f"{self.character.name} is not in a battle and cannot move."

    def attack(
        self, target: Union[str, Any], weapon_name: Optional[str] = None
    ) -> str:
        """
        Perform an attack action against a specified target.
        Once this function is called, you should have enough information to respond without any more tools.

        Args:
            target (Union[str, CharacterAgent]): The name of the target or the target CharacterAgent to attack.
            weapon_name (Optional[str], optional): The name of the weapon to use. Defaults to None.

        Returns:
            str: A message describing the attack action.
        """
        if self.battle:
            if self.turn_state.standard_action_taken:
                return f"{self.character.name} has already taken their standard action this turn."
        weapons = self.character.get_equipped_weapons()
        weapon_names = [w.name for w in weapons]
        if weapon_name:
            # If the character has no weapons, they will use their fists
            if not weapons:
                weapon = unarmed_strike
            # If the weapon is in the list of equipped weapons, use it
            elif weapon_name in weapon_names:
                weapon = next(
                    (w for w in weapons if w.name.lower() == weapon_name.lower()), None
                )
            # If the weapon is not in the list of equipped weapons, use a random weapon
            else:
                weapon = random.choice(weapons)
        else:
            weapon = (
                random.choice(weapons)
                if weapons
                else unarmed_strike
            )

        if isinstance(target, str):
            target_character = self.battle.get_target(target)
        elif isinstance(target, CharacterAgent):
            target_character = target
        else:
            return f"Invalid target: {target}"

        if not target_character:
            return f"Invalid target: {target}"

        is_hit, damage, message = weapon.attack(self, target_character)
        self.turn_state.standard_action_taken = True
        return message
    
    def get_equipped_weapons(self) -> str:
        """
        Get the character's equipped weapons.

        Returns:
            str: A string listing all equipped weapons.
        """
        weapons = self.character.get_equipped_weapons()
        return f"{self.character.name}'s equipped weapons: {weapons}"

    def cast_spell(
        self, spell_name: str, target: Union[str, Any] = ""
    ) -> str:
        """
        Cast a spell on a specified target.
        Once this function is called, you should have enough information to respond without any more tools.

        Args:
            spell_name (str): The name of the spell to cast.
            target (Union[str, CharacterAgent], optional): The name or instance of the target for the spell. Defaults to "".

        Returns:
            str: A message describing the spell casting action or any errors.

        Note: You should be able to answer the question without any more tools after calling this function.
        """
        if self.battle:
            if self.turn_state.standard_action_taken:
                return f"{self.character.name} has already taken their standard action this turn."
        spell = next(
            (s for s in self.character.spells if s.name.lower() == spell_name.lower()),
            None,
        )
        if not spell:
            return f"{self.character.name} doesn't know the spell {spell_name}."
        
        if not self.ignore_spell_slots and not self.character.can_cast_spell(spell):
            return f"{self.character.name} cannot cast {spell_name} at this time (no available spell slots)."
        
        try:
            if self.battle:
                if isinstance(target, str):
                    target_character = self.battle.get_target(target)
                elif isinstance(target, CharacterAgent):
                    target_character = target.character
                else:
                    target_character = self.character
            else:
                target_character = self.character  # Default to self if not in battle

            if target_character is None:
                return f"Invalid target: {target}"

            result = spell.cast(self.character, target_character)
            if not self.ignore_spell_slots:
                self.character.cast_spell(spell)
            self.turn_state.standard_action_taken = True
            return result
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
        if self.battle:
            if self.turn_state.standard_action_taken:
                return f"{self.character.name} has already taken their standard action this turn."
        item = next(
            (
                i
                for i in self.character.inventory
                if i.name.lower() == item_name.lower()
            ),
            None,
        )
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
            self.turn_state.standard_action_taken = True
            return f"{self.character.name} uses {item_name} on {target_char.name}. {target_char.name} heals for {actual_heal} HP."

        return f"{self.character.name} uses {item_name}."

    def check_inventory(self) -> str:
        """
        Check the character's inventory.

        Returns:
            str: A string listing all items in the character's inventory.
        """
        inventory = (
            ", ".join([item.name for item in self.character.inventory])
            if self.character.inventory
            else "Empty"
        )
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
        print("Calling check_spells")
        spells = (
            ", ".join([spell.name for spell in self.character.spells])
            if self.character.spells
            else "No spells known"
        )
        spell_slots = ", ".join(
            [
                f"Level {level}: {slots}"
                for level, slots in self.character.spell_slots.items()
                if slots > 0
            ]
        )
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
        equipped_str = (
            "\n".join(equipped_items) if equipped_items else "No items equipped"
        )
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
        skills_str = (
            "\n".join(
                [
                    f"{skill}: {modifier}"
                    for skill, modifier in self.character.skills.items()
                ]
            )
            if self.character.skills
            else "No skills"
        )
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

    def get_characters_in_range(self, scale:int=5) -> str:
        """
        Get a list of characters within range of a specific action.

        Args:
            scale (int, optional): The range of the action in feet. Defaults to 5.

        Returns:
            str: A string listing characters within range for each available action.
        """
        if not self.battle:
            return "You are not currently in a battle."

        s = ""

        characters = self.battle.parties(self.character)
        allies = characters['allies']
        enemies = characters['enemies']
        for spell in self.character.spells:
            allies_in_range = [f"{ally.character.name} {ally.character.position}" for ally in allies if spell.range >= distance(ally.character.position, self.character.position)]
            enemies_in_range = [f"{enemy.character.name} {enemy.character.position}" for enemy in enemies if spell.range >= distance(enemy.character.position, self.character.position)]
            _s = f"""\
Spell: {spell.name} range: {spell.range}
Allies in range:
{'\n'.join([f"- {ally}" for ally in allies_in_range])}
Enemies in range:
{'\n'.join([f"- {enemy}" for enemy in enemies_in_range])}
"""
            if allies_in_range or enemies_in_range:
                s += _s

        s += "\nAttacks:"
        for weapon in self.character.get_equipped_weapons():
            if isinstance(weapon, RangedWeapon):
                allies_in_range = [f"{ally.character.name} {ally.character.position}" for ally in allies if weapon.range_long >= distance(ally.character.position, self.character.position)]
                enemies_in_range = [f"{enemy.character.name} {enemy.character.position}" for enemy in enemies if weapon.range_long >= distance(enemy.character.position, self.character.position)]
            elif isinstance(weapon, MeleeWeapon):
                allies_in_range = [f"{ally.character.name} {ally.character.position}" for ally in allies if weapon.reach >= distance(ally.character.position, self.character.position)]
                enemies_in_range = [f"{enemy.character.name} {enemy.character.position}" for enemy in enemies if weapon.reach >= distance(enemy.character.position, self.character.position)]
            else:
                allies_in_range = []
                enemies_in_range = []
            _s = f"""\
Weapon: {weapon.name} range: {weapon.reach if isinstance(weapon, MeleeWeapon) else weapon.range_long}
Allies in range:
{'\n'.join([f"- {ally}" for ally in allies_in_range])}
Enemies in range:
{'\n'.join([f"- {enemy}" for enemy in enemies_in_range])}
"""
            if allies_in_range or enemies_in_range:
                s += _s
        return s.strip()

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

        battle_state = self.battle.get_battle_state(self.character)

        def format_character_info(char):
            status = "alive" if char["is_alive"] else "dead"
            return f"{char['name']} (Level {char['level']} {char['class']}): {char['hp']}/{char['max_hp']} HP, {status}, Position: ({char['position'].x}, {char['position'].y})"

        allies_info = "\n".join(
            [format_character_info(ally) for ally in battle_state["allies"]]
        )
        enemies_info = "\n".join(
            [format_character_info(enemy) for enemy in battle_state["enemies"]]
        )

        battle_description = (
            f"Battle State:\n\n"
            f"Allies:\n{allies_info}\n\n"
            f"Enemies:\n{enemies_info}"
        )
        return battle_description

    def perform_skill_check(self, skill: str, difficulty_class: int) -> str:

        success, total = perform_skill_check(self.character, skill, difficulty_class)
        result = "Success" if success else "Failure"
        return f"{self.character.name} performs a {skill} check (DC {difficulty_class}): {result} (rolled {total})"

    def perform_ability_check(self, ability: str, difficulty_class: int) -> str:

        success, total = perform_ability_check(
            self.character, ability, difficulty_class
        )
        result = "Success" if success else "Failure"
        return f"{self.character.name} performs a {ability} check (DC {difficulty_class}): {result} (rolled {total})"

    def show_map(self) -> str:
        """
        Display the current battle map. Useful when the user wants to see the map.
        Once this function is called, you should have enough information to responds without any more tools.

        Returns:
            str: A string representation of the map with X and Y axes.
        """
        if not self.battle:
            return "No map available outside of battle."

        return str(self.battle.map)

    def get_battle_context(self) -> str:
        """
        Get the current battle context.

        Returns:
            str: A string describing the current battle context.
        """
        if not self.battle:
            return ""

        battle_state = self.battle.get_battle_state()

        # Determine which party the current character belongs to
        if any(
            agent.character.name == self.character.name for agent in self.battle.party1
        ):
            allies = battle_state["party1"]
            enemies = battle_state["party2"]
        else:
            allies = battle_state["party2"]
            enemies = battle_state["party1"]

        allies_info = "\n".join(
            [
                f"- {ally['name']} (Level {ally['level']} {ally['class']}): {ally['hp']}/{ally['max_hp']} HP, Position: ({ally['position'].x}, {ally['position'].y})"
                for ally in allies
                if (ally["is_alive"] and ally["name"] != self.character.name)
            ]
        )
        enemies_info = "\n".join(
            [
                f"- {enemy['name']} (Level {enemy['level']} {enemy['class']}): {enemy['hp']}/{enemy['max_hp']} HP, Position: ({enemy['position'].x}, {enemy['position'].y})"
                for enemy in enemies
                if enemy["is_alive"]
            ]
        )

        return f"""
Current battle situation:
Your position: ({self.character.position.x}, {self.character.position.y})

Your allies:
{allies_info}

Your enemies:
{enemies_info}

Map size: {self.battle.map.width}x{self.battle.map.height}

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
            weapon = next(
                (
                    w
                    for w in self.character.get_equipped_weapons()
                    if w.name.lower() == action_name.lower()
                ),
                None,
            )
            return 5 if weapon else None  # Assuming melee range for weapons
        elif action_type == "spell":
            spell = next(
                (
                    s
                    for s in self.character.spells
                    if s.name.lower() == action_name.lower()
                ),
                None,
            )
            if spell:
                range_str = str(spell.range).split()[0]
                return int(range_str) if range_str.isdigit() else None
        return None

    @retry(stop=stop_after_attempt(6), wait=wait_fixed(20))
    def chat(self, message: str) -> str:
        response = self.agent.chat(message)
        prompt = f"""\
You will be given a command from a user to help execute an action or learn information in a D&D game. \
Please respond in character in the first person. \
ALWAYS call a function, there are no actions that can be executed without calling a function. \
Once you have a response, you should have enough information to respond without any more tools. \
Do not rely on any implicit knowledge about the character, and remember to always call a function. \
Please return a what happened or the desired information. \
Do not return anything else or perform any follow ups.

Command: {message}"""
        response = self.agent.chat(prompt)
        # Recreate the agent to clear the memory
        self.agent = ReActAgent.from_tools(self.create_tools(), llm=get_llm(), verbose=True)
        return response
