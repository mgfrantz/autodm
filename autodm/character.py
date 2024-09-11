from typing import List, Optional, Dict, Union, ClassVar, Tuple
from pydantic import BaseModel, Field
import random
from .items import Item, WeaponAttack, EquipmentItem
from enum import Enum
from .spells import Spell, fireball, magic_missile, shield, cure_wounds
import copy

class BattleState(Enum):
    NOT_IN_BATTLE = 0
    IN_BATTLE = 1

class CharacterState(Enum):
    ALIVE = 0
    DEAD = 1

class Attributes(BaseModel):
    strength: int = Field(10, ge=1, le=20)
    dexterity: int = Field(10, ge=1, le=20)
    constitution: int = Field(10, ge=1, le=20)
    intelligence: int = Field(10, ge=1, le=20)
    wisdom: int = Field(10, ge=1, le=20)
    charisma: int = Field(10, ge=1, le=20)

    def get_modifier(self, attribute: str) -> int:
        """Calculate the modifier for a given attribute."""
        return (getattr(self, attribute) - 10) // 2

    def __str__(self):
        return "\n".join([f"{attr.capitalize()}: {getattr(self, attr)} ({self.get_modifier(attr):+d})" for attr in self.__fields__])

class Relationship(BaseModel):
    target: str  # Name of the character this relationship is with
    attitude: int = Field(0, ge=-100, le=100)  # -100 (hostile) to 100 (friendly)
    description: str = ""

class Position(BaseModel):
    x: int = 0
    y: int = 0

    def __eq__(self, other):
        return self.x == other.x and self.y == other.y

    def distance_to(self, other: 'Position') -> int:
        return abs(self.x - other.x) + abs(self.y - other.y)

