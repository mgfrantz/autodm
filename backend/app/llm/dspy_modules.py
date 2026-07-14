"""DSPy modules for character creation, world generation, and DM narration."""
import logging
from typing import AsyncIterator

import dspy

from app.llm.dspy_signatures import (
    GenerateCharacterFlavor,
    GenerateWorld,
    DMNarration,
    DMActionableNarration,
    SummarizeStory,
    DetectQuests,
    DetectNPCMoodChanges,
    DetectGameFlags,
    GenerateActionSuggestions,
    ResolveSkillCheck,
)

logger = logging.getLogger(__name__)

class CharacterCreationModule(dspy.Module):
    """Generate DnD 5e character flavor (backstory + personality profile)."""

    def __init__(self):
        super().__init__()
        self.generate = dspy.ChainOfThought(GenerateCharacterFlavor)

    def forward(self, *, race, char_class, background, alignment, level,
                strength, dexterity, constitution, intelligence, wisdom, charisma):
        try:
            return self.generate(
                race=race, char_class=char_class,
                background=background or "Unknown", alignment=alignment or "neutral",
                level=level, strength=strength, dexterity=dexterity,
                constitution=constitution, intelligence=intelligence,
                wisdom=wisdom, charisma=charisma,
            )
        except Exception as e:
            logger.error(f"Character flavor generation failed: {e}")
            return dspy.Prediction(
                name="", backstory="", personality_traits=[], ideal="", bond="", flaw="",
            )

# Singleton
_character_creation: CharacterCreationModule | None = None

def get_character_creation_module() -> CharacterCreationModule:
    global _character_creation
    if _character_creation is None:
        _character_creation = CharacterCreationModule()
    return _character_creation


class WorldGenerationModule(dspy.Module):
    """Generate a complete DnD 5e world (regions, arc, NPCs, factions, hook)."""

    def __init__(self):
        super().__init__()
        self.generate = dspy.ChainOfThought(GenerateWorld)

    def forward(self, *, tone, character_context=""):
        try:
            return self.generate(tone=tone, character_context=character_context)
        except Exception as e:
            logger.error(f"World generation failed: {e}")
            return dspy.Prediction(
                name="", description="", world_tone="",
                regions=[], campaign_arc={}, starting_settlement={},
                npcs=[], factions=[], hook="",
            )

    def to_world_dict(self, result, fallback_tone: str = "") -> dict:
        """Convert a module Prediction into the WORLD_SCHEMA-compatible dict
        consumed by the rest of the codebase."""
        return {
            "name": result.name or "Unnamed World",
            "description": result.description or "",
            "tone": getattr(result, "world_tone", "") or fallback_tone,
            "regions": result.regions or [],
            "campaign_arc": result.campaign_arc or {},
            "starting_settlement": result.starting_settlement or {},
            "npcs": result.npcs or [],
            "factions": result.factions or [],
            "hook": result.hook or "",
        }


# Singleton
_world_generation: WorldGenerationModule | None = None

def get_world_generation_module() -> WorldGenerationModule:
    global _world_generation
    if _world_generation is None:
        _world_generation = WorldGenerationModule()
    return _world_generation


class DMNarrationModule(dspy.Module):
    """Generate free-text DM narration for a scene or player action."""

    def __init__(self):
        super().__init__()
        self.generate = dspy.ChainOfThought(DMNarration)

    def forward(self, *, situation):
        try:
            return self.generate(situation=situation)
        except Exception as e:
            logger.error(f"DM narration failed: {e}")
            return dspy.Prediction(narration="")


# Singleton
_dm_narration: DMNarrationModule | None = None

def get_dm_narration_module() -> DMNarrationModule:
    global _dm_narration
    if _dm_narration is None:
        _dm_narration = DMNarrationModule()
    return _dm_narration


class DMActionableNarrationModule(dspy.Module):
    """Generate DM narration with structured game actions for mechanical resolution.

    Like :class:`DMNarrationModule` but the output includes ``game_actions`` —
    a list of structured action dicts that the backend resolves via the engine
    (dice rolls, check prompts). Used by the ``/action`` endpoints (not
    ``/start``) so the opening narration remains backward-compatible.
    """

    def __init__(self):
        super().__init__()
        self.generate = dspy.ChainOfThought(DMActionableNarration)

    def forward(self, *, situation):
        try:
            return self.generate(situation=situation)
        except Exception as e:
            logger.error(f"DM actionable narration failed: {e}")
            return dspy.Prediction(narration="", game_actions=[])


# Singleton
_dm_actionable_narration: DMActionableNarrationModule | None = None

