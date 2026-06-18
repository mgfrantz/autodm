"""
Background system API — inspect backgrounds and apply them to characters.

Backgrounds are the third pillar of DnD 5e character creation (with race and
class). This API exposes the canonical background registry and lets a client
resolve a character's background (feature, skills, tools, languages, and
starting equipment) and optionally apply a background to a character (setting
``Character.background`` and granting the starting equipment + gold pouch).

Routes (mounted under ``/api``):

- ``GET  /backgrounds``                       — list all backgrounds (summary)
- ``GET  /backgrounds/{name}``                — full background detail
- ``GET  /characters/{character_id}/background`` — the character's background
- ``POST /characters/{character_id}/background`` — set/change a background
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.engine import backgrounds as bg_engine
from app.engine.backgrounds import Background
from app.engine.inventory import Item, Rarity
from app.models.database import get_db
from app.models.models import Character
from app.api.inventory import _load_inventory, _save_inventory

router = APIRouter()


# --------------------------------------------------------------------------- #
# Response schemas
# --------------------------------------------------------------------------- #

class BackgroundFeatureResponse(BaseModel):
    name: str
    description: str


class EquipmentItemResponse(BaseModel):
    name: str
    item_type: str
    description: str
    rarity: str
    value: int
    weight: float
    quantity: int

    @classmethod
    def from_item(cls, item: Item) -> "EquipmentItemResponse":
        return cls(
            name=item.name,
            item_type=item.item_type.value if hasattr(item.item_type, "value") else str(item.item_type),
            description=item.description,
            rarity=item.rarity.value if hasattr(item.rarity, "value") else str(item.rarity),
            value=item.value,
            weight=item.weight,
            quantity=item.quantity,
        )


class ToolChoiceResponse(BaseModel):
    count: int
    categories: list[str]


class BackgroundResponse(BaseModel):
    """Full detail of a single background."""
    id: str
    name: str
    description: str
    skill_proficiencies: list[str]
    tool_proficiencies_fixed: list[str]
    tool_proficiencies_choice: ToolChoiceResponse | None = None
    languages: list[str]
    extra_languages: int
    equipment: list[EquipmentItemResponse]
    equipment_gold: int
    feature: BackgroundFeatureResponse | None = None
    personality_traits: list[str] = []
    ideals: list[str] = []
    bonds: list[str] = []
    flaws: list[str] = []
    variant_of: str | None = None

    @classmethod
    def from_background(cls, bg: Background) -> "BackgroundResponse":
        tool_choice = None
        if bg.tool_choice:
            tool_choice = ToolChoiceResponse(
                count=bg.tool_choice.get("count", 0),
                categories=list(bg.tool_choice.get("categories", [])),
            )
        return cls(
            id=bg.id,
            name=bg.name,
            description=bg.description,
            skill_proficiencies=list(bg.skill_proficiencies),
            tool_proficiencies_fixed=list(bg.tool_fixed),
            tool_proficiencies_choice=tool_choice,
            languages=list(bg.languages),
            extra_languages=bg.extra_languages,
            equipment=[EquipmentItemResponse.from_item(i) for i in bg.equipment],
            equipment_gold=bg.equipment_gold,
            feature=BackgroundFeatureResponse(name=bg.feature.name, description=bg.feature.description)
            if bg.feature else None,
            personality_traits=list(bg.personality_traits),
            ideals=list(bg.ideals),
            bonds=list(bg.bonds),
            flaws=list(bg.flaws),
            variant_of=bg.variant_of,
        )


class BackgroundSummaryResponse(BaseModel):
    """Lightweight background entry for list views."""
    id: str
    name: str
    description: str
    skill_proficiencies: list[str]
    feature: str | None
    variant_of: str | None


class CharacterBackgroundResponse(BaseModel):
    """A character's resolved background."""
    character_id: int
    character_name: str
    background: str | None
    background_known: bool
    detail: BackgroundResponse | None = None


class SetBackgroundRequest(BaseModel):
    """Set or change a character's background."""
    background: str
    apply_equipment: bool = Field(
        default=True,
        description="Grant the background's starting equipment + gold pouch "
                    "(skipped if the background is unchanged to stay idempotent).",
    )


class SetBackgroundResult(BaseModel):
    success: bool
    character_id: int
    background: str
    background_id: str
    feature: str | None
    equipment_granted: list[str] = []
    gold_granted: int = 0
    total_gold: int


# --------------------------------------------------------------------------- #
# Registry routes
# --------------------------------------------------------------------------- #

@router.get("/backgrounds", response_model=list[BackgroundSummaryResponse])
def list_backgrounds():
    """List all available backgrounds (summary form)."""
    return [
        BackgroundSummaryResponse(
            id=s["id"],
            name=s["name"],
            description=s["description"],
            skill_proficiencies=s["skill_proficiencies"],
            feature=s["feature"],
            variant_of=s["variant_of"],
        )
        for s in bg_engine.background_summary()
    ]


@router.get("/backgrounds/{name}", response_model=BackgroundResponse)
def get_background(name: str):
    """Get full detail for a single background by name or id."""
    bg = bg_engine.get_background(name)
    if not bg:
        raise HTTPException(status_code=404, detail=f"Unknown background: {name!r}")
    return BackgroundResponse.from_background(bg)


# --------------------------------------------------------------------------- #
# Character routes
# --------------------------------------------------------------------------- #

def _get_character_or_404(character_id: int, db: Session) -> Character:
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


@router.get("/characters/{character_id}/background", response_model=CharacterBackgroundResponse)
def get_character_background(character_id: int, db: Session = Depends(get_db)):
    """Resolve a character's background into its full definition."""
    character = _get_character_or_404(character_id, db)
    bg_name = character.background
    bg = bg_engine.get_background(bg_name) if bg_name else None
    return CharacterBackgroundResponse(
        character_id=character.id,
        character_name=character.name,
        background=bg_name,
        background_known=bg is not None,
        detail=BackgroundResponse.from_background(bg) if bg else None,
    )


@router.post("/characters/{character_id}/background", response_model=SetBackgroundResult)
def set_character_background(
    character_id: int,
    request: SetBackgroundRequest,
    db: Session = Depends(get_db),
):
    """Set or change a character's background.

    By default also grants the background's starting equipment and gold pouch.
    Equipment grant is skipped when the background is unchanged (so the endpoint
    is idempotent and won't duplicate gold/items on repeat calls).
    """
    character = _get_character_or_404(character_id, db)

    bg = bg_engine.get_background(request.background)
    if not bg:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown background: {request.background!r}",
        )

    previous_bg = (character.background or "").strip().lower()
    same_background = previous_bg == bg.id

    granted_names: list[str] = []
    gold_granted = 0

    if request.apply_equipment and not same_background:
        # Add the background's starting equipment to the character's inventory
        inventory = _load_inventory(character)
        for item in bg_engine.get_background_equipment(bg.id):
            inventory.add_item(item)
            granted_names.append(item.name)
        _save_inventory(character, inventory)

        # Add the gold pouch
        gold_granted = bg_engine.get_background_equipment_gold(bg.id)
        character.gold = (character.gold or 0) + gold_granted

    # Persist the background on the character
    character.background = bg.name

    db.commit()
    db.refresh(character)

    return SetBackgroundResult(
        success=True,
        character_id=character.id,
        background=bg.name,
        background_id=bg.id,
        feature=bg.feature.name if bg.feature else None,
        equipment_granted=granted_names,
        gold_granted=gold_granted,
        total_gold=character.gold or 0,
    )
