from __future__ import annotations
from typing import List, Optional

from pydantic import BaseModel, Field

from ..character.models import Character
from .enums import AbilityEnum
from .dice import Check


class Round(BaseModel):
    """Represents a single round of combat."""
    initiative_order: List[Character] = []
    current_turn: int = 0


class Combat(BaseModel):
    """Represents the overall combat encounter."""
    participants: List[Character]
    rounds: List[Round] = Field(default_factory=list)
    is_active: bool = True


class Game(BaseModel):
    """Top-level class representing a D&D game session."""
    dungeon_master: str
    players: List[Character]
    combat: Optional[Combat] = None

    def start_combat(self):
        """Initiates combat."""
        if self.combat is None:
            self.combat = Combat(participants=self.players)
            self.combat.rounds.append(Round())  # start with first round

    def set_initiative(self):
        """Sets initiative for all combat participants"""
        if self.combat is not None:
            current_round = self.combat.rounds[-1]

            for character in self.combat.participants:
                initiative_check = Check(character=character, target=AbilityEnum.DEXTERITY)
                initiative_roll = initiative_check.resolve()
                # Pair each character with their initiative roll
                current_round.initiative_order.append((character, initiative_roll))

            # Sort the initiative order by the initiative roll (second element of the tuple)
            current_round.initiative_order.sort(key=lambda x: x[1], reverse=True)

            # Extract only characters from sorted list
            current_round.initiative_order = [char for char, roll in current_round.initiative_order]

    def end_combat(self):
        """Ends the combat encounter."""
        if self.combat is not None:
            self.combat.is_active = False

    def advance_turn(self):
        """Progresses to the next turn in combat."""
        if self.combat and self.combat.is_active:
            current_round = self.combat.rounds[-1]
            current_round.current_turn += 1
            if current_round.current_turn >= len(current_round.initiative_order):
                # End of round, start a new round
                self.combat.rounds.append(Round())
                self.set_initiative()
                self.combat.rounds[-1].current_turn = 0 