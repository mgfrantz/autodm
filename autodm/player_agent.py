from typing import List, Optional, Dict, Union, TYPE_CHECKING
from llama_index.core.tools import BaseTool, FunctionTool
from llama_index.core.agent import ReActAgent
from .character import Character, Attributes
from .spells import Spell
from pydantic import Field
from .llm import get_llm, complete

if TYPE_CHECKING:
    from .battle import Battle
else:
    from .types import Battle

class PlayerAgent:
    character: Character
    tools: List[BaseTool]
    agent: ReActAgent
    allies: Dict[str, Character] = Field(default_factory=dict)
    enemies: Dict[str, Character] = Field(default_factory=dict)
    battle: Optional['Battle'] = None

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
            FunctionTool.from_defaults(fn=self.observe_battle, name="observe_battle"),
        ]
        self.agent = ReActAgent.from_tools(self.tools, llm=get_llm(), verbose=True)

    def interpret_action(self, user_input: str) -> str:
        battle_context = self.get_battle_context() if self.battle else ""
        
        context = f"""
You are an interpreter for {self.character.name}, a level {self.character.level} \
{self.character.chr_race} {self.character.chr_class}. 
{battle_context}
Based on the user's input, determine the most appropriate action to take then take that action. \
For example, if the user wants to cast a spell, first check if the character knows the spell using the check_spells function. \
Then, if the spell is known, use the cast_spell function with the appropriate parameters. \
For other actions, use the appropriate function from the available tools. \
Respond with the result of the action taken. \
If you cannot determine the action to take, respond with "The narrator is confused by these strange words, can you try again?" \
If you do not call a function, the action will not be taken. \
During battle, once an action like casting a spell or attacking is taken, the turn should end.

User input: {user_input} \
"""
        response = self.agent.chat(context)
        return str(response)

    def get_battle_context(self) -> str:
        battle_state = self.battle.get_battle_state()
        
        allies_info = "\n".join([f"- {ally['name']} (Level {ally['level']} {ally['class']}): {ally['hp']}/{ally['max_hp']} HP" for ally in battle_state['allies']])
        enemies_info = "\n".join([f"- {enemy['name']} (Level {enemy['level']} {enemy['class']}): {enemy['hp']}/{enemy['max_hp']} HP" for enemy in battle_state['enemies']])
        
        return f"""
You are currently in a battle.
Your allies:
{allies_info}

Your enemies:
{enemies_info}

Remember to consider the battle situation when interpreting actions.
"""

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

    def add_character(self, name: str, relation: str, chr_class: str, chr_race: str, level: int = 1) -> str:
        """
        Add a new character as an ally or enemy.

        Args:
        name (str): The name of the character to add.
        relation (str): The relation to the player character ('ally' or 'enemy').
        chr_class (str): The class of the character.
        chr_race (str): The race of the character.
        level (int): The level of the character (default is 1).

        Returns:
        str: A message confirming the addition of the character.

        Example:
        >>> player_agent.add_character("Gandalf", "ally", "Wizard", "Human", 20)
        "Gandalf, a level 20 Human Wizard, has been added as an ally."
        """
        new_character = Character.generate(name, chr_class=chr_class, chr_race=chr_race, level=level)
        
        if relation.lower() == 'ally':
            self.allies[name] = new_character
            return f"{name}, a level {level} {chr_race} {chr_class}, has been added as an ally."
        elif relation.lower() == 'enemy':
            self.enemies[name] = new_character
            return f"{name}, a level {level} {chr_race} {chr_class}, has been added as an enemy."
        else:
            return f"Invalid relation '{relation}'. Please use 'ally' or 'enemy'."

    def check_allies(self) -> str:
        """
        Check the list of allies.

        Returns:
        str: A string listing all allies or a message if there are no allies.

        Example:
        >>> player_agent.check_allies()
        "Allies: Gandalf (level 20 Human Wizard), Aragorn (level 15 Human Ranger)"
        """
        if not self.allies:
            return f"{self.character.name} has no allies at the moment."
        ally_list = ", ".join([f"{name} (level {char.level} {char.chr_race} {char.chr_class})" for name, char in self.allies.items()])
        return f"Allies: {ally_list}"

    def check_enemies(self) -> str:
        """
        Check the list of enemies.

        Returns:
        str: A string listing all enemies or a message if there are no enemies.

        Example:
        >>> player_agent.check_enemies()
        "Enemies: Sauron (level 30 Maiar Necromancer), Saruman (level 25 Human Wizard)"
        """
        if not self.enemies:
            return f"{self.character.name} has no known enemies at the moment."
        enemy_list = ", ".join([f"{name} (level {char.level} {char.chr_race} {char.chr_class})" for name, char in self.enemies.items()])
        return f"Enemies: {enemy_list}"

    def observe_battle(self) -> str:
        """
        Observe the current state of the battle.
        
        Returns:
        str: A description of the current battle state.
        """
        if not self.battle:
            return "You are not currently in a battle."

        battle_state = self.battle.get_battle_state()
        
        allies_info = []
        for ally in battle_state['allies']:
            status = "alive" if ally['is_alive'] else "dead"
            allies_info.append(f"{ally['name']} (Level {ally['level']} {ally['class']}): {ally['hp']}/{ally['max_hp']} HP, {status}")

        enemies_info = []
        for enemy in battle_state['enemies']:
            status = "alive" if enemy['is_alive'] else "dead"
            enemies_info.append(f"{enemy['name']} (Level {enemy['level']} {enemy['class']}): {enemy['hp']}/{enemy['max_hp']} HP, {status}")

        battle_description = f"Battle State:\n\nAllies:\n" + "\n".join(allies_info) + "\n\nEnemies:\n" + "\n".join(enemies_info)
        return battle_description

    def set_battle(self, battle: 'Battle'):
        """Set the current battle for the player agent."""
        self.battle = battle