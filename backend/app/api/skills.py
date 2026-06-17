"""
API endpoints for the skill system.

Allows querying skill data, setting chosen proficiencies/expertise, rolling
skill checks, and reading passive scores.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.engine import skills
from app.engine.skills import ALL_SKILLS, SKILL_ABILITIES
from app.models.database import get_db
from app.models.models import Character

router = APIRouter(prefix="/characters/{character_id}", tags=["skills"])


# --------------------------------------------------------------------------- #
# Request / Response schemas
# --------------------------------------------------------------------------- #

class SkillInfo(BaseModel):
    """One skill's resolved state for a character."""
    skill: str
    ability: str
    ability_score: int
    ability_modifier: int
    proficient: bool
    expertise: bool
    proficiency_bonus: int  # 0, pb, or 2*pb
    modifier: int  # total skill modifier


class SkillsResponse(BaseModel):
    """All skills for a character with resolved modifiers."""
    character_id: int
    proficiencies: list[str]
    expertise: list[str]
    skills: list[SkillInfo]
    passive_scores: dict[str, int]


class SkillCandidatesResponse(BaseModel):
    """The skills a character may choose proficiency in, per class."""
    character_id: int
    class_choices: list[dict]  # [{class, count, candidates}]
    background_skills: list[str]
    current_proficiencies: list[str]


class SetSkillsRequest(BaseModel):
    """Set a character's chosen skill proficiencies."""
    skills: list[str] = Field(..., description="Skill names to be proficient in")


class SetExpertiseRequest(BaseModel):
    """Set a character's Expertise skills (Rogue/Bard)."""
    skills: list[str] = Field(..., description="Skill names to apply Expertise to")


class SkillCheckRequest(BaseModel):
    """Roll a skill check."""
    skill: str = Field(..., description="Skill name (e.g., 'stealth')")
    dc: int = Field(..., ge=1, le=40, description="Difficulty Class")
    advantage: bool = Field(default=False)
    disadvantage: bool = Field(default=False)
    conditions: list[str] = Field(default_factory=list, description="Active conditions")


class SkillCheckResponse(BaseModel):
    skill: str
    ability: str
    roll: str
    rolls: list[int]
    modifier: int
    total: int
    success: bool
    dc: int
    proficient: bool
    expertise: bool
    advantage: bool
    disadvantage: bool
    description: str


class PassiveScoresResponse(BaseModel):
    character_id: int
    perception: int
    investigation: int
    insight: int


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _get_character_or_404(character_id: int, db: Session) -> Character:
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


def _build_skill_infos(character: Character) -> list[SkillInfo]:
    profs = skills.get_all_skill_proficiencies(character)
    exp = skills.get_all_skill_expertise(character)
    infos: list[SkillInfo] = []
    for sk in ALL_SKILLS:
        bd = skills.calculate_skill_breakdown(sk, character, profs, exp)
        infos.append(SkillInfo(
            skill=sk,
            ability=bd["ability"],
            ability_score=bd["ability_score"],
            ability_modifier=bd["ability_modifier"],
            proficient=bd["proficient"],
            expertise=bd["expertise"],
            proficiency_bonus=bd["proficiency_bonus"],
            modifier=bd["modifier"],
        ))
    return infos


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("/skills", response_model=SkillsResponse)
def get_skills(character_id: int, db: Session = Depends(get_db)):
    """Get all skills for a character with resolved modifiers and passive scores."""
    character = _get_character_or_404(character_id, db)
    profs = sorted(skills.get_all_skill_proficiencies(character))
    exp = sorted(skills.get_all_skill_expertise(character))
    return SkillsResponse(
        character_id=character_id,
        proficiencies=profs,
        expertise=exp,
        skills=_build_skill_infos(character),
        passive_scores=skills.calculate_all_passive_scores(character),
    )


@router.get("/skills/candidates", response_model=SkillCandidatesResponse)
def get_skill_candidates(character_id: int, db: Session = Depends(get_db)):
    """Get the skills a character may choose proficiency in, per class + background."""
    character = _get_character_or_404(character_id, db)
    class_choices = []
    for cls_name in skills._iter_classes(character):
        info = skills.get_class_skill_info(cls_name)
        class_choices.append({
            "class": cls_name,
            "count": info["count"],
            "candidates": skills.get_class_skill_candidates(cls_name),
        })
    background_skills = skills.get_background_skills(character.background or "")
    return SkillCandidatesResponse(
        character_id=character_id,
        class_choices=class_choices,
        background_skills=background_skills,
        current_proficiencies=sorted(skills.get_skill_proficiencies(character)),
    )


