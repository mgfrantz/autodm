from pydantic import Field
from .base_spell import Spell
from autodm.utils.dice import roll_dice
from typing import Optional

class HealingSpell(Spell):
    healing_amount: str = Field('1d6', description="The amount of healing to be done by the spell. Ex: 1d8.")
    attack_type: str = Field('heal', description="The type of attack to be done by the spell. Ex: heal.")

    def cast(self, caster, target):
        spellcasting_ability = self.get_spellcasting_ability(caster)
        spellcasting_modifier = caster.attributes.get_modifier(spellcasting_ability)
        
        success_roll = sum(roll_dice('1d20')) + spellcasting_modifier
        if success_roll >= 10 or self.is_cantrip:
            healing_rolls = roll_dice(self.healing_amount)
            healing_amount = sum(healing_rolls) + spellcasting_modifier
            
            old_hp = target.hp
            target.hp = min(target.hp + healing_amount, target.max_hp)
            actual_heal = target.hp - old_hp
            
            return f"{caster.name} heals {target.name} with {self.name} for {actual_heal} HP (rolled {healing_amount})."
        else:
            return f"{caster.name} fails to heal {target.name} with {self.name}."

    @classmethod
    def generate(cls, message: Optional[str] = None):
        from autodm.utils.llm import complete_pydantic
        if message is None:
            message = "Generate a spell for healing."
        spell = complete_pydantic(message, cls)
        return spell