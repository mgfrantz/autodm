from typing import List, Optional, Dict, Union, ClassVar
from pydantic import BaseModel, Field
import random
from .items import Item, WeaponAttack, EquipmentItem
from enum import Enum
from .spells import Spell
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
    spell_slots: Dict[int, int] = Field(default_factory=lambda: {1: 2, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0})

    class Config:
        arbitrary_types_allowed = True

    @property
    def hp(self) -> int:
        return self.current_hp

    @hp.setter
    def hp(self, value: int) -> None:
        self.current_hp = max(0, min(value, self.max_hp))
        self.check_death()

    skills: Dict[str, int] = {}
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
        Set the spell's level to the character's level, not exceeding the spell's base level.
        
        Args:
        spell (Spell): The spell to add.
        
        Returns:
        bool: True if the spell was added, False if the character already knew the spell.
        """
        if not any(existing_spell.name == spell.name for existing_spell in self.spells):
            spell_copy = copy.deepcopy(spell)  # Create a copy of the spell
            spell_copy.set_level(min(self.level, spell.base_level))
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
            from .spells import fireball
            default_spells.append(fireball)
        elif chr_class in ["Cleric", "Druid", "Paladin"]:
            from .spells import cure_wounds
            default_spells.append(cure_wounds)

        # Set up spell slots based on class and level
        spell_slots = {1: 2, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}
        if chr_class in ["Wizard", "Sorcerer", "Bard", "Cleric", "Druid"]:
            if level >= 3:
                spell_slots[2] = 2
            if level >= 5:
                spell_slots[3] = 2

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
            "skills": {},  # Skills can be added based on class and background
            "spells": [],  # Start with an empty spell list
            "spell_slots": spell_slots
        }

        # Update default_args with any additional kwargs
        default_args.update(kwargs)

        character = cls(**default_args)

        # Add default spells using the new add_spell method
        for spell in default_spells:
            character.add_spell(spell)

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

# Move this part inside the if __name__ == "__main__": block
if __name__ == "__main__":
    items = [
        EquipmentItem(name="Leather Armor", item_type="armor", effects={"armor_class": 14}, quantity=1, weight=10.0),
        EquipmentItem(name="Ring of Protection", item_type="ring", effects={"armor_class": 3}, quantity=1, weight=0.1),
        EquipmentItem(name="Longsword", item_type="weapon", effects={"damage": "1d8+2"}, quantity=1, weight=3.0),
    ]

    character = Character.generate("Elara Moonwhisper")
    print(character)
    print(f"Race: {character.chr_race}")
    print(f"Class: {character.chr_class}")
    print(f"Attributes: {character.attributes}")
    print(f"Hit Dice: {character.hit_dice}")
    print(f"Max HP: {character.max_hp}")
    print(f"Armor Class: {character.armor_class}")

    for item in items:
        character.add_to_inventory(item)

    character.equip_item(items[0])  # Leather Armor
    print(f"After equipping leather armor - Armor Class: {character.armor_class}")

    character.equip_item(items[1])  # Ring of Protection
    print(f"After equipng ring of protection - Armor Class: {character.armor_class}")

    character.unequip_item("ring")
    print(f"After unequipping ring of protection - Armor Class: {character.armor_class}")

    character.unequip_item("armor")
    print(f"After unequipping leather armor - Armor Class: {character.armor_class}")

    print(character)

