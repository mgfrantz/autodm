"""
Save/Load API — named save-game snapshots with full state restoration.

The live ``GameSave`` is auto-updated on every action, but a player also needs
the ability to capture a *named point-in-time snapshot* and rewind to it later.
A ``SaveSlot`` freezes the entire mutable game state — including a copy of the
character's HP, XP, level, inventory, spells, and ability scores — so that
loading it fully restores the character, not just the story log.

Endpoints
---------
* ``POST   /api/game/{game_id}/save``              — create a named snapshot
* ``GET    /api/game/{game_id}/saves``             — list snapshots (newest first)
* ``GET    /api/game/{game_id}/saves/{slot_id}``   — snapshot detail + preview
* ``POST   /api/game/{game_id}/load/{slot_id}``    — restore live state from a snapshot
* ``DELETE /api/game/{game_id}/saves/{slot_id}``    — delete a snapshot
"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave, SaveSlot, Character

router = APIRouter()


# Character fields that can change during play and therefore must be snapshotted
# so they can be restored on load. Identity fields (name/race/class/background/
# backstory) are left alone — they describe the character, not its state.
MUTABLE_CHARACTER_FIELDS = (
    "level",
    "xp",
    "asi_used",
    "gold",
    "feats",
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
    "max_hp",
    "current_hp",
    "armor_class",
    "speed",
    "inventory",
    "spells",
    "skill_proficiencies",
    "skill_expertise",
    "tool_proficiencies",
    "languages",
)


class CreateSaveRequest(BaseModel):
    """Request body for creating a named save snapshot."""
    slot_name: str


def capture_character_snapshot(character: Character) -> dict:
    """Capture the mutable character state into a plain dict for storage.

    Inventory/spells/feats are stored as JSON text on the character row, so they are
    parsed here so the snapshot stores structured data (not nested JSON strings).
    """
    snapshot: dict = {}
    for field in MUTABLE_CHARACTER_FIELDS:
        value = getattr(character, field)
        if field in ("inventory", "spells", "feats", "skill_proficiencies", "skill_expertise", "tool_proficiencies", "languages"):
            try:
                value = json.loads(value) if value else ([] if field != "spells" else {})
            except (TypeError, json.JSONDecodeError):
                value = [] if field != "spells" else {}
        snapshot[field] = value
    return snapshot


def apply_character_snapshot(character: Character, snapshot: dict) -> None:
    """Restore mutable character state from a snapshot dict.

    Inventory/spells/feats are written back as JSON text to match the column type.
    Unknown/missing keys are skipped defensively.
    """
    for field in MUTABLE_CHARACTER_FIELDS:
        if field not in snapshot:
            continue
        value = snapshot[field]
        if field in ("inventory", "spells", "feats", "skill_proficiencies", "skill_expertise", "tool_proficiencies", "languages"):
            value = json.dumps(value)
        setattr(character, field, value)


@router.post("/{game_id}/save")
def create_save(game_id: int, request: CreateSaveRequest, db: Session = Depends(get_db)):
    """Create a named save-game snapshot of the current live state."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    character = save.character

    slot = SaveSlot(
        game_save_id=game_id,
        name=request.slot_name,
        character_snapshot=json.dumps(capture_character_snapshot(character)),
        game_state=save.game_state or "{}",
        story_log=save.story_log or "[]",
        story_summary=save.story_summary or "null",
        current_act=save.current_act or 1,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)

    return _slot_summary(slot)


@router.get("/{game_id}/saves")
def list_saves(game_id: int, db: Session = Depends(get_db)):
    """List all named save snapshots for a game, newest first."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    return [_slot_summary(s) for s in save.save_slots]


@router.get("/{game_id}/saves/{slot_id}")
def get_save(game_id: int, slot_id: int, db: Session = Depends(get_db)):
    """Get details of a single save snapshot, including a state preview."""
    slot = _get_slot(db, game_id, slot_id)
    detail = _slot_summary(slot)
    detail["game_state"] = json.loads(slot.game_state or "{}")
    detail["story_log_length"] = len(json.loads(slot.story_log or "[]"))
    detail["character_snapshot"] = json.loads(slot.character_snapshot or "{}")
    return detail


@router.post("/{game_id}/load/{slot_id}")
def load_save(game_id: int, slot_id: int, db: Session = Depends(get_db)):
    """Restore the live game + character state from a named snapshot.

    This overwrites the current ``GameSave`` game_state/story_log and writes the
    snapshotted character state back onto the live ``Character`` row, effectively
    rewinding the game to the moment the snapshot was taken.
    """
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    slot = _get_slot(db, game_id, slot_id)

    # Restore the live GameSave from the snapshot.
    save.game_state = slot.game_state or "{}"
    save.story_log = slot.story_log or "[]"
    save.story_summary = slot.story_summary or "null"
    save.current_act = slot.current_act or 1
    # Restore XP from the character snapshot
    save.xp = json.loads(slot.character_snapshot or "{}").get("xp", 0)
    save.updated_at = datetime.utcnow()

    # Restore the live character's mutable state.
    snapshot = json.loads(slot.character_snapshot or "{}")
    apply_character_snapshot(save.character, snapshot)

    db.commit()

    snapshot_char = json.loads(slot.character_snapshot or "{}")
    return {
        "message": "Game loaded",
        "slot_name": slot.name,
        "restored_character": {
            "level": snapshot_char.get("level"),
            "current_hp": snapshot_char.get("current_hp"),
            "max_hp": snapshot_char.get("max_hp"),
            "xp": snapshot_char.get("xp"),
        },
        "story_log_entries": len(json.loads(slot.story_log or "[]")),
    }


@router.delete("/{game_id}/saves/{slot_id}")
def delete_save(game_id: int, slot_id: int, db: Session = Depends(get_db)):
    """Delete a named save snapshot."""
    slot = _get_slot(db, game_id, slot_id)
    db.delete(slot)
    db.commit()
    return {"message": "Save slot deleted", "slot_id": slot_id}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _get_slot(db: Session, game_id: int, slot_id: int) -> SaveSlot:
    """Fetch a SaveSlot, validating it belongs to the given game."""
    slot = (
        db.query(SaveSlot)
        .filter(SaveSlot.id == slot_id, SaveSlot.game_save_id == game_id)
        .first()
    )
    if not slot:
        raise HTTPException(status_code=404, detail="Save slot not found")
    return slot


def _slot_summary(slot: SaveSlot) -> dict:
    """Compact public summary of a save slot (no large payloads)."""
    snapshot = json.loads(slot.character_snapshot or "{}")
    return {
        "id": slot.id,
        "game_save_id": slot.game_save_id,
        "slot_name": slot.name,
        "created_at": slot.created_at.isoformat() if slot.created_at else None,
        "current_act": slot.current_act,
        "character_level": snapshot.get("level"),
        "character_hp": snapshot.get("current_hp"),
        "character_max_hp": snapshot.get("max_hp"),
        "xp": snapshot.get("xp"),
    }
