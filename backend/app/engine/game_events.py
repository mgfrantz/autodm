"""
GameEvent system — typed structured events produced by DM function calls.

Each event flows from a DM-emitted ``game_action`` through the engine resolver
and ultimately to the frontend as an SSE ``game_event`` payload, where it is
rendered as an inline UI card (dice roll card, check prompt, etc.).

Extensible: new event types for future phases (combat, spells, inventory,
conditions) can be added to :class:`GameEventType` and given a factory
classmethod on :class:`GameEvent`.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class GameEventType(str, Enum):
    """All supported game-event types.

    Inherits ``str`` so values are JSON-serializable directly.
    """

    DICE_ROLL = "dice_roll"
    CHECK_PROMPT = "check_prompt"
    # Phase 2: Combat
    ATTACK = "attack"
    DAMAGE = "damage"
    INITIATIVE = "initiative"
    # Phase 3: Spells
    SPELL_CAST = "spell_cast"
    # Phase 4: Inventory
    LOOT = "loot"
    # Phase 5: Conditions
    CONDITION_APPLIED = "condition_applied"
    # Phase 3.5: Concentration
    CONCENTRATION = "concentration"


@dataclass
class GameEvent:
    """A structured game event produced by DM function calls.

    The ``data`` dict carries type-specific payload fields (dice rolls, DC,
    skill name, etc.) while the top-level ``type`` and ``label`` fields let the
    frontend dispatch to the right UI component without parsing the payload.
    """

    type: GameEventType
    label: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict for SSE / API responses."""
        return {
            "type": self.type.value,
            "label": self.label,
            "data": self.data,
            "timestamp": self.timestamp,
        }

    # --- factory classmethods ---------------------------------------------

    @classmethod
    def dice_roll(
        cls,
        label: str,
        rolls: list[int],
        modifier: int,
        total: int,
        dc: int | None = None,
        success: bool | None = None,
        advantage: bool = False,
        disadvantage: bool = False,
    ) -> "GameEvent":
        """Create a ``dice_roll`` event."""
        return cls(
            type=GameEventType.DICE_ROLL,
            label=label,
            data={
                "rolls": rolls,
                "modifier": modifier,
                "total": total,
                "dc": dc,
                "success": success,
                "advantage": advantage,
                "disadvantage": disadvantage,
            },
        )

    @classmethod
    def check_prompt(
        cls,
        skill: str,
        dc: int | None = None,
        reason: str = "",
    ) -> "GameEvent":
        """Create a ``check_prompt`` event (DM calls for a player roll)."""
        return cls(
            type=GameEventType.CHECK_PROMPT,
            label=f"{skill} Check",
            data={"skill": skill, "dc": dc, "reason": reason},
        )

    @classmethod
    def attack(
        cls,
        label: str,
        attacker: str,
        target: str,
        attack_total: int,
        ac: int,
        hit: bool,
        critical: bool,
        critical_miss: bool,
        damage: int,
        damage_type: str,
        target_remaining_hp: int,
        target_max_hp: int,
    ) -> "GameEvent":
        """Create an ``attack`` event with full to-hit + damage resolution."""
        return cls(
            type=GameEventType.ATTACK,
            label=label,
            data={
                "attacker": attacker,
                "target": target,
                "attack_total": attack_total,
                "ac": ac,
                "hit": hit,
                "critical": critical,
                "critical_miss": critical_miss,
                "damage": damage,
                "damage_type": damage_type,
                "target_remaining_hp": target_remaining_hp,
                "target_max_hp": target_max_hp,
            },
        )

    @classmethod
    def damage(
        cls,
        label: str,
        target: str,
        amount: int,
        damage_type: str,
        target_remaining_hp: int,
        target_max_hp: int,
        made_save: bool | None = None,
        half_damage: bool | None = None,
    ) -> "GameEvent":
        """Create a ``damage`` event (standalone damage application).

        ``made_save`` / ``half_damage`` are optional and used by AoE spell
        damage (Phase 3.5b) to surface each target's saving-throw outcome on
        the DamageCard. They are ``None`` for non-spell damage (traps, falls,
        weapon follow-ups), which renders unchanged.
        """
        data: dict = {
            "target": target,
            "amount": amount,
            "damage_type": damage_type,
            "target_remaining_hp": target_remaining_hp,
            "target_max_hp": target_max_hp,
        }
        if made_save is not None:
            data["made_save"] = made_save
        if half_damage is not None:
            data["half_damage"] = half_damage
        return cls(
            type=GameEventType.DAMAGE,
            label=label,
            data=data,
        )

    @classmethod
    def initiative(cls, label: str, combatants: list[dict]) -> "GameEvent":
        """Create an ``initiative`` event.

        ``combatants`` is a list of dicts in turn order:
        ``[{name, initiative, side}, ...]``
        """
        return cls(
            type=GameEventType.INITIATIVE,
            label=label,
            data={"combatants": combatants},
        )

    @classmethod
    def spell_cast(
        cls,
        label: str,
        spell_name: str,
        spell_id: str,
        level: int,
        school: str,
        slot_level: int | None,
        success: bool,
        attack_total: int | None = None,
        hit: bool | None = None,
        made_save: bool | None = None,
        save_dc: int | None = None,
        save_ability: str | None = None,
        damage: int = 0,
        healing: int = 0,
        damage_type: str = "",
        half_damage: bool = False,
        target: str = "",
        target_remaining_hp: int | None = None,
        target_max_hp: int | None = None,
        message: str = "",
        slots_remaining: list[dict] | None = None,
        is_aoe: bool = False,
        target_count: int | None = None,
        total_damage: int | None = None,
    ) -> "GameEvent":
        """Create a ``spell_cast`` event with full spell resolution + HP tracking.

        Captures the outcome of a DM-emitted ``cast_spell`` game_action resolved
        via the real ``Spellbook.cast()`` engine: the expended slot, to-hit roll
        (attack spells), saving throw (save spells), damage/healing, and — when
        the target is an encounter combatant — its remaining/max HP. Failed
        casts (no slots / unknown / component-blocked) carry ``success=False``
        and a human-readable ``message``.

        AoE casts (Phase 3.5b) set ``is_aoe=True`` and carry ``target_count`` +
        ``total_damage`` (sum across targets); per-target HP then lives in the
        follow-up ``damage`` events, so the AoE summary carries no single HP bar.
        """
        return cls(
            type=GameEventType.SPELL_CAST,
            label=label,
            data={
                "spell_name": spell_name,
                "spell_id": spell_id,
                "level": level,
                "school": school,
                "slot_level": slot_level,
                "success": success,
                "attack_total": attack_total,
                "hit": hit,
                "made_save": made_save,
                "save_dc": save_dc,
                "save_ability": save_ability,
                "damage": damage,
                "healing": healing,
                "damage_type": damage_type,
                "half_damage": half_damage,
                "target": target,
                "target_remaining_hp": target_remaining_hp,
                "target_max_hp": target_max_hp,
                "message": message,
                "slots_remaining": slots_remaining,
                "is_aoe": is_aoe,
                "target_count": target_count,
                "total_damage": total_damage,
            },
        )

    @classmethod
    def loot(
        cls,
        label: str,
        operation: str,
        item_name: str,
        item_type: str,
        item_id: str = "",
        quantity: int = 1,
        rarity: str = "common",
        value: int = 0,
        source: str = "",
        healing: int | None = None,
        ac_after: int | None = None,
        uses_remaining: int | None = None,
        success: bool = True,
        message: str = "",
    ) -> "GameEvent":
        """Create a ``loot`` event (DM function calling Phase 4: inventory).

        Captures the outcome of a DM-emitted ``give_item`` / ``remove_item`` /
        ``equip_item`` / ``use_item`` game_action resolved via the real
        ``Inventory`` engine. ``operation`` is one of ``"gained"``,
        ``"removed"``, ``"equipped"``, ``"used"``. Operation-specific fields:

        * ``healing`` — set when a ``use_item`` healing potion restored HP.
        * ``ac_after`` — set after an ``equip_item`` AC recalculation.
        * ``uses_remaining`` — charges left on a consumable after ``use_item``.

        Failed operations (item not found, not equippable, depleted, etc.)
        carry ``success=False`` and a human-readable ``message``.
        """
        return cls(
            type=GameEventType.LOOT,
            label=label,
            data={
                "operation": operation,
                "item_name": item_name,
                "item_type": item_type,
                "item_id": item_id,
                "quantity": quantity,
                "rarity": rarity,
                "value": value,
                "source": source,
                "healing": healing,
                "ac_after": ac_after,
                "uses_remaining": uses_remaining,
                "success": success,
                "message": message,
            },
        )

    @classmethod
    def condition_applied(
        cls,
        label: str,
        operation: str,
        condition: str,
        target: str,
        target_type: str = "player",
        duration: int | None = None,
        description: str = "",
        success: bool = True,
        message: str = "",
    ) -> "GameEvent":
        """Create a ``condition_applied`` event (DM function calling Phase 5).

        Captures the outcome of a DM-emitted ``apply_condition`` /
        ``remove_condition`` game_action resolved via the real conditions
        engine (``app.engine.conditions``). ``operation`` is one of
        ``"applied"`` or ``"removed"``.

        * ``target`` — display name of the affected creature ("Player",
          "Goblin Brute", etc.).
        * ``target_type`` — ``"player"`` or ``"combatant"``.
        * ``duration`` — rounds remaining (``None`` = permanent until removed).
        * ``description`` — the condition's mechanical effect text.

        Failed operations (unknown condition, condition not present on
        remove) carry ``success=False`` and a human-readable ``message``.
        """
        return cls(
            type=GameEventType.CONDITION_APPLIED,
            label=label,
            data={
                "operation": operation,
                "condition": condition,
                "target": target,
                "target_type": target_type,
                "duration": duration,
                "description": description,
                "success": success,
                "message": message,
            },
        )

    @classmethod
    def concentration(
        cls,
        label: str,
        operation: str,
        spell_name: str = "",
        spell_id: str = "",
        reason: str = "",
        damage_taken: int | None = None,
        concentration_dc: int | None = None,
        roll_total: int | None = None,
        success: bool = True,
        message: str = "",
    ) -> "GameEvent":
        """Create a ``concentration`` event (DM function calling Phase 3.5).

        Captures a change to the player caster's concentration state, wired to
        the real ``concentration.py`` engine. ``operation`` is one of:

        * ``"started"`` — a concentration spell was cast; concentration began.
        * ``"ended"`` — concentration ended (voluntary drop, replaced, or
          natural end).
        * ``"broken"`` — an incapacitating condition broke concentration.
        * ``"check_passed"`` — a damage-triggered Con save was made.
        * ``"check_failed"`` — a damage-triggered Con save was failed;
          concentration was lost.

        Concentration-check fields (``damage_taken``, ``concentration_dc``,
        ``roll_total``) are populated for ``check_passed`` / ``check_failed``
        operations and left ``None`` otherwise. ``reason`` is a human-readable
        explanation of why the concentration state changed.
        """
        return cls(
            type=GameEventType.CONCENTRATION,
            label=label,
            data={
                "operation": operation,
                "spell_name": spell_name,
                "spell_id": spell_id,
                "reason": reason,
                "damage_taken": damage_taken,
                "concentration_dc": concentration_dc,
                "roll_total": roll_total,
                "success": success,
                "message": message,
            },
        )