def get_dm_actionable_narration_module() -> DMActionableNarrationModule:
    global _dm_actionable_narration
    if _dm_actionable_narration is None:
        _dm_actionable_narration = DMActionableNarrationModule()
    return _dm_actionable_narration


class StorySummaryModule(dspy.Module):
    """Summarize story log entries into a structured story summary.

    Given the formatted story text (optionally prefixed with a previous
    summary), produce a structured summary (prose + NPCs + locations +
    quests + act number).
    """

    def __init__(self):
        super().__init__()
        self.generate = dspy.ChainOfThought(SummarizeStory)

    def forward(self, *, story_entries):
        try:
            return self.generate(story_entries=story_entries)
        except Exception as e:
            logger.error(f"Story summarization failed: {e}")
            return dspy.Prediction(
                summary="",
                npcs_met=[],
                key_locations=[],
                active_quests=[],
                completed_quests=[],
                current_act=1,
            )


# Singleton
_story_summary: StorySummaryModule | None = None

def get_story_summary_module() -> StorySummaryModule:
    global _story_summary
    if _story_summary is None:
        _story_summary = StorySummaryModule()
    return _story_summary


# --- Streaming narration -------------------------------------------------
#
# The DM narration endpoints offer a streaming variant (Server-Sent Events)
# so the player sees the DM "talk" in real time. The non-streaming path uses
# ``DMNarrationModule`` (a ChainOfThought), but ChainOfThought emits a hidden
# reasoning trace that we do NOT want streamed to the player — only the final
# narration prose. So the streaming path drives litellm's async streaming
# directly through the same DSPy-configured ``dspy.LM`` (provider-agnostic),
# reusing the ``DMNarration`` signature's persona as the system prompt. This
# keeps a single source of truth for the DM persona while yielding raw tokens.

_DM_STREAM_OUTPUT_INSTRUCTIONS = (
    "\n\nYou will be given a situation to narrate. Respond ONLY with the vivid "
    "DM narration (2-4 paragraphs), ending with clear choices when appropriate. "
    "Do not include any preamble, labels, reasoning, field names, or JSON — "
    "only the narration text itself."
)


def _dm_stream_system_prompt() -> str:
    """Build the system prompt for streaming DM narration.

    Reuses the ``DMNarration`` signature docstring (the DM persona) so the
    streaming and non-streaming narration paths share one persona definition.
    """
    persona = (DMNarration.__doc__ or "").strip()
    return persona + _DM_STREAM_OUTPUT_INSTRUCTIONS


def _extract_stream_delta(chunk) -> str:
    """Pull the streamed text delta from a litellm chunk.

    litellm streaming chunks are returned as ModelResponse-style objects that
    also support dict access; this helper is robust to both shapes and never
    raises (callers rely on the generator staying alive across chunks).
    """
    try:
        if hasattr(chunk, "choices"):
            choices = chunk.choices
        elif isinstance(chunk, dict):
            choices = chunk.get("choices") or []
        else:
            return ""
        if not choices:
            return ""
        choice = choices[0]
        if isinstance(choice, dict):
            delta = choice.get("delta") or {}
            return delta.get("content") or ""
        delta = getattr(choice, "delta", None)
        if delta is None:
            return ""
        if isinstance(delta, dict):
            return delta.get("content") or ""
        return getattr(delta, "content", "") or ""
    except Exception:  # noqa: BLE001 - never let one bad chunk kill the stream
        return ""


async def stream_narration_dspy(user_prompt: str) -> AsyncIterator[str]:
    """Stream DM narration token-by-token via the DSPy-configured LM.

    This is the streaming counterpart of :class:`DMNarrationModule`. It uses
    the same DM persona (the ``DMNarration`` signature docstring) as the
    system prompt but drives litellm's async streaming directly so callers
    receive raw narration chunks — no ChainOfThought reasoning trace.

    Provider-agnostic: the request is routed through litellm using the model
    and kwargs resolved by the DSPy ``dspy.LM`` (see
    ``dspy_config.get_dspy_lm``), so it works with OpenAI, Anthropic,
    OpenRouter, and OpenAI-compatible local endpoints alike.
    """
    # Imported lazily so the module remains importable without litellm
    # installed in environments that only use the non-streaming modules.
    import litellm

    from app.llm.config import config
    from app.llm.dspy_config import ensure_dspy_configured, get_dspy_lm

    ensure_dspy_configured()
    lm = get_dspy_lm()

    messages = [
        {"role": "system", "content": _dm_stream_system_prompt()},
        {"role": "user", "content": user_prompt},
    ]

    # Merge the LM's kwargs (temperature, max_tokens, api_base for self-hosted,
    # ...) and pass the resolved API key explicitly for robustness across
    # providers — litellm would otherwise resolve it from a provider-specific
    # env var, which works but is fragile if only LLM_API_KEY is set.
    kwargs = dict(lm.kwargs)
    api_key = getattr(config, "api_key", "") or ""
    if api_key:
        kwargs["api_key"] = api_key

    stream = await litellm.acompletion(
        model=lm.model,
        messages=messages,
        stream=True,
        **kwargs,
    )
    async for chunk in stream:
        content = _extract_stream_delta(chunk)
        if content:
            yield content


