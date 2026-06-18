"""
API endpoints for the tool proficiency system.

Allows querying a character's tool proficiencies and modifiers, inspecting
the class/background tool grants, setting chosen tool proficiencies, and
rolling tool checks.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.engine import tools
from app.engine.tools import TOOL_CATEGORIES, TOOL_REGISTRY
from app.models.database import get_db
from app.models.models import Character

router = APIRouter(prefix="/characters/{character_id}", tags=["tools"])


# --------------------------------------------------------------------------- #
# Request / Response schemas
# --------------------------------------------------------------------------- #

class ToolInfo(BaseModel):
    """One tool's resolved state for a character."""
    tool: str
    name: str
    category: str
    default_ability: str
    ability: str
    ability_score: int
    ability_modifier: int
    proficient: bool
    proficiency_bonus: int  # 0 or pb
    modifier: int  # total tool modifier


class ToolsResponse(BaseModel):
    """All tools for a character with resolved modifiers, grouped by category."""
    character_id: int
    proficiencies: list[str]
    tools_by_category: dict[str, list[ToolInfo]]


class ToolCandidatesResponse(BaseModel):
    """The tool grants a character's class/background provide."""
    character_id: int
    class_grants: list[dict]   # [{class, fixed, choice}]
    background_grants: dict     # {fixed, choice}
    current_proficiencies: list[str]


class SetToolsRequest(BaseModel):
    """Set a character's chosen tool proficiencies.

    The list is the *full* set of chosen tool proficiencies. Fixed tools
    granted automatically by class/background are always included on top.
    """
    tools: list[str] = Field(..., description="Tool ids/names to be proficient in")


class ToolCheckRequest(BaseModel):
    """Roll a tool check."""
    tool: str = Field(..., description="Tool name/id (e.g., 'thieves_tools')")
    dc: int = Field(..., ge=1, le=40, description="Difficulty Class")
    ability: str | None = Field(default=None, description="Override the check ability")
    advantage: bool = Field(default=False)
    disadvantage: bool = Field(default=False)
    conditions: list[str] = Field(default_factory=list, description="Active conditions")


class ToolCheckResponse(BaseModel):
    tool: str
    name: str
    category: str
    ability: str
    roll: str
    rolls: list[int]
    modifier: int
    total: int
    success: bool
    dc: int
    proficient: bool
    advantage: bool
    disadvantage: bool
    description: str


class ToolRegistryResponse(BaseModel):
    """The static tool registry (category -> tools)."""
    categories: list[str]
    tools_by_category: dict[str, list[dict]]  # [{id, name, ability, description}]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _get_character_or_404(character_id: int, db: Session) -> Character:
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


def _build_tool_infos(character: Character, proficiencies: set[str]) -> dict[str, list[ToolInfo]]:
    infos: dict[str, list[ToolInfo]] = {cat: [] for cat in TOOL_CATEGORIES}
    for td in TOOL_REGISTRY.values():
        bd = tools.calculate_tool_breakdown(td.id, character, proficiencies=proficiencies)
        infos[td.category].append(ToolInfo(
            tool=bd["tool"],
            name=bd["name"],
            category=bd["category"],
            default_ability=bd["default_ability"],
            ability=bd["ability"],
            ability_score=bd["ability_score"],
            ability_modifier=bd["ability_modifier"],
            proficient=bd["proficient"],
            proficiency_bonus=bd["proficiency_bonus"],
            modifier=bd["modifier"],
        ))
    return infos


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("/tools", response_model=ToolsResponse)
def get_tools(character_id: int, db: Session = Depends(get_db)):
    """Get all tools for a character with resolved modifiers, grouped by category."""
    character = _get_character_or_404(character_id, db)
    profs = tools.get_all_tool_proficiencies(character)
    return ToolsResponse(
        character_id=character_id,
        proficiencies=sorted(profs),
        tools_by_category=_build_tool_infos(character, profs),
    )


