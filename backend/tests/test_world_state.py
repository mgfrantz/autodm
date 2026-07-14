"""
Tests for world state engine — NPC relationships and faction reputation.
"""
import pytest

from app.engine.world_state import (
    NPCRelationship,
    FactionReputation,
    WorldState,
    merge_world_state_into_game_state,
    extract_world_state_from_game_state,
)


class TestNPCRelationship:
    """Test NPC relationship tracking."""

    def test_npc_relationship_creation(self):
        """Test creating a new NPC relationship."""
        npc = NPCRelationship(npc_name="Gandalf")
        assert npc.npc_name == "Gandalf"
        assert npc.attitude == "neutral"
        assert npc.trust == 0
        assert npc.last_interacted == ""
        assert npc.interactions == []

    def test_npc_attitude_update_positive(self):
        """Test improving NPC relationship."""
        npc = NPCRelationship(npc_name="Gandalf")
        npc.update_attitude(30, "Helped defeat a goblin ambush")
        
        assert npc.trust == 30
        assert npc.attitude == "friendly"
        assert len(npc.interactions) == 1
        assert npc.interactions[0] == "Helped defeat a goblin ambush"
        assert npc.last_interacted

    def test_npc_attitude_update_negative(self):
        """Test worsening NPC relationship."""
        npc = NPCRelationship(npc_name="Gandalf")
        npc.update_attitude(-40, "Stole his staff")
        
        assert npc.trust == -40
        assert npc.attitude == "unfriendly"
        assert len(npc.interactions) == 1

    def test_npc_attitude_extremes(self):
        """Test extreme attitude changes."""
        npc = NPCRelationship(npc_name="Gandalf")
        
        # Devoted
        npc.trust = 100
        npc.update_attitude(0, "")
        assert npc.attitude == "devoted"
        
        # Hostile
        npc.trust = -100
        npc.update_attitude(0, "")
        assert npc.attitude == "hostile"

    def test_npc_trust_bounds(self):
        """Test trust values are bounded between -100 and 100."""
        npc = NPCRelationship(npc_name="Gandalf")
        
        npc.update_attitude(200, "Overly positive")
        assert npc.trust == 100
        
        npc.update_attitude(-300, "Overly negative")
        assert npc.trust == -100

    def test_npc_attitude_thresholds(self):
        """Test attitude thresholds based on trust."""
        npc = NPCRelationship(npc_name="Gandalf")
        
        npc.trust = -75
        npc.update_attitude(0, "")
        assert npc.attitude == "hostile"
        
        npc.trust = -50
        npc.update_attitude(0, "")
        assert npc.attitude == "unfriendly"
        
        npc.trust = 0
        npc.update_attitude(0, "")
        assert npc.attitude == "neutral"
        
        npc.trust = 50
        npc.update_attitude(0, "")
        assert npc.attitude == "friendly"
        
        npc.trust = 80
        npc.update_attitude(0, "")
        assert npc.attitude == "devoted"

    def test_npc_serialization(self):
        """Test NPC relationship serialization."""
        npc = NPCRelationship(
            npc_name="Gandalf",
            attitude="friendly",
            trust=40,
            last_interacted="2024-01-01T00:00:00",
            interactions=["Met in the tavern"],
        )
        
        data = npc.to_dict()
        assert data["npc_name"] == "Gandalf"
        assert data["attitude"] == "friendly"
        assert data["trust"] == 40
        
        npc2 = NPCRelationship.from_dict(data)
        assert npc2.npc_name == npc.npc_name
        assert npc2.attitude == npc.attitude
        assert npc2.trust == npc.trust

    def test_npc_multiple_interactions(self):
        """Test tracking multiple interactions."""
        npc = NPCRelationship(npc_name="Gandalf")
        
        npc.update_attitude(10, "First interaction")
        npc.update_attitude(20, "Second interaction")
        npc.update_attitude(-5, "Third interaction")
        
        assert npc.trust == 25
        assert len(npc.interactions) == 3
        assert npc.interactions[2] == "Third interaction"


