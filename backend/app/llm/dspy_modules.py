"""DSPy modules for character creation, world generation, and DM narration."""
import logging
import dspy
from app.llm.dspy_signatures import GenerateCharacterFlavor, GenerateWorld, DMNarration

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
