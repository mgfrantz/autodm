"""
Game API — manages the active game session, DM narration, and player actions.
"""
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.models.database import get_db, get_session_factory
from app.models.models import GameSave, Character, World
from app.llm.dspy_config import ensure_dspy_configured
from app.llm.dspy_modules import get_dm_narration_module, stream_narration_dspy, get_quest_detection_module, get_npc_mood_detection_module, get_game_flags_detection_module
from app.prompts.dm_prompts import ENCOUNTER_PROMPT
from app.engine.dice import roll_d20, ability_modifier, proficiency_bonus
from app.engine.context import ContextManager, StorySummary, get_context_manager
from app.engine.quests import (
    QuestLog,
    extract_quest_log_from_game_state,
    merge_quest_log_into_game_state,
)
from app.engine.world_state import (
    WorldState,
    extract_world_state_from_game_state,
    merge_world_state_into_game_state,
)

router = APIRouter()


async def _dm_narrate(situation: str) -> str:
    """Generate DM narration via DSPy (runs in a threadpool to avoid
    blocking the async event loop during the synchronous LLM call).

    Returns an empty string on failure; callers should treat an empty
    narration as a degraded-response signal.
    """
    def _call() -> str:
        ensure_dspy_configured()
        module = get_dm_narration_module()
        result = module(situation=situation)
        return result.narration
    return await run_in_threadpool(_call)


def _detect_and_update_quests(
    narration: str,
    game_state: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Detect quest events in DM narration and update the quest log.

    Returns:
        Tuple of (updated game_state, list of information_revealed strings)
    """
    quest_log = extract_quest_log_from_game_state(game_state)
    existing_titles = [q.title for q in quest_log.get_quests_by_status("active")]

    try:
        ensure_dspy_configured()
        module = get_quest_detection_module()
        result = module(narration=narration, existing_quests=existing_titles)
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.error(f"Quest detection failed: {e}")
        return game_state, []

    # Process new quests offered
    for quest_data in getattr(result, "quests_offered", []):
        quest_log.add_quest(
            title=quest_data.get("title", "Untitled Quest"),
            description=quest_data.get("description", ""),
            giver=quest_data.get("giver", ""),
            objective=quest_data.get("objective", ""),
            reward_hint=quest_data.get("reward_hint", ""),
        )

    # Process quests completed
    for title in getattr(result, "quests_completed", []):
        quest = quest_log.find_quest_by_title(title)
        if quest and quest.status == "active":
            quest_log.update_quest_status(quest.id, "completed")

    # Process quests failed
    for title in getattr(result, "quests_failed", []):
        quest = quest_log.find_quest_by_title(title)
        if quest and quest.status == "active":
            quest_log.update_quest_status(quest.id, "failed")

    # Merge updated quest log back into game state
    updated_state = merge_quest_log_into_game_state(game_state, quest_log)
    info_revealed = getattr(result, "information_revealed", [])
    return updated_state, info_revealed


def _detect_and_update_npc_mood(
    narration: str,
    game_state: dict[str, Any],
) -> dict[str, Any]:
    """Detect NPC mood changes in DM narration and update world state.

    Returns:
        Updated game_state with NPC relationship changes applied.
    """
    world_state = extract_world_state_from_game_state(game_state)

    try:
        ensure_dspy_configured()
        module = get_npc_mood_detection_module()
        result = module(narration=narration)
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.error(f"NPC mood detection failed: {e}")
        return game_state

    # Process each detected mood change
    for mood_change_data in getattr(result, "npc_mood_changes", []):
        npc_name = mood_change_data.get("npc_name", "").strip()
        trust_change = mood_change_data.get("trust_change", 0)
        reason = mood_change_data.get("reason", "")

        if not npc_name:
            continue

        # Clamp trust change to -20..20 as per signature documented output range.
        # This is a safety net in case the LLM violates the contract.
        trust_change = max(-20, min(20, trust_change))

        # Apply the change via world_state
        interaction_summary = reason or f"Mood detected as {mood_change_data.get('mood_change', 'unknown')}"
        world_state.update_npc_relationship(
            npc_name=npc_name,
            trust_change=trust_change,
            interaction_summary=interaction_summary,
        )

    # Merge updated world state back into game state
    updated_state = merge_world_state_into_game_state(game_state, world_state)
    return updated_state


def _detect_and_update_game_flags(
    narration: str,
    game_state: dict[str, Any],
) -> dict[str, Any]:
    """Detect game flags to set/clear in DM narration and update world state.

    Returns:
        Updated game_state with flag changes applied.
    """
    world_state = extract_world_state_from_game_state(game_state)

    try:
        ensure_dspy_configured()
        module = get_game_flags_detection_module()
        result = module(narration=narration)
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.error(f"Game flags detection failed: {e}")
        return game_state

    # Process flags to set
    for flag_name in getattr(result, "flags_to_set", []):
        if flag_name:  # Skip empty strings
            world_state.set_flag(flag_name.strip(), True)

    # Process flags to clear
    for flag_name in getattr(result, "flags_to_clear", []):
        if flag_name:  # Skip empty strings
            world_state.clear_flag(flag_name.strip())

    # Merge updated world state back into game state
    updated_state = merge_world_state_into_game_state(game_state, world_state)
    return updated_state


def _sse(payload: dict) -> str:
    """Format a dict as a Server-Sent Events data line."""
    return f"data: {json.dumps(payload)}\n\n"


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
Alignment: {_alignment_for_dm(character.alignment)}

Narrate the opening scene. Set the mood, introduce the setting, and present the hook.
End with 2-3 clear choices for the player.
"""

    narration = await _dm_narrate(situation=user_prompt)

    # Detect and update quests
    game_state = json.loads(save.game_state)
    game_state, _info_revealed = _detect_and_update_quests(narration, game_state)

    # Detect and update NPC mood
    game_state = _detect_and_update_npc_mood(narration, game_state)

    # Detect and update game flags
    game_state = _detect_and_update_game_flags(narration, game_state)

    # Save to story log
    story_log = json.loads(save.story_log)
    story_log.append({"role": "dm", "content": narration, "timestamp": datetime.utcnow().isoformat()})
    save.story_log = json.dumps(story_log)
    save.game_state = json.dumps(game_state)
    db.commit()

    return {"narration": narration}


def _alignment_for_dm(alignment: str | None) -> str:
    """Render a character's alignment for DM context (id known or 'Unaligned')."""
    if not alignment:
        return "Unaligned"
    from app.engine.alignment import alignment_context
    ctx = alignment_context(alignment)
    return ctx or "Unaligned"


def _exhaustion_for_dm(level) -> str:
    """Render a character's exhaustion level for DM context.

    Returns 'none' at level 0, otherwise 'level N (<short effects>)'. The DM
    needs to know exhaustion so it can narrate its debilitating effects and
    adjudicate hazards that add levels.
    """
    try:
        lvl = int(level or 0)
    except (TypeError, ValueError):
        lvl = 0
    if lvl <= 0:
        return "none"
    from app.engine import exhaustion as exhaust
    effects = exhaust.level_effects(lvl)
    return f"level {lvl} ({'; '.join(effects['active_effects']) or 'afflicted'})"


def _survival_for_dm(game_state: dict, character) -> str:
    """Render a character's food/water situation for DM context.

    Returns 'well provisioned' when the character is eating and drinking, or a
    short note flagging how many days of deprivation have accrued and whether
    the character is actively starving/dehydrated — so the DM can narrate the
    toll of a long trek or a desert crossing.
    """
    from app.engine import starvation as surv
    from app.engine.dice import ability_modifier
    state = surv.SurvivalState.from_dict(game_state.get("survival"))
    if state.days_without_food == 0 and state.days_without_water == 0:
        return "well provisioned"
    con_mod = ability_modifier(int(getattr(character, "constitution", 10) or 10))
    env = game_state.get("environment")
    temp = env.get("temperature", "normal") if isinstance(env, dict) else "normal"
    summ = surv.deficit_summary(state, con_mod, surv.is_hot(temp))
    parts = []
    if state.days_without_food > 0:
        tag = "starving" if summ["starving"] else f"{summ['food_days_until_exhaustion']} food-day(s) of grace left"
        parts.append(f"{state.days_without_food} day(s) without food ({tag})")
    if state.days_without_water > 0:
        need = summ["daily_water_gal"]
        parts.append(f"{state.days_without_water} day(s) without water (need {need} gal/day)")
    return "; ".join(parts) or "well provisioned"


def _mount_for_dm(game_state: dict) -> str:
    """Render the character's mount situation for DM context.

    Returns 'on foot' when the character has no mount, or a short note naming
    the mount, its HP, and its overland-travel multiplier — so the DM can
    narrate mounted travel, aerial scouting, and the consequences of a downed
    steed in combat.
    """
    from app.engine import mounts
    state = mounts.MountState.from_dict(game_state.get("mount"))
    return mounts.mount_for_dm(state)


def _downtime_for_dm(game_state: dict, character) -> str:
    """Render the character's between-adventures situation for DM context.

    Surfaces the character's purse (gold) plus their most recent downtime
    activity, so the DM can narrate the texture of off-screen life — a flush
    purse after a heist, hard-won training, a week of carousing — and weight
    costs and opportunities accordingly. Returns just the wealth when no
    downtime activity has been recorded yet.
    """
    try:
        gold = int(getattr(character, "gold", 0) or 0)
    except (TypeError, ValueError):
        gold = 0
    dt_state = game_state.get("downtime") or {}
    wealth = f"{gold} gp"
    if isinstance(dt_state, dict) and dt_state.get("name"):
        return f"{wealth}; recently: {dt_state['name'].lower()}"
    return wealth


def _subclass_for_dm(character) -> str:
    """Render the character's subclass for DM context.

    Returns 'none' when no subclass is modelled, a prompt when one is due, or
    the subclass name plus its active features — so the DM can narrate a
    Champion's improved crits, a Life cleric's enhanced healing, etc.
    """
    from app.engine import subclasses
    primary = character.primary_class
    sub_id = character.subclass_dict.get(primary) if hasattr(character, "subclass_dict") else None
    return subclasses.subclass_summary_for_dm(primary, sub_id, character.level)


def _boss_for_dm(game_state: dict) -> str:
    """Render the active combat's legendary/lair creatures for DM context.

    When the party is fighting a legendary boss, surfaces the creature's
    legendary-action budget + remaining actions and any lair actions, so the
    DM narrates off-turn legendary strikes and lair hazards correctly. Returns
    'none' outside of combat or when no legendary creature is present.
    """
    if not game_state.get("in_combat", False):
        return "none"
    from app.engine import legendary as legendary_mod
    combat = game_state.get("combat") or {}
    lair_raw = combat.get("lair_actions") or []
    lair = [legendary_mod.LairAction.from_dict(a) for a in lair_raw]
    lines: list[str] = []
    for c in combat.get("combatants", []):
        if not legendary_mod.is_legendary(c):
            continue
        state = legendary_mod.LegendaryState(
            budget_max=c.get("legendary_budget_max", 3) or 3,
            budget_used=c.get("legendary_budget_used", 0) or 0,
        )
        summary = legendary_mod.legendary_summary_for_dm(
            type("X", (), {"name": c.get("name", "Creature"),
                            "is_legendary": True,
                            "legendary_actions": c.get("legendary_actions", []),
                            "legendary_budget_max": c.get("legendary_budget_max", 3),
                            "lair_actions": []})()
        )
        lines.append(f"{c.get('name', 'Creature')} — {summary} [{state.remaining}/{state.budget_max} left]")
    if lair:
        names = ", ".join(a.name for a in lair)
        lines.append(f"Lair actions (initiative {legendary_mod.LAIR_INITIATIVE_COUNT}): {names}")
    return "; ".join(lines) if lines else "none"


@router.post("/{game_id}/start/stream")
async def start_adventure_stream(game_id: int, session_factory=Depends(get_session_factory)):
    """Stream the opening narration to the client via Server-Sent Events.

    Streams DM narration token-by-token, then persists the full narration to
    the story log once streaming completes. Emits ``chunk`` events while the
    LLM is producing text and a final ``done`` event.
    """
    # Read phase: load game in a short-lived session.
    db = session_factory()
    try:
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
Alignment: {_alignment_for_dm(character.alignment)}

Narrate the opening scene. Set the mood, introduce the setting, and present the hook.
End with 2-3 clear choices for the player.
"""
    finally:
        db.close()

    async def event_stream():
        collected: list[str] = []
        try:
            async for chunk in stream_narration_dspy(user_prompt=user_prompt):
                collected.append(chunk)
                yield _sse({"type": "chunk", "content": chunk})
        except Exception as exc:  # noqa: BLE001 - surface errors to the client
            yield _sse({"type": "error", "message": str(exc)})
            return

        narration = "".join(collected)

        # Persist the completed narration.
        db = session_factory()
        try:
            save = db.query(GameSave).filter(GameSave.id == game_id).first()
            if save:
                # Detect and update quests
                game_state = json.loads(save.game_state)
                game_state, _info_revealed = _detect_and_update_quests(narration, game_state)

                # Detect and update NPC mood
                game_state = _detect_and_update_npc_mood(narration, game_state)

                # Detect and update game flags
                game_state = _detect_and_update_game_flags(narration, game_state)

                story_log = json.loads(save.story_log)
                story_log.append({
                    "role": "dm",
                    "content": narration,
                    "timestamp": datetime.utcnow().isoformat(),
                })
                save.story_log = json.dumps(story_log)
                save.game_state = json.dumps(game_state)
                db.commit()
        finally:
            db.close()

        yield _sse({"type": "done"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
    
    # Context management
    context_manager = get_context_manager()
    
    # Load existing summary
    summary = None
    if save.story_summary and save.story_summary != "null":
        summary_data = json.loads(save.story_summary)
        summary = StorySummary.from_dict(summary_data)
    
    # Build context using context manager
    recent_context = context_manager.build_context(
        story_log=story_log,
        summary=summary,
    )
    
    base_context = f"""\
Character: {character.name} (Level {character.level} {character.race} {character.char_class})
Alignment: {_alignment_for_dm(character.alignment)}
HP: {character.current_hp}/{character.max_hp}
AC: {character.armor_class}
Location: {game_state.get('location', 'Unknown')}
Conditions: {', '.join(game_state.get('conditions', ['none']))}
Exhaustion: {_exhaustion_for_dm(game_state.get('exhaustion', 0))}
Sustenance: {_survival_for_dm(game_state, character)}
Mount: {_mount_for_dm(game_state)}
Downtime: {_downtime_for_dm(game_state, character)}
Subclass: {_subclass_for_dm(character)}
Boss: {_boss_for_dm(game_state)}
"""

    user_prompt = f"""{ENCOUNTER_PROMPT.format(
        location=game_state.get("location", "Unknown"),
        hp=character.current_hp,
        max_hp=character.max_hp,
        conditions=", ".join(game_state.get("conditions", ["none"])),
        recent_events=recent_context,
        player_action=action.action,
    )}

{base_context}"""

    narration = await _dm_narrate(situation=user_prompt)

    # Detect and update quests
    game_state, _info_revealed = _detect_and_update_quests(narration, game_state)

    # Detect and update NPC mood
    game_state = _detect_and_update_npc_mood(narration, game_state)

    # Detect and update game flags
    game_state = _detect_and_update_game_flags(narration, game_state)

    # Log the exchange
    story_log.append({"role": "player", "content": action.action, "timestamp": datetime.utcnow().isoformat()})
    story_log.append({"role": "dm", "content": narration, "timestamp": datetime.utcnow().isoformat()})
    save.story_log = json.dumps(story_log)
    save.game_state = json.dumps(game_state)
    save.updated_at = datetime.utcnow()
    
    # Check if we need to summarize
    if context_manager.should_summarize(story_log, summary):
        # Summarize asynchronously (we'll await it since this is already an async function)
        new_summary = await context_manager.summarize_story(story_log, summary)
        save.story_summary = json.dumps(new_summary.to_dict())
        # Update current_act from summary if provided
        if new_summary.current_act:
            save.current_act = new_summary.current_act
    
    db.commit()

    return DMResponse(
        narration=narration,
        combat_active=game_state.get("in_combat", False),
    )


@router.post("/{game_id}/action/stream")
async def player_action_stream(game_id: int, action: PlayerAction, session_factory=Depends(get_session_factory)):
    """Stream the DM's response to a player action via Server-Sent Events.

    Mirrors the non-streaming ``player_action`` endpoint but emits narration
    token-by-token. The player's action and the full DM response are persisted
    to the story log once streaming completes. Emits ``chunk`` events followed
    by a ``done`` event that carries combat state metadata.
    """
    # Read phase: load the current game state in a short-lived session.
    db = session_factory()
    try:
        save = db.query(GameSave).filter(GameSave.id == game_id).first()
        if not save:
            raise HTTPException(status_code=404, detail="Game not found")
        character = save.character
        game_state = json.loads(save.game_state)
        story_log = json.loads(save.story_log)
        
        # Context management
        context_manager = get_context_manager()
        
        # Load existing summary
        summary = None
        if save.story_summary and save.story_summary != "null":
            summary_data = json.loads(save.story_summary)
            summary = StorySummary.from_dict(summary_data)
        
        # Build context using context manager
        recent_context = context_manager.build_context(
            story_log=story_log,
            summary=summary,
        )
        
        base_context = f"""\
Character: {character.name} (Level {character.level} {character.race} {character.char_class})
Alignment: {_alignment_for_dm(character.alignment)}
HP: {character.current_hp}/{character.max_hp}
AC: {character.armor_class}
Location: {game_state.get('location', 'Unknown')}
Conditions: {', '.join(game_state.get('conditions', ['none']))}
Exhaustion: {_exhaustion_for_dm(game_state.get('exhaustion', 0))}
Sustenance: {_survival_for_dm(game_state, character)}
Mount: {_mount_for_dm(game_state)}
Downtime: {_downtime_for_dm(game_state, character)}
Subclass: {_subclass_for_dm(character)}
Boss: {_boss_for_dm(game_state)}
"""

        user_prompt = f"""{ENCOUNTER_PROMPT.format(
            location=game_state.get("location", "Unknown"),
            hp=character.current_hp,
            max_hp=character.max_hp,
            conditions=", ".join(game_state.get("conditions", ["none"])),
            recent_events=recent_context,
            player_action=action.action,
        )}

{base_context}"""

        combat_active = game_state.get("in_combat", False)
        
        # Store summary data for later use in the async stream
        summary_data = None
        if summary:
            summary_data = summary.to_dict()
    finally:
        db.close()

    async def event_stream():
        collected: list[str] = []
        try:
            async for chunk in stream_narration_dspy(user_prompt=user_prompt):
                collected.append(chunk)
                yield _sse({"type": "chunk", "content": chunk})
        except Exception as exc:  # noqa: BLE001 - surface errors to the client
            yield _sse({"type": "error", "message": str(exc)})
            return

        narration = "".join(collected)

        # Persist the exchange once streaming is complete.
        db = session_factory()
        try:
            save = db.query(GameSave).filter(GameSave.id == game_id).first()
            if save:
                log = json.loads(save.story_log)
                now = datetime.utcnow().isoformat()
                log.append({"role": "player", "content": action.action, "timestamp": now})
                log.append({"role": "dm", "content": narration, "timestamp": now})
                save.story_log = json.dumps(log)
                save.updated_at = datetime.utcnow()

                # Detect and update quests
                game_state = json.loads(save.game_state)
                game_state, _info_revealed = _detect_and_update_quests(narration, game_state)

                # Detect and update NPC mood
                game_state = _detect_and_update_npc_mood(narration, game_state)

                # Detect and update game flags
                game_state = _detect_and_update_game_flags(narration, game_state)

                save.game_state = json.dumps(game_state)

                # Check if we need to summarize
                local_summary = None
                if save.story_summary and save.story_summary != "null":
                    local_summary_data = json.loads(save.story_summary)
                    local_summary = StorySummary.from_dict(local_summary_data)

                if context_manager.should_summarize(log, local_summary):
                    new_summary = await context_manager.summarize_story(log, local_summary)
                    save.story_summary = json.dumps(new_summary.to_dict())
                    if new_summary.current_act:
                        save.current_act = new_summary.current_act

                db.commit()
        finally:
            db.close()

        yield _sse({"type": "done", "combat_active": combat_active})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
            "gold": save.character.gold,
            "alignment": save.character.alignment,
            "background": save.character.background,
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
