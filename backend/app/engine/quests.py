"""
Quest Engine — tracks player quests detected from DM narration.

Follows the DSPy tutorial pattern: the DM narration is analyzed for
quest hooks (quests offered) and quest completion/failure.
"""
from dataclasses import dataclass, field
from app.utils.time_utils import utcnow
from typing import Any


@dataclass
class Quest:
    """A single quest in the player's quest log."""
    id: int  # Auto-incremented quest ID
    title: str  # Quest title (e.g., "Retrieve the Lost Amulet")
    description: str  # Quest description
    status: str = "active"  # active, completed, failed
    giver: str = ""  # NPC name who offered the quest
    objective: str = ""  # Primary objective
    reward_hint: str = ""  # Hint about rewards
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "giver": self.giver,
            "objective": self.objective,
            "reward_hint": self.reward_hint,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Quest":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            status=data.get("status", "active"),
            giver=data.get("giver", ""),
            objective=data.get("objective", ""),
            reward_hint=data.get("reward_hint", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


@dataclass
class QuestLog:
    """Manages the player's quest log."""
    quests: list[Quest] = field(default_factory=list)
    next_id: int = 1  # Next auto-increment ID

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "quests": [q.to_dict() for q in self.quests],
            "next_id": self.next_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QuestLog":
        """Deserialize from dictionary."""
        quest_log = cls()
        quest_log.next_id = data.get("next_id", 1)
        for quest_data in data.get("quests", []):
            quest_log.quests.append(Quest.from_dict(quest_data))
        return quest_log

    def add_quest(
        self,
        title: str,
        description: str,
        giver: str = "",
        objective: str = "",
        reward_hint: str = "",
    ) -> Quest:
        """Add a new quest to the log."""
        now = utcnow().isoformat()
        quest = Quest(
            id=self.next_id,
            title=title,
            description=description,
            giver=giver,
            objective=objective,
            reward_hint=reward_hint,
            created_at=now,
            updated_at=now,
        )
        self.quests.append(quest)
        self.next_id += 1
        return quest

    def update_quest_status(self, quest_id: int, new_status: str) -> Quest | None:
        """Update a quest's status."""
        for quest in self.quests:
            if quest.id == quest_id:
                quest.status = new_status
                quest.updated_at = utcnow().isoformat()
                return quest
        return None

    def get_quest(self, quest_id: int) -> Quest | None:
        """Get a quest by ID."""
        for quest in self.quests:
            if quest.id == quest_id:
                return quest
        return None

    def get_quests_by_status(self, status: str) -> list[Quest]:
        """Get all quests with a specific status."""
        return [q for q in self.quests if q.status == status]

    def find_quest_by_title(self, title: str) -> Quest | None:
        """Find a quest by title (case-insensitive, partial match)."""
        title_lower = title.lower()
        for quest in self.quests:
            if title_lower in quest.title.lower():
                return quest
        return None


def merge_quest_log_into_game_state(
    game_state: dict[str, Any],
    quest_log: QuestLog,
) -> dict[str, Any]:
    """Merge QuestLog data into the game_state dict.

    This ensures backward compatibility while adding new fields.
    """
    game_state["quest_log"] = quest_log.to_dict()
    return game_state


def extract_quest_log_from_game_state(
    game_state: dict[str, Any],
) -> QuestLog:
    """Extract QuestLog from the game_state dict.

    Returns an empty QuestLog if not present (backward compatibility).
    """
    quest_log_data = game_state.get("quest_log", {})
    if not quest_log_data:
        return QuestLog()
    return QuestLog.from_dict(quest_log_data)