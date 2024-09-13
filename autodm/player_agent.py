from typing import List, Optional, Dict, Union, TYPE_CHECKING
from llama_index.core.tools import BaseTool, FunctionTool
from llama_index.core.agent import ReActAgent
from .character_agent import CharacterAgent
from .character import Character, Attributes, Position
from .spells import Spell
from pydantic import Field
from .llm import get_llm, complete
from .skill_checks import perform_skill_check, perform_ability_check
from .npc import NPC
import re

if TYPE_CHECKING:
    from .battle import Battle
else:
    from .types import Battle

class PlayerAgent(CharacterAgent):
    def __init__(self, character: Character):
        super().__init__(character)
        self.is_npc = False