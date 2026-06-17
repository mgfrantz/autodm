"""
API endpoints for saving throws.

Allows querying character save proficiencies and rolling saving throws.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.engine import saving_throws
from app.engine.saving_throws import ABILITIES
from app.models.database import get_db
from app.models.models import Character


router = APIRouter(prefix="/characters/{character_id}", tags=["saving-throws"])


# --------------------------------------------------------------------------- #
# Request/Response schemas
# --------------------------------------------------------------------------- #

class SavingThrowProficienciesResponse(BaseModel):
    """Response with a character's saving throw proficiencies."""
    character_id: int
    proficiencies: list[str]  # List of abilities the character is proficient in
    bonus_by_ability: dict[str, int]  # Static bonus per ability (prof + mod)


class SavingThrowRollRequest(BaseModel):
    """Request to roll a saving throw."""
    ability: str = Field(..., description="Ability to save with (strength, dexterity, etc.)")
    dc: int = Field(..., ge=1, le=30, description="Difficulty Class")
    advantage: bool = Field(default=False, description="Roll with advantage")
    disadvantage: bool = Field(default=False, description="Roll with disadvantage")
    conditions: list[str] = Field(default_factory=list, description="Active conditions")


class SavingThrowRollResponse(BaseModel):
    """Response with the result of a saving throw."""
    ability: str
    roll: str  # Roll description
    rolls: list[int]  # Individual die rolls
    modifier: int
    total: int
    success: bool
    dc: int
    advantage: bool
    disadvantage: bool
    auto_failed: bool
    description: str


class SaveDCResponse(BaseModel):
    """Response with a calculated save DC."""
    spellcasting_ability: str
    dc: int
    ability_score: int
    ability_modifier: int
    proficiency_bonus: int
    breakdown: str


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("/saving-throws/proficiencies", response_model=SavingThrowProficienciesResponse)
def get_saving_throw_proficiencies(
    character_id: int,
    db: Session = Depends(get_db),
):
    """Get a character's saving throw proficiencies and bonuses."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    proficiencies = saving_throws.get_saving_throw_proficiencies(character)

    bonus_by_ability = {}
    for ability in ABILITIES:
        bonus = saving_throws.calculate_save_bonus(ability, character, proficiencies)
        bonus_by_ability[ability] = bonus

    return SavingThrowProficienciesResponse(
        character_id=character_id,
        proficiencies=sorted(proficiencies),
        bonus_by_ability=bonus_by_ability,
    )


@router.post("/saving-throws/roll", response_model=SavingThrowRollResponse)
def roll_saving_throw(
    character_id: int,
    request: SavingThrowRollRequest,
    db: Session = Depends(get_db),
):
    """Roll a saving throw for a character against a DC."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    ability = request.ability.lower()
    if ability not in ABILITIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ability '{ability}'. Must be one of: {', '.join(ABILITIES)}"
        )

    proficiencies = saving_throws.get_saving_throw_proficiencies(character)

    result = saving_throws.roll_saving_throw(
        ability=ability,
        character=character,
        dc=request.dc,
        advantage=request.advantage,
        disadvantage=request.disadvantage,
        conditions=request.conditions,
        proficiencies=proficiencies,
    )

    return SavingThrowRollResponse(
        ability=result.ability,
        roll=result.roll.description,
        rolls=result.roll.rolls,
        modifier=result.modifier,
        total=result.total,
        success=result.success,
        dc=result.dc,
        advantage=result.advantage,
        disadvantage=result.disadvantage,
        auto_failed=result.auto_failed,
        description=result.description,
    )


@router.get("/saving-throws/dc", response_model=SaveDCResponse)
def calculate_save_dc(
    character_id: int,
    spellcasting_ability: str,
    bonus: int = 0,
    db: Session = Depends(get_db),
):
    """Calculate a save DC for a character's spells/abilities."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    ability = spellcasting_ability.lower()
    if ability not in ABILITIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ability '{ability}'. Must be one of: {', '.join(ABILITIES)}"
        )

    dc = saving_throws.calculate_character_save_dc(
        character=character,
        spellcasting_ability=ability,
        bonus=bonus,
    )

    ability_score = saving_throws.get_ability_score(character, ability)
    ability_mod = saving_throws.ability_modifier(ability_score)
    prof_bon = saving_throws.proficiency_bonus(saving_throws.get_character_level(character))

    return SaveDCResponse(
        spellcasting_ability=ability,
        dc=dc,
        ability_score=ability_score,
        ability_modifier=ability_mod,
        proficiency_bonus=prof_bon,
        breakdown=f"8 + {prof_bon} (proficiency) + {ability_mod:+d} ({ability}) + {bonus:+d} (bonus) = {dc}",
    )