@router.get("/tools/candidates", response_model=ToolCandidatesResponse)
def get_tool_candidates(character_id: int, db: Session = Depends(get_db)):
    """Get the tool grants provided by a character's class(es) and background."""
    character = _get_character_or_404(character_id, db)

    class_grants = []
    for cls_name in tools._iter_classes(character):
        grant = tools.get_class_tool_grants(cls_name)
        class_grants.append({
            "class": cls_name,
            "fixed": grant["fixed"],
            "choice": grant["choice"],
        })

    bg_grant = tools.get_background_tool_grants(character.background or "")

    return ToolCandidatesResponse(
        character_id=character_id,
        class_grants=class_grants,
        background_grants=bg_grant,
        current_proficiencies=sorted(tools.get_tool_proficiencies(character)),
    )


@router.post("/tools/proficiencies", response_model=ToolsResponse)
def set_tool_proficiencies(
    character_id: int,
    request: SetToolsRequest,
    db: Session = Depends(get_db),
):
    """Set a character's chosen tool proficiencies.

    Validates that each requested tool is a known tool, and that the number
    of *chosen* tools does not exceed the choice budget from the character's
    class(es) and background. Fixed tools are always granted in addition to
    the chosen ones and are merged back into the stored list.
    """
    character = _get_character_or_404(character_id, db)

    # Normalize + validate tool names.
    chosen: list[str] = []
    for raw in request.tools:
        try:
            chosen.append(tools.normalize_tool_id(raw))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown tool '{raw}'.",
            )
    chosen = list(dict.fromkeys(chosen))  # dedupe, preserve order

    # Compute the fixed tools + choice budget from class(es) + background.
    fixed: set[str] = set()
    total_choice_budget = 0
    for cls_name in tools._iter_classes(character):
        grant = tools.get_class_tool_grants(cls_name)
        fixed.update(grant["fixed"])
        if grant["choice"]:
            total_choice_budget += grant["choice"]["count"]
    bg_grant = tools.get_background_tool_grants(character.background or "")
    fixed.update(bg_grant["fixed"])
    if bg_grant["choice"]:
        total_choice_budget += bg_grant["choice"]["count"]

    # The player may only *choose* tools that aren't auto-fixed.
    player_choices = [t for t in chosen if t not in fixed]
    if len(player_choices) > total_choice_budget:
        raise HTTPException(
            status_code=400,
            detail=f"Too many tool choices ({len(player_choices)}). "
                   f"This character's class/background allows {total_choice_budget} "
                   f"player-chosen tool(s) on top of fixed grants.",
        )

    # Store the full proficiency list (fixed + chosen) so reads are consistent.
    full = sorted(set(chosen) | fixed)
    character.tool_proficiencies = json.dumps(full)
    db.commit()
    db.refresh(character)

    profs = tools.get_all_tool_proficiencies(character)
    return ToolsResponse(
        character_id=character_id,
        proficiencies=sorted(profs),
        tools_by_category=_build_tool_infos(character, profs),
    )


@router.post("/tools/check", response_model=ToolCheckResponse)
def roll_tool_check_endpoint(
    character_id: int,
    request: ToolCheckRequest,
    db: Session = Depends(get_db),
):
    """Roll a tool check for a character against a DC."""
    character = _get_character_or_404(character_id, db)

    try:
        tool_id = tools.normalize_tool_id(request.tool)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown tool '{request.tool}'.",
        )

    result = tools.roll_tool_check(
        tool_id=tool_id,
        character=character,
        dc=request.dc,
        ability=request.ability,
        advantage=request.advantage,
        disadvantage=request.disadvantage,
        conditions=request.conditions,
    )

    return ToolCheckResponse(
        tool=result.tool,
        name=result.name,
        category=result.category,
        ability=result.ability,
        roll=result.roll.description,
        rolls=result.roll.rolls,
        modifier=result.modifier,
        total=result.total,
        success=result.success,
        dc=result.dc,
        proficient=result.proficient,
        advantage=result.advantage,
        disadvantage=result.disadvantage,
        description=result.description,
    )


@router.get("/tools/registry", response_model=ToolRegistryResponse)
def get_tool_registry(character_id: int):
    """Return the static tool registry (does not require a character)."""
    by_cat: dict[str, list[dict]] = {cat: [] for cat in TOOL_CATEGORIES}
    for td in TOOL_REGISTRY.values():
        by_cat[td.category].append({
            "id": td.id,
            "name": td.name,
            "ability": td.ability,
            "description": td.description,
        })
    return ToolRegistryResponse(
        categories=list(TOOL_CATEGORIES),
        tools_by_category=by_cat,
    )
