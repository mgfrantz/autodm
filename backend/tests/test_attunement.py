"""
Tests for the attunement engine (app.engine.attunement).
"""
import pytest

from app.engine.attunement import (
    attune_item,
    break_attunement,
    break_all_attunements,
    get_attunement_info,
    max_attunement_slots,
    item_requires_attunement,
    AttunementSlot,
    AttunementInfo,
    AttunementResult,
    AttunementStatus,
)


# --------------------------------------------------------------------------- #
# max_attunement_slots tests
# --------------------------------------------------------------------------- #

class TestMaxAttunementSlots:
    """Test maximum attunement slot calculation."""

    def test_base_slots(self):
        """All characters get at least 3 slots."""
        assert max_attunement_slots(1, "fighter") == 3
        assert max_attunement_slots(5, "wizard") == 3
        assert max_attunement_slots(10, "rogue") == 3
        assert max_attunement_slots(20, "cleric") == 3

    def test_artificer_bonus_slots(self):
        """Artificer gets bonus slots at certain levels."""
        # Level 1-9: 3 slots (base)
        assert max_attunement_slots(1, "artificer") == 3
        assert max_attunement_slots(9, "artificer") == 3

        # Level 10-13: 4 slots (+1 bonus)
        assert max_attunement_slots(10, "artificer") == 4
        assert max_attunement_slots(13, "artificer") == 4

        # Level 14-17: 5 slots (+2 bonus)
        assert max_attunement_slots(14, "artificer") == 5
        assert max_attunement_slots(17, "artificer") == 5

        # Level 18-20: 6 slots (+3 bonus)
        assert max_attunement_slots(18, "artificer") == 6
        assert max_attunement_slots(20, "artificer") == 6


# --------------------------------------------------------------------------- #
# item_requires_attunement tests
# --------------------------------------------------------------------------- #

class TestItemRequiresAttunement:
    """Test attunement requirement detection."""

    def test_common_items_no_attunement(self):
        """Common items never require attunement."""
        assert not item_requires_attunement({"rarity": "common", "attack_bonus": 0})
        assert not item_requires_attunement({"rarity": "common", "armor_bonus": 5})

    def test_uncommon_plus_requires_attunement(self):
        """Uncommon+ items require attunement."""
        assert item_requires_attunement({"rarity": "uncommon"})
        assert item_requires_attunement({"rarity": "rare"})
        assert item_requires_attunement({"rarity": "very_rare"})
        assert item_requires_attunement({"rarity": "legendary"})

    def test_case_insensitive_rarity(self):
        """Rarity check is case-insensitive."""
        assert item_requires_attunement({"rarity": "UNCOMMON"})
        assert item_requires_attunement({"rarity": "Rare"})
        assert item_requires_attunement({"rarity": "VERY_RARE"})


# --------------------------------------------------------------------------- #
# get_attunement_info tests
# --------------------------------------------------------------------------- #

class TestGetAttunementInfo:
    """Test attunement information retrieval."""

    def test_not_required(self):
        """Items that don't require attunement."""
        info = get_attunement_info(
            item={"id": "item1", "name": "Iron Sword", "rarity": "common"},
            attuned_items=[],
            level=5,
        )
        assert info.status == AttunementStatus.NOT_REQUIRED
        assert not info.requires_attunement
        assert not info.is_attuned
        assert not info.can_attune
        assert "does not require attunement" in info.attunement_reason.lower()

    def test_requires_attunement_not_yet_attuned(self):
        """Items requiring attunement, not yet attuned."""
        info = get_attunement_info(
            item={"id": "item1", "name": "+1 Longsword", "rarity": "uncommon"},
            attuned_items=[],
            level=5,
        )
        assert info.status == AttunementStatus.REQUIRES_ATTUNEMENT
        assert info.requires_attunement
        assert not info.is_attuned
        assert info.can_attune
        assert info.attunement_slots_used == 0
        assert info.attunement_slots_max == 3

    def test_already_attuned(self):
        """Items already attuned."""
        slot = AttunementSlot(item_id="item1", item_name="+1 Longsword")
        info = get_attunement_info(
            item={"id": "item1", "name": "+1 Longsword", "rarity": "uncommon"},
            attuned_items=[slot],
            level=5,
        )
        assert info.status == AttunementStatus.ATTUNED
        assert info.requires_attunement
        assert info.is_attuned
        assert not info.can_attune
        assert "already attuned" in info.attunement_reason.lower()

    def test_max_slots_reached(self):
        """Cannot attune when all slots are used."""
        slots = [
            AttunementSlot(item_id="item1", item_name="Ring of Protection"),
            AttunementSlot(item_id="item2", item_name="Amulet of Strength"),
            AttunementSlot(item_id="item3", item_name="Cloak of Elvenkind"),
        ]
        info = get_attunement_info(
            item={"id": "item4", "name": "Boots of Speed", "rarity": "rare"},
            attuned_items=slots,
            level=5,
        )
        assert info.status == AttunementStatus.REQUIRES_ATTUNEMENT
        assert info.requires_attunement
        assert not info.is_attuned
        assert not info.can_attune
        assert info.attunement_slots_used == 3
        assert info.attunement_slots_max == 3
        assert "maximum" in info.attunement_reason.lower()

    def test_artificer_extra_slots(self):
        """Artificer gets extra attunement slots."""
        slots = [
            AttunementSlot(item_id="item1", item_name="Ring of Protection"),
            AttunementSlot(item_id="item2", item_name="Amulet of Strength"),
            AttunementSlot(item_id="item3", item_name="Cloak of Elvenkind"),
        ]
        info = get_attunement_info(
            item={"id": "item4", "name": "Boots of Speed", "rarity": "rare"},
            attuned_items=slots,
            level=15,
            primary_class="artificer",
        )
        assert info.attunement_slots_max == 5  # 3 base + 2 bonus
        assert info.can_attune  # 3 < 5 slots


