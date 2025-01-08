from __future__ import annotations
from typing import List, Optional, Dict
import random

from pydantic import BaseModel, Field, validator

from ..gameplay.enums import (
    AbilityEnum,
    SkillEnum,
    DamageTypeEnum,
    ConditionEnum,
    CharacterClassEnum,
    HitDiceType,
)


class AbilityScore(BaseModel):
    """Represents a single ability score."""
    ability: AbilityEnum
    value: int = Field(..., ge=1, le=30, description="The ability score value (1-30).")
    modifier: int = Field(..., description="The calculated ability modifier.")

    @validator("modifier", always=True)
    def calculate_modifier(cls, v, values):
        """Calculates the modifier based on the score."""
        if 'value' in values:
            return (values['value'] - 10) // 2
        return v


class Skill(BaseModel):
    """Represents a skill check."""
    skill: SkillEnum
    is_proficient: bool = False

    def get_skill_ability(self) -> AbilityEnum:
        """Determines the ability associated with a skill."""
        skill_ability_map = {
            SkillEnum.ATHLETICS: AbilityEnum.STRENGTH,
            SkillEnum.ACROBATICS: AbilityEnum.DEXTERITY,
            SkillEnum.SLEIGHT_OF_HAND: AbilityEnum.DEXTERITY,
            SkillEnum.STEALTH: AbilityEnum.DEXTERITY,
            SkillEnum.ARCANA: AbilityEnum.INTELLIGENCE,
            SkillEnum.HISTORY: AbilityEnum.INTELLIGENCE,
            SkillEnum.INVESTIGATION: AbilityEnum.INTELLIGENCE,
            SkillEnum.NATURE: AbilityEnum.INTELLIGENCE,
            SkillEnum.RELIGION: AbilityEnum.INTELLIGENCE,
            SkillEnum.ANIMAL_HANDLING: AbilityEnum.WISDOM,
            SkillEnum.INSIGHT: AbilityEnum.WISDOM,
            SkillEnum.MEDICINE: AbilityEnum.WISDOM,
            SkillEnum.PERCEPTION: AbilityEnum.WISDOM,
            SkillEnum.SURVIVAL: AbilityEnum.WISDOM,
            SkillEnum.DECEPTION: AbilityEnum.CHARISMA,
            SkillEnum.INTIMIDATION: AbilityEnum.CHARISMA,
            SkillEnum.PERFORMANCE: AbilityEnum.CHARISMA,
            SkillEnum.PERSUASION: AbilityEnum.CHARISMA,
        }
        return skill_ability_map[self.skill]


class SavingThrow(BaseModel):
    """Represents a saving throw."""
    ability: AbilityEnum
    is_proficient: bool = False


class Attack(BaseModel):
    """Represents an attack roll."""
    name: str
    attack_bonus: int
    damage_dice: str
    damage_bonus: int
    damage_type: DamageTypeEnum


class Armor(BaseModel):
    """Represents armor being worn."""
    name: str
    armor_class: int
    has_stealth_disadvantage: bool


class CharacterClass(BaseModel):
    """Represents a character class and its features."""
    name: CharacterClassEnum
    level: int
    hit_dice: HitDiceType
    armor_proficiencies: List[str]
    weapon_proficiencies: List[str]
    saving_throw_proficiencies: List[AbilityEnum]
    starting_skills: List[SkillEnum]
    num_skills: int  # Number of skills to choose from starting_skills
    equipment: List[str]
    features: Dict[int, str]  # Key: level, Value: feature description

    def choose_skills(self, selected_skills: List[SkillEnum]) -> List[Skill]:
        if len(selected_skills) != self.num_skills:
            raise ValueError(f"Must select exactly {self.num_skills} skills for {self.name}.")
        
        for skill in selected_skills:
            if skill not in self.starting_skills:
                raise ValueError(f"Invalid skill choice for {self.name}: {skill}.")

        return [Skill(skill=skill, is_proficient=True) for skill in selected_skills]


