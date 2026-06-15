"""
Character API — create, list, and manage player characters.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import Character
from app.engine.dice import ability_modifier

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
    id: int
    name: str
    race: str
    char_class: str
    level: int
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
    backstory: str | None

    class Config:
        from_attributes = True


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

# Race speed
RACE_SPEED = {
    "human": 30, "elf": 30, "dwarf": 25, "halfling": 25,
    "gnome": 25, "half-elf": 30, "half-orc": 30, "tiefling": 30,
    "dragonborn": 30,
}


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

    character = Character(
        name=char_data.name,
        race=char_data.race,
        char_class=char_data.char_class,
        level=char_data.level,
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
