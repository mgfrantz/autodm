"""
Migration: Add 'feats' column to Character table.

This migration adds a new 'feats' column to the Character model to store
learned feats as a JSON array. The column is nullable with a default of "[]"
(empty JSON array).

Run this migration to update existing databases:
    python -m migrations.add_feats_column
"""
import sys
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from app.models.database import engine, SessionLocal


def migrate():
    """Add the 'feats' column to the Character table."""
    print("Adding 'feats' column to Character table...")

    # Check if column already exists
    with SessionLocal() as db:
        inspector = text("PRAGMA table_info(characters)")
        columns = db.execute(inspector).fetchall()
        column_names = [col[1] for col in columns]

        if "feats" in column_names:
            print("Column 'feats' already exists. Skipping migration.")
            return

        # Add the column
        alter_sql = text(
            "ALTER TABLE characters ADD COLUMN feats TEXT DEFAULT '[]'"
        )
        db.execute(alter_sql)
        db.commit()

    print("Migration complete: 'feats' column added to Character table.")


def rollback():
    """Remove the 'feats' column from the Character table."""
    print("Rolling back: removing 'feats' column from Character table...")

    with SessionLocal() as db:
        # SQLite doesn't support DROP COLUMN directly, need to recreate table
        # For simplicity in this project, we'll just note this limitation
        print("SQLite doesn't support DROP COLUMN directly.")
        print("To rollback, manually delete the database file and recreate.")
        print("Database location: backend/data/dnd_game.db")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Add feats column migration")
    parser.add_argument("--rollback", action="store_true", help="Rollback the migration")
    args = parser.parse_args()

    if args.rollback:
        rollback()
    else:
        migrate()