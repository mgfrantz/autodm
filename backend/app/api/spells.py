"""
Spells API — manage character spellbooks, slots, and casting.

Provides endpoints for:
- Getting a character's spellbook (known spells, prepared spells, slots)
- Initializing starting spells by class
- Learning new spells
- Preparing/unpreparing spells
- Casting spells (consuming slots, resolving effects)
- Recovering slots on a long rest
"""
import json
from app.utils.time_utils import utcnow

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import Character
from app.engine.spells import (
    Spell,
    Spellbook,
    SpellLevel,
    get_spell,
    get_starting_spellbook,
    SPELL_REGISTRY,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class SpellResponse(BaseModel):
    id: str
    name: str
    level: int
    school: str
    description: str
    casting_time: str
    range: str
    components: str
    material_description: str = ""
    duration: str
    concentration: bool
    ritual: bool
    requires_attack_roll: bool
    save_ability: str | None
    damage_dice_count: int
    damage_dice_sides: int
    damage_bonus: int
    damage_type: str
    healing_dice_count: int
    healing_dice_sides: int
    healing_bonus: int
    at_higher_levels_dice: int
    parsed_components: dict


class SpellSlotResponse(BaseModel):
    level: int
    max: int
    used: int
    available: int


class SpellbookResponse(BaseModel):
    char_class: str
    level: int
    caster_type: str
    casting_style: str
    casting_ability: str
    known_spells: list[str]
    prepared_spells: list[str]
    slots: list[SpellSlotResponse]
    castable_spells: list[SpellResponse]


class CastSpellRequest(BaseModel):
    spell_id: str
    slot_level: int | None = None
    caster_mod: int = 0  # ability modifier for casting (e.g., INT, WIS, CHA)
    target_ac: int | None = None  # for attack-roll spells
    target_save_total: int | None = None  # for saving-throw spells
    active_conditions: list[str] = []  # active conditions affecting the caster


class CastSpellResponse(BaseModel):
    success: bool
    message: str
    slot_level: int | None
    spell: SpellResponse | None
    damage: int = 0
    healing: int = 0
    hit: bool | None = None
    made_save: bool | None = None
    rolled_attack: int | None = None
    damage_type: str = ""


class LearnSpellRequest(BaseModel):
    spell_id: str


class PrepareSpellRequest(BaseModel):
    spell_id: str


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _load_spellbook(character: Character) -> Spellbook:
    """Load spellbook from character's JSON storage."""
    try:
        data = json.loads(character.spells)
    except (json.JSONDecodeError, TypeError):
        data = {}

    # If the spellbook is empty or missing char_class, use the character's
    if not data.get("char_class"):
        data["char_class"] = character.char_class

    return Spellbook.from_dict(data)


def _save_spellbook(character: Character, spellbook: Spellbook) -> None:
    """Save spellbook to character's JSON storage."""
    character.spells = json.dumps(spellbook.to_dict())


def _spell_to_response(spell: Spell) -> SpellResponse:
    """Convert Spell to SpellResponse."""
    return SpellResponse(
        id=spell.id,
        name=spell.name,
        level=spell.level,
        school=spell.school.value,
        description=spell.description,
        casting_time=spell.casting_time,
        range=spell.range,
        components=spell.components,
        material_description=spell.material_description,
        duration=spell.duration,
        concentration=spell.concentration,
        ritual=spell.ritual,
        requires_attack_roll=spell.requires_attack_roll,
        save_ability=spell.save_ability,
        damage_dice_count=spell.damage_dice_count,
        damage_dice_sides=spell.damage_dice_sides,
        damage_bonus=spell.damage_bonus,
        damage_type=spell.damage_type,
        healing_dice_count=spell.healing_dice_count,
        healing_dice_sides=spell.healing_dice_sides,
        healing_bonus=spell.healing_bonus,
        at_higher_levels_dice=spell.at_higher_levels_dice,
        parsed_components=spell.parsed_components.to_dict(),
    )


def _spellbook_to_response(spellbook: Spellbook) -> SpellbookResponse:
    """Convert Spellbook to SpellbookResponse."""
    return SpellbookResponse(
        char_class=spellbook.char_class,
        level=spellbook.level,
        caster_type=spellbook.caster_type.value,
        casting_style=spellbook.casting_style.value,
        casting_ability=spellbook.casting_ability,
        known_spells=spellbook.known_spells,
        prepared_spells=spellbook.prepared_spells,
        slots=[SpellSlotResponse(**s) for s in spellbook.slots_overview()],
        castable_spells=[_spell_to_response(s) for s in spellbook.castable_spells()],
    )


def _cast_outcome_to_response(outcome, spellbook: Spellbook) -> CastSpellResponse:
    """Convert CastOutcome to CastSpellResponse."""
    effect = outcome.effect
    return CastSpellResponse(
        success=outcome.success,
        message=outcome.message,
        slot_level=outcome.slot_level,
        spell=_spell_to_response(outcome.spell) if outcome.spell else None,
        damage=effect.damage if effect else 0,
        healing=effect.healing if effect else 0,
        hit=effect.hit if effect else None,
        made_save=effect.made_save if effect else None,
        rolled_attack=effect.rolled_attack if effect else None,
        damage_type=effect.damage_type if effect else "",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/{character_id}/spells", response_model=SpellbookResponse)
def get_spellbook(character_id: int, db: Session = Depends(get_db)):
    """Get a character's spellbook."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    spellbook = _load_spellbook(character)
    # Ensure spellbook is synced with current character level and class
    spellbook.char_class = character.char_class.lower()
    spellbook.set_level(character.level)
    _save_spellbook(character, spellbook)
    db.commit()

    return _spellbook_to_response(spellbook)


@router.post("/{character_id}/spells/initialize", response_model=SpellbookResponse)
def initialize_spellbook(character_id: int, db: Session = Depends(get_db)):
    """Initialize a character's spellbook with starting spells by class."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    spellbook = get_starting_spellbook(character.char_class, character.level)
    _save_spellbook(character, spellbook)
    character.updated_at = utcnow()
    db.commit()

    return _spellbook_to_response(spellbook)


@router.post("/{character_id}/spells/learn", response_model=SpellbookResponse)
def learn_spell(character_id: int, request: LearnSpellRequest, db: Session = Depends(get_db)):
    """Learn a new spell (adds to known spells)."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    spellbook = _load_spellbook(character)
    success = spellbook.learn_spell(request.spell_id)

    if not success:
        raise HTTPException(status_code=400, detail="Spell not found or already known")

    _save_spellbook(character, spellbook)
    character.updated_at = utcnow()
    db.commit()

    return _spellbook_to_response(spellbook)


@router.post("/{character_id}/spells/prepare", response_model=SpellbookResponse)
def prepare_spell(character_id: int, request: PrepareSpellRequest, db: Session = Depends(get_db)):
    """Prepare a spell (for prepared casters)."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    spellbook = _load_spellbook(character)
    if request.spell_id in spellbook.prepared_spells:
        # Already prepared — toggle to unprepare
        spellbook.unprepare_spell(request.spell_id)
    else:
        success = spellbook.prepare_spell(request.spell_id)
        if not success:
            raise HTTPException(status_code=400, detail="Spell not known or cannot be prepared")

    _save_spellbook(character, spellbook)
    character.updated_at = utcnow()
    db.commit()

    return _spellbook_to_response(spellbook)


@router.post("/{character_id}/spells/cast", response_model=CastSpellResponse)
def cast_spell(character_id: int, request: CastSpellRequest, db: Session = Depends(get_db)):
    """Cast a spell, consuming a slot and resolving its effect."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    spellbook = _load_spellbook(character)
    outcome = spellbook.cast(
        spell_id=request.spell_id,
        slot_level=request.slot_level,
        caster_mod=request.caster_mod,
        target_ac=request.target_ac,
        target_save_total=request.target_save_total,
        active_conditions=request.active_conditions,
    )

    if not outcome.success:
        raise HTTPException(status_code=400, detail=outcome.message)

    _save_spellbook(character, spellbook)
    character.updated_at = utcnow()
    db.commit()

    return _cast_outcome_to_response(outcome, spellbook)


@router.post("/{character_id}/spells/rest", response_model=SpellbookResponse)
def long_rest(character_id: int, db: Session = Depends(get_db)):
    """Recover all expended spell slots."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    spellbook = _load_spellbook(character)
    spellbook.long_rest()
    _save_spellbook(character, spellbook)
    character.updated_at = utcnow()
    db.commit()

    return _spellbook_to_response(spellbook)


@router.get("/spells/registry")
def get_spell_registry():
    """Get all available spells in the registry (for UI spell selection)."""
    spells = sorted(SPELL_REGISTRY.values(), key=lambda s: (s.level, s.name))
    return {"spells": [_spell_to_response(s) for s in spells]}


@router.get("/spells/registry/{spell_id}", response_model=SpellResponse)
def get_spell_by_id(spell_id: str):
    """Get a single spell by ID from the registry."""
    spell = get_spell(spell_id)
    if not spell:
        raise HTTPException(status_code=404, detail="Spell not found")
    return _spell_to_response(spell)