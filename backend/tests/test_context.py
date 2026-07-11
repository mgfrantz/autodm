"""
Tests for context window management and story summarization.
"""
import json
from datetime import datetime
from unittest.mock import patch, Mock

import dspy
import pytest

from app.engine.context import (
    ContextManager,
    StorySummary,
    get_context_manager,
)
from app.llm.dspy_modules import (
    StorySummaryModule,
    get_story_summary_module,
)


class TestStorySummary:
    """Test StorySummary dataclass."""

    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        summary = StorySummary(
            summary="The hero began their journey.",
            npcs_met=["Aldric - wise old wizard"],
            key_locations=["Grimhollow", "Dark Forest"],
            active_quests=["Find the lost amulet"],
            completed_quests=["Defeat the goblins"],
            current_act=1,
            last_summarized_at="2025-01-01T00:00:00",
            entries_summarized=10,
            summary_created_at="2025-01-01T00:00:00",
        )

        data = summary.to_dict()
        assert data["summary"] == "The hero began their journey."
        assert len(data["npcs_met"]) == 1
        assert data["current_act"] == 1
        assert data["entries_summarized"] == 10

        restored = StorySummary.from_dict(data)
        assert restored.summary == summary.summary
        assert restored.current_act == summary.current_act
        assert restored.entries_summarized == summary.entries_summarized


