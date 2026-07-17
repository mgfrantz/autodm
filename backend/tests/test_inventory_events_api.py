"""
Tests for inventory-operation event integration in the /action and
/action/stream endpoints (DM function calling Phase 4).

These verify:
- DM-emitted ``give_item`` / ``remove_item`` / ``equip_item`` / ``use_item``
  game_actions produce ``loot`` game_events.
- Item changes persist to ``character.inventory``.
- equip_item triggers an Armor Class recalculation (``ac_after`` set).
- use_item on a healing potion restores HP (``healing`` field + character HP).
- Streaming emits ``game_event`` SSE payloads for loot.
- The ``_inventory_for_dm`` roster helper formats inventory items.
- Failed operations (invalid item type, missing item) surface as events.

All DSPy-mediated LLM functions are patched so no live LLM call is made.
"""
import json
from contextlib import contextmanager
from unittest.mock import patch, AsyncMock

import pytest

from app.engine.game_events import GameEventType
from app.engine.inventory import (
    Inventory,
    create_armor,
    create_potion,
    create_weapon,
)
from app.models.models import Character, World, GameSave


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game_save_with_inventory(db_session):
    """Create a game save whose character has a known inventory.

    Returns (char, world, save, potion_id, armor_id, weapon_id).
    """
    char = Character(
        name="Bjorn", race="Human", char_class="fighter", level=2,
        strength=16, dexterity=14, constitution=15, intelligence=10,
        wisdom=12, charisma=10, max_hp=24, current_hp=12, armor_class=11,
    )
    # Build an inventory with a healing potion, unequipped leather armor,
    # and an unequipped longsword. Capture the ids for game_actions.
    potion = create_potion("Health Potion", "Restores 2d4+2 HP", uses=1)
    # create armor explicitly with a LIGHT ArmorType.
    from app.engine.inventory import ArmorType
    armor = create_armor("Leather Armor", ArmorType.LIGHT)
    weapon = create_weapon("Longsword", "1d8", "slashing")

    inv = Inventory()
    inv.add_item(potion)
    inv.add_item(armor)
    inv.add_item(weapon)
    char.inventory = json.dumps(inv.to_dict())

    world = World(
        name="The Iron Vale",
        description="A harsh frontier land.",
        world_data=json.dumps({
            "description": "A harsh frontier land.",
            "starting_settlement": {"name": "Oakhaven"},
            "hook": "A horn sounds.",
        }),
        tone="heroic fantasy",
    )
    db_session.add(char)
    db_session.add(world)
    db_session.commit()
    db_session.refresh(char)
    db_session.refresh(world)

    save = GameSave(
        name="Inventory Test",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps({
            "location": "Oakhaven",
            "visited_locations": ["Oakhaven"],
            "conditions": [],
            "in_combat": False,
        }),
        story_log=json.dumps([]),
    )
    db_session.add(save)
    db_session.commit()
    db_session.refresh(save)
    return char, world, save, potion.id, armor.id, weapon.id


def _parse_sse(text):
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        for line in block.split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    return events


async def _fake_stream(*_args, **_kwargs):
    for piece in ["The ", "goblin ", "drops loot!"]:
        yield piece


@contextmanager
def mock_action_llm(narration="You find a potion.", game_actions=None):
    with patch("app.api.game._dm_actionable_narrate", new=AsyncMock(
        return_value=(narration, game_actions or [])
    )), \
    patch("app.api.game._resolve_skill_check", return_value={}), \
    patch("app.api.game._detect_and_update_quests", side_effect=lambda n, gs: (gs, [])), \
    patch("app.api.game._detect_and_update_npc_mood", side_effect=lambda n, gs: gs), \
    patch("app.api.game._detect_and_update_game_flags", side_effect=lambda n, gs: gs), \
    patch("app.api.game._generate_action_suggestions", return_value=[]):
        yield


@contextmanager
def mock_stream_llm(narration="You find a potion.", game_actions=None):
    with patch("app.api.game.stream_narration_dspy", new=_fake_stream), \
    patch("app.api.game._dm_actionable_narrate", new=AsyncMock(
        return_value=(narration, game_actions or [])
    )), \
    patch("app.api.game._resolve_skill_check", return_value={}), \
    patch("app.api.game._detect_and_update_quests", side_effect=lambda n, gs: (gs, [])), \
    patch("app.api.game._detect_and_update_npc_mood", side_effect=lambda n, gs: gs), \
    patch("app.api.game._detect_and_update_game_flags", side_effect=lambda n, gs: gs), \
    patch("app.api.game._generate_action_suggestions", return_value=[]):
        yield


# Sample inventory game_action dicts.
def _give_potion():
    return [{
        "function": "give_item", "label": "Found a Health Potion",
        "args": {
            "item_name": "Health Potion", "item_type": "potion",
            "quantity": 2, "rarity": "common", "value": 50,
        },
    }]


