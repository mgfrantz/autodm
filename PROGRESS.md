# PROGRESS.md — DnD LLM Game Development Tracker

## Status: MVP SCAFFOLD COMPLETE ✅ VERIFIED ✅ STREAMING ✅ COMBAT ENGINE ✅

## Completed
- [x] Project structure created (backend + frontend)
- [x] DESIGN.md with full architecture
- [x] AGENTS.md with build priorities
- [x] Backend: FastAPI app structure
- [x] Backend: SQLAlchemy models (Character, World, GameSave)
- [x] Backend: Database setup + session management
- [x] Backend: Dice engine (d20, advantage/disadvantage, ability mods)
- [x] Backend: LLM orchestrator (provider-agnostic)
- [x] Backend: DM prompt templates
- [x] Backend: Character API (create, list, get, delete)
- [x] Backend: World API (LLM generation, list, detail)
- [x] Backend: Game API (create, start, action, state, list)
- [x] Frontend: Vite + React + TypeScript + TailwindCSS
- [x] Frontend: Types and API client
- [x] Frontend: Zustand game store
- [x] Frontend: Home view (character/game lists)
- [x] Frontend: Character creation wizard (3-step: identity, abilities, story)
- [x] Frontend: World generation view (tone selection)
- [x] Frontend: Game view (DM narration, action input, character sidebar)
- [x] Dependencies installed (backend pip, frontend npm)
- [x] Initial git commit
- [x] **Verify backend boots** — fixed lazy LLM initialization
- [x] **Verify frontend compiles** — fixed unused TypeScript imports
- [x] **Fix any import/type errors** — all resolved
- [x] **Write tests** for dice engine — 35 tests, all passing
- [x] **Write tests** for character creation — 26 tests, all passing
- [x] **Add LLM streaming** — stream DM narration to frontend for real-time feel
  - Backend: `stream_narration` generator + SSE endpoints (`/start/stream`, `/action/stream`)
  - Frontend: SSE client + live typing-cursor DM bubble in GameView
  - 7 streaming tests passing (68 total)
- [x] **Add combat engine** — initiative tracker, turn order, enemy stats
  - `Combatant` (HP/damage/conditions/enemy stats), `Attack` (crit doubling)
  - `Encounter` (initiative roll, deterministic turn order, round cycling,
    active/winner detection, `resolve_attack` d20-vs-AC with nat1/nat20)
  - JSON serialization for persistence; 27 combat tests (95 total)

## Next Priorities
|- [x] **Combat API integration** — expose combat engine via REST endpoints (start encounter, take turn, attack) + frontend combat tracker UI
- [ ] **Add inventory management** — items, equipment, loot
- [ ] **Add spell system** — spell slots, known spells per class
- [ ] **Add XP/leveling** — automatic level-up, stat increases
- [ ] **Add map/region navigation** — visual region explorer
- [ ] **Add save/load** — proper game persistence
- [ ] **Frontend polish** — animations, transitions, responsive design
- [ ] **Context window management** — smart summarization of story log
- [ ] **World state persistence** — NPC relationship tracking, faction reputation

## How to Use This File
When you (the agent) work on the project:
1. Read this file first
2. Pick the top unchecked item from "Next Priorities"
3. Implement it
4. Test it
5. Move it to "Completed" and commit
6. Report what you did
