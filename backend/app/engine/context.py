"""
Context Window Management — smart story summarization for efficient LLM context.

As the story log grows, old entries are summarized and condensed to keep the
context window manageable. The system maintains:
1. A summary of early game events
2. Recent raw entries for freshness
3. Structured summaries (NPCs, quests, locations) for fast retrieval

Summarization is mediated by DSPy (``StorySummaryModule``).
"""
import asyncio
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Optional

from app.llm.dspy_config import ensure_dspy_configured
from app.llm.dspy_modules import get_story_summary_module

logger = logging.getLogger(__name__)


@dataclass
class StorySummary:
    """Structured summary of story progress."""
    # Narrative summary
    summary: str  # Prose summary of key events
    
    # Structured data for quick reference
    npcs_met: list[str]  # Names and brief descriptions of NPCs encountered
    key_locations: list[str]  # Important places visited
    active_quests: list[str]  # Current quest objectives
    completed_quests: list[str]  # Finished quests
    current_act: int  # Story act number
    last_summarized_at: str  # ISO timestamp of last summary
    
    # Metadata
    entries_summarized: int  # How many story entries this summary covers
    summary_created_at: str  # When this summary was created
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StorySummary":
        """Create from JSON-serializable dict."""
        return cls(**data)


def _coerce_act(value: Any, default: int) -> int:
    """Coerce an LLM-returned act value to an int, falling back on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class ContextManager:
    """Manages story summarization and context building for LLM calls."""
    
    def __init__(
        self,
        summary_threshold: int = 20,  # Summarize after this many entries
        keep_raw_entries: int = 10,   # Keep this many recent entries un-summarized
    ):
        self.summary_threshold = summary_threshold
        self.keep_raw_entries = keep_raw_entries
    
    def should_summarize(self, story_log: list[dict], summary: Optional[StorySummary]) -> bool:
        """Check if story log is long enough to trigger summarization.
        
        Args:
            story_log: Current story log entries
            summary: Existing summary (if any)
        
        Returns:
            True if summarization is needed
        """
        # If we have no summary and log is over threshold
        if summary is None and len(story_log) > self.summary_threshold:
            return True
        
        # If we have a summary, check how many NEW entries since last summary
        # Use >= so that exactly threshold new entries triggers summarization
        if summary:
            new_entries = len(story_log) - summary.entries_summarized
            return new_entries >= self.summary_threshold
        
        return False
    
    async def summarize_story(
        self,
        story_log: list[dict],
        existing_summary: Optional[StorySummary] = None,
    ) -> StorySummary:
        """Generate a summary of the story log entries.
        
        Args:
            story_log: Full story log entries
            existing_summary: Previous summary to merge with (if any)
        
        Returns:
            New StorySummary covering all entries
        """
        # Determine which entries to summarize
        if existing_summary:
            # Summarize only new entries since last summary
            entries_to_summarize = story_log[existing_summary.entries_summarized:]
            base_summary = existing_summary.summary
            current_act = existing_summary.current_act
        else:
            # Summarize all entries
            entries_to_summarize = story_log
            base_summary = ""
            current_act = 1
        
        # Build story text for LLM
        story_text = "\n\n".join(
            f"[{entry.get('role', 'unknown')}]: {entry.get('content', '')}"
            for entry in entries_to_summarize
        )
        
        # If we have an existing summary, include it for context
        if base_summary:
            story_text = f"PREVIOUS SUMMARY:\n{base_summary}\n\nNEW EVENTS:\n{story_text}"
        
        # Generate summary via DSPy (sync call offloaded to a worker thread
        # so the async event loop is not blocked while the LM responds).
        ensure_dspy_configured()
        module = get_story_summary_module()
        try:
            result = await asyncio.to_thread(module.forward, story_entries=story_text)
        except Exception as e:
            logger.error(f"Story summarization failed: {e}")
            result = None
        
        # Build StorySummary from the DSPy Prediction (with graceful
        # fallbacks if the module returned an empty/None result).
        now = datetime.utcnow().isoformat()
        entries_count = len(story_log)
        
        summary = StorySummary(
            summary=getattr(result, "summary", "") or "",
            npcs_met=getattr(result, "npcs_met", None) or [],
            key_locations=getattr(result, "key_locations", None) or [],
            active_quests=getattr(result, "active_quests", None) or [],
            completed_quests=getattr(result, "completed_quests", None) or [],
            current_act=_coerce_act(getattr(result, "current_act", None), current_act),
            last_summarized_at=now,
            entries_summarized=entries_count,
            summary_created_at=now,
        )
        
        return summary
    
    def build_context(
        self,
        story_log: list[dict],
        summary: Optional[StorySummary] = None,
        max_recent_entries: Optional[int] = None,
    ) -> str:
        """Build context string for LLM calls combining summary and recent entries.
        
        Args:
            story_log: Current story log entries
            summary: Optional story summary
            max_recent_entries: Override default keep_raw_entries
        
        Returns:
            Context string for LLM prompt
        """
        keep = max_recent_entries or self.keep_raw_entries
        parts = []
        
        # Add summary if available
        if summary:
            parts.append(f"STORY SO FAR:\n{summary.summary}")
            
            # Add structured summaries for quick reference
            if summary.npcs_met:
                parts.append(f"\nNPCs Met: {', '.join(summary.npcs_met)}")
            if summary.key_locations:
                parts.append(f"Locations Visited: {', '.join(summary.key_locations)}")
            if summary.active_quests:
                parts.append(f"Active Quests: {', '.join(summary.active_quests)}")
            if summary.completed_quests:
                parts.append(f"Completed Quests: {', '.join(summary.completed_quests)}")
        
        # Add recent raw entries
        if story_log:
            # Determine starting index for recent entries
            if summary:
                # If we have a summary, only include entries AFTER it
                start_idx = summary.entries_summarized
                recent = story_log[start_idx:]
            else:
                # No summary, just get the last N entries
                recent = story_log[-keep:]
            
            # Always limit to the last `keep` entries
            recent = recent[-keep:] if len(recent) > keep else recent
            
            if recent:
                parts.append("\n\nRECENT EVENTS:")
                for entry in recent:
                    role = entry.get('role', 'unknown')
                    content = entry.get('content', '')[:300]  # Truncate long entries
                    parts.append(f"[{role}]: {content}")
        
        return "\n".join(parts)
    
    def get_estimated_tokens(self, text: str) -> int:
        """Rough estimate of token count (4 chars ≈ 1 token).
        
        Args:
            text: Text to estimate
        
        Returns:
            Estimated token count
        """
        return len(text) // 4


# Default singleton
_default_manager = ContextManager()


def get_context_manager() -> ContextManager:
    """Get the default context manager singleton."""
    return _default_manager