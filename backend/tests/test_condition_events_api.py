"""
Tests for condition-operation event integration in the /action and
/action/stream endpoints (DM function calling Phase 5).

These verify:
- DM-emitted ``apply_condition`` / ``remove_condition`` game_actions produce
  ``condition_applied`` game_events.
- Player conditions persist to ``game_state["conditions"]`` +
  ``game_state["condition_durations"]``.
- Combatant conditions persist in the encounter (``game_state["combat"]``).
- Streaming emits ``game_event`` SSE payloads for conditions.
- The ``_conditions_for_dm`` roster helper formats active conditions.
- Failed operations (invalid condition) surface as events.

All DSPy-mediated LLM functions are patched so no live LLM call is made.
"""
import json
from contextlib import contextmanager
from unittest.mock import patch, AsyncMock

import pytest

from app.engine.combat import Attack, Combatant, Encounter
from app.engine.game_events import GameEventType
from app.models.models import Character, GameSave, World


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_game_save(db_session, with_combat=False):
    """Create a game save, optionally with a live encounter."""
    char = Character(
        name="Thalia", race="Human", char_class="fighter", level=3,
        strength=16, dexterity=14, constitution=15, intelligence=10,
        wisdom=12, charisma=10, max_hp=28, current_hp=20, armor_class=16,
    )
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

    game_state = {
        "location": "Oakhaven",
        "visited_locations": ["Oakhaven"],
        "conditions": [],
        "condition_durations": {},
        "in_combat": False,
    }

    if with_combat:
        hero = Combatant(
            id="player", name="Thalia", side="player", max_hp=28, armor_class=16,
            attacks=[Attack(name="Longsword", attack_bonus=5,
                            damage_dice_count=1, damage_dice_sides=8,
                            damage_bonus=3, damage_type="slashing")],
        )
        hero.current_hp = 20
        goblin = Combatant(
            id="goblin_1", name="Goblin Brute", side="enemy",
            max_hp=12, armor_class=13,
            attacks=[Attack(name="Morningstar", attack_bonus=4,
                            damage_dice_count=1, damage_dice_sides=6,
                            damage_bonus=2, damage_type="piercing")],
        )
        goblin.current_hp = 12
        encounter = Encounter(combatants=[hero, goblin])
        game_state["combat"] = encounter.to_dict()
        game_state["in_combat"] = True

    save = GameSave(
        name="Condition Test",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps(game_state),
        story_log=json.dumps([]),
    )
    db_session.add(save)
    db_session.commit()
    db_session.refresh(save)
    return char, world, save


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
    for piece in ["The ", "spider ", "bites!"]:
        yield piece


@contextmanager
def mock_action_llm(narration="You feel woozy.", game_actions=None):
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
def mock_stream_llm(narration="You feel woozy.", game_actions=None):
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


def _apply_player(condition, duration=None):
    args = {"condition": condition, "target": "player"}
    if duration is not None:
        args["duration"] = duration
    return [{"function": "apply_condition", "label": f"{condition}", "args": args}]


def _remove_player(condition):
    return [{"function": "remove_condition", "label": f"remove {condition}",
             "args": {"condition": condition, "target": "player"}}]


def _apply_combatant(condition, combatant_id, duration=None):
    args = {"condition": condition, "target": combatant_id}
    if duration is not None:
        args["duration"] = duration
    return [{"function": "apply_condition", "label": f"{condition}", "args": args}]


def _game_state_after(db_session, save):
    db_session.expire_all()
    refreshed = db_session.query(GameSave).filter(GameSave.id == save.id).first()
    return json.loads(refreshed.game_state)


# =========================================================================== #
# Non-streaming /action with condition operations (player)
# =========================================================================== #