class TestContextManager:
    """Test context management logic."""

    def test_default_thresholds(self):
        """Test default configuration."""
        cm = ContextManager()
        assert cm.summary_threshold == 20
        assert cm.keep_raw_entries == 10

    def test_custom_thresholds(self):
        """Test custom configuration."""
        cm = ContextManager(summary_threshold=30, keep_raw_entries=15)
        assert cm.summary_threshold == 30
        assert cm.keep_raw_entries == 15

    def test_should_summarize_no_summary(self):
        """Test summarization trigger with no existing summary."""
        cm = ContextManager(summary_threshold=20)

        # Not enough entries
        story_log = [{"role": "dm", "content": "Test"}] * 10
        assert not cm.should_summarize(story_log, None)

        # Enough entries
        story_log = [{"role": "dm", "content": "Test"}] * 25
        assert cm.should_summarize(story_log, None)

    def test_should_summarize_with_summary(self):
        """Test summarization trigger with existing summary."""
        cm = ContextManager(summary_threshold=20)

        summary = StorySummary(
            summary="Previous events...",
            npcs_met=[],
            key_locations=[],
            active_quests=[],
            completed_quests=[],
            current_act=1,
            last_summarized_at="2025-01-01",
            entries_summarized=20,
            summary_created_at="2025-01-01",
        )

        # Not enough new entries (20 + 19 = 39, threshold is 20 new entries)
        story_log = [{"role": "dm", "content": "Test"}] * 39
        assert not cm.should_summarize(story_log, summary)

        # Enough new entries (20 + 20 = 40)
        story_log = [{"role": "dm", "content": "Test"}] * 40
        assert cm.should_summarize(story_log, summary)

    def test_build_context_no_summary(self):
        """Test context building without a summary."""
        cm = ContextManager(keep_raw_entries=5)

        story_log = [
            {"role": "dm", "content": "Welcome to the adventure."},
            {"role": "player", "content": "I look around."},
            {"role": "dm", "content": "You see a forest."},
        ]

        context = cm.build_context(story_log, None)
        assert "RECENT EVENTS:" in context
        assert "Welcome to the adventure" in context
        assert "I look around" in context

    def test_build_context_with_summary(self):
        """Test context building with a summary."""
        cm = ContextManager(keep_raw_entries=5)

        summary = StorySummary(
            summary="The hero defeated the dragon.",
            npcs_met=["Aldric - wizard", "Elena - blacksmith"],
            key_locations=["Grimhollow", "Dragon's Lair"],
            active_quests=["Find the artifact"],
            completed_quests=["Defeat the dragon"],
            current_act=2,
            last_summarized_at="2025-01-01",
            entries_summarized=15,
            summary_created_at="2025-01-01",
        )

        # Recent entries (after summary)
        story_log = [{"role": "dm", "content": "Test"}] * 20
        story_log[15] = {"role": "dm", "content": "Recent event 1"}
        story_log[16] = {"role": "player", "content": "I do something"}
        story_log[17] = {"role": "dm", "content": "Recent event 2"}

        context = cm.build_context(story_log, summary)
        assert "STORY SO FAR:" in context
        assert "The hero defeated the dragon" in context
        assert "NPCs Met: Aldric - wizard, Elena - blacksmith" in context
        assert "Active Quests: Find the artifact" in context
        assert "RECENT EVENTS:" in context

    def test_build_context_respects_keep_raw_entries(self):
        """Test that only the last N recent entries are included."""
        cm = ContextManager(keep_raw_entries=3)

        story_log = [{"role": "dm", "content": f"Entry {i}"} for i in range(10)]

        context = cm.build_context(story_log, None)
        # Should only have last 3 entries (7, 8, 9)
        assert "Entry 6" not in context
        assert "Entry 7" in context
        assert "Entry 8" in context
        assert "Entry 9" in context

    def test_build_context_with_summary_only_shows_recent(self):
        """Test that when summary exists, only entries AFTER it are shown."""
        cm = ContextManager(keep_raw_entries=10)

        summary = StorySummary(
            summary="Summary",
            npcs_met=[],
            key_locations=[],
            active_quests=[],
            completed_quests=[],
            current_act=1,
            last_summarized_at="2025-01-01",
            entries_summarized=15,
            summary_created_at="2025-01-01",
        )

        story_log = [{"role": "dm", "content": f"Entry {i}"} for i in range(25)]

        context = cm.build_context(story_log, summary)
        # Entries 0-14 should be excluded (summarized)
        assert "Entry 10" not in context
        assert "Entry 15" in context

    def test_build_context_truncates_long_entries(self):
        """Test that long story entries are truncated."""
        cm = ContextManager(keep_raw_entries=2)

        long_content = "x" * 500
        story_log = [
            {"role": "dm", "content": long_content},
            {"role": "player", "content": "short"},
        ]

        context = cm.build_context(story_log, None)
        assert len(context) < 500  # Should be truncated
        assert "short" in context

    def test_get_estimated_tokens(self):
        """Test token estimation."""
        cm = ContextManager()
        # Rough estimate: 4 chars ≈ 1 token
        assert cm.get_estimated_tokens("hello world") == 2  # 11 chars / 4 = 2
        assert cm.get_estimated_tokens("") == 0

    @pytest.mark.asyncio
    async def test_summarize_story_no_existing_summary(self):
        """Test summarization with no existing summary."""
        cm = ContextManager()

        # Mock the DSPy story-summary module (sync forward, run via asyncio.to_thread)
        mock_prediction = dspy.Prediction(
            summary="The hero began their adventure and met a wizard.",
            npcs_met=["Aldric - wizard"],
            key_locations=["Grimhollow"],
            active_quests=["Find the lost amulet"],
            completed_quests=[],
            current_act=1,
        )
        mock_module = Mock()
        mock_module.forward = Mock(return_value=mock_prediction)

        with patch("app.engine.context.ensure_dspy_configured") as mock_cfg, \
             patch("app.engine.context.get_story_summary_module", return_value=mock_module):
            story_log = [
                {"role": "dm", "content": "Welcome to the adventure!"},
                {"role": "player", "content": "I look around."},
                {"role": "dm", "content": "You see a village called Grimhollow."},
                {"role": "player", "content": "I walk to the village square."},
                {"role": "dm", "content": "An old wizard approaches you."},
            ]

            summary = await cm.summarize_story(story_log, None)

        assert summary.summary == "The hero began their adventure and met a wizard."
        assert summary.npcs_met == ["Aldric - wizard"]
        assert summary.key_locations == ["Grimhollow"]
        assert summary.active_quests == ["Find the lost amulet"]
        assert summary.current_act == 1
        assert summary.entries_summarized == 5

        # Verify the DSPy module was called with the formatted story text
        mock_cfg.assert_called_once()
        mock_module.forward.assert_called_once()
        story_entries = mock_module.forward.call_args[1]["story_entries"]
        assert "Welcome to the adventure!" in story_entries
        assert "Grimhollow" in story_entries

    @pytest.mark.asyncio
    async def test_summarize_story_with_existing_summary(self):
        """Test summarization that merges with existing summary."""
        cm = ContextManager()

        mock_prediction = dspy.Prediction(
            summary="The hero continued their journey and fought goblins.",
            npcs_met=[],
            key_locations=["Dark Forest"],
            active_quests=["Find the lost amulet"],
            completed_quests=["Defeat the goblins"],
            current_act=2,
        )
        mock_module = Mock()
        mock_module.forward = Mock(return_value=mock_prediction)

        existing_summary = StorySummary(
            summary="The hero began their adventure.",
            npcs_met=["Aldric - wizard"],
            key_locations=["Grimhollow"],
            active_quests=["Find the lost amulet"],
            completed_quests=[],
            current_act=1,
            last_summarized_at="2025-01-01",
            entries_summarized=5,
            summary_created_at="2025-01-01",
        )

        # New entries
        story_log = [
            {"role": "dm", "content": "Entry 1"},
            {"role": "player", "content": "Action 1"},
        ] * 5  # 10 new entries (total 15)
        # Prepend the old entries to simulate full log
        story_log = [{"role": "dm", "content": "Old"}] * 5 + story_log

        with patch("app.engine.context.ensure_dspy_configured"), \
             patch("app.engine.context.get_story_summary_module", return_value=mock_module):
            summary = await cm.summarize_story(story_log, existing_summary)

        assert summary.current_act == 2
        assert summary.entries_summarized == 15

        # Verify that the existing summary was included in the story_entries input
        story_entries = mock_module.forward.call_args[1]["story_entries"]
        assert "PREVIOUS SUMMARY:" in story_entries
        assert "The hero began their adventure" in story_entries

    def test_build_context_empty_story_log(self):
        """Test context building with empty story log."""
        cm = ContextManager()
        context = cm.build_context([], None)
        assert context == ""

    def test_build_context_empty_summary(self):
        """Test context building with summary but no recent entries."""
        cm = ContextManager()

        summary = StorySummary(
            summary="The hero began their journey.",
            npcs_met=["Aldric - wizard"],
            key_locations=["Grimhollow"],
            active_quests=["Find the lost amulet"],
            completed_quests=[],
            current_act=1,
            last_summarized_at="2025-01-01",
            entries_summarized=5,
            summary_created_at="2025-01-01",
        )

        context = cm.build_context([], summary)
        assert "STORY SO FAR:" in context
        assert "The hero began their journey" in context
        assert "RECENT EVENTS:" not in context  # No recent entries


