"""
API routers registration.
"""
from fastapi import APIRouter

from app.api import characters, world, game, combat, inventory, spells, leveling, navigation, saves, world_state, homebrew

api_router = APIRouter()

# Register all routers
api_router.include_router(characters.router)
api_router.include_router(world.router)
api_router.include_router(game.router)
api_router.include_router(combat.router)
api_router.include_router(inventory.router)
api_router.include_router(spells.router)
api_router.include_router(leveling.router)
api_router.include_router(navigation.router)
api_router.include_router(saves.router)
api_router.include_router(world_state.router)
api_router.include_router(homebrew.router)