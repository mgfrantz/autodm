"""
Game API — manages the active game session, DM narration, and player actions.
"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave, Character, World
from app.llm.orchestrator import orchestrator
from app.prompts.dm_prompts import DM_SYSTEM_PROMPT, ENCOUNTER_PROMPT
from app.engine.dice import roll_d20, ability_modifier, proficiency_bonus

router = APIRouter()


class GameCreate(BaseModel):
    name: str = "New Adventure"
    character_id: int
    world_id: int


class PlayerAction(BaseModel):
    action: str


class DMResponse(BaseModel):
    narration: str
    choices: list[str] | None = None
    combat_active: bool = False
    roll_requested: bool = False


@router.post("/create")
def create_game(game_data: GameCreate, db: Session = Depends(get_db)):
    """Create a new game session linking a character to a world."""
    character = db.query(Character).filter(Character.id == game_data.character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    world = db.query(World).filter(World.id == game_data.world_id).first()
    if not world:
        raise HTTPException(status_code=404, detail="World not found")

    world_data = json.loads(world.world_data)
    starting_loc = world_data.get("starting_settlement", {}).get("name", "Unknown")

    # Build initial game state
    game_state = {
        "location": starting_loc,
        "visited_locations": [starting_loc],
        "active_quests": [],
        "completed_quests": [],
        "npcs_met": [],
        "conditions": [],
        "in_combat": False,
    }

    save = GameSave(
        name=game_data.name,
        character_id=game_data.character_id,
        world_id=game_data.world_id,
        game_state=json.dumps(game_state),
        story_log=json.dumps([]),
    )

    db.add(save)
    db.commit()
    db.refresh(save)
    return {"game_id": save.id, "starting_location": starting_loc}


@router.post("/{game_id}/start")
async def start_adventure(game_id: int, db: Session = Depends(get_db)):
    """Get the opening narration for the adventure."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    character = save.character
    world = save.world
    world_data = json.loads(world.world_data)

    user_prompt = f"""\
The adventure begins.

World: {world.name}
Setting: {world_data.get('description', '')}
Starting Location: {world_data.get('starting_settlement', {}).get('name', '')}
Hook: {world_data.get('hook', '')}

Character: {character.name}, a level {character.level} {character.race} {character.char_class}.

Narrate the opening scene. Set the mood, introduce the setting, and present the hook.
End with 2-3 clear choices for the player.
"""

    narration = await orchestrator.generate_narration(
        system_prompt=DM_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )

    # Save to story log
    story_log = json.loads(save.story_log)
    story_log.append({"role": "dm", "content": narration, "timestamp": datetime.utcnow().isoformat()})
    save.story_log = json.dumps(story_log)
    db.commit()

    return {"narration": narration}


@router.post("/{game_id}/action", response_model=DMResponse)
async def player_action(game_id: int, action: PlayerAction, db: Session = Depends(get_db)):
    """Process a player action and get DM response."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    character = save.character
    world = save.world
    game_state = json.loads(save.game_state)
    story_log = json.loads(save.story_log)

    # Build context from recent story (last 10 entries)
    recent_events = "\n".join(
        f"[{entry.get('role', 'unknown')}]: {entry.get('content', '')[:200]}"
        for entry in story_log[-10:]
    )

    context = f"""\
Character: {character.name} (Level {character.level} {character.race} {character.char_class})
HP: {character.current_hp}/{character.max_hp}
AC: {character.armor_class}
Location: {game_state.get('location', 'Unknown')}
Conditions: {', '.join(game_state.get('conditions', ['none']))}
"""

    user_prompt = ENCOUNTER_PROMPT.format(
        location=game_state.get("location", "Unknown"),
        hp=character.current_hp,
        max_hp=character.max_hp,
        conditions=", ".join(game_state.get("conditions", ["none"])),
        recent_events=recent_events,
        player_action=action.action,
    )

    narration = await orchestrator.generate_narration(
        system_prompt=DM_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        context=context,
    )

    # Log the exchange
    story_log.append({"role": "player", "content": action.action, "timestamp": datetime.utcnow().isoformat()})
    story_log.append({"role": "dm", "content": narration, "timestamp": datetime.utcnow().isoformat()})
    save.story_log = json.dumps(story_log)
    save.updated_at = datetime.utcnow()
    db.commit()

    return DMResponse(
        narration=narration,
        combat_active=game_state.get("in_combat", False),
    )


@router.get("/{game_id}/state")
def get_game_state(game_id: int, db: Session = Depends(get_db)):
    """Get the current game state including story log."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    return {
        "game_id": save.id,
        "name": save.name,
        "character": {
            "id": save.character.id,
            "name": save.character.name,
            "race": save.character.race,
            "char_class": save.character.char_class,
            "level": save.character.level,
            "hp": save.character.current_hp,
            "max_hp": save.character.max_hp,
        },
        "world": {
            "id": save.world.id,
            "name": save.world.name,
        },
        "game_state": json.loads(save.game_state),
        "story_log": json.loads(save.story_log),
        "current_act": save.current_act,
        "xp": save.xp,
    }


@router.get("/")
def list_games(db: Session = Depends(get_db)):
    """List all saved games."""
    saves = db.query(GameSave).order_by(GameSave.updated_at.desc()).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "character_name": s.character.name,
            "world_name": s.world.name,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in saves
    ]