# --------------------------------------------------------------------------- #
# attune_item tests
# --------------------------------------------------------------------------- #

class TestAttuneItem:
    """Test item attunement."""

    def test_attune_success(self):
        """Successfully attune to an item."""
        result = attune_item(
            item={"id": "item1", "name": "+1 Longsword", "rarity": "uncommon"},
            attuned_items=[],
            level=5,
        )
        assert result.success
        assert result.item_id == "item1"
        assert result.item_name == "+1 Longsword"
        assert result.attunement_slots_used == 1
        assert result.attunement_slots_max == 3
        assert len(result.attuned_items) == 1
        assert result.attuned_items[0].item_id == "item1"

    def test_attune_multiple(self):
        """Attune to multiple items."""
        result1 = attune_item(
            item={"id": "item1", "name": "+1 Longsword", "rarity": "uncommon"},
            attuned_items=[],
            level=5,
        )
        result2 = attune_item(
            item={"id": "item2", "name": "+2 Shield", "rarity": "rare"},
            attuned_items=result1.attuned_items,
            level=5,
        )
        assert result2.success
        assert result2.attunement_slots_used == 2
        assert len(result2.attuned_items) == 2

    def test_attune_max_slots(self):
        """Cannot attune beyond max slots."""
        slots = [
            AttunementSlot(item_id="item1", item_name="Ring 1"),
            AttunementSlot(item_id="item2", item_name="Ring 2"),
        ]
        result = attune_item(
            item={"id": "item3", "name": "Amulet", "rarity": "rare"},
            attuned_items=slots,
            level=5,
        )
        assert result.success
        assert result.attunement_slots_used == 3

        # Try to add a 4th - should fail
        result4 = attune_item(
            item={"id": "item4", "name": "Boots", "rarity": "rare"},
            attuned_items=result.attuned_items,
            level=5,
        )
        assert not result4.success
        assert "maximum" in result4.message.lower()

    def test_attune_already_attuned(self):
        """Cannot attune to an item you already have attuned."""
        slot = AttunementSlot(item_id="item1", item_name="+1 Longsword")
        result = attune_item(
            item={"id": "item1", "name": "+1 Longsword", "rarity": "uncommon"},
            attuned_items=[slot],
            level=5,
        )
        assert not result.success
        assert "already attuned" in result.message.lower()

    def test_attune_not_required(self):
        """Cannot attune to items that don't require attunement."""
        result = attune_item(
            item={"id": "item1", "name": "Iron Sword", "rarity": "common"},
            attuned_items=[],
            level=5,
        )
        assert not result.success
        assert "does not require attunement" in result.message.lower()

    def test_attune_tracks_round(self):
        """Attunement tracks the round it was performed."""
        result = attune_item(
            item={"id": "item1", "name": "+1 Longsword", "rarity": "uncommon"},
            attuned_items=[],
            level=5,
            current_round=42,
        )
        assert result.attuned_items[0].attuned_at_round == 42


# --------------------------------------------------------------------------- #
# break_attunement tests
# --------------------------------------------------------------------------- #

