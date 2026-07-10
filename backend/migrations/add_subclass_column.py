"""
Migration: Add 'subclass' column to Character table.

Stores subclass choices as a JSON object: ``{"class_name": subclass_id}``,
supporting one subclass per class for multiclassed characters. Nullable with a
default of ``"{}"`` so existing rows are unaffected.

Run this migration to update existing databases:
    uv run python -m migrations.add_subclass_column
"""
import sys
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from app.models.database import engine, SessionLocal


def migrate():
    """Add the 'subclass' column to the Character table."""
    print("Adding 'subclass' column to Character table...")

    with SessionLocal() as db:
        columns = db.execute(text("PRAGMA table_info(characters)")).fetchall()
        column_names = [col[1] for col in columns]

        if "subclass" in column_names:
            print("Column 'subclass' already exists. Skipping migration.")
            return

        db.execute(
            text("ALTER TABLE characters ADD COLUMN subclass TEXT DEFAULT '{}'")
        )
        db.commit()

    print("Migration complete: 'subclass' column added to Character table.")


if __name__ == "__main__":
    migrate()
