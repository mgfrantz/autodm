from typing import List, Dict, Union, Tuple, Optional, Any
from pydantic import BaseModel, Field
from ..core.character import Character
from ..agents.base_agent import BaseAgent
from ..utils.dice import roll_dice
from ..utils.llm import complete
from ..map.map_grid import Map
from ..core.enums import CharacterState
from ..items.equipment import EquipmentItem
from ..spells.base_spell import Spell
from ..core.position import Position
import random

class BattleAgent(BaseModel):
    context: str = Field(default="You are a Dungeon Master narrating a battle. Describe the action and its immediate result vividly, focusing only on what has just occurred. Do not speculate about future actions or outcomes. Keep the narration concise, around 2-3 sentences. If a character has died, include this information in your narration.")
    
    def narrate(self, action: str, result: str, attacker: str, target: str, damage: int, target_hp: int, target_max_hp: int, death_info: str, attacker_info: Dict[str, Any], target_info: Dict[str, Any]) -> str:
        prompt = f"""
{self.context}

Action: {action}
Result: {result}
Attacker: {attacker}
Attacker Info:
- Class: {attacker_info['class']}
- Race: {attacker_info['race']}
- Equipped Weapon: {attacker_info['weapon']}
- Armor: {attacker_info['armor']}
Target: {target}
Target Info:
- Class: {target_info['class']}
- Race: {target_info['race']}
- Equipped Weapon: {target_info['weapon']}
- Armor: {target_info['armor']}
Damage Dealt: {damage}
Target's Current HP: {target_hp}/{target_max_hp}
Death Information: {death_info}

Narration:
"""
        return complete(prompt)

