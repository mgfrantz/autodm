from pydantic import BaseModel
from ..core.enums import ActionType

class TurnState(BaseModel):
    standard_action_taken: bool = False
    movement_taken: bool = False
    has_bonus_action: bool = False
    bonus_action_taken: bool = False
    reaction_taken: bool = False
    movement_remaining: int = 0

    def take_action(self, action_type: ActionType) -> bool:
        if action_type == ActionType.STANDARD and not self.standard_action_taken:
            self.standard_action_taken = True
            return True
        elif action_type == ActionType.MOVEMENT and not self.movement_taken:
            self.movement_taken = True
            return True
        elif action_type == ActionType.BONUS and not self.bonus_action_taken:
            self.bonus_action_taken = True
            return True
        elif action_type == ActionType.REACTION and not self.reaction_taken:
            self.reaction_taken = True
            return True
        return False

    def can_take_action(self, action_type: ActionType) -> bool:
        if action_type == ActionType.STANDARD:
            return not self.standard_action_taken
        elif action_type == ActionType.MOVEMENT:
            return not self.movement_taken and self.movement_remaining > 0
        elif action_type == ActionType.BONUS:
            return not self.bonus_action_taken
        elif action_type == ActionType.REACTION:
            return not self.reaction_taken
        return False

    def reset(self, movement_speed: int):
        self.standard_action_taken = False
        self.movement_taken = False
        self.bonus_action_taken = False
        self.reaction_taken = False
        self.movement_remaining = movement_speed