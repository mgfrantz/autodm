"""DSPy modules for character creation."""
import logging
import dspy
from app.llm.dspy_signatures import GenerateCharacterFlavor

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
