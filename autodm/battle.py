from typing import List, Dict, Union, Tuple
from .character import Character
from .player_agent import PlayerAgent
from .npc import NPC
from .tools import roll_dice
from .llm import complete
import random

class BattleAgent:
    def __init__(self):
        self.context = "You are a Dungeon Master narrating a battle. Describe the actions and their results vividly."

    def narrate(self, action: str) -> str:
        prompt = f"{self.context}\n\nAction: {action}\nNarration:"
        return complete(prompt)

    def check_rules(self, action: str, character: Character) -> bool:
        # Implement rule checking logic here
        return True

class Battle:
    def __init__(self, players: List[PlayerAgent], npcs: List[NPC]):
        self.players = players
        self.npcs = npcs
        self.battle_agent = BattleAgent()
        self.initiative_order: List[Union[PlayerAgent, NPC]] = []
        self.current_turn: int = 0
        self.is_battle_over: bool = False
        self.turn_ending_actions = {"attack", "cast", "use", "move", "dash", "disengage", "dodge", "help", "hide", "ready"}

    def start_battle(self):
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

    def get_initiative(self, agent: Union[PlayerAgent, NPC]) -> int:
        if isinstance(agent, PlayerAgent):
            return agent.character.initiative
        else:  # NPC
            return agent.initiative

    def get_name(self, agent: Union[PlayerAgent, NPC]) -> str:
        if isinstance(agent, PlayerAgent):
            return agent.character.name
        else:  # NPC
            return agent.name

    def run_battle(self):
        while not self.is_battle_over:
            current_agent = self.initiative_order[self.current_turn]
            
            print("\n" + "="*40)  # Clear separator between turns
            
            if isinstance(current_agent, PlayerAgent):
                self.player_turn(current_agent)
            else:  # NPC's turn
                self.npc_turn(current_agent)

            self.current_turn = (self.current_turn + 1) % len(self.initiative_order)
            self.check_battle_status()

    def player_turn(self, player: PlayerAgent):
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
                narration = self.battle_agent.narrate(response)
                print(f"\nNarrator: {narration}")
                target = self.get_target(action)
                if target:
                    success, damage = self.apply_action_effects(response, player.character, target)
                    if success:
                        print(f"The attack was successful! {self.get_name(target)} takes {damage} damage.")
                    else:
                        if damage > 0:
                            print(f"{self.get_name(target)} saved against the effect but still takes {damage} damage.")
                        else:
                            print(f"The attack missed {self.get_name(target)}.")
                    self.print_target_hp(target)
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
        action = self.npc_decide_action(npc)
        response = npc.converse(action)
        narration = self.battle_agent.narrate(response)
        print(f"\nNarrator: {narration}")
        target = self.get_random_target(npc)
        if target:
            success, damage = self.apply_action_effects(response, npc, target)
            if success:
                print(f"The attack was successful! {self.get_name(target)} takes {damage} damage.")
            else:
                if damage > 0:
                    print(f"{self.get_name(target)} saved against the effect but still takes {damage} damage.")
                else:
                    print(f"The attack missed {self.get_name(target)}.")
            self.print_target_hp(target)
        print(f"{npc.name}'s turn ends.")

    def npc_decide_action(self, npc: NPC) -> str:
        # Simple AI: randomly choose between attacking and using an ability
        if random.random() < 0.7:  # 70% chance to attack
            target = self.get_random_target(npc)
            return f"attack {self.get_name(target) if target else 'a random enemy'}"
        else:
            return "use a special ability"

    def get_target(self, action: str) -> Union[PlayerAgent, NPC, None]:
        words = action.lower().split()
        if "attack" in words or "cast" in words:
            target_name = words[-1]
            for agent in self.initiative_order:
                if self.get_name(agent).lower() == target_name.lower():
                    return agent
        return None

    def get_random_target(self, attacker: Union[PlayerAgent, NPC]) -> Union[PlayerAgent, NPC, None]:
        possible_targets = self.players if isinstance(attacker, NPC) else self.npcs
        return random.choice(possible_targets) if possible_targets else None

    def apply_action_effects(self, action: str, attacker: Union[Character, NPC], defender: Union[PlayerAgent, NPC]) -> Tuple[bool, int]:
        attacker_char = attacker if isinstance(attacker, Character) else attacker
        defender_char = defender.character if isinstance(defender, PlayerAgent) else defender

        if "attacks" in action.lower():
            return self.resolve_weapon_attack(attacker_char, defender_char)
        elif "casts" in action.lower():
            spell_name = action.split("casts")[1].split()[0].lower()
            return self.resolve_spell_attack(attacker_char, defender_char, spell_name)
        else:
            # Other effects (implement as needed)
            return False, 0

    def resolve_weapon_attack(self, attacker: Character, defender: Character) -> Tuple[bool, int]:
        attack_roll = roll_dice("1d20")[0]
        attack_bonus = attacker.attributes.get_modifier('strength') + attacker.proficiency_bonus
        total_attack = attack_roll + attack_bonus

        if attack_roll == 20 or (attack_roll != 1 and total_attack >= defender.armor_class):
            # Critical hit on 20, otherwise hit if meets or exceeds AC
            weapon = attacker.get_equipped_weapons()[0] if attacker.get_equipped_weapons() else None
            damage_dice = weapon.effects['damage'] if weapon else "1d4"  # Unarmed strike damage
            damage = sum(roll_dice(damage_dice)) + attacker.attributes.get_modifier('strength')
            if attack_roll == 20:
                damage *= 2  # Double damage on critical hit

            defender.hp -= damage
            return True, damage
        else:
            return False, 0

    def resolve_spell_attack(self, attacker: Character, defender: Character, spell_name: str) -> Tuple[bool, int]:
        spell = next((s for s in attacker.spells if s.name.lower() == spell_name.lower()), None)
        if not spell:
            return False, 0

        if spell.attack_type == "ranged":
            attack_roll = roll_dice("1d20")[0]
            attack_bonus = attacker.attributes.get_modifier('intelligence') + attacker.proficiency_bonus
            total_attack = attack_roll + attack_bonus

            if attack_roll == 20 or (attack_roll != 1 and total_attack >= defender.armor_class):
                damage_roll = roll_dice(spell.damage)
                damage = sum(damage_roll) if isinstance(damage_roll, list) else damage_roll
                if attack_roll == 20:
                    damage *= 2  # Double damage on critical hit

                defender.hp -= damage
                return True, damage
            else:
                return False, 0
        elif spell.attack_type == "save":
            save_dc = 8 + attacker.attributes.get_modifier('intelligence') + attacker.proficiency_bonus
            save_roll = roll_dice("1d20")[0] + defender.attributes.get_modifier(spell.save_attribute)

            damage_roll = roll_dice(spell.damage)
            damage = sum(damage_roll) if isinstance(damage_roll, list) else damage_roll
            if save_roll < save_dc:
                defender.hp -= damage
                return True, damage
            else:
                half_damage = damage // 2
                defender.hp -= half_damage
                return False, half_damage  # Successful save, but still takes half damage

    def print_target_hp(self, target: Union[PlayerAgent, NPC]):
        if isinstance(target, PlayerAgent):
            print(f"{target.character.name}'s HP: {target.character.hp}/{target.character.max_hp}")
        else:
            print(f"{target.name}'s HP: {target.hp}/{target.max_hp}")

    def check_battle_status(self):
        players_alive = any(p.character.hp > 0 for p in self.players)
        npcs_alive = any(npc.hp > 0 for npc in self.npcs)

        if not players_alive or not npcs_alive:
            self.is_battle_over = True
            if players_alive:
                print("\nThe battle is over! The players are victorious!")
            elif npcs_alive:
                print("\nThe battle is over! The NPCs are victorious!")
            else:
                print("\nThe battle is over! It's a draw!")

# Test scenario
if __name__ == "__main__":
    from .character import Character
    
    player1 = PlayerAgent(Character.generate("Hero1"))
    player2 = PlayerAgent(Character.generate("Hero2"))
    
    npc1 = NPC.generate("Goblin1", "Warrior", "Goblin")
    npc2 = NPC.generate("Goblin2", "Archer", "Goblin")
    
    battle = Battle([player1, player2], [npc1, npc2])
    battle.start_battle()