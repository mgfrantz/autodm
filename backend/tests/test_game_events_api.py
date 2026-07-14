"""
Tests for the game events API integration — non-streaming /action returns
game_events, streaming /action/stream emits game_event SSE events, and the
/resolve-check endpoint rolls a real d20 for player-initiated checks.

All DSPy-mediated LLM functions are patched so no live LLM call is made.
"""
import json
from contextlib import contextmanager
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from app.models.models import Character, World, GameSave


def _make_game_save(db_session, story_log=None):
    """Create a character + world + game save in the test DB."""
    char = Character(
        name="Lyra", race="Elf", char_class="Wizard", level=3,
        strength=8, dexterity=14, constitution=12, intelligence=18,
        wisdom=15, charisma=10, max_hp=24, current_hp=24, armor_class=13,
    )
    world = World(
        name="The Shattered Vale",
        description="A land broken by ancient magic.",
        world_data=json.dumps({
            "description": "A land broken by ancient magic.",
            "starting_settlement": {"name": "Oakhaven"},
            "hook": "A strange light pulses from the old tower.",
        }),
        tone="heroic fantasy",
    )
    db_session.add(char)
    db_session.add(world)
    db_session.commit()
    db_session.refresh(char)
    db_session.refresh(world)
    save = GameSave(
        name="Test Adventure",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps({
            "location": "Oakhaven",
            "visited_locations": ["Oakhaven"],
            "conditions": [],
            "in_combat": False,
        }),
        story_log=json.dumps(story_log or []),
    )
    db_session.add(save)
    db_session.commit()
    db_session.refresh(save)
    return char, world, save


def _parse_sse(text):
    """Parse a raw SSE response body into a list of event payloads."""
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
    """Async generator mimicking stream_narration_dspy."""
    for piece in ["The ", "tower ", "glows ", "brightly."]:
        yield piece


# --- LLM mock helpers --------------------------------------------------------

@contextmanager
def mock_action_llm(narration="The door creaks.", game_actions=None):
    """Patch all LLM-calling functions in the /action endpoint."""
    with patch("app.api.game._dm_actionable_narrate", new=AsyncMock(
        return_value=(narration, game_actions or [])
    )), \
    patch("app.api.game._resolve_skill_check", return_value={}), \
    patch("app.api.game._detect_and_update_quests", side_effect=lambda n, gs: (gs, [])), \
    patch("app.api.game._detect_and_update_npc_mood", side_effect=lambda n, gs: gs), \
    patch("app.api.game._detect_and_update_game_flags", side_effect=lambda n, gs: gs), \
    patch("app.api.game._generate_action_suggestions", return_value=["Look around"]):
        yield


@contextmanager
def mock_stream_llm(narration="The tower glows brightly.", game_actions=None):
    """Patch all LLM-calling functions in the /action/stream endpoint."""
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


# Sample game_action dicts the DM might emit.
_SAMPLE_ACTIONS = [
    {"function": "roll_dice", "label": "Perception Check",
     "args": {"sides": 20, "modifier": 3, "dc": 15}},
]
_SAMPLE_ACTIONS_MULTI = [
    {"function": "roll_dice", "label": "Attack",
     "args": {"sides": 20, "modifier": 5, "dc": 12}},
    {"function": "request_check", "label": "Stealth",
     "args": {"skill": "Stealth", "dc": 10, "reason": "Sneaking past guards"}},
]


class TestNonStreamingActionEvents:
    """POST /api/game/{game_id}/action returns game_events."""

    def test_non_streaming_returns_events(self, client, db_session):
        _, _, save = _make_game_save(db_session)
        with mock_action_llm("The door creaks.", _SAMPLE_ACTIONS):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I listen at the door."},
            )
        assert response.status_code == 200
        data = response.json()
        assert "game_events" in data
        assert len(data["game_events"]) == 1
        assert data["game_events"][0]["type"] == "dice_roll"
        assert data["game_events"][0]["label"] == "Perception Check"
        assert data["game_events"][0]["data"]["dc"] == 15

    def test_empty_actions_returns_empty_events(self, client, db_session):
        _, _, save = _make_game_save(db_session)
        with mock_action_llm("Nothing happens.", []):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I wait."},
            )
        assert response.status_code == 200
        assert response.json()["game_events"] == []

    def test_multiple_events(self, client, db_session):
        _, _, save = _make_game_save(db_session)
        with mock_action_llm("You attack and sneak.", _SAMPLE_ACTIONS_MULTI):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I attack then hide."},
            )
        assert response.status_code == 200
        events = response.json()["game_events"]
        assert len(events) == 2
        assert events[0]["type"] == "dice_roll"
        assert events[1]["type"] == "check_prompt"

    def test_dmresponse_shape_includes_game_events(self, client, db_session):
        """The DMResponse model includes the game_events field."""
        _, _, save = _make_game_save(db_session)
        with mock_action_llm("You look around.", []):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I look around."},
            )
        data = response.json()
        # DMResponse must have these fields
        assert "narration" in data
        assert "action_suggestions" in data
        assert "combat_active" in data
        assert "skill_check_resolution" in data
        assert "game_events" in data
        assert isinstance(data["game_events"], list)


