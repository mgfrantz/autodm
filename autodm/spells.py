from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field

class SpellSchool(Enum):
    ABJURATION = "Abjuration"
    CONJURATION = "Conjuration"
    DIVINATION = "Divination"
    ENCHANTMENT = "Enchantment"
    EVOCATION = "Evocation"
    ILLUSION = "Illusion"
    NECROMANCY = "Necromancy"
    TRANSMUTATION = "Transmutation"

class Spell(BaseModel):
    name: str
    level: int
    school: str
    casting_time: str
    range: str
    components: str
    duration: str
    description: str
    attack_type: Optional[str] = None  # "ranged" or "save" or None
    save_attribute: Optional[str] = None  # e.g., "dexterity", "wisdom", etc.
    damage: Optional[str] = None  # e.g., "3d6"
    classes: List[str] = Field(default_factory=list)
    ritual: bool = False

    def set_level(self, new_level: int):
        self.level = new_level

fireball = Spell(
    name="Fireball",
    level=3,
    school="Evocation",
    casting_time="1 action",
    range="150 feet",
    components="V, S, M (a tiny ball of bat guano and sulfur)",
    duration="Instantaneous",
    description="A bright streak flashes from your pointing finger to a point you choose within range and then blossoms with a low roar into an explosion of flame.",
    attack_type="save",
    save_attribute="dexterity",
    damage="8d6",
    classes=["Sorcerer", "Wizard"]
)

magic_missile = Spell(
    name="Magic Missile",
    level=1,
    school="Evocation",
    casting_time="1 action",
    range="120 feet",
    components="V, S",
    duration="Instantaneous",
    description="You create three glowing darts of magical force. Each dart hits a creature of your choice that you can see within range.",
    attack_type="ranged",
    damage="1d4+1",
    classes=["Sorcerer", "Wizard"]
)

shield = Spell(
    name="Shield",
    level=1,
    school="Abjuration",
    casting_time="1 reaction",
    range="Self",
    components="V, S",
    duration="1 round",
    description="An invisible barrier of magical force appears and protects you.",
    classes=["Bard", "Cleric", "Druid", "Paladin", "Ranger"]
)

# Example spells
cure_wounds = Spell(
    name="Cure Wounds",
    level=1,
    school="Evocation",
    casting_time="1 action",
    range="Touch",
    components="V, S",
    duration="Instantaneous",
    description="A creature you touch regains a number of hit points equal to 1d8 + your spellcasting ability modifier...",
    attack_type=None,
    save_attribute=None,
    damage=None,
    classes=["Bard", "Cleric", "Druid", "Paladin", "Ranger"]
)


# Additional common D&D spells

healing_word = Spell(
    name="Healing Word",
    level=1,
    school="Evocation",
    casting_time="1 bonus action",
    range="60 feet",
    components="V",
    duration="Instantaneous",
    description="A creature of your choice that you can see within range regains hit points equal to 1d4 + your spellcasting ability modifier...",
    attack_type=None,
    save_attribute=None,
    damage=None,
    classes=["Bard", "Cleric", "Druid"]
)

bless = Spell(
    name="Bless",
    level=1,
    school="Enchantment",
    casting_time="1 action",
    range="30 feet",
    components="V, S, M (a sprinkling of holy water)",
    duration="Concentration, up to 1 minute",
    description="You bless up to three creatures of your choice within range. Whenever a target makes an attack roll or a saving throw before the spell ends, the target can roll a d4 and add the number rolled to the attack roll or saving throw.",
    attack_type=None,
    save_attribute=None,
    damage=None,
    classes=["Cleric", "Paladin"]
)

detect_magic = Spell(
    name="Detect Magic",
    level=1,
    school="Divination",
    casting_time="1 action",
    range="Self",
    components="V, S",
    duration="Concentration, up to 10 minutes",
    description="For the duration, you sense the presence of magic within 30 feet of you. If you sense magic in this way, you can use your action to see a faint aura around any visible creature or object in the area that bears magic...",
    attack_type=None,
    save_attribute=None,
    damage=None,
    classes=["Bard", "Cleric", "Druid", "Paladin", "Ranger", "Sorcerer", "Wizard"],
    ritual=True
)
