"""
DM-callable game functions.

Each function is a thin wrapper around an existing engine function that
returns a :class:`GameEvent` suitable for frontend rendering. Phase 1 covers
dice rolling and check prompts; Phase 2 adds combat functions wrapping the
``Encounter`` engine.
"""
from app.engine.combat import Attack, AttackResult, Combatant, Encounter
from app.engine.dice import (
    RollResult,
    roll_dice as engine_roll_dice,
    roll_d20,
)
from app.engine.game_events import GameEvent


def dm_roll_d20(
    label: str,
    modifier: int = 0,
    advantage: bool = False,
    disadvantage: bool = False,
    dc: int | None = None,
) -> GameEvent:
    """Roll a d20 for a check, save, or attack.

    Returns a ``dice_roll`` :class:`GameEvent`.
    """
    result = roll_d20(modifier=modifier, advantage=advantage, disadvantage=disadvantage)
    success: bool | None = None
    if dc is not None:
        success = result.total >= dc
    return GameEvent.dice_roll(
        label=label,
        rolls=result.rolls,
        modifier=result.modifier,
        total=result.total,
        dc=dc,
        success=success,
        advantage=advantage,
        disadvantage=disadvantage,
    )


def dm_roll_dice(
    label: str,
    count: int,
    sides: int,
    modifier: int = 0,
) -> GameEvent:
    """Roll arbitrary dice (e.g. 3d6 for damage).

    Returns a ``dice_roll`` :class:`GameEvent`.
    """
    result = engine_roll_dice(count, sides, modifier)
    return GameEvent.dice_roll(
        label=label,
        rolls=result.rolls,
        modifier=result.modifier,
        total=result.total,
    )


def dm_request_check(
    skill: str,
    dc: int | None = None,
    reason: str = "",
) -> GameEvent:
    """The DM calls for a player-initiated check.

    Returns a ``check_prompt`` :class:`GameEvent` — no roll yet, the frontend
    renders a roll button and calls ``POST /resolve-check`` when the player
    clicks it.
    """
    return GameEvent.check_prompt(skill=skill, dc=dc, reason=reason)


# --- Phase 2: Combat functions ----------------------------------------------

def dm_attack(
    encounter: Encounter,
    attacker_id: str,
    target_id: str,
    attack_index: int = 0,
    advantage: bool = False,
    disadvantage: bool = False,
) -> GameEvent:
    """Resolve an attack via encounter.resolve_attack().

    Looks up Combatant objects by id, selects the Attack by index,
    and returns an ``attack`` GameEvent with full resolution.

    Args:
        encounter: The live Encounter object (already loaded from game_state).
        attacker_id: ID of the attacking combatant.
        target_id: ID of the target combatant.
        attack_index: Index into attacker.attacks list (default 0 for primary).
        advantage: Whether the attack has advantage.
        disadvantage: Whether the attack has disadvantage.

    Returns:
        An ``attack`` GameEvent with to-hit roll, damage, and HP updates.

    Raises:
        ValueError: If attacker_id or target_id is not found, or if attack_index
            is out of range.
    """
    # Look up combatants by ID
    attacker = None
    target = None
    for combatant in encounter.combatants:
        if combatant.id == attacker_id:
            attacker = combatant
        if combatant.id == target_id:
            target = combatant

    if attacker is None:
        raise ValueError(f"Attacker not found: {attacker_id}")
    if target is None:
        raise ValueError(f"Target not found: {target_id}")

    # Select the attack
    if attack_index < 0 or attack_index >= len(attacker.attacks):
        raise ValueError(
            f"Attack index {attack_index} out of range for {attacker.name} "
            f"(has {len(attacker.attacks)} attacks)"
        )
    attack = attacker.attacks[attack_index]

    # Resolve the attack via the Encounter engine
    result: AttackResult = encounter.resolve_attack(
        attacker=attacker,
        target=target,
        attack=attack,
        advantage=advantage,
        disadvantage=disadvantage,
    )

    # Build a descriptive label
    label = f"{attacker.name} → {target.name}"
    if result.hit:
        if result.critical:
            label = f"⚔️ {attacker.name} → {target.name} (CRITICAL!)"
        else:
            label = f"⚔️ {attacker.name} → {target.name}"
    else:
        if result.critical_miss:
            label = f"⚔️ {attacker.name} → {target.name} (FUMBLE!)"
        else:
            label = f"⚔️ {attacker.name} → {target.name} (Miss)"

    # Return the attack GameEvent
    return GameEvent.attack(
        label=label,
        attacker=attacker.name,
        target=target.name,
        attack_total=result.attack_total,
        ac=target.armor_class,
        hit=result.hit,
        critical=result.critical,
        critical_miss=result.critical_miss,
        damage=result.damage,
        damage_type=attack.damage_type,
        target_remaining_hp=result.target_remaining_hp,
        target_max_hp=target.max_hp,
    )


def dm_apply_damage(
    encounter: Encounter,
    target_id: str,
    amount: int,
    damage_type: str = "slashing",
) -> GameEvent:
    """Apply direct damage to a combatant (no to-hit roll).

    Handles death at 0 HP. Returns a ``damage`` GameEvent.

    Args:
        encounter: The live Encounter object (already loaded from game_state).
        target_id: ID of the target combatant.
        amount: Damage amount to apply.
        damage_type: Type of damage (slashing, fire, etc.).

    Returns:
        A ``damage`` GameEvent with HP update.

    Raises:
        ValueError: If target_id is not found.
    """
    # Look up combatant by ID
    target = None
    for combatant in encounter.combatants:
        if combatant.id == target_id:
            target = combatant
            break

    if target is None:
        raise ValueError(f"Target not found: {target_id}")

    # Apply damage
    new_hp = target.take_damage(amount)

    # Build a descriptive label
    label = f"💥 {target.name} takes {amount} {damage_type} damage"

    return GameEvent.damage(
        label=label,
        target=target.name,
        amount=amount,
        damage_type=damage_type,
        target_remaining_hp=new_hp,
        target_max_hp=target.max_hp,
    )


def dm_roll_initiative(encounter: Encounter) -> GameEvent:
    """Roll initiative for all combatants via encounter.roll_initiative().

    Returns an ``initiative`` GameEvent with the full turn order.

    Args:
        encounter: The live Encounter object (already loaded from game_state).

    Returns:
        An ``initiative`` GameEvent with combatants sorted by initiative.
    """
    # Roll initiative for all combatants
    for combatant in encounter.combatants:
        combatant.roll_initiative()

    # Sort by initiative (descending), then by Dex modifier for ties
    sorted_combatants = sorted(
        encounter.combatants,
        key=lambda c: (-c.initiative, -c.initiative_bonus)
    )

    # Build the turn order dict list
    combatants_list = [
        {
            "id": c.id,
            "name": c.name,
            "initiative": c.initiative,
            "side": c.side,
        }
        for c in sorted_combatants
    ]

    # Update the encounter's turn order (for future turns)
    encounter.turn_order = sorted_combatants
    encounter.started = True

    return GameEvent.initiative(
        label="🎯 Initiative Order",
        combatants=combatants_list,
    )