class TestStreamingActionEvents:
    """POST /api/game/{game_id}/action/stream emits game_event SSE events."""

    def test_streaming_emits_game_event_sse(self, client, db_session):
        _, _, save = _make_game_save(db_session)
        with mock_stream_llm("The tower glows brightly.", _SAMPLE_ACTIONS):
            response = client.post(
                f"/api/game/{save.id}/action/stream",
                json={"action": "I examine the tower."},
            )
        assert response.status_code == 200
        events = _parse_sse(response.text)
        # Should have chunks, then game_event, then done
        types = [e["type"] for e in events]
        assert "game_event" in types
        assert types[-1] == "done"
        # The game_event should come before done
        game_event_idx = types.index("game_event")
        done_idx = types.index("done")
        assert game_event_idx < done_idx
        # Check the event content
        game_event = events[game_event_idx]
        assert game_event["type"] == "game_event"
        assert game_event["event"]["label"] == "Perception Check"
        assert game_event["event"]["type"] == "dice_roll"

    def test_streaming_done_includes_game_events(self, client, db_session):
        """The done event payload includes game_events for batch clients."""
        _, _, save = _make_game_save(db_session)
        with mock_stream_llm("The tower glows brightly.", _SAMPLE_ACTIONS):
            response = client.post(
                f"/api/game/{save.id}/action/stream",
                json={"action": "I look."},
            )
        events = _parse_sse(response.text)
        done_event = events[-1]
        assert done_event["type"] == "done"
        assert "game_events" in done_event
        assert len(done_event["game_events"]) == 1

    def test_streaming_no_events_when_empty(self, client, db_session):
        _, _, save = _make_game_save(db_session)
        with mock_stream_llm("The tower glows brightly.", []):
            response = client.post(
                f"/api/game/{save.id}/action/stream",
                json={"action": "I wait."},
            )
        events = _parse_sse(response.text)
        types = [e["type"] for e in events]
        assert "game_event" not in types
        assert types[-1] == "done"
        assert events[-1]["game_events"] == []

    def test_streaming_error_handling_for_game_actions(self, client, db_session):
        """If _dm_actionable_narrate raises, streaming still completes with empty events."""
        _, _, save = _make_game_save(db_session)
        with patch("app.api.game.stream_narration_dspy", new=_fake_stream), \
             patch("app.api.game._dm_actionable_narrate",
                   new=AsyncMock(side_effect=RuntimeError("LLM down"))), \
             patch("app.api.game._resolve_skill_check", return_value={}), \
             patch("app.api.game._detect_and_update_quests", side_effect=lambda n, gs: (gs, [])), \
             patch("app.api.game._detect_and_update_npc_mood", side_effect=lambda n, gs: gs), \
             patch("app.api.game._detect_and_update_game_flags", side_effect=lambda n, gs: gs), \
             patch("app.api.game._generate_action_suggestions", return_value=[]):
            response = client.post(
                f"/api/game/{save.id}/action/stream",
                json={"action": "I look."},
            )
        assert response.status_code == 200
        events = _parse_sse(response.text)
        done_event = events[-1]
        assert done_event["type"] == "done"
        assert done_event["game_events"] == []

    def test_streaming_persists_narration_with_events(self, client, db_session):
        """Narration is still persisted to the story log when game events are present."""
        _, _, save = _make_game_save(db_session)
        with mock_stream_llm("The tower glows brightly.", _SAMPLE_ACTIONS):
            client.post(
                f"/api/game/{save.id}/action/stream",
                json={"action": "I examine the tower."},
            )
        db_session.expire_all()
        refreshed = db_session.query(GameSave).filter(GameSave.id == save.id).first()
        log = json.loads(refreshed.story_log)
        assert len(log) == 2
        assert log[0]["role"] == "player"
        assert log[1]["role"] == "dm"
        assert log[1]["content"] == "The tower glows brightly."


class TestResolveCheckEndpoint:
    """POST /api/game/{game_id}/resolve-check rolls a real d20."""

    def test_resolve_check_returns_dice_roll_event(self, client, db_session):
        _, _, save = _make_game_save(db_session)
        response = client.post(
            f"/api/game/{save.id}/resolve-check",
            json={"skill": "Perception", "dc": 15},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "dice_roll"
        assert data["label"] == "Perception Check"
        assert "rolls" in data["data"]
        assert len(data["data"]["rolls"]) == 1
        assert 1 <= data["data"]["rolls"][0] <= 20
        assert data["data"]["dc"] == 15
        assert "success" in data["data"]
        assert isinstance(data["data"]["success"], bool)

    def test_resolve_check_no_dc(self, client, db_session):
        _, _, save = _make_game_save(db_session)
        response = client.post(
            f"/api/game/{save.id}/resolve-check",
            json={"skill": "Investigation"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["dc"] is None
        assert data["data"]["success"] is None

    def test_resolve_check_missing_game_404(self, client, db_session):
        response = client.post(
            "/api/game/9999/resolve-check",
            json={"skill": "Perception", "dc": 15},
        )
        assert response.status_code == 404
