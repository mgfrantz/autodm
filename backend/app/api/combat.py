"""
Combat API — exposes the combat engine via REST endpoints.

Manages combat encounters, turn order, attacks, and combat state persistence.
"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import GameSave, Character
from app.engine.combat import Encounter, Combatant, Attack, AttackResult
from app.engine import conditions as conditions_mod
from app.engine.dice import ability_modifier
from app.engine.leveling import apply_xp
from app.engine.skills import calculate_skill_modifier

router = APIRouter()


class StartCombatRequest(BaseModel):
    """Request to start a combat encounter."""
    enemies: list[dict]  # Each enemy has name, max_hp, armor_class, attacks, etc.


class AttackRequest(BaseModel):
    """Request to make an attack."""
    attacker_id: str  # Combatant ID (player or enemy)
    target_id: str    # Combatant ID to attack
    attack_name: str  # Name of the attack to use
    advantage: bool = False
    disadvantage: bool = False


class ConditionRequest(BaseModel):
    """Request to apply or remove a condition on a combatant."""
    condition: str
    duration: int | None = None  # rounds; None = permanent until removed


@router.post("/{game_id}/combat/start")
def start_combat(game_id: int, request: StartCombatRequest, db: Session = Depends(get_db)):
    """Start a new combat encounter for the given game."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    character = save.character
    game_state = json.loads(save.game_state)

    # Check if already in combat
    if game_state.get("in_combat", False):
        raise HTTPException(status_code=400, detail="Already in combat")

    # Build the encounter
    encounter = Encounter()

    # Derive the player's attacks and Armor Class from their equipped gear.
    # Falls back to class-based stats for characters with no equipment.
    player_attacks, player_ac = _build_player_combat_stats(character)

    # Add the player character
    player_combatant = Combatant(
        id="player",
        name=character.name,
        side="player",
        max_hp=character.max_hp,
        current_hp=character.current_hp,
        armor_class=player_ac,
        initiative_bonus=(character.dexterity - 10) // 2,  # Dex mod
        speed=character.speed,
        # Ability scores + skill bonuses power grapple/shove contests.
        strength=character.strength,
        dexterity=character.dexterity,
        athletics_bonus=_skill_bonus_for_character(character, "athletics"),
        acrobatics_bonus=_skill_bonus_for_character(character, "acrobatics"),
        # Attacks derived from the equipped weapon (equipment-driven combat),
        # or a class-based fallback when no weapon is equipped.
        attacks=player_attacks,
    )
    encounter.add_combatant(player_combatant)

    # Add enemies
    for i, enemy_data in enumerate(request.enemies, start=1):
        enemy_attacks = [Attack(**a) for a in enemy_data.get("attacks", [])]
        enemy = Combatant(
            id=f"enemy_{i}",
            name=enemy_data["name"],
            side="enemy",
            max_hp=enemy_data["max_hp"],
            armor_class=enemy_data["armor_class"],
            initiative_bonus=enemy_data.get("initiative_bonus", 0),
            speed=enemy_data.get("speed", 30),
            attacks=enemy_attacks,
            current_hp=enemy_data.get("current_hp", enemy_data["max_hp"]),
            size=enemy_data.get("size", "medium"),
            strength=enemy_data.get("strength", 10),
            dexterity=enemy_data.get("dexterity", 10),
            athletics_bonus=enemy_data.get("athletics_bonus"),
            acrobatics_bonus=enemy_data.get("acrobatics_bonus"),
            cr=enemy_data.get("cr", 0.0),
        )
        encounter.add_combatant(enemy)

    # Roll initiative and start
    turn_order = encounter.start()

    # Update game state
    game_state["in_combat"] = True
    game_state["combat"] = encounter.to_dict()

    save.game_state = json.dumps(game_state)
    save.updated_at = datetime.utcnow()
    db.commit()

    return {
        "message": "Combat started",
        "turn_order": turn_order,
        "current_turn": encounter.current_combatant.name if encounter.current_combatant else None,
        "round": encounter.round_number,
        "encounter": encounter.to_dict(),
    }


