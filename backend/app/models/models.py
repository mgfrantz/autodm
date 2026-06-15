"""
Database models using SQLAlchemy.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Character(Base):
    """Player character."""
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    race = Column(String(50), nullable=False)
    char_class = Column(String(50), nullable=False)
    level = Column(Integer, default=1)
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

    # Story
    backstory = Column(Text, nullable=True)
    inventory = Column(Text, default="[]")  # JSON array
    spells = Column(Text, default="{}")  # JSON: spellbook data

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    saves = relationship("GameSave", back_populates="character")


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
    saves = relationship("GameSave", back_populates="world")


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

    # Progress
    current_act = Column(Integer, default=1)
    xp = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    character = relationship("Character", back_populates="saves")
    world = relationship("World", back_populates="saves")
