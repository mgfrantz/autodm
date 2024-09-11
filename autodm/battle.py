from typing import List, Dict, Union, Tuple, Optional, Literal, TYPE_CHECKING, Any
from .character import Character, CharacterState, Position
from .npc import NPC
from .tools import roll_dice
from .llm import complete
from .spells import Spell
import random
from .skill_checks import perform_skill_check, perform_ability_check

if TYPE_CHECKING:
    from .player_agent import PlayerAgent
    CharacterUnion = Union[PlayerAgent, NPC]
else:
    from .types import PlayerAgent, CharacterUnion

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
    def __init__(self, players: List[Any], npcs: List[NPC], map_size: Tuple[int, int] = (10, 10)):
        self.players = players
        self.npcs = npcs
        self.battle_agent = BattleAgent()
        self.initiative_order: List[CharacterUnion] = []
        self.current_turn: int = 0
        self.is_battle_over: bool = False
        self.turn_ending_actions = {"attack", "cast", "use", "move", "dash", "disengage", "dodge", "help", "hide", "ready"}
        self.map_size = map_size
        self.map = [[' . ' for _ in range(map_size[0])] for _ in range(map_size[1])]
        self.character_symbols = {}
        self.initialize_character_symbols()
        self.initialize_positions()

    def start_battle(self):
        for player in self.players:
            player.set_battle(self)
        for npc in self.npcs:
            npc.set_battle(self)
        self.roll_initiative()
        self.run_battle()

    def roll_initiative(self):
        all_combatants = self.players + self.npcs
        initiative_rolls = [(roll_dice("1d20")[0] + self.get_initiative(c), c) for c in all_combatants]
        initiative_rolls.sort(reverse=True, key=lambda x: x[0])
        self.initiative_order = [agent for _, agent in initiative_rolls]

        print("Initiative order:")
        for i, agent in enumerate(self.initiative_order, 1):
            name = self.get_name(agent)
            print(f"{i}. {name}")

    def get_initiative(self, agent: CharacterUnion) -> int:
        if hasattr(agent, 'character'):  # PlayerAgent
            return agent.character.initiative
        else:  # NPC
            return agent.initiative

    def get_name(self, agent: CharacterUnion) -> str:
        if hasattr(agent, 'character'):  # PlayerAgent
            return agent.character.name
        else:  # NPC
            return agent.name

    def run_battle(self):
        while not self.is_battle_over:
            current_agent = self.initiative_order[self.current_turn]
            
            print("\n" + "="*40)  # Clear separator between turns
            
            if self.is_character_alive(current_agent):
                if hasattr(current_agent, 'character'):  # PlayerAgent
                    self.player_turn(current_agent)
                else:  # NPC's turn
                    self.npc_turn(current_agent)
            else:
                print(f"{self.get_name(current_agent)} is dead and cannot take any actions.")

            self.current_turn = (self.current_turn + 1) % len(self.initiative_order)
            self.check_battle_status()

    def is_character_alive(self, agent: CharacterUnion) -> bool:
        if hasattr(agent, 'character'):  # PlayerAgent
            return agent.character.character_state == CharacterState.ALIVE
        else:  # NPC
            return agent.character_state == CharacterState.ALIVE

    def player_turn(self, player: Any):
        player.character.movement_remaining = player.character.speed
        print(f"\n{player.character.name}'s turn!")
        
        action_taken = False
        movement_taken = False

        while not (action_taken and movement_taken):
            if not action_taken and not movement_taken:
                action = input(f"{player.character.name}, what would you like to do? (move/attack/cast/use/end turn) ").strip().lower()
            elif action_taken:
                action = input(f"{player.character.name}, would you like to move? (yes/no) ").strip().lower()
                if action == "no":
                    break
                action = "move"
            elif movement_taken:
                action = input(f"{player.character.name}, would you like to attack, cast a spell, or use an item? (attack/cast/use/end turn) ").strip().lower()

            if action == "help":
                print("Available actions: move [direction] [distance], move to [X] [Y], attack [target], cast [spell] [target], use [item] [target], end turn")
                print("You can also check your status, inventory, or spells without ending your turn.")
                continue

            if action == "end turn":
                break

            if action.startswith("move to"):
                if not movement_taken:
                    parts = action.split()
                    if len(parts) == 4:
                        _, _, x, y = parts
                        response = player.move_to(int(x), int(y))
                        print(response)
                        if "moves to" in response:
                            movement_taken = True
                    else:
                        print("Invalid move command. Use 'move to [X] [Y]'.")
                else:
                    print("You've already moved this turn.")
            elif action.startswith("move"):
                if not movement_taken:
                    parts = action.split()
                    if len(parts) == 3:
                        direction, distance = parts[1], int(parts[2])
                        print(player.move(direction, distance))
                        movement_taken = True
                    else:
                        print("Invalid move command. Use 'move [direction] [distance]'.")
                else:
                    print("You've already moved this turn.")
            elif any(action.startswith(keyword) for keyword in ["attack", "cast", "use"]):
                if not action_taken:
                    response = player.interpret_action(action)
                    print(response)
                    action_taken = True
                else:
                    print("You've already taken an action this turn.")
            else:
                response = player.interpret_action(action)
                print(response)

        print(f"{player.character.name}'s turn ends.")

    def parse_action(self, action: str) -> Tuple[str, Optional[str]]:
        words = action.lower().split()
        if "attack" in words:
            return "attack", words[-1] if len(words) > 1 else None
        elif "cast" in words:
            return "cast", words[-1] if len(words) > 2 else None
        elif "use" in words:
            return "use", words[-1] if len(words) > 2 else None
        else:
            return words[0], None

    def npc_turn(self, npc: NPC):
        npc.movement_remaining = npc.speed
        print(f"\n{npc.name}'s turn!")
        
        # Movement
        move_action = npc.decide_movement()
        if move_action:
            direction = move_action['direction']
            distance = move_action['distance']
            success, moved_distance = self.move_character(npc, direction, distance)
            if success:
                print(f"{npc.name} moves {direction} {moved_distance} feet.")
            else:
                print(f"{npc.name} couldn't move {direction} {distance} feet.")

        # Action
        action = npc.decide_action()
        print(f"{npc.name} decides to: {action['description']}")
        
        if action['action_type'] == "attack":
            target = self.get_target(action['target'])
            if target and self.is_character_alive(target):
                weapon = npc.get_equipped_weapon()
                target_name = self.get_name(target)
                
                # Check if the target is in range
                distance = self.get_distance_between(npc, target)
                weapon_range = 5  # Default melee range
                if weapon and 'range' in weapon.effects:
                    weapon_range = weapon.effects['range']
                
                if distance * 5 <= weapon_range:  # Convert grid distance to feet
                    response = f"{npc.name} attacks {target_name} with {weapon.name if weapon else 'an unarmed strike'}."
                    success, damage = self.apply_action_effects(response, npc, target)
                    self.print_action_result(response, success, damage, target_name)
                    self.print_target_hp(target)
                    
                    # Check for character death before narration
                    target_died = self.check_character_death(target)
                    
                    target_hp = target.hp if isinstance(target, NPC) else target.character.hp
                    target_max_hp = target.max_hp if isinstance(target, NPC) else target.character.max_hp
                    result = "Success" if success else "Failure"
                    death_info = f"{target_name} has died!" if target_died else ""
                    
                    attacker_info = self.get_character_info(npc)
                    target_info = self.get_character_info(target.character if hasattr(target, 'character') else target)
                    
                    narration = self.battle_agent.narrate(
                        action=response,
                        result=result,
                        attacker=npc.name,
                        target=target_name,
                        damage=damage,
                        target_hp=target_hp,
                        target_max_hp=target_max_hp,
                        death_info=death_info,
                        attacker_info=attacker_info,
                        target_info=target_info
                    )
                    print(f"\nNarrator: {narration}")
                else:
                    print(f"{npc.name} tries to attack {target_name}, but they are out of range.")
            else:
                print(f"{npc.name} tries to attack {action['target']}, but they are not a valid target.")
        elif action['action_type'] == "cast_spell":
            target = self.get_target(action['target'])
            if target and self.is_character_alive(target):
                spell_name = action['spell_name']
                spell = next((s for s in npc.spells if s.name.lower() == spell_name.lower()), None)
                if spell:
                    target_name = self.get_name(target)
                    
                    # Check if the target is in range
                    distance = self.get_distance_between(npc, target)
                    spell_range = int(spell.range.split()[0])  # Assume range is in format "120 feet"
                    
                    if distance * 5 <= spell_range:  # Convert grid distance to feet
                        response = f"{npc.name} casts {spell_name} at {target_name}."
                        success, damage = self.apply_action_effects(response, npc, target)
                        self.print_action_result(response, success, damage, target_name)
                        self.print_target_hp(target)
                        
                        target_hp = target.hp if isinstance(target, NPC) else target.character.hp
                        target_max_hp = target.max_hp if isinstance(target, NPC) else target.character.max_hp
                        result = "Success" if success else "Failure"
                        
                        attacker_info = self.get_character_info(npc)
                        target_info = self.get_character_info(target.character if hasattr(target, 'character') else target)
                        
                        narration = self.battle_agent.narrate(
                            action=response,
                            result=result,
                            attacker=npc.name,
                            target=target_name,
                            damage=damage,
                            target_hp=target_hp,
                            target_max_hp=target_max_hp,
                            death_info="",
                            attacker_info=attacker_info,
                            target_info=target_info
                        )
                        print(f"\nNarrator: {narration}")
                        
                        self.check_character_death(target)
                    else:
                        print(f"{npc.name} tries to cast {spell_name} at {target_name}, but they are out of range.")
                else:
                    print(f"{npc.name} tries to cast {spell_name}, but they don't know this spell.")
            else:
                print(f"{npc.name} tries to cast {action['spell_name']} at {action['target']}, but they are not a valid target.")
        elif action['action_type'] == "skill_check":
            skill = action['skill']
            difficulty_class = 15  # You might want to adjust this based on the situation
            success, total = perform_skill_check(npc, skill, difficulty_class)
            result = "Success" if success else "Failure"
            print(f"{npc.name} performs a {skill} check (DC {difficulty_class}): {result} (rolled {total})")
            
            narration = self.battle_agent.narrate(
                action=f"{npc.name} attempts a {skill} check",
                result=result,
                attacker=npc.name,
                target="N/A",
                damage=0,
                target_hp=npc.hp,
                target_max_hp=npc.max_hp,
                death_info="",
                attacker_info=self.get_character_info(npc),
                target_info={"class": "N/A", "race": "N/A", "weapon": "N/A", "armor": "N/A"}
            )
            print(f"\nNarrator: {narration}")
        else:
            print(f"{npc.name} performs the action: {action['description']}")
        
        print(f"{npc.name}'s turn ends.")

    def get_target(self, target_name: str) -> Union[Any, NPC, None]:
        for agent in self.initiative_order:
            if isinstance(agent, NPC):
                if agent.name.lower() == target_name.lower():
                    return agent
            else:  # PlayerAgent
                if agent.character.name.lower() == target_name.lower():
                    return agent
        return None

    def get_living_targets(self, attacker: CharacterUnion) -> List[CharacterUnion]:
        if isinstance(attacker, NPC):
            return [player for player in self.players if self.is_character_alive(player)]
        else:
            return [npc for npc in self.npcs if self.is_character_alive(npc)]

    def get_random_target(self, attacker: CharacterUnion) -> Union[CharacterUnion, None]:
        living_targets = self.get_living_targets(attacker)
        return random.choice(living_targets) if living_targets else None

    def get_random_enemy(self, attacker: CharacterUnion) -> Union[CharacterUnion, None]:
        if isinstance(attacker, NPC):
            living_targets = [player for player in self.players if self.is_character_alive(player)]
        else:
            living_targets = [npc for npc in self.npcs if self.is_character_alive(npc)]
        return random.choice(living_targets) if living_targets else None

    def apply_action_effects(self, action: str, attacker: Union[Character, NPC], defender: CharacterUnion) -> Tuple[bool, int]:
        attacker_char = attacker if isinstance(attacker, Character) else attacker
        defender_char = defender.character if hasattr(defender, 'character') else defender

        if "attacks" in action.lower():
            return self.resolve_weapon_attack(attacker_char, defender_char)
        elif "casts" in action.lower():
            spell_name = action.split("casts")[1].split()[0].lower()
            spell = next((s for s in attacker_char.spells if s.name.lower() == spell_name), None)
            if spell:
                if spell.attack_type == "heal":
                    return self.resolve_healing_spell(attacker_char, defender_char, spell)
                elif spell.attack_type in ["ranged", "save"]:
                    return self.resolve_spell_attack(attacker_char, defender_char, spell)
                elif spell.attack_type == "none":
                    return True, 0  # The spell was cast successfully but doesn't deal damage or heal
            return False, 0
        else:
            # Other effects (implement as needed)
            return False, 0

    def resolve_weapon_attack(self, attacker: Character, defender: Character) -> Tuple[bool, int]:
        attack_roll = roll_dice("1d20")[0]
        attack_bonus = attacker.attributes.get_modifier('strength') + attacker.proficiency_bonus
        total_attack = attack_roll + attack_bonus

        if attack_roll >= 20 or (attack_roll != 1 and total_attack >= defender.armor_class):
            # Critical hit on 20, otherwise hit if meets or exceeds AC
            weapon = attacker.get_equipped_weapons()[0] if attacker.get_equipped_weapons() else None
            damage_dice = weapon.effects['damage'] if weapon else "1d4"  # Unarmed strike damage
            damage_roll = roll_dice(damage_dice)
            damage = sum(damage_roll) + attacker.attributes.get_modifier('strength')
            if attack_roll == 20:
                damage *= 2  # Double damage on critical hit

            defender.hp -= damage
            return True, damage
        else:
            return False, 0

    def resolve_spell_attack(self, attacker: Character, defender: Character, spell: Spell) -> Tuple[bool, int]:
        if spell.attack_type == "ranged":
            attack_roll = roll_dice("1d20")[0]
            attack_bonus = attacker.attributes.get_modifier('intelligence') + attacker.proficiency_bonus
            total_attack = attack_roll + attack_bonus

            if attack_roll == 20 or (attack_roll != 1 and total_attack >= defender.armor_class):
                damage = self.calculate_spell_damage(spell, attacker)
                if attack_roll == 20:
                    damage *= 2  # Double damage on critical hit

                defender.hp -= damage
                return True, damage
            else:
                return False, 0
        elif spell.attack_type == "save":
            save_dc = 8 + attacker.attributes.get_modifier('intelligence') + attacker.proficiency_bonus
            save_attribute = spell.save_attribute or "dexterity"  # Default to dexterity if not specified
            save_roll = roll_dice("1d20")[0] + defender.attributes.get_modifier(save_attribute)

            damage = self.calculate_spell_damage(spell, attacker)
            
            if save_roll < save_dc:
                defender.hp -= damage
                return False, damage  # The target failed the save
            else:
                half_damage = damage // 2
                defender.hp -= half_damage
                return True, half_damage  # The target succeeded the save, but still takes half damage

        return False, 0  # Default case if the attack type is not handled

    def calculate_spell_damage(self, spell: Spell, caster: Character) -> int:
        if not spell.damage:
            return 0
        
        base_damage_dice = spell.damage
        spell_level = spell.level
        caster_level = caster.level

        # Scale damage based on spell level and caster level
        if spell.name.lower() == "fireball":
            damage_dice = f"{max(1, min(caster_level, 10))}d6"  # Scales up to 10d6 at level 10
        else:
            damage_dice = base_damage_dice

        damage_rolls = roll_dice(damage_dice)
        total_damage = sum(damage_rolls)
        
        # Add spellcasting ability modifier for cantrips (level 0 spells)
        if spell.level == 0:
            total_damage += caster.attributes.get_modifier('intelligence')
        
        return total_damage

    def resolve_healing_spell(self, caster: Character, target: Character, spell: Spell) -> Tuple[bool, int]:
        if spell.damage:
            healing = self.calculate_spell_damage(spell, caster)
            target.hp = min(target.hp + healing, target.max_hp)
            return True, healing
        return False, 0

    def print_target_hp(self, target: CharacterUnion):
        if hasattr(target, 'character'):  # PlayerAgent
            print(f"{target.character.name}'s HP: {target.character.hp}/{target.character.max_hp}")
        else:  # NPC
            print(f"{target.name}'s HP: {target.hp}/{target.max_hp}")

    def check_battle_status(self):
        players_alive = any(self.is_character_alive(p) for p in self.players)
        npcs_alive = any(self.is_character_alive(npc) for npc in self.npcs)

        if not players_alive or not npcs_alive:
            self.is_battle_over = True
            if players_alive:
                print("\nThe battle is over! The players are victorious!")
            elif npcs_alive:
                print("\nThe battle is over! The NPCs are victorious!")
            else:
                print("\nThe battle is over! It's a draw!")

    def print_action_result(self, action: str, success: bool, amount: int, target_name: str):
        if "attacks" in action.lower():
            weapon = action.split("with")[-1].strip() if "with" in action else "weapon"
            if success:
                print(f"Attack Result: The attack with {weapon} hits {target_name}!")
                print(f"Damage: {target_name} takes {amount} damage.")
            else:
                print(f"Attack Result: The attack with {weapon} misses {target_name}.")
        elif "casts" in action.lower():
            spell_name = action.split("casts")[1].split()[0]
            spell = next((s for s in self.get_current_character().spells if s.name.lower() == spell_name.lower()), None)
            if spell:
                if spell.attack_type == "heal":
                    print(f"Spell Result: The {spell_name} spell successfully heals {target_name} for {amount} hit points!")
                elif spell.attack_type == "none":
                    print(f"Spell Result: The {spell_name} spell is cast successfully.")
                elif spell.attack_type == "save":
                    if success:
                        print(f"Spell Result: {target_name} successfully saves against the {spell_name} spell.")
                        print(f"Damage: Despite the save, {target_name} still takes {amount} damage (half damage).")
                    else:
                        print(f"Spell Result: {target_name} fails to save against the {spell_name} spell.")
                        print(f"Damage: {target_name} takes full damage of {amount} points.")
                elif spell.attack_type == "ranged":
                    if success:
                        print(f"Spell Result: The {spell_name} spell hits {target_name}!")
                        print(f"Damage: {target_name} takes {amount} damage.")
                    else:
                        print(f"Spell Result: The {spell_name} spell misses {target_name}.")
            else:
                print(f"Spell Result: Unknown spell {spell_name}.")
        else:
            print(f"Action Result: {action}")

        if amount > 0:
            print(f"Total Damage/Healing: {amount}")

    def get_current_character(self) -> Union[Character, NPC]:
        current_agent = self.initiative_order[self.current_turn]
        return current_agent.character if hasattr(current_agent, 'character') else current_agent

    def check_character_death(self, character: CharacterUnion) -> bool:
        if hasattr(character, 'character'):  # PlayerAgent
            if character.character.hp <= 0:
                character.character.character_state = CharacterState.DEAD
                print(f"{character.character.name} has died!")
                return True
        else:  # NPC
            if character.hp <= 0:
                character.character_state = CharacterState.DEAD
                print(f"{character.name} has died!")
                return True
        return False

    def get_battle_state(self) -> Dict[str, List[Dict[str, Union[str, int, bool, Position]]]]:
        def character_state(char: CharacterUnion) -> Dict[str, Union[str, int, bool, Position]]:
            if hasattr(char, 'character'):  # PlayerAgent
                c = char.character
                return {
                    "name": c.name,
                    "class": c.chr_class,
                    "level": c.level,
                    "hp": c.hp,
                    "max_hp": c.max_hp,
                    "is_alive": self.is_character_alive(char),
                    "position": c.position
                }
            else:  # NPC
                return {
                    "name": char.name,
                    "class": char.chr_class,
                    "level": char.level,
                    "hp": char.hp,
                    "max_hp": char.max_hp,
                    "is_alive": self.is_character_alive(char),
                    "position": char.position
                }

        return {
            "allies": [character_state(player) for player in self.players],
            "enemies": [character_state(npc) for npc in self.npcs]
        }

    def get_character_info(self, character: Union[Character, NPC]) -> Dict[str, Any]:
        equipped_weapons = character.get_equipped_weapons()
        weapon_name = equipped_weapons[0].name if equipped_weapons else "Unarmed"
        return {
            "class": character.chr_class,
            "race": character.chr_race,
            "weapon": weapon_name,
            "armor": ", ".join([item.name for item in character.equipped_items.get('armor', []) if item]) or "No armor"
        }

    def initialize_positions(self):
        available_positions = [(x, y) for x in range(self.map_size[0]) for y in range(self.map_size[1])]
        random.shuffle(available_positions)
        
        for character in self.players + self.npcs:
            x, y = available_positions.pop()
            character.position = Position(x=x, y=y)
            self.update_map_position(character)

    def update_map_position(self, character: Union[Character, NPC]):
        x, y = character.position.x, character.position.y
        symbol = self.character_symbols[self.get_name(character)]
        self.map[y][x] = f' {symbol} '

    def display_map(self):
        print("\nBattle Map:")
        
        # Create column labels using letters
        col_labels = '    ' + ' '.join([f'{chr(65+i):2}' for i in range(self.map_size[0])])
        print(col_labels)
        
        # Print rows with row numbers
        for i, row in enumerate(self.map):
            print(f'{i+1:2} |' + ''.join(row))
        
        print("\nLegend:")
        for name, symbol in self.character_symbols.items():
            character = next((c for c in self.players + self.npcs if self.get_name(c) == name), None)
            if character:
                if hasattr(character, 'character'):  # PlayerAgent
                    char_type = "Player"
                    char_class = character.character.chr_class
                else:  # NPC
                    char_type = "NPC"
                    char_class = character.chr_class
                print(f"{symbol}: {name} ({char_type} - {char_class})")
        print()

    def initialize_character_symbols(self):
        symbols = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        all_characters = self.players + self.npcs
        for i, character in enumerate(all_characters):
            symbol = symbols[i % len(symbols)]
            self.character_symbols[self.get_name(character)] = symbol

    def move_character(self, character: Union[Character, NPC], direction: str, distance: int) -> Tuple[bool, int]:
        dx, dy = self.get_direction_vector(direction)
        cells_to_move = distance // 5  # Convert feet to grid cells

        new_x = character.position.x + (dx * cells_to_move)
        new_y = character.position.y + (dy * cells_to_move)

        if 0 <= new_x < self.map_size[0] and 0 <= new_y < self.map_size[1]:
            if character.movement_remaining >= distance:
                # Clear the old position
                self.map[character.position.y][character.position.x] = ' . '
                
                # Update the character's position
                character.position = Position(x=new_x, y=new_y)
                
                # Update the new position on the map
                self.update_map_position(character)
                
                character.movement_remaining -= distance
                return True, distance
            else:
                return False, 0
        return False, 0

    def get_direction_vector(self, direction: str) -> Tuple[int, int]:
        direction = direction.lower()
        direction_vectors = {
            "north": (0, -1),
            "northeast": (1, -1),
            "east": (1, 0),
            "southeast": (1, 1),
            "south": (0, 1),
            "southwest": (-1, 1),
            "west": (-1, 0),
            "northwest": (-1, -1)
        }
        return direction_vectors.get(direction, (0, 0))

    def get_character_position(self, character: Union[Character, NPC]) -> str:
        return f"{self.get_name(character)} is at position ({character.position.x}, {character.position.y})"

    def get_distance_between(self, char1: Union[Character, NPC], char2: Union[Character, NPC]) -> int:
        return abs(char1.position.x - char2.position.x) + abs(char1.position.y - char2.position.y)

    def get_direction_to(self, from_char: Union[Character, NPC], to_char: Union[Character, NPC]) -> str:
        dx = to_char.position.x - from_char.position.x
        dy = to_char.position.y - from_char.position.y
        
        if abs(dx) > abs(dy):
            return "east" if dx > 0 else "west"
        else:
            return "south" if dy > 0 else "north"

    def get_characters_in_range(self, attacker: Union[Character, NPC], range_feet: int) -> List[Union[Character, NPC]]:
        attacker_pos = attacker.position
        in_range = []
        for character in self.players + self.npcs:
            if character == attacker:
                continue
            target_pos = character.position if isinstance(character, NPC) else character.character.position
            distance = abs(attacker_pos.x - target_pos.x) + abs(attacker_pos.y - target_pos.y)
            if distance * 5 <= range_feet:  # Convert grid distance to feet
                in_range.append(character)
        return in_range

    def move_to(self, character: Union[Character, NPC], coord: str) -> Tuple[bool, str]:
        col, row = coord[0].upper(), int(coord[1:])
        x, y = ord(col) - 65, row - 1  # Convert to 0-based index

        if 0 <= x < self.map_size[0] and 0 <= y < self.map_size[1]:
            current_x, current_y = character.position.x, character.position.y
            distance = (abs(current_x - x) + abs(current_y - y)) * 5  # Each cell is 5 feet
            if distance <= character.movement_remaining:
                # Clear the old position
                self.map[current_y][current_x] = ' . '
                
                # Update the character's position
                character.position = Position(x=x, y=y)
                
                # Update the new position on the map
                self.update_map_position(character)
                
                character.movement_remaining -= distance
                return True, f"{self.get_name(character)} moves to {coord}. Movement remaining: {character.movement_remaining} feet."
            else:
                return False, f"Not enough movement. Required: {distance} feet, Remaining: {character.movement_remaining} feet."
        return False, f"Invalid coordinates {coord}. Map size is {chr(65+self.map_size[0]-1)}x{self.map_size[1]}."

# Test scenario
if __name__ == "__main__":
    from .character import Character
    
    player1 = PlayerAgent(Character.generate("Hero1"))
    player2 = PlayerAgent(Character.generate("Hero2"))
    
    npc1 = NPC.generate("Goblin1", "Warrior", "Goblin")
    npc2 = NPC.generate("Goblin2", "Archer", "Goblin")
    
    battle = Battle([player1, player2], [npc1, npc2])
    battle.start_battle()