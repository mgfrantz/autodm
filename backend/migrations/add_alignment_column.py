"""
Migration: Add an alignment column to the Character table.

The alignment system stores a character's DnD 5e alignment (one of the classic
nine alignments, e.g. "lawful_good") as a short string. It is nullable so
existing characters keep working; the alignment engine treats ``None`` as
True Neutral with no error.

Run this migration to update existing databases:
    python -m migrations.add_alignment_column

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
    """Add the alignment column to the Character table."""
    print("Adding alignment column to Character table...")

    with SessionLocal() as db:
        columns = db.execute(text("PRAGMA table_info(characters)")).fetchall()
        column_names = [col[1] for col in columns]

        if "alignment" in column_names:
            print("Column 'alignment' already exists. Skipping.")
        else:
            db.execute(
                text("ALTER TABLE characters ADD COLUMN alignment TEXT")
            )
            print("Added column 'alignment'.")

        db.commit()

    print("Migration complete: alignment column added to Character table.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Add alignment column migration")
    parser.add_argument("--rollback", action="store_true", help="Rollback the migration")
    args = parser.parse_args()

    if args.rollback:
        print("SQLite doesn't support DROP COLUMN directly.")
        print("To rollback, manually delete the database file and recreate.")
        print("Database location: backend/data/dnd_game.db")
    else:
        migrate()