@router.get("/{game_id}/combat/state")
def get_combat_state(game_id: int, db: Session = Depends(get_db)):
    """Get the current combat state for the game."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state = json.loads(save.game_state)

    if not game_state.get("in_combat", False):
        return {"in_combat": False}

    encounter_data = game_state.get("combat", {})
    encounter = Encounter.from_dict(encounter_data)

    return {
        "in_combat": True,
        "is_active": encounter.is_active,
        "winner": encounter.winner,
        "round": encounter.round_number,
        "current_turn": encounter.current_combatant.name if encounter.current_combatant else None,
        "current_turn_id": encounter.current_combatant.id if encounter.current_combatant else None,
        "encounter": encounter.to_dict(),
    }


@router.post("/{game_id}/combat/next-turn")
def next_turn(game_id: int, db: Session = Depends(get_db)):
    """Advance to the next combatant's turn."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state = json.loads(save.game_state)

    if not game_state.get("in_combat", False):
        raise HTTPException(status_code=400, detail="Not in combat")

    encounter = Encounter.from_dict(game_state.get("combat", {}))
    next_combatant = encounter.next_turn()

    # Save updated encounter
    game_state["combat"] = encounter.to_dict()

    # Update character HP if player changed
    player_combatant = next(c for c in encounter.combatants if c.id == "player")
    save.character.current_hp = player_combatant.current_hp

    save.game_state = json.dumps(game_state)
    save.updated_at = datetime.utcnow()
    db.commit()

    # Check if combat ended
    if not encounter.is_active:
        game_state["in_combat"] = False
        save.game_state = json.dumps(game_state)
        db.commit()

        return {
            "message": "Combat ended",
            "winner": encounter.winner,
            "combat_over": True,
        }

    return {
        "message": f"Next turn: {next_combatant.name}" if next_combatant else "No more combatants",
        "current_turn": next_combatant.name if next_combatant else None,
        "current_turn_id": next_combatant.id if next_combatant else None,
        "round": encounter.round_number,
        "encounter": encounter.to_dict(),
    }


@router.post("/{game_id}/combat/attack")
def make_attack(game_id: int, request: AttackRequest, db: Session = Depends(get_db)):
    """Make an attack from one combatant to another."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state = json.loads(save.game_state)

    if not game_state.get("in_combat", False):
        raise HTTPException(status_code=400, detail="Not in combat")

    encounter = Encounter.from_dict(game_state.get("combat", {}))

    # Find combatants
    attacker = next((c for c in encounter.combatants if c.id == request.attacker_id), None)
    target = next((c for c in encounter.combatants if c.id == request.target_id), None)

    if not attacker:
        raise HTTPException(status_code=404, detail=f"Attacker {request.attacker_id} not found")
    if not target:
        raise HTTPException(status_code=404, detail=f"Target {request.target_id} not found")

    # Find the attack
    attack = next((a for a in attacker.attacks if a.name == request.attack_name), None)
    if not attack:
        raise HTTPException(status_code=400, detail=f"Attack '{request.attack_name}' not found")

    # Resolve the attack
    result = encounter.resolve_attack(
        attacker=attacker,
        target=target,
        attack=attack,
        advantage=request.advantage,
        disadvantage=request.disadvantage,
    )

    # Save updated encounter
    game_state["combat"] = encounter.to_dict()

    # Update character HP if player was damaged
    loot_drop = None
    if target.id == "player":
        save.character.current_hp = target.current_hp
    elif attacker.id == "player" and not target.is_alive:
        # Grant XP for the kill (simplified: 50 XP per enemy) and auto-level.
        xp_award = 50
        char = save.character
        con_mod = ability_modifier(char.constitution)
        levelup = apply_xp(
            char_class=char.char_class,
            level=char.level,
            xp_before=char.xp or 0,
            xp_after=(char.xp or 0) + xp_award,
            con_mod=con_mod,
            asi_used=char.asi_used or 0,
        )
        char.xp = levelup.xp
        # Keep the game-save XP mirrored for backward compatibility.
        save.xp = (save.xp or 0) + xp_award
        if levelup.leveled_up:
            char.level = levelup.to_level
            if levelup.hp_gained:
                char.max_hp = (char.max_hp or 0) + levelup.hp_gained
                char.current_hp = (char.current_hp or 0) + levelup.hp_gained
                # Reflect the HP increase on the in-combat player combatant too.
                attacker.max_hp = char.max_hp
                attacker.current_hp = char.current_hp
        # Roll individual treasure loot for the slain enemy (CR-driven) and
        # stage it as pending loot for the player to collect after combat.
        loot_drop = _roll_kill_loot(target)
        if loot_drop is not None:
            _stage_pending_loot(game_state, loot_drop)

    save.game_state = json.dumps(game_state)
    save.updated_at = datetime.utcnow()
    db.commit()

    response = {
        "result": {
            "attacker": attacker.name,
            "target": target.name,
            "attack": request.attack_name,
            "hit": result.hit,
            "critical": result.critical,
            "critical_miss": result.critical_miss,
            "damage": result.damage,
            "target_remaining_hp": result.target_remaining_hp,
            "description": result.description,
        },
        "encounter": encounter.to_dict(),
        "combat_active": encounter.is_active,
        "winner": encounter.winner if not encounter.is_active else None,
    }
    # Surface any loot dropped by the kill so the UI can celebrate it.
    if loot_drop is not None and not loot_drop.is_empty:
        response["loot"] = loot_drop.to_dict()
    return response


@router.post("/{game_id}/combat/end")
def end_combat(game_id: int, db: Session = Depends(get_db)):
    """Manually end the current combat encounter."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state = json.loads(save.game_state)

    if not game_state.get("in_combat", False):
        raise HTTPException(status_code=400, detail="Not in combat")

    game_state["in_combat"] = False
    game_state["combat"] = None
    save.game_state = json.dumps(game_state)
    save.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Combat ended manually"}


