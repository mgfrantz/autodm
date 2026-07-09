#!/usr/bin/env python3
"""
Simple migration script to add the 'story_summary' column to existing tables.

Run this from the backend directory after pulling new code.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "dnd_game.db"


def migrate():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}. Skipping migration.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if column already exists in game_saves
    cursor.execute("PRAGMA table_info(game_saves)")
    columns = [col[1] for col in cursor.fetchall()]

    if "story_summary" not in columns:
        print("Adding 'story_summary' column to game_saves table...")
        cursor.execute("ALTER TABLE game_saves ADD COLUMN story_summary TEXT DEFAULT 'null'")
        print("Migration complete!")
    else:
        print("Column 'story_summary' already exists in game_saves table.")

    # Check if column already exists in save_slots
    cursor.execute("PRAGMA table_info(save_slots)")
    columns = [col[1] for col in cursor.fetchall()]

    if "story_summary" not in columns:
        print("Adding 'story_summary' column to save_slots table...")
        cursor.execute("ALTER TABLE save_slots ADD COLUMN story_summary TEXT DEFAULT 'null'")
        print("Migration complete!")
    else:
        print("Column 'story_summary' already exists in save_slots table.")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    migrate()