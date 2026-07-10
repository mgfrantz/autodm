"""
Subclass API — list, view, and choose DnD 5e subclasses.

In 5e every class gains a subclass at a set level (1, 2, or 3). This API lets a
player see the available subclasses for their class and lock in a permanent
choice, which then surfaces in the feature timeline and the DM context.

Endpoints (mounted under /api/characters/subclasses):
- GET  /list                      — list all subclasses (optional ?class= filter)
- GET  /list/{subclass_id}        — a specific subclass's definition
- GET  /{character_id}            — the character's current subclass choices +
                                    the merged class+subclass feature timeline
- GET  /{character_id}/available  — subclasses the character can choose now
- POST /{character_id}/choose     — choose a subclass (permanent)

The choice is stored in the Character.subclass JSON column as
``{"class_name": subclass_id}`` so multiclassed characters can hold one
subclass per class.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import Character
from app.engine.subclasses import (
    Subclass,
    all_subclasses,
    subclasses_for_class,
    get_subclass,
    subclass_choice_level,
    subclass_category,
    can_choose_subclass,
    validate_subclass_choice,
    features_through_level,
    next_subclass_feature,
    subclass_summary_for_dm,
    combined_features_through_level,
)

router = APIRouter()


# --------------------------------------------------------------------------- #
# Request / Response models                                                   #
# --------------------------------------------------------------------------- #

class SubclassFeatureInfo(BaseModel):
    level: int
    feature: str


class SubclassInfo(BaseModel):
    """A subclass definition for display."""
    id: str
    name: str
    char_class: str
    category: str
    description: str
    features: list[SubclassFeatureInfo]
    choice_level: int

    @classmethod
    def from_engine(cls, sub: Subclass) -> "SubclassInfo":
        d = sub.to_dict()
        return cls(
            id=d["id"],
            name=d["name"],
            char_class=d["char_class"],
            category=d["category"],
            description=d["description"],
            features=[SubclassFeatureInfo(**f) for f in d["features"]],
            choice_level=subclass_choice_level(sub.char_class),
        )


class ChosenSubclassInfo(BaseModel):
    """A subclass a character has chosen, with active features."""
    class_name: str
    subclass_id: str
    name: str
    category: str
    features: list[SubclassFeatureInfo]


class TimelineEntry(BaseModel):
    """One merged class-or-subclass feature in the level timeline."""
    level: int
    source: str
    feature: str


class CharacterSubclassResponse(BaseModel):
    """A character's subclass state and feature timeline."""
    character_id: int
    character_name: str
    level: int
    choices: list[ChosenSubclassInfo]
    pending: list[dict]  # classes that still need a subclass choice
    timeline: list[TimelineEntry]
    dm_summary: str


class AvailableSubclass(SubclassInfo):
    """A subclass the character is eligible to choose right now."""
    eligible: bool = True
    choice_level: int = 0


class AvailableResponse(BaseModel):
    character_id: int
    level: int
    available: list[AvailableSubclass]


class ChooseSubclassRequest(BaseModel):
    subclass_id: str
    class_name: str | None = None  # default: primary class


class ChooseSubclassResponse(BaseModel):
    success: bool
    message: str
    class_name: str
    subclass_id: str
    subclass_name: str
    dm_summary: str


# --------------------------------------------------------------------------- #
# Registry endpoints (static paths)                                          #
# --------------------------------------------------------------------------- #

@router.get("/list", response_model=list[SubclassInfo])
def list_subclasses(class_name: str | None = None):
    """List all subclasses in the registry, optionally filtered by class."""
    if class_name:
        return [SubclassInfo.from_engine(s) for s in subclasses_for_class(class_name)]
    return [SubclassInfo.from_engine(s) for s in all_subclasses()]


@router.get("/list/{subclass_id}", response_model=SubclassInfo)
def get_subclass_detail(subclass_id: str):
    """Get a specific subclass's definition."""
    sub = get_subclass(subclass_id)
    if not sub:
        raise HTTPException(status_code=404, detail=f"Subclass '{subclass_id}' not found")
    return SubclassInfo.from_engine(sub)


# --------------------------------------------------------------------------- #
# Character endpoints                                                         #
# --------------------------------------------------------------------------- #

def _get_character_or_404(character_id: int, db: Session) -> Character:
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


def _build_choices(character: Character) -> list[ChosenSubclassInfo]:
    """Build the list of chosen subclasses from the character's state."""
    out: list[ChosenSubclassInfo] = []
    for cls_name, sub_id in character.subclass_dict.items():
        sub = get_subclass(sub_id)
        if sub is None:
            continue
        feats = [
            SubclassFeatureInfo(level=lvl, feature=feat)
            for lvl, feat in features_through_level(sub_id, character.level)
        ]
        out.append(ChosenSubclassInfo(
            class_name=cls_name,
            subclass_id=sub_id,
            name=sub.name,
            category=sub.category,
            features=feats,
        ))
    return out


def _build_pending(character: Character) -> list[dict]:
    """Classes that have reached their choice level but lack a subclass."""
    pending: list[dict] = []
    chosen = character.subclass_dict
    for cls_name, cls_level in character.classes_dict.items():
        choice_lvl = subclass_choice_level(cls_name)
        if choice_lvl == 0:
            continue
        if cls_name in chosen:
            continue
        if cls_level < choice_lvl:
            continue
        pending.append({
            "class_name": cls_name,
            "choice_level": choice_lvl,
            "category": subclass_category(cls_name),
            "options": [s.id for s in subclasses_for_class(cls_name)],
        })
    return pending


@router.get("/{character_id}", response_model=CharacterSubclassResponse)
def get_character_subclass(character_id: int, db: Session = Depends(get_db)):
    """Get a character's subclass choices and the merged feature timeline."""
    character = _get_character_or_404(character_id, db)

    # Use the primary class for the DM summary line.
    primary = character.primary_class
    primary_sub = character.subclass_dict.get(primary)
    dm_summary = subclass_summary_for_dm(primary, primary_sub, character.level)

    # Build the timeline from the primary class + its subclass.
    timeline = [
        TimelineEntry(**entry)
        for entry in combined_features_through_level(
            primary, character.level, primary_sub
        )
    ]

    return CharacterSubclassResponse(
        character_id=character.id,
        character_name=character.name,
        level=character.level,
        choices=_build_choices(character),
        pending=_build_pending(character),
        timeline=timeline,
        dm_summary=dm_summary,
    )


@router.get("/{character_id}/available", response_model=AvailableResponse)
def get_available_subclasses(character_id: int, db: Session = Depends(get_db)):
    """List subclasses the character can choose right now.

    A subclass is available if the character has a class at or past its choice
    level and hasn't already chosen a subclass for that class. Returns one set
    of options per eligible class (supporting multiclassing).
    """
    character = _get_character_or_404(character_id, db)
    chosen = character.subclass_dict
    available: list[AvailableSubclass] = []
    seen: set[str] = set()

    for cls_name, cls_level in character.classes_dict.items():
        if cls_name in chosen:
            continue
        if not can_choose_subclass(cls_name, cls_level):
            continue
        for sub in subclasses_for_class(cls_name):
            if sub.id in seen:
                continue
            seen.add(sub.id)
            d = SubclassInfo.from_engine(sub).model_dump()
            available.append(AvailableSubclass(**d, eligible=True))

    return AvailableResponse(
        character_id=character.id,
        level=character.level,
        available=available,
    )


@router.post("/{character_id}/choose", response_model=ChooseSubclassResponse)
def choose_subclass(
    character_id: int,
    request: ChooseSubclassRequest,
    db: Session = Depends(get_db),
):
    """Permanently choose a subclass for one of the character's classes.

    ``class_name`` defaults to the primary class. The choice is validated
    against the subclass's parent class and the class's choice level, then
    stored in the Character.subclass JSON column.
    """
    character = _get_character_or_404(character_id, db)

    cls_name = (request.class_name or character.primary_class).lower()
    classes_dict = character.classes_dict

    # The target class must actually be one the character has levels in.
    if cls_name not in classes_dict:
        raise HTTPException(
            status_code=400,
            detail=f"Character has no levels in '{cls_name}'.",
        )
    cls_level = classes_dict[cls_name]

    result = validate_subclass_choice(
        cls_name,
        request.subclass_id,
        cls_level,
        current_subclass=character.subclass_dict.get(cls_name),
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    sub = result.subclass
    assert sub is not None  # validated above

    # Persist the choice.
    choices = character.subclass_dict
    choices[cls_name] = sub.id
    character.subclass = json.dumps(choices)
    db.commit()
    db.refresh(character)

    dm_summary = subclass_summary_for_dm(cls_name, sub.id, character.level)
    return ChooseSubclassResponse(
        success=True,
        message=f"{character.name} became a {sub.name}.",
        class_name=cls_name,
        subclass_id=sub.id,
        subclass_name=sub.name,
        dm_summary=dm_summary,
    )