class QuestDetectionModule(dspy.Module):
    """Detect quest events in DM narration (quest offered, completed, failed)."""

    def __init__(self):
        super().__init__()
        self.detect = dspy.ChainOfThought(DetectQuests)

    def forward(self, *, narration: str, existing_quests: list[str] | None = None):
        try:
            return self.detect(
                narration=narration,
                existing_quests=existing_quests or [],
            )
        except Exception as e:
            logger.error(f"Quest detection failed: {e}")
            return dspy.Prediction(
                quests_offered=[],
                quests_completed=[],
                quests_failed=[],
                information_revealed=[],
            )


# Singleton
_quest_detection: QuestDetectionModule | None = None


def get_quest_detection_module() -> QuestDetectionModule:
    global _quest_detection
    if _quest_detection is None:
        _quest_detection = QuestDetectionModule()
    return _quest_detection


class NPCMoodModule(dspy.Module):
    """Detect NPC mood/relationship changes in DM narration."""

    def __init__(self):
        super().__init__()
        self.detect = dspy.ChainOfThought(DetectNPCMoodChanges)

    def forward(self, *, narration: str):
        try:
            return self.detect(narration=narration)
        except Exception as e:
            logger.error(f"NPC mood detection failed: {e}")
            return dspy.Prediction(
                npc_mood_changes=[],
            )


# Singleton
_npc_mood_detection: NPCMoodModule | None = None


def get_npc_mood_detection_module() -> NPCMoodModule:
    global _npc_mood_detection
    if _npc_mood_detection is None:
        _npc_mood_detection = NPCMoodModule()
    return _npc_mood_detection


class GameFlagsModule(dspy.Module):
    """Detect game flags to set/clear in DM narration."""

    def __init__(self):
        super().__init__()
        self.detect = dspy.ChainOfThought(DetectGameFlags)

    def forward(self, *, narration: str):
        try:
            return self.detect(narration=narration)
        except Exception as e:
            logger.error(f"Game flags detection failed: {e}")
            return dspy.Prediction(
                flags_to_set=[],
                flags_to_clear=[],
            )


# Singleton
_game_flags_detection: GameFlagsModule | None = None


def get_game_flags_detection_module() -> GameFlagsModule:
    global _game_flags_detection
    if _game_flags_detection is None:
        _game_flags_detection = GameFlagsModule()
    return _game_flags_detection


class ActionSuggestionsModule(dspy.Module):
    """Generate scene-aware action suggestions based on DM narration."""

    def __init__(self):
        super().__init__()
        self.generate = dspy.ChainOfThought(GenerateActionSuggestions)

    def forward(self, *, narration: str):
        try:
            return self.generate(narration=narration)
        except Exception as e:
            logger.error(f"Action suggestions generation failed: {e}")
            return dspy.Prediction(
                action_suggestions=[],
            )


# Singleton
_action_suggestions: ActionSuggestionsModule | None = None


def get_action_suggestions_module() -> ActionSuggestionsModule:
    global _action_suggestions
    if _action_suggestions is None:
        _action_suggestions = ActionSuggestionsModule()
    return _action_suggestions


class SkillCheckResolverModule(dspy.Module):
    """Resolve freeform player actions with structured mechanical outcomes."""

    def __init__(self):
        super().__init__()
        self.resolve = dspy.ChainOfThought(ResolveSkillCheck)

    def forward(self, *, action: str, character_context: str, scene_context: str):
        try:
            return self.resolve(
                action=action,
                character_context=character_context,
                scene_context=scene_context,
            )
        except Exception as e:
            logger.error(f"Skill check resolution failed: {e}")
            return dspy.Prediction(
                success=False,
                degree="failure",
                stat_changes={},
                items_gained=[],
                experience_gained=0,
                narrative_notes="Resolution failed due to an error.",
            )


# Singleton
_skill_check_resolver: SkillCheckResolverModule | None = None


def get_skill_check_resolver_module() -> SkillCheckResolverModule:
    global _skill_check_resolver
    if _skill_check_resolver is None:
        _skill_check_resolver = SkillCheckResolverModule()
    return _skill_check_resolver
