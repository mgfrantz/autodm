"""
Migration: Add the tool_proficiencies column to the Character table.

The tool proficiency system tracks which tools a character is proficient in.
The new column stores a JSON array of tool ids (e.g. ``["thieves_tools", "lute"]``):

  - tool_proficiencies (TEXT, default '[]'): chosen tool ids

Run this migration to update existing databases:
    python -m migrations.add_tool_proficiencies_column

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
    """Add the tool_proficiencies column to the Character table."""
    print("Adding tool_proficiencies column to Character table...")

    new_column = ("tool_proficiencies", "TEXT DEFAULT '[]'")

    with SessionLocal() as db:
        columns = db.execute(text("PRAGMA table_info(characters)")).fetchall()
        column_names = [col[1] for col in columns]

        col_name, col_def = new_column
        if col_name in column_names:
            print(f"Column '{col_name}' already exists. Skipping.")
        else:
            alter_sql = text(
                f"ALTER TABLE characters ADD COLUMN {col_name} {col_def}"
            )
            db.execute(alter_sql)
            print(f"Added column '{col_name}'.")

        db.commit()

    print("Migration complete: tool_proficiencies column added to Character table.")


if __name__ == "__main__":
    migrate()
