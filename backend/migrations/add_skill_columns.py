"""
Migration: Add skill columns to the Character table.

The skill system tracks which skills a character has chosen proficiency in and
which (Rogue/Bard) have Expertise. Two new columns store JSON arrays:

  - skill_proficiencies (TEXT, default '[]'): chosen skill names
  - skill_expertise     (TEXT, default '[]'): Expertise skill names

Run this migration to update existing databases:
    python -m migrations.add_skill_columns

New databases created from the models already include these columns.
"""
import sys
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from app.models.database import engine, SessionLocal


def migrate():
    """Add the skill columns to the Character table."""
    print("Adding skill columns to Character table...")

    new_columns = [
        ("skill_proficiencies", "TEXT DEFAULT '[]'"),
        ("skill_expertise", "TEXT DEFAULT '[]'"),
    ]

    with SessionLocal() as db:
        columns = db.execute(text("PRAGMA table_info(characters)")).fetchall()
        column_names = [col[1] for col in columns]

        for col_name, col_def in new_columns:
            if col_name in column_names:
                print(f"Column '{col_name}' already exists. Skipping.")
                continue
            alter_sql = text(
                f"ALTER TABLE characters ADD COLUMN {col_name} {col_def}"
            )
            db.execute(alter_sql)
            print(f"Added column '{col_name}'.")

        db.commit()

    print("Migration complete: skill columns added to Character table.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Add skill columns migration")
    parser.add_argument("--rollback", action="store_true", help="Rollback the migration")
    args = parser.parse_args()

    if args.rollback:
        print("SQLite doesn't support DROP COLUMN directly.")
        print("To rollback, manually delete the database file and recreate.")
        print("Database location: backend/data/dnd_game.db")
    else:
        migrate()
