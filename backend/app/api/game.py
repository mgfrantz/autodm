"""
Game API — manages the active game session, DM narration, and player actions.
"""
import json
import logging
from app.utils.time_utils import utcnow
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.models.database import get_db, get_session_factory
from app.models.models import GameSave, Character, World
from app.llm.dspy_config import ensure_dspy_configured
from app.llm.dspy_modules import (
    get_dm_narration_module,
    get_dm_actionable_narration_module,
    stream_narration_dspy,
    get_quest_detection_module,
    get_npc_mood_detection_module,
    get_game_flags_detection_module,
    get_action_suggestions_module,
    get_skill_check_resolver_module,
)
from app.prompts.dm_prompts import ENCOUNTER_PROMPT
from app.engine.dice import roll_d20, ability_modifier, proficiency_bonus, roll_dice
from app.engine.game_events import GameEvent
from app.engine.dm_functions import (
    dm_roll_d20,
    dm_roll_dice,
    dm_request_check,
    dm_attack,
    dm_apply_damage,
    dm_roll_initiative,
    dm_cast_spell,
    dm_give_item,
    dm_remove_item,
    dm_equip_item,
    dm_use_item,
)
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
logger = logging.getLogger(__name__)


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


async def _dm_actionable_narrate(situation: str) -> tuple[str, list[dict]]:
    """Generate DM narration with structured game_actions via DSPy.

    Like :func:`_dm_narrate` but uses :class:`DMActionableNarrationModule`
    which outputs both narration text and ``game_actions`` (structured
    action dicts for mechanical resolution).

    Returns:
        Tuple of (narration_text, game_actions_list). On failure, returns
        (narration_text, []).
    """
    def _call() -> tuple[str, list[dict]]:
        ensure_dspy_configured()
        module = get_dm_actionable_narration_module()
        result = module(situation=situation)
        narration = result.narration
        actions = getattr(result, "game_actions", None) or []
        if not isinstance(actions, list):
            actions = []
        return narration, actions
    return await run_in_threadpool(_call)


def _combatant_roster_for_dm(game_state: dict[str, Any]) -> str:
    """Build a combatant roster string for the DM context.

    Returns a formatted list of combatants (id, name, side, HP, AC) if combat
    is active, or an empty string.
    """
    combat_data = game_state.get("combat")
    if not combat_data:
        return ""

    try:
        from app.engine.combat import Encounter
        encounter = Encounter.from_dict(combat_data)
        if not encounter.combatants:
            return ""

        lines = ["COMBATANT_ROSTER:"]
        for c in encounter.combatants:
            lines.append(
                f"  - ID: {c.id} | {c.name} ({c.side}) | HP: {c.current_hp}/{c.max_hp} | AC: {c.armor_class}"
            )
        lines.append("Use these IDs in combat game_actions (attack, damage).")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Failed to build combatant roster: {e}")
        return ""


# Mapping of casting-ability keys (as stored on a Spellbook) to the matching
# Character column name.
_ABILITY_TO_COLUMN = {
    "str": "strength",
    "dex": "dexterity",
    "con": "constitution",
    "int": "intelligence",
    "wis": "wisdom",
    "cha": "charisma",
}


def _caster_modifier_for_character(character: "Character", spellbook) -> int:
    """Derive the casting-ability modifier from the character's real scores.

    Uses the Spellbook's ``casting_ability`` (e.g. ``"int"``) to look up the
    matching ability score column on the Character, then computes the standard
    DnD ability modifier ``(score - 10) // 2``. Falls back to 0 on any error.
    """
    try:
        col = _ABILITY_TO_COLUMN.get(spellbook.casting_ability, "intelligence")
        score = getattr(character, col, 10) or 10
        return ability_modifier(score)
    except Exception:
        return 0