def test_get_context_manager_singleton():
    """Test that get_context_manager returns the same instance."""
    cm1 = get_context_manager()
    cm2 = get_context_manager()
    assert cm1 is cm2


# ---------------------------------------------------------------------------
# StorySummaryModule (DSPy) tests
# ---------------------------------------------------------------------------

class TestStorySummaryModule:
    """Test the DSPy StorySummaryModule singleton + graceful failure."""

    def test_singleton_is_cached(self):
        """The module singleton is created once and reused."""
        first = get_story_summary_module()
        assert get_story_summary_module() is first

    def test_forward_returns_structured_summary(self):
        """forward() returns a Prediction with the summary fields."""
        mod = StorySummaryModule()
        mock_result = dspy.Prediction(
            summary="The hero entered Grimhollow.",
            npcs_met=["Aldric - wizard"],
            key_locations=["Grimhollow"],
            active_quests=["Find the amulet"],
            completed_quests=[],
            current_act=1,
        )
        with patch.object(mod, "generate", return_value=mock_result):
            result = mod(story_entries="[dm]: The hero entered Grimhollow.")
        assert result.summary == "The hero entered Grimhollow."
        assert result.npcs_met == ["Aldric - wizard"]
        assert result.current_act == 1

    def test_forward_failure_returns_empty_prediction(self):
        """A DSPy failure yields a graceful empty Prediction (act defaults to 1)."""
        mod = StorySummaryModule()
        with patch.object(mod, "generate", side_effect=RuntimeError("boom")):
            result = mod(story_entries="[dm]: something happened.")
        assert result.summary == ""
        assert result.npcs_met == []
        assert result.current_act == 1


class TestSummarizeStoryGracefulFallback:
    """ContextManager.summarize_story must degrade gracefully on DSPy failure."""

    @pytest.mark.asyncio
    async def test_module_failure_yields_empty_summary(self):
        """When the DSPy module raises, summarize_story still returns a summary."""
        cm = ContextManager()

        mock_module = Mock()
        mock_module.forward = Mock(side_effect=RuntimeError("LM down"))

        with patch("app.engine.context.ensure_dspy_configured"), \
             patch("app.engine.context.get_story_summary_module", return_value=mock_module):
            story_log = [{"role": "dm", "content": f"Entry {i}"} for i in range(25)]
            summary = await cm.summarize_story(story_log, None)

        # Graceful empty fallback — no crash, sensible defaults
        assert summary.summary == ""
        assert summary.npcs_met == []
        assert summary.current_act == 1
        assert summary.entries_summarized == 25