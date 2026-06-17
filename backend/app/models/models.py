"""
Database models using SQLAlchemy.
"""
import json
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

# Valid item types
class ItemType:
    WEAPON = "weapon"
    ARMOR = "armor"
    POTION = "potion"
    SCROLL = "scroll"
    MISC = "misc"
    QUEST = "quest"

    @classmethod
    def all(cls):
        return [cls.WEAPON, cls.ARMOR, cls.POTION, cls.SCROLL, cls.MISC, cls.QUEST]

# Valid rarities
class Rarity:
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    VERY_RARE = "very_rare"
    LEGENDARY = "legendary"

    @classmethod
    def all(cls):
        return [cls.COMMON, cls.UNCOMMON, cls.RARE, cls.VERY_RARE, cls.LEGENDARY]


class Character(Base):
    """Player character."""
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    race = Column(String(50), nullable=False)
    char_class = Column(String(50), nullable=False)  # Kept for backward compatibility
    level = Column(Integer, default=1)  # Total level (sum of all class levels)
    classes = Column(Text, default="{}")  # JSON: {"class_name": level, ...}
    background = Column(String(100), nullable=True)

    # Ability scores
    strength = Column(Integer, default=10)
    dexterity = Column(Integer, default=10)
    constitution = Column(Integer, default=10)
    intelligence = Column(Integer, default=10)
    wisdom = Column(Integer, default=10)
    charisma = Column(Integer, default=10)

    # Combat stats
    max_hp = Column(Integer, default=10)
    current_hp = Column(Integer, default=10)
    armor_class = Column(Integer, default=10)
    speed = Column(Integer, default=30)

    # Progression
    xp = Column(Integer, default=0)
    asi_used = Column(Integer, default=0)  # Ability Score Improvement instances spent
    feats = Column(Text, default="[]")  # JSON array of learned feat dicts
    hit_dice_used = Column(Integer, default=0)  # Hit Dice spent since last long rest

    # Skills
    skill_proficiencies = Column(Text, default="[]")  # JSON array of chosen skill names
    skill_expertise = Column(Text, default="[]")  # JSON array of Expertise skill names

    # Story
    backstory = Column(Text, nullable=True)
    inventory = Column(Text, default="[]")  # JSON array
    spells = Column(Text, default="{}")  # JSON: spellbook data

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    saves = relationship("GameSave", back_populates="character")

    @property
    def primary_class(self) -> str:
        """Get the class with the highest level (for display/UI)."""
        try:
            classes_dict = json.loads(self.classes or "{}")
            if not classes_dict:
                return (self.char_class or "commoner").lower()
            return max(classes_dict.items(), key=lambda x: x[1])[0].lower()
        except (json.JSONDecodeError, ValueError):
            return (self.char_class or "commoner").lower()

    @property
    def classes_dict(self) -> dict[str, int]:
        """Get classes as a dictionary."""
        try:
            classes_dict = json.loads(self.classes or "{}")
            if not classes_dict:
                # Backward compatibility
                return {self.char_class.lower(): self.level or 1}
            return classes_dict
        except (json.JSONDecodeError, ValueError):
            return {self.char_class.lower(): self.level or 1}


class World(Base):
    """Generated world/campaign."""
    __tablename__ = "worlds"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    world_data = Column(Text, nullable=False)  # Full JSON: regions, NPCs, quests, factions
    tone = Column(String(50), default="heroic fantasy")

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    world_saves = relationship("GameSave", back_populates="world")


class GameSave(Base):
    """A saved game — links a character to a world with current state."""
    __tablename__ = "game_saves"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)

    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False)
    world_id = Column(Integer, ForeignKey("worlds.id"), nullable=False)

    # Dynamic game state (location, quest progress, story log, etc.)
    game_state = Column(Text, default="{}")  # JSON
    story_log = Column(Text, default="[]")  # JSON array of narration entries
    story_summary = Column(Text, default="null")  # JSON: StorySummary for context management

    # Progress
    current_act = Column(Integer, default=1)
    xp = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    character = relationship("Character", back_populates="saves")
    world = relationship("World", back_populates="world_saves")
    save_slots = relationship(
        "SaveSlot",
        back_populates="game_save",
        cascade="all, delete-orphan",
        order_by="SaveSlot.created_at.desc()",
    )


class SaveSlot(Base):
    """A named save snapshot — frozen point-in-time copy of mutable game state."""
    __tablename__ = "save_slots"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    game_save_id = Column(Integer, ForeignKey("game_saves.id"), nullable=False)

    # Frozen snapshot of mutable game state (for restoration)
    character_snapshot = Column(Text, nullable=False)  # JSON: Character mutable fields
    game_state = Column(Text, default="{}")  # JSON
    story_log = Column(Text, default="[]")  # JSON array
    story_summary = Column(Text, default="null")  # JSON
    current_act = Column(Integer, default=1)

    created_at = Column(DateTime, default=datetime.utcnow)

    game_save = relationship("GameSave", back_populates="save_slots")


class HomebrewItem(Base):
    """Custom/homebrew items created by players."""
    __tablename__ = "homebrew_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    item_type = Column(String(20), nullable=False)  # weapon, armor, potion, scroll, misc, quest
    description = Column(Text, nullable=True)
    rarity = Column(String(20), default="common")  # common, uncommon, rare, very_rare, legendary

    # Item stats (JSON for flexibility)
    stats = Column(Text, nullable=False)  # JSON: all item fields from Item dataclass

    # Metadata
    creator_name = Column(String(100), nullable=True)  # Optional: player who created it
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        """Convert to dictionary for API responses."""
        import json
        from app.engine.inventory import Item, ItemType, Rarity

        stats_data = json.loads(self.stats)
        stats_data["id"] = f"homebrew_{self.id}"  # Unique ID prefix
        stats_data["name"] = self.name
        stats_data["item_type"] = ItemType(self.item_type)
        stats_data["rarity"] = Rarity(self.rarity)

        return {
            "id": self.id,
            "name": self.name,
            "item_type": self.item_type,
            "description": self.description,
            "rarity": self.rarity,
            "stats": stats_data,
            "creator_name": self.creator_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_item_dict(cls, item_dict: dict, creator_name: str = None):
        """Create HomebrewItem from Item dictionary."""
        import json
        from app.engine.inventory import Item

        # Remove fields that shouldn't be in stats
        stats_data = {
            "id": "",  # Will be generated by Item
            "name": item_dict["name"],
            "item_type": item_dict["item_type"],
            "description": item_dict.get("description", ""),
            "rarity": item_dict.get("rarity", "common"),
            "value": item_dict.get("value", 0),
            "weight": item_dict.get("weight", 1.0),
            "damage_dice_count": item_dict.get("damage_dice_count", 0),
            "damage_dice_sides": item_dict.get("damage_dice_sides", 0),
            "damage_bonus": item_dict.get("damage_bonus", 0),
            "damage_type": item_dict.get("damage_type", ""),
            "attack_bonus": item_dict.get("attack_bonus", 0),
            "armor_type": item_dict.get("armor_type"),
            "armor_bonus": item_dict.get("armor_bonus", 0),
            "dex_limit": item_dict.get("dex_limit"),
            "uses": item_dict.get("uses", 1),
            "max_uses": item_dict.get("max_uses", 1),
            "quantity": item_dict.get("quantity", 1),
        }

        # Handle enum conversions for storage
        item_type_str = item_dict["item_type"].value if hasattr(item_dict["item_type"], "value") else item_dict["item_type"]
        rarity_value = item_dict.get("rarity", "common")
        rarity_str = rarity_value.value if hasattr(rarity_value, "value") else rarity_value

        return cls(
            name=item_dict["name"],
            item_type=item_type_str,
            description=item_dict.get("description", ""),
            rarity=rarity_str,
            stats=json.dumps(stats_data),
            creator_name=creator_name or "Anonymous",
        )