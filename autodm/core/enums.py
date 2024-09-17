from enum import Enum, auto

class CharacterState(Enum):
    ALIVE = auto()
    DEAD = auto()
    UNCONSCIOUS = auto()

class WeaponDamageType(Enum):
    SLASHING = auto()
    PIERCING = auto()
    BLUDGEONING = auto()

class SpellSchool(Enum):
    ABJURATION = auto()
    CONJURATION = auto()
    DIVINATION = auto()
    ENCHANTMENT = auto()
    EVOCATION = auto()
    ILLUSION = auto()
    NECROMANCY = auto()
    TRANSMUTATION = auto()

class ItemType(Enum):
    WEAPON = "weapon"
    ARMOR = "armor"
    POTION = "potion"
    SCROLL = "scroll"
    WAND = "wand"
    RING = "ring"
    AMULET = "amulet"
    MISCELLANEOUS = "miscellaneous"

class CharacterClass(Enum):
    BARBARIAN = "Barbarian"
    BARD = "Bard"
    CLERIC = "Cleric"
    DRUID = "Druid"
    FIGHTER = "Fighter"
    MONK = "Monk"
    PALADIN = "Paladin"
    RANGER = "Ranger"
    ROGUE = "Rogue"
    SORCERER = "Sorcerer"
    WARLOCK = "Warlock"
    WIZARD = "Wizard"

class CharacterRace(Enum):
    HUMAN = "Human"
    ELF = "Elf"
    DWARF = "Dwarf"
    HALFLING = "Halfling"
    GNOME = "Gnome"
    HALF_ELF = "Half-Elf"
    HALF_ORC = "Half-Orc"
    TIEFLING = "Tiefling"
    DRAGONBORN = "Dragonborn"

class ActionType(Enum):
    STANDARD = auto()
    MOVEMENT = auto()
    BONUS = auto()
    REACTION = auto()