def _combatant_save_total(combatant, save_ability: str | None) -> int:
    """Roll a combatant's saving throw total for a given ability.

    Combatants reliably track Strength and Dexterity; other abilities default
    to a score of 10 (modifier 0) and no save proficiency, which is a
    reasonable approximation for most monsters. Returns ``d20 + modifier``.
    """
    ability = (save_ability or "").lower()
    col = _ABILITY_TO_COLUMN.get(ability)
    score = getattr(combatant, col, 10) if col else 10
    return roll_d20(modifier=ability_modifier(score)).total


def _available_spells_for_dm(character: "Character") -> str:
    """Build an available-spells roster string for the DM context (casters only).

    Mirrors :func:`_combatant_roster_for_dm`: lists the character's castable
    spells (id, name, school, level) and remaining slots so the DM can emit
    real ``cast_spell`` game_actions. Returns an empty string for non-casters.
    """
    try:
        from app.api.spells import _load_spellbook
        spellbook = _load_spellbook(character)
    except Exception as e:
        logger.error(f"Failed to load spellbook for DM roster: {e}")
        return ""

    if not spellbook.is_caster:
        return ""

    castable = spellbook.castable_spells()
    if not castable:
        return ""

    lines = ["AVAILABLE_SPELLS:"]
    for spell in castable:
        slot = "cantrip" if spell.is_cantrip else f"level {spell.level}"
        school = spell.school.value if hasattr(spell.school, "value") else str(spell.school)
        lines.append(f"  - ID: {spell.id} | {spell.name} ({school}, {slot})")

    slots = spellbook.slots_overview()
    avail = [f"L{sl['level']}:{sl['available']}" for sl in slots if sl.get("max", 0) > 0]
    if avail:
        lines.append(f"REMAINING_SLOTS: {', '.join(avail)}")
    lines.append("Use cast_spell with a real spell_id from this roster.")
    return "\n".join(lines)


# Inventory game-action functions (Phase 4).
_INVENTORY_ACTIONS = ("give_item", "remove_item", "equip_item", "use_item")


def _inventory_for_dm(character: "Character") -> str:
    """Build an inventory roster string for the DM context.

    Mirrors :func:`_combatant_roster_for_dm` / :func:`_available_spells_for_dm`:
    lists the character's inventory items (id, name, type, qty, equipped,
    rarity) so the DM can emit real ``remove_item`` / ``equip_item`` /
    ``use_item`` game_actions referencing exact item_ids. Returns an empty
    string when the inventory is empty or fails to load.
    """
    try:
        from app.api.inventory import _load_inventory
        inventory = _load_inventory(character)
    except Exception as e:
        logger.error(f"Failed to load inventory for DM roster: {e}")
        return ""

    if not inventory.slots:
        return ""

    lines = ["INVENTORY_ROSTER:"]
    for slot in inventory.slots:
        item = slot.item
        eq = " [equipped]" if slot.equipped else ""
        qty = f" x{item.quantity}" if item.quantity > 1 else ""
        rarity = item.rarity.value if hasattr(item.rarity, "value") else str(item.rarity)
        lines.append(
            f"  - ID: {item.id} | {item.name}{qty} ({item.item_type.value}, "
            f"{rarity}){eq}"
        )
    lines.append(
        "Use these item_ids for remove_item, equip_item, and use_item."
    )
    return "\n".join(lines)