class TestNonStreamingConditionEventsPlayer:
    """POST /action returns condition_applied events for player conditions."""

    def test_apply_condition_on_player_emits_event(self, client, db_session):
        char, _, save = _make_game_save(db_session)
        with mock_action_llm("You are poisoned.", _apply_player("poisoned")):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "The spider bites me."},
            )
        assert response.status_code == 200
        events = response.json()["game_events"]
        cond_events = [e for e in events if e["type"] == "condition_applied"]
        assert len(cond_events) == 1
        ev = cond_events[0]
        assert ev["data"]["operation"] == "applied"
        assert ev["data"]["condition"] == "poisoned"
        assert ev["data"]["target"] == "Thalia"
        assert ev["data"]["target_type"] == "player"
        assert ev["data"]["success"] is True

    def test_apply_condition_persists_to_game_state(self, client, db_session):
        char, _, save = _make_game_save(db_session)
        with mock_action_llm("Poisoned!", _apply_player("poisoned")):
            client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I get bitten."},
            )
        gs = _game_state_after(db_session, save)
        assert "poisoned" in gs["conditions"]

    def test_apply_condition_with_duration_persists_duration(self, client, db_session):
        char, _, save = _make_game_save(db_session)
        with mock_action_llm("Frightened!", _apply_player("frightened", duration=3)):
            client.post(
                f"/api/game/{save.id}/action",
                json={"action": "The dragon roars."},
            )
        gs = _game_state_after(db_session, save)
        assert "frightened" in gs["conditions"]
        assert gs.get("condition_durations", {}).get("frightened") == 3

    def test_apply_permanent_condition_no_duration_entry(self, client, db_session):
        char, _, save = _make_game_save(db_session)
        with mock_action_llm("Blinded!", _apply_player("blinded")):
            client.post(
                f"/api/game/{save.id}/action",
                json={"action": "A flash of light."},
            )
        gs = _game_state_after(db_session, save)
        assert "blinded" in gs["conditions"]
        # Permanent conditions don't get a duration entry.
        assert "blinded" not in gs.get("condition_durations", {})

    def test_apply_includes_description(self, client, db_session):
        char, _, save = _make_game_save(db_session)
        with mock_action_llm("Poisoned!", _apply_player("poisoned")):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I get bitten."},
            )
        ev = [e for e in response.json()["game_events"] if e["type"] == "condition_applied"][0]
        assert ev["data"]["description"]
        assert "disadvantage" in ev["data"]["description"]

    def test_remove_condition_on_player_persists(self, client, db_session):
        char, _, save = _make_game_save(db_session)
        # First apply, then remove.
        with mock_action_llm("Poisoned!", _apply_player("poisoned")):
            client.post(f"/api/game/{save.id}/action", json={"action": "Bitten."})
        with mock_action_llm("Cured!", _remove_player("poisoned")):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I drink the antitoxin."},
            )
        ev = [e for e in response.json()["game_events"] if e["type"] == "condition_applied"][0]
        assert ev["data"]["operation"] == "removed"
        assert ev["data"]["success"] is True
        gs = _game_state_after(db_session, save)
        assert "poisoned" not in gs["conditions"]

    def test_apply_invalid_condition_returns_failed_event(self, client, db_session):
        char, _, save = _make_game_save(db_session)
        with mock_action_llm("???", _apply_player("bogus")):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "Something weird."},
            )
        ev = [e for e in response.json()["game_events"] if e["type"] == "condition_applied"][0]
        assert ev["data"]["success"] is False
        assert "Unknown condition" in ev["data"]["message"]
        gs = _game_state_after(db_session, save)
        assert "bogus" not in gs["conditions"]


# =========================================================================== #
# Non-streaming /action with condition operations (combatant)
# =========================================================================== #

class TestNonStreamingConditionEventsCombatant:
    """POST /action applies conditions to encounter combatants."""

    def test_apply_condition_on_combatant(self, client, db_session):
        char, _, save = _make_game_save(db_session, with_combat=True)
        with mock_action_llm("The goblin is stunned!", _apply_combatant("stunned", "goblin_1", 2)):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I cast a stunning spell."},
            )
        ev = [e for e in response.json()["game_events"] if e["type"] == "condition_applied"][0]
        assert ev["data"]["operation"] == "applied"
        assert ev["data"]["condition"] == "stunned"
        assert ev["data"]["target"] == "Goblin Brute"
        assert ev["data"]["target_type"] == "combatant"
        assert ev["data"]["success"] is True

    def test_apply_condition_on_combatant_persists(self, client, db_session):
        char, _, save = _make_game_save(db_session, with_combat=True)
        with mock_action_llm("Stunned!", _apply_combatant("stunned", "goblin_1")):
            client.post(
                f"/api/game/{save.id}/action",
                json={"action": "Stun the goblin."},
            )
        gs = _game_state_after(db_session, save)
        encounter = Encounter.from_dict(gs["combat"])
        goblin = next(c for c in encounter.combatants if c.id == "goblin_1")
        assert "stunned" in goblin.conditions

    def test_remove_condition_on_combatant(self, client, db_session):
        char, _, save = _make_game_save(db_session, with_combat=True)
        # Apply first.
        with mock_action_llm("Blinded!", _apply_combatant("blinded", "goblin_1")):
            client.post(f"/api/game/{save.id}/action", json={"action": "Flash."})
        # Then remove.
        with mock_action_llm("Recovered!", [{"function": "remove_condition",
                "label": "remove", "args": {"condition": "blinded", "target": "goblin_1"}}]):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "The goblin shakes it off."},
            )
        ev = [e for e in response.json()["game_events"] if e["type"] == "condition_applied"][0]
        assert ev["data"]["operation"] == "removed"
        assert ev["data"]["success"] is True
        gs = _game_state_after(db_session, save)
        encounter = Encounter.from_dict(gs["combat"])
        goblin = next(c for c in encounter.combatants if c.id == "goblin_1")
        assert "blinded" not in goblin.conditions

    def test_apply_condition_unknown_combatant_defaults_to_player(self, client, db_session):
        char, _, save = _make_game_save(db_session, with_combat=True)
        with mock_action_llm("Poisoned!", [{"function": "apply_condition",
                "label": "poison", "args": {"condition": "poisoned", "target": "nobody"}}]):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "Something happens."},
            )
        ev = [e for e in response.json()["game_events"] if e["type"] == "condition_applied"][0]
        # Unknown combatant id → falls back to player.
        assert ev["data"]["target_type"] == "player"
        assert ev["data"]["target"] == "Thalia"


