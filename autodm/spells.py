from typing import List, Literal, Optional, Union
from enum import Enum
from pydantic import BaseModel, Field
from .tools import roll_dice
from .llm import complete_pydantic

class SpellSchool(Enum):
    ABJURATION = "Abjuration"
    CONJURATION = "Conjuration"
    DIVINATION = "Divination"
    ENCHANTMENT = "Enchantment"
    EVOCATION = "Evocation"
    ILLUSION = "Illusion"
    NECROMANCY = "Necromancy"
    TRANSMUTATION = "Transmutation"

SaveAttributeTypes = Literal["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]
AttackTypes = Literal["ranged", "save", "heal", "none"]

class Spell(BaseModel):
    name: str = Field(..., description="The name of the spell. Ex: Magic Missile.")
    level: int = Field(1, description="The level of the spell. Ex: 1.")
    is_cantrip: bool = Field(False, description="Whether the spell is a cantrip. Ex: False.")
    school: SpellSchool = Field(..., description="The school of the spell. Ex: Evocation.")
    casting_time: int = Field(1, description="The casting time of the spell in actions. Ex: 1")
    range: Union[int, Literal['touch']] = Field(..., description="The range of the spell in feet. Ex: 150.")
    attack_type: Optional[AttackTypes] = Field(..., description="The type of attack to be done by the spell. Ex: ranged.")
    save_attribute: Optional[SaveAttributeTypes] = Field(None, description="The attribute to be saved against the spell. Ex: strength.")
    components: Optional[str] = Field(..., description="The components of the spell. Ex: V, S, M (a tiny ball of bat guano and sulfur).")
    duration: str = Field(..., description="The duration of the spell. Ex: Instantaneous.")
    description: str = Field(..., description="The description of the spell. Ex: A bright streak flashes from your pointing finger to a point you choose within range and then blossoms with a low roar into an explosion of flame.")
    classes: List[str] = Field(default_factory=list, description="The classes that can use the spell. Ex: [Bard, Cleric, Paladin].")
    ritual: bool = Field(default=False, description="Whether the spell is a ritual. Ex: False.")

    def set_level(self, new_level: int):
        """
        Set a new level for the spell.

        Args:
            new_level (int): The new level to set for the spell.

        Raises:
            ValueError: If the new_level is not between 0 and 9 (inclusive).
        """
        if not 0 <= new_level <= 9:
            raise ValueError("Spell level must be between 0 and 9.")
        self.level = new_level

    def learn(self, character):
        """
        Learn the spell.

        Args:
            character: The character learning the spell.
        """
        character.spells.append(self)

    def get_spellcasting_ability(self, character):
        """
        Get the spellcasting ability for the character.

        Args:
            character: The character to get the spellcasting ability for.

        Returns:
            The spellcasting ability for the character.
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

    def cast(self, caster, target):
        """
        Cast the spell.

        Args:
            caster: The character casting the spell.
            target: The target of the spell.
        """
        raise NotImplementedError("This method must be implemented by a subclass.")
    
    def __str__(self):
        return f"{self.name} (Level {self.level} {self.school}), {self.description}"

class AttackSpell(Spell):
    attack_type: Literal["ranged", "touch"] = Field(..., description="The type of attack to be done by the spell. Ex: ranged.")
    save_attribute: Optional[SaveAttributeTypes] = Field(None, description="The attribute to be saved against the spell. Ex: strength.")
    damage: Optional[str] = Field(None, description="The damage to be done by the spell. Ex: 1d6.")

    def cast(self, caster, target):
        # Get the arcana modifier
        ability = self.get_spellcasting_ability(caster)
        modifier = caster.attributes.get_modifier(ability)
        # Roll the attack
        attack_roll = sum(roll_dice('1d20')) + modifier
        # Check if the attack hits
        if attack_roll >= 10 or self.is_cantrip:  # Assuming a default AC of 10 for simplicity
            # Calculate the damage
            damage_rolls = roll_dice(self.damage)
            damage = sum(damage_rolls)
            # Apply the damage
            target.hp = max(0, target.hp - damage)
            return f"{caster.name} attacks with {self.name} and rolls a {attack_roll} (hit). {target.name} takes {damage} damage."
        else:
            return f"{caster.name} attacks with {self.name} and rolls a {attack_roll} (miss)."
    
    @classmethod
    def generate(cls, message: Optional[str] = None):
        """
        Generate an attack spell using the LLM.

        Args:
            message (Optional[str]): The message to generate the spell.

        Returns:
            AttackSpell: The generated spell.
        """
        if message is None:
            message = "Generate a spell for the attack type."
        spell = complete_pydantic(message, AttackSpell)
        return spell

class HealingSpell(Spell):
    healing_amount: str = Field('1d6', description="The amount of healing to be done by the spell. Ex: 1d8.")
    attack_type: str = Field('heal', description="The type of attack to be done by the spell. Ex: heal.")

    def cast(self, caster, target):
        # Get the spellcasting ability modifier
        spellcasting_ability = self.get_spellcasting_ability(caster)
        spellcasting_modifier = caster.attributes.get_modifier(spellcasting_ability)
        
        # Roll for success
        success_roll = sum(roll_dice('1d20')) + spellcasting_modifier
        if success_roll >= 10 or self.is_cantrip:
            # Roll the healing
            healing_rolls = roll_dice(self.healing_amount)
            healing_amount = sum(healing_rolls) + spellcasting_modifier
            
            # Apply the healing
            old_hp = target.hp
            target.hp = min(target.hp + healing_amount, target.max_hp)
            actual_heal = target.hp - old_hp
            
            # Return the healing message
            return f"{caster.name} heals {target.name} with {self.name} for {actual_heal} HP (rolled {healing_amount})."
        else:
            return f"{caster.name} fails to heal {target.name} with {self.name}."

    @classmethod
    def generate(cls, message: Optional[str] = None):
        """
        Generate a healing spell using the LLM.

        Args:
            message (Optional[str]): The message to generate the spell.

        Returns:
            HealingSpell: The generated spell.
        """
        if message is None:
            message = "Generate a spell for healing."
        spell = complete_pydantic(message, cls)
        return spell

if __name__ == "__main__":
    from .character import Character
    from .defined_spells import cure_wounds, fireball

    # test casting a healing spell
    character = Character.generate()
    character.hp = character.max_hp - 5
    print(character)
    print(cure_wounds.cast(character, character))
    print(character)

    # test casting an attack spell
    character = Character.generate()
    print(character)
    print(fireball.cast(character, character))
    print(character)

    # test generating a healing spell
    try:
        print("Generating a healing spell...")
        print(HealingSpell.generate())
    except Exception as e:
        print(f"Unable to generate a healing spell: {str(e)}")

    # test generating an attack spell
    try:
        print("Generating an attack spell...")
        print(AttackSpell.generate())
    except Exception as e:
        print(f"Unable to generate an attack spell: {str(e)}")