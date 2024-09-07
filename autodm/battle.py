from typing import List, Tuple, Dict, Optional
from .character import Character, CharacterState
from .actions import (Action, AttackAction, CastSpellAction, SkillCheckAction, UseItemAction,
                      DodgeAction, DisengageAction, DashAction, HideAction, HelpAction)
from .tools import roll_dice
import random
from .items import Item, EquipmentItem, WeaponAttack
from .spells import Spell

class Battle:
    def __init__(self, player_characters: List[Character], enemy_characters: List[Character]):
        self.player_characters = player_characters
        self.enemy_characters = enemy_characters
        self.all_characters = player_characters + enemy_characters
        self.initiative_order: List[Character] = []
        self.round_number = 0
        self.current_character_index = 0

        # Ensure all characters have their armor class calculated correctly
        for character in self.all_characters:
            character.calculate_armor_class()

    def roll_initiative(self):
        """Roll initiative for all characters and sort them in descending order."""
        initiative_rolls: List[Tuple[Character, int]] = []
        for character in self.all_characters:
            roll, _ = roll_dice("1d20")
            initiative_rolls.append((character, roll + character.initiative))

        initiative_rolls.sort(key=lambda x: x[1], reverse=True)
        self.initiative_order = [character for character, _ in initiative_rolls]

    def start_battle(self):
        """Start the battle by rolling initiative."""
        self.roll_initiative()
        print("Initiative order:")
        for i, character in enumerate(self.initiative_order, 1):
            print(f"{i}. {character.name}")

    def get_current_character(self) -> Character:
        """Get the character whose turn it currently is."""
        return self.initiative_order[self.current_character_index]

    def get_valid_targets(self, character: Character, action: Action) -> List[Character]:
        """Get a list of valid targets for the given character and action."""
        if isinstance(action, AttackAction):
            if character in self.player_characters:
                return [c for c in self.enemy_characters if c.character_state == CharacterState.ALIVE]
            else:
                return [c for c in self.player_characters if c.character_state == CharacterState.ALIVE]
        elif isinstance(action, CastSpellAction):
            if action.spell.name in ["Cure Wounds", "Healing Word", "Bless"]:  # Add more healing/buff spells as needed
                return [c for c in self.all_characters if c.character_state == CharacterState.ALIVE]
            else:
                return [c for c in self.all_characters if c.character_state == CharacterState.ALIVE and c != character]
        else:
            return [c for c in self.all_characters if c.character_state == CharacterState.ALIVE]

    def get_available_actions(self, character: Character) -> Dict[str, Action]:
        """Get a dictionary of available actions for the given character."""
        actions = {}
        weapons = character.get_equipped_weapons()
        if weapons:
            for weapon in weapons:
                actions[f"Attack with {weapon.name}"] = AttackAction(character, None, weapon)
        else:
            actions["Unarmed Attack"] = AttackAction(character, None)
        
        # Add spell casting action if the character has spells
        if character.spells:
            actions["Cast Spell"] = CastSpellAction(character, None, None)
        
        # Add other actions...
        actions["Dodge"] = DodgeAction(character)
        actions["Disengage"] = DisengageAction(character)
        actions["Dash"] = DashAction(character)
        actions["Hide"] = HideAction(character)
        
        return actions

    def execute_turn(self, character: Character, action: Action, target: Optional[Character] = None):
        """Execute a turn for a single character."""
        print(f"\n{character.name}'s turn:")
        
        if isinstance(action, AttackAction):
            action.target = target
        elif isinstance(action, CastSpellAction):
            action.target = target
        
        result = action.execute()
        print(result)

        # Remove dead characters from the initiative order
        self.initiative_order = [c for c in self.initiative_order if c.character_state == CharacterState.ALIVE]

    def next_turn(self):
        """Move to the next character's turn."""
        self.current_character_index = (self.current_character_index + 1) % len(self.initiative_order)
        if self.current_character_index == 0:
            self.round_number += 1
            print(f"\nRound {self.round_number}")

    def is_battle_over(self) -> bool:
        """Check if the battle has ended."""
        players_alive = any(c.character_state == CharacterState.ALIVE for c in self.player_characters)
        enemies_alive = any(c.character_state == CharacterState.ALIVE for c in self.enemy_characters)
        
        if not players_alive or not enemies_alive:
            print("\nThe battle has ended!")
            if players_alive:
                print("The players are victorious!")
            elif enemies_alive:
                print("The enemies have won!")
            else:
                print("All combatants have fallen!")
            return True
        return False

    def get_battle_status(self) -> str:
        """Get a string representation of the current battle status."""
        status = f"Round: {self.round_number}\n"
        status += "Players:\n"
        for character in self.player_characters:
            status += f"  {character.name}: HP {character.hp}/{character.max_hp}\n"
        status += "Enemies:\n"
        for character in self.enemy_characters:
            status += f"  {character.name}: HP {character.hp}/{character.max_hp}\n"
        return status

