"""
Database setup and session management.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.models import Base

DATABASE_URL = "sqlite:///./data/dnd_game.db"

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
