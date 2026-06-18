"""
Alignment system API — inspect alignments and apply them to characters.

DnD 5e alignment combines two axes (Law-Chaos and Good-Evil) into the classic
nine alignments. This API exposes the canonical alignment registry, lets a
client resolve a character's alignment, set/change it, and query the
relationship between two alignments (useful for DM NPC-reaction hooks).

Routes (mounted under ``/api``):

- ``GET  /alignment``                                   — list all nine alignments
- ``GET  /alignment/{name}``                            — single alignment detail
- ``GET  /alignment/compatibility``                     — relationship of two alignments
- ``GET  /characters/{character_id}/alignment``         — the character's alignment
- ``POST /characters/{character_id}/alignment``         — set/change a character's alignment
- ``GET  /characters/{character_id}/alignment/suggested`` — suggested alignments for the char
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.engine import alignment as align_engine
from app.models.database import get_db
from app.models.models import Character

router = APIRouter()


# --------------------------------------------------------------------------- #
# Response schemas
# --------------------------------------------------------------------------- #

class AlignmentResponse(BaseModel):
    """Full detail of a single alignment."""
    id: str
    name: str
    abbreviation: str
    ethics: str
    morals: str
    description: str
    roleplay_hooks: list[str] = []

    @classmethod
    def from_alignment(cls, a: "align_engine.Alignment") -> "AlignmentResponse":
        return cls(
            id=a.id,
            name=a.name,
            abbreviation=a.abbreviation,
            ethics=a.ethics,
            morals=a.morals,
            description=a.description,
            roleplay_hooks=list(a.roleplay_hooks),
        )


class AlignmentSummaryResponse(BaseModel):
    """Lightweight alignment entry for list views / pickers."""
    id: str
    name: str
    abbreviation: str
    ethics: str
    morals: str
    description: str


class RelationshipResponse(BaseModel):
    other_id: str
    other_name: str
    ethics_delta: int
    morals_delta: int
    total_distance: int
    disposition: str
    description: str


class CompatibilityResponse(BaseModel):
    alignment_a: str | None
    alignment_b: str | None
    relationship: RelationshipResponse | None


class CharacterAlignmentResponse(BaseModel):
    """A character's resolved alignment."""
    character_id: int
    character_name: str
    alignment: str | None
    alignment_known: bool
    detail: AlignmentResponse | None = None


class SetAlignmentRequest(BaseModel):
    """Set or change a character's alignment."""
    alignment: str


class SetAlignmentResult(BaseModel):
    success: bool
    character_id: int
    alignment: str  # canonical id
    name: str
    abbreviation: str


class SuggestedAlignmentsResponse(BaseModel):
    character_id: int
    race: str | None
    char_class: str | None
    suggested: list[str] = []
    race_tendencies: list[str] = []
    class_tendencies: list[str] = []


# --------------------------------------------------------------------------- #
# Registry routes
# --------------------------------------------------------------------------- #

@router.get("/alignment", response_model=list[AlignmentSummaryResponse])
def list_alignments():
    """List all nine alignments in canonical grid order."""
    return [
        AlignmentSummaryResponse(**s)
        for s in align_engine.list_alignment_summaries()
    ]


@router.get("/alignment/compatibility", response_model=CompatibilityResponse)
def alignment_compatibility(
    a: str = Query(..., description="First alignment (id, name, or abbreviation)"),
    b: str = Query(..., description="Second alignment (id, name, or abbreviation)"),
):
    """Score how alignment ``a`` relates to alignment ``b``.

    Returns the per-axis deltas, total grid distance, and a disposition label
    (friendly / cordial / wary / tense / hostile). Useful for DM NPC-reaction
    hooks and for the client to colour social encounters.
    """
    rel = align_engine.relationship(a, b)
    align_a = align_engine.get_alignment(a)
    align_b = align_engine.get_alignment(b)
    relationship_obj = (
        RelationshipResponse(
            other_id=rel.other_id,
            other_name=rel.other_name,
            ethics_delta=rel.ethics_delta,
            morals_delta=rel.morals_delta,
            total_distance=rel.total_distance,
            disposition=rel.disposition,
            description=rel.description,
        )
        if rel
        else None
    )
    return CompatibilityResponse(
        alignment_a=align_a.id if align_a else None,
        alignment_b=align_b.id if align_b else None,
        relationship=relationship_obj,
    )


@router.get("/alignment/{name}", response_model=AlignmentResponse)
def get_alignment(name: str):
    """Get full detail for a single alignment by id, name, or abbreviation."""
    a = align_engine.get_alignment(name)
    if a is None:
        raise HTTPException(status_code=404, detail=f"Unknown alignment: {name!r}")
    return AlignmentResponse.from_alignment(a)


# --------------------------------------------------------------------------- #
# Character routes
# --------------------------------------------------------------------------- #

def _get_character_or_404(character_id: int, db: Session) -> Character:
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


@router.get("/characters/{character_id}/alignment", response_model=CharacterAlignmentResponse)
def get_character_alignment(character_id: int, db: Session = Depends(get_db)):
    """Resolve a character's alignment into its full definition."""
    character = _get_character_or_404(character_id, db)
    align = align_engine.get_alignment(character.alignment) if character.alignment else None
    return CharacterAlignmentResponse(
        character_id=character.id,
        character_name=character.name,
        alignment=character.alignment,
        alignment_known=align is not None,
        detail=AlignmentResponse.from_alignment(align) if align else None,
    )


@router.post("/characters/{character_id}/alignment", response_model=SetAlignmentResult)
def set_character_alignment(
    character_id: int,
    request: SetAlignmentRequest,
    db: Session = Depends(get_db),
):
    """Set or change a character's alignment.

    Accepts an alignment id, name (``"Lawful Good"``), or abbreviation
    (``"LG"``) and stores the canonical id on the character.
    """
    character = _get_character_or_404(character_id, db)

    align = align_engine.get_alignment(request.alignment)
    if align is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown alignment: {request.alignment!r}",
        )

    character.alignment = align.id
    db.commit()
    db.refresh(character)

    return SetAlignmentResult(
        success=True,
        character_id=character.id,
        alignment=align.id,
        name=align.name,
        abbreviation=align.abbreviation,
    )


@router.get(
    "/characters/{character_id}/alignment/suggested",
    response_model=SuggestedAlignmentsResponse,
)
def get_suggested_alignments(character_id: int, db: Session = Depends(get_db)):
    """Suggested alignments for a character based on their race and class.

    Alignments implied by *both* race and class come first. Pure flavour
    suggestions — never enforced restrictions in DnD 5e.
    """
    character = _get_character_or_404(character_id, db)
    return SuggestedAlignmentsResponse(
        character_id=character.id,
        race=character.race,
        char_class=character.char_class,
        suggested=align_engine.suggested_alignments(character.race, character.char_class),
        race_tendencies=align_engine.get_race_tendencies(character.race),
        class_tendencies=align_engine.get_class_tendencies(character.char_class),
    )
