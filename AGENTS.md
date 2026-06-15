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
# Backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

## Build Priorities (in order)
1. Backend: project scaffold + FastAPI app structure + DB models
2. Backend: LLM orchestrator + DM prompt system
3. Backend: World generation pipeline
4. Backend: Character creation API + game state management
5. Backend: Combat/dice engine
6. Frontend: Character creation wizard
7. Frontend: Game/narration UI
8. Frontend: Combat tracker
9. Integration: Full gameplay loop

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
