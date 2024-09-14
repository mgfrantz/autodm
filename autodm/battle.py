from typing import List, Dict, Union, Tuple, Optional, Any
from .character import Character, CharacterState, Position
from .npc import NPC
from .player_agent import PlayerAgent
from .tools import roll_dice
from .llm import complete
from .spells import Spell
from .items import EquipmentItem
from .weapons import MeleeWeapon, RangedWeapon, WeaponDamageType
from .map_grid import Map
import random
from rich import print

CharacterUnion = Union[PlayerAgent, NPC]

class BattleAgent:
    def __init__(self):
        self.context = "You are a Dungeon Master narrating a battle. Describe the action and its immediate result vividly, focusing only on what has just occurred. Do not speculate about future actions or outcomes. Keep the narration concise, around 2-3 sentences. If a character has died, include this information in your narration."

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

class Battle:
    def __init__(self, party1: List[CharacterUnion], party2: List[CharacterUnion], map_size: Tuple[int, int] = (10, 10)):
        self.party1 = party1
        self.party2 = party2
        self.battle_agent = BattleAgent()
        self.initiative_order: List[CharacterUnion] = []
        self.current_turn: int = 0
        self.is_battle_over: bool = False
        self.map = Map(width=map_size[0], height=map_size[1])
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

    def get_initiative(self, agent: CharacterUnion) -> int:
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

    def is_character_alive(self, agent: CharacterUnion) -> bool:
        return agent.character.character_state == CharacterState.ALIVE

    def agent_turn(self, agent: CharacterUnion):
        agent.character.movement_remaining = agent.character.speed
        print(f"\n{agent.character.name}'s turn!")
        
        action_taken = False
        movement_taken = False

        while not (action_taken and movement_taken):
            prompt_str = f"You have the following options:\n{'- move' if not movement_taken else ''}\n{'- attack' if not action_taken else ''}\n{'- cast_spell' if not action_taken else ''}\n{'- use_item' if not action_taken else ''}\n{'- end_turn' if not action_taken else ''}\n"
            if agent.is_npc:
                action = agent.decide_action()
            else:
                action = agent.chat(input(prompt_str))
            print(f"{agent.character.name} : {action}")
            
            # For NPCs, end the turn if both movement and action are taken
            if agent.is_npc and (action_taken and movement_taken):
                break
            
            # For players, ask if they want to continue their turn
            if not agent.is_npc:
                if action_taken and movement_taken:
                    if not self.player_continue_turn():
                        break
                elif action_taken or movement_taken:
                    print(f"You have {'an action' if movement_taken else 'movement'} remaining.")
                    if not self.player_continue_turn():
                        break

        print(f"{agent.character.name}'s turn ends.")

    def handle_action(self, agent: CharacterUnion, action: Dict[str, Any]):
        if action['action_type'] == "attack":
            self.handle_attack(agent, action)
        elif action['action_type'] == "cast_spell":
            self.handle_spell(agent, action)
        elif action['action_type'] == "use_item":
            self.handle_item_use(agent, action)

    def player_continue_turn(self) -> bool:
        response = input("Do you want to continue your turn? (yes/no): ").lower().strip()
        return response == 'yes' or response == 'y'

    def handle_attack(self, agent: CharacterUnion, action: Dict[str, Any]):
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

    def handle_spell(self, agent: CharacterUnion, action: Dict[str, Any]):
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
                    
                    attacker_info = self.get_character_info(agent.character)
                    target_info = self.get_character_info(target.character)
                    
                    narration = self.battle_agent.narrate(
                        action=f"{agent.character.name} casts {spell_name} at {target_name}",
                        result=result,
                        attacker=agent.character.name,
                        target=target_name,
                        damage=0,  # We don't have access to the damage here, so we'll pass 0
                        target_hp=target.character.hp,
                        target_max_hp=target.character.max_hp,
                        death_info="",
                        attacker_info=attacker_info,
                        target_info=target_info
                    )
                    print(f"\nNarrator: {narration}")
                    
                    self.check_character_death(target)
                else:
                    print(f"{agent.character.name} tries to cast {spell_name} at {target_name}, but they are out of range.")
            else:
                print(f"{agent.character.name} tries to cast {spell_name}, but they don't know this spell.")
        else:
            print(f"{agent.character.name} tries to cast {spell.name} at {target.character.name}, but they are not a valid target.")

    def handle_item_use(self, agent: CharacterUnion, action: Dict[str, Any]):
        # Implement item use logic
        pass

    def get_target(self, target_name: str) -> Optional[CharacterUnion]:
        for agent in self.initiative_order:
            if isinstance(agent, 'CharacterAgent') and agent.character.name.lower() == target_name.lower():
                return agent
        return None

    def get_random_target(self, attacker: CharacterUnion) -> Optional[CharacterUnion]:
        opposing_party = self.party2 if attacker in self.party1 else self.party1
        living_targets = [agent for agent in opposing_party if self.is_character_alive(agent)]
        return random.choice(living_targets) if living_targets else None

    def calculate_weapon_damage(self, weapon: Optional[EquipmentItem], attacker: Character) -> int:
        if not weapon:
            return 1  # Unarmed strike damage
        
        damage_dice = weapon.effects['damage']
        damage_rolls = roll_dice(damage_dice)
        total_damage = sum(damage_rolls) + attacker.attributes.get_modifier('strength')
        
        return total_damage

    def calculate_spell_damage(self, spell: Spell, caster: Character) -> int:
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

    def print_target_hp(self, target: CharacterUnion):
        print(f"{target.character.name}'s HP: {target.character.hp}/{target.character.max_hp}")

    def check_battle_status(self):
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

    def check_character_death(self, agent: CharacterUnion) -> bool:
        if agent.character.hp <= 0:
            agent.character.character_state = CharacterState.DEAD
            print(f"{agent.character.name} has died!")
            return True
        return False

    def get_battle_state(self) -> Dict[str, List[Dict[str, Union[str, int, bool, Position]]]]:
        return {
            "party1": [self.get_character_info(agent.character) for agent in self.party1],
            "party2": [self.get_character_info(agent.character) for agent in self.party2]
        }

    def get_character_info(self, character: Character) -> Dict[str, Any]:
        equipped_weapons = character.get_equipped_weapons()
        weapon_name = equipped_weapons[0].name if equipped_weapons else "Unarmed"
        return {
            "name": character.name,
            "class": character.chr_class,
            "race": character.chr_race,
            "weapon": weapon_name,
            "armor": ", ".join([item.name for item in character.equipped_items.get('armor', []) if item]) or "No armor",
            "armor_class": character.armor_class,
            'hp': f"{character.hp}/{character.max_hp}",
            "position": character.position,
        }

    def initialize_positions(self):
        all_agents = self.party1 + self.party2
        available_positions = [(x, y) for x in range(self.map.width) for y in range(self.map.height)]
        random.shuffle(available_positions)

        for agent in all_agents:
            x, y = available_positions.pop()
            self.map.add_or_update_player(x, y, agent)

    def move_to(self, character: CharacterUnion, x: int, y: int, verbose=False) -> Tuple[bool, str]:
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
        map_str = str(self.map)
        print(map_str)
        if do_return:
            return map_str

    def get_distance_between(self, char1: Character, char2: Character) -> int:
        return self.map.distance_between_players(char1.name, char2.name)

    def get_character_position(self, character: CharacterUnion) -> Position:
        return self.map.locations[character.character.name]["position"]

    def get_characters_in_range(self, character: Character, range_feet: int) -> List[CharacterUnion]:
        in_range = []
        for agent in self.party1 + self.party2:
            if agent.character != character:
                distance = self.get_distance_between(character, agent.character)
                if distance * self.map.scale <= range_feet:  # Convert grid distance to feet
                    in_range.append(agent)
        return in_range

