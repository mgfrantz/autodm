from typing import Optional
from .character import Character, BattleState, CharacterState
from .items import Item, WeaponAttack, EquipmentItem
from .tools import roll_dice, apply_modifier
from .spells import Spell
import random

class Action:
    """Base class for all actions."""
    def __init__(self, character: Character):
        self.character = character

    def execute(self) -> str:
        """Execute the action and return a description of the result."""
        raise NotImplementedError("Subclasses must implement execute method")

class AttackAction(Action):
    """Action for attacking a target."""
    def __init__(self, character: Character, target: Optional[Character] = None, weapon: Optional[EquipmentItem] = None):
        super().__init__(character)
        self.target = target
        self.weapon = weapon or self._get_default_attack()

    def _get_default_attack(self) -> WeaponAttack:
        """Get a default unarmed attack if no weapon is specified."""
        return WeaponAttack(
            name="Unarmed Strike",
            hit_bonus=self.character.proficiency_bonus + self.character.attributes.get_modifier('strength'),
            damage="1d4"
        )

    def _get_weapon_attack(self, weapon: EquipmentItem) -> WeaponAttack:
        """Get a WeaponAttack object for the given weapon."""
        return WeaponAttack(
            name=weapon.name,
            hit_bonus=self.character.proficiency_bonus + self.character.attributes.get_modifier('strength'),
            damage=weapon.effects.get('damage', '1d4')
        )

    def execute(self) -> str:
        if self.target.character_state == CharacterState.DEAD:
            return f"{self.target.name} is already dead and cannot be attacked."

        if isinstance(self.weapon, EquipmentItem):
            weapon_attack = self._get_weapon_attack(self.weapon)
        else:
            weapon_attack = self.weapon

        attack_roll, _ = roll_dice("1d20")
        attack_total = apply_modifier(attack_roll, weapon_attack.hit_bonus)
        
        if attack_total >= self.target.armor_class:
            damage, _ = roll_dice(weapon_attack.damage)  # damage is now the total, not a list of rolls
            old_hp = self.target.hp
            self.target.hp -= damage
            actual_damage = old_hp - self.target.hp
            result = (f"{self.character.name} hits {self.target.name} with {weapon_attack.name} for {actual_damage} damage! "
                      f"{self.target.name}'s HP: {self.target.hp}/{self.target.max_hp}")
            if self.target.character_state == CharacterState.DEAD:
                result += f" {self.target.name} has been slain!"
            return result
        else:
            return (f"{self.character.name} misses {self.target.name} with {weapon_attack.name}. "
                    f"{self.target.name}'s HP: {self.target.hp}/{self.target.max_hp}")

class CastSpellAction(Action):
    """Action for casting a spell."""
    def __init__(self, character: Character, spell: Optional[Spell] = None, target: Optional[Character] = None):
        super().__init__(character)
        self.spell = spell
        self.target = target

    def execute(self) -> str:
        if not self.spell:
            return f"{self.character.name} tried to cast a spell, but no spell was specified."
        if self.spell not in self.character.spells:
            return f"{self.character.name} doesn't know the spell {self.spell.name}."
        if not self.character.can_cast_spell(self.spell):
            return f"{self.character.name} cannot cast {self.spell.name} at this time (no available spell slots)."
        
        try:
            self.character.cast_spell(self.spell)
            # ... (rest of the spell casting logic)
        except ValueError as e:
            return str(e)

class SkillCheckAction(Action):
    """Action for performing a skill check."""
    def __init__(self, character: Character, skill: str):
        super().__init__(character)
        self.skill = skill

    def execute(self) -> str:
        skill_modifier = self.character.skills.get(self.skill, 0)
        ability = self.get_ability_for_skill(self.skill)
        ability_modifier = self.character.attributes.get_modifier(ability)
        
        roll, _ = roll_dice("1d20")
        total = roll + skill_modifier + ability_modifier
        
        result = f"{self.character.name} attempts a {self.skill.capitalize()} check: "
        result += f"Roll: {roll}, Skill Modifier: {skill_modifier}, Ability Modifier: {ability_modifier}, Total: {total}"
        
        return result

    def get_ability_for_skill(self, skill: str) -> str:
        skill_ability_map = {
            'athletics': 'strength',
            'acrobatics': 'dexterity', 'sleight_of_hand': 'dexterity', 'stealth': 'dexterity',
            'arcana': 'intelligence', 'history': 'intelligence', 'investigation': 'intelligence', 'nature': 'intelligence', 'religion': 'intelligence',
            'animal_handling': 'wisdom', 'insight': 'wisdom', 'medicine': 'wisdom', 'perception': 'wisdom', 'survival': 'wisdom',
            'deception': 'charisma', 'intimidation': 'charisma', 'performance': 'charisma', 'persuasion': 'charisma'
        }
        return skill_ability_map.get(skill.lower(), 'intelligence')  # Default to intelligence if skill not found

