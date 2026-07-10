"""
Feat API — list, view, and learn DnD 5e feats.

Feats provide an alternative to Ability Score Improvements (ASIs): each class
grants ASI instances at certain levels, and the player may spend an instance on
either a +2 to one ability (or +1 to two) OR a feat. Both consume one ASI.

Endpoints (mounted under /api/characters):
- GET  /feats                — list all available feats (registry)
- GET  /feats/{name}         — get a specific feat's definition
- GET  /{character_id}/feats — list a character's learned feats
- GET  /{character_id}/feats/available — list feats a character can learn now
- POST /{character_id}/feats/learn       — learn a feat (consumes an ASI)

Feats with ability-choice options (e.g., Resilient, Athlete) require a
`chosen_ability` in the learn request. Feats with HP effects (Tough) update
max/current HP retroactively (+2 per level already attained).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import Character
from app.engine.dice import ability_modifier
from app.engine.multiclassing import parse_classes, serialize_classes, calculate_multiclass_asi_status
from app.engine.feats import (
    get_feat,
    list_feats,
    list_available_feats,
    apply_feat,
    check_prerequisites,
)

router = APIRouter()


# --------------------------------------------------------------------------- #
# Request / Response models                                                   #
# --------------------------------------------------------------------------- #

class FeatInfo(BaseModel):
    """A feat's definition for display."""
    name: str
    description: str
    ability_bonus: dict[str, int]  # Fixed ability bumps (e.g., none currently)
    ability_bonus_choices: list[str]  # Pick one to +1 (half-feats)
    saving_throw_proficiency: str | None
    hp_per_level: int
    initiative_bonus: int
    speed_bonus: int
    ac_bonus: int
    skill_proficiencies: list[str]
    combat_modifiers: dict
    notes: list[str]
    prerequisite: dict | None
    source: str

    @classmethod
    def from_engine(cls, feat) -> "FeatInfo":
        """Convert engine Feat to API model."""
        return cls(**feat.to_dict())


class LearnedFeatInfo(BaseModel):
    """A feat a character has learned, with its effects applied."""
    name: str
    description: str
    effects_applied: dict
    learned_at_level: int | None = None


class CharacterFeatsResponse(BaseModel):
    """A character's learned feats and ASI status."""
    character_id: int
    character_name: str
    level: int
    feats: list[LearnedFeatInfo]
    asi_available: int
    asi_used: int
    asi_earned: int
    next_asi_level: int | None


class LearnFeatRequest(BaseModel):
    """Request to learn a feat (consumes one ASI instance)."""
    feat_name: str
    chosen_ability: str | None = None  # Required for choice feats


class LearnFeatResponse(BaseModel):
    """Result of learning a feat."""
    success: bool
    message: str
    feat_name: str
    ability_changes: dict[str, int]
    max_hp_change: int
    current_hp_change: int
    max_hp: int
    current_hp: int
    asi_available: int
    asi_used: int
    effects_applied: dict


# --------------------------------------------------------------------------- #
# Registry endpoints (static paths)                                          #
# --------------------------------------------------------------------------- #

@router.get("/list", response_model=list[FeatInfo])
def list_all_feats():
    """List all available feats in the registry."""
    return [FeatInfo.from_engine(f) for f in list_feats()]


@router.get("/list/{feat_name}", response_model=FeatInfo)
def get_feat_detail(feat_name: str):
    """Get a specific feat's definition."""
    feat = get_feat(feat_name)
    if not feat:
        raise HTTPException(status_code=404, detail=f"Feat '{feat_name}' not found")
    return FeatInfo.from_engine(feat)


# --------------------------------------------------------------------------- #
# Character feat endpoints (parameterized)                                   #
# --------------------------------------------------------------------------- #

def _load_character_feats(character: Character) -> list[dict]:
    """Parse a character's feats JSON column into a list."""
    import json
    try:
        return json.loads(character.feats or "[]")
    except (json.JSONDecodeError, TypeError):
        return []


def _save_character_feats(character: Character, feats: list[dict]) -> None:
    """Save feats list back to JSON column."""
    import json
    character.feats = json.dumps(feats) if feats else "[]"


