"""
Startup script — initializes the database and runs the server.
"""
import os
from dotenv import load_dotenv

load_dotenv()

from app.models.database import init_db

init_db()
print("Database initialized.")

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
