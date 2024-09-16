from typing import Tuple, TYPE_CHECKING, Optional
from pydantic import Field
from .equipment import EquipmentItem
from autodm.core.enums import WeaponDamageType, ItemType
from autodm.utils.dice import roll_dice
from autodm.utils.llm import complete_pydantic

if TYPE_CHECKING:
    from ..agents.character_agent import CharacterAgent

class Weapon(EquipmentItem):
    damage_dice: str = Field(..., description="The damage dice of the weapon (ex: 1d8, 2d6, etc.)")
    damage_type: WeaponDamageType = Field(..., description="The damage type of the weapon")
    hit_bonus: int = Field(default=0, description="The hit bonus of the weapon")
    item_type: ItemType = Field(default=ItemType.WEAPON, description="The type of item")

    def calculate_damage(self) -> int:
        damage_rolls = roll_dice(self.damage_dice)
        return sum(damage_rolls)

    def attack(self, attacker: 'CharacterAgent', target: 'CharacterAgent') -> Tuple[bool, int, str]:
        """
        Attacks a target with the weapon.

        Args:
            attacker (CharacterAgent): The attacker.
            target (CharacterAgent): The target.

        Returns:
            Tuple[bool, int, str]: A tuple containing the result of the attack, the damage dealt, and the attack roll.
        """
        attacker_char = attacker.character if hasattr(attacker, 'character') else attacker
        target_char = target.character if hasattr(target, 'character') else target

        attack_roll = roll_dice("1d20")[0] + attacker_char.get_attack_bonus() + self.hit_bonus
        is_hit = attack_roll >= target_char.armor_class

        if is_hit:
            damage = self.calculate_damage() + attacker_char.get_damage_bonus()
            target_char.take_damage(damage)
            return True, damage, f"{attacker_char.name} hits {target_char.name} with {self.name} for {damage} {self.damage_type.name} damage. (Attack roll: {attack_roll})"
        else:
            return False, 0, f"{attacker_char.name} misses {target_char.name} with {self.name}. (Attack roll: {attack_roll})"

    @classmethod
    def generate(cls, message: Optional[str] = None):
        if message is None:
            message = "Generate a weapon."
        weapon = complete_pydantic(message, cls)
        return weapon

class MeleeWeapon(Weapon):
    reach: int = Field(5, description="The reach of the melee weapon in feet")

    def attack(self, attacker: 'CharacterAgent', target: 'CharacterAgent') -> Tuple[bool, int, str]:
        attacker_char = attacker.character if hasattr(attacker, 'character') else attacker
        target_char = target.character if hasattr(target, 'character') else target

        distance = attacker_char.position.distance_to(target_char.position)
        if distance > self.reach:
            return False, 0, f"{attacker_char.name} is too far from {target_char.name} to attack with {self.name}. (Distance: {distance} feet, Reach: {self.reach} feet)"
        return super().attack(attacker, target)

    @classmethod
    def generate(cls, message: Optional[str] = None):
        if message is None:
            message = "Generate a melee weapon."
        weapon = complete_pydantic(message, cls)
        return weapon

class RangedWeapon(Weapon):
    range_normal: int = Field(..., description="The normal range of the ranged weapon in feet")
    range_long: int = Field(..., description="The long range of the ranged weapon in feet")

    def attack(self, attacker: 'CharacterAgent', target: 'CharacterAgent') -> Tuple[bool, int, str]:
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
        if message is None:
            message = "Generate a ranged weapon."
        weapon = complete_pydantic(message, cls)
        return weapon

# Example weapon instances
unarmed_strike = MeleeWeapon(
    name="Unarmed Strike",
    description="You hit an opponent with your bare hands.",
    damage_dice="1d4",
    damage_type=WeaponDamageType.BLUDGEONING,
    hit_bonus=0,
    effects={},
    reach=5,
    weight=0
)

longsword = MeleeWeapon(
    name="Longsword",
    description="A versatile sword that can be wielded with one or two hands.",
    damage_dice="1d8",
    damage_type=WeaponDamageType.SLASHING,
    effects={},
    weight=5
)
greataxe = MeleeWeapon(
    name="Greataxe",
    description="A heavy, two-handed axe that deals devastating damage.",
    damage_dice="1d12",
    damage_type=WeaponDamageType.SLASHING,
    effects={},
    weight=0,
    reach=5,
)
shortbow = RangedWeapon(
    name="Shortbow",
    description="A small bow that's easy to use in close quarters.",
    damage_dice="1d6",
    damage_type=WeaponDamageType.PIERCING,
    range_normal=80,
    range_long=320,
    effects={},
    weight=2.0
)
longbow = RangedWeapon(
    name="Longbow",
    description="A tall bow that can shoot arrows at great distances.",
    damage_dice="1d8",
    damage_type=WeaponDamageType.PIERCING,
    range_normal=150,
    range_long=600,
    effects={},
    weight=2.0
)

if __name__ == "__main__":
    # Test generating weapons
    print("\nGenerating a melee weapon:")
    print(MeleeWeapon.generate())

    print("\nGenerating a ranged weapon:")
    print(RangedWeapon.generate())

    print("\nGenerating a specific weapon:")
    print(MeleeWeapon.generate("Generate a legendary two-handed sword with fire damage."))