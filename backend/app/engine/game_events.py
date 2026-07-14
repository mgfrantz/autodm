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
    # Future phases:
    # ATTACK = "attack"
    # DAMAGE = "damage"
    # SPELL_CAST = "spell_cast"
    # LOOT = "loot"
    # CONDITION_APPLIED = "condition_applied"


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
