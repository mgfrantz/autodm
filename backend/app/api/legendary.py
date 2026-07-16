"""
Legendary Actions & Lair Actions API — DnD 5e boss-monster combat (MM p. 11).

Exposes the legendary/lair engine (``engine/legendary.py``) over REST:

* Registry — list/look-up ready-to-use legendary creature presets (dragons,
  liches, beholders, etc.) that the DM can drop into ``/combat/start``.
* In-combat — inspect a legendary creature's available actions + remaining
  budget, spend a legendary action off-turn, and fire the lair action due on
  initiative count 20.

All in-combat mutations persist the encounter back to ``game_state['combat']``
and append a story-log entry so the DM narration reflects the boss's moves.
"""
from app.utils.time_utils import utcnow

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine.combat import Encounter, Attack
from app.engine import legendary as legendary_mod

router = APIRouter()


# --------------------------------------------------------------------------- #
# Registry endpoints (mounted at /api/game/legendary)
# --------------------------------------------------------------------------- #
@router.get("/legendary/creatures")
def list_legendary_creatures():
    """List all ready-to-use legendary creature presets."""
    return {"creatures": [p.to_dict() for p in legendary_mod.list_legendary_creatures()]}


@router.get("/legendary/creatures/{creature_id}")
def get_legendary_creature(creature_id: str):
    """Look up a single legendary creature preset."""
    preset = legendary_mod.get_legendary_creature(creature_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Legendary creature '{creature_id}' not found")
    return preset.to_dict()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _load_active_encounter(save: GameSave) -> tuple[dict, Encounter]:
    import json

    game_state = json.loads(save.game_state)
    if not game_state.get("in_combat", False):
        raise HTTPException(status_code=400, detail="Not in combat")
    encounter = Encounter.from_dict(game_state.get("combat", {}))
    return game_state, encounter


def _persist(save: GameSave, game_state: dict, encounter: Encounter, db: Session) -> None:
    import json

    game_state["combat"] = encounter.to_dict()
    player = next((c for c in encounter.combatants if c.id == "player"), None)
    if player is not None:
        save.character.current_hp = player.current_hp
    save.game_state = json.dumps(game_state)
    save.updated_at = utcnow()
    db.commit()


def _log_to_story(save: GameSave, content: str) -> None:
    import json

    story_log = json.loads(save.story_log)
    story_log.append({
        "role": "dm",
        "content": content,
        "timestamp": utcnow().isoformat(),
    })
    save.story_log = json.dumps(story_log)


def _find_combatant(encounter: Encounter, combatant_id: str):
    combatant = next((c for c in encounter.combatants if c.id == combatant_id), None)
    if combatant is None:
        raise HTTPException(status_code=404, detail=f"Combatant '{combatant_id}' not found")
    return combatant


def _legendary_view(combatant) -> dict:
    """Build the JSON view of a combatant's legendary state + actions."""
    state = legendary_mod.creature_state(combatant)
    actions = legendary_mod.get_legendary_actions(combatant)
    return {
        "combatant_id": combatant.id,
        "name": combatant.name,
        "is_legendary": legendary_mod.is_legendary(combatant),
        "budget_max": state.budget_max,
        "budget_used": state.budget_used,
        "budget_remaining": state.remaining,
        "legendary_actions": [a.to_dict() for a in actions],
        "available_actions": [
            a.to_dict() for a in legendary_mod.available_legendary_actions(combatant, state)
        ],
    }


# --------------------------------------------------------------------------- #
# In-combat endpoints
# --------------------------------------------------------------------------- #
@router.get("/{game_id}/legendary/{combatant_id}")
def get_legendary_state(game_id: int, combatant_id: str, db: Session = Depends(get_db)):
    """Get a combatant's legendary-action budget and available actions."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")
    game_state, encounter = _load_active_encounter(save)
    combatant = _find_combatant(encounter, combatant_id)
    return _legendary_view(combatant)


class UseLegendaryActionRequest(BaseModel):
    """Spend a legendary action off-turn (at the end of another creature's turn)."""

    combatant_id: str  # the legendary creature acting
    action_id: str     # which legendary action to use
    target_id: str | None = None  # required for attack-kind actions


@router.post("/{game_id}/legendary/use")
def use_legendary_action(
    game_id: int, request: UseLegendaryActionRequest, db: Session = Depends(get_db)
):
    """A legendary creature uses one of its legendary actions off-turn.

    Resolves the action's cost against the per-round budget. For attack-kind
    actions, resolves the attack against ``target_id`` through the encounter.
    Persists the encounter and logs the move to the story.
    """
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")
    game_state, encounter = _load_active_encounter(save)
    combatant = _find_combatant(encounter, request.combatant_id)

    state = legendary_mod.creature_state(combatant)
    actions = legendary_mod.get_legendary_actions(combatant)
    action = next((a for a in actions if a.id == request.action_id), None)
    if action is None:
        raise HTTPException(
            status_code=400,
            detail=f"Legendary action '{request.action_id}' not available to {combatant.name}.",
        )

    result = legendary_mod.spend_legendary_action(combatant, state, action)
    if not result.used:
        raise HTTPException(status_code=400, detail=result.reason)

    # Resolve attack-kind actions mechanically.
    attack_desc = ""
    if action.kind == "attack" and action.attack:
        if not request.target_id:
            raise HTTPException(
                status_code=400,
                detail=f"Legendary action '{action.name}' is an attack and needs a target_id.",
            )
        target = _find_combatant(encounter, request.target_id)
        attack = Attack(
            name=action.attack.get("name", action.name),
            attack_bonus=action.attack.get("attack_bonus", 0),
            damage_dice_count=action.attack.get("damage_dice_count", 1),
            damage_dice_sides=action.attack.get("damage_dice_sides", 6),
            damage_bonus=action.attack.get("damage_bonus", 0),
            damage_type=action.attack.get("damage_type", "slashing"),
            ranged=action.attack.get("ranged", False),
            magical=action.attack.get("magical", False),
            silvered=action.attack.get("silvered", False),
        )
        atk_result = encounter.resolve_attack(
            attacker=combatant, target=target, attack=attack
        )
        attack_desc = atk_result.description
        if action.condition and atk_result.hit:
            target.add_condition(action.condition, duration=action.condition_duration)
            attack_desc += f" {target.name} is now {action.condition}."

    description = result.description
    if attack_desc:
        description += f" {attack_desc}"

    _log_to_story(save, description)
    _persist(save, game_state, encounter, db)

    return {
        "used": result.used,
        "action": action.to_dict(),
        "remaining_budget": result.remaining_budget,
        "description": description,
        "encounter": encounter.to_dict(),
    }


@router.post("/{game_id}/lair/action")
def fire_lair_action(game_id: int, db: Session = Depends(get_db)):
    """Fire the lair action due this round (initiative count 20).

    Picks the rotating lair action for the current round (if any), records it
    as fired, and returns its narrative description. The mechanical resolution
    of any attack/save payload is the DM's to narrate via the returned effect
    description.
    """
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")
    game_state, encounter = _load_active_encounter(save)

    result = encounter.trigger_lair_action()
    if result is None:
        raise HTTPException(status_code=400, detail="No lair actions configured for this encounter.")
    if not result.triggered:
        raise HTTPException(
            status_code=400,
            detail=result.reason or "Lair action already fired this round or no actions available.",
        )

    _log_to_story(save, result.description)
    _persist(save, game_state, encounter, db)

    return {
        "triggered": result.triggered,
        "action": result.action.to_dict() if result.action else None,
        "description": result.description,
        "lair_last_fired_round": encounter.lair_last_fired_round,
        "encounter": encounter.to_dict(),
    }


@router.get("/{game_id}/lair")
def get_lair_state(game_id: int, db: Session = Depends(get_db)):
    """List the encounter's lair actions and which round last fired."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")
    game_state, encounter = _load_active_encounter(save)
    lair = [legendary_mod.LairAction.from_dict(a) for a in encounter.lair_actions]
    return {
        "has_lair": bool(lair),
        "initiative_count": legendary_mod.LAIR_INITIATIVE_COUNT,
        "lair_last_fired_round": encounter.lair_last_fired_round,
        "round_number": encounter.round_number,
        "lair_actions": [a.to_dict() for a in lair],
    }


@router.get("/{game_id}/legendary")
def get_encounter_legendary(game_id: int, db: Session = Depends(get_db)):
    """List every legendary creature in the active encounter with its budget."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")
    game_state, encounter = _load_active_encounter(save)
    bosses = [
        _legendary_view(c)
        for c in encounter.combatants
        if legendary_mod.is_legendary(c)
    ]
    return {
        "in_combat": True,
        "legendary_creatures": bosses,
        "has_lair": bool(encounter.lair_actions),
    }
