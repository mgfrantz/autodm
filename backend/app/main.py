"""
FastAPI application entry point for the DnD LLM Game.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import characters, combat, game, world, inventory, spells, leveling, navigation, saves, world_state, homebrew, feats, rest

app = FastAPI(
    title="DnD LLM Game",
    description="A browser-based DnD game powered by an LLM Dungeon Master.",
    version="0.1.0",
)

# CORS — allow the Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "ok", "game": "DnD LLM Game", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


# Register routers
app.include_router(characters.router, prefix="/api/characters", tags=["characters"])
app.include_router(inventory.router, prefix="/api/characters", tags=["inventory"])
app.include_router(spells.router, prefix="/api/characters", tags=["spells"])
app.include_router(leveling.router, prefix="/api/characters", tags=["leveling"])
app.include_router(feats.router, prefix="/api/characters/feats", tags=["feats"])
app.include_router(combat.router, prefix="/api/game", tags=["combat"])
app.include_router(game.router, prefix="/api/game", tags=["game"])
app.include_router(rest.router, prefix="/api/game", tags=["rest"])
app.include_router(saves.router, prefix="/api/game", tags=["saves"])
app.include_router(world_state.router, prefix="/api/game", tags=["world_state"])
app.include_router(world.router, prefix="/api/world", tags=["world"])
app.include_router(navigation.router, prefix="/api/navigation", tags=["navigation"])
app.include_router(homebrew.router, prefix="/api/homebrew", tags=["homebrew"])