class Character(BaseModel):
    name: str
    chr_class: str
    level: int
    chr_race: str
    background: str
    alignment: str
    experience_points: int
    attributes: Attributes
    proficiency_bonus: int
    armor_class: int
    initiative: int
    speed: int
    max_hp: int
    current_hp: int = Field(...)  # Remove the default value and alias
    spells: List[Spell] = Field(default_factory=list)
    spell_slots: Dict[int, int] = Field(default_factory=lambda: {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0})
    relationships: Dict[str, Relationship] = Field(default_factory=dict)
    position: Position = Field(default_factory=Position)

    class Config:
        arbitrary_types_allowed = True

    @property
    def hp(self) -> int:
        return self.current_hp

    @hp.setter
    def hp(self, value: int) -> None:
        self.current_hp = max(0, min(value, self.max_hp))
        self.check_death()

    skills: Dict[str, int] = Field(default_factory=dict)
    equipped_items: Dict[str, List[Optional[EquipmentItem]]] = Field(default_factory=lambda: {
        "weapon": [],
        "armor": [],
        "accessory": []
    })
    inventory: List[EquipmentItem] = Field(default_factory=list)
    movement_speed: int = 30  # Default movement speed in feet
    movement_remaining: int = 30  # Default movement remaining in feet
    battle_state: BattleState = BattleState.NOT_IN_BATTLE  # Default battle state
    character_state: CharacterState = CharacterState.ALIVE  # Default character state

    RACES: ClassVar[Dict[str, Dict[str, int]]] = {
        "Human": {"all": 1},
        "Elf": {"dexterity": 2, "intelligence": 1},
        "Dwarf": {"constitution": 2, "wisdom": 1},
        "Halfling": {"dexterity": 2, "charisma": 1},
        "Dragonborn": {"strength": 2, "charisma": 1},
        "Gnome": {"intelligence": 2, "constitution": 1},
        "Half-Elf": {"charisma": 2, "choice": 2},
        "Half-Orc": {"strength": 2, "constitution": 1},
        "Tiefling": {"intelligence": 1, "charisma": 2}
    }

    CLASSES: ClassVar[Dict[str, Dict[str, str]]] = {
        "Barbarian": {"hit_dice": "1d12", "primary": "strength"},
        "Bard": {"hit_dice": "1d8", "primary": "charisma"},
        "Cleric": {"hit_dice": "1d8", "primary": "wisdom"},
        "Druid": {"hit_dice": "1d8", "primary": "wisdom"},
        "Fighter": {"hit_dice": "1d10", "primary": "strength"},
        "Monk": {"hit_dice": "1d8", "primary": "dexterity"},
        "Paladin": {"hit_dice": "1d10", "primary": "strength"},
        "Ranger": {"hit_dice": "1d10", "primary": "dexterity"},
        "Rogue": {"hit_dice": "1d8", "primary": "dexterity"},
        "Sorcerer": {"hit_dice": "1d6", "primary": "charisma"},
        "Warlock": {"hit_dice": "1d8", "primary": "charisma"},
        "Wizard": {"hit_dice": "1d6", "primary": "intelligence"}
    }

    def add_spell(self, spell: Spell):
        """
        Add a spell to the character's spell list if they don't already know it.
        The spell's level remains unchanged.
        
        Args:
        spell (Spell): The spell to add.
        
        Returns:
        bool: True if the spell was added, False if the character already knew the spell.
        """
        if not any(existing_spell.name == spell.name for existing_spell in self.spells):
            spell_copy = copy.deepcopy(spell)
            self.spells.append(spell_copy)
            return True
        return False

    def can_cast_spell(self, spell: Spell) -> bool:
        """Check if the character can cast the given spell."""
        return self.spell_slots.get(spell.level, 0) > 0

    def cast_spell(self, spell: Spell) -> None:
        """Cast a spell, using up a spell slot."""
        if self.can_cast_spell(spell):
            self.spell_slots[spell.level] -= 1
        else:
            raise ValueError(f"Cannot cast {spell.name}: no available spell slots")

    @classmethod
    def generate(cls, name: str, **kwargs) -> 'Character':
        """
        Generate a new Character instance with random attributes, race, and class.

        Args:
        name (str): The character's name.
        **kwargs: Additional arguments to pass to the Character constructor.

        Returns:
        Character: A new Character instance with randomly generated attributes.
        """
        def roll_attribute():
            return sum(sorted([random.randint(1, 6) for _ in range(4)])[1:])

        attributes = Attributes(
            strength=roll_attribute(),
            dexterity=roll_attribute(),
            constitution=roll_attribute(),
            intelligence=roll_attribute(),
            wisdom=roll_attribute(),
            charisma=roll_attribute()
        )

        chr_race = kwargs.get('chr_race', random.choice(list(cls.RACES.keys())))
        chr_class = kwargs.get('chr_class', random.choice(list(cls.CLASSES.keys())))

        # Apply racial modifiers
        race_mods = cls.RACES[chr_race]
        for attr, mod in race_mods.items():
            if attr == "all":
                for key in attributes.__fields__:
                    setattr(attributes, key, getattr(attributes, key) + mod)
            elif attr == "choice":
                # For races like Half-Elf that get to choose which attributes to increase
                for _ in range(mod):
                    chosen_attr = random.choice([a for a in attributes.__fields__ if a != "charisma"])
                    setattr(attributes, chosen_attr, getattr(attributes, chosen_attr) + 1)
            else:
                setattr(attributes, attr, getattr(attributes, attr) + mod)

        level = kwargs.get('level', 1)
        proficiency_bonus = 2
        armor_class = 10 + attributes.get_modifier('dexterity')
        initiative = attributes.get_modifier('dexterity')
        speed = kwargs.get('speed', 30)  # Default speed, can be adjusted based on race
        hit_dice = cls.CLASSES[chr_class]["hit_dice"]
        max_hp = int(hit_dice.split('d')[1]) + attributes.get_modifier('constitution')

        default_spells = []
        if chr_class in ["Wizard", "Sorcerer"]:
            default_spells.extend([fireball, magic_missile, shield])
        elif chr_class in ["Cleric", "Druid", "Paladin"]:
            default_spells.append(cure_wounds)

        # Set up spell slots based on class and level
        spell_slots = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}
        if chr_class in ["Wizard", "Sorcerer", "Bard", "Cleric", "Druid"]:
            if level >= 1:
                spell_slots[1] = 2
            if level >= 3:
                spell_slots[2] = 2
            if level >= 5:
                spell_slots[3] = 2

        # Initialize skills based on class and background
        skills = {
            'acrobatics': 0, 'animal_handling': 0, 'arcana': 0, 'athletics': 0,
            'deception': 0, 'history': 0, 'insight': 0, 'intimidation': 0,
            'investigation': 0, 'medicine': 0, 'nature': 0, 'perception': 0,
            'performance': 0, 'persuasion': 0, 'religion': 0, 'sleight_of_hand': 0,
            'stealth': 0, 'survival': 0
        }

        # Add proficiency to skills based on class (simplified version)
        class_skills = {
            "Barbarian": ["animal_handling", "athletics", "intimidation", "nature", "perception", "survival"],
            "Bard": ["acrobatics", "animal_handling", "arcana", "athletics", "deception", "history", "insight", "intimidation", "investigation", "medicine", "nature", "perception", "performance", "persuasion", "religion", "sleight_of_hand", "stealth", "survival"],
            "Cleric": ["history", "insight", "medicine", "persuasion", "religion"],
            "Druid": ["arcana", "animal_handling", "insight", "medicine", "nature", "perception", "religion", "survival"],
            "Fighter": ["acrobatics", "animal_handling", "athletics", "history", "insight", "intimidation", "perception", "survival"],
            "Monk": ["acrobatics", "athletics", "history", "insight", "religion", "stealth"],
            "Paladin": ["athletics", "insight", "intimidation", "medicine", "persuasion", "religion"],
            "Ranger": ["animal_handling", "athletics", "insight", "investigation", "nature", "perception", "stealth", "survival"],
            "Rogue": ["acrobatics", "athletics", "deception", "insight", "intimidation", "investigation", "perception", "performance", "persuasion", "sleight_of_hand", "stealth"],
            "Sorcerer": ["arcana", "deception", "insight", "intimidation", "persuasion", "religion"],
            "Warlock": ["arcana", "deception", "history", "intimidation", "investigation", "nature", "religion"],
            "Wizard": ["arcana", "history", "insight", "investigation", "medicine", "religion"]
        }

        # Add proficiency to 2 random skills from the class list
        proficient_skills = random.sample(class_skills[chr_class], 2)
        for skill in proficient_skills:
            skills[skill] = proficiency_bonus

        default_args = {
            "name": name,
            "chr_class": chr_class,
            "level": level,
            "chr_race": chr_race,
            "background": random.choice(["Acolyte", "Criminal", "Folk Hero", "Noble", "Sage", "Soldier"]),
            "alignment": random.choice(["Lawful Good", "Neutral Good", "Chaotic Good", "Lawful Neutral", "True Neutral", "Chaotic Neutral", "Lawful Evil", "Neutral Evil", "Chaotic Evil"]),
            "experience_points": 0,
            "attributes": attributes,
            "proficiency_bonus": proficiency_bonus,
            "armor_class": armor_class,
            "initiative": initiative,
            "speed": speed,
            "max_hp": max_hp,
            "current_hp": max_hp,  # Set current_hp to max_hp initially
            "hit_dice": hit_dice,
            "skills": skills,
            "spells": [],  # Start with an empty spell list
            "spell_slots": spell_slots
        }

        # Update default_args with any additional kwargs
        default_args.update(kwargs)

        character = cls(**default_args)

        # Add default spells using the new add_spell method
        for spell in default_spells:
            character.add_spell(spell)

        # Set up spell slots for a level 5 Wizard
        if character.chr_class.lower() == "wizard" and character.level == 5:
            character.spell_slots = {1: 4, 2: 3, 3: 2, 4: 1, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}

        return character

    def equip_item(self, item: EquipmentItem) -> None:
        """
        Equip an item to the character.
        """
        if item.item_type.lower() in ['weapon', 'armor', 'shield', 'ring']:
            slot = item.item_type.lower()
            if slot == 'shield':
                slot = 'armor'
            self.equipped_items[slot].append(item)
            print(f"Equipped: {item.name}")
            self.calculate_armor_class()
        else:
            raise ValueError(f"{item.name} is not equippable.")

    def get_equipped_weapons(self) -> List[EquipmentItem]:
        """Get a list of all equipped weapons."""
        return [item for item in self.equipped_items['weapon'] if item is not None]

    def calculate_armor_class(self):
        """
        Calculate the character's armor class based on equipped items and dexterity.
        """
        dex_modifier = self.attributes.get_modifier('dexterity')
        base_ac = 10 + dex_modifier  # Start with base AC

        armor = self.equipped_items.get('armor')
        if armor:
            for item in armor:
                if 'armor_class' in item.effects:
                    if isinstance(item.effects['armor_class'], int):
                        base_ac = max(base_ac, item.effects['armor_class'] + dex_modifier)
                    else:
                        # If it's a string (like "11 + Dex modifier"), we'll need to parse it
                        armor_base = int(item.effects['armor_class'].split()[0])
                        base_ac = max(base_ac, armor_base + dex_modifier)

        # Add AC bonuses from other equipped items
        for item in self.equipped_items.values():
            if item:
                for i in item:
                    if i and 'armor_class' in i.effects:
                        if isinstance(i.effects['armor_class'], int):
                            base_ac += i.effects['armor_class']

        self.armor_class = base_ac
        print(f"Armor Class recalculated: {self.armor_class}")

    def unequip_item(self, item_type: str):
        """
        Unequip an item and remove its effects from the character.

        Args:
        item_type (str): The type of item to unequip.
        """
        item = self.equipped_items.get(item_type.lower())
        if item:
            # Remove the item from equipped items
            self.equipped_items[item_type.lower()] = []
            
            # Add the item back to inventory
            self.inventory.append(item)
            
            # Recalculate armor class
            self.calculate_armor_class()
            
            print(f"Unequipped: {item.name}")
        else:
            print(f"No item equipped in {item_type} slot.")

    def add_to_inventory(self, item: Item):
        """
        Add an item to the character's inventory.

        Args:
        item (Item): The item to add to the inventory.
        """
        self.inventory.append(item)

    @property
    def hp(self) -> int:
        return self.current_hp

    @hp.setter
    def hp(self, value: int) -> None:
        self.current_hp = max(0, min(value, self.max_hp))
        self.check_death()

    def check_death(self) -> None:
        """Check if the character has died and update their state accordingly."""
        if self.current_hp <= 0:
            self.current_hp = 0  # Ensure HP doesn't go below 0
            self.character_state = CharacterState.DEAD
            print(f"{self.name} has died!")

    def __str__(self):
        status = "ALIVE" if self.character_state == CharacterState.ALIVE else "DEAD"
        equipped_items_str = ", ".join([f"{slot}: {', '.join([item.name for item in items if item])}" for slot, items in self.equipped_items.items() if items])
        return (f"{self.name}, Level {self.level} {self.chr_race} {self.chr_class} ({status})\n"
                f"Attributes:\n{self.attributes}\n"
                f"Armor Class: {self.armor_class}\n"
                f"Hit Points: {self.current_hp}/{self.max_hp}\n"
                f"Equipped: {equipped_items_str}")

    def reset_movement(self):
        """Reset the character's movement at the start of their turn."""
        self.movement_remaining = self.movement_speed

    def set_relationship(self, target_name: str, attitude: int, description: str = ""):
        """Set or update a relationship with another character."""
        self.relationships[target_name] = Relationship(
            target=target_name,
            attitude=attitude,
            description=description
        )

    def get_relationship(self, target_name: str) -> Optional[Relationship]:
        """Get the relationship with another character."""
        return self.relationships.get(target_name)

    def get_skill_modifier(self, skill: str) -> int:
        """Calculate the modifier for a given skill."""
        ability = self.get_ability_for_skill(skill)
        return self.skills.get(skill, 0) + self.attributes.get_modifier(ability)

    def get_ability_for_skill(self, skill: str) -> str:
        skill_ability_map = {
            'athletics': 'strength',
            'acrobatics': 'dexterity', 'sleight_of_hand': 'dexterity', 'stealth': 'dexterity',
            'arcana': 'intelligence', 'history': 'intelligence', 'investigation': 'intelligence', 'nature': 'intelligence', 'religion': 'intelligence',
            'animal_handling': 'wisdom', 'insight': 'wisdom', 'medicine': 'wisdom', 'perception': 'wisdom', 'survival': 'wisdom',
            'deception': 'charisma', 'intimidation': 'charisma', 'performance': 'charisma', 'persuasion': 'charisma'
        }
        return skill_ability_map.get(skill.lower(), 'intelligence')  # Default to intelligence if skill not found

    def move(self, new_position: Position):
        self.position = new_position

