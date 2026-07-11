"""
Tests for the LLM streaming (Server-Sent Events) endpoints.

These verify that the streaming start/action endpoints:
- Emit correctly formatted SSE events (chunk -> done)
- Reconstruct the full narration from chunks
- Persist narration to the story log after streaming completes
- Surface error events without crashing
- Return 404 for missing games

The endpoints are mediated by DSPy (``stream_narration_dspy``), which is
patched here so no live LLM call is made.
"""
import json
from unittest.mock import patch

import pytest

from app.models.models import Character, World, GameSave


def _make_game_save(db_session, story_log=None):
    """Create a character + world + game save in the test DB."""
    char = Character(
        name="Lyra",
        race="Elf",
        char_class="Wizard",
        level=3,
        strength=8,
        dexterity=14,
        constitution=12,
        intelligence=18,
        wisdom=15,
        charisma=10,
        max_hp=24,
        current_hp=24,
        armor_class=13,
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
    save = GameSave(
        name="Test Adventure",
        character_id=1,
        world_id=1,
        game_state=json.dumps({
            "location": "Oakhaven",
            "visited_locations": ["Oakhaven"],
            "conditions": [],
            "in_combat": False,
        }),
        story_log=json.dumps(story_log or []),
    )
    db_session.add(char)
    db_session.add(world)
    db_session.add(save)
    db_session.commit()
    return char, world, save


async def _fake_stream(*_args, **_kwargs):
    """Async generator mimicking stream_narration_dspy."""
    for piece in ["The ", "tower ", "glows ", "brightly."]:
        yield piece


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


class TestStartAdventureStream:
    """Tests for POST /api/game/{game_id}/start/stream."""

    def test_streams_chunks_and_done(self, client, db_session):
        """The stream emits chunk events followed by a done event."""
        _, _, save = _make_game_save(db_session)

        with patch(
            "app.api.game.stream_narration_dspy",
            new=_fake_stream,
        ):
            response = client.post(f"/api/game/{save.id}/start/stream")

        assert response.status_code == 200
        events = _parse_sse(response.text)
        assert [e["type"] for e in events] == ["chunk", "chunk", "chunk", "chunk", "done"]
        reconstructed = "".join(e["content"] for e in events if e["type"] == "chunk")
        assert reconstructed == "The tower glows brightly."

    def test_persists_narration_to_story_log(self, client, db_session):
        """The full narration is saved to the story log after streaming."""
        _, _, save = _make_game_save(db_session)

        with patch(
            "app.api.game.stream_narration_dspy",
            new=_fake_stream,
        ):
            client.post(f"/api/game/{save.id}/start/stream")

        # Re-read from a fresh session to confirm persistence.
        db_session.expire_all()
        refreshed = db_session.query(GameSave).filter(GameSave.id == save.id).first()
        log = json.loads(refreshed.story_log)
        assert len(log) == 1
        assert log[0]["role"] == "dm"
        assert log[0]["content"] == "The tower glows brightly."

    def test_missing_game_returns_404(self, client, db_session):
        """A non-existent game id yields a 404."""
        with patch("app.api.game.stream_narration_dspy", new=_fake_stream):
            response = client.post("/api/game/9999/start/stream")
        assert response.status_code == 404

    def test_error_event_on_llm_failure(self, client, db_session):
        """An LLM error surfaces as an error event rather than crashing."""
        _, _, save = _make_game_save(db_session)

        async def failing_stream(*_a, **_k):
            raise RuntimeError("LLM is down")
            yield  # pragma: no cover - make this an async generator

        with patch("app.api.game.stream_narration_dspy", new=failing_stream):
            response = client.post(f"/api/game/{save.id}/start/stream")

        assert response.status_code == 200
        events = _parse_sse(response.text)
        assert events[-1]["type"] == "error"
        assert "LLM is down" in events[-1]["message"]


class TestPlayerActionStream:
    """Tests for POST /api/game/{game_id}/action/stream."""

    def test_streams_response_and_combat_flag(self, client, db_session):
        """Action stream includes combat flag on the done event."""
        _, _, save = _make_game_save(db_session)

        with patch("app.api.game.stream_narration_dspy", new=_fake_stream):
            response = client.post(
                f"/api/game/{save.id}/action/stream",
                json={"action": "I examine the glowing tower."},
            )

        assert response.status_code == 200
        events = _parse_sse(response.text)
        assert events[-1]["type"] == "done"
        assert events[-1]["combat_active"] is False

    def test_persists_action_and_response(self, client, db_session):
        """Both the player action and DM response are stored."""
        _, _, save = _make_game_save(db_session)

        with patch("app.api.game.stream_narration_dspy", new=_fake_stream):
            client.post(
                f"/api/game/{save.id}/action/stream",
                json={"action": "I approach the door."},
            )

        db_session.expire_all()
        refreshed = db_session.query(GameSave).filter(GameSave.id == save.id).first()
        log = json.loads(refreshed.story_log)
        assert len(log) == 2
        assert log[0]["role"] == "player"
        assert log[0]["content"] == "I approach the door."
        assert log[1]["role"] == "dm"
        assert log[1]["content"] == "The tower glows brightly."

    def test_missing_game_returns_404(self, client, db_session):
        """A non-existent game id yields a 404."""
        with patch("app.api.game.stream_narration_dspy", new=_fake_stream):
            response = client.post(
                "/api/game/9999/action/stream",
                json={"action": "look"},
            )
        assert response.status_code == 404
