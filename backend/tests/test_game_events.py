"""
Tests for the GameEvent system — construction, serialization, factory
classmethods, enum values, and JSON round-trip.
"""
import json
from datetime import datetime

import pytest

from app.engine.game_events import GameEvent, GameEventType


class TestGameEventType:
    """GameEventType enum is string-valued and JSON-serializable."""

    def test_enum_values_are_strings(self):
        assert GameEventType.DICE_ROLL.value == "dice_roll"
        assert GameEventType.CHECK_PROMPT.value == "check_prompt"

    def test_enum_is_json_serializable(self):
        data = {"type": GameEventType.DICE_ROLL.value}
        assert json.dumps(data) == '{"type": "dice_roll"}'


class TestGameEventConstruction:
    """Direct GameEvent construction + to_dict()."""

    def test_basic_construction(self):
        event = GameEvent(
            type=GameEventType.DICE_ROLL,
            label="Perception Check",
            data={"rolls": [18], "modifier": 3, "total": 21},
        )
        assert event.type == GameEventType.DICE_ROLL
        assert event.label == "Perception Check"
        assert event.data["rolls"] == [18]
        assert event.data["total"] == 21

    def test_timestamp_is_set_automatically(self):
        event = GameEvent(type=GameEventType.DICE_ROLL, label="Test")
        assert event.timestamp != ""
        # Should be a valid ISO format string
        datetime.fromisoformat(event.timestamp)

    def test_explicit_timestamp_is_preserved(self):
        ts = "2025-07-14T12:00:00+00:00"
        event = GameEvent(type=GameEventType.DICE_ROLL, label="Test", timestamp=ts)
        assert event.timestamp == ts

    def test_to_dict_serialization(self):
        event = GameEvent(
            type=GameEventType.CHECK_PROMPT,
            label="Perception Check",
            data={"skill": "Perception", "dc": 15},
        )
        d = event.to_dict()
        assert d["type"] == "check_prompt"
        assert d["label"] == "Perception Check"
        assert d["data"]["skill"] == "Perception"
        assert d["data"]["dc"] == 15
        assert "timestamp" in d

    def test_to_dict_is_json_serializable(self):
        event = GameEvent.dice_roll("Attack", [17], 5, 22, dc=15, success=True)
        d = event.to_dict()
        # Should not raise
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["type"] == "dice_roll"
        assert parsed["data"]["total"] == 22


class TestGameEventFactories:
    """Factory classmethods produce correct type/label/data."""

    def test_dice_roll_factory(self):
        event = GameEvent.dice_roll(
            label="Attack vs Goblin",
            rolls=[17],
            modifier=5,
            total=22,
            dc=15,
            success=True,
        )
        assert event.type == GameEventType.DICE_ROLL
        assert event.label == "Attack vs Goblin"
        assert event.data["rolls"] == [17]
        assert event.data["modifier"] == 5
        assert event.data["total"] == 22
        assert event.data["dc"] == 15
        assert event.data["success"] is True

    def test_dice_roll_factory_no_dc(self):
        event = GameEvent.dice_roll(
            label="Damage",
            rolls=[6, 4],
            modifier=2,
            total=12,
        )
        assert event.data["dc"] is None
        assert event.data["success"] is None
        assert event.data["advantage"] is False
        assert event.data["disadvantage"] is False

    def test_dice_roll_factory_with_advantage(self):
        event = GameEvent.dice_roll(
            label="Perception",
            rolls=[18, 12],
            modifier=3,
            total=21,
            advantage=True,
        )
        assert event.data["advantage"] is True
        assert event.data["disadvantage"] is False
        assert len(event.data["rolls"]) == 2

    def test_check_prompt_factory(self):
        event = GameEvent.check_prompt(
            skill="Perception",
            dc=15,
            reason="You hear a faint sound.",
        )
        assert event.type == GameEventType.CHECK_PROMPT
        assert event.label == "Perception Check"
        assert event.data["skill"] == "Perception"
        assert event.data["dc"] == 15
        assert event.data["reason"] == "You hear a faint sound."

    def test_check_prompt_factory_no_dc(self):
        event = GameEvent.check_prompt(skill="Investigation")
        assert event.data["dc"] is None
        assert event.data["reason"] == ""


class TestGameEventRoundTrip:
    """to_dict() → JSON → parse → matches original."""

    def test_dice_roll_round_trip(self):
        original = GameEvent.dice_roll(
            label="Attack",
            rolls=[17, 12],
            modifier=5,
            total=22,
            dc=15,
            success=True,
            advantage=True,
        )
        d = original.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["type"] == "dice_roll"
        assert parsed["label"] == "Attack"
        assert parsed["data"]["rolls"] == [17, 12]
        assert parsed["data"]["modifier"] == 5
        assert parsed["data"]["total"] == 22
        assert parsed["data"]["dc"] == 15
        assert parsed["data"]["success"] is True
        assert parsed["data"]["advantage"] is True

    def test_check_prompt_round_trip(self):
        original = GameEvent.check_prompt(
            skill="Stealth",
            dc=12,
            reason="Sneaking past guards.",
        )
        d = original.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["type"] == "check_prompt"
        assert parsed["label"] == "Stealth Check"
        assert parsed["data"]["skill"] == "Stealth"
        assert parsed["data"]["dc"] == 12
        assert parsed["data"]["reason"] == "Sneaking past guards."