class Character(BaseModel):
    """The main character class."""
    name: str
    level: int = Field(1, ge=1, le=20)
    ability_scores: List[AbilityScore] = Field(..., min_items=6, max_items=6)
    proficiency_bonus: int = Field(..., description="Calculated from level.")
    skills: List[Skill] = Field(default_factory=list)
    saving_throws: List[SavingThrow] = Field(default_factory=list)
    armor_class: int = 10
    equipped_armor: Optional[Armor] = None
    hit_points: int
    max_hit_points: int
    conditions: List[ConditionEnum] = Field(default_factory=list)
    attacks: List[Attack] = Field(default_factory=list)
    speed: int = 30
    character_class: Optional[CharacterClass] = None

    @validator("proficiency_bonus", always=True)
    def calculate_proficiency_bonus(cls, v, values):
        """Calculates proficiency bonus based on level."""
        if 'level' in values:
            return (values['level'] - 1) // 4 + 2
        return v

    @validator('ability_scores')
    def validate_ability_scores_unique(cls, v):
        abilities = [score.ability for score in v]
        if len(set(abilities)) != len(abilities):
            raise ValueError("Ability scores must be unique.")
        return v

    @validator('skills')
    def validate_skills_unique(cls, v):
        skills = [skill.skill for skill in v]
        if len(set(skills)) != len(skills):
            raise ValueError("Skills must be unique.")
        return v

    @validator('saving_throws')
    def validate_saving_throws_unique(cls, v):
        abilities = [st.ability for st in v]
        if len(set(abilities)) != len(abilities):
            raise ValueError("Saving throw abilities must be unique.")
        return v

    def get_ability_modifier(self, ability: AbilityEnum) -> int:
        """Get the modifier for a specific ability."""
        for score in self.ability_scores:
            if score.ability == ability:
                return score.modifier
        raise ValueError(f"Ability score not found: {ability}")

    def get_skill_modifier(self, skill_check: Skill) -> int:
        """Calculates the modifier for a skill check."""
        ability = skill_check.get_skill_ability()
        modifier = self.get_ability_modifier(ability)

        if skill_check.is_proficient:
            modifier += self.proficiency_bonus

        return modifier

    def get_saving_throw_modifier(self, saving_throw: SavingThrow) -> int:
        """Calculates the modifier for a saving throw."""
        modifier = self.get_ability_modifier(saving_throw.ability)
        if saving_throw.is_proficient:
            modifier += self.proficiency_bonus
        return modifier

    @validator("armor_class", always=True)
    def calculate_armor_class(cls, v, values):
        """Calculates AC based on equipped armor and Dexterity."""
        dex_modifier = 0
        if 'ability_scores' in values:
            for score in values['ability_scores']:
                if score.ability == AbilityEnum.DEXTERITY:
                    dex_modifier = score.modifier
                    break

        if 'equipped_armor' in values and values['equipped_armor'] is not None:
            return values['equipped_armor'].armor_class + dex_modifier
        else:
            return 10 + dex_modifier  # Base AC

    def level_up(self):
        """Increases the character's level and updates relevant attributes."""
        if self.level < 20:
            self.level += 1
            self.proficiency_bonus = (self.level - 1) // 4 + 2
            self.update_hit_points_on_level_up()

            # Add new features based on class and level
            if self.character_class:
                new_features = self.character_class.features.get(self.level)
                if new_features:
                    # Logic to handle adding new features to the character
                    print(f"New features gained at level {self.level}: {new_features}")

    def update_hit_points_on_level_up(self):
        """Updates character's hit points when leveling up."""
        if self.character_class:
            constitution_modifier = self.get_ability_modifier(AbilityEnum.CONSTITUTION)
            hit_dice_value = int(self.character_class.hit_dice.value[1:])  # Extract number from 'dX'
            new_hit_points = random.randint(1, hit_dice_value) + constitution_modifier
            self.max_hit_points += max(new_hit_points, 1)  # Ensure at least 1 HP increase
            self.hit_points = self.max_hit_points

            print(f"Hit points increased by {new_hit_points} to {self.hit_points}") 