from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from .player_agent import PlayerAgent
    from .npc import NPC
    from .battle import Battle

    CharacterUnion = Union[PlayerAgent, NPC]
else:
    CharacterUnion = Union['PlayerAgent', 'NPC']
    PlayerAgent = 'PlayerAgent'  # Add this line

# Add this line at the end of the file
Battle = 'Battle'  # This is a string to avoid circular imports