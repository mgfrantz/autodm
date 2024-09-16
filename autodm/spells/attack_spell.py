from typing import Literal, Optional
from pydantic import Field
from .base_spell import Spell, SaveAttributeTypes
from autodm.utils.dice import roll_dice

class AttackSpell(Spell):
    attack_type: Literal["ranged", "touch"]
    save_attribute: Optional[SaveAttributeTypes] = None
    damage: Optional[str] = None

    def cast(self, caster, target):
        # Ensure we're working with Character objects, not Agent objects
        caster_char = caster.character if hasattr(caster, 'character') else caster
        target_char = target.character if hasattr(target, 'character') else target

        ability = self.get_spellcasting_ability(caster_char)
        modifier = caster_char.attributes.get_modifier(ability)
        attack_roll = sum(roll_dice('1d20')) + modifier
        if attack_roll >= target_char.armor_class or self.is_cantrip:
            damage_rolls = roll_dice(self.damage)
            damage = sum(damage_rolls)
            target_char.current_hp = max(0, target_char.current_hp - damage)
            return f"{caster_char.name} attacks with {self.name} and rolls a {attack_roll} (hit). {target_char.name} takes {damage} damage."
        else:
            return f"{caster_char.name} attacks with {self.name} and rolls a {attack_roll} (miss)."
    
    @classmethod
    def generate(cls, message: Optional[str] = None):
        from autodm.utils.llm import complete_pydantic
        if message is None:
            message = "Generate a spell for the attack type."
        spell = complete_pydantic(message, AttackSpell)
        return spell