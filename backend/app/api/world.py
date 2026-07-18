"""
World API — generate and manage game worlds.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import World
from app.llm.dspy_config import ensure_dspy_configured
from app.llm.dspy_modules import get_world_generation_module

router = APIRouter()


class WorldGenerateRequest(BaseModel):
    tone: str = "heroic fantasy"
    character_id: int | None = None  # If provided, tailor world to character


class WorldResponse(BaseModel):
    id: int
    name: str
    description: str
    tone: str

    model_config = ConfigDict(from_attributes=True)


def _build_character_context(character) -> str:
    """Build a character-tailoring context string for the world generator."""
    return (
        f"Tailor the world to this player character:\n"
        f"  Name: {character.name}\n"
        f"  Race: {character.race}\n"
        f"  Class: {character.char_class}\n"
        f"  Level: {character.level}\n"
        f"  Background: {character.background or 'unknown'}\n"
        f"  Abilities: STR {character.strength}, DEX {character.dexterity}, CON {character.constitution}\n"
        f"Adjust encounter types, social dynamics, and plot hooks to create a personalized experience."
    )


@router.post("/generate", response_model=WorldResponse)
def generate_world(request: WorldGenerateRequest, db: Session = Depends(get_db)):
    """Generate a new world using the LLM (DSPy-mediated)."""
    character_context = ""
    if request.character_id:
        from app.models.models import Character
        character = db.query(Character).filter(Character.id == request.character_id).first()
        if character:
            character_context = _build_character_context(character)

    try:
        ensure_dspy_configured()
        module = get_world_generation_module()
        result = module(tone=request.tone, character_context=character_context)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"World generation unavailable: {e}")

    if not result.name:
        raise HTTPException(status_code=503, detail="World generation returned an empty result.")

    world_data = module.to_world_dict(result, fallback_tone=request.tone)

    world = World(
        name=world_data.get("name", "Unnamed World"),
        description=world_data.get("description", ""),
        world_data=json.dumps(world_data),
        tone=world_data.get("tone", request.tone),
    )

    db.add(world)
    db.commit()
    db.refresh(world)
    return world


@router.get("/", response_model=list[WorldResponse])
def list_worlds(db: Session = Depends(get_db)):
    """List all generated worlds."""
    return db.query(World).order_by(World.created_at.desc()).all()


@router.get("/{world_id}")
def get_world_detail(world_id: int, db: Session = Depends(get_db)):
    """Get full world details including all generated content."""
    world = db.query(World).filter(World.id == world_id).first()
    if not world:
        raise HTTPException(status_code=404, detail="World not found")
    return {
        "id": world.id,
        "name": world.name,
        "description": world.description,
        "tone": world.tone,
        "world_data": json.loads(world.world_data),
    }
