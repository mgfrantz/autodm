from enum import Enum
from pydantic import BaseModel, Field
import numpy as np

class DiceType(int, Enum):
    D4 = 4
    D6 = 6
    D8 = 8
    D10 = 10
    D12 = 12
    D20 = 20

class Dice(BaseModel):
    """
    Represents a dice with a specific type and count.

    Attributes:
        type (DiceType): The type of dice to roll.
        count (int): The number of dice to roll.
    """

    type: DiceType = Field(DiceType.D20, title="Dice Type", description="The type of dice to roll")
    count: int = Field(1, title="Dice Count", description="The number of dice to roll")

    def roll(self):
        """
        Rolls the dice and returns the sum of the rolled values.

        Returns:
            int: The sum of the rolled values.
        """
        return sum(np.random.randint(1, self.type.value + 1, self.count))

    def __str__(self):
        return f"{self.count}d{self.type.value}"

    def __repr__(self):
        return f"Dice(type={self.type}, count={self.count})"
    
class RollResult(Enum):
    CRITICAL_FAILURE = 1
    FAILURE = 2
    NEUTRAL = 10
    SUCCESS = 14
    CRITICAL_SUCCESS = 20
    HEROIC = 25
    LEGENDARY = 30