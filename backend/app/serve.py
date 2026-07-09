"""Console-script entry point — `uv run backend`.

Loads the unified .env, initializes the DB, and serves the FastAPI app.
Replaces the old backend/run.py launcher.
"""
import os

from dotenv import load_dotenv


def main() -> None:
    # Load the unified .env from the project root (searched upward from CWD)
    # BEFORE importing app modules that read environment variables at import.
    load_dotenv()

    from app.models.database import init_db

    init_db()
    print("Database initialized.")

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "true").lower() == "true",
    )


if __name__ == "__main__":
    main()