class TestBreakAttunement:
    """Test attunement breaking."""

    def test_break_success(self):
        """Successfully break attunement."""
        slots = [
            AttunementSlot(item_id="item1", item_name="+1 Longsword"),
            AttunementSlot(item_id="item2", item_name="+2 Shield"),
        ]
        result = break_attunement("item1", slots)
        assert result.success
        assert result.item_id == "item1"
        assert result.item_name == "+1 Longsword"
        assert result.attunement_slots_used == 1
        assert len(result.attuned_items) == 1
        assert result.attuned_items[0].item_id == "item2"

    def test_break_not_attuned(self):
        """Cannot break attunement to an item not attuned."""
        slots = [AttunementSlot(item_id="item1", item_name="+1 Longsword")]
        result = break_attunement("item2", slots)
        assert not result.success
        assert "not attuned" in result.message.lower()

    def test_break_last_item(self):
        """Break attunement to the last item."""
        slots = [AttunementSlot(item_id="item1", item_name="+1 Longsword")]
        result = break_attunement("item1", slots)
        assert result.success
        assert result.attunement_slots_used == 0
        assert len(result.attuned_items) == 0


# --------------------------------------------------------------------------- #
# break_all_attunements tests
# --------------------------------------------------------------------------- #

class TestBreakAllAttunements:
    """Test breaking all attunements."""

    def test_break_all(self):
        """Break all attunements at once."""
        slots = [
            AttunementSlot(item_id="item1", item_name="+1 Longsword"),
            AttunementSlot(item_id="item2", item_name="+2 Shield"),
            AttunementSlot(item_id="item3", item_name="Ring of Protection"),
        ]
        result = break_all_attunements(slots)
        assert result == []

    def test_break_empty(self):
        """Breaking empty attunements is safe."""
        assert break_all_attunements([]) == []


# --------------------------------------------------------------------------- #
# AttunementSlot tests
# --------------------------------------------------------------------------- #

class TestAttunementSlot:
    """Test AttunementSlot serialization."""

    def test_to_dict(self):
        """Serialize to dictionary."""
        slot = AttunementSlot(
            item_id="item1",
            item_name="+1 Longsword",
            attuned_at_round=42,
            requires_specific_class="wizard",
        )
        data = slot.to_dict()
        assert data["item_id"] == "item1"
        assert data["item_name"] == "+1 Longsword"
        assert data["attuned_at_round"] == 42
        assert data["requires_specific_class"] == "wizard"

    def test_from_dict(self):
        """Deserialize from dictionary."""
        data = {
            "item_id": "item1",
            "item_name": "+1 Longsword",
            "attuned_at_round": 42,
            "requires_specific_class": "wizard",
        }
        slot = AttunementSlot.from_dict(data)
        assert slot.item_id == "item1"
        assert slot.item_name == "+1 Longsword"
        assert slot.attuned_at_round == 42
        assert slot.requires_specific_class == "wizard"

    def test_roundtrip(self):
        """Round-trip serialization."""
        original = AttunementSlot(
            item_id="item1",
            item_name="+1 Longsword",
            attuned_at_round=42,
        )
        roundtrip = AttunementSlot.from_dict(original.to_dict())
        assert roundtrip.item_id == original.item_id
        assert roundtrip.item_name == original.item_name
        assert roundtrip.attuned_at_round == original.attuned_at_round


# --------------------------------------------------------------------------- #
# AttunementInfo tests
# --------------------------------------------------------------------------- #

class TestAttunementInfo:
    """Test AttunementInfo serialization."""

    def test_to_dict(self):
        """Serialize to dictionary."""
        info = AttunementInfo(
            status=AttunementStatus.ATTUNED,
            requires_attunement=True,
            is_attuned=True,
            attunement_slots_used=2,
            attunement_slots_max=3,
            can_attune=False,
            attunement_reason="Already attuned to this item.",
        )
        data = info.to_dict()
        assert data["status"] == "attuned"
        assert data["requires_attunement"] is True
        assert data["is_attuned"] is True
        assert data["attunement_slots_used"] == 2
        assert data["attunement_slots_max"] == 3
        assert data["can_attune"] is False


# --------------------------------------------------------------------------- #
# AttunementResult tests
# --------------------------------------------------------------------------- #

class TestAttunementResult:
    """Test AttunementResult serialization."""

    def test_to_dict(self):
        """Serialize to dictionary."""
        slot = AttunementSlot(item_id="item1", item_name="+1 Longsword")
        result = AttunementResult(
            success=True,
            message="Attuned to +1 Longsword.",
            item_id="item1",
            item_name="+1 Longsword",
            attunement_slots_used=1,
            attunement_slots_max=3,
            attuned_items=[slot],
        )
        data = result.to_dict()
        assert data["success"] is True
        assert data["message"] == "Attuned to +1 Longsword."
        assert data["item_id"] == "item1"
        assert data["attunement_slots_used"] == 1
        assert data["attunement_slots_max"] == 3
        assert len(data["attuned_items"]) == 1
        assert data["attuned_items"][0]["item_id"] == "item1"