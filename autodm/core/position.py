from pydantic import BaseModel
from scipy.spatial.distance import chebyshev
from typing import TYPE_CHECKING

def distance(pos1: 'Position', pos2: 'Position') -> int:
    return chebyshev(pos1.to_tuple(), pos2.to_tuple())

class Position(BaseModel):
    x: int
    y: int

    def to_tuple(self):
        return (self.x, self.y)
    
    def distance_to(self, other: 'Position') -> int:
        return distance(self, other)
    
    def __str__(self):
        return f"x={self.x}, y={self.y}"