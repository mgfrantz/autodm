"""
Attunement engine — magic items that require attunement.

DnD 5e rules:
- Some magic items require attunement to function
- Attunement happens during a short rest (takes 10 minutes)
- A character can attune to at most 3 items at once (increases by 1 for Artificer at 10th/14th/18th level)
- Items must be worn/carried during attunement
- Attunement persists across short rests until explicitly broken
- Long rest doesn't break attunement
- If you die, attunement ends
- Attunement can be broken intentionally during a short rest
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class AttunementStatus(str, Enum):
    """Status of an item's attunement."""
    NOT_REQUIRED = "not_required"
    REQUIRES_ATTUNEMENT = "requires_attunement"
    ATTUNED = "attuned"


@dataclass
class AttunementSlot:
    """An attunement slot tracked by a character."""
    item_id: str
    item_name: str
    attuned_at_round: int = 0  # Combat round when attuned (for tracking when it becomes active)
    requires_specific_class: Optional[str] = None  # e.g., "wizard" for spellbooks

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "item_name": self.item_name,
            "attuned_at_round": self.attuned_at_round,
            "requires_specific_class": self.requires_specific_class,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AttunementSlot":
        return cls(
            item_id=data["item_id"],
            item_name=data["item_name"],
            attuned_at_round=data.get("attuned_at_round", 0),
            requires_specific_class=data.get("requires_specific_class"),
        )


@dataclass
class AttunementInfo:
    """Information about an item's attunement status."""
    status: AttunementStatus
    requires_attunement: bool
    is_attuned: bool
    attunement_slots_used: int
    attunement_slots_max: int
    can_attune: bool
    attunement_reason: str  # Human-readable explanation

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "requires_attunement": self.requires_attunement,
            "is_attuned": self.is_attuned,
            "attunement_slots_used": self.attunement_slots_used,
            "attunement_slots_max": self.attunement_slots_max,
            "can_attune": self.can_attune,
            "attunement_reason": self.attunement_reason,
        }


@dataclass
class AttunementResult:
    """Result of an attunement operation."""
    success: bool
    message: str
    item_id: str
    item_name: str
    attunement_slots_used: int
    attunement_slots_max: int
    attuned_items: list[AttunementSlot]

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "item_id": self.item_id,
            "item_name": self.item_name,
            "attunement_slots_used": self.attunement_slots_used,
            "attunement_slots_max": self.attunement_slots_max,
            "attuned_items": [slot.to_dict() for slot in self.attuned_items],
        }


# --------------------------------------------------------------------------- #
# Core attunement logic
# --------------------------------------------------------------------------- #

def max_attunement_slots(level: int, primary_class: str = "fighter") -> int:
    """Calculate the maximum number of attunement slots for a character.

    Base: 3 slots for all characters
    Artificer bonus: +1 slot at 10th, 14th, and 18th level
    """
    slots = 3

    # Artificer gets extra slots at certain levels
    if primary_class.lower() == "artificer":
        if level >= 18:
            slots += 3
        elif level >= 14:
            slots += 2
        elif level >= 10:
            slots += 1

    return slots


def item_requires_attunement(item: dict) -> bool:
    """Check if an item requires attunement based on its properties.

    An item requires attunement if:
    - Rarity is uncommon or higher (rare, very_rare, legendary)
    - Has magic properties (attack_bonus > 0, armor_bonus > 0, special effects)
    """
    rarity = item.get("rarity", "common").lower()

    # Common items never require attunement
    if rarity == "common":
        return False

    # Uncommon+ items might require attunement
    # For now, we'll mark all uncommon+ items as requiring attunement
    # In a full implementation, this could be a field on the Item itself
    return rarity in ("uncommon", "rare", "very_rare", "legendary")


def get_attunement_info(
    item: dict,
    attuned_items: list[AttunementSlot],
    level: int,
    primary_class: str = "fighter",
) -> AttunementInfo:
    """Get detailed information about an item's attunement status."""
    item_id = item.get("id", "")
    item_name = item.get("name", "Unknown Item")
    requires_att = item_requires_attunement(item)

    slots_max = max_attunement_slots(level, primary_class)
    slots_used = len(attuned_items)

    # Check if already attuned
    is_attuned = any(slot.item_id == item_id for slot in attuned_items)

    # Determine status
    if not requires_att:
        status = AttunementStatus.NOT_REQUIRED
        can_attune = False
        reason = "This item does not require attunement."
    elif is_attuned:
        status = AttunementStatus.ATTUNED
        can_attune = False
        reason = "Already attuned to this item."
    elif slots_used >= slots_max:
        status = AttunementStatus.REQUIRES_ATTUNEMENT
        can_attune = False
        reason = f"Maximum attunement slots reached ({slots_max}/{slots_max}). Break an existing attunement first."
    else:
        status = AttunementStatus.REQUIRES_ATTUNEMENT
        can_attune = True
        reason = f"Can attune ({slots_used}/{slots_max} slots used)."

    return AttunementInfo(
        status=status,
        requires_attunement=requires_att,
        is_attuned=is_attuned,
        attunement_slots_used=slots_used,
        attunement_slots_max=slots_max,
        can_attune=can_attune,
        attunement_reason=reason,
    )


def attune_item(
    item: dict,
    attuned_items: list[AttunementSlot],
    level: int,
    primary_class: str = "fighter",
    current_round: int = 0,
) -> AttunementResult:
    """Attempt to attune to an item.

    Returns an AttunementResult with success status and updated attunement state.
    """
    item_id = item.get("id", "")
    item_name = item.get("name", "Unknown Item")

    info = get_attunement_info(item, attuned_items, level, primary_class)

    if not info.can_attune:
        return AttunementResult(
            success=False,
            message=info.attunement_reason,
            item_id=item_id,
            item_name=item_name,
            attunement_slots_used=info.attunement_slots_used,
            attunement_slots_max=info.attunement_slots_max,
            attuned_items=attuned_items.copy(),
        )

    # Create new attunement slot
    new_slot = AttunementSlot(
        item_id=item_id,
        item_name=item_name,
        attuned_at_round=current_round,
    )

    updated = attuned_items + [new_slot]

    return AttunementResult(
        success=True,
        message=f"Attuned to {item_name}.",
        item_id=item_id,
        item_name=item_name,
        attunement_slots_used=len(updated),
        attunement_slots_max=info.attunement_slots_max,
        attuned_items=updated,
    )


def break_attunement(
    item_id: str,
    attuned_items: list[AttunementSlot],
) -> AttunementResult:
    """Break attunement to an item."""
    # Find the item
    slot = next((s for s in attuned_items if s.item_id == item_id), None)

    if not slot:
        return AttunementResult(
            success=False,
            message="Item is not attuned.",
            item_id=item_id,
            item_name="Unknown",
            attunement_slots_used=len(attuned_items),
            attunement_slots_max=max_attunement_slots(1),
            attuned_items=attuned_items.copy(),
        )

    # Remove the attunement
    updated = [s for s in attuned_items if s.item_id != item_id]

    return AttunementResult(
        success=True,
        message=f"Broken attunement to {slot.item_name}.",
        item_id=item_id,
        item_name=slot.item_name,
        attunement_slots_used=len(updated),
        attunement_slots_max=max_attunement_slots(1),  # Will be updated by caller
        attuned_items=updated,
    )


def break_all_attunements(attuned_items: list[AttunementSlot]) -> list[AttunementSlot]:
    """Break all attunements (e.g., on character death)."""
    return []


def get_attuned_items(attuned_items: list[AttunementSlot]) -> list[str]:
    """Get list of attuned item IDs."""
    return [slot.item_id for slot in attuned_items]