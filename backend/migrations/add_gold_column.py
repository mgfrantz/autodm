"""
Migration: Add a gold column to the Character table.

The shop/economy system tracks each character's wealth in gold pieces. A new
column stores this as a non-negative integer:

  - gold (INTEGER DEFAULT 0): current gold pieces the character holds

Run this migration to update existing databases:
    python -m migrations.add_gold_column

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
    """Add the gold column to the Character table."""
    print("Adding gold column to Character table...")

    with SessionLocal() as db:
        tables = [
            row[0]
            for row in db.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        ]
        if "characters" not in tables:
            print("  'characters' table does not exist yet — the model will create it with the column. Nothing to do.")
            return

        columns = db.execute(text("PRAGMA table_info(characters)")).fetchall()
        column_names = [col[1] for col in columns]

        if "gold" in column_names:
            print("  Column 'gold' already exists — nothing to do.")
            return

        db.execute(text("ALTER TABLE characters ADD COLUMN gold INTEGER DEFAULT 0 NOT NULL"))
        db.commit()
        print("  Added 'gold' column (default 0).")


if __name__ == "__main__":
    migrate()
