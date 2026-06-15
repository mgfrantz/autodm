#!/usr/bin/env python3
"""
Simple migration script to add the 'spells' column to existing Character tables.

Run this from the backend directory after pulling new code.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "dnd_game.db"


def migrate():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}. Skipping migration.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if column already exists
    cursor.execute("PRAGMA table_info(characters)")
    columns = [col[1] for col in cursor.fetchall()]

    if "spells" in columns:
        print("Column 'spells' already exists in characters table.")
        conn.close()
        return

    # Add the column
    print("Adding 'spells' column to characters table...")
    cursor.execute("ALTER TABLE characters ADD COLUMN spells TEXT DEFAULT '{}'")
    conn.commit()
    print("Migration complete!")

    conn.close()


if __name__ == "__main__":
    migrate()