# =========================================================================== #
# Streaming /action/stream
# =========================================================================== #

class TestStreamingConditionEvents:
    """POST /action/stream emits condition_applied SSE events."""

    def test_stream_emits_condition_event_and_persists(self, client, db_session):
        char, _, save = _make_game_save(db_session)
        with mock_stream_llm("You are poisoned!", _apply_player("poisoned", 3)):
            response = client.post(
                f"/api/game/{save.id}/action/stream",
                json={"action": "The spider bites me."},
            )
        events = _parse_sse(response.text)
        cond_events = [e for e in events if e.get("type") == "game_event"
                       and e["event"]["type"] == "condition_applied"]
        assert len(cond_events) == 1
        assert cond_events[0]["event"]["data"]["condition"] == "poisoned"
        # Persisted.
        gs = _game_state_after(db_session, save)
        assert "poisoned" in gs["conditions"]
        assert gs.get("condition_durations", {}).get("poisoned") == 3


# =========================================================================== #
# _conditions_for_dm roster helper
# =========================================================================== #

class TestConditionsForDm:
    """The _conditions_for_dm roster helper formats active conditions."""

    def test_empty_when_no_conditions(self):
        from app.api.game import _conditions_for_dm
        result = _conditions_for_dm({"conditions": []}, None)
        assert result == ""

    def test_lists_player_conditions(self):
        from app.api.game import _conditions_for_dm
        result = _conditions_for_dm({
            "conditions": ["poisoned", "blinded"],
            "condition_durations": {"poisoned": 2},
        }, None)
        assert "PLAYER_CONDITIONS" in result
        assert "poisoned" in result
        assert "blinded" in result
        assert "(2r)" in result  # duration for poisoned

    def test_lists_combatant_conditions(self):
        from app.api.game import _conditions_for_dm
        goblin = Combatant(
            id="goblin_1", name="Goblin", side="enemy",
            max_hp=10, armor_class=12,
            attacks=[Attack(name="Club", attack_bonus=2,
                            damage_dice_count=1, damage_dice_sides=4,
                            damage_bonus=0, damage_type="bludgeoning")],
        )
        goblin.conditions = ["frightened"]
        goblin.condition_durations = {"frightened": 1}
        encounter = Encounter(combatants=[goblin])
        result = _conditions_for_dm({
            "conditions": [],
            "combat": encounter.to_dict(),
        }, None)
        assert "Goblin" in result
        assert "frightened" in result

    def test_both_player_and_combatant(self):
        from app.api.game import _conditions_for_dm
        goblin = Combatant(
            id="goblin_1", name="Goblin", side="enemy",
            max_hp=10, armor_class=12,
            attacks=[Attack(name="Club", attack_bonus=2,
                            damage_dice_count=1, damage_dice_sides=4,
                            damage_bonus=0, damage_type="bludgeoning")],
        )
        goblin.conditions = ["stunned"]
        encounter = Encounter(combatants=[goblin])
        result = _conditions_for_dm({
            "conditions": ["poisoned"],
            "combat": encounter.to_dict(),
        }, None)
        assert "PLAYER_CONDITIONS" in result
        assert "poisoned" in result
        assert "Goblin" in result
        assert "stunned" in result
