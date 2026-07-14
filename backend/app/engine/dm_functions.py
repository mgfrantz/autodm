"""
DM-callable game functions.

Each function is a thin wrapper around an existing engine function that
returns a :class:`GameEvent` suitable for frontend rendering. Phase 1 covers
dice rolling and check prompts; future phases will add combat, spells,
inventory, and condition functions.
"""
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