@router.get("/{game_id}/combat/conditions")
def list_conditions(game_id: int, db: Session = Depends(get_db)):
    """List all known DnD 5e conditions with their mechanical effects."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")
    return {"conditions": [conditions_mod.get_condition_info(name) for name in conditions_mod.list_conditions()]}


def _load_active_encounter(save: GameSave) -> tuple[dict, Encounter]:
    """Parse a game save's combat state into the raw dict and Encounter."""
    game_state = json.loads(save.game_state)
    if not game_state.get("in_combat", False):
        raise HTTPException(status_code=400, detail="Not in combat")
    encounter = Encounter.from_dict(game_state.get("combat", {}))
    return game_state, encounter


def _persist_encounter(save: GameSave, game_state: dict, encounter: Encounter, db: Session) -> None:
    """Write the encounter back to the save and mirror player HP to the character."""
    game_state["combat"] = encounter.to_dict()
    player_combatant = next((c for c in encounter.combatants if c.id == "player"), None)
    if player_combatant is not None:
        save.character.current_hp = player_combatant.current_hp
    save.game_state = json.dumps(game_state)
    save.updated_at = datetime.utcnow()
    db.commit()


@router.post("/{game_id}/combat/conditions/{combatant_id}")
def apply_condition(
    game_id: int,
    combatant_id: str,
    request: ConditionRequest,
    db: Session = Depends(get_db),
):
    """Apply a condition to a combatant in the active encounter.

    An optional ``duration`` (in rounds) makes the condition expire; omit it for
    a permanent condition that lasts until removed or the encounter ends.
    """
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    if not conditions_mod.is_valid_condition(request.condition):
        raise HTTPException(status_code=400, detail=f"Unknown condition: {request.condition}")

    game_state, encounter = _load_active_encounter(save)
    combatant = next((c for c in encounter.combatants if c.id == combatant_id), None)
    if not combatant:
        raise HTTPException(status_code=404, detail=f"Combatant {combatant_id} not found")

    added = conditions_mod.apply_condition(combatant, request.condition, duration=request.duration)
    _persist_encounter(save, game_state, encounter, db)

    return {
        "message": (
            f"{combatant.name} is now {request.condition}"
            if added
            else f"{combatant.name} remains {request.condition} (duration refreshed)"
        ),
        "combatant": combatant.to_dict(),
    }


