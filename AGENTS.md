# AGENTS.md — DnD LLM Game

## Project: DnD LLM Game
A browser-based single-player DnD game where an LLM acts as the Dungeon Master.

## Location
`~/dev/dnd-llm-game`

## Design Doc
Read `DESIGN.md` first — it has the full architecture, tech stack, and scope.

## Tech Stack
- **Frontend:** React 18 + Vite + TypeScript + TailwindCSS + Zustand
- **Backend:** Python FastAPI + SQLite
- **LLM:** Provider-agnostic (configure in backend/app/llm/config.py)

## Development Commands
```bash
# Backend — run all commands from the project root
uv sync                          # create the venv and install runtime + dev deps
uv run backend                   # start the FastAPI service on :8000
uv run pytest                    # run the backend tests

# Environment — unified .env at the project root (LLM_* plus HOST/PORT/RELOAD)
# cp .env.example .env

# Frontend
cd frontend && npm install && npm run dev
```

## Build Priorities (in order)
1. ✅ Backend: project scaffold + FastAPI app structure + DB models
2. ✅ Backend: LLM orchestrator + DM prompt system
3. ✅ Backend: World generation pipeline
4. ✅ Backend: Character creation API + game state management
5. ✅ Backend: Combat/dice engine
6. ✅ Frontend: Character creation wizard
7. ✅ Frontend: Game/narration UI
8. ✅ Frontend: Combat tracker
9. ✅ Integration: Full gameplay loop
10. ✅ Frontend: Visual map rendering
11. ✅ Images: AI-generated scene/NPC images (provider-agnostic)
12. 🚧 Audio: Voice narration (TTS DM) — provider-agnostic, mirrors #11
13. ⏳ Future: Multiplayer (party-based)
14. ✅ Future: Advanced rules refinements (subclass system ✅, feat expansion ✅ — 53 feats incl. XGE race-specific)
15. ✅ Infra: DSPy migration complete — all LLM interactions mediated by DSPy (legacy `LLMOrchestrator` deprecated/removed)

## Rules
- Keep the LLM provider configurable — don't hardcode OpenAI or Claude
- All LLM game outputs should be structured (JSON schemas) for world/character data
- DM narration should be free text (streaming)
- Write tests for the game engine (dice, combat math, character stats)
- Commit after each major component works
- Keep `DESIGN.md` updated if architecture changes

## Commit Style
- Clear messages: "feat: add character creation API", "fix: combat initiative ordering"
- Don't push without asking Mike first