if __name__ == "__main__":
    from .character import Character, Attributes
    from .player_agent import PlayerAgent
    from .npc import NPC
    from .spells import Spell
    from .items import EquipmentItem
    from .weapons import MeleeWeapon, RangedWeapon, WeaponDamageType

    # Create characters
    print("Creating characters...")
    character1 = Character.generate(chr_class="Wizard", max_hp=100, current_hp=100)
    character2 = Character.generate(chr_class="Fighter", max_hp=100, current_hp=100)
    
    print("Equipping characters with items and spells...")
    # Create a spell
    fireball = Spell(name="Fireball", description="A magical explosion that deals fire damage to all creatures in a 15-foot radius.", level=1, range=60, components="V, S, M", duration="Instantaneous", casting_time=1, attack_type='ranged', school="Evocation", damage="1d6")
    fireball.learn(character1)
    
    # Create items
    longsword = MeleeWeapon(name='Longsword', damage_dice='1d8', damage_type=WeaponDamageType.SLASHING)
    character2.equip_item(longsword)
    bow = RangedWeapon(name='Bow', damage_dice='1d6', damage_type=WeaponDamageType.PIERCING, range_normal=100, range_long=400)
    character2.equip_item(bow)

    # Create player and NPC agents
    print("Creating player and NPC agents...")
    player = PlayerAgent(character1)
    npc = NPC(character2)

    # Create a battle
    print("Creating a battle...")
    battle = Battle([player], [npc])

    # Test movement
    print("Testing movement. Initializing player 1 to (0,0) and npc to (9,9)")
    battle.move_to(player, 0, 0, verbose=True)
    battle.move_to(npc, 9, 9, verbose=True)
    battle.display_map()
    print("Testing movement. Moving player 1 to (3,3) and npc to (6,6)")
    battle.move_to(player, 3, 3, verbose=True)
    battle.move_to(npc, 6, 6, verbose=True)
    battle.display_map()

    # Test spell casting
    print("Testing spell casting...")
    print(battle.get_battle_state())
    print("Player 1 casts Fireball at npc")
    print(player.cast_spell("Fireball", npc))
    print(battle.get_battle_state())

    # Test melee attack
    print("Testing melee attack...")
    print("Moving npc to (3,4)")
    battle.move_to(npc, 3, 4, verbose=True)
    print("Npc attacks player with Longsword")
    print(npc.attack(player, "Longsword"))
    print(battle.get_battle_state())

    # Test ranged attack
    print("Testing ranged attack...")
    print("Moving npc to (9,9)")
    battle.move_to(npc, 9, 9, verbose=True)
    print("Npc attacks player with Bow")
    print(npc.attack(player, "Bow"))
    print(battle.get_battle_state())
