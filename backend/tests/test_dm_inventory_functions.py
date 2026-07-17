"""
Tests for the DM-callable inventory functions (Phase 4) — ``dm_give_item``,
``dm_remove_item``, ``dm_equip_item``, and ``dm_use_item`` wrap the real
``Inventory`` engine and produce ``loot`` GameEvents.
"""
import pytest

from app.engine.game_events import GameEvent, GameEventType
from app.engine.dm_functions import (
    dm_equip_item,
    dm_give_item,
    dm_remove_item,
    dm_use_item,
)
from app.engine.inventory import Inventory, Item, ItemType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_inventory() -> Inventory:
    return Inventory()


# ===========================================================================
# dm_give_item
# ===========================================================================

class TestDmGiveItem:
    """dm_give_item constructs a real Item and adds it to the inventory."""

    def test_give_potion_returns_gained_event(self):
        inv = _empty_inventory()
        event = dm_give_item(
            inv, "Health Potion", item_type="potion",
            quantity=2, rarity="common", value=50,
            description="Restores 2d4+2 HP",
        )
        assert event.type == GameEventType.LOOT
        assert event.data["operation"] == "gained"
        assert event.data["item_name"] == "Health Potion"
        assert event.data["item_type"] == "potion"
        assert event.data["quantity"] == 2
        assert event.data["rarity"] == "common"
        assert event.data["value"] == 50
        assert event.data["success"] is True
        assert event.data["item_id"]  # non-empty id assigned
        assert len(inv.slots) == 1
        assert inv.slots[0].item.name == "Health Potion"

    def test_give_weapon_parses_damage_dice(self):
        inv = _empty_inventory()
        event = dm_give_item(
            inv, "Longsword", item_type="weapon",
            damage_dice="1d8", damage_type="slashing", value=15,
        )
        assert event.data["item_type"] == "weapon"
        weapon = inv.get_item(event.data["item_id"])
        assert weapon is not None
        assert weapon.damage_dice_count == 1
        assert weapon.damage_dice_sides == 8
        assert weapon.damage_type == "slashing"

    def test_give_armor_sets_armor_type(self):
        inv = _empty_inventory()
        event = dm_give_item(
            inv, "Chain Mail", item_type="armor",
            armor_type="heavy", value=75,
        )
        armor = inv.get_item(event.data["item_id"])
        assert armor is not None
        assert armor.armor_type is not None
        assert armor.armor_type.value == "heavy"

    def test_give_potion_with_uses(self):
        inv = _empty_inventory()
        event = dm_give_item(
            inv, "Healing Draught", item_type="potion", uses=2,
        )
        potion = inv.get_item(event.data["item_id"])
        assert potion is not None
        assert potion.uses == 2
        assert potion.max_uses == 2

    def test_give_stacks_consumables(self):
        inv = _empty_inventory()
        dm_give_item(inv, "Health Potion", item_type="potion", quantity=2)
        dm_give_item(inv, "Health Potion", item_type="potion", quantity=1)
        # Stackable → still one slot, quantity 3.
        assert len(inv.slots) == 1
        assert inv.slots[0].item.quantity == 3

    def test_give_item_type_case_insensitive(self):
        inv = _empty_inventory()
        event = dm_give_item(inv, "Scroll", item_type="SCROLL")
        assert event.data["item_type"] == "scroll"
        # Plural form also normalised.
        event2 = dm_give_item(inv, "Club", item_type="weapons")
        assert event2.data["item_type"] == "weapon"

    def test_give_invalid_item_type_fails_gracefully(self):
        inv = _empty_inventory()
        event = dm_give_item(inv, "Garbage", item_type="bogus")
        assert event.data["success"] is False
        assert "bogus" in event.data["message"]
        assert len(inv.slots) == 0


# ===========================================================================
# dm_remove_item
# ===========================================================================

class TestDmRemoveItem:
    """dm_remove_item removes an existing item from the inventory."""

    def test_remove_existing_item(self):
        inv = _empty_inventory()
        give = dm_give_item(inv, "Gold Pouch", item_type="misc", quantity=3)
        item_id = give.data["item_id"]
        event = dm_remove_item(inv, item_id, quantity=2)
        assert event.data["operation"] == "removed"
        assert event.data["success"] is True
        assert event.data["item_name"] == "Gold Pouch"
        assert event.data["quantity"] == 2
        # 3 - 2 = 1 remaining.
        remaining = inv.get_item(item_id)
        assert remaining is not None
        assert remaining.quantity == 1

    def test_remove_removes_slot_when_quantity_reaches_zero(self):
        inv = _empty_inventory()
        give = dm_give_item(inv, "Key", item_type="quest", quantity=1)
        item_id = give.data["item_id"]
        dm_remove_item(inv, item_id, quantity=1)
        assert inv.get_item(item_id) is None

    def test_remove_not_found_fails(self):
        inv = _empty_inventory()
        event = dm_remove_item(inv, "does-not-exist")
        assert event.data["success"] is False
        assert "not found" in event.data["message"].lower()


