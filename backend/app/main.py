"""
FastAPI application entry point for the DnD LLM Game.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import characters, combat, combat_actions, game, world, inventory, spells, leveling, navigation, saves, world_state, homebrew, feats, subclasses, rest, saving_throws, skills, encounters, shop, loot, stealth, concentration, attunement, tools, environment, backgrounds, alignment, languages, exhaustion, starvation, mounts, afflictions, traps, social, downtime, images, legendary, tts

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
app.include_router(subclasses.router, prefix="/api/characters/subclasses", tags=["subclasses"])
app.include_router(saving_throws.router, prefix="/api", tags=["saving-throws"])
app.include_router(skills.router, prefix="/api", tags=["skills"])
app.include_router(tools.router, prefix="/api", tags=["tools"])
app.include_router(combat.router, prefix="/api/game", tags=["combat"])
app.include_router(combat_actions.router, prefix="/api/game", tags=["combat-actions"])
app.include_router(game.router, prefix="/api/game", tags=["game"])
app.include_router(rest.router, prefix="/api/game", tags=["rest"])
app.include_router(saves.router, prefix="/api/game", tags=["saves"])
app.include_router(world_state.router, prefix="/api/game", tags=["world_state"])
app.include_router(world.router, prefix="/api/world", tags=["world"])
app.include_router(navigation.router, prefix="/api/navigation", tags=["navigation"])
app.include_router(homebrew.router, prefix="/api/homebrew", tags=["homebrew"])
app.include_router(encounters.router, prefix="/api/encounters", tags=["encounters"])
app.include_router(shop.router, prefix="/api/game", tags=["shop"])
app.include_router(loot.router, prefix="/api/game", tags=["loot"])
app.include_router(stealth.router, prefix="/api/game", tags=["stealth"])
app.include_router(concentration.router, prefix="/api/game", tags=["concentration"])
app.include_router(attunement.router, prefix="/api/game", tags=["attunement"])
app.include_router(environment.router, prefix="/api/game", tags=["environment"])
app.include_router(exhaustion.router, prefix="/api/game", tags=["exhaustion"])
app.include_router(starvation.router, prefix="/api/game", tags=["starvation"])
app.include_router(mounts.router, prefix="/api/game", tags=["mounts"])
app.include_router(backgrounds.router, prefix="/api", tags=["backgrounds"])
app.include_router(alignment.router, prefix="/api", tags=["alignment"])
app.include_router(languages.router, prefix="/api", tags=["languages"])
app.include_router(afflictions.router, prefix="/api", tags=["afflictions"])
app.include_router(traps.router, prefix="/api", tags=["traps"])
app.include_router(social.router, prefix="/api/game", tags=["social"])
app.include_router(downtime.router, prefix="/api/game", tags=["downtime"])
app.include_router(images.router, prefix="/api/game", tags=["images"])
app.include_router(tts.router, prefix="/api/game", tags=["tts"])
app.include_router(legendary.router, prefix="/api/game", tags=["legendary"])
# Character-prefixed language endpoints (/api/characters/{character_id}/languages...)
app.include_router(languages.char_router, prefix="/api", tags=["languages"])
