"""
Add languages column to Character table.

Languages are stored as a JSON array of language IDs (e.g., ["common", "elvish", "draconic"]).
"""
from sqlalchemy import text


def upgrade(db):
    """Add the languages column to the Character table."""
    # Check if column exists
    conn = db.connection
    inspector = db.dialect.get_inspector(conn)

    existing_columns = [col['name'] for col in inspector.get_columns('character')]
    if 'languages' not in existing_columns:
        db.execute(text('ALTER TABLE character ADD COLUMN languages TEXT DEFAULT "[]"'))
        db.commit()


def downgrade(db):
    """Remove the languages column from the Character table."""
    conn = db.connection
    inspector = db.dialect.get_inspector(conn)

    existing_columns = [col['name'] for col in inspector.get_columns('character')]
    if 'languages' in existing_columns:
        db.execute(text('ALTER TABLE character DROP COLUMN languages'))
        db.commit()