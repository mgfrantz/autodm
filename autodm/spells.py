from typing import List, Optional
from enum import Enum

class SpellSchool(Enum):
    ABJURATION = "Abjuration"
    CONJURATION = "Conjuration"
    DIVINATION = "Divination"
    ENCHANTMENT = "Enchantment"
    EVOCATION = "Evocation"
    ILLUSION = "Illusion"
    NECROMANCY = "Necromancy"
    TRANSMUTATION = "Transmutation"

class Spell:
    def __init__(self, 
                 name: str,
                 base_level: int,
                 school: SpellSchool,
                 casting_time: str,
                 range: str,
                 components: str,
                 duration: str,
                 description: str,
                 classes: List[str],
                 ritual: bool = False):
        self.name = name
        self.base_level = base_level
        self.level = 0  # Default to 0 when learned
        self.school = school
        self.casting_time = casting_time
        self.range = range
        self.components = components
        self.duration = duration
        self.description = description
        self.classes = classes
        self.ritual = ritual

    def __str__(self):
        return f"{self.name} (Level {self.level}/{self.base_level} {self.school.value})"

    def set_level(self, level: int):
        """Set the spell's level, not exceeding its base level."""
        self.level = min(level, self.base_level)

# Example spells
fireball = Spell(
    name="Fireball",
    base_level=3,
    school=SpellSchool.EVOCATION,
    casting_time="1 action",
    range="150 feet",
    components="V, S, M (a tiny ball of bat guano and sulfur)",
    duration="Instantaneous",
    description="A bright streak flashes from your pointing finger to a point you choose within range and then blossoms with a low roar into an explosion of flame...",
    classes=["Sorcerer", "Wizard"]
)

cure_wounds = Spell(
    name="Cure Wounds",
    base_level=1,
    school=SpellSchool.EVOCATION,
    casting_time="1 action",
    range="Touch",
    components="V, S",
    duration="Instantaneous",
    description="A creature you touch regains a number of hit points equal to 1d8 + your spellcasting ability modifier...",
    classes=["Bard", "Cleric", "Druid", "Paladin", "Ranger"]
)


# Additional common D&D spells

magic_missile = Spell(
    name="Magic Missile",
    base_level=1,
    school=SpellSchool.EVOCATION,
    casting_time="1 action",
    range="120 feet",
    components="V, S",
    duration="Instantaneous",
    description="You create three glowing darts of magical force. Each dart hits a creature of your choice that you can see within range...",
    classes=["Sorcerer", "Wizard"]
)

healing_word = Spell(
    name="Healing Word",
    base_level=1,
    school=SpellSchool.EVOCATION,
    casting_time="1 bonus action",
    range="60 feet",
    components="V",
    duration="Instantaneous",
    description="A creature of your choice that you can see within range regains hit points equal to 1d4 + your spellcasting ability modifier...",
    classes=["Bard", "Cleric", "Druid"]
)

shield = Spell(
    name="Shield",
    base_level=1,
    school=SpellSchool.ABJURATION,
    casting_time="1 reaction",
    range="Self",
    components="V, S",
    duration="1 round",
    description="An invisible barrier of magical force appears and protects you. Until the start of your next turn, you have a +5 bonus to AC...",
    classes=["Sorcerer", "Wizard"]
)

bless = Spell(
    name="Bless",
    base_level=1,
    school=SpellSchool.ENCHANTMENT,
    casting_time="1 action",
    range="30 feet",
    components="V, S, M (a sprinkling of holy water)",
    duration="Concentration, up to 1 minute",
    description="You bless up to three creatures of your choice within range. Whenever a target makes an attack roll or a saving throw before the spell ends, the target can roll a d4 and add the number rolled to the attack roll or saving throw.",
    classes=["Cleric", "Paladin"]
)

detect_magic = Spell(
    name="Detect Magic",
    base_level=1,
    school=SpellSchool.DIVINATION,
    casting_time="1 action",
    range="Self",
    components="V, S",
    duration="Concentration, up to 10 minutes",
    description="For the duration, you sense the presence of magic within 30 feet of you. If you sense magic in this way, you can use your action to see a faint aura around any visible creature or object in the area that bears magic...",
    classes=["Bard", "Cleric", "Druid", "Paladin", "Ranger", "Sorcerer", "Wizard"],
    ritual=True
)
