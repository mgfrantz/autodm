from typing import Tuple, TYPE_CHECKING, Optional, Dict, Union
from pydantic import BaseModel, Field
from enum import Enum, auto
from .tools import roll_dice
from .llm import complete_pydantic

if TYPE_CHECKING:
    from .character import Character
    from .character_agent import CharacterAgent

class WeaponDamageType(Enum):
    SLASHING = auto()
    PIERCING = auto()
    BLUDGEONING = auto()

class Weapon(BaseModel):
    name: str = Field(..., description="The name of the weapon")
    damage_dice: str = Field(..., description="The dice roll used for damage calculation (e.g., '1d8')")
    damage_type: WeaponDamageType = Field(..., description="The type of damage dealt by the weapon")
    hit_bonus: int = Field(0, description="Bonus added to the attack roll")
    description: Optional[str] = Field(None, description="A description of the weapon")
    effects: Dict[str, Union[int, str]] = Field(default_factory=dict, description="The effects the weapon has when equipped")

    def calculate_damage(self) -> int:
        damage_rolls = roll_dice(self.damage_dice)
        return sum(damage_rolls)  # Return the sum of the damage rolls

    def attack(self, attacker: Union['Character', 'CharacterAgent'], target: Union['Character', 'CharacterAgent']) -> Tuple[bool, int, str]:
        attacker_char = attacker.character if hasattr(attacker, 'character') else attacker
        target_char = target.character if hasattr(target, 'character') else target

        attack_roll = roll_dice("1d20")[0] + attacker_char.get_attack_bonus() + self.hit_bonus
        is_hit = attack_roll >= target_char.armor_class

        if is_hit:
            damage = self.calculate_damage() + attacker_char.get_damage_bonus()
            if hasattr(target_char, 'take_damage'):
                target_char.take_damage(damage)
            else:
                print(f"Warning: {target_char.name} doesn't have a take_damage method.")
            return True, damage, f"{attacker_char.name} hits {target_char.name} with {self.name} for {damage} {self.damage_type.name} damage. (Attack roll: {attack_roll})"
        else:
            return False, 0, f"{attacker_char.name} misses {target_char.name} with {self.name}. (Attack roll: {attack_roll})"

    @classmethod
    def generate(cls, message: Optional[str] = None):
        """
        Generate a weapon using the LLM.

        Args:
            message (Optional[str]): The message to generate the weapon.

        Returns:
            Weapon: The generated weapon.
        """
        if message is None:
            message = "Generate a weapon."
        weapon = complete_pydantic(message, cls)
        return weapon

class MeleeWeapon(Weapon):
    reach: int = Field(5, description="The reach of the melee weapon in feet")
    item_type: str = Field("weapon", description="The type of item")

    def attack(self, attacker: Union['Character', 'CharacterAgent'], target: Union['Character', 'CharacterAgent']) -> Tuple[bool, int, str]:
        attacker_char = attacker.character if hasattr(attacker, 'character') else attacker
        target_char = target.character if hasattr(target, 'character') else target

        distance = attacker_char.position.distance_to(target_char.position)
        if distance > self.reach:
            return False, 0, f"{attacker_char.name} is too far from {target_char.name} to attack with {self.name}. (Distance: {distance} feet, Reach: {self.reach} feet)"
        return super().attack(attacker, target)

    @classmethod
    def generate(cls, message: Optional[str] = None):
        """
        Generate a melee weapon using the LLM.

        Args:
            message (Optional[str]): The message to generate the melee weapon.

        Returns:
            MeleeWeapon: The generated melee weapon.
        """
        if message is None:
            message = "Generate a melee weapon."
        weapon = complete_pydantic(message, cls)
        return weapon

class RangedWeapon(Weapon):
    range_normal: int = Field(80, description="The normal range of the ranged weapon in feet")
    range_long: int = Field(320, description="The long range of the ranged weapon in feet")
    item_type: str = Field("weapon", description="The type of item")

    def attack(self, attacker: Union['Character', 'CharacterAgent'], target: Union['Character', 'CharacterAgent']) -> Tuple[bool, int, str]:
        attacker_char = attacker.character if hasattr(attacker, 'character') else attacker
        target_char = target.character if hasattr(target, 'character') else target

        distance = attacker_char.position.distance_to(target_char.position)
        if distance > self.range_long:
            return False, 0, f"{attacker_char.name} is too far from {target_char.name} to attack with {self.name}. (Distance: {distance} feet, Max Range: {self.range_long} feet)"
        
        disadvantage = distance > self.range_normal
        
        if disadvantage:
            attack_roll = min(roll_dice("1d20")[0], roll_dice("1d20")[0]) + attacker_char.get_attack_bonus() + self.hit_bonus
            roll_info = "with disadvantage"
        else:
            attack_roll = roll_dice("1d20")[0] + attacker_char.get_attack_bonus() + self.hit_bonus
            roll_info = "normal roll"

        is_hit = attack_roll >= target_char.armor_class

        if is_hit:
            damage = self.calculate_damage() + attacker_char.get_damage_bonus()
            target_char.take_damage(damage)
            return True, damage, f"{attacker_char.name} hits {target_char.name} with {self.name} for {damage} {self.damage_type.name} damage. (Attack roll: {attack_roll}, {roll_info})"
        else:
            return False, 0, f"{attacker_char.name} misses {target_char.name} with {self.name}. (Attack roll: {attack_roll}, {roll_info})"

    @classmethod
    def generate(cls, message: Optional[str] = None):
        """
        Generate a ranged weapon using the LLM.

        Args:
            message (Optional[str]): The message to generate the ranged weapon.

        Returns:
            RangedWeapon: The generated ranged weapon.
        """
        if message is None:
            message = "Generate a ranged weapon."
        weapon = complete_pydantic(message, cls)
        return weapon

# Example weapon instances
longsword = MeleeWeapon(name="Longsword", damage_dice="1d8", damage_type=WeaponDamageType.SLASHING, effects={})
greataxe = MeleeWeapon(name="Greataxe", damage_dice="1d12", damage_type=WeaponDamageType.SLASHING, effects={})
shortbow = RangedWeapon(name="Shortbow", damage_dice="1d6", damage_type=WeaponDamageType.PIERCING, range_normal=80, range_long=320, effects={})
longbow = RangedWeapon(name="Longbow", damage_dice="1d8", damage_type=WeaponDamageType.PIERCING, range_normal=150, range_long=600, effects={})

if __name__ == "__main__":
    # Test generating weapons
    print("\nGenerating a melee weapon:")
    print(MeleeWeapon.generate())

    print("\nGenerating a ranged weapon:")
    print(RangedWeapon.generate())

    print("\nGenerating a specific weapon:")
    print(MeleeWeapon.generate("Generate a legendary two-handed sword with fire damage."))