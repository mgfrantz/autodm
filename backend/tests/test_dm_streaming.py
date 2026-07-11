"""Tests for the DSPy-mediated streaming narration helper.

Covers:
- ``_extract_stream_delta`` (robust to object/dict chunk shapes, never raises)
- ``_dm_stream_system_prompt`` (reuses the DMNarration persona)
- ``stream_narration_dspy`` (drives litellm async streaming via the
  DSPy-configured LM, yields non-empty deltas, passes model + messages + key)
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.llm import config as llm_config
from app.llm.dspy_modules import (
    _extract_stream_delta,
    _dm_stream_system_prompt,
    stream_narration_dspy,
)


# --------------------------------------------------------------------------- #
# _extract_stream_delta
# --------------------------------------------------------------------------- #

class TestExtractStreamDelta:
    def test_object_shaped_chunk(self):
        chunk = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="Hello "))]
        )
        assert _extract_stream_delta(chunk) == "Hello "

    def test_dict_shaped_chunk(self):
        chunk = {"choices": [{"delta": {"content": "world!"}}]}
        assert _extract_stream_delta(chunk) == "world!"

    def test_empty_choices(self):
        assert _extract_stream_delta({"choices": []}) == ""

    def test_delta_without_content(self):
        # litellm sometimes sends a delta with role only, or empty content
        chunk = {"choices": [{"delta": {"role": "assistant"}}]}
        assert _extract_stream_delta(chunk) == ""
        chunk2 = {"choices": [{"delta": {"content": None}}]}
        assert _extract_stream_delta(chunk2) == ""

    def test_missing_choices_key(self):
        assert _extract_stream_delta({}) == ""

    def test_arbitrary_object_input(self):
        assert _extract_stream_delta(object()) == ""

    def test_never_raises_on_malformed_input(self):
        # A single bad chunk must not propagate an exception (the generator
        # must stay alive across the whole stream).
        assert _extract_stream_delta({"choices": "not-a-list"}) == ""
        assert _extract_stream_delta({"choices": [42]}) == ""


# --------------------------------------------------------------------------- #
# _dm_stream_system_prompt
# --------------------------------------------------------------------------- #

class TestDmStreamSystemPrompt:
    def test_contains_dm_persona(self):
        prompt = _dm_stream_system_prompt()
        # The DMNarration signature docstring persona must be present.
        assert "Dungeon Master" in prompt
        assert "Heroic fantasy" in prompt

    def test_contains_output_instructions(self):
        prompt = _dm_stream_system_prompt()
        assert "Respond ONLY" in prompt
        assert "narration text" in prompt


# --------------------------------------------------------------------------- #
# stream_narration_dspy
# --------------------------------------------------------------------------- #

class _FakeLM:
    """Stand-in for a configured dspy.LM (model string + kwargs only)."""
    model = "openrouter/test-model"
    kwargs = {"temperature": 0.8, "max_tokens": 4096}


def _make_acompletion(chunks, captured):
    """Build a fake litellm.acompletion that records kwargs + streams chunks."""
    async def _acompletion(**kwargs):
        captured.update(kwargs)
        async def _gen():
            for c in chunks:
                yield c
        return _gen()
    return _acompletion


class TestStreamNarrationDspy:
    def _collect(self, user_prompt):
        out = []
        async def _go():
            async for piece in stream_narration_dspy(user_prompt):
                out.append(piece)
        asyncio.run(_go())
        return out

    def test_yields_content_deltas_in_order(self):
        chunks = [
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="The "))]),
            {"choices": [{"delta": {"content": "tower "}}]},
            {"choices": [{"delta": {"content": "glows."}}]},
        ]
        captured = {}
        with patch("app.llm.dspy_config.get_dspy_lm", return_value=_FakeLM()), \
             patch("app.llm.dspy_config.ensure_dspy_configured"), \
             patch("litellm.acompletion", new=_make_acompletion(chunks, captured)), \
             patch.object(llm_config.config, "api_key", ""):
            out = self._collect("A scene to narrate.")
        assert "".join(out) == "The tower glows."

    def test_skips_empty_deltas(self):
        chunks = [
            {"choices": [{"delta": {"content": "Hi"}}]},
            {"choices": [{"delta": {"role": "assistant"}}]},   # no content
            {"choices": []},                                    # no choices
            {"choices": [{"delta": {"content": " there"}}]},
        ]
        captured = {}
        with patch("app.llm.dspy_config.get_dspy_lm", return_value=_FakeLM()), \
             patch("app.llm.dspy_config.ensure_dspy_configured"), \
             patch("litellm.acompletion", new=_make_acompletion(chunks, captured)), \
             patch.object(llm_config.config, "api_key", ""):
            out = self._collect("scene")
        assert out == ["Hi", " there"]

    def test_passes_model_and_stream_flag(self):
        captured = {}
        chunks = [{"choices": [{"delta": {"content": "x"}}]}]
        with patch("app.llm.dspy_config.get_dspy_lm", return_value=_FakeLM()), \
             patch("app.llm.dspy_config.ensure_dspy_configured"), \
             patch("litellm.acompletion", new=_make_acompletion(chunks, captured)), \
             patch.object(llm_config.config, "api_key", ""):
            self._collect("scene")
        assert captured["model"] == "openrouter/test-model"
        assert captured["stream"] is True
        # LM kwargs are forwarded.
        assert captured["temperature"] == 0.8
        assert captured["max_tokens"] == 4096

    def test_builds_system_message_with_persona(self):
        captured = {}
        chunks = [{"choices": [{"delta": {"content": "x"}}]}]
        with patch("app.llm.dspy_config.get_dspy_lm", return_value=_FakeLM()), \
             patch("app.llm.dspy_config.ensure_dspy_configured"), \
             patch("litellm.acompletion", new=_make_acompletion(chunks, captured)), \
             patch.object(llm_config.config, "api_key", ""):
            self._collect("the scene")
        messages = captured["messages"]
        assert messages[0]["role"] == "system"
        assert "Dungeon Master" in messages[0]["content"]
        assert messages[1] == {"role": "user", "content": "the scene"}

    def test_passes_api_key_when_configured(self):
        captured = {}
        chunks = [{"choices": [{"delta": {"content": "x"}}]}]
        with patch("app.llm.dspy_config.get_dspy_lm", return_value=_FakeLM()), \
             patch("app.llm.dspy_config.ensure_dspy_configured"), \
             patch("litellm.acompletion", new=_make_acompletion(chunks, captured)), \
             patch.object(llm_config.config, "api_key", "secret-key-123"):
            self._collect("scene")
        assert captured.get("api_key") == "secret-key-123"

    def test_omits_api_key_when_unset(self):
        captured = {}
        chunks = [{"choices": [{"delta": {"content": "x"}}]}]
        with patch("app.llm.dspy_config.get_dspy_lm", return_value=_FakeLM()), \
             patch("app.llm.dspy_config.ensure_dspy_configured"), \
             patch("litellm.acompletion", new=_make_acompletion(chunks, captured)), \
             patch.object(llm_config.config, "api_key", ""):
            self._collect("scene")
        assert "api_key" not in captured
