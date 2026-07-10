"""
Social Interaction REST API — DMG ch.4/ch.8 NPC interaction resolution.

Mounts under ``/api/game``. Turns the pure :mod:`app.engine.social` resolution
rules into game-scoped endpoints that:

- read the character's real skill modifiers (Persuasion / Intimidation /
  Deception / Insight) via the ``skills`` engine,
- auto-detect the character's active combat conditions from ``game_state`` so
  condition effects (charmed / frightened / poisoned) apply automatically,
- sync reaction + influence outcomes back into the ``world_state`` NPC
  relationship (attitude + trust) so the social pillar and the relationship
  tracker never drift, and
- log narration lines to the story.

Endpoints:
- GET  /{game_id}/social/npcs
      Known NPCs with their DMG attitude, trust, and the influence DC to
      improve the relationship.
- GET  /{game_id}/social/npcs/{npc_name}
      A single NPC's interaction summary (404 if not yet met).
- POST /{game_id}/social/reaction
      Roll an initial-reaction (2d6 + CHA) for a newly-met NPC; persists the
      resulting attitude + trust midpoint on the NPC relationship.
- POST /{game_id}/social/influence
      A Charisma (Persuasion/Intimidation/Deception/Performance) check to shift
      the NPC's attitude one step; success improves, fail-by-5+ or nat 1
      worsens; persists the new attitude + trust delta.
- POST /{game_id}/social/insight
      An Insight check against an NPC's (passive or rolled) Deception to detect
      a lie. Informational; logged to the story.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave
from app.engine import social
from app.engine import skills as skills_engine
from app.engine.world_state import (
    WorldState,
    extract_world_state_from_game_state,
    merge_world_state_into_game_state,
)

router = APIRouter()


# --------------------------------------------------------------------------- #
# Persistence helpers (mirror the starvation / world_state routers)
# --------------------------------------------------------------------------- #

def _load_game(db: Session, game_id: int) -> GameSave:
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")
    return save


def _game_state(save: GameSave) -> dict:
    try:
        return json.loads(save.game_state)
    except (json.JSONDecodeError, TypeError):
        return {}


def _persist(save: GameSave, game_state: dict, db: Session) -> None:
    save.game_state = json.dumps(game_state)
    save.updated_at = datetime.utcnow()
    db.commit()


def _log(save: GameSave, content: str) -> None:
    try:
        story_log = json.loads(save.story_log)
    except (json.JSONDecodeError, TypeError):
        story_log = []
    story_log.append({
        "role": "system",
        "content": content,
        "timestamp": datetime.utcnow().isoformat(),
    })
    save.story_log = json.dumps(story_log)


def _world_state(game_state: dict) -> WorldState:
    return extract_world_state_from_game_state(game_state)


def _save_world_state(save: GameSave, game_state: dict, ws: WorldState) -> dict:
    merge_world_state_into_game_state(game_state, ws)
    return game_state


def _active_conditions(game_state: dict) -> list[str]:
    """The character's active combat conditions (auto-detected from game_state).

    Stored as a list of condition names on ``game_state["conditions"]``.
    """
    conds = game_state.get("conditions") or []
    if not isinstance(conds, list):
        return []
    return [str(c) for c in conds]


def _charisma_modifier(save: GameSave) -> int:
    from app.engine.dice import ability_modifier as _am
    return _am(int(getattr(save.character, "charisma", 10) or 10))


def _skill_modifier(save: GameSave, skill: str) -> int:
    """The character's full skill modifier (ability + prof + expertise + feats)."""
    try:
        return int(skills_engine.calculate_skill_modifier(skill, save.character))
    except (ValueError, AttributeError):
        # Unknown skill or missing character data → fall back to the raw ability.
        return _charisma_modifier(save)


# --------------------------------------------------------------------------- #
# Response schemas
# --------------------------------------------------------------------------- #

class NPCInteractionResponse(BaseModel):
    npc_name: str
    attitude: str           # DMG attitude level
    trust: int              # world_state trust score
    influence_dc: int       # DC to improve one step (0 if already helpful)
    target_attitude: str    # attitude a success would reach
    summary: str            # one-line DM-ready summary


class NPCListResponse(BaseModel):
    npcs: list[NPCInteractionResponse]


class ReactionRequest(BaseModel):
    npc_name: str = Field(..., description="The NPC to roll a reaction for.")
    charisma_modifier: int | None = Field(
        default=None,
        description="Override CHA mod; defaults to the character's Charisma.",
    )
    reaction_dice: tuple[int, int] | None = Field(
        default=None,
        description="Explicit (d1, d2) for determinism / DM adjudication.",
    )


class InfluenceRequest(BaseModel):
    npc_name: str = Field(..., description="The NPC to influence.")
    skill: str = Field(
        default="persuasion",
        description="Approach skill: persuasion / intimidation / deception / performance.",
    )
    skill_modifier: int | None = Field(
        default=None,
        description="Override skill modifier; defaults to the character's skill mod.",
    )
    conditions: list[str] | None = Field(
        default=None,
        description="Override active conditions; defaults to game_state combat conditions.",
    )
    forced_advantage: bool = False
    forced_disadvantage: bool = False
    roll: int | None = Field(
        default=None, ge=1, le=20,
        description="Explicit d20 for the influence check (DM-adjudicated).",
    )
    fail_margin_for_worsen: int = Field(
        default=5, ge=0,
        description="Failure margin that worsens attitude. Set high (e.g. 99) to disable.",
    )


class InsightRequest(BaseModel):
    npc_name: str = Field(..., description="The NPC being read for deception.")
    insight_modifier: int | None = Field(
        default=None,
        description="Override Insight modifier; defaults to the character's Insight.",
    )
    npc_deception_total: int | None = Field(
        default=None,
        description="A rolled NPC Deception total (active contest).",
    )
    npc_passive_deception: int | None = Field(
        default=None,
        description="The NPC's passive Deception (10 + Deception mod).",
    )
    insight_roll: int | None = Field(
        default=None, ge=1, le=20,
        description="Explicit d20 for the Insight check (DM-adjudicated).",
    )


# --------------------------------------------------------------------------- #
# NPC lookup helpers
# --------------------------------------------------------------------------- #

def _npc_attitude(ws: WorldState, npc_name: str) -> str:
    """The DMG attitude for an NPC (derived from trust, or 'indifferent' if new)."""
    if npc_name in ws.npc_relationships:
        return social.attitude_for_trust(ws.npc_relationships[npc_name].trust)
    return "indifferent"


def _npc_interaction(ws: WorldState, npc_name: str) -> NPCInteractionResponse:
    attitude = _npc_attitude(ws, npc_name)
    trust = ws.npc_relationships[npc_name].trust if npc_name in ws.npc_relationships else 0
    return NPCInteractionResponse(
        npc_name=npc_name,
        attitude=attitude,
        trust=trust,
        influence_dc=social.INFLUENCE_DC[attitude],
        target_attitude=social.shift_attitude(attitude, +1),
        summary=social.npc_interaction_summary(npc_name, attitude, trust),
    )


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("/{game_id}/social/npcs", response_model=NPCListResponse)
def list_npcs(game_id: int, db: Session = Depends(get_db)):
    """Known NPCs with their DMG attitude, trust, and influence-DC."""
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    ws = _world_state(game_state)
    npcs = [_npc_interaction(ws, name) for name in ws.npc_relationships]
    return NPCListResponse(npcs=npcs)


@router.get(
    "/{game_id}/social/npcs/{npc_name}",
    response_model=NPCInteractionResponse,
)
def get_npc(game_id: int, npc_name: str, db: Session = Depends(get_db)):
    """A single NPC's interaction summary.

    Returns the DMG attitude derived from the stored trust (defaults to
    'indifferent' with trust 0 for an NPC not yet tracked).
    """
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    ws = _world_state(game_state)
    return _npc_interaction(ws, npc_name)


@router.post("/{game_id}/social/reaction")
def roll_reaction(
    game_id: int,
    request: ReactionRequest,
    db: Session = Depends(get_db),
):
    """Roll an initial-reaction (2d6 + CHA) for a newly-met NPC.

    The resulting attitude is persisted on the NPC relationship: the trust
    score is set to the attitude's band midpoint and the attitude string is
    updated, so a follow-up influence check starts from the right place.
    """
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    cha_mod = (
        request.charisma_modifier
        if request.charisma_modifier is not None
        else _charisma_modifier(save)
    )

    result = social.reaction_roll(cha_mod, request.reaction_dice)

    # Persist the disposition onto the NPC relationship.
    ws = _world_state(game_state)
    npc = ws.get_or_create_npc(request.npc_name)
    target_trust = social.trust_for_attitude(result.attitude)
    # Set trust to the band midpoint (this is an *initial* reaction, not a delta).
    npc.trust = target_trust
    npc.attitude = result.attitude
    npc.last_interacted = datetime.utcnow().isoformat()
    npc.interactions.append(f"Initial reaction: {result.description}")
    game_state = _save_world_state(save, game_state, ws)

    _log(save, f"{request.npc_name}'s initial reaction: {result.description}.")
    _persist(save, game_state, db)

    return {
        "npc_name": request.npc_name,
        "character_id": save.character_id,
        **result.to_dict(),
        "trust": target_trust,
    }


@router.post("/{game_id}/social/influence")
def influence_npc(
    game_id: int,
    request: InfluenceRequest,
    db: Session = Depends(get_db),
):
    """Make a Charisma check to shift an NPC's attitude one step.

    Uses the character's real skill modifier (via the skills engine) and
    auto-detects combat conditions unless overridden. On success the NPC's
    attitude improves one step and trust rises; on a fail-by-``margin``+ or a
    natural 1 the attitude worsens and trust drops. Both are persisted on the
    NPC relationship and narrated to the story.
    """
    save = _load_game(db, game_id)
    game_state = _game_state(save)
    ws = _world_state(game_state)

    current = _npc_attitude(ws, request.npc_name)
    skill_mod = (
        request.skill_modifier
        if request.skill_modifier is not None
        else _skill_modifier(save, request.skill)
    )
    conditions = (
        request.conditions
        if request.conditions is not None
        else _active_conditions(game_state)
    )

    result = social.influence_check(
        skill=request.skill,
        skill_modifier=skill_mod,
        current_attitude=current,
        conditions=conditions,
        forced_advantage=request.forced_advantage,
        forced_disadvantage=request.forced_disadvantage,
        roll=request.roll,
        fail_margin_for_worsen=request.fail_margin_for_worsen,
    )

    # Apply the attitude/trust change to the NPC relationship.
    npc = ws.get_or_create_npc(request.npc_name)
    if result.trust_delta != 0:
        npc.trust = max(-100, min(100, npc.trust + result.trust_delta))
    # Re-derive the stored attitude string from the (possibly new) trust.
    npc.attitude = social.attitude_for_trust(npc.trust)
    npc.last_interacted = datetime.utcnow().isoformat()
    npc.interactions.append(result.description)
    game_state = _save_world_state(save, game_state, ws)

    _log(save, f"Social check vs {request.npc_name}: {result.description}")
    _persist(save, game_state, db)

    return {
        "npc_name": request.npc_name,
        "character_id": save.character_id,
        **result.to_dict(),
        "trust": npc.trust,
        "stored_attitude": npc.attitude,
    }


@router.post("/{game_id}/social/insight")
def insight_npc(
    game_id: int,
    request: InsightRequest,
    db: Session = Depends(get_db),
):
    """An Insight check against an NPC's Deception to detect a lie.

    Provide either ``npc_deception_total`` (a rolled contest) or
    ``npc_passive_deception`` (10 + Deception mod). The character's Insight
    modifier is used unless overridden. Informational outcome; logged to story.
    """
    save = _load_game(db, game_id)
    insight_mod = (
        request.insight_modifier
        if request.insight_modifier is not None
        else _skill_modifier(save, "insight")
    )

    try:
        result = social.insight_check(
            insight_modifier=insight_mod,
            npc_deception_total=request.npc_deception_total,
            npc_passive_deception=request.npc_passive_deception,
            insight_roll=request.insight_roll,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Provide npc_deception_total or npc_passive_deception.",
        ) from exc

    _log(save, f"Insight vs {request.npc_name}: {result.description}")
    _persist(save, game_state=_game_state(save), db=db)

    return {
        "npc_name": request.npc_name,
        "character_id": save.character_id,
        **result.to_dict(),
    }