class TestFactionReputation:
    """Test faction reputation tracking."""

    def test_faction_creation(self):
        """Test creating a new faction."""
        faction = FactionReputation(faction_name="Mages Guild")
        assert faction.faction_name == "Mages Guild"
        assert faction.standing == "neutral"
        assert faction.reputation == 0
        assert faction.quests_completed == 0
        assert faction.quests_failed == 0

    def test_faction_reputation_modify(self):
        """Test modifying faction reputation."""
        faction = FactionReputation(faction_name="Mages Guild")
        faction.modify_reputation(25)
        
        assert faction.reputation == 25
        assert faction.standing == "friendly"

    def test_faction_reputation_bounds(self):
        """Test reputation bounds."""
        faction = FactionReputation(faction_name="Mages Guild")
        
        faction.modify_reputation(200)
        assert faction.reputation == 100
        
        faction.modify_reputation(-300)
        assert faction.reputation == -100

    def test_faction_standing_thresholds(self):
        """Test standing thresholds based on reputation."""
        faction = FactionReputation(faction_name="Mages Guild")
        
        faction.reputation = -75
        faction.modify_reputation(0)
        assert faction.standing == "hated"
        
        faction.reputation = -50
        faction.modify_reputation(0)
        assert faction.standing == "hostile"
        
        faction.reputation = -25
        faction.modify_reputation(0)
        assert faction.standing == "unfriendly"
        
        faction.reputation = 0
        faction.modify_reputation(0)
        assert faction.standing == "neutral"
        
        faction.reputation = 30
        faction.modify_reputation(0)
        assert faction.standing == "friendly"
        
        faction.reputation = 60
        faction.modify_reputation(0)
        assert faction.standing == "honored"
        
        faction.reputation = 90
        faction.modify_reputation(0)
        assert faction.standing == "revered"

    def test_faction_quest_completion(self):
        """Test quest completion tracking."""
        faction = FactionReputation(faction_name="Mages Guild")
        faction.complete_quest()
        
        assert faction.quests_completed == 1
        assert faction.reputation == 10

    def test_faction_quest_failure(self):
        """Test quest failure tracking."""
        faction = FactionReputation(faction_name="Mages Guild")
        faction.fail_quest()
        
        assert faction.quests_failed == 1
        assert faction.reputation == -15

    def test_faction_serialization(self):
        """Test faction serialization."""
        faction = FactionReputation(
            faction_name="Mages Guild",
            standing="honored",
            reputation=60,
            quests_completed=5,
            quests_failed=1,
        )
        
        data = faction.to_dict()
        assert data["faction_name"] == "Mages Guild"
        assert data["standing"] == "honored"
        assert data["reputation"] == 60
        assert data["quests_completed"] == 5
        
        faction2 = FactionReputation.from_dict(data)
        assert faction2.faction_name == faction.faction_name
        assert faction2.standing == faction.standing
        assert faction2.reputation == faction.reputation