class TestSpellCastFactory:
    """Phase 3: the spell_cast() factory classmethod + serialization."""

    def test_spell_cast_enum_value(self):
        assert GameEventType.SPELL_CAST.value == "spell_cast"

    def test_spell_cast_factory_success(self):
        event = GameEvent.spell_cast(
            label="🔮 Fire Bolt",
            spell_name="Fire Bolt",
            spell_id="fire_bolt",
            level=0,
            school="evocation",
            slot_level=None,
            success=True,
            attack_total=18,
            hit=True,
            damage=10,
            damage_type="fire",
            target="Goblin",
            target_remaining_hp=2,
            target_max_hp=12,
            message="Fire Bolt hit for 10 fire damage.",
            slots_remaining=[{"level": 1, "available": 3}],
        )
        assert event.type == GameEventType.SPELL_CAST
        assert event.label == "🔮 Fire Bolt"
        assert event.data["spell_name"] == "Fire Bolt"
        assert event.data["spell_id"] == "fire_bolt"
        assert event.data["level"] == 0
        assert event.data["school"] == "evocation"
        assert event.data["slot_level"] is None
        assert event.data["success"] is True
        assert event.data["hit"] is True
        assert event.data["damage"] == 10
        assert event.data["damage_type"] == "fire"
        assert event.data["target"] == "Goblin"
        assert event.data["target_remaining_hp"] == 2

    def test_spell_cast_factory_failed(self):
        event = GameEvent.spell_cast(
            label="🔮 Fireball (cast failed)",
            spell_name="Fireball",
            spell_id="fireball",
            level=3,
            school="evocation",
            slot_level=None,
            success=False,
            message="No spell slots available for Fireball",
        )
        assert event.data["success"] is False
        assert event.data["damage"] == 0
        assert event.data["hit"] is None
        assert event.data["message"] == "No spell slots available for Fireball"

    def test_spell_cast_round_trip(self):
        original = GameEvent.spell_cast(
            label="🔮 Cure Wounds",
            spell_name="Cure Wounds",
            spell_id="cure_wounds",
            level=1,
            school="evocation",
            slot_level=1,
            success=True,
            healing=8,
            target="Lyra",
            target_remaining_hp=18,
            target_max_hp=24,
            message="Cure Wounds restores 8 HP.",
        )
        parsed = json.loads(json.dumps(original.to_dict()))
        assert parsed["type"] == "spell_cast"
        assert parsed["data"]["spell_name"] == "Cure Wounds"
        assert parsed["data"]["healing"] == 8
        assert parsed["data"]["slot_level"] == 1
        assert parsed["data"]["target_remaining_hp"] == 18


class TestLootFactory:
    """Phase 4: the loot() factory classmethod + serialization."""

    def test_loot_enum_value(self):
        assert GameEventType.LOOT.value == "loot"

    def test_loot_factory_gained(self):
        event = GameEvent.loot(
            label="🎁 Health Potion acquired",
            operation="gained",
            item_name="Health Potion",
            item_type="potion",
            item_id="abc-123",
            quantity=2,
            rarity="common",
            value=50,
            source="Goblin loot",
        )
        assert event.type == GameEventType.LOOT
        assert event.label == "🎁 Health Potion acquired"
        assert event.data["operation"] == "gained"
        assert event.data["item_name"] == "Health Potion"
        assert event.data["item_type"] == "potion"
        assert event.data["item_id"] == "abc-123"
        assert event.data["quantity"] == 2
        assert event.data["rarity"] == "common"
        assert event.data["value"] == 50
        assert event.data["source"] == "Goblin loot"
        assert event.data["success"] is True

    def test_loot_factory_equipped_with_ac(self):
        event = GameEvent.loot(
            label="⚔️ Equipped Chain Mail",
            operation="equipped",
            item_name="Chain Mail",
            item_type="armor",
            item_id="armor-1",
            ac_after=16,
        )
        assert event.data["operation"] == "equipped"
        assert event.data["ac_after"] == 16
        assert event.data["success"] is True

    def test_loot_factory_failed(self):
        event = GameEvent.loot(
            label="🎒 Longsword (give failed)",
            operation="gained",
            item_name="Longsword",
            item_type="weapon",
            success=False,
            message="Unknown item type: 'bogus'",
        )
        assert event.data["success"] is False
        assert event.data["message"] == "Unknown item type: 'bogus'"
        # Operation-specific fields default to None / sensible values.
        assert event.data["healing"] is None
        assert event.data["ac_after"] is None
        assert event.data["uses_remaining"] is None

    def test_loot_factory_round_trip(self):
        original = GameEvent.loot(
            label="🧪 Used Health Potion",
            operation="used",
            item_name="Health Potion",
            item_type="potion",
            item_id="pot-1",
            healing=7,
            uses_remaining=None,
        )
        parsed = json.loads(json.dumps(original.to_dict()))
        assert parsed["type"] == "loot"
        assert parsed["data"]["operation"] == "used"
        assert parsed["data"]["item_name"] == "Health Potion"
        assert parsed["data"]["healing"] == 7
        assert parsed["data"]["uses_remaining"] is None

    def test_loot_factory_defaults(self):
        event = GameEvent.loot(
            label="🎁 Gold acquired",
            operation="gained",
            item_name="Gold",
            item_type="misc",
        )
        assert event.data["quantity"] == 1
        assert event.data["rarity"] == "common"
        assert event.data["value"] == 0
        assert event.data["success"] is True
        assert event.data["message"] == ""
