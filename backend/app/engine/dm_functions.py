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
    proficiency_bonus,
    roll_dice as engine_roll_dice,
    roll_d20,
)
from app.engine.game_events import GameEvent
from app.engine.spells import Spellbook


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


# --- Phase 3: Spell functions -----------------------------------------------


def _norm_spell_id(spell_id: str) -> str:
    """Normalise a spell id/name to the registry key form."""
    return (spell_id or "").lower().replace(" ", "_")


def dm_cast_spell(
    spellbook: Spellbook,
    spell_id: str,
    slot_level: int | None = None,
    caster_mod: int = 0,
    target_ac: int | None = None,
    target_save_total: int | None = None,
    active_conditions: list[str] | None = None,
) -> GameEvent:
    """Resolve a spell cast via ``spellbook.cast()``.

    Looks up the spell in the registry, consumes a real spell slot, rolls the
    real attack/damage/save via the spell engine, and returns a ``spell_cast``
    :class:`GameEvent`. If the cast fails (no slots, not known, or
    component-blocked by an active condition), returns a ``spell_cast`` event
    with ``success=False`` and a human-readable ``message``.

    The caller is responsible for:

    * deriving ``caster_mod`` from the character's casting ability,
    * looking up ``target_ac`` / ``target_save_total`` from the encounter, and
    * applying any damage/healing to an encounter combatant (dual-state
      coupling) and augmenting the returned event's HP fields afterwards.

    Args:
        spellbook: The character's live Spellbook (consumes a slot on success).
        spell_id: Spell id or name (e.g. ``"fire_bolt"``, ``"Cure Wounds"``).
        slot_level: Desired slot level for upcasting (``None`` = auto/lowest).
        caster_mod: Casting-ability modifier (INT/WIS/CHA).
        target_ac: Target AC for attack-roll spells.
        target_save_total: Target's save total for saving-throw spells.
        active_conditions: Caster's conditions (may block V/S components).

    Returns:
        A ``spell_cast`` GameEvent describing the full resolution.
    """
    try:
        outcome = spellbook.cast(
            spell_id=spell_id,
            slot_level=slot_level,
            caster_mod=caster_mod,
            target_ac=target_ac,
            target_save_total=target_save_total,
            active_conditions=active_conditions,
        )
    except Exception as exc:  # noqa: BLE001 — never crash the narration pipeline
        # Defensive: resolve_spell_effect raises for attack-roll spells without
        # a target_ac, or on any unexpected engine error. Surface it as a
        # first-class failed-cast event with a human-readable message.
        sid = _norm_spell_id(spell_id)
        return GameEvent.spell_cast(
            label=f"🔮 {spell_id} (cast failed)",
            spell_name=spell_id,
            spell_id=sid,
            level=0,
            school="",
            slot_level=None,
            success=False,
            message=f"Spell cast could not be resolved: {exc}",
        )

    spell = outcome.spell
    effect = outcome.effect

    if spell is not None:
        spell_name = spell.name
        sid = spell.id
        level = spell.level
        school = spell.school.value if hasattr(spell.school, "value") else str(spell.school)
        save_ability = spell.save_ability
        damage_type = effect.damage_type if (effect and effect.damage_type) else spell.damage_type
    else:
        # Unknown spell — degrade gracefully with the raw id.
        spell_name = spell_id
        sid = _norm_spell_id(spell_id)
        level = 0
        school = ""
        save_ability = None
        damage_type = ""

    # Compute the save DC the same way resolve_spell_effect does (8 + prof +
    # casting_mod), since Spellbook.spell_save_dc uses a placeholder ability
    # modifier of 0 and would under-report the real DC.
    save_dc = (
        8 + proficiency_bonus(spellbook.level) + caster_mod
        if (spell is not None and save_ability)
        else None
    )

    # Cantrips report slot_level 0 from the engine; normalise to None so the
    # event carries "no slot expended" (None) for cantrips and failed casts,
    # and the real expended slot level (1-9) for leveled spells.
    expended_slot = outcome.slot_level if (outcome.slot_level and outcome.slot_level > 0) else None

    label = f"🔮 {spell_name}"
    if not outcome.success:
        label = f"🔮 {spell_name} (cast failed)"

    return GameEvent.spell_cast(
        label=label,
        spell_name=spell_name,
        spell_id=sid,
        level=level,
        school=school,
        slot_level=expended_slot,
        success=outcome.success,
        attack_total=effect.rolled_attack if effect else None,
        hit=effect.hit if effect else None,
        made_save=effect.made_save if effect else None,
        save_dc=save_dc,
        save_ability=save_ability,
        damage=effect.damage if effect else 0,
        healing=effect.healing if effect else 0,
        damage_type=damage_type,
        half_damage=effect.half_damage if effect else False,
        message=outcome.message,
        slots_remaining=spellbook.slots_overview() if outcome.success else None,
    )
