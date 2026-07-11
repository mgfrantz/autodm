"""
Migration: Add a personality column to the Character table.

The personality system stores a DnD 5e-standard personality profile
(generated via DSPy) as JSON: ``{"traits": [str, str], "ideal": str,
"bond": str, "flaw": str}``. It defaults to an empty JSON object so
existing characters keep working; the model properties treat ``{}`` as
no personality set with no error.

Run this migration to update existing databases:
    python -m migrations.add_personality_column

New databases created from the models already include this column.
"""
import sys
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from app.models.database import engine, SessionLocal


def migrate():
    """Add the personality column to the Character table."""
    print("Adding personality column to Character table...")

    with SessionLocal() as db:
        columns = db.execute(text("PRAGMA table_info(characters)")).fetchall()
        column_names = [col[1] for col in columns]

        if "personality" in column_names:
            print("Column 'personality' already exists. Skipping.")
        else:
            db.execute(
                text("ALTER TABLE characters ADD COLUMN personality TEXT DEFAULT '{}'")
            )
            print("Added column 'personality'.")

        db.commit()

    print("Migration complete: personality column added to Character table.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Add personality column migration")
    parser.add_argument("--rollback", action="store_true", help="Rollback the migration")
    args = parser.parse_args()

    if args.rollback:
        print("SQLite doesn't support DROP COLUMN directly.")
        print("To rollback, manually delete the database file and recreate.")
        print("Database location: backend/data/dnd_game.db")
    else:
        migrate()
