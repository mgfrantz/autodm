from pydantic import BaseModel

class Attributes(BaseModel):
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int

    def get_modifier(self, attribute: str) -> int:
        value = getattr(self, attribute)
        return (value - 10) // 2