@router.delete("/{game_id}/combat/conditions/{combatant_id}")
def remove_condition(
    game_id: int,
    combatant_id: str,
    request: ConditionRequest,
    db: Session = Depends(get_db),
):
    """Remove a condition from a combatant in the active encounter."""
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    if not save:
        raise HTTPException(status_code=404, detail="Game not found")

    game_state, encounter = _load_active_encounter(save)
    combatant = next((c for c in encounter.combatants if c.id == combatant_id), None)
    if not combatant:
        raise HTTPException(status_code=404, detail=f"Combatant {combatant_id} not found")

    removed = conditions_mod.remove_condition(combatant, request.condition)
    _persist_encounter(save, game_state, encounter, db)

    return {
        "message": (
            f"{combatant.name} is no longer {request.condition}"
            if removed
            else f"{combatant.name} did not have {request.condition}"
        ),
        "combatant": combatant.to_dict(),
    }


def _skill_bonus_for_character(character: Character, skill: str) -> int:
    """Compute a skill check bonus (athletics/acrobatics) for a character.

    Delegates to the skills engine so proficiency + expertise are respected,
    with a safe fallback to the plain ability modifier.
    """
    try:
        return calculate_skill_modifier(skill, character)
    except Exception:
        ability = "strength" if skill == "athletics" else "dexterity"
        score = getattr(character, ability, 10) or 10
        return ability_modifier(score)


def _load_character_inventory(character: Character):
    """Load a character's inventory, tolerating missing/corrupt JSON."""
    try:
        data = json.loads(character.inventory)
    except (json.JSONDecodeError, TypeError):
        return None
    if not data:
        return None
    from app.engine.inventory import Inventory
    return Inventory.from_dict(data)


def _roll_kill_loot(target):
    """Roll individual treasure for a slain enemy, keyed by its CR.

    Returns a ``LootResult`` (possibly empty) or ``None`` when the enemy has no
    CR recorded (preserving legacy "no loot" behaviour for CR-less encounters).
    """
    cr = getattr(target, "cr", 0.0) or 0.0
    if cr <= 0:
        return None
    from app.engine.loot import roll_individual_loot
    return roll_individual_loot(cr)


def _stage_pending_loot(game_state: dict, loot_result) -> None:
    """Accumulate a loot drop into the game's ``pending_loot`` ledger.

    The player collects the staged coins/items via the loot API after combat.
    Empty results are ignored so the ledger stays clean.
    """
    if loot_result.is_empty:
        return
    pending = game_state.get("pending_loot")
    if not isinstance(pending, dict):
        pending = {
            "coins": {"cp": 0, "sp": 0, "ep": 0, "gp": 0, "pp": 0},
            "items": [],
        }
    coins = loot_result.coins
    pc = pending["coins"]
    pc["cp"] = pc.get("cp", 0) + coins.cp
    pc["sp"] = pc.get("sp", 0) + coins.sp
    pc["ep"] = pc.get("ep", 0) + coins.ep
    pc["gp"] = pc.get("gp", 0) + coins.gp
    pc["pp"] = pc.get("pp", 0) + coins.pp
    for item in loot_result.items:
        pending["items"].append(item.to_dict())
    game_state["pending_loot"] = pending


