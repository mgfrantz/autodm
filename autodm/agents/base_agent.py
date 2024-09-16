from pydantic import BaseModel, Field
from ..core.character import Character

class BaseAgent(BaseModel):
    character: Character = Field(..., description="The character that the agent is controlling")