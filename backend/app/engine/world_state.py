"""
World State Engine — tracks NPC relationships and faction reputation.
"""
from dataclasses import dataclass, field
from app.utils.time_utils import utcnow
from typing import Any
import json


@dataclass
class NPCRelationship:
    """Tracks the player's relationship with an NPC."""
    npc_name: str
    attitude: str = "neutral"  # hostile, unfriendly, neutral, friendly, devoted
    trust: int = 0  # -100 to 100
    last_interacted: str = ""
    interactions: list[str] = field(default_factory=list)  # Brief summaries

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "npc_name": self.npc_name,
            "attitude": self.attitude,
            "trust": self.trust,
            "last_interacted": self.last_interacted,
            "interactions": self.interactions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NPCRelationship":
        """Deserialize from dictionary."""
        return cls(
            npc_name=data["npc_name"],
            attitude=data.get("attitude", "neutral"),
            trust=data.get("trust", 0),
            last_interacted=data.get("last_interacted", ""),
            interactions=data.get("interactions", []),
        )

    def update_attitude(self, change: int, interaction_summary: str) -> None:
        """Update attitude based on player action.
        
        Args:
            change: Trust change amount (-100 to 100)
            interaction_summary: Brief description of what happened
        """
        self.trust = max(-100, min(100, self.trust + change))
        self.last_interacted = utcnow().isoformat()
        self.interactions.append(interaction_summary)
        
        # Update attitude string based on trust score
        if self.trust <= -75:
            self.attitude = "hostile"
        elif self.trust <= -25:
            self.attitude = "unfriendly"
        elif self.trust <= 25:
            self.attitude = "neutral"
        elif self.trust <= 75:
            self.attitude = "friendly"
        else:
            self.attitude = "devoted"


@dataclass
class FactionReputation:
    """Tracks the player's reputation with a faction."""
    faction_name: str
    standing: str = "neutral"  # hated, hostile, unfriendly, neutral, friendly, honored, revered
    reputation: int = 0  # -100 to 100
    quests_completed: int = 0
    quests_failed: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "faction_name": self.faction_name,
            "standing": self.standing,
            "reputation": self.reputation,
            "quests_completed": self.quests_completed,
            "quests_failed": self.quests_failed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FactionReputation":
        """Deserialize from dictionary."""
        return cls(
            faction_name=data["faction_name"],
            standing=data.get("standing", "neutral"),
            reputation=data.get("reputation", 0),
            quests_completed=data.get("quests_completed", 0),
            quests_failed=data.get("quests_failed", 0),
        )

    def modify_reputation(self, change: int) -> None:
        """Modify reputation based on player actions.
        
        Args:
            change: Reputation change amount (-100 to 100)
        """
        self.reputation = max(-100, min(100, self.reputation + change))
        
        # Update standing based on reputation
        if self.reputation <= -75:
            self.standing = "hated"
        elif self.reputation <= -50:
            self.standing = "hostile"
        elif self.reputation <= -25:
            self.standing = "unfriendly"
        elif self.reputation < 25:
            self.standing = "neutral"
        elif self.reputation < 50:
            self.standing = "friendly"
        elif self.reputation < 75:
            self.standing = "honored"
        else:
            self.standing = "revered"

    def complete_quest(self) -> None:
        """Mark a quest as completed and adjust reputation."""
        self.quests_completed += 1
        self.modify_reputation(10)  # Base reputation gain for completing a quest

    def fail_quest(self) -> None:
        """Mark a quest as failed and adjust reputation."""
        self.quests_failed += 1
        self.modify_reputation(-15)  # Base reputation loss for failing a quest


@dataclass
class WorldState:
    """Manages all world state (NPCs, factions, game flags)."""
    npc_relationships: dict[str, NPCRelationship] = field(default_factory=dict)
    faction_reputation: dict[str, FactionReputation] = field(default_factory=dict)
    story_flags: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "npc_relationships": {
                name: rel.to_dict()
                for name, rel in self.npc_relationships.items()
            },
            "faction_reputation": {
                name: rep.to_dict()
                for name, rep in self.faction_reputation.items()
            },
            "story_flags": dict(self.story_flags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorldState":
        """Deserialize from dictionary."""
        world_state = cls()

        for name, rel_data in data.get("npc_relationships", {}).items():
            world_state.npc_relationships[name] = NPCRelationship.from_dict(rel_data)

        for name, rep_data in data.get("faction_reputation", {}).items():
            world_state.faction_reputation[name] = FactionReputation.from_dict(rep_data)

        # Load story flags, validating they're booleans
        for flag_name, flag_value in data.get("story_flags", {}).items():
            if isinstance(flag_value, bool):
                world_state.story_flags[flag_name] = flag_value

        return world_state

    def get_or_create_npc(self, npc_name: str) -> NPCRelationship:
        """Get an NPC relationship or create a new one."""
        if npc_name not in self.npc_relationships:
            self.npc_relationships[npc_name] = NPCRelationship(npc_name=npc_name)
        return self.npc_relationships[npc_name]

    def get_or_create_faction(self, faction_name: str) -> FactionReputation:
        """Get a faction reputation or create a new one."""
        if faction_name not in self.faction_reputation:
            self.faction_reputation[faction_name] = FactionReputation(faction_name=faction_name)
        return self.faction_reputation[faction_name]

    def update_npc_relationship(
        self,
        npc_name: str,
        trust_change: int,
        interaction_summary: str,
    ) -> NPCRelationship:
        """Update an NPC relationship based on an interaction."""
        npc = self.get_or_create_npc(npc_name)
        npc.update_attitude(trust_change, interaction_summary)
        return npc

    def update_faction_reputation(self, faction_name: str, reputation_change: int) -> FactionReputation:
        """Update faction reputation."""
        faction = self.get_or_create_faction(faction_name)
        faction.modify_reputation(reputation_change)
        return faction

    def complete_faction_quest(self, faction_name: str) -> FactionReputation:
        """Complete a quest for a faction."""
        faction = self.get_or_create_faction(faction_name)
        faction.complete_quest()
        return faction

    def fail_faction_quest(self, faction_name: str) -> FactionReputation:
        """Fail a quest for a faction."""
        faction = self.get_or_create_faction(faction_name)
        faction.fail_quest()
        return faction

    def get_npc_summary_for_context(self) -> str:
        """Generate a summary of notable NPC relationships for DM context."""
        if not self.npc_relationships:
            return "No notable relationships with NPCs yet."
        
        lines = ["Notable NPC Relationships:"]
        for name, rel in self.npc_relationships.items():
            if rel.trust <= -25 or rel.trust >= 25:  # Only notable relationships
                lines.append(f"- {name}: {rel.attitude} (trust: {rel.trust})")
                if rel.interactions:
                    lines.append(f"  Last: {rel.interactions[-1]}")
        
        if len(lines) == 1:
            return "No notable relationships with NPCs yet."
        
        return "\n".join(lines)

    def get_faction_summary_for_context(self) -> str:
        """Generate a summary of faction standings for DM context."""
        if not self.faction_reputation:
            return "No notable faction reputation yet."
        
        lines = ["Faction Reputation:"]
        for name, rep in self.faction_reputation.items():
            if rep.reputation <= -25 or rep.reputation >= 25:  # Only notable standings
                lines.append(f"- {name}: {rep.standing} (reputation: {rep.reputation})")
                lines.append(f"  Quests: {rep.quests_completed} completed, {rep.quests_failed} failed")
        
        if len(lines) == 1:
            return "No notable faction reputation yet."

        return "\n".join(lines)

    def set_flag(self, flag_name: str, value: bool = True) -> None:
        """Set a game flag to a boolean value."""
        self.story_flags[flag_name] = value

    def clear_flag(self, flag_name: str) -> None:
        """Clear a game flag (set to False)."""
        self.story_flags[flag_name] = False

    def get_flag(self, flag_name: str, default: bool = False) -> bool:
        """Get a game flag's value, returning default if not set."""
        # Strip whitespace from flag name
        flag_name = flag_name.strip()
        return self.story_flags.get(flag_name, default)

    def get_flag_summary_for_context(self) -> str:
        """Generate a summary of notable story flags for DM context."""
        if not self.story_flags:
            return "No story flags set yet."

        # Only include True flags (set flags) for context
        active_flags = [name for name, value in self.story_flags.items() if value]

        if not active_flags:
            return "No story flags set yet."

        lines = ["Story Flags (set):"]
        for flag_name in sorted(active_flags):
            lines.append(f"- {flag_name}")

        return "\n".join(lines)


def merge_world_state_into_game_state(
    game_state: dict[str, Any],
    world_state: WorldState,
) -> dict[str, Any]:
    """Merge WorldState data into the game_state dict.
    
    This ensures backward compatibility while adding new fields.
    """
    game_state["world_state"] = world_state.to_dict()
    return game_state


def extract_world_state_from_game_state(
    game_state: dict[str, Any],
) -> WorldState:
    """Extract WorldState from the game_state dict.
    
    Returns an empty WorldState if not present (backward compatibility).
    """
    world_state_data = game_state.get("world_state", {})
    if not world_state_data:
        return WorldState()
    return WorldState.from_dict(world_state_data)