class UseItemAction(Action):
    """Action for using an item."""
    def __init__(self, character: Character, item: Item, target: Optional[Character] = None):
        super().__init__(character)
        self.item = item
        self.target = target

    def execute(self) -> str:
        if self.item not in self.character.inventory:
            return f"{self.character.name} doesn't have {self.item.name} in their inventory."
        
        # Implement item use logic here
        return f"{self.character.name} uses {self.item.name} on {self.target.name if self.target else 'themselves'}."

class DodgeAction(Action):
    """Action for dodging in combat."""
    def execute(self) -> str:
        # Implement dodge mechanics here (e.g., advantage on Dex saves, attacks have disadvantage)
        return f"{self.character.name} takes the Dodge action, focusing entirely on avoiding attacks."

class DisengageAction(Action):
    """Action for disengaging from combat."""
    def execute(self) -> str:
        # Implement disengage mechanics here (e.g., movement doesn't provoke opportunity attacks)
        return f"{self.character.name} takes the Disengage action, carefully withdrawing from combat."

class DashAction(Action):
    """Action for dashing (extra movement)."""
    def execute(self) -> str:
        # Implement dash mechanics here (e.g., double movement speed)
        return f"{self.character.name} takes the Dash action, gaining extra movement speed."

class HideAction(Action):
    """Action for hiding."""
    def execute(self) -> str:
        stealth_check = SkillCheckAction(self.character, 'stealth')
        result = stealth_check.execute()
        return f"{self.character.name} attempts to Hide. {result}"

class HelpAction(Action):
    """Action for helping another character."""
    def __init__(self, character: Character, target: Character):
        super().__init__(character)
        self.target = target

    def execute(self) -> str:
        # Implement help mechanics here (e.g., target gets advantage on next check)
        return f"{self.character.name} helps {self.target.name}, granting advantage on their next ability check."

# ... (other action classes can be added as needed)

# Example usage
if __name__ == "__main__":
    from .character import Character, EquipmentItem, BattleState, CharacterState
    
    # Create two characters
    player = Character.generate("Elara")
    print(f"Player: {player}")
    enemy = Character.generate("Goblin")
    print(f"Enemy: {enemy}")
    
    # Create a weapon
    sword = EquipmentItem(name="Longsword", item_type="weapon", effects={"damage": "1d8+2"}, quantity=1, weight=3.0)
    player.equip_item(sword)
    
    # Create attack actions for both characters
    player_attack = AttackAction(player, enemy, WeaponAttack(name="Longsword", hit_bonus=5, damage="1d8+2"))
    enemy_attack = AttackAction(enemy, player, WeaponAttack(name="Shortsword", hit_bonus=4, damage="1d6+2"))
    
    # Continue battle until one character is dead
    round_count = 1
    while player.character_state == CharacterState.ALIVE and enemy.character_state == CharacterState.ALIVE:
        print(f"\nRound {round_count}:")
        
        # Player's turn
        result = player_attack.execute()
        print(result)
        if enemy.character_state == CharacterState.DEAD:
            print(f"\nThe battle is over. {enemy.name} has been defeated after {round_count} rounds.")
            break
        
        # Enemy's turn
        result = enemy_attack.execute()
        print(result)
        if player.character_state == CharacterState.DEAD:
            print(f"\nThe battle is over. {player.name} has been defeated after {round_count} rounds.")
            break
        
        round_count += 1
        if round_count > 20:  # Safety check to prevent infinite loop
            print("\nThe battle has gone on for too long. Ending simulation.")
            break

    print(f"\nFinal state of {player.name}: State: {player.character_state}, HP: {player.hp}/{player.max_hp}")
    print(f"Final state of {enemy.name}: State: {enemy.character_state}, HP: {enemy.hp}/{enemy.max_hp}")