class TestWorldState:
    """Test world state management."""

    def test_world_state_creation(self):
        """Test creating a new world state."""
        world_state = WorldState()
        assert len(world_state.npc_relationships) == 0
        assert len(world_state.faction_reputation) == 0

    def test_get_or_create_npc(self):
        """Test getting or creating NPCs."""
        world_state = WorldState()
        
        npc1 = world_state.get_or_create_npc("Gandalf")
        assert npc1.npc_name == "Gandalf"
        assert len(world_state.npc_relationships) == 1
        
        npc2 = world_state.get_or_create_npc("Gandalf")
        assert npc1 is npc2  # Same object
        assert len(world_state.npc_relationships) == 1

    def test_get_or_create_faction(self):
        """Test getting or creating factions."""
        world_state = WorldState()
        
        faction1 = world_state.get_or_create_faction("Mages Guild")
        assert faction1.faction_name == "Mages Guild"
        assert len(world_state.faction_reputation) == 1
        
        faction2 = world_state.get_or_create_faction("Mages Guild")
        assert faction1 is faction2
        assert len(world_state.faction_reputation) == 1

    def test_update_npc_relationship(self):
        """Test updating NPC relationships."""
        world_state = WorldState()
        
        npc = world_state.update_npc_relationship(
            "Gandalf",
            trust_change=30,
            interaction_summary="Helped him",
        )
        
        assert npc.trust == 30
        assert npc.attitude == "friendly"
        assert "Gandalf" in world_state.npc_relationships

    def test_update_faction_reputation(self):
        """Test updating faction reputation."""
        world_state = WorldState()
        
        faction = world_state.update_faction_reputation("Mages Guild", 25)
        
        assert faction.reputation == 25
        assert faction.standing == "friendly"
        assert "Mages Guild" in world_state.faction_reputation

    def test_complete_faction_quest(self):
        """Test completing faction quests."""
        world_state = WorldState()
        
        faction = world_state.complete_faction_quest("Mages Guild")
        
        assert faction.quests_completed == 1
        assert faction.reputation == 10

    def test_fail_faction_quest(self):
        """Test failing faction quests."""
        world_state = WorldState()
        
        faction = world_state.fail_faction_quest("Mages Guild")
        
        assert faction.quests_failed == 1
        assert faction.reputation == -15

    def test_world_state_serialization(self):
        """Test world state serialization."""
        world_state = WorldState()
        world_state.update_npc_relationship("Gandalf", 30, "Helped")
        world_state.update_faction_reputation("Mages Guild", 25)
        
        data = world_state.to_dict()
        assert "npc_relationships" in data
        assert "faction_reputation" in data
        assert "Gandalf" in data["npc_relationships"]
        assert "Mages Guild" in data["faction_reputation"]
        
        world_state2 = WorldState.from_dict(data)
        assert len(world_state2.npc_relationships) == 1
        assert len(world_state2.faction_reputation) == 1
        assert world_state2.npc_relationships["Gandalf"].trust == 30
        assert world_state2.faction_reputation["Mages Guild"].reputation == 25

    def test_get_npc_summary_for_context(self):
        """Test generating NPC context summary."""
        world_state = WorldState()
        
        # Empty state
        summary = world_state.get_npc_summary_for_context()
        assert "no notable" in summary.lower()
        
        # With notable relationships
        world_state.update_npc_relationship("Gandalf", 40, "Helped")
        world_state.update_npc_relationship("Saruman", -30, "Betrayed")
        world_state.update_npc_relationship("Random Villager", 5, "Said hi")
        
        summary = world_state.get_npc_summary_for_context()
        assert "Gandalf" in summary
        assert "Saruman" in summary
        assert "Random Villager" not in summary  # Not notable enough

    def test_get_faction_summary_for_context(self):
        """Test generating faction context summary."""
        world_state = WorldState()
        
        # Empty state
        summary = world_state.get_faction_summary_for_context()
        assert "no notable" in summary.lower()
        
        # With notable standings
        world_state.update_faction_reputation("Mages Guild", 50)
        world_state.update_faction_reputation("Thieves Guild", -40)
        world_state.update_faction_reputation("Farmers Collective", 10)
        
        summary = world_state.get_faction_summary_for_context()
        assert "Mages Guild" in summary
        assert "Thieves Guild" in summary
        assert "Farmers Collective" not in summary  # Not notable enough


