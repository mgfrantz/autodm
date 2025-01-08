from __future__ import annotations
from typing import Optional, Union
import random

from pydantic import BaseModel, Field, validator

from .enums import AbilityEnum
from ..character.models import Character, Skill, SavingThrow


class Roll(BaseModel):
    """Represents a generic die roll (e.g., 1d20, 2d6)."""
    num_dice: int = Field(..., ge=1)
    die_size: int = Field(..., ge=1)
    bonus: int = 0

    def roll(self) -> int:
        """Simulates rolling the dice and returns the total."""
        total = 0
        for _ in range(self.num_dice):
            total += random.randint(1, self.die_size)
        return total + self.bonus


class Check(BaseModel):
    """Represents an ability check, skill check, or saving throw."""
    character: Character
    roll: Roll = Field(default_factory=lambda: Roll(num_dice=1, die_size=20))
    advantage: bool = False
    disadvantage: bool = False
    target: Union[Skill, SavingThrow, AbilityEnum]
    dc: Optional[int] = Field(None, description="The Difficulty Class (if applicable).")

    @validator("disadvantage", always=True)
    def check_advantage_disadvantage(cls, v, values):
        """Ensures advantage and disadvantage are mutually exclusive."""
        if v and values.get("advantage"):
            raise ValueError("Cannot have both advantage and disadvantage.")
        return v

    def resolve(self) -> bool:
        """Resolves the check and determines success or failure."""
        if isinstance(self.target, Skill):
            modifier = self.character.get_skill_modifier(self.target)
        elif isinstance(self.target, SavingThrow):
            modifier = self.character.get_saving_throw_modifier(self.target)
        elif isinstance(self.target, AbilityEnum):
            modifier = self.character.get_ability_modifier(self.target)
        else:
            raise ValueError("Invalid target for check.")

        self.roll.bonus = modifier

        if self.advantage:
            result = max(self.roll.roll(), self.roll.roll())
        elif self.disadvantage:
            result = min(self.roll.roll(), self.roll.roll())
        else:
            result = self.roll.roll()

        if self.dc is not None:
            return result >= self.dc
        else:
            return result  # Return the raw result if no DC is set 