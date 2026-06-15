"""
Dice rolling engine — implements the d20 system.
"""
import random
from dataclasses import dataclass


@dataclass
class RollResult:
    """Result of a dice roll."""
    rolls: list[int]
    modifier: int
    total: int
    description: str

    def __str__(self) -> str:
        roll_str = " + ".join(str(r) for r in self.rolls)
        if self.modifier:
            sign = "+" if self.modifier > 0 else ""
            return f"{roll_str} {sign}{self.modifier} = {self.total}"
        return f"{roll_str} = {self.total}"


def roll_die(sides: int = 20) -> int:
    """Roll a single die."""
    return random.randint(1, sides)


def roll_dice(count: int, sides: int, modifier: int = 0) -> RollResult:
    """Roll multiple dice and add a modifier."""
    rolls = [roll_die(sides) for _ in range(count)]
    total = sum(rolls) + modifier
    return RollResult(
        rolls=rolls,
        modifier=modifier,
        total=total,
        description=f"{count}d{sides}{'+' if modifier >= 0 else ''}{modifier}",
    )


def roll_d20(modifier: int = 0, advantage: bool = False, disadvantage: bool = False) -> RollResult:
    """Roll a d20 with optional advantage/disadvantage."""
    if advantage and disadvantage:
        # Both cancel out — straight roll
        advantage = False
        disadvantage = False

    if advantage:
        r1, r2 = roll_die(20), roll_die(20)
        result = max(r1, r2)
        return RollResult(
            rolls=[r1, r2],
            modifier=modifier,
            total=result + modifier,
            description=f"d20(advantage) {modifier:+d}",
        )
    elif disadvantage:
        r1, r2 = roll_die(20), roll_die(20)
        result = min(r1, r2)
        return RollResult(
            rolls=[r1, r2],
            modifier=modifier,
            total=result + modifier,
            description=f"d20(disadvantage) {modifier:+d}",
        )
    else:
        result = roll_die(20)
        return RollResult(
            rolls=[result],
            modifier=modifier,
            total=result + modifier,
            description=f"d20 {modifier:+d}",
        )


def ability_modifier(score: int) -> int:
    """Calculate ability modifier from score (DnD 5e formula)."""
    return (score - 10) // 2


def proficiency_bonus(level: int) -> int:
    """Calculate proficiency bonus from level."""
    return (level - 1) // 4 + 2