@router.get("/{character_id}", response_model=CharacterFeatsResponse)
def get_character_feats(character_id: int, db: Session = Depends(get_db)):
    """List a character's learned feats and ASI status."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    classes = parse_classes(character.classes or "{}")
    if not classes:
        classes = {character.char_class.lower(): character.level or 1}

    asi_status = calculate_multiclass_asi_status(classes, character.asi_used or 0)

    feat_infos = []
    for f_dict in _load_character_feats(character):
        feat_infos.append(LearnedFeatInfo(
            name=f_dict.get("name", "Unknown"),
            description=f_dict.get("description", ""),
            effects_applied=f_dict.get("effects_applied", {}),
            learned_at_level=f_dict.get("learned_at_level"),
        ))

    return CharacterFeatsResponse(
        character_id=character.id,
        character_name=character.name,
        level=character.level,
        feats=feat_infos,
        asi_available=asi_status.available,
        asi_used=asi_status.used,
        asi_earned=asi_status.earned,
        next_asi_level=asi_status.next_asi_level,
    )


@router.get("/{character_id}/available", response_model=list[FeatInfo])
def get_available_feats(character_id: int, db: Session = Depends(get_db)):
    """List feats a character can learn right now.

    Filters by:
    - Not already known
    - Prerequisites met (ability scores, level, caster status, class, armor prof)
    """
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    classes = parse_classes(character.classes or "{}")
    if not classes:
        classes = {character.char_class.lower(): character.level or 1}

    abilities = {
        "strength": character.strength or 10,
        "dexterity": character.dexterity or 10,
        "constitution": character.constitution or 10,
        "intelligence": character.intelligence or 10,
        "wisdom": character.wisdom or 10,
        "charisma": character.charisma or 10,
    }

    known = [f.get("name") for f in _load_character_feats(character) if f.get("name")]

    available = list_available_feats(
        ability_scores=abilities,
        level=character.level,
        classes=classes,
        known_feats=known,
        race=str(character.race),
    )

    return [FeatInfo.from_engine(f) for f in available]


@router.post("/{character_id}/learn", response_model=LearnFeatResponse)
def learn_feat(
    character_id: int,
    request: LearnFeatRequest,
    db: Session = Depends(get_db),
):
    """Learn a feat, consuming one ASI instance.

    Validates:
    - ASI instance is available
    - Feat exists and is not already known
    - Prerequisites are met
    - For choice feats, chosen_ability is provided and valid
    - Ability scores have room for the bump (cap at 20)

    Applies:
    - Ability score changes (if any)
    - HP changes (e.g., Tough)
    - Feat added to character.feats
    - ASI used incremented
    - If CON changed, max HP is recomputed retroactively
    """
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    classes = parse_classes(character.classes or "{}")
    if not classes:
        classes = {character.char_class.lower(): character.level or 1}

    # Check ASI availability
    asi_status = calculate_multiclass_asi_status(classes, character.asi_used or 0)
    if asi_status.available <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"No ASI instances available. Earned: {asi_status.earned}, Used: {asi_status.used}"
        )

    # Lookup the feat
    feat = get_feat(request.feat_name)
    if not feat:
        raise HTTPException(
            status_code=404,
            detail=f"Feat '{request.feat_name}' not found"
        )

    # Check not already known
    known = [f.get("name", "") for f in _load_character_feats(character)]
    known_lower = [k.lower() for k in known if k]
    if feat.name.lower() in known_lower:
        raise HTTPException(
            status_code=400,
            detail=f"Character already knows the {feat.name} feat"
        )

    # Check prerequisites
    abilities = {
        "strength": character.strength or 10,
        "dexterity": character.dexterity or 10,
        "constitution": character.constitution or 10,
        "intelligence": character.intelligence or 10,
        "wisdom": character.wisdom or 10,
        "charisma": character.charisma or 10,
    }

    prereq_check = check_prerequisites(feat, abilities, character.level, classes, race=str(character.race))
    if not prereq_check.met:
        raise HTTPException(status_code=400, detail=prereq_check.message)

    # Apply the feat
    result = apply_feat(
        feat,
        abilities=abilities,
        level=character.level,
        max_hp=character.max_hp or 1,
        current_hp=character.current_hp or 1,
        chosen_ability=request.chosen_ability,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    # Persist ability changes
    con_changed = False
    for ability, delta in result.ability_changes.items():
        current = int(getattr(character, ability))
        setattr(character, ability, current + delta)
        if ability == "constitution" and delta > 0:
            con_changed = True

    # Update HP
    character.max_hp = (character.max_hp or 1) + result.max_hp_change
    character.current_hp = min(
        character.max_hp,
        (character.current_hp or 1) + result.current_hp_change,
    )

    # If CON changed, recompute max HP retroactively (like apply_asi does)
    if con_changed:
        from app.engine.leveling import hp_gained_for_levels
        con_mod = ability_modifier(character.constitution or 10)
        # Recalculate total HP from all classes
        from app.engine.multiclassing import calculate_multiclass_hp
        new_max, _ = calculate_multiclass_hp(classes, con_mod)
        old_max = character.max_hp
        character.max_hp = max(1, new_max)
        # Shift current HP by the delta
        delta = character.max_hp - old_max
        if delta > 0:
            character.current_hp = min(character.max_hp, (character.current_hp or 0) + delta)

    # Store the feat
    learned_feats = _load_character_feats(character)
    learned_feats.append({
        "name": result.feat_name,
        "description": feat.description,
        "effects_applied": result.effects_applied,
        "ability_changes": result.ability_changes,
        "learned_at_level": character.level,
    })
    _save_character_feats(character, learned_feats)

    # Increment ASI used
    character.asi_used = (character.asi_used or 0) + 1

    character.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(character)

    # Recalculate ASI status
    asi_status = calculate_multiclass_asi_status(classes, character.asi_used)

    return LearnFeatResponse(
        success=True,
        message=result.message,
        feat_name=result.feat_name,
        ability_changes=result.ability_changes,
        max_hp_change=result.max_hp_change,
        current_hp_change=result.current_hp_change,
        max_hp=character.max_hp,
        current_hp=character.current_hp,
        asi_available=asi_status.available,
        asi_used=asi_status.used,
        effects_applied=result.effects_applied,
    )