def _give_weapon():
    return [{
        "function": "give_item", "label": "Found a Shortsword",
        "args": {
            "item_name": "Shortsword", "item_type": "weapon",
            "damage_dice": "1d6", "damage_type": "piercing", "value": 10,
        },
    }]


def _give_invalid():
    return [{
        "function": "give_item", "label": "Strange object",
        "args": {"item_name": "Garbage", "item_type": "bogus"},
    }]


def _remove(item_id, qty=1):
    return [{
        "function": "remove_item", "label": "Item consumed",
        "args": {"item_id": item_id, "quantity": qty},
    }]


def _equip(item_id):
    return [{
        "function": "equip_item", "label": "Equip armor",
        "args": {"item_id": item_id},
    }]


def _use(item_id):
    return [{
        "function": "use_item", "label": "Drink potion",
        "args": {"item_id": item_id},
    }]


def _load_inventory_from_char(db_session, char):
    """Re-read the character's inventory from the DB."""
    from app.api.inventory import _load_inventory
    db_session.expire_all()
    refreshed = db_session.query(Character).filter(Character.id == char.id).first()
    return _load_inventory(refreshed)


# ===========================================================================
# Non-streaming /action with inventory operations
# ===========================================================================

class TestNonStreamingInventoryEvents:
    """POST /action returns loot game_events from DM inventory actions."""

    def test_give_item_emits_loot_event_and_persists(self, client, db_session):
        char, _, save, _, _, _ = _make_game_save_with_inventory(db_session)
        with mock_action_llm("You find a potion.", _give_potion()):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I search the goblin's body."},
            )
        assert response.status_code == 200
        events = response.json()["game_events"]
        loot_events = [e for e in events if e["type"] == "loot"]
        assert len(loot_events) == 1
        ev = loot_events[0]
        assert ev["data"]["operation"] == "gained"
        assert ev["data"]["item_name"] == "Health Potion"
        assert ev["data"]["quantity"] == 2
        # Persisted: a new Health Potion slot (stacks onto existing).
        inv = _load_inventory_from_char(db_session, char)
        potions = [s for s in inv.slots if s.item.name == "Health Potion"]
        assert len(potions) == 1
        # Started with 1 (from helper) + 2 given = 3.
        assert potions[0].item.quantity == 3

    def test_give_item_with_quantity_stacks(self, client, db_session):
        char, _, save, _, _, _ = _make_game_save_with_inventory(db_session)
        with mock_action_llm("Loot!", _give_potion()):
            client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I loot the chest."},
            )
        inv = _load_inventory_from_char(db_session, char)
        potions = [s for s in inv.slots if s.item.name == "Health Potion"]
        assert potions[0].item.quantity == 3  # 1 + 2

    def test_give_item_weapon_details_constructed(self, client, db_session):
        char, _, save, _, _, _ = _make_game_save_with_inventory(db_session)
        with mock_action_llm("A fine blade.", _give_weapon()):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I take the sword."},
            )
        events = response.json()["game_events"]
        ev = [e for e in events if e["type"] == "loot"][0]
        assert ev["data"]["item_type"] == "weapon"
        inv = _load_inventory_from_char(db_session, char)
        sword = next(s.item for s in inv.slots if s.item.name == "Shortsword")
        assert sword.damage_dice_count == 1
        assert sword.damage_dice_sides == 6

    def test_remove_item_persists(self, client, db_session):
        char, _, save, potion_id, _, _ = _make_game_save_with_inventory(db_session)
        with mock_action_llm("You drink it.", _remove(potion_id)):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I use the potion."},
            )
        events = response.json()["game_events"]
        ev = [e for e in events if e["type"] == "loot"][0]
        assert ev["data"]["operation"] == "removed"
        assert ev["data"]["success"] is True
        inv = _load_inventory_from_char(db_session, char)
        assert inv.get_item(potion_id) is None

    def test_equip_item_recalculates_ac(self, client, db_session):
        char, _, save, _, armor_id, _ = _make_game_save_with_inventory(db_session)
        before_ac = char.armor_class
        with mock_action_llm("You don the armor.", _equip(armor_id)):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I equip the leather armor."},
            )
        events = response.json()["game_events"]
        ev = [e for e in events if e["type"] == "loot"][0]
        assert ev["data"]["operation"] == "equipped"
        assert ev["data"]["success"] is True
        # ac_after is filled by the caller after _recalc_armor_class.
        assert ev["data"]["ac_after"] is not None
        # Persisted: the character's armor_class changed.
        db_session.expire_all()
        refreshed = db_session.query(Character).filter(Character.id == char.id).first()
        assert refreshed.armor_class != before_ac
        assert refreshed.armor_class == ev["data"]["ac_after"]

    def test_use_healing_potion_increases_hp(self, client, db_session):
        char, _, save, potion_id, _, _ = _make_game_save_with_inventory(db_session)
        # character starts at current_hp=12, max_hp=24
        with patch("app.api.game.roll_dice") as mock_roll:
            from app.engine.dice import RollResult
            mock_roll.return_value = RollResult(
                rolls=[3, 2], modifier=2, total=7, description="2d4+2")
            with mock_action_llm("You drink the potion.", _use(potion_id)):
                response = client.post(
                    f"/api/game/{save.id}/action",
                    json={"action": "I drink the healing potion."},
                )
        events = response.json()["game_events"]
        ev = [e for e in events if e["type"] == "loot"][0]
        assert ev["data"]["operation"] == "used"
        assert ev["data"]["success"] is True
        assert ev["data"]["healing"] == 7
        # HP persisted: 12 + 7 = 19.
        db_session.expire_all()
        refreshed = db_session.query(Character).filter(Character.id == char.id).first()
        assert refreshed.current_hp == 19

    def test_failed_give_item_invalid_type(self, client, db_session):
        _, _, save, _, _, _ = _make_game_save_with_inventory(db_session)
        with mock_action_llm("Hmm.", _give_invalid()):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I pick up the strange object."},
            )
        events = response.json()["game_events"]
        ev = [e for e in events if e["type"] == "loot"][0]
        assert ev["data"]["success"] is False
        assert ev["data"]["message"]

    def test_failed_remove_not_found(self, client, db_session):
        _, _, save, _, _, _ = _make_game_save_with_inventory(db_session)
        with mock_action_llm("Nothing happens.", _remove("ghost-item")):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I discard the ghost item."},
            )
        events = response.json()["game_events"]
        ev = [e for e in events if e["type"] == "loot"][0]
        assert ev["data"]["success"] is False