# Example usage (this would typically be in your main game loop)
if __name__ == "__main__":
    from .character import Character
    from .spells import fireball, cure_wounds

    # Create some characters
    player1 = Character.generate("Alice", chr_class="Wizard")
    player2 = Character.generate("Bob", chr_class="Sorcerer")
    enemy1 = Character.generate("Goblin 1")
    enemy2 = Character.generate("Goblin 2")

    # Equip Alice with a sword and a dagger
    sword = EquipmentItem(name="Sword", item_type="weapon", effects={"damage": "1d8+2"}, quantity=1, weight=3.0)
    dagger = EquipmentItem(name="Dagger", item_type="weapon", effects={"damage": "1d4+2"}, quantity=1, weight=1.0)
    shield = EquipmentItem(name="Shield", item_type="armor", effects={"armor_class": 2}, quantity=1, weight=6.0)
    player1.equip_item(sword)
    player1.equip_item(dagger)
    player1.equip_item(shield)

    # Recalculate armor class after equipping items
    player1.calculate_armor_class()

    # Give Bob (player2) the Fireball and Cure Wounds spells
    player2.add_spell(fireball)
    player2.add_spell(cure_wounds)

    # Create a battle
    battle = Battle([player1, player2], [enemy1, enemy2])
    battle.start_battle()

    while not battle.is_battle_over():
        print(battle.get_battle_status())
        current_character = battle.get_current_character()
        
        if current_character in battle.player_characters:
            print(f"\n{current_character.name}'s turn:")
            actions = battle.get_available_actions(current_character)
            print("Available actions:")
            for i, action_name in enumerate(actions.keys(), 1):
                print(f"{i}. {action_name}")
            
            action_choice = int(input("Choose an action (enter the number): ")) - 1
            chosen_action = list(actions.values())[action_choice]
            
            chosen_spell = None
            if isinstance(chosen_action, CastSpellAction):
                print("Available spells:")
                for i, spell in enumerate(current_character.spells, 1):
                    print(f"{i}. {spell}")
                spell_choice = int(input("Choose a spell (enter the number): ")) - 1
                chosen_spell = current_character.spells[spell_choice]
                chosen_action = CastSpellAction(current_character, chosen_spell)
            
            targets = battle.get_valid_targets(current_character, chosen_action)
            print("Available targets:")
            for i, target in enumerate(targets, 1):
                print(f"{i}. {target.name}")
            
            target_choice = int(input("Choose a target (enter the number): ")) - 1
            chosen_target = targets[target_choice]
            
            battle.execute_turn(current_character, chosen_action, chosen_target, chosen_spell)
        else:
            # For enemy turns, we'll use a simple AI that just attacks a random player
            action = AttackAction(current_character, None)
            target = random.choice(battle.get_valid_targets(current_character, action))
            battle.execute_turn(current_character, action, target)
        
        battle.next_turn()

    print(battle.get_battle_status())