def _resolve_game_actions(
    game_actions: list[dict],
    game_state: dict[str, Any],
    character: "Character | None" = None,
) -> tuple[list[GameEvent], dict[str, Any]]:
    """Resolve DM-emitted game_actions into GameEvents via the engine.

    Each game_action is a dict with:
    - ``function``: "roll_dice" | "request_check" | "attack" | "damage" |
      "roll_initiative" | "cast_spell"
    - ``label``: short description
    - ``args``: function-specific arguments

    Combat actions (attack, damage, roll_initiative) are stateful: they load
    the Encounter from game_state["combat"], mutate it, and persist it back.

    Spell actions (cast_spell) are doubly stateful: they load the Spellbook
    from ``character.spells`` (consuming a real slot), and — when a damage
    spell targets an encounter combatant — also reduce that combatant's HP in
    the Encounter (dual-state coupling). The mutated Spellbook is persisted
    back to ``character.spells``; the caller's ``db.commit()`` persists it.

    Returns (events, updated_game_state) so the caller can persist changes.

    Unknown or malformed actions are logged and skipped (never crash).
    """
    from app.engine.combat import Encounter

    events: list[GameEvent] = []

    # Check if any combat actions are present
    has_combat = any(
        a.get("function") in ("attack", "damage", "roll_initiative")
        for a in game_actions or []
        if isinstance(a, dict)
    )

    # Check if any spell actions are present
    has_spell = any(
        a.get("function") == "cast_spell"
        for a in game_actions or []
        if isinstance(a, dict)
    )

    # Check if any inventory actions are present (Phase 4)
    has_inventory = any(
        a.get("function") in _INVENTORY_ACTIONS
        for a in game_actions or []
        if isinstance(a, dict)
    )

    # Load encounter if combat actions (or spell damage coupling) need it
    encounter: Encounter | None = None
    if has_combat and game_state.get("combat"):
        try:
            encounter = Encounter.from_dict(game_state["combat"])
        except Exception as e:
            logger.error(f"Failed to load encounter from game_state: {e}")

    # An encounter is also useful for spell-damage coupling even without
    # explicit combat actions (a cast_spell targeting a combatant).
    if encounter is None and has_spell and game_state.get("combat"):
        try:
            encounter = Encounter.from_dict(game_state["combat"])
        except Exception as e:
            logger.error(f"Failed to load encounter for spell coupling: {e}")

    # Load spellbook if spell actions exist and a character is available
    spellbook = None
    spellbook_loaded = False
    if has_spell and character is not None:
        try:
            from app.api.spells import _load_spellbook
            spellbook = _load_spellbook(character)
            spellbook_loaded = True
        except Exception as e:
            logger.error(f"Failed to load spellbook for DM spell casting: {e}")

    # Load inventory if inventory actions exist and a character is available
    # (Phase 4). Same load/mutate/persist pattern as the Spellbook.
    inventory = None
    inventory_loaded = False
    if has_inventory and character is not None:
        try:
            from app.api.inventory import _load_inventory
            inventory = _load_inventory(character)
            inventory_loaded = True
        except Exception as e:
            logger.error(f"Failed to load inventory for DM item actions: {e}")

    for action in game_actions or []:
        if not isinstance(action, dict):
            continue
        func = action.get("function", "")
        label = action.get("label", "Unknown")
        args = action.get("args", {})
        if not isinstance(args, dict):
            args = {}
        try:
            if func == "roll_dice":
                sides = args.get("sides", 20)
                modifier = args.get("modifier", 0)
                dc = args.get("dc")
                advantage = args.get("advantage", False)
                disadvantage = args.get("disadvantage", False)
                if sides == 20:
                    events.append(dm_roll_d20(
                        label, modifier, advantage, disadvantage, dc,
                    ))
                else:
                    count = args.get("count", 1)
                    events.append(dm_roll_dice(label, count, sides, modifier))
            elif func == "request_check":
                events.append(dm_request_check(
                    skill=args.get("skill", "Unknown"),
                    dc=args.get("dc"),
                    reason=args.get("reason", ""),
                ))
            elif func == "attack":
                if encounter is None:
                    logger.warning("Skipping attack action: no encounter loaded")
                    continue
                attacker_id = args.get("attacker_id")
                target_id = args.get("target_id")
                attack_index = args.get("attack_index", 0)
                advantage = args.get("advantage", False)
                disadvantage = args.get("disadvantage", False)
                if not attacker_id or not target_id:
                    logger.warning("Skipping attack action: missing attacker_id or target_id")
                    continue
                events.append(dm_attack(
                    encounter=encounter,
                    attacker_id=attacker_id,
                    target_id=target_id,
                    attack_index=attack_index,
                    advantage=advantage,
                    disadvantage=disadvantage,
                ))
            elif func == "damage":
                if encounter is None:
                    logger.warning("Skipping damage action: no encounter loaded")
                    continue
                target_id = args.get("target_id")
                amount = args.get("amount", 0)
                damage_type = args.get("damage_type", "slashing")
                if not target_id:
                    logger.warning("Skipping damage action: missing target_id")
                    continue
                events.append(dm_apply_damage(
                    encounter=encounter,
                    target_id=target_id,
                    amount=amount,
                    damage_type=damage_type,
                ))
            elif func == "roll_initiative":
                if encounter is None:
                    logger.warning("Skipping roll_initiative action: no encounter loaded")
                    continue
                events.append(dm_roll_initiative(encounter=encounter))
            elif func == "cast_spell":
                if character is None:
                    logger.warning(
                        "Skipping cast_spell action: no character available"
                    )
                    continue
                if spellbook is None or not spellbook.is_caster:
                    # Non-caster (or spellbook load failure) — skip gracefully
                    # per the graceful-degradation design decision.
                    logger.warning(
                        "Skipping cast_spell action: character is not a caster"
                    )
                    continue
                spell_id = args.get("spell_id")
                if not spell_id:
                    logger.warning("Skipping cast_spell action: missing spell_id")
                    continue
                target_id = args.get("target_id")
                requested_slot = args.get("slot_level")

                # Resolve target combatant (AC / save) from the encounter, if any
                from app.engine.spells import get_spell as _get_spell
                looked_up = _get_spell(spell_id)
                save_ability = looked_up.save_ability if looked_up else None

                # An attack-roll spell requires a target AC to resolve. If the
                # DM emitted one without a target combatant, fail gracefully
                # (first-class failed-cast event) rather than crashing inside
                # resolve_spell_effect — and without consuming a slot.
                if looked_up and looked_up.requires_attack_roll and (
                    not target_id or encounter is None
                ):
                    events.append(GameEvent.spell_cast(
                        label=f"🔮 {looked_up.name} (cast failed)",
                        spell_name=looked_up.name,
                        spell_id=looked_up.id,
                        level=looked_up.level,
                        school=looked_up.school.value if hasattr(looked_up.school, "value") else str(looked_up.school),
                        slot_level=None,
                        success=False,
                        message=f"{looked_up.name} requires a target to resolve.",
                    ))
                    continue

                target_combatant = None
                target_ac = None
                target_save_total = None
                target_name = ""
                if target_id and encounter is not None:
                    for c in encounter.combatants:
                        if c.id == target_id:
                            target_combatant = c
                            break
                    if target_combatant is not None:
                        target_ac = target_combatant.armor_class
                        target_name = target_combatant.name
                        if save_ability:
                            target_save_total = _combatant_save_total(
                                target_combatant, save_ability
                            )

                caster_mod = _caster_modifier_for_character(character, spellbook)
                active_conditions = game_state.get("conditions", []) or []

                spell_event = dm_cast_spell(
                    spellbook=spellbook,
                    spell_id=spell_id,
                    slot_level=requested_slot,
                    caster_mod=caster_mod,
                    target_ac=target_ac,
                    target_save_total=target_save_total,
                    active_conditions=active_conditions,
                )

                # Attach the target name (dm_cast_spell does not know it).
                if target_name:
                    spell_event.data["target"] = target_name

                # Dual-state coupling: a damage/healing spell targeting an
                # encounter combatant also mutates that combatant's HP.
                if (
                    target_combatant is not None
                    and spell_event.data.get("success")
                ):
                    dmg = spell_event.data.get("damage", 0) or 0
                    heal = spell_event.data.get("healing", 0) or 0
                    if dmg > 0:
                        new_hp = target_combatant.take_damage(dmg)
                        spell_event.data["target_remaining_hp"] = new_hp
                        spell_event.data["target_max_hp"] = target_combatant.max_hp
                    elif heal > 0:
                        new_hp = target_combatant.heal(heal)
                        spell_event.data["target_remaining_hp"] = new_hp
                        spell_event.data["target_max_hp"] = target_combatant.max_hp
                elif (
                    target_combatant is None
                    and spell_event.data.get("success")
                    and (spell_event.data.get("healing", 0) or 0) > 0
                    and character is not None
                ):
                    # Self/utility healing outside combat updates character HP.
                    heal_amt = spell_event.data["healing"]
                    before = int(character.current_hp or 0)
                    max_hp = int(character.max_hp or before)
                    character.current_hp = min(max_hp, before + heal_amt)
                    spell_event.data["target"] = spell_event.data.get("target") or character.name
                    spell_event.data["target_remaining_hp"] = character.current_hp
                    spell_event.data["target_max_hp"] = character.max_hp

                events.append(spell_event)

                # Follow-up DAMAGE event when a combatant took spell damage,
                # mirroring the Phase 2 DamageCard so the combat UI stays
                # consistent (the SpellCastCard shows the spell mechanics +
                # HP bar; the DamageCard surfaces the HP delta).
                if (
                    target_combatant is not None
                    and spell_event.data.get("success")
                    and (spell_event.data.get("damage", 0) or 0) > 0
                ):
                    events.append(GameEvent.damage(
                        label=(
                            f"💥 {target_combatant.name} takes "
                            f"{spell_event.data['damage']} "
                            f"{spell_event.data.get('damage_type', '')} damage"
                        ),
                        target=target_combatant.name,
                        amount=spell_event.data["damage"],
                        damage_type=spell_event.data.get("damage_type", ""),
                        target_remaining_hp=target_combatant.current_hp,
                        target_max_hp=target_combatant.max_hp,
                    ))
            elif func in _INVENTORY_ACTIONS:
                # Phase 4: inventory operations resolved via the real engine.
                if character is None:
                    logger.warning(f"Skipping {func} action: no character available")
                    continue
                if inventory is None or not inventory_loaded:
                    logger.warning(f"Skipping {func} action: no inventory loaded")
                    continue
                if func == "give_item":
                    item_name = args.get("item_name") or args.get("name") or "Unknown Item"
                    event = dm_give_item(
                        inventory=inventory,
                        item_name=item_name,
                        item_type=args.get("item_type", "misc"),
                        quantity=args.get("quantity", 1),
                        rarity=args.get("rarity", "common"),
                        value=args.get("value", 0),
                        description=args.get("description", ""),
                        damage_dice=args.get("damage_dice", ""),
                        damage_type=args.get("damage_type", ""),
                        attack_bonus=args.get("attack_bonus", 0),
                        armor_type=args.get("armor_type", ""),
                        armor_bonus=args.get("armor_bonus", 0),
                        dex_limit=args.get("dex_limit"),
                        uses=args.get("uses", 1),
                        source=args.get("source", ""),
                    )
                    events.append(event)
                elif func == "remove_item":
                    item_id = args.get("item_id")
                    if not item_id:
                        logger.warning("Skipping remove_item action: missing item_id")
                        continue
                    events.append(dm_remove_item(
                        inventory=inventory,
                        item_id=str(item_id),
                        quantity=args.get("quantity", 1),
                    ))
                elif func == "equip_item":
                    item_id = args.get("item_id")
                    if not item_id:
                        logger.warning("Skipping equip_item action: missing item_id")
                        continue
                    event = dm_equip_item(inventory=inventory, item_id=str(item_id))
                    # AC coupling: recompute Armor Class after a successful equip
                    # (same _recalc_armor_class the Inventory API uses).
                    if event.data.get("success"):
                        try:
                            from app.api.inventory import _recalc_armor_class
                            _recalc_armor_class(character, inventory)
                            event.data["ac_after"] = character.armor_class
                        except Exception as e:
                            logger.error(f"AC recalc after equip failed: {e}")
                    events.append(event)
                elif func == "use_item":
                    item_id = args.get("item_id")
                    if not item_id:
                        logger.warning("Skipping use_item action: missing item_id")
                        continue
                    event = dm_use_item(inventory=inventory, item_id=str(item_id))
                    # HP coupling: a healing potion restores HP (2d4+2), mirroring
                    # the Inventory API's use_item endpoint.
                    if event.data.get("success"):
                        iname = (event.data.get("item_name") or "").lower()
                        if "healing" in iname or "potion" in iname:
                            try:
                                heal = roll_dice(2, 4, 2).total
                                before = int(character.current_hp or 0)
                                max_hp = int(character.max_hp or before)
                                character.current_hp = min(max_hp, before + heal)
                                event.data["healing"] = heal
                            except Exception as e:
                                logger.error(f"Healing on use_item failed: {e}")
                    events.append(event)
            else:
                logger.warning(f"Unknown game_action function: {func}")
        except Exception as e:
            logger.error(f"Failed to resolve game action {func}: {e}")

    # Persist spellbook back to character.spells if it was loaded/mutated
    if spellbook_loaded and spellbook is not None:
        try:
            from app.api.spells import _save_spellbook
            _save_spellbook(character, spellbook)
        except Exception as e:
            logger.error(f"Failed to persist spellbook after DM spell casting: {e}")

    # Persist inventory back to character.inventory if it was loaded/mutated
    # (Phase 4). The caller's db.commit() persists the column change.
    if inventory_loaded and inventory is not None:
        try:
            from app.api.inventory import _save_inventory
            _save_inventory(character, inventory)
        except Exception as e:
            logger.error(f"Failed to persist inventory after DM item actions: {e}")

    # Persist encounter back if it was loaded and mutated
    if encounter is not None:
        game_state["combat"] = encounter.to_dict()

    return events, game_state


