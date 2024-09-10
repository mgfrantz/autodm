from typing import List, Dict, Union, Tuple, Literal, TYPE_CHECKING, Any
from .character import Character, CharacterState
from .npc import NPC
from .tools import roll_dice
from .llm import complete
from .spells import Spell
import random

if TYPE_CHECKING:
    from .player_agent import PlayerAgent
    CharacterUnion = Union[PlayerAgent, NPC]
else:
    CharacterUnion = Union[Any, NPC]

class BattleAgent:
    def __init__(self):
        self.context = "You are a Dungeon Master narrating a battle. Describe the actions and their results vividly, taking into account whether the action succeeded or failed and how much damage was dealt."

    def narrate(self, action: str) -> str:
        prompt = f"{self.context}\n\nAction and Result: {action}\nNarration:"
        return complete(prompt)

    def check_rules(self, action: str, character: Character) -> bool:
        # Implement rule checking logic here
        return True

class Battle:
    def __init__(self, players: List[Any], npcs: List[NPC]):
        self.players = players
        self.npcs = npcs
        self.battle_agent = BattleAgent()
        self.initiative_order: List[CharacterUnion] = []
        self.current_turn: int = 0
        self.is_battle_over: bool = False
        self.turn_ending_actions = {"attack", "cast", "use", "move", "dash", "disengage", "dodge", "help", "hide", "ready"}

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
        print(f"\n{player.character.name}'s turn!")
        while True:
            action = input(f"{player.character.name}, what would you like to do? ").strip()
            if action.lower() == 'help':
                print("Available actions: attack [target], cast [spell] [target], use [item], move [direction], end turn")
                print("You can also check your status, inventory, or spells without ending your turn.")
                continue

            response = player.interpret_action(action)
            
            # Check if the action ends the turn
            if any(keyword in action.lower() for keyword in self.turn_ending_actions):
                target = self.get_target(action)
                if target and self.is_character_alive(target):
                    success, damage = self.apply_action_effects(response, player.character, target)
                    target_name = self.get_name(target)
                    self.print_action_result(action, success, damage, target_name)
                    self.print_target_hp(target)
                    
                    # Generate narration after knowing the result
                    target_hp = target.hp if isinstance(target, NPC) else target.character.hp
                    target_max_hp = target.max_hp if isinstance(target, NPC) else target.character.max_hp
                    narration = self.battle_agent.narrate(f"{response} - {'Success' if success else 'Failure'}, Damage: {damage}, Target HP: {target_hp}/{target_max_hp}")
                    print(f"\nNarrator: {narration}")
                    
                    self.check_character_death(target)
                else:
                    print(f"Invalid target or target is already dead.")
                print(f"{player.character.name}'s turn ends.")
                return  # End the turn immediately after a turn-ending action
            elif "end turn" in action.lower():
                print(f"{player.character.name}'s turn ends.")
                return  # End the turn if the player explicitly ends it
            else:
                # For non-turn-ending actions, just print the response without narration
                print(response)

    def npc_turn(self, npc: NPC):
        print(f"\n{npc.name}'s turn!")
        
        action = npc.decide_action()
        print(f"{npc.name} decides to: {action}")
        
        # Parse the action and execute it
        if "attack" in action.lower():
            target = self.get_random_target(npc)
            if target:
                response = f"{npc.name} attacks {self.get_name(target)}."
                success, damage = self.apply_action_effects(response, npc, target)
                target_name = self.get_name(target)
                self.print_action_result(response, success, damage, target_name)
                self.print_target_hp(target)
                
                narration = self.battle_agent.narrate(f"{response} - {'Success' if success else 'Failure'}, Damage: {damage}")
                print(f"\nNarrator: {narration}")
                
                self.check_character_death(target)
            else:
                print(f"{npc.name} has no valid targets and skips their turn.")
        else:
            # Handle other types of actions (spells, items, etc.)
            print(f"{npc.name} performs the action: {action}")
        
        print(f"{npc.name}'s turn ends.")

    def get_target(self, action: str) -> Union[Any, NPC, None]:
        words = action.lower().split()
        if "attack" in words or "cast" in words:
            target_name = words[-1]
            for agent in self.initiative_order:
                if self.get_name(agent).lower() == target_name.lower():
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
        
        damage_rolls = roll_dice(spell.damage)
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

    def check_character_death(self, character: CharacterUnion):
        if hasattr(character, 'character'):  # PlayerAgent
            if character.character.hp <= 0:
                character.character.character_state = CharacterState.DEAD
                print(f"{character.character.name} has died!")
        else:  # NPC
            if character.hp <= 0:
                character.character_state = CharacterState.DEAD
                print(f"{character.name} has died!")

    def get_battle_state(self) -> Dict[str, List[Dict[str, Union[str, int, bool]]]]:
        """
        Get the current state of the battle.
        
        Returns:
        Dict with keys 'allies' and 'enemies', each containing a list of character states.
        """
        def character_state(char: CharacterUnion) -> Dict[str, Union[str, int, bool]]:
            if hasattr(char, 'character'):  # PlayerAgent
                c = char.character
                return {
                    "name": c.name,
                    "class": c.chr_class,
                    "level": c.level,
                    "hp": c.hp,
                    "max_hp": c.max_hp,
                    "is_alive": self.is_character_alive(char)
                }
            else:
                return {
                    "name": char.name,
                    "class": char.chr_class,
                    "level": char.level,
                    "hp": char.hp,
                    "max_hp": char.max_hp,
                    "is_alive": self.is_character_alive(char)
                }

        return {
            "allies": [character_state(player) for player in self.players],
            "enemies": [character_state(npc) for npc in self.npcs]
        }

# Test scenario
if __name__ == "__main__":
    from .character import Character
    
    player1 = PlayerAgent(Character.generate("Hero1"))
    player2 = PlayerAgent(Character.generate("Hero2"))
    
    npc1 = NPC.generate("Goblin1", "Warrior", "Goblin")
    npc2 = NPC.generate("Goblin2", "Archer", "Goblin")
    
    battle = Battle([player1, player2], [npc1, npc2])
    battle.start_battle()