class TestGameStateIntegration:
    """Test integration with game_state dict."""

    def test_merge_world_state_into_game_state(self):
        """Test merging WorldState into game_state dict."""
        world_state = WorldState()
        world_state.update_npc_relationship("Gandalf", 30, "Helped")
        
        game_state = {"location": "Shire", "in_combat": False}
        result = merge_world_state_into_game_state(game_state, world_state)
        
        assert result["location"] == "Shire"
        assert result["in_combat"] is False
        assert "world_state" in result
        assert "Gandalf" in result["world_state"]["npc_relationships"]

    def test_extract_world_state_from_game_state(self):
        """Test extracting WorldState from game_state dict."""
        game_state = {
            "location": "Shire",
            "world_state": {
                "npc_relationships": {
                    "Gandalf": {
                        "npc_name": "Gandalf",
                        "attitude": "friendly",
                        "trust": 30,
                        "last_interacted": "",
                        "interactions": [],
                    }
                },
                "faction_reputation": {},
            },
        }
        
        world_state = extract_world_state_from_game_state(game_state)
        assert len(world_state.npc_relationships) == 1
        assert world_state.npc_relationships["Gandalf"].trust == 30

    def test_extract_world_state_empty(self):
        """Test extracting WorldState when not present (backward compatibility)."""
        game_state = {"location": "Shire"}
        
        world_state = extract_world_state_from_game_state(game_state)
        assert isinstance(world_state, WorldState)
        assert len(world_state.npc_relationships) == 0

    def test_round_trip_world_state(self):
        """Test WorldState survives round-trip through game_state."""
        original = WorldState()
        original.update_npc_relationship("Gandalf", 30, "Helped")
        original.update_faction_reputation("Mages Guild", 25)

        game_state = {"location": "Shire"}
        game_state = merge_world_state_into_game_state(game_state, original)
        extracted = extract_world_state_from_game_state(game_state)

        assert len(extracted.npc_relationships) == 1
        assert extracted.npc_relationships["Gandalf"].trust == 30
        assert len(extracted.faction_reputation) == 1
        assert extracted.faction_reputation["Mages Guild"].reputation == 25


class TestGameFlags:
    """Test game flags for branching narrative state."""

    def test_set_flag(self):
        """Test setting a game flag."""
        world_state = WorldState()
        world_state.set_flag("met_king", True)

        assert world_state.get_flag("met_king") is True
        assert len(world_state.story_flags) == 1

    def test_clear_flag(self):
        """Test clearing a game flag."""
        world_state = WorldState()
        world_state.set_flag("met_king", True)
        assert world_state.get_flag("met_king") is True

        world_state.clear_flag("met_king")
        assert world_state.get_flag("met_king") is False

    def test_get_flag_default(self):
        """Test getting a flag that doesn't exist returns default."""
        world_state = WorldState()

        assert world_state.get_flag("nonexistent_flag") is False
        assert world_state.get_flag("nonexistent_flag", default=True) is True

    def test_set_multiple_flags(self):
        """Test setting multiple flags."""
        world_state = WorldState()
        world_state.set_flag("met_king")
        world_state.set_flag("saved_village")
        world_state.set_flag("found_secret_passage")

        assert world_state.get_flag("met_king") is True
        assert world_state.get_flag("saved_village") is True
        assert world_state.get_flag("found_secret_passage") is True
        assert len(world_state.story_flags) == 3

    def test_set_flag_false(self):
        """Test setting a flag to False explicitly."""
        world_state = WorldState()
        world_state.set_flag("met_king", False)

        assert world_state.get_flag("met_king") is False
        # The flag is still tracked even when False
        assert "met_king" in world_state.story_flags

    def test_update_existing_flag(self):
        """Test updating an existing flag."""
        world_state = WorldState()
        world_state.set_flag("met_king", True)
        world_state.set_flag("met_king", False)

        assert world_state.get_flag("met_king") is False

    def test_flag_serialization(self):
        """Test flag serialization round-trip."""
        world_state = WorldState()
        world_state.set_flag("met_king")
        world_state.set_flag("saved_village")
        world_state.set_flag("village_destroyed", False)

        data = world_state.to_dict()
        assert "story_flags" in data
        assert data["story_flags"]["met_king"] is True
        assert data["story_flags"]["saved_village"] is True
        assert data["story_flags"]["village_destroyed"] is False

        world_state2 = WorldState.from_dict(data)
        assert world_state2.get_flag("met_king") is True
        assert world_state2.get_flag("saved_village") is True
        assert world_state2.get_flag("village_destroyed") is False

    def test_flag_serialization_filters_non_booleans(self):
        """Test that from_dict filters out non-boolean flag values."""
        world_state = WorldState()
        # Manually corrupt data
        world_state.story_flags["valid_flag"] = True
        world_state.story_flags["invalid_flag"] = "not_a_boolean"
        world_state.story_flags["another_invalid"] = 42

        data = world_state.to_dict()

        # from_dict should only load valid booleans
        world_state2 = WorldState.from_dict(data)
        assert world_state2.get_flag("valid_flag") is True
        assert world_state2.get_flag("invalid_flag") is False  # Filtered out
        assert world_state2.get_flag("another_invalid") is False  # Filtered out

    def test_get_flag_summary_for_context_empty(self):
        """Test flag summary when no flags are set."""
        world_state = WorldState()
        summary = world_state.get_flag_summary_for_context()
        assert "no story flags set yet" in summary.lower()

    def test_get_flag_summary_for_context_with_flags(self):
        """Test flag summary when flags are set."""
        world_state = WorldState()
        world_state.set_flag("met_king")
        world_state.set_flag("saved_village")
        world_state.set_flag("village_destroyed", False)

        summary = world_state.get_flag_summary_for_context()
        assert "Story Flags (set):" in summary
        assert "met_king" in summary
        assert "saved_village" in summary
        # False flags should not appear in the summary
        assert "village_destroyed" not in summary

    def test_world_state_includes_flags(self):
        """Test WorldState includes flags in to_dict."""
        world_state = WorldState()
        world_state.set_flag("met_king")
        world_state.update_npc_relationship("Gandalf", 30, "Helped")

        data = world_state.to_dict()
        assert "story_flags" in data
        assert data["story_flags"]["met_king"] is True
        assert "npc_relationships" in data

    def test_merge_flags_into_game_state(self):
        """Test merging flags into game_state."""
        world_state = WorldState()
        world_state.set_flag("met_king")

        game_state = {"location": "Castle"}
        result = merge_world_state_into_game_state(game_state, world_state)

        assert result["location"] == "Castle"
        assert "world_state" in result
        assert result["world_state"]["story_flags"]["met_king"] is True

    def test_extract_flags_from_game_state(self):
        """Test extracting flags from game_state."""
        game_state = {
            "location": "Castle",
            "world_state": {
                "npc_relationships": {},
                "faction_reputation": {},
                "story_flags": {
                    "met_king": True,
                    "saved_village": False,
                },
            },
        }

        world_state = extract_world_state_from_game_state(game_state)
        assert world_state.get_flag("met_king") is True
        assert world_state.get_flag("saved_village") is False

    def test_extract_flags_empty_game_state(self):
        """Test extracting flags when world_state is empty."""
        game_state = {"location": "Castle"}
        world_state = extract_world_state_from_game_state(game_state)

        assert isinstance(world_state, WorldState)
        assert len(world_state.story_flags) == 0

    def test_round_trip_flags_through_game_state(self):
        """Test flags survive round-trip through game_state."""
        original = WorldState()
        original.set_flag("met_king")
        original.set_flag("saved_village")
        original.update_npc_relationship("Gandalf", 30, "Helped")

        game_state = {"location": "Shire"}
        game_state = merge_world_state_into_game_state(game_state, original)
        extracted = extract_world_state_from_game_state(game_state)

        assert extracted.get_flag("met_king") is True
        assert extracted.get_flag("saved_village") is True
        assert extracted.npc_relationships["Gandalf"].trust == 30