class Characters:
    def __init__(self):
        self.characters: Dict[str, Character] = {}

    def add_character(self, character: Character):
        """Add a character to the game."""
        self.characters[character.name] = character

    def get_character(self, name: str) -> Optional[Character]:
        """Get a character by name."""
        return self.characters.get(name)

    def remove_character(self, name: str):
        """Remove a character from the game."""
        if name in self.characters:
            del self.characters[name]

    def set_relationship(self, character1_name: str, character2_name: str, attitude: int, description: str = ""):
        """Set or update a relationship between two characters."""
        char1 = self.get_character(character1_name)
        char2 = self.get_character(character2_name)
        
        if char1 and char2:
            char1.set_relationship(character2_name, attitude, description)
            char2.set_relationship(character1_name, attitude, description)
        else:
            raise ValueError("One or both characters not found.")

    def get_relationship(self, character1_name: str, character2_name: str) -> Optional[Relationship]:
        """Get the relationship between two characters."""
        char1 = self.get_character(character1_name)
        if char1:
            return char1.get_relationship(character2_name)
        return None

    def list_characters(self) -> List[str]:
        """List all character names in the game."""
        return list(self.characters.keys())

# Example usage
if __name__ == "__main__":
    # Create some characters
    alice = Character.generate("Alice", chr_class="Wizard")
    bob = Character.generate("Bob", chr_class="Fighter")
    eve = Character.generate("Eve", chr_class="Rogue")

    # Create a Characters instance
    game_characters = Characters()

    # Add characters to the game
    game_characters.add_character(alice)
    game_characters.add_character(bob)
    game_characters.add_character(eve)

    # Set relationships
    game_characters.set_relationship("Alice", "Bob", 75, "Close friends and adventuring companions")
    game_characters.set_relationship("Alice", "Eve", -30, "Distrusts Eve's motives")
    game_characters.set_relationship("Bob", "Eve", 20, "Casual acquaintances")

    # Print relationships
    for char_name in game_characters.list_characters():
        character = game_characters.get_character(char_name)
        print(f"\n{char_name}'s relationships:")
        for rel_name, relationship in character.relationships.items():
            print(f"  {rel_name}: Attitude {relationship.attitude}, {relationship.description}")

    # Get a specific relationship
    alice_bob_relationship = game_characters.get_relationship("Alice", "Bob")
    if alice_bob_relationship:
        print(f"\nAlice's relationship with Bob: {alice_bob_relationship.attitude}, {alice_bob_relationship.description}")