@router.post("/skills/proficiencies", response_model=SkillsResponse)
def set_skill_proficiencies(
    character_id: int,
    request: SetSkillsRequest,
    db: Session = Depends(get_db),
):
    """Set a character's chosen skill proficiencies.

    Validates that each requested skill is a valid skill name and that the
    number chosen does not exceed the class + background budget.
    """
    character = _get_character_or_404(character_id, db)

    chosen = [s.lower() for s in request.skills]
    # Validate skill names
    for s in chosen:
        if s not in SKILL_ABILITIES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid skill '{s}'. Must be one of: {', '.join(ALL_SKILLS)}",
            )

    # Compute the budget: sum of class skill counts + background skills
    budget_skills = set()
    class_count = 0
    for cls_name in skills._iter_classes(character):
        budget_skills.update(skills.get_class_skill_candidates(cls_name))
        class_count += skills.get_class_skill_count(cls_name)
    bg_skills = set(skills.get_background_skills(character.background or ""))
    budget_skills.update(bg_skills)
    max_count = class_count + len(bg_skills)

    # Deduplicate the chosen list
    unique_chosen = list(dict.fromkeys(chosen))
    if len(unique_chosen) > max_count:
        raise HTTPException(
            status_code=400,
            detail=f"Too many skills chosen ({len(unique_chosen)}). "
                   f"This character's class/background allows up to {max_count}.",
        )

    # Validate each chosen skill is in the allowed candidate set
    invalid = [s for s in unique_chosen if s not in budget_skills and not (
        skills.get_class_skill_info(skills._iter_classes(character)[0] if skills._iter_classes(character) else "")["skills"] == "any"
    )]
    # If any class is "any" (Bard), all skills are allowed
    has_any_class = any(
        skills.get_class_skill_info(c)["skills"] == "any"
        for c in skills._iter_classes(character)
    )
    if invalid and not has_any_class:
        raise HTTPException(
            status_code=400,
            detail=f"Skills not in this class/background's list: {', '.join(invalid)}.",
        )

    character.skill_proficiencies = json.dumps(unique_chosen)
    db.commit()
    db.refresh(character)

    profs = sorted(skills.get_all_skill_proficiencies(character))
    exp = sorted(skills.get_all_skill_expertise(character))
    return SkillsResponse(
        character_id=character_id,
        proficiencies=profs,
        expertise=exp,
        skills=_build_skill_infos(character),
        passive_scores=skills.calculate_all_passive_scores(character),
    )


@router.post("/skills/expertise", response_model=SkillsResponse)
def set_skill_expertise(
    character_id: int,
    request: SetExpertiseRequest,
    db: Session = Depends(get_db),
):
    """Set a character's Expertise skills (Rogue/Bard feature).

    Validates that the character is eligible for Expertise (Rogue/Bard at the
    right levels) and that the number chosen does not exceed their slots.
    """
    character = _get_character_or_404(character_id, db)

    chosen = [s.lower() for s in request.skills]
    for s in chosen:
        if s not in SKILL_ABILITIES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid skill '{s}'. Must be one of: {', '.join(ALL_SKILLS)}",
            )

    classes_dict = character.classes_dict
    max_slots = skills.get_multiclass_expertise_slots(classes_dict)
    unique_chosen = list(dict.fromkeys(chosen))
    if len(unique_chosen) > max_slots:
        raise HTTPException(
            status_code=400,
            detail=f"Too many Expertise skills ({len(unique_chosen)}). "
                   f"This character has {max_slots} Expertise slot(s).",
        )

    # Expertise requires proficiency in the skill first
    current_profs = skills.get_skill_proficiencies(character)
    # Merge background + chosen proficiencies
    all_profs = skills.get_all_skill_proficiencies(character)
    not_proficient = [s for s in unique_chosen if s not in all_profs]
    if not_proficient:
        raise HTTPException(
            status_code=400,
            detail=f"Expertise requires proficiency first. Not proficient in: "
                   f"{', '.join(not_proficient)}.",
        )

    if max_slots <= 0:
        raise HTTPException(
            status_code=400,
            detail="This character's class/level does not grant Expertise.",
        )

    character.skill_expertise = json.dumps(unique_chosen)
    db.commit()
    db.refresh(character)

    profs = sorted(skills.get_all_skill_proficiencies(character))
    exp = sorted(skills.get_all_skill_expertise(character))
    return SkillsResponse(
        character_id=character_id,
        proficiencies=profs,
        expertise=exp,
        skills=_build_skill_infos(character),
        passive_scores=skills.calculate_all_passive_scores(character),
    )


@router.post("/skills/check", response_model=SkillCheckResponse)
def roll_skill_check(
    character_id: int,
    request: SkillCheckRequest,
    db: Session = Depends(get_db),
):
    """Roll a skill check for a character against a DC."""
    character = _get_character_or_404(character_id, db)

    skill = request.skill.lower()
    if skill not in SKILL_ABILITIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid skill '{skill}'. Must be one of: {', '.join(ALL_SKILLS)}",
        )

    result = skills.roll_skill_check(
        skill=skill,
        character=character,
        dc=request.dc,
        advantage=request.advantage,
        disadvantage=request.disadvantage,
        conditions=request.conditions,
    )

    return SkillCheckResponse(
        skill=result.skill,
        ability=result.ability,
        roll=result.roll.description,
        rolls=result.roll.rolls,
        modifier=result.modifier,
        total=result.total,
        success=result.success,
        dc=result.dc,
        proficient=result.proficient,
        expertise=result.expertise,
        advantage=result.advantage,
        disadvantage=result.disadvantage,
        description=result.description,
    )


@router.get("/skills/passive", response_model=PassiveScoresResponse)
def get_passive_scores(character_id: int, db: Session = Depends(get_db)):
    """Get a character's passive Perception, Investigation, and Insight scores."""
    character = _get_character_or_404(character_id, db)
    scores = skills.calculate_all_passive_scores(character)
    return PassiveScoresResponse(
        character_id=character_id,
        perception=scores["perception"],
        investigation=scores["investigation"],
        insight=scores["insight"],
    )
