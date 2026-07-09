"""
Database setup and session management.
"""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.models import Base

# Default to backend/data/dnd_game.db, resolved from this file so the location
# is independent of the process working directory. Override via DATABASE_URL.
_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "dnd_game.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_DEFAULT_DB_PATH}")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency for DB sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_factory():
    """FastAPI dependency returning the session factory (a callable).

    Used for routes that need to open their own sessions across request
    lifetimes — notably streaming endpoints where the DB write happens inside
    an async generator after the response has started. Returns
    ``SessionLocal`` by default; tests override this to point at the test DB.
    """
    return SessionLocal