# ===========================================================================
# Streaming /action/stream with inventory operations
# ===========================================================================

class TestStreamingInventoryEvents:
    """POST /action/stream emits loot game_event SSE payloads."""

    def test_streaming_emits_loot_event(self, client, db_session):
        _, _, save, _, _, _ = _make_game_save_with_inventory(db_session)
        with mock_stream_llm("You find loot!", _give_potion()):
            response = client.post(
                f"/api/game/{save.id}/action/stream",
                json={"action": "I search the room."},
            )
        events = _parse_sse(response.text)
        types = [e["type"] for e in events]
        assert "game_event" in types
        loot_payloads = [
            e for e in events if e["type"] == "game_event"
            and e["event"]["type"] == "loot"
        ]
        assert len(loot_payloads) == 1
        assert loot_payloads[0]["event"]["data"]["item_name"] == "Health Potion"

    def test_streaming_persists_inventory(self, client, db_session):
        char, _, save, _, _, _ = _make_game_save_with_inventory(db_session)
        with mock_stream_llm("Loot!", _give_potion()):
            client.post(
                f"/api/game/{save.id}/action/stream",
                json={"action": "I loot the goblin."},
            )
        inv = _load_inventory_from_char(db_session, char)
        potions = [s for s in inv.slots if s.item.name == "Health Potion"]
        assert potions[0].item.quantity == 3  # 1 + 2

    def test_streaming_use_healing_potion_persists_hp(self, client, db_session):
        char, _, save, potion_id, _, _ = _make_game_save_with_inventory(db_session)
        with patch("app.api.game.roll_dice") as mock_roll:
            from app.engine.dice import RollResult
            mock_roll.return_value = RollResult(
                rolls=[4, 3], modifier=2, total=9, description="2d4+2")
            with mock_stream_llm("You drink it.", _use(potion_id)):
                client.post(
                    f"/api/game/{save.id}/action/stream",
                    json={"action": "I drink the healing potion."},
                )
        db_session.expire_all()
        refreshed = db_session.query(Character).filter(Character.id == char.id).first()
        assert refreshed.current_hp == 21  # 12 + 9


# ===========================================================================
# _inventory_for_dm roster helper
# ===========================================================================

class TestInventoryRosterHelper:
    """The roster builder formats inventory items for DM context."""

    def test_roster_lists_items(self):
        from app.api.game import _inventory_for_dm
        char = Character(
            name="Bjorn", race="Human", char_class="fighter", level=2,
            strength=16, dexterity=14, constitution=15, intelligence=10,
            wisdom=12, charisma=10, max_hp=24, current_hp=24, armor_class=13,
        )
        inv = Inventory()
        inv.add_item(create_weapon("Longsword", "1d8", "slashing"))
        inv.add_item(create_potion("Health Potion", "heals", uses=1))
        char.inventory = json.dumps(inv.to_dict())
        roster = _inventory_for_dm(char)
        assert "INVENTORY_ROSTER:" in roster
        assert "Longsword" in roster
        assert "Health Potion" in roster
        assert "weapon" in roster
        assert "Use these item_ids" in roster

    def test_roster_empty_for_no_inventory(self):
        from app.api.game import _inventory_for_dm
        char = Character(
            name="Bjorn", race="Human", char_class="fighter", level=2,
            strength=16, dexterity=14, constitution=15, intelligence=10,
            wisdom=12, charisma=10, max_hp=24, current_hp=24, armor_class=13,
        )
        char.inventory = json.dumps({"slots": []})
        assert _inventory_for_dm(char) == ""
