"""Map-related enumerations and constants."""
from __future__ import annotations
import enum


class SizeEnum(str, enum.Enum):
    """Creature sizes."""
    TINY = "Tiny"
    SMALL = "Small"
    MEDIUM = "Medium"
    LARGE = "Large"
    HUGE = "Huge"
    GARGANTUAN = "Gargantuan"


# Size-related constants
SIZE_SQUARES = {
    SizeEnum.TINY: 1,  # 1x1 square
    SizeEnum.SMALL: 1,  # 1x1 square
    SizeEnum.MEDIUM: 1,  # 1x1 square
    SizeEnum.LARGE: 4,  # 2x2 squares
    SizeEnum.HUGE: 9,  # 3x3 squares
    SizeEnum.GARGANTUAN: 16,  # 4x4 squares
}

CHARACTERS_PER_SQUARE = {
    SizeEnum.TINY: 4,
    SizeEnum.SMALL: 1,
    SizeEnum.MEDIUM: 1,
    SizeEnum.LARGE: 1/4,
    SizeEnum.HUGE: 1/9,
    SizeEnum.GARGANTUAN: 1/16,
}

# Movement constants
FEET_PER_SQUARE = 5  # Each square represents 5 feet

# Export all constants
__all__ = [
    'SizeEnum',
    'SIZE_SQUARES',
    'CHARACTERS_PER_SQUARE',
    'FEET_PER_SQUARE',
]