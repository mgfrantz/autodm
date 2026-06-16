#!/usr/bin/env python3
"""
Migration: Add homebrew_items table for custom items.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.models.database import engine, Base
from app.models.models import HomebrewItem


def migrate():
    """Create the homebrew_items table."""
    print("Creating homebrew_items table...")
    HomebrewItem.__table__.create(engine, checkfirst=True)
    print("✅ Migration complete: homebrew_items table created")


if __name__ == "__main__":
    migrate()