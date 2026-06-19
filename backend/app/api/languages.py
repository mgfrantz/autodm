"""
API endpoints for the language system.

Allows querying language data, character language status, and setting
a character's known languages.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.engine import languages
from app.engine.languages import (
    ALL_LANGUAGES,
    STANDARD_LANGUAGES,
    EXOTIC_LANGUAGES,
    SECRET_LANGUAGES,
    get_language_info,
    list_languages,
    get_language_choices,
    validate_character_languages,
    calculate_language_summary,
)
from app.models.database import get_db
from app.models.models import Character

router = APIRouter()


# --------------------------------------------------------------------------- #
# Global language registry endpoints (no character_id)
# --------------------------------------------------------------------------- #

class LanguageDetail(BaseModel):
    """Detailed information about a single language."""
    id: str
    name: str
    type: str
    typical_speakers: str
    script: str | None


class LanguagesResponse(BaseModel):
    """All languages available in the game."""
    standard: list[LanguageDetail]
    exotic: list[LanguageDetail]
    secret: list[LanguageDetail]
    all: list[LanguageDetail]


@router.get("/languages/registry", response_model=LanguagesResponse, tags=["languages"])
def get_languages_registry():
    """Get the complete language registry grouped by type."""
    all_langs = list_languages()
    standard = [l for l in all_langs if l.type == languages.LanguageType.STANDARD]
    exotic = [l for l in all_langs if l.type == languages.LanguageType.EXOTIC]
    secret = [l for l in all_langs if l.type == languages.LanguageType.SECRET]

    def _to_model(info: languages.LanguageInfo) -> LanguageDetail:
        return LanguageDetail(
            id=info.id,
            name=info.name,
            type=info.type,
            typical_speakers=info.typical_speakers,
            script=info.script,
        )

    return LanguagesResponse(
        standard=[_to_model(l) for l in standard],
        exotic=[_to_model(l) for l in exotic],
        secret=[_to_model(l) for l in secret],
        all=[_to_model(l) for l in all_langs],
    )


@router.get("/languages/info/{language_id}", response_model=LanguageDetail, tags=["languages"])
def get_language_by_id(language_id: str):
    """Get detailed information about a specific language."""
    info = get_language_info(language_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Language '{language_id}' not found")
    return LanguageDetail(
        id=info.id,
        name=info.name,
        type=info.type,
        typical_speakers=info.typical_speakers,
        script=info.script,
    )


# --------------------------------------------------------------------------- #
# Character language endpoints (require character_id)
# --------------------------------------------------------------------------- #

# Separate router for character endpoints
char_router = APIRouter(prefix="/characters/{character_id}", tags=["languages"])


class CharacterLanguageInfo(BaseModel):
    """A character's language state."""
    character_id: int
    race: str
    background: str | None
    known_languages: list[str]
    automatic_languages: list[str]  # From race/background/class
    extra_languages: list[str]  # Chosen beyond automatic
    remaining_choices: int
    available_choices: list[str]
    summary: str


class SetLanguagesRequest(BaseModel):
    """Set a character's known languages."""
    languages: list[str] = Field(..., description="Language IDs the character knows")


class LanguageValidationResult(BaseModel):
    """Result of validating a character's languages."""
    valid: bool
    error: str | None
    known_languages: list[str]
    automatic_languages: list[str]
    extra_languages: list[str]


def _get_character_or_404(character_id: int, db: Session) -> Character:
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


@char_router.get("/languages/choices", response_model=CharacterLanguageInfo)
def get_character_language_choices(character_id: int, db: Session = Depends(get_db)):
    """Get valid language choices for a character.

    Includes:
    - Known languages
    - Automatic languages (race + background + class)
    - Remaining choices
    - Valid pool for remaining choices
    - Human-readable summary
    """
    character = _get_character_or_404(character_id, db)
    choices = get_language_choices(character)
    summary = calculate_language_summary(character)

    return CharacterLanguageInfo(
        character_id=character_id,
        race=character.race,
        background=character.background,
        known_languages=choices.current_languages,
        automatic_languages=choices.race_fixed + choices.background_languages + choices.class_languages,
        extra_languages=[l for l in choices.current_languages if l not in (
            choices.race_fixed + choices.background_languages + choices.class_languages
        )],
        remaining_choices=choices.remaining_choices,
        available_choices=choices.available_choices,
        summary=summary["summary"],
    )


@char_router.post("/languages", response_model=CharacterLanguageInfo)
def set_character_languages(
    character_id: int,
    request: SetLanguagesRequest,
    db: Session = Depends(get_db),
):
    """Set a character's known languages.

    Validates that:
    - All languages are valid
    - Automatic languages (race/background/class) are included
    - Extra choices don't exceed the racial allotment
    - Extra choices are from the valid pool

    Returns the updated language info.
    """
    character = _get_character_or_404(character_id, db)

    # Normalize language IDs
    normalized = []
    for lang in request.languages:
        lang_id = languages.normalize_language_id(lang)
        if lang_id:
            normalized.append(lang_id)

    # Validate
    is_valid, error = validate_character_languages(character, normalized)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    # Save
    character.languages = json.dumps(normalized)
    db.commit()
    db.refresh(character)

    # Return updated info
    choices = get_language_choices(character)
    summary = calculate_language_summary(character)

    return CharacterLanguageInfo(
        character_id=character_id,
        race=character.race,
        background=character.background,
        known_languages=choices.current_languages,
        automatic_languages=choices.race_fixed + choices.background_languages + choices.class_languages,
        extra_languages=[l for l in choices.current_languages if l not in (
            choices.race_fixed + choices.background_languages + choices.class_languages
        )],
        remaining_choices=choices.remaining_choices,
        available_choices=choices.available_choices,
        summary=summary["summary"],
    )


@char_router.post("/languages/validate", response_model=LanguageValidationResult)
def validate_languages(
    character_id: int,
    request: SetLanguagesRequest,
    db: Session = Depends(get_db),
):
    """Validate a proposed set of languages for a character without saving."""
    character = _get_character_or_404(character_id, db)

    # Normalize
    normalized = []
    for lang in request.languages:
        lang_id = languages.normalize_language_id(lang)
        if lang_id:
            normalized.append(lang_id)

    # Validate
    is_valid, error = validate_character_languages(character, normalized)

    # Get derived info
    derived = languages.get_derived_languages(character)
    known_set = set(normalized)
    auto_set = set(derived["all_automatic"])

    return LanguageValidationResult(
        valid=is_valid,
        error=error,
        known_languages=normalized,
        automatic_languages=derived["all_automatic"],
        extra_languages=[l for l in normalized if l not in auto_set],
    )