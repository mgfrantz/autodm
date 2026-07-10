# DnD LLM Game — Design Document

## Vision

A browser-based single-player DnD game where an LLM acts as the Dungeon Master. The LLM generates complete worlds, campaigns, and encounters, then guides the player through them with dynamic narration, combat, and decision-making — all tailored to the player's character.

## Core Pillars

1. **LLM as DM** — The LLM narrates, reacts, adjudicates, and improvises. It runs the world.
2. **Procedural Worlds** — Each new game generates a unique world: regions, settlements, factions, dungeons, and a campaign arc.
3. **Character-Driven** — Full DnD character creation. Campaigns scale and adapt to class, level, and abilities.
4. **Browser-Native** — Runs entirely in the browser. No downloads. React frontend + backend API.

## Architecture

### Frontend (React + Vite + TypeScript)
- Character creation wizard
- World map / region navigation view
- Story/narration panel (DM text, dialogue, descriptions)
- Combat tracker (initiative, HP, dice rolls, abilities)
- Inventory & character sheet
- Decision/choice interface

### Backend (Python — FastAPI)
- **Game Engine** — Manages game state, rules adjudication, dice mechanics
- **LLM Orchestrator** — Manages prompts, context windows, and DM responses
- **World Generator** — Uses LLM to generate worlds, regions, NPCs, quest arcs
- **Campaign Manager** — Tracks story state, quest progress, encounters
- **Persistence** — SQLite for game saves, character data, world state

### LLM Integration
- Provider-agnostic (OpenAI / Claude / local model via config)
- Structured outputs for game data (JSON schemas)
- Context management: maintains session history + world state + character state
- Prompt engineering for DM persona, tone, and rule adherence

## Game Flow

```
1. New Game → Choose: Generate New World (or load save)
2. Character Creation:
   - Race, Class, Background
   - Ability scores (point buy or roll)
   - Equipment, spells (if applicable)
   - Backstory hooks
3. World Generation (LLM creates):
   - World overview (setting, tone, major conflicts)
   - Starting region + settlement
   - Campaign arc (3-5 acts with escalating stakes)
   - Key NPCs, factions, and hooks
4. Gameplay Loop:
   - DM narrates scene → Player chooses action → DM resolves
   - Exploration, social, combat encounters
   - Level progression, loot, story advancement
   - World reacts to player choices
```

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Frontend | React 18 + Vite + TypeScript | Fast, type-safe, huge ecosystem |
| Styling | TailwindCSS | Rapid UI, consistent theming |
| State | Zustand | Lightweight, no boilerplate |
| Backend | FastAPI (Python) | Async, fast, LLM-friendly ecosystem |
| Database | SQLite (start) → PostgreSQL (scale) | Zero-config to start |
| LLM | Provider-agnostic via config | Flexibility |

## DnD Rules Coverage (MVP)

- Character: Race, Class (core 12), Background, Abilities
- Mechanics: d20 rolls, advantage/disadvantage, skill checks
- Combat: Initiative, attacks, damage, conditions
- Magic: Spell slots, cantrips (simplified per class)
- Progression: XP, leveling (1-20)
- Equipment: Weapons, armor, consumables

## MVP Scope (First Playable)

1. ✅ Character creation (race, class, abilities)
2. ✅ World generation (single region + 1 quest arc)
3. ✅ DM narration with choice responses
4. ✅ Basic combat (attack, damage, HP)
5. ✅ Dice rolling (d20 system)
6. ✅ Save/load game

## Future (Post-MVP)
- Multiplayer (party-based)
- Visual map rendering
- AI-generated images for scenes/NPCs (in flight)
- Voice narration (TTS DM) (in flight)
- Homebrew content support
- Advanced rules (multiclassing, feats)

## Project Structure

```
dnd-llm-game/
├── frontend/          # React app
│   ├── src/
│   │   ├── components/
│   │   ├── views/
│   │   ├── stores/
│   │   └── types/
├── backend/           # FastAPI server
│   ├── app/
│   │   ├── api/       # API routes
│   │   ├── engine/    # Game logic & rules
│   │   ├── llm/       # LLM orchestration
│   │   ├── models/    # DB models
│   │   └── prompts/   # DM prompt templates
│   └── data/          # SQLite, world data
├── DESIGN.md
└── AGENTS.md
```
