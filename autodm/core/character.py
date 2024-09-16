from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from .attributes import Attributes
from .skills import Skills
from .enums import CharacterState, CharacterClass, CharacterRace
from .position import Position
from ..items.equipment import EquipmentItem, ItemType
from ..spells.base_spell import Spell
from ..utils.llm import complete_pydantic, complete
from ..utils.dice import roll_attribute
from ..spells.defined_spells import fireball, magic_missile, shield, cure_wounds
import random

class Character(BaseModel):
    name: str = Field(..., description="The name of the character.")
    level: int = Field(..., description="The level of the character.")
    chr_class: CharacterClass = Field(..., description="The class of the character.")
    chr_race: CharacterRace = Field(..., description="The race of the character.")
    attributes: Attributes = Field(..., description="The attributes of the character.")
    skills: Skills = Field(..., description="The skills of the character.")
    max_hp: int = Field(..., description="The maximum hit points of the character.")
    current_hp: int = Field(..., description="The current hit points of the character.")
    armor_class: int = Field(..., description="The armor class of the character.")
    initiative: int = Field(..., description="The initiative of the character.")
    speed: int = Field(..., description="The speed of the character.")
    movement_remaining: int = Field(0, description="The remaining movement of the character for the current turn.")
    experience_points: int = Field(default=0, description="The experience points of the character.")
    proficiency_bonus: int = Field(default=2, description="The proficiency bonus of the character.")
    character_state: CharacterState = Field(default=CharacterState.ALIVE, description="The state of the character.")
    position: Position = Field(default_factory=lambda: Position(x=0, y=0), description="The position of the character.")
    inventory: List[EquipmentItem] = Field(default_factory=list, description="The inventory of the character.")
    equipped_items: Dict[str, List[EquipmentItem]] = Field(default_factory=dict, description="The equipped items of the character.")
    spells: List[Spell] = Field(default_factory=list, description="The spells of the character.")
    spell_slots: Dict[int, int] = Field(default_factory=dict, description="The spell slots of the character.")
    backstory: Optional[str] = Field(None, description="The backstory of the character.")

    def take_damage(self, damage: int):
        self.current_hp = max(0, self.current_hp - damage)
        if self.current_hp == 0:
            self.character_state = CharacterState.DEAD

    def heal(self, amount: int):
        self.current_hp = min(self.max_hp, self.current_hp + amount)
        if self.current_hp > 0:
            self.character_state = CharacterState.ALIVE

    def get_attack_bonus(self) -> int:
        # This is a simplified version. In a real game, this would depend on the weapon and other factors.
        return self.attributes.get_modifier('strength') + self.proficiency_bonus

    def get_damage_bonus(self) -> int:
        # This is a simplified version. In a real game, this would depend on the weapon and other factors.
        return self.attributes.get_modifier('strength')

    def get_equipped_weapons(self) -> List[EquipmentItem]:
        return self.equipped_items.get('weapon', [])

    def can_cast_spell(self, spell: Spell) -> bool:
        return self.spell_slots.get(spell.level, 0) > 0

    def cast_spell(self, spell: Spell):
        if self.can_cast_spell(spell):
            self.spell_slots[spell.level] -= 1
        else:
            raise ValueError(f"Cannot cast {spell.name}. No spell slots available.")

    def equip(self, item: EquipmentItem):
        """
        Equip an item to the character.

        Args:
            item (EquipmentItem): The item to equip.
        """
        if item.item_type == ItemType.WEAPON:
            self.equipped_items.setdefault('weapon', []).append(item)
        elif item.item_type == ItemType.ARMOR:
            self.equipped_items.setdefault('armor', []).append(item)
        else:
            raise ValueError(f"Cannot equip item of type {item.item_type}")

    @classmethod
    def generate(cls, name: Optional[str] = None, **kwargs) -> 'Character':
        """
        Generate a new Character instance with random attributes, race, and class.

        Args:
        name (str): The character's name.
        **kwargs: Additional arguments to pass to the Character constructor.

        Returns:
        Character: A new Character instance with randomly generated attributes.
        """
        attributes = Attributes(
            strength=roll_attribute(),
            dexterity=roll_attribute(),
            constitution=roll_attribute(),
            intelligence=roll_attribute(),
            wisdom=roll_attribute(),
            charisma=roll_attribute()
        )

        chr_race = kwargs.get('chr_race', random.choice(list(CharacterRace)))
        chr_class = kwargs.get('chr_class', random.choice(list(CharacterClass)))

        class Name(BaseModel):
            name: str

        if name is None:
            name = complete_pydantic(f"Generate a creative and on-character name for a D&D player with the race of {chr_race.value} and class of {chr_class.value}.", Name).name

        # Apply racial modifiers
        race_mods = {
            CharacterRace.HUMAN: {"all": 1},
            CharacterRace.ELF: {"dexterity": 2},
            CharacterRace.DWARF: {"constitution": 2},
            CharacterRace.HALFLING: {"dexterity": 2},
            CharacterRace.GNOME: {"intelligence": 2},
            CharacterRace.HALF_ELF: {"charisma": 2, "choice": 2},
            CharacterRace.HALF_ORC: {"strength": 2, "constitution": 1},
            CharacterRace.TIEFLING: {"intelligence": 1, "charisma": 2},
            CharacterRace.DRAGONBORN: {"strength": 2, "charisma": 1},
        }

        race_mod = race_mods[chr_race]
        for attr, mod in race_mod.items():
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

        hit_dice = {
            CharacterClass.BARBARIAN: "1d12",
            CharacterClass.FIGHTER: "1d10",
            CharacterClass.PALADIN: "1d10",
            CharacterClass.RANGER: "1d10",
            CharacterClass.BARD: "1d8",
            CharacterClass.CLERIC: "1d8",
            CharacterClass.DRUID: "1d8",
            CharacterClass.MONK: "1d8",
            CharacterClass.ROGUE: "1d8",
            CharacterClass.WARLOCK: "1d8",
            CharacterClass.SORCERER: "1d6",
            CharacterClass.WIZARD: "1d6",
        }[chr_class]

        max_hp = int(hit_dice.split('d')[1]) + attributes.get_modifier('constitution')

        default_spells = []
        if chr_class in [CharacterClass.WIZARD, CharacterClass.SORCERER]:
            default_spells.extend([fireball, magic_missile, shield])
        elif chr_class in [CharacterClass.CLERIC, CharacterClass.DRUID, CharacterClass.PALADIN]:
            default_spells.append(cure_wounds)

        # Initialize spell slots based on class and level
        spell_slots = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}
        if chr_class in [CharacterClass.WIZARD, CharacterClass.SORCERER, CharacterClass.BARD, CharacterClass.CLERIC, CharacterClass.DRUID]:
            if level >= 1:
                spell_slots[1] = 2
            if level >= 3:
                spell_slots[2] = 1
            if level >= 5:
                spell_slots[3] = 1
        elif chr_class in [CharacterClass.PALADIN, CharacterClass.RANGER]:
            if level >= 2:
                spell_slots[1] = 2
            if level >= 5:
                spell_slots[2] = 1

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
            CharacterClass.BARBARIAN: ["animal_handling", "athletics", "intimidation", "nature", "perception", "survival"],
            CharacterClass.BARD: ["acrobatics", "animal_handling", "arcana", "athletics", "deception", "history", "insight", "intimidation", "investigation", "medicine", "nature", "perception", "performance", "persuasion", "religion", "sleight_of_hand", "stealth", "survival"],
            CharacterClass.CLERIC: ["history", "insight", "medicine", "persuasion", "religion"],
            CharacterClass.DRUID: ["arcana", "animal_handling", "insight", "medicine", "nature", "perception", "religion", "survival"],
            CharacterClass.FIGHTER: ["acrobatics", "animal_handling", "athletics", "history", "insight", "intimidation", "perception", "survival"],
            CharacterClass.MONK: ["acrobatics", "athletics", "history", "insight", "religion", "stealth"],
            CharacterClass.PALADIN: ["athletics", "insight", "intimidation", "medicine", "persuasion", "religion"],
            CharacterClass.RANGER: ["animal_handling", "athletics", "insight", "investigation", "nature", "perception", "stealth", "survival"],
            CharacterClass.ROGUE: ["acrobatics", "athletics", "deception", "insight", "intimidation", "investigation", "perception", "performance", "persuasion", "sleight_of_hand", "stealth"],
            CharacterClass.SORCERER: ["arcana", "deception", "insight", "intimidation", "persuasion", "religion"],
            CharacterClass.WARLOCK: ["arcana", "deception", "history", "intimidation", "investigation", "nature", "religion"],
            CharacterClass.WIZARD: ["arcana", "history", "insight", "investigation", "medicine", "religion"]
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
            "movement_remaining": speed,  # Initialize movement_remaining to full speed
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
            character.spells.append(spell)

        # Generate backstory
        backstory_prompt = f"Generate a brief backstory for {character.name}, a level {character.level} {character.chr_race.value} {character.chr_class.value}. Consider their attributes: {character.attributes}"
        character.backstory = complete(backstory_prompt)

        return character

    class Config:
        arbitrary_types_allowed = True