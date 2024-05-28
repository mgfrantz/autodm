from .roll import Dice
from .llm import get_llm
from pydantic import BaseModel, Field
from llama_index.core.program import LLMTextCompletionProgram # type: ignore

CLASSES = ["wizard", "fighter"]
RACES = ["human", "elf", "dwarf"]


class Attributes(BaseModel):
    strength: int = Field(..., ge=1, le=20)
    dexterity: int = Field(..., ge=1, le=20)
    constitution: int = Field(..., ge=1, le=20)
    intelligence: int = Field(..., ge=1, le=20)
    wisdom: int = Field(..., ge=1, le=20)
    charisma: int = Field(..., ge=1, le=20)

    @classmethod
    def roll(cls):
        return cls(
            strength=Dice().roll(),
            dexterity=Dice().roll(),
            constitution=Dice().roll(),
            intelligence=Dice().roll(),
            wisdom=Dice().roll(),
            charisma=Dice().roll(),
        )

    def reroll(self):
        self.strength = Dice().roll()
        self.dexterity = Dice().roll()
        self.constitution = Dice().roll()
        self.intelligence = Dice().roll()
        self.wisdom = Dice().roll()
        self.charisma = Dice().roll()


class Character(BaseModel):
    chr_class: str = Field(
        "wizard", description=f"Character class. One of {', '.join(CLASSES)}"
    )
    chr_race: str = Field(
        "human", description=f"Character race. One of {', '.join(RACES)}"
    )
    name: str = Field(..., description="Character name")
    attributes: Attributes
    level: int = Field(default=0, ge=0, le=20, description="Character level")
    max_hp: int = Field(default=10, ge=10, description="Maximum hit points")
    hp: int = Field(default=10, ge=0, description="Current hit points")
    spells: list = Field(default=[], description="List of spells")
    equipment: list = Field(default=[], description="List of equipment")

    @classmethod
    def generate(cls, **kwargs):
        if "attributes" not in kwargs:
            kwargs["attributes"] = Attributes.roll()
        kwargs["max_hp"] = kwargs["attributes"].constitution + 10
        kwargs["hp"] = kwargs["max_hp"]
        kwgs = "\n".join([f"{k}: {v}" for k, v in kwargs.items()])
        pt = f"""\
Please generate a D&D character. Make sure the character has the following attributes, then generate the rest.
Do not add any spells or equipment.
Require attributes:
{kwgs}\
"""
        prog = LLMTextCompletionProgram.from_defaults(
            output_cls=Character, llm=get_llm(), prompt_template_str=pt
        )
        return prog()
