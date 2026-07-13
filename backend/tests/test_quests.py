"""Tests for the quest engine."""
import pytest
from datetime import datetime
from app.engine.quests import (
    Quest,
    QuestLog,
    extract_quest_log_from_game_state,
    merge_quest_log_into_game_state,
)


class TestQuest:
    """Test the Quest dataclass."""

    def test_quest_creation(self):
        """Test creating a quest."""
        quest = Quest(
            id=1,
            title="Retrieve the Lost Amulet",
            description="Find the stolen amulet from the castle ruins.",
            giver="Eldrin the Wise",
            objective="Retrieve the amulet",
            reward_hint="500 gold pieces",
        )
        assert quest.id == 1
        assert quest.title == "Retrieve the Lost Amulet"
        assert quest.status == "active"
        assert quest.giver == "Eldrin the Wise"

    def test_quest_serialization(self):
        """Test quest to_dict and from_dict."""
        quest = Quest(
            id=1,
            title="Rescue the Villagers",
            description="Save the villagers from the goblins.",
            status="active",
            giver="Captain Thorne",
        )
        data = quest.to_dict()
        assert data["id"] == 1
        assert data["title"] == "Rescue the Villagers"
        assert data["status"] == "active"

        restored = Quest.from_dict(data)
        assert restored.id == quest.id
        assert restored.title == quest.title
        assert restored.status == quest.status

    def test_quest_defaults(self):
        """Test quest default values."""
        quest = Quest(
            id=1,
            title="Untitled Quest",
            description="No description",
        )
        assert quest.status == "active"
        assert quest.giver == ""
        assert quest.objective == ""
        assert quest.reward_hint == ""
        assert quest.created_at == ""
        assert quest.updated_at == ""


class TestQuestLog:
    """Test the QuestLog dataclass."""

    def test_quest_log_creation(self):
        """Test creating an empty quest log."""
        log = QuestLog()
        assert log.quests == []
        assert log.next_id == 1

    def test_quest_log_serialization(self):
        """Test quest log to_dict and from_dict."""
        log = QuestLog()
        log.add_quest(
            title="Find the Sword",
            description="Retrieve the ancient sword.",
            giver="Quest Giver",
        )
        log.add_quest(
            title="Defeat the Dragon",
            description="Slay the dragon in its lair.",
            giver="King",
        )

        data = log.to_dict()
        assert len(data["quests"]) == 2
        assert data["next_id"] == 3

        restored = QuestLog.from_dict(data)
        assert len(restored.quests) == 2
        assert restored.next_id == 3
        assert restored.quests[0].title == "Find the Sword"
        assert restored.quests[1].title == "Defeat the Dragon"

    def test_add_quest(self):
        """Test adding a quest to the log."""
        log = QuestLog()
        quest = log.add_quest(
            title="Retrieve the Amulet",
            description="Find the stolen amulet.",
            giver="Eldrin",
            objective="Get the amulet",
            reward_hint="500 gold",
        )
        assert quest.id == 1
        assert quest.title == "Retrieve the Amulet"
        assert len(log.quests) == 1
        assert log.next_id == 2

    def test_add_multiple_quests(self):
        """Test adding multiple quests."""
        log = QuestLog()
        quest1 = log.add_quest(title="Quest 1", description="First quest")
        quest2 = log.add_quest(title="Quest 2", description="Second quest")
        assert quest1.id == 1
        assert quest2.id == 2
        assert len(log.quests) == 2
        assert log.next_id == 3

    def test_update_quest_status(self):
        """Test updating a quest's status."""
        log = QuestLog()
        quest = log.add_quest(title="Test Quest", description="Test")
        assert quest.status == "active"

        updated = log.update_quest_status(quest.id, "completed")
        assert updated is not None
        assert updated.status == "completed"
        assert log.quests[0].status == "completed"

    def test_update_nonexistent_quest(self):
        """Test updating a quest that doesn't exist."""
        log = QuestLog()
        result = log.update_quest_status(999, "completed")
        assert result is None

    def test_get_quest(self):
        """Test getting a quest by ID."""
        log = QuestLog()
        quest = log.add_quest(title="Test Quest", description="Test")
        retrieved = log.get_quest(quest.id)
        assert retrieved is not None
        assert retrieved.id == quest.id
        assert retrieved.title == quest.title

    def test_get_quests_by_status(self):
        """Test filtering quests by status."""
        log = QuestLog()
        q1 = log.add_quest(title="Active Quest", description="Test")
        q2 = log.add_quest(title="Completed Quest", description="Test")
        q3 = log.add_quest(title="Another Active", description="Test")

        log.update_quest_status(q2.id, "completed")
        log.update_quest_status(q3.id, "failed")

        active = log.get_quests_by_status("active")
        completed = log.get_quests_by_status("completed")
        failed = log.get_quests_by_status("failed")

        assert len(active) == 1
        assert len(completed) == 1
        assert len(failed) == 1
        assert active[0].title == "Active Quest"
        assert completed[0].title == "Completed Quest"
        assert failed[0].title == "Another Active"

    def test_find_quest_by_title(self):
        """Test finding a quest by title (case-insensitive partial match)."""
        log = QuestLog()
        quest = log.add_quest(title="Retrieve the Lost Amulet", description="Test")

        # Exact match
        found = log.find_quest_by_title("Retrieve the Lost Amulet")
        assert found is not None
        assert found.id == quest.id

        # Case-insensitive
        found = log.find_quest_by_title("retrieve the lost amulet")
        assert found is not None
        assert found.id == quest.id

        # Partial match
        found = log.find_quest_by_title("lost amulet")
        assert found is not None
        assert found.id == quest.id

        # No match
        found = log.find_quest_by_title("nonexistent quest")
        assert found is None


