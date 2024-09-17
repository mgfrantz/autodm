from typing import Dict
from pydantic import BaseModel, Field

class SpellSlots(BaseModel):
    slots: Dict[int, int] = Field(default_factory=lambda: {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0})

    def use_slot(self, level: int) -> bool:
        """
        Use a spell slot of the given level.

        Args:
            level (int): The level of the spell slot to use.

        Returns:
            bool: True if the slot was successfully used, False if no slots of that level were available.
        """
        if self.slots[level] > 0:
            self.slots[level] -= 1
            return True
        return False

    def restore_slot(self, level: int):
        """
        Restore a spell slot of the given level.

        Args:
            level (int): The level of the spell slot to restore.
        """
        self.slots[level] += 1

    def restore_all(self):
        """
        Restore all spell slots to their maximum value.
        This should be called after a long rest.
        """
        # This is a placeholder. In a real implementation, this would restore
        # slots based on the character's class and level.
        for level in self.slots:
            self.slots[level] = 4  # Example: 4 slots per level

    def get_slots(self, level: int) -> int:
        """
        Get the number of available spell slots for a given level.

        Args:
            level (int): The level of spell slots to check.

        Returns:
            int: The number of available spell slots of the given level.
        """
        return self.slots[level]

    def set_max_slots(self, level: int, max_slots: int):
        """
        Set the maximum number of spell slots for a given level.

        Args:
            level (int): The level of spell slots to set.
            max_slots (int): The maximum number of slots for this level.
        """
        self.slots[level] = max_slots

    def __str__(self):
        return ", ".join([f"Level {level}: {slots}" for level, slots in self.slots.items() if slots > 0])