# ===========================================================================
# dm_equip_item
# ===========================================================================

class TestDmEquipItem:
    """dm_equip_item equips gear via the Inventory engine."""

    def test_equip_weapon(self):
        inv = _empty_inventory()
        give = dm_give_item(inv, "Longsword", item_type="weapon")
        item_id = give.data["item_id"]
        event = dm_equip_item(inv, item_id)
        assert event.data["operation"] == "equipped"
        assert event.data["success"] is True
        assert event.data["item_name"] == "Longsword"
        # ac_after is left to the caller.
        assert event.data["ac_after"] is None
        assert inv.slots[0].equipped is True

    def test_equip_armor(self):
        inv = _empty_inventory()
        give = dm_give_item(
            inv, "Leather Armor", item_type="armor", armor_type="light",
        )
        item_id = give.data["item_id"]
        event = dm_equip_item(inv, item_id)
        assert event.data["success"] is True
        assert inv.equipped_armor is not None

    def test_equip_non_equippable_fails(self):
        inv = _empty_inventory()
        give = dm_give_item(inv, "Health Potion", item_type="potion")
        event = dm_equip_item(inv, give.data["item_id"])
        assert event.data["success"] is False
        assert event.data["message"]

    def test_equip_not_found_fails(self):
        inv = _empty_inventory()
        event = dm_equip_item(inv, "missing")
        assert event.data["success"] is False
        assert "not found" in event.data["message"].lower()


# ===========================================================================
# dm_use_item
# ===========================================================================

class TestDmUseItem:
    """dm_use_item consumes a charge from a consumable."""

    def test_use_consumable_with_charges_left(self):
        inv = _empty_inventory()
        give = dm_give_item(inv, "Healing Elixir", item_type="potion", uses=2)
        item_id = give.data["item_id"]
        event = dm_use_item(inv, item_id)
        assert event.data["operation"] == "used"
        assert event.data["success"] is True
        assert event.data["uses_remaining"] == 1
        # healing is filled by the caller, not dm_use_item.
        assert event.data["healing"] is None

    def test_use_consumes_depleted_item(self):
        inv = _empty_inventory()
        give = dm_give_item(inv, "Minor Potion", item_type="potion", uses=1)
        item_id = give.data["item_id"]
        event = dm_use_item(inv, item_id)
        assert event.data["success"] is True
        # Single-use potion is removed on use → None.
        assert event.data["uses_remaining"] is None
        assert inv.get_item(item_id) is None

    def test_use_non_consumable_fails(self):
        inv = _empty_inventory()
        give = dm_give_item(inv, "Longsword", item_type="weapon")
        event = dm_use_item(inv, give.data["item_id"])
        assert event.data["success"] is False
        assert event.data["message"]

    def test_use_not_found_fails(self):
        inv = _empty_inventory()
        event = dm_use_item(inv, "ghost")
        assert event.data["success"] is False
        assert "not found" in event.data["message"].lower()

    def test_use_depleted_item_fails(self):
        inv = _empty_inventory()
        # Construct a depleted potion directly.
        depleted = Item(
            id="depleted-1", name="Empty Vial",
            item_type=ItemType.POTION, uses=0, max_uses=1, quantity=2,
        )
        inv.add_item(depleted)
        event = dm_use_item(inv, "depleted-1")
        assert event.data["success"] is False
        assert "no uses" in event.data["message"].lower() or "left" in event.data["message"].lower()


# ===========================================================================
# Event shape / serialization
# ===========================================================================

class TestLootEventShape:
    """The returned loot events are well-formed and JSON-serializable."""

    def test_loot_event_is_json_serializable(self):
        import json
        inv = _empty_inventory()
        event = dm_give_item(inv, "Health Potion", item_type="potion", quantity=2)
        parsed = json.loads(json.dumps(event.to_dict()))
        assert parsed["type"] == "loot"
        assert parsed["data"]["operation"] == "gained"
        assert parsed["data"]["item_name"] == "Health Potion"

    def test_failed_event_has_message(self):
        inv = _empty_inventory()
        event = dm_give_item(inv, "X", item_type="bogus")
        assert event.data["success"] is False
        assert isinstance(event.data["message"], str)
        assert event.data["message"]
