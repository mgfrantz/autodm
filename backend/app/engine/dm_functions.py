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
from app.engine.inventory import (
    ArmorType,
    Inventory,
    Item,
    ItemType,
    Rarity,
)
from app.engine.spells import Spellbook, get_spell, resolve_spell_aoe_target


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


# --- Phase 3.5b: AoE spell functions ---------------------------------------


def dm_cast_spell_aoe(
    spellbook: Spellbook,
    spell_id: str,
    target_specs: list[dict],
    slot_level: int | None = None,
    caster_mod: int = 0,
    active_conditions: list[str] | None = None,
) -> tuple[GameEvent, list[dict]]:
    """Resolve an AoE spell: ONE slot consumed, ONE damage roll, per-target saves.

    This is the multi-target companion to :func:`dm_cast_spell`. Per PHB p.204
    an AoE spell's damage is rolled once and each target makes its own saving
    throw against that shared damage. The spell slot is consumed exactly once
    (via :meth:`Spellbook.prepare_cast`), then each target is resolved
    independently against the single damage roll.

    Args:
        spellbook: The character's live Spellbook (consumes a slot on success).
        spell_id: Spell id or name (e.g. ``"fireball"``).
        target_specs: Per-target descriptors, each a dict with at least
            ``{"name": str}`` and optionally ``{"target_save_total": int}``
            and/or ``{"target_ac": int}``. The caller (which owns the
            Encounter) computes these from each combatant.
        slot_level: Desired slot level for upcasting (``None`` = auto/lowest).
        caster_mod: Casting-ability modifier (INT/WIS/CHA).
        active_conditions: Caster's conditions (may block V/S components).

    Returns:
        ``(summary_event, per_target_results)`` where ``summary_event`` is a
        ``spell_cast`` GameEvent (``is_aoe=True``, no single HP bar) and
        ``per_target_results`` is a list of dicts::

            {"name": str, "damage": int, "made_save": bool | None,
             "half_damage": bool, "damage_type": str}

        The caller applies each target's damage to the matching encounter
        combatant and emits the follow-up DAMAGE events (it owns the
        Encounter; this function does not). On a failed cast (no slots /
        unknown / component-blocked) the summary event carries
        ``success=False`` and ``per_target_results`` is empty.
    """
    sid = _norm_spell_id(spell_id)

    # 1) Consume ONE slot without resolving the effect (AoE splits the two).
    try:
        outcome = spellbook.prepare_cast(
            spell_id=spell_id,
            slot_level=slot_level,
            active_conditions=active_conditions,
        )
    except Exception as exc:  # noqa: BLE001 — never crash the pipeline
        return (
            GameEvent.spell_cast(
                label=f"🔮 {spell_id} (cast failed)",
                spell_name=spell_id,
                spell_id=sid,
                level=0,
                school="",
                slot_level=None,
                success=False,
                message=f"AoE spell cast could not be resolved: {exc}",
            ),
            [],
        )

    if not outcome.success or outcome.spell is None:
        spell_name = spell_id
        looked = get_spell(sid)
        if looked is not None:
            spell_name = looked.name
        return (
            GameEvent.spell_cast(
                label=f"🔮 {spell_name} (cast failed)",
                spell_name=spell_name,
                spell_id=sid,
                level=looked.level if looked is not None else 0,
                school=(
                    looked.school.value
                    if looked is not None and hasattr(looked.school, "value")
                    else (str(looked.school) if looked is not None else "")
                ),
                slot_level=None,
                success=False,
                message=outcome.message,
            ),
            [],
        )

    spell = outcome.spell
    used_slot = outcome.slot_level or 0  # 0 for cantrips; always int after success

    spell_name = spell.name
    school = spell.school.value if hasattr(spell.school, "value") else str(spell.school)
    save_ability = spell.save_ability
    damage_type = spell.damage_type

    # Save DC, computed the same way as dm_cast_spell (8 + prof + caster_mod).
    save_dc: int | None = None
    if save_ability:
        save_dc = 8 + proficiency_bonus(spellbook.level) + caster_mod

    # 2) Roll the spell damage ONCE for the whole AoE (PHB p.204).
    full_damage = (
        spell.roll_damage(spellbook.level, used_slot if used_slot > 0 else None)
        if spell.deals_damage
        else 0
    )

    # 3) Resolve each target independently against the shared damage roll.
    per_target: list[dict] = []
    for spec in target_specs or []:
        name = spec.get("name") or "target"
        target_save_total = spec.get("target_save_total")
        try:
            effect = resolve_spell_aoe_target(
                spell=spell,
                slot_level=used_slot if used_slot > 0 else None,
                full_damage=full_damage,
                target_save_total=target_save_total,
                spell_save_dc=save_dc,
            )
        except Exception:  # noqa: BLE001 — defensive, never crash
            continue
        per_target.append(
            {
                "name": name,
                "damage": effect.damage,
                "made_save": effect.made_save,
                "half_damage": effect.half_damage,
                "damage_type": damage_type,
            }
        )

    total_damage = sum(t["damage"] for t in per_target)
    target_count = len(per_target)

    # Normalise the expended slot for the event (None for cantrips / failed).
    expended_slot = used_slot if (used_slot and used_slot > 0) else None

    label = f"🔮 {spell_name} (AoE × {target_count})" if target_count else f"🔮 {spell_name}"

    summary = GameEvent.spell_cast(
        label=label,
        spell_name=spell_name,
        spell_id=spell.id,
        level=spell.level,
        school=school,
        slot_level=expended_slot,
        success=True,
        save_dc=save_dc,
        save_ability=save_ability,
        damage=full_damage,
        damage_type=damage_type,
        is_aoe=True,
        target_count=target_count,
        total_damage=total_damage,
        message=f"{spell_name} hits {target_count} target(s) for {total_damage} total {damage_type} damage.",
        slots_remaining=spellbook.slots_overview(),
    )
    return summary, per_target


# --- Phase 4: Inventory functions ------------------------------------------


def _norm_item_type(item_type: str) -> ItemType | None:
    """Normalise a DM-supplied item-type string to an ``ItemType``.

    Accepts value (``"weapon"``) and name (``"WEAPON"``) forms, plurals, and
    ``-``/``_``/space separators. Returns ``None`` if the type is unrecognised.
    """
    raw = (item_type or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not raw:
        return ItemType.MISC
    # Singularise a trailing 's' (weapons → weapon) for a closer match.
    candidates = {raw, raw.rstrip("s")}
    for it in ItemType:
        if raw == it.value or raw == it.name.lower():
            return it
    for cand in candidates:
        for it in ItemType:
            if cand == it.value or cand == it.name.lower():
                return it
    return None


def _norm_rarity(rarity: str) -> Rarity:
    """Normalise a rarity string to a ``Rarity`` (defaults to COMMON)."""
    raw = (rarity or "common").strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return Rarity(raw)
    except ValueError:
        return Rarity.COMMON


def _norm_armor_type(armor_type: str) -> ArmorType | None:
    """Normalise an armor-type string to an ``ArmorType`` (``None`` if unset)."""
    raw = (armor_type or "").strip().lower()
    if not raw:
        return None
    try:
        return ArmorType(raw)
    except ValueError:
        return None


def _parse_damage_dice(damage_dice: str) -> tuple[int, int]:
    """Parse a dice notation like ``"1d8"`` → (count, sides).

    Tolerates a trailing modifier (``"2d6+3"``) and bare ``"d8"`` forms.
    """
    if not damage_dice:
        return 0, 0
    text = damage_dice.lower().split("+", 1)[0].strip()
    parts = text.split("d")
    count = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 1
    sides = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 6
    return count, sides


_DEFAULT_WEIGHTS: dict[ItemType, float] = {
    ItemType.WEAPON: 3.0,
    ItemType.ARMOR: 10.0,
    ItemType.POTION: 0.5,
    ItemType.SCROLL: 0.1,
    ItemType.MISC: 1.0,
    ItemType.QUEST: 0.5,
}


def dm_give_item(
    inventory: Inventory,
    item_name: str,
    item_type: str = "misc",
    quantity: int = 1,
    rarity: str = "common",
    value: int = 0,
    description: str = "",
    damage_dice: str = "",
    damage_type: str = "",
    attack_bonus: int = 0,
    armor_type: str = "",
    armor_bonus: int = 0,
    dex_limit: int | None = None,
    uses: int = 1,
    weight: float | None = None,
    source: str = "",
) -> GameEvent:
    """Create an ``Item`` from DM-supplied details and add it to the inventory.

    Constructs a real :class:`Item` (normalising type/rarity/armor/dice) and
    calls ``inventory.add_item()`` (which stacks stackable items). Returns a
    ``loot`` :class:`GameEvent` with ``operation="gained"``.

    Args:
        inventory: The character's live Inventory (loaded by the caller).
        item_name: Display name of the item to create.
        item_type: One of weapon/armor/potion/scroll/misc/quest (case-insensitive).
        quantity: How many to add (stacked for stackable types).
        rarity: common/uncommon/rare/very_rare/legendary.
        value: Value in gold pieces.
        description: Flavour text (doubles as effect text for potions).
        damage_dice: Weapon dice (e.g. ``"1d8"``).
        damage_type: Weapon damage type (e.g. ``"slashing"``).
        attack_bonus: Magic/quality attack bonus.
        armor_type: light/medium/heavy/shield.
        armor_bonus: AC bonus (esp. for shields / magic armor).
        dex_limit: Max Dex bonus for medium/heavy armor.
        uses: Charges for consumables (potions/scrolls).
        weight: Item weight (defaults to a sensible per-type value).
        source: Provenance label (e.g. ``"Goblin loot"``).

    Returns:
        A ``loot`` GameEvent. Failed construction (bad item_type, engine error)
        returns ``success=False`` + a human-readable ``message``.
    """
    name = str(item_name or "Unknown Item")
    try:
        itype = _norm_item_type(item_type)
        if itype is None:
            return GameEvent.loot(
                label=f"🎒 {name} (invalid item)",
                operation="gained",
                item_name=name,
                item_type=str(item_type or ""),
                success=False,
                message=f"Unknown item type: {item_type!r}",
                source=source,
            )
        qty = max(1, int(quantity or 1))
        dice_count, dice_sides = _parse_damage_dice(damage_dice)
        atype = _norm_armor_type(armor_type)
        item_weight = float(weight) if weight is not None else _DEFAULT_WEIGHTS.get(itype, 1.0)
        consumable_uses = max(1, int(uses or 1)) if itype in (ItemType.POTION, ItemType.SCROLL) else 1

        item = Item(
            id="",  # auto-generated
            name=name,
            item_type=itype,
            description=str(description or ""),
            rarity=_norm_rarity(rarity),
            value=int(value or 0),
            weight=item_weight,
            damage_dice_count=dice_count,
            damage_dice_sides=dice_sides,
            damage_bonus=0,
            damage_type=str(damage_type or ""),
            attack_bonus=int(attack_bonus or 0),
            armor_type=atype,
            armor_bonus=int(armor_bonus or 0),
            dex_limit=dex_limit,
            uses=consumable_uses,
            max_uses=consumable_uses,
            quantity=qty,
        )
        slot = inventory.add_item(item)
        stored = slot.item  # the actual persisted item (may be a stacked original)
        return GameEvent.loot(
            label=f"🎁 {name} acquired",
            operation="gained",
            item_name=stored.name,
            item_type=stored.item_type.value,
            item_id=stored.id,
            quantity=qty,
            rarity=stored.rarity.value,
            value=stored.value,
            source=source,
        )
    except Exception as exc:  # noqa: BLE001 — never crash the narration pipeline
        return GameEvent.loot(
            label=f"🎒 {name} (give failed)",
            operation="gained",
            item_name=name,
            item_type=str(item_type or ""),
            success=False,
            message=f"Could not give item: {exc}",
            source=source,
        )


def dm_remove_item(
    inventory: Inventory,
    item_id: str,
    quantity: int = 1,
) -> GameEvent:
    """Remove an existing item from the inventory.

    Calls ``inventory.remove_item()``. Returns a ``loot`` GameEvent with
    ``operation="removed"``. Failed removal (item not found / insufficient
    quantity) returns ``success=False`` with a human-readable ``message``.
    """
    try:
        item = inventory.get_item(item_id)
        if item is None:
            return GameEvent.loot(
                label="🎒 Item not found",
                operation="removed",
                item_name=str(item_id),
                item_type="",
                item_id=str(item_id),
                success=False,
                message=f"Item not found: {item_id}",
            )
        name = item.name
        itype = item.item_type.value
        qty = max(1, int(quantity or 1))
        ok = inventory.remove_item(item_id, qty)
        if not ok:
            return GameEvent.loot(
                label=f"📤 {name} (remove failed)",
                operation="removed",
                item_name=name,
                item_type=itype,
                item_id=str(item_id),
                success=False,
                message=f"Could not remove {name} (insufficient quantity).",
            )
        return GameEvent.loot(
            label=f"📤 {qty}× {name} removed",
            operation="removed",
            item_name=name,
            item_type=itype,
            item_id=str(item_id),
            quantity=qty,
            rarity=item.rarity.value,
            value=item.value,
        )
    except Exception as exc:  # noqa: BLE001 — never crash the narration pipeline
        return GameEvent.loot(
            label="🎒 Remove failed",
            operation="removed",
            item_name=str(item_id),
            item_type="",
            item_id=str(item_id),
            success=False,
            message=f"Could not remove item: {exc}",
        )


def dm_equip_item(
    inventory: Inventory,
    item_id: str,
) -> GameEvent:
    """Equip an existing item (weapon or armor) in the inventory.

    Calls ``inventory.equip_item()`` (which unequips conflicting gear). Returns
    a ``loot`` GameEvent with ``operation="equipped"``. The ``ac_after`` field
    is left as ``None`` — the caller fills it in after recomputing Armor Class.
    Failed equip (not equippable / not found) returns ``success=False``.
    """
    try:
        item = inventory.get_item(item_id)
        if item is None:
            return GameEvent.loot(
                label="🎒 Item not found",
                operation="equipped",
                item_name=str(item_id),
                item_type="",
                item_id=str(item_id),
                success=False,
                message=f"Item not found: {item_id}",
            )
        equipped = inventory.equip_item(item_id)
        if equipped is None:
            return GameEvent.loot(
                label=f"⚔️ {item.name} (not equippable)",
                operation="equipped",
                item_name=item.name,
                item_type=item.item_type.value,
                item_id=str(item_id),
                rarity=item.rarity.value,
                success=False,
                message=f"{item.name} cannot be equipped.",
            )
        return GameEvent.loot(
            label=f"⚔️ Equipped {equipped.name}",
            operation="equipped",
            item_name=equipped.name,
            item_type=equipped.item_type.value,
            item_id=equipped.id,
            rarity=equipped.rarity.value,
            value=equipped.value,
            # ac_after left None — caller fills after _recalc_armor_class().
        )
    except Exception as exc:  # noqa: BLE001 — never crash the narration pipeline
        return GameEvent.loot(
            label=" Equip failed",
            operation="equipped",
            item_name=str(item_id),
            item_type="",
            item_id=str(item_id),
            success=False,
            message=f"Could not equip item: {exc}",
        )


def dm_use_item(
    inventory: Inventory,
    item_id: str,
) -> GameEvent:
    """Use a consumable item (potion, scroll) from the inventory.

    Calls ``inventory.use_item()`` (consumes one charge; removes the item when
    depleted). Returns a ``loot`` GameEvent with ``operation="used"``. The
    ``uses_remaining`` field reflects charges left (``None`` if the item was
    fully consumed and removed). The ``healing`` field is left as ``None`` —
    the caller fills it in after applying the healing effect.
    Failed use (depleted / not consumable / not found) returns
    ``success=False`` with the engine's message.
    """
    try:
        item = inventory.get_item(item_id)
        if item is None:
            return GameEvent.loot(
                label="🎒 Item not found",
                operation="used",
                item_name=str(item_id),
                item_type="",
                item_id=str(item_id),
                success=False,
                message=f"Item not found: {item_id}",
            )
        name = item.name
        itype = item.item_type.value
        ok, msg = inventory.use_item(item_id)
        if not ok:
            return GameEvent.loot(
                label=f"🧪 {name} (use failed)",
                operation="used",
                item_name=name,
                item_type=itype,
                item_id=str(item_id),
                success=False,
                message=msg or f"Could not use {name}.",
            )
        # After use the item may have been consumed (removed from inventory).
        remaining = inventory.get_item(item_id)
        uses_left = remaining.uses if remaining is not None else None
        return GameEvent.loot(
            label=f"🧪 Used {name}",
            operation="used",
            item_name=name,
            item_type=itype,
            item_id=str(item_id),
            rarity=item.rarity.value,
            uses_remaining=uses_left,
            # healing left None — caller fills after applying the effect.
        )
    except Exception as exc:  # noqa: BLE001 — never crash the narration pipeline
        return GameEvent.loot(
            label="🧪 Use failed",
            operation="used",
            item_name=str(item_id),
            item_type="",
            item_id=str(item_id),
            success=False,
            message=f"Could not use item: {exc}",
        )


# --- Phase 5: Condition functions ------------------------------------------ #


def _norm_condition(condition: str) -> str:
    """Normalise a DM-supplied condition string to the registry key form.

    Lowercases, replaces spaces/hyphens with underscores, and strips a trailing
    's' (e.g. ``"Poisoned"`` → ``"poisoned"``, ``"blinded"`` stays). Returns the
    normalised string even if it is not a recognised condition (the caller
    validates against the registry).
    """
    raw = (condition or "").strip().lower().replace(" ", "_").replace("-", "_")
    return raw


def dm_apply_condition(
    target,
    condition: str,
    duration: int | None = None,
) -> GameEvent:
    """Apply a condition to a combatant-like object via the conditions engine.

    Wraps ``conditions.apply_condition(target, condition, duration)``. The
    *target* must be a combatant-like object exposing ``.conditions`` and
    ``.condition_durations`` (a :class:`Combatant` or a player-conditions
    adapter). Returns a ``condition_applied`` :class:`GameEvent` with
    ``operation="applied"``.

    Invalid conditions (not in the 14 core DnD 5e conditions) return a failed
    event with ``success=False`` and a human-readable ``message`` — they never
    raise.

    Args:
        target: A combatant-like object (Combatant or player adapter).
        condition: A condition name (case-insensitive), e.g. ``"poisoned"``.
        duration: Optional duration in rounds (``None`` = permanent).

    Returns:
        A ``condition_applied`` GameEvent.
    """
    from app.engine import conditions as conditions_mod

    name = _norm_condition(condition)
    target_name = getattr(target, "name", "Target")
    if not conditions_mod.is_valid_condition(name):
        return GameEvent.condition_applied(
            label=f"🌀 {condition} (unknown condition)",
            operation="applied",
            condition=name,
            target=target_name,
            success=False,
            message=f"Unknown condition: {condition!r}. Valid conditions: "
                    f"{', '.join(conditions_mod.list_conditions())}",
        )
    try:
        conditions_mod.apply_condition(target, name, duration=duration)
        info = conditions_mod.get_condition_info(name)
        desc = info.get("description", "") if info else ""
        remaining = conditions_mod.remaining_duration(target, name)
        label = f"🌀 {target_name} is now {name}"
        if duration is not None:
            label += f" ({duration} round{'s' if duration != 1 else ''})"
        return GameEvent.condition_applied(
            label=label,
            operation="applied",
            condition=name,
            target=target_name,
            duration=remaining,
            description=desc,
        )
    except Exception as exc:  # noqa: BLE001 — never crash the narration pipeline
        return GameEvent.condition_applied(
            label=f"🌀 {condition} (apply failed)",
            operation="applied",
            condition=name,
            target=target_name,
            success=False,
            message=f"Could not apply {condition}: {exc}",
        )


def dm_remove_condition(
    target,
    condition: str,
) -> GameEvent:
    """Remove a condition from a combatant-like object.

    Wraps ``conditions.remove_condition(target, condition)``. Returns a
    ``condition_applied`` :class:`GameEvent` with ``operation="removed"``. If
    the condition was not present, returns ``success=False``.

    Args:
        target: A combatant-like object (Combatant or player adapter).
        condition: A condition name (case-insensitive).

    Returns:
        A ``condition_applied`` GameEvent.
    """
    from app.engine import conditions as conditions_mod

    name = _norm_condition(condition)
    target_name = getattr(target, "name", "Target")
    if not conditions_mod.is_valid_condition(name):
        return GameEvent.condition_applied(
            label=f"🌀 {condition} (unknown condition)",
            operation="removed",
            condition=name,
            target=target_name,
            success=False,
            message=f"Unknown condition: {condition!r}",
        )
    try:
        removed = conditions_mod.remove_condition(target, name)
        if not removed:
            return GameEvent.condition_applied(
                label=f"🌀 {target_name} did not have {name}",
                operation="removed",
                condition=name,
                target=target_name,
                success=False,
                message=f"{target_name} did not have {name}.",
            )
        info = conditions_mod.get_condition_info(name)
        desc = info.get("description", "") if info else ""
        return GameEvent.condition_applied(
            label=f"🌀 {target_name} is no longer {name}",
            operation="removed",
            condition=name,
            target=target_name,
            description=desc,
        )
    except Exception as exc:  # noqa: BLE001 — never crash the narration pipeline
        return GameEvent.condition_applied(
            label=f"🌀 {condition} (remove failed)",
            operation="removed",
            condition=name,
            target=target_name,
            success=False,
            message=f"Could not remove {condition}: {exc}",
        )


# --- Phase 3.5: Concentration functions ------------------------------------ #


def dm_start_concentration(spell_name: str, spell_id: str) -> GameEvent:
    """Start concentrating on a spell.

    Wraps ``concentration.start_concentration()``. Returns a ``concentration``
    :class:`GameEvent` with ``operation="started"``.

    Args:
        spell_name: Display name of the spell.
        spell_id: Normalised spell id.

    Returns:
        A ``concentration`` GameEvent.
    """
    from app.engine import concentration as conc_mod

    try:
        state = conc_mod.start_concentration(spell_name=spell_name, spell_id=spell_id)
        return GameEvent.concentration(
            label=f"🧠 Concentrating on {state.spell_name}",
            operation="started",
            spell_name=state.spell_name,
            spell_id=state.spell_id,
            reason="Concentration spell cast",
        )
    except Exception as exc:  # noqa: BLE001 — never crash the narration pipeline
        return GameEvent.concentration(
            label="🧠 Concentration (start failed)",
            operation="started",
            spell_name=spell_name,
            spell_id=spell_id,
            success=False,
            message=f"Could not start concentration: {exc}",
        )


def dm_end_concentration(spell_name: str = "", reason: str = "") -> GameEvent:
    """End concentration on a spell.

    Wraps ``concentration.end_concentration()``. Returns a ``concentration``
    :class:`GameEvent` with ``operation="ended"``.

    Args:
        spell_name: The spell that was being concentrated on (for display).
        reason: Why concentration ended (voluntary, replaced, natural end).

    Returns:
        A ``concentration`` GameEvent.
    """
    try:
        conc_end = __import__(
            "app.engine.concentration", fromlist=["end_concentration"]
        ).end_concentration
        conc_end(reason=reason)
        return GameEvent.concentration(
            label=f"🛑 Concentration ended{' on ' + spell_name if spell_name else ''}",
            operation="ended",
            spell_name=spell_name,
            reason=reason or "Concentration ended",
        )
    except Exception as exc:  # noqa: BLE001 — never crash the narration pipeline
        return GameEvent.concentration(
            label="🧠 Concentration (end failed)",
            operation="ended",
            spell_name=spell_name,
            success=False,
            message=f"Could not end concentration: {exc}",
        )


def dm_check_concentration(
    spell_name: str,
    damage_taken: int,
    con_score: int,
    proficiency_bonus: int,
    con_proficient: bool = False,
) -> GameEvent:
    """Roll a concentration check after the concentrating player takes damage.

    Wraps ``concentration.check_concentration()``. Returns a ``concentration``
    :class:`GameEvent` — ``operation="check_passed"`` if the save succeeded
    (concentration holds) or ``operation="check_failed"`` if it failed
    (concentration is lost; the caller clears ``game_state``).

    Args:
        spell_name: The spell being concentrated on (for display).
        damage_taken: Damage dealt to the caster (after resistances).
        con_score: Constitution ability score.
        proficiency_bonus: Character's proficiency bonus.
        con_proficient: Whether the character is proficient in Con saves.

    Returns:
        A ``concentration`` GameEvent.
    """
    from app.engine import concentration as conc_mod
    from app.engine.concentration import ConcentrationState

    # check_concentration needs a ConcentrationState; build one representing an
    # active concentration (the caller only invokes this when concentrating).
    state = ConcentrationState(
        spell_name=spell_name, spell_id="", is_concentrating=True
    )
    try:
        result = conc_mod.check_concentration(
            concentration_state=state,
            damage_taken=damage_taken,
            con_score=con_score,
            proficiency_bonus=proficiency_bonus,
            con_proficient=con_proficient,
        )
        operation = "check_passed" if result.success else "check_failed"
        if result.success:
            label = f"✅ Concentration held on {spell_name}"
        else:
            label = f"⚠️ Concentration lost on {spell_name}"
        return GameEvent.concentration(
            label=label,
            operation=operation,
            spell_name=spell_name,
            reason=result.reason,
            damage_taken=result.damage_taken,
            concentration_dc=result.concentration_dc,
            roll_total=result.roll_total,
        )
    except Exception as exc:  # noqa: BLE001 — never crash the narration pipeline
        return GameEvent.concentration(
            label=f"🧠 Concentration check failed to resolve ({spell_name})",
            operation="check_failed",
            spell_name=spell_name,
            success=False,
            message=f"Concentration check error: {exc}",
        )