class TestExtractionMerge:
    """Test extraction and merge helpers for game_state."""

    def test_extract_empty_game_state(self):
        """Test extracting from a game_state with no quest_log."""
        game_state = {"location": "Town", "in_combat": False}
        log = extract_quest_log_from_game_state(game_state)
        assert isinstance(log, QuestLog)
        assert log.quests == []
        assert log.next_id == 1

    def test_extract_with_quest_log(self):
        """Test extracting a quest_log from game_state."""
        log_data = {
            "quests": [
                {
                    "id": 1,
                    "title": "Test Quest",
                    "description": "Test description",
                    "status": "active",
                    "giver": "NPC",
                    "objective": "Test",
                    "reward_hint": "",
                    "created_at": "",
                    "updated_at": "",
                }
            ],
            "next_id": 2,
        }
        game_state = {"location": "Town", "quest_log": log_data}
        log = extract_quest_log_from_game_state(game_state)
        assert len(log.quests) == 1
        assert log.quests[0].title == "Test Quest"
        assert log.next_id == 2

    def test_merge_into_game_state(self):
        """Test merging a QuestLog into game_state."""
        log = QuestLog()
        log.add_quest(title="Test Quest", description="Test")
        game_state = {"location": "Town"}

        merged = merge_quest_log_into_game_state(game_state, log)
        assert "quest_log" in merged
        assert len(merged["quest_log"]["quests"]) == 1
        assert merged["quest_log"]["quests"][0]["title"] == "Test Quest"

    def test_merge_preserves_other_fields(self):
        """Test that merging preserves other game_state fields."""
        log = QuestLog()
        log.add_quest(title="Test Quest", description="Test")
        game_state = {"location": "Town", "in_combat": True, "hp": 10}

        merged = merge_quest_log_into_game_state(game_state, log)
        assert merged["location"] == "Town"
        assert merged["in_combat"] is True
        assert merged["hp"] == 10
        assert "quest_log" in merged

    def test_roundtrip(self):
        """Test that extraction and merge work together."""
        original_log = QuestLog()
        original_log.add_quest(title="Quest 1", description="First")
        original_log.add_quest(title="Quest 2", description="Second")

        game_state = {"location": "Town"}
        game_state = merge_quest_log_into_game_state(game_state, original_log)

        extracted_log = extract_quest_log_from_game_state(game_state)
        assert len(extracted_log.quests) == 2
        assert extracted_log.quests[0].title == "Quest 1"
        assert extracted_log.quests[1].title == "Quest 2"
        assert extracted_log.next_id == original_log.next_id