def _compute_skill_modifier(character: Character, skill: str) -> int:
    """Compute the skill modifier for a character.

    Uses the existing skills engine (ability mod + proficiency/expertise).
    Falls back to 0 for unknown skills.
    """
    try:
        from app.engine.skills import calculate_skill_modifier
        return calculate_skill_modifier(skill, character)
    except (ValueError, Exception) as e:
        logger.warning(f"Could not compute skill modifier for '{skill}': {e}")
        return 0


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


def _generate_action_suggestions(
    narration: str,
) -> list[str]:
    """Generate scene-aware action suggestions based on DM narration.

    Returns:
        List of 4-6 action suggestions, empty list on failure.
    """
    try:
        ensure_dspy_configured()
        module = get_action_suggestions_module()
        result = module(narration=narration)
        suggestions = getattr(result, "action_suggestions", [])
        # Ensure we return a list, filter out empty/None suggestions
        return [s.strip() for s in suggestions if s and s.strip()]
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.error(f"Action suggestions generation failed: {e}")
        return []


def _resolve_skill_check(
    action: str,
    character: Character,
    game_state: dict[str, Any],
    recent_context: str,
) -> dict[str, Any]:
    """Resolve a freeform player action using DSPy skill check resolver.

    This provides structured mechanical outcomes (success, stat changes,
    items gained, XP) for actions that don't map to standard 5e mechanics.

    Returns:
        Dict with resolution data:
        - success: bool
        - degree: str (great_success, success, partial_success, failure, critical_failure)
        - stat_changes: dict
        - items_gained: list
        - experience_gained: int
        - narrative_notes: str
        Empty dict on failure.
    """
    try:
        ensure_dspy_configured()
        module = get_skill_check_resolver_module()

        # Build character context
        character_context = f"""\
Character: {character.name}, Level {character.level} {character.race} {character.char_class}
Ability Scores: STR {character.strength}, DEX {character.dexterity}, CON {character.constitution},
               INT {character.intelligence}, WIS {character.wisdom}, CHA {character.charisma}
HP: {character.current_hp}/{character.max_hp}
AC: {character.armor_class}
Conditions: {', '.join(game_state.get('conditions', ['none']))}
"""
        # Add skill proficiencies if available
        try:
            from app.engine.skills import get_skill_proficiencies
            skill_profs = get_skill_proficiencies(character)
            if skill_profs:
                character_context += f"Skill Proficiencies: {', '.join(sorted(skill_profs))}\n"
        except Exception:
            pass  # Skills not critical

        # Build scene context
        scene_context = f"""\
Location: {game_state.get('location', 'Unknown')}
Recent Events: {recent_context[:500]}  # Truncated for brevity
Active Conditions: {', '.join(game_state.get('conditions', []))}
"""
        result = module(
            action=action,
            character_context=character_context,
            scene_context=scene_context,
        )

        return {
            "success": getattr(result, "success", False),
            "degree": getattr(result, "degree", "failure"),
            "stat_changes": getattr(result, "stat_changes", {}) or {},
            "items_gained": getattr(result, "items_gained", []) or [],
            "experience_gained": getattr(result, "experience_gained", 0) or 0,
            "narrative_notes": getattr(result, "narrative_notes", ""),
        }
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.error(f"Skill check resolution failed: {e}")
        return {}


def _sse(payload: dict) -> str:
    """Format a dict as a Server-Sent Events data line."""
    return f"data: {json.dumps(payload)}\n\n"


class GameCreate(BaseModel):
    name: str = "New Adventure"
    character_id: int
    world_id: int


class PlayerAction(BaseModel):
    action: str


class CheckRequest(BaseModel):
    """Player-initiated check resolution request (from a check_prompt GameEvent)."""
    skill: str
    dc: int | None = None


class DMResponse(BaseModel):
    narration: str
    action_suggestions: list[str] = []
    choices: list[str] | None = None
    combat_active: bool = False
    roll_requested: bool = False
    skill_check_resolution: dict[str, Any] = {}
    game_events: list[dict[str, Any]] = []


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

    # Generate action suggestions
    action_suggestions = _generate_action_suggestions(narration)

    # Save to story log
    story_log = json.loads(save.story_log)
    story_log.append({"role": "dm", "content": narration, "timestamp": utcnow().isoformat()})
    save.story_log = json.dumps(story_log)
    save.game_state = json.dumps(game_state)
    db.commit()

    return {"narration": narration, "action_suggestions": action_suggestions}


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
        action_suggestions: list[str] = []  # Initialize for use in done event

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

                # Generate action suggestions
                action_suggestions = _generate_action_suggestions(narration)

                story_log = json.loads(save.story_log)
                story_log.append({
                    "role": "dm",
                    "content": narration,
                    "timestamp": utcnow().isoformat(),
                })
                save.story_log = json.dumps(story_log)
                save.game_state = json.dumps(game_state)
                db.commit()
        finally:
            db.close()

        yield _sse({"type": "done", "action_suggestions": action_suggestions})

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
{_combatant_roster_for_dm(game_state)}
{_available_spells_for_dm(character)}
{_inventory_for_dm(character)}
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

    narration, game_actions = await _dm_actionable_narrate(situation=user_prompt)
    game_events, game_state = _resolve_game_actions(game_actions, game_state, character=character)

    # Resolve skill check for structured mechanical outcomes
    skill_check_resolution = _resolve_skill_check(
        action=action.action,
        character=character,
        game_state=game_state,
        recent_context=recent_context,
    )

    # Store resolution in game_state if successful
    if skill_check_resolution:
        game_state["skill_check_resolution"] = skill_check_resolution

    # Detect and update quests
    game_state, _info_revealed = _detect_and_update_quests(narration, game_state)

    # Detect and update NPC mood
    game_state = _detect_and_update_npc_mood(narration, game_state)

    # Detect and update game flags
    game_state = _detect_and_update_game_flags(narration, game_state)

    # Generate action suggestions
    action_suggestions = _generate_action_suggestions(narration)

    # Log the exchange
    story_log.append({"role": "player", "content": action.action, "timestamp": utcnow().isoformat()})
    story_log.append({"role": "dm", "content": narration, "timestamp": utcnow().isoformat()})
    save.story_log = json.dumps(story_log)
    save.game_state = json.dumps(game_state)
    save.updated_at = utcnow()

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
        action_suggestions=action_suggestions,
        combat_active=game_state.get("in_combat", False),
        skill_check_resolution=skill_check_resolution or {},
        game_events=[e.to_dict() for e in game_events],
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
{_combatant_roster_for_dm(game_state)}
{_available_spells_for_dm(character)}
{_inventory_for_dm(character)}
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

        # Store character and game_state for skill check resolution in stream
        stored_character = character
        stored_game_state = game_state
        stored_recent_context = recent_context
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
        action_suggestions: list[str] = []  # Initialize for use in done event
        skill_check_resolution: dict[str, Any] = {}  # Initialize for use in done event

        # Resolve skill check for structured mechanical outcomes
        try:
            skill_check_resolution = _resolve_skill_check(
                action=action.action,
                character=stored_character,
                game_state=stored_game_state,
                recent_context=stored_recent_context,
            )
        except Exception:
            skill_check_resolution = {}

        # Persist the exchange once streaming is complete.
        db = session_factory()
        try:
            save = db.query(GameSave).filter(GameSave.id == game_id).first()
            if save:
                log = json.loads(save.story_log)
                now = utcnow().isoformat()
                log.append({"role": "player", "content": action.action, "timestamp": now})
                log.append({"role": "dm", "content": narration, "timestamp": now})
                save.story_log = json.dumps(log)
                save.updated_at = utcnow()

                # Load fresh game_state
                game_state = json.loads(save.game_state)
                stored_game_state = game_state  # Update for later use

                # Store resolution in game_state if successful
                if skill_check_resolution:
                    game_state["skill_check_resolution"] = skill_check_resolution

                # Detect and update quests
                game_state, _info_revealed = _detect_and_update_quests(narration, game_state)

                # Detect and update NPC mood
                game_state = _detect_and_update_npc_mood(narration, game_state)

                # Detect and update game flags
                game_state = _detect_and_update_game_flags(narration, game_state)

                # Generate action suggestions
                action_suggestions = _generate_action_suggestions(narration)

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

        # Resolve game actions (DM function calling Phase 1/2).
        # The streaming path produces narration text via stream_narration_dspy;
        # we make a separate non-streaming call to get structured game_actions.
        game_events: list[GameEvent] = []
        try:
            _, game_actions = await _dm_actionable_narrate(situation=user_prompt)
            game_events, stored_game_state = _resolve_game_actions(
                game_actions, stored_game_state, character=stored_character
            )
        except Exception as e:
            logger.error(f"Game action resolution failed: {e}")

        # Persist updated game_state (combat mutations from DM function calls)
        # and character.spells (slot consumption from DM spell casting).
        db = session_factory()
        try:
            save = db.query(GameSave).filter(GameSave.id == game_id).first()
            if save:
                save.game_state = json.dumps(stored_game_state)
                # Spell casting mutates stored_character.spells; copy it onto
                # the session-attached character so the commit persists it.
                # Inventory actions (Phase 4) mutate stored_character.inventory
                # and may change current_hp (healing potion) / armor_class
                # (equip) — copy those too.
                if stored_character is not None:
                    save.character.spells = stored_character.spells
                    save.character.inventory = stored_character.inventory
                    save.character.current_hp = stored_character.current_hp
                    save.character.armor_class = stored_character.armor_class
                db.commit()
        finally:
            db.close()

        # Emit game_event SSE events before the done event.
        for event in game_events:
            yield _sse({"type": "game_event", "event": event.to_dict()})

        yield _sse({"type": "done", "combat_active": combat_active, "action_suggestions": action_suggestions, "skill_check_resolution": skill_check_resolution, "game_events": [e.to_dict() for e in game_events]})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{game_id}/resolve-check")
def resolve_check(game_id: int, check: CheckRequest, db: Session = Depends(get_db)):
    """Resolve a player-initiated check (from a check_prompt GameEvent).

    The DM emits a ``check_prompt`` event asking the player to roll; the
    frontend renders a roll button. When the player clicks it, this endpoint
    rolls a real d20 using the character's skill modifier and returns the
    result as a ``dice_roll`` GameEvent.
    """
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    character = save.character
    modifier = _compute_skill_modifier(character, check.skill)

    event = dm_roll_d20(
        label=f"{check.skill} Check",
        modifier=modifier,
        dc=check.dc,
    )
    return event.to_dict()


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