def _build_player_combat_stats(character: Character) -> tuple[list[Attack], int]:
    """Derive the player's combat attacks and Armor Class from equipped gear.

    When the character has an equipped weapon, the equipment engine produces
    attacks whose damage dice, attack/damage bonuses, and ranged flag come from
    the actual weapon (plus ability + proficiency + magic enhancement), and the
    Armor Class reflects worn body armor + shield + unarmored defense.

    Characters with no equipped gear fall back to the legacy class-based attack
    list and the character's stored ``armor_class``, preserving the behaviour
    every existing combat test relies on.
    """
    fallback_attacks = _build_attacks_for_class(character.char_class, character.level)
    inventory = _load_character_inventory(character)
    if inventory is None or not inventory.equipped_items:
        # No equipment at all → use the legacy hardcoded stats.
        return fallback_attacks, character.armor_class

    try:
        from app.engine.dice import proficiency_bonus as prof_for_level
        from app.engine.equipment import compute_equipment_combat_stats

        cls = character.primary_class or character.char_class or "commoner"
        stats = compute_equipment_combat_stats(
            inventory,
            strength=character.strength or 10,
            dexterity=character.dexterity or 10,
            constitution=character.constitution or 10,
            wisdom=character.wisdom or 10,
            proficiency=prof_for_level(character.level or 1),
            char_class=cls,
            level=character.level or 1,
        )
        # If a weapon is equipped, use the equipment-derived attacks; otherwise
        # keep the class-based list but still honour the gear-derived AC.
        attacks = stats.attacks if stats.weapon is not None else fallback_attacks
        return attacks, stats.armor_class
    except Exception:
        return fallback_attacks, character.armor_class


def _build_attacks_for_class(char_class: str, level: int) -> list[Attack]:
    """Build a simple attack list based on character class (MVP)."""
    # Simplified attack calculations for MVP
    # In a full implementation, this would use proper DnD mechanics
    proficiency = 1 + (level - 1) // 4  # Proficiency bonus

    attacks: list[Attack] = []

    if char_class.lower() in ["fighter", "paladin", "ranger"]:
        attacks.append(
            Attack(
                name="Longsword",
                attack_bonus=proficiency + 2,  # Str mod approx
                damage_dice_count=1,
                damage_dice_sides=8,
                damage_bonus=2,
                damage_type="slashing",
            )
        )
        if level >= 5:
            # Extra attack
            attacks.append(attacks[0])

    elif char_class.lower() in ["rogue"]:
        attacks.append(
            Attack(
                name="Dagger",
                attack_bonus=proficiency + 3,  # Dex mod approx
                damage_dice_count=1,
                damage_dice_sides=4,
                damage_bonus=3,
                damage_type="piercing",
            )
        )

    elif char_class.lower() in ["wizard", "sorcerer", "warlock"]:
        attacks.append(
            Attack(
                name="Fire Bolt",
                attack_bonus=proficiency + 0,  # No stat mod for cantrip usually
                damage_dice_count=1,
                damage_dice_sides=10,
                damage_bonus=0,
                damage_type="fire",
            )
        )

    elif char_class.lower() in ["cleric", "druid"]:
        attacks.append(
            Attack(
                name="Spiritual Weapon",
                attack_bonus=proficiency + 2,  # Wis mod approx
                damage_dice_count=1,
                damage_dice_sides=8,
                damage_bonus=2,
                damage_type="force",
            )
        )

    elif char_class.lower() in ["barbarian"]:
        attacks.append(
            Attack(
                name="Greataxe",
                attack_bonus=proficiency + 3,  # Str mod approx
                damage_dice_count=1,
                damage_dice_sides=12,
                damage_bonus=3,
                damage_type="slashing",
            )
        )

    elif char_class.lower() in ["monk"]:
        attacks.append(
            Attack(
                name="Unarmed Strike",
                attack_bonus=proficiency + 2,  # Dex mod approx
                damage_dice_count=1,
                damage_dice_sides=6,
                damage_bonus=0,
                damage_type="bludgeoning",
            )
        )

    elif char_class.lower() in ["bard"]:
        attacks.append(
            Attack(
                name="Rapier",
                attack_bonus=proficiency + 2,  # Dex mod approx
                damage_dice_count=1,
                damage_dice_sides=8,
                damage_bonus=2,
                damage_type="piercing",
            )
        )

    else:  # Fallback
        attacks.append(
            Attack(
                name="Club",
                attack_bonus=proficiency + 0,
                damage_dice_count=1,
                damage_dice_sides=4,
                damage_bonus=0,
                damage_type="bludgeoning",
            )
        )

    return attacks