from typing import List, Optional, Dict, Union, ClassVar
from pydantic import BaseModel, Field
import random
from .items import Item, WeaponAttack, EquipmentItem

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
    player_name: str
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
    hp: int
    hit_dice: str
    skills: Dict[str, int] = {}
    spells: List[str] = []
    equipped_items: Dict[str, Optional[EquipmentItem]] = Field(default_factory=lambda: {
        "weapon": None,
        "armor": None,
        "accessory": None
    })
    inventory: List[EquipmentItem] = Field(default_factory=list)

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

    @classmethod
    def generate(cls, name: str, player_name: str) -> 'Character':
        """
        Generate a new Character instance with random attributes, race, and class.

        Args:
        name (str): The character's name.
        player_name (str): The player's name.

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

        chr_race = random.choice(list(cls.RACES.keys()))
        chr_class = random.choice(list(cls.CLASSES.keys()))

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

        level = 1
        proficiency_bonus = 2
        armor_class = 10 + attributes.get_modifier('dexterity')
        initiative = attributes.get_modifier('dexterity')
        speed = 30  # Default speed, can be adjusted based on race
        hit_dice = cls.CLASSES[chr_class]["hit_dice"]
        max_hp = int(hit_dice.split('d')[1]) + attributes.get_modifier('constitution')

        return cls(
            name=name,
            player_name=player_name,
            chr_class=chr_class,
            level=level,
            chr_race=chr_race,
            background=random.choice(["Acolyte", "Criminal", "Folk Hero", "Noble", "Sage", "Soldier"]),
            alignment=random.choice(["Lawful Good", "Neutral Good", "Chaotic Good", "Lawful Neutral", "True Neutral", "Chaotic Neutral", "Lawful Evil", "Neutral Evil", "Chaotic Evil"]),
            experience_points=0,
            attributes=attributes,
            proficiency_bonus=proficiency_bonus,
            armor_class=armor_class,
            initiative=initiative,
            speed=speed,
            max_hp=max_hp,
            hp=max_hp,
            hit_dice=hit_dice,
            skills={},  # Skills can be added based on class and background
            spells=[]  # Spells can be added based on class and level
        )

    def equip_item(self, item: EquipmentItem) -> None:
        """
        Equip an item to the character.

        Args:
            item (EquipmentItem): The item to equip.

        Raises:
            ValueError: If the item is not equippable.
        """
        if item.item_type.lower() in ['weapon', 'armor', 'shield', 'ring']:
            slot = item.item_type.lower()
            if slot == 'shield':
                slot = 'armor'  # Shields go in the armor slot
            self.equipped_items[slot] = item
            print(f"Equipped: {item.name}")
            self.calculate_armor_class()
        else:
            raise ValueError(f"{item.name} is not equippable.")

    def calculate_armor_class(self):
        """
        Calculate the character's armor class based on equipped items and dexterity.
        """
        dex_modifier = self.attributes.get_modifier('dexterity')
        base_ac = 10 + dex_modifier  # Start with base AC

        armor = self.equipped_items.get('armor')
        if armor and 'armor_class' in armor.effects:
            if isinstance(armor.effects['armor_class'], int):
                base_ac = max(base_ac, armor.effects['armor_class'] + dex_modifier)
            else:
                # If it's a string (like "11 + Dex modifier"), we'll need to parse it
                armor_base = int(armor.effects['armor_class'].split()[0])
                base_ac = max(base_ac, armor_base + dex_modifier)

        # Add AC bonuses from other equipped items
        for item in self.equipped_items.values():
            if item and item != armor and 'armor_class' in item.effects:
                if isinstance(item.effects['armor_class'], int):
                    base_ac += item.effects['armor_class']

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
            self.equipped_items[item_type.lower()] = None
            
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

    def __str__(self):
        equipped_items_str = ", ".join([f"{slot}: {item}" for slot, item in self.equipped_items.items() if item])
        return (f"{self.name}, Level {self.level} {self.chr_race} {self.chr_class}\n"
                f"Attributes:\n{self.attributes}\n"
                f"Armor Class: {self.armor_class}\n"
                f"Hit Points: {self.hp}/{self.max_hp}\n"
                f"Equipped: {equipped_items_str}")

# Move this part inside the if __name__ == "__main__": block
if __name__ == "__main__":
    items = [
        EquipmentItem(name="Leather Armor", item_type="armor", effects={"armor_class": 14}, quantity=1, weight=10.0),
        EquipmentItem(name="Ring of Protection", item_type="ring", effects={"armor_class": 3}, quantity=1, weight=0.1),
        EquipmentItem(name="Longsword", item_type="weapon", effects={"damage": "1d8+2"}, quantity=1, weight=3.0),
    ]

    character = Character.generate("Elara Moonwhisper", "Alice")
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
    print(f"After equipping ring of protection - Armor Class: {character.armor_class}")

    character.unequip_item("ring")
    print(f"After unequipping ring of protection - Armor Class: {character.armor_class}")

    character.unequip_item("armor")
    print(f"After unequipping leather armor - Armor Class: {character.armor_class}")

    print(character)