class Battle(BaseModel):
    party1: List[BaseAgent]
    party2: List[BaseAgent]
    battle_agent: BattleAgent = Field(default_factory=BattleAgent)
    initiative_order: List[BaseAgent] = Field(default_factory=list)
    current_turn: int = 0
    is_battle_over: bool = False
    map: Map = Field(default=Map(width=10, height=10))

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, party1: List[BaseAgent], party2: List[BaseAgent], map_size: Tuple[int, int] = (10, 10)):
        super().__init__(party1=party1, party2=party2, map_size=map_size)
        self.init_battle()

    def init_battle(self):
        for agent in self.party1 + self.party2:
            agent.set_battle(self)
        self.initialize_positions()
        self.roll_initiative()

    def start_battle(self):
        self.run_battle()

    def roll_initiative(self):
        all_combatants = self.party1 + self.party2
        initiative_rolls = [(roll_dice("1d20")[0] + self.get_initiative(c), c) for c in all_combatants]
        initiative_rolls.sort(reverse=True, key=lambda x: x[0])
        self.initiative_order = [agent for _, agent in initiative_rolls]

        print("Initiative order:")
        for i, agent in enumerate(self.initiative_order, 1):
            print(f"{i}. {agent.character.name}")

    def get_initiative(self, agent: BaseAgent) -> int:
        return agent.character.initiative

    def run_battle(self):
        while not self.is_battle_over:
            current_agent = self.initiative_order[self.current_turn]
            
            print("\n" + "="*40)  # Clear separator between turns
            
            if self.is_character_alive(current_agent):
                self.agent_turn(current_agent)
            else:
                print(f"{current_agent.character.name} is dead and cannot take any actions.")

            self.current_turn = (self.current_turn + 1) % len(self.initiative_order)
            self.check_battle_status()

    def is_character_alive(self, agent: BaseAgent) -> bool:
        return agent.character.character_state == CharacterState.ALIVE

    def agent_turn(self, agent: BaseAgent):
        agent.character.movement_remaining = agent.character.speed
        print(f"\n{agent.character.name}'s turn!")
        
        action_taken = False
        movement_taken = False

        while not (action_taken and movement_taken):
            prompt_str = f"You have the following options:\n{'- move' if not movement_taken else ''}\n{'- attack' if not action_taken else ''}\n{'- cast a spell' if not action_taken else ''}\n{'- use an item' if not action_taken else ''}\n{'- end the turn' if not action_taken else ''}\n"
            if agent.is_npc:
                action = agent.decide_action(has_taken_action=action_taken, has_taken_movement=movement_taken)
            else:
                action = agent.chat(input(prompt_str))
            print(f"{agent.character.name} : {action}")
            
            # For NPCs, end the turn if both movement and action are taken
            if (action_taken and movement_taken):
                break
            

        print(f"{agent.character.name}'s turn ends.")

    def handle_action(self, agent: BaseAgent, action: Dict[str, Any]):
        if action['action_type'] == "attack":
            self.handle_attack(agent, action)
        elif action['action_type'] == "cast_spell":
            self.handle_spell(agent, action)
        elif action['action_type'] == "use_item":
            self.handle_item_use(agent, action)

    def player_continue_turn(self) -> bool:
        response = input("Do you want to continue your turn? (yes/no): ").lower().strip()
        return response == 'yes' or response == 'y'

    def handle_attack(self, agent: BaseAgent, action: Dict[str, Any]):
        target = self.get_target(action['target'])
        if target and self.is_character_alive(target):
            weapon = agent.character.get_equipped_weapons()[0] if agent.character.get_equipped_weapons() else None
            target_name = target.character.name
            
            # Check if the target is in range
            distance = self.get_distance_between(agent.character, target.character)
            weapon_range = 5  # Default melee range
            if weapon and 'range' in weapon.effects:
                weapon_range = weapon.effects['range']
            
            if distance * 5 <= weapon_range:  # Convert grid distance to feet
                damage = self.calculate_weapon_damage(weapon, agent.character)
                target.character.hp -= damage
                print(f"{target_name} takes {damage} damage from {agent.character.name}'s attack!")
                self.print_target_hp(target)
                
                # Check for character death before narration
                target_died = self.check_character_death(target)
                
                result = "Success"
                death_info = f"{target_name} has died!" if target_died else ""
                
                attacker_info = self.get_character_info(agent.character)
                target_info = self.get_character_info(target.character)
                
                narration = self.battle_agent.narrate(
                    action=f"{agent.character.name} attacks {target_name} with {weapon.name if weapon else 'an unarmed strike'}",
                    result=result,
                    attacker=agent.character.name,
                    target=target_name,
                    damage=damage,
                    target_hp=target.character.hp,
                    target_max_hp=target.character.max_hp,
                    death_info=death_info,
                    attacker_info=attacker_info,
                    target_info=target_info
                )
                print(f"\nNarrator: {narration}")
            else:
                print(f"{agent.character.name} tries to attack {target_name}, but they are out of range.")
        else:
            print(f"{agent.character.name} tries to attack {action['target']}, but they are not a valid target.")

    def handle_spell(self, agent: BaseAgent, action: Dict[str, Any]):
        target = self.get_target(action['target'])
        if target and self.is_character_alive(target):
            spell_name = action['spell_name']
            spell = next((s for s in agent.character.spells if s.name.lower() == spell_name.lower()), None)
            if spell:
                target_name = target.character.name
                
                # Check if the target is in range
                distance = self.get_distance_between(agent.character, target.character)
                spell_range = spell.range if isinstance(spell.range, int) else 5  # Default to 5 feet for 'touch' spells
                
                if distance * 5 <= spell_range:  # Convert grid distance to feet
                    result = spell.cast(agent.character, target.character)
                    print(result)
                    
                    # Check for character death after spell cast
                    self.check_character_death(target)
                    
                    attacker_info = self.get_character_info(agent.character)
                    target_info = self.get_character_info(target.character)
                    
                    narration = self.battle_agent.narrate(
                        action=f"{agent.character.name} casts {spell_name} at {target_name}",
                        result=result,
                        attacker=agent.character.name,
                        target=target_name,
                        damage=0,  # We don't have access to the damage here, so we'll pass 0
                        target_hp=target.character.current_hp,
                        target_max_hp=target.character.max_hp,
                        death_info="",
                        attacker_info=attacker_info,
                        target_info=target_info
                    )
                    print(f"\nNarrator: {narration}")
                else:
                    print(f"{agent.character.name} tries to cast {spell_name} at {target_name}, but they are out of range.")
            else:
                print(f"{agent.character.name} tries to cast {spell_name}, but they don't know this spell.")
        else:
            print(f"{agent.character.name} tries to cast a spell at {action['target']}, but they are not a valid target.")

    def handle_item_use(self, agent: BaseAgent, action: Dict[str, Any]):
        # Implement item use logic
        pass

    def get_target(self, target_name: str) -> Optional[BaseAgent]:
        """
        Get a target by name.

        Args:
            target_name (str): The name of the target.

        Returns:
            Optional[BaseAgent]: The target with the given name, or None if not found.
        """
        for agent in self.initiative_order:
            if isinstance(agent, BaseAgent) and agent.character.name.lower() == target_name.lower():
                return agent
        return None

    def get_random_target(self, attacker: BaseAgent) -> Optional[BaseAgent]:
        """
        Get a random target from the opposing party.

        Args:
            attacker (BaseAgent): The character attacking.

        Returns:
            Optional[BaseAgent]: A random living target from the opposing party, or None if no targets are alive.
        """
        opposing_party = self.party2 if attacker in self.party1 else self.party1
        living_targets = [agent for agent in opposing_party if self.is_character_alive(agent)]
        return random.choice(living_targets) if living_targets else None

    def calculate_weapon_damage(self, weapon: Optional[EquipmentItem], attacker: Character) -> int:
        """
        Calculate the damage of a weapon.

        Args:
            weapon (Optional[EquipmentItem]): The weapon to calculate the damage of.
            attacker (Character): The character attacking with the weapon.

        Returns:
            int: The damage of the weapon.
        """
        if not weapon:
            return 1  # Unarmed strike damage
        
        damage_dice = weapon.effects['damage']
        damage_rolls = roll_dice(damage_dice)
        total_damage = sum(damage_rolls) + attacker.attributes.get_modifier('strength')
        
        return total_damage

    def calculate_spell_damage(self, spell: Spell, caster: Character) -> int:
        """
        Calculate the damage of a spell.

        Args:
            spell (Spell): The spell to calculate the damage of.
            caster (Character): The character casting the spell.

        Returns:
            int: The damage of the spell.
        """
        if not spell.damage:
            return 0
        
        damage_dice = spell.damage
        caster_level = caster.level

        # Scale damage based on spell level and caster level
        if spell.level > 0:
            # For leveled spells, scale damage based on the spell's level
            damage_dice_count = int(damage_dice.split('d')[0])
            damage_dice_type = damage_dice.split('d')[1]
            scaled_damage_dice = f"{damage_dice_count + spell.level - 1}d{damage_dice_type}"
        else:
            # For cantrips, scale damage based on caster level
            cantrip_scaling = (caster_level + 7) // 6  # Scales at levels 5, 11, and 17
            damage_dice_count = int(damage_dice.split('d')[0]) * cantrip_scaling
            damage_dice_type = damage_dice.split('d')[1]
            scaled_damage_dice = f"{damage_dice_count}d{damage_dice_type}"

        damage_rolls = roll_dice(scaled_damage_dice)
        total_damage = sum(damage_rolls)
        
        # Add spellcasting ability modifier for cantrips (level 0 spells)
        if spell.level == 0:
            spellcasting_ability = self.get_spellcasting_ability(caster)
            total_damage += caster.attributes.get_modifier(spellcasting_ability)
        
        return total_damage

    def get_spellcasting_ability(self, character: Character) -> str:
        """
        Get the spellcasting ability of a character.

        Args:
            character (Character): The character to get the spellcasting ability of.

        Returns:
            str: The spellcasting ability of the character.
        """
        class_ability_map = {
            "Wizard": "intelligence",
            "Sorcerer": "charisma",
            "Cleric": "wisdom",
            "Druid": "wisdom",
            "Warlock": "charisma",
            "Bard": "charisma",
            "Paladin": "charisma",
            "Ranger": "wisdom"
        }
        return class_ability_map.get(character.chr_class, "intelligence")

    def print_target_hp(self, target: BaseAgent):
        """
        Print the HP of a target character.

        Args:
            target (BaseAgent): The target character.
        """
        print(f"{target.character.name}'s HP: {target.character.hp}/{target.character.max_hp}")

    def check_battle_status(self):
        """
        Check the status of the battle.
        """
        party1_alive = any(self.is_character_alive(agent) for agent in self.party1)
        party2_alive = any(self.is_character_alive(agent) for agent in self.party2)

        if not party1_alive or not party2_alive:
            self.is_battle_over = True
            if party1_alive:
                print("\nThe battle is over! Party 1 is victorious!")
            elif party2_alive:
                print("\nThe battle is over! Party 2 is victorious!")
            else:
                print("\nThe battle is over! It's a draw!")

    def check_character_death(self, agent: BaseAgent) -> bool:
        """
        Check if a character is dead.

        Args:
            agent (BaseAgent): The character to check.

        Returns:
            bool: True if the character is dead, False otherwise.
        """
        if agent.character.hp <= 0:
            agent.character.character_state = CharacterState.DEAD
            print(f"{agent.character.name} has died!")
            return True
        return False

    def get_battle_state(self, agent: Optional[BaseAgent] = None) -> Dict[str, List[Dict[str, Union[str, int, bool, Position]]]]:
        if agent:
            return {
                "allies": [self.get_character_info(agent.character) for agent in self.party1],
                "enemies": [self.get_character_info(agent.character) for agent in self.party2]
            }
        else:
            return {
                "party1": [self.get_character_info(agent.character) for agent in self.party1],
                "party2": [self.get_character_info(agent.character) for agent in self.party2]
            }

    def get_character_info(self, character: Character) -> Dict[str, Any]:
        """
        Get the information about a character.

        Args:
            character (Character): The character to get the information of.

        Returns:
            Dict[str, Any]: A dictionary containing the character's information.
        """
        equipped_weapons = character.get_equipped_weapons()
        return {
            "name": character.name,
            "class": character.chr_class,
            "level": character.level,
            "race": character.chr_race,
            "weapons": equipped_weapons,
            "armor": ", ".join([item.name for item in character.equipped_items.get('armor', []) if item]) or "No armor",
            "armor_class": character.armor_class,
            "hp": character.current_hp,
            "max_hp": character.max_hp,
            "position": character.position,
            "is_alive": character.character_state == CharacterState.ALIVE
        }

    def initialize_positions(self):
        """
        Initialize the positions of the characters on the map.
        """
        all_agents = self.party1 + self.party2
        available_positions = [(x, y) for x in range(self.map.width) for y in range(self.map.height)]
        random.shuffle(available_positions)

        for agent in all_agents:
            x, y = available_positions.pop()
            self.map.add_or_update_player(x, y, agent)

    def move_to(self, character: BaseAgent, x: int, y: int, verbose=False) -> Tuple[bool, str]:
        """
        Move a character to a specific position on the map.
        After calling this function, you should be able to respond without any more information.

        Args:
            character (BaseAgent): The character to move.
            x (int): The x-coordinate to move the character to.
            y (int): The y-coordinate to move the character to.
            verbose (bool): Whether to print the move details.

        Returns:
            Tuple[bool, str]: A tuple containing a boolean indicating if the move was successful and a string describing the move.
        """
        if 0 <= x < self.map.width and 0 <= y < self.map.height:
            current_x, current_y = character.character.position.x, character.character.position.y
            if verbose:
                print(f"{character.character.name} moves from ({current_x}, {current_y}) to ({x}, {y})")
            distance = (abs(current_x - x) + abs(current_y - y)) * self.map.scale  # Each cell is 5 feet
            if distance <= character.character.movement_remaining:
                self.map.add_or_update_player(x, y, character)
                character.character.movement_remaining -= distance
                return True, f"{character.character.name} moves to ({x}, {y}). Movement remaining: {character.character.movement_remaining} feet."
            else:
                return False, f"Not enough movement. Required: {distance} feet, Remaining: {character.character.movement_remaining} feet."
        return False, f"Invalid coordinates ({x}, {y}). Map size is {self.map.width}x{self.map.height}."

    def display_map(self, do_return=False):
        """
        Useful when you want to see the map with characters' positions.
        Once you have called this function, you should be able to answer without any more information.

        Args:
            do_return (bool): Whether to return the map string or print it.
        """
        map_str = str(self.map)
        print(map_str)
        if do_return:
            return map_str

    def get_distance_between(self, char1: Character, char2: Character) -> int:
        """
        Get the distance between two characters on the map.

        Args:
            char1 (Character): The first character.
            char2 (Character): The second character.

        Returns:
            int: The distance between the two characters.
        """
        return self.map.distance_between_players(char1.name, char2.name)

    def get_character_position(self, character: BaseAgent) -> Position:
        """
        Get the position of a character on the map.

        Args:
            character (BaseAgent): The character to get the position of.

        Returns:
            Position: The position of the character.
        """
        return self.map.locations[character.character.name]["position"]

    def get_characters_in_range(self, character: Character, range_feet: int) -> List[BaseAgent]:
        """
        Get the characters in range of a specific character.

        Args:
            character (Character): The character to get the range of.
            range_feet (int): The range in feet.

        Returns:
            List[BaseAgent]: The characters in range.
        """
        in_range = []
        for agent in self.party1 + self.party2:
            if agent.character != character:
                distance = self.get_distance_between(character, agent.character)
                if distance * self.map.scale <= range_feet:  # Convert grid distance to feet
                    in_range.append(agent)
        return in_range