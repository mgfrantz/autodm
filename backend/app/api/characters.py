"""
Character API — create, list, and manage player characters.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator, ConfigDict
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import Character
from app.engine.dice import ability_modifier
from app.engine.multiclassing import (
    parse_classes,
    serialize_classes,
    check_multiclass_requirements,
    calculate_multiclass_hp,
    calculate_proficiency_bonus,
    build_multiclass_summary,
)

router = APIRouter()


class CharacterCreate(BaseModel):
    name: str
    race: str
    char_class: str
    level: int = 1
    background: str | None = None
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10
    backstory: str | None = None


class CharacterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    race: str
    char_class: str
    level: int
    classes: dict[str, int]  # All classes with levels
    primary_class: str  # The class with the highest level
    background: str | None
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int
    max_hp: int
    current_hp: int
    armor_class: int
    speed: int
    xp: int
    asi_used: int
    gold: int = 0  # Wealth in gold pieces
    feats: list[dict]  # Learned feats
    skill_proficiencies: list[str] = []  # Chosen skill proficiencies
    skill_expertise: list[str] = []  # Expertise skills
    tool_proficiencies: list[str] = []  # Chosen tool proficiencies
    backstory: str | None

    @field_validator('classes', mode='before')
    @classmethod
    def parse_classes_field(cls, v):
        """Parse JSON string to dict if needed."""
        if isinstance(v, str):
            return parse_classes(v)
        return v or {}

    @field_validator('feats', mode='before')
    @classmethod
    def parse_feats_field(cls, v):
        """Parse JSON string to list if needed."""
        if isinstance(v, str):
            return json.loads(v) if v else []
        return v or []

    @field_validator('skill_proficiencies', 'skill_expertise', 'tool_proficiencies', mode='before')
    @classmethod
    def parse_skill_list_field(cls, v):
        """Parse JSON string to list if needed."""
        if isinstance(v, str):
            return json.loads(v) if v else []
        return v or []

    @field_validator('primary_class', mode='before')
    @classmethod
    def lower_primary_class(cls, v):
        """Normalize primary_class to lowercase."""
        return v.lower() if isinstance(v, str) else v


class AddClassRequest(BaseModel):
    """Request to add a multiclass to an existing character."""
    new_class: str


class AddClassResponse(BaseModel):
    """Response when adding a multiclass."""
    success: bool
    message: str
    classes: dict[str, int]
    total_level: int
    proficiency_bonus: int
    hp_gained: int
    max_hp: int


# Starting HP by class (simplified — 5e hit die + CON mod)
CLASS_HIT_DICE = {
    "barbarian": 12,
    "fighter": 10,
    "paladin": 10,
    "ranger": 10,
    "bard": 8,
    "cleric": 8,
    "druid": 8,
    "monk": 8,
    "rogue": 8,
    "warlock": 8,
    "sorcerer": 6,
    "wizard": 6,
}

# Starting AC by class (base armor assumption)
CLASS_BASE_AC = {
    "barbarian": 12,  # Unarmored defense
    "monk": 12,  # Unarmored defense
    "fighter": 16,  # Chain mail
    "paladin": 16,
    "ranger": 14,  # Leather + DEX
    "bard": 12,
    "cleric": 14,
    "druid": 13,
    "rogue": 13,
    "warlock": 12,
    "sorcerer": 11,
    "wizard": 11,
}

# Starting gold by class (simplified — gives every new character a little
# spending money so they can engage with the shop/economy system right away).
CLASS_STARTING_GOLD = {
    "barbarian": 40,
    "fighter": 60,
    "paladin": 60,
    "ranger": 50,
    "bard": 50,
    "cleric": 50,
    "druid": 40,
    "monk": 15,
    "rogue": 60,
    "warlock": 50,
    "sorcerer": 40,
    "wizard": 40,
}

# Race speed
RACE_SPEED = {
    "human": 30, "elf": 30, "dwarf": 25, "halfling": 25,
    "gnome": 25, "half-elf": 30, "half-orc": 30, "tiefling": 30,
    "dragonborn": 30,
}


def _get_character_classes(character: Character) -> dict[str, int]:
    """Get a character's classes from the JSON column, with fallback for single-class."""
    classes = parse_classes(character.classes or "{}")
    if not classes:
        # Backward compatibility: use char_class and level
        classes = {character.char_class.lower(): character.level or 1}
    return classes


def _set_character_classes(character: Character, classes: dict[str, int]):
    """Set a character's classes JSON and update denormalized fields."""
    character.classes = serialize_classes(classes)

    # Update denormalized fields
    character.level = sum(classes.values())
    character.char_class = max(classes.items(), key=lambda x: x[1])[0]


def _calculate_hp_for_classes(classes: dict[str, int], con_mod: int) -> int:
    """Calculate max HP for a set of classes."""
    total_hp, _ = calculate_multiclass_hp(classes, con_mod)
    return total_hp


@router.post("/", response_model=CharacterResponse)
def create_character(char_data: CharacterCreate, db: Session = Depends(get_db)):
    """Create a new player character with auto-calculated combat stats."""
    char_class_lower = char_data.char_class.lower()
    hit_die = CLASS_HIT_DICE.get(char_class_lower, 8)
    con_mod = ability_modifier(char_data.constitution)

    # Starting HP = max hit die + CON mod
    starting_hp = hit_die + con_mod
    if starting_hp < 1:
        starting_hp = 1

    base_ac = CLASS_BASE_AC.get(char_class_lower, 11)
    speed = RACE_SPEED.get(char_data.race.lower(), 30)
    starting_gold = CLASS_STARTING_GOLD.get(char_class_lower, 25)

    # Initialize classes dict
    classes = {char_class_lower: char_data.level}

    character = Character(
        name=char_data.name,
        race=char_data.race,
        char_class=char_data.char_class,
        level=char_data.level,
        classes=serialize_classes(classes),
        background=char_data.background,
        strength=char_data.strength,
        dexterity=char_data.dexterity,
        constitution=char_data.constitution,
        intelligence=char_data.intelligence,
        wisdom=char_data.wisdom,
        charisma=char_data.charisma,
        max_hp=starting_hp,
        current_hp=starting_hp,
        armor_class=base_ac,
        speed=speed,
        gold=starting_gold,
        backstory=char_data.backstory,
    )

    db.add(character)
    db.commit()
    db.refresh(character)
    return character


@router.get("/", response_model=list[CharacterResponse])
def list_characters(db: Session = Depends(get_db)):
    """List all characters."""
    return db.query(Character).order_by(Character.created_at.desc()).all()


@router.get("/{character_id}", response_model=CharacterResponse)
def get_character(character_id: int, db: Session = Depends(get_db)):
    """Get a specific character."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


@router.delete("/{character_id}")
def delete_character(character_id: int, db: Session = Depends(get_db)):
    """Delete a character."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    db.delete(character)
    db.commit()
    return {"status": "deleted", "id": character_id}


@router.post("/{character_id}/classes", response_model=AddClassResponse)
def add_class(
    character_id: int,
    request: AddClassRequest,
    db: Session = Depends(get_db),
):
    """Add a new class to an existing character (multiclassing).

    Checks ability score prerequisites and prevents duplicate classes.
    Raises the character to total level 2 (1 + 1) when adding first multiclass.
    """
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    new_class_lower = request.new_class.lower()
    classes = _get_character_classes(character)

    # Limit to two classes total
    if len(classes) >= 2:
        current_classes_str = ", ".join(classes.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Character already has two classes: {current_classes_str}. Cannot add more."
        )

    # Check if character already has this class
    if new_class_lower in classes:
        raise HTTPException(
            status_code=400,
            detail=f"Character already has levels in {new_class_lower}"
        )

    # Check ability score prerequisites
    abilities = {
        "strength": character.strength or 10,
        "dexterity": character.dexterity or 10,
        "constitution": character.constitution or 10,
        "intelligence": character.intelligence or 10,
        "wisdom": character.wisdom or 10,
        "charisma": character.charisma or 10,
    }

    check = check_multiclass_requirements(new_class_lower, abilities)
    if not check.can_multiclass:
        raise HTTPException(
            status_code=400,
            detail=check.message
        )

    # Add the class at level 1
    classes[new_class_lower] = 1
    _set_character_classes(character, classes)

    # Recalculate HP with new class
    con_mod = ability_modifier(character.constitution or 10)
    new_max_hp = _calculate_hp_for_classes(classes, con_mod)
    hp_gained = new_max_hp - (character.max_hp or 1)
    character.max_hp = new_max_hp
    character.current_hp = (character.current_hp or 1) + hp_gained

    # Update proficiency bonus based on new total level
    character.armor_class = CLASS_BASE_AC.get(new_class_lower, 11)  # Simplified AC recalc

    db.commit()
    db.refresh(character)

    summary = build_multiclass_summary(classes, con_mod, character.asi_used or 0)

    # Keep the stored ``level`` column in sync with the new total level so that
    # every reader (UI, DM context, other endpoints) sees a consistent value
    # without having to re-sum the ``classes`` JSON themselves.
    if character.level != summary.total_level:
        character.level = summary.total_level
        db.commit()
        db.refresh(character)

    return AddClassResponse(
        success=True,
        message=f"Added {new_class_lower} as a second class at level 1",
        classes=classes,
        total_level=summary.total_level,
        proficiency_bonus=summary.proficiency_bonus,
        hp_gained=hp_gained,
        max_hp=character.max_hp,
    )