"""
Encounter Difficulty API — provides CR/XP balancing tools.

Exposes the encounters engine via REST endpoints for:
- Calculating encounter difficulty
- Getting encounter budgets
- Listing enemy templates
- Building balanced encounters
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.engine.encounters import (
    cr_to_xp,
    calculate_party_xp_budget,
    calculate_encounter_difficulty,
    build_encounter_budget,
    get_enemy_template,
    list_enemy_templates,
    get_enemies_by_cr,
    EncounterDifficulty,
    EncounterBudget,
    EnemyTemplate,
)

router = APIRouter()


class PartyInfo(BaseModel):
    """Information about the party."""
    levels: List[int]  # Each party member's level


class EncounterAnalysisRequest(BaseModel):
    """Request to analyze an encounter's difficulty."""
    enemies: List[dict]  # Each enemy has 'cr' and optionally 'name'
    party_levels: List[int]
    target_difficulty: str = "medium"


class BudgetRequest(BaseModel):
    """Request to get an encounter budget."""
    party_levels: List[int]
    difficulty: str = "medium"


@router.get("/cr-to-xp/{cr}")
def convert_cr_to_xp(cr: float):
    """Convert Challenge Rating to XP value."""
    xp = cr_to_xp(cr)
    return {"cr": cr, "xp": xp}


@router.get("/xp-budget")
def get_xp_budget(
    party_levels: str,  # Comma-separated levels
    difficulty: str = "medium"
):
    """Calculate XP budget for a party at a given difficulty."""
    try:
        levels = [int(l.strip()) for l in party_levels.split(",")]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid party levels format")
    
    if difficulty not in ["easy", "medium", "hard", "deadly"]:
        raise HTTPException(status_code=400, detail="Invalid difficulty")
    
    budget = calculate_party_xp_budget(levels, difficulty)
    return {
        "party_levels": levels,
        "difficulty": difficulty,
        "budget": budget,
    }


@router.post("/analyze")
def analyze_encounter(request: EncounterAnalysisRequest):
    """Analyze the difficulty of a proposed encounter.
    
    Takes a list of enemies (with CRs) and party levels, then calculates
    the encounter difficulty accounting for group multipliers.
    """
    if request.target_difficulty not in ["easy", "medium", "hard", "deadly"]:
        raise HTTPException(status_code=400, detail="Invalid difficulty")
    
    difficulty = calculate_encounter_difficulty(
        enemies=request.enemies,
        party_levels=request.party_levels,
        target_difficulty=request.target_difficulty,
    )
    
    return difficulty.to_dict()


@router.post("/budget")
def get_encounter_budget(request: BudgetRequest):
    """Get encounter budget with recommendations for enemy counts.
    
    Returns the XP budget for a party at each difficulty level and
    recommendations for how many enemies of each CR fit each budget.
    """
    if request.difficulty not in ["easy", "medium", "hard", "deadly"]:
        raise HTTPException(status_code=400, detail="Invalid difficulty")
    
    budget = build_encounter_budget(
        party_levels=request.party_levels,
        difficulty=request.difficulty,
    )
    
    return budget.to_dict()


@router.get("/enemies/templates")
def list_templates():
    """List all available enemy templates."""
    templates = list_enemy_templates()
    return {"templates": templates}


@router.get("/enemies/templates/{name}")
def get_template(name: str):
    """Get a specific enemy template by name."""
    template = get_enemy_template(name)
    if not template:
        raise HTTPException(status_code=404, detail=f"Enemy template '{name}' not found")
    return template.to_dict()


@router.get("/enemies/by-cr/{cr}")
def list_enemies_by_cr(cr: float):
    """List all enemy templates of a specific CR."""
    enemies = get_enemies_by_cr(cr)
    return {
        "cr": cr,
        "xp": cr_to_xp(cr),
        "enemies": [e.to_dict() for e in enemies],
    }


@router.get("/enemies/appropriate/{party_level}")
def list_appropriate_enemies(party_level: int):
    """List enemy templates appropriate for a party of a given level.
    
    Returns enemies within ±2 CR of the party level, which is a reasonable
    range for balanced encounters.
    """
    min_cr = max(0, party_level - 3)
    max_cr = min(party_level + 2, 8)  # Cap at CR 8 for reasonable variety
    
    all_enemies = list_enemy_templates()
    appropriate = []
    
    for name in all_enemies:
        template = get_enemy_template(name)
        if template and min_cr <= template.cr <= max_cr:
            appropriate.append(template.to_dict())
    
    # Sort by CR
    appropriate.sort(key=lambda e: e["cr"])
    
    return {
        "party_level": party_level,
        "cr_range": f"{min_cr} to {max_cr}",
        "enemies": appropriate,
    }