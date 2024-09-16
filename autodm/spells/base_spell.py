from typing import List, Literal, Optional, Union
from pydantic import BaseModel, Field
from ..core.enums import SpellSchool

SaveAttributeTypes = Literal["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]
AttackTypes = Literal["ranged", "save", "heal", "none"]

class Spell(BaseModel):
    name: str
    level: int
    is_cantrip: bool = False
    school: SpellSchool
    casting_time: int
    range: Union[int, Literal['touch']]
    attack_type: Optional[AttackTypes]
    save_attribute: Optional[SaveAttributeTypes] = None
    components: Optional[str]
    duration: str
    description: str
    classes: List[str] = Field(default_factory=list)
    ritual: bool = False

    def set_level(self, new_level: int):
        if not 0 <= new_level <= 9:
            raise ValueError("Spell level must be between 0 and 9.")
        self.level = new_level

    def learn(self, character):
        character.spells.append(self)

    def get_spellcasting_ability(self, character):
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
        raise NotImplementedError("This method must be implemented by a subclass.")
    
    def __str__(self):
        return f"{self.name} (Level {self.level} {self.school}), {self.description}"