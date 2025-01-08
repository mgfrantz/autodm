"""
Core mechanics module for the D&D game system.
This module re-exports all the important classes and enums from the submodules.
"""

from .enums import (
    AbilityEnum,
    SkillEnum,
    DamageTypeEnum,
    ConditionEnum,
    CharacterClassEnum,
    HitDiceType,
)

from .dice import Roll, Check
from .combat import Round, Combat, Game
from ..character.models import (
    AbilityScore,
    Skill,
    SavingThrow,
    Attack,
    Armor,
    CharacterClass,
    Character,
)

__all__ = [
    # Enums
    'AbilityEnum',
    'SkillEnum',
    'DamageTypeEnum',
    'ConditionEnum',
    'CharacterClassEnum',
    'HitDiceType',
    # Dice mechanics
    'Roll',
    'Check',
    # Combat mechanics
    'Round',
    'Combat',
    'Game',
    # Character models
    'AbilityScore',
    'Skill',
    'SavingThrow',
    'Attack',
    'Armor',
    'CharacterClass',
    'Character',
]