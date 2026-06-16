"""
Migration: Add 'hit_dice_used' column to Character table.

The rest system (short/long rests) tracks how many Hit Dice a character has
spent since their last long rest. The column is an integer defaulting to 0.

Run this migration to update existing databases:
    python -m migrations.add_hit_dice_column
"""
import sys
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from app.models.database import engine, SessionLocal


def migrate():
    """Add the 'hit_dice_used' column to the Character table."""
    print("Adding 'hit_dice_used' column to Character table...")

    with SessionLocal() as db:
        columns = db.execute(text("PRAGMA table_info(characters)")).fetchall()
        column_names = [col[1] for col in columns]

        if "hit_dice_used" in column_names:
            print("Column 'hit_dice_used' already exists. Skipping migration.")
            return

        alter_sql = text(
            "ALTER TABLE characters ADD COLUMN hit_dice_used INTEGER DEFAULT 0"
        )
        db.execute(alter_sql)
        db.commit()

    print("Migration complete: 'hit_dice_used' column added to Character table.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Add hit_dice_used column migration")
    parser.add_argument("--rollback", action="store_true", help="Rollback the migration")
    args = parser.parse_args()

    if args.rollback:
        print("SQLite doesn't support DROP COLUMN directly.")
        print("To rollback, manually delete the database file and recreate.")
        print("Database location: backend/data/dnd_game.db")
    else:
        migrate()
