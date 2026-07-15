# DnD LLM Game

A browser-based single-player Dungeons & Dragons game where an LLM acts as the Dungeon Master. The AI generates complete worlds, campaigns, and encounters, then guides you through them with dynamic narration, combat, and decision-making — all tailored to your character.

## Features

### Core Gameplay
- **Full DnD 5e Character Creation** — Race, class (all 12 core classes), abilities, background, multiclassing support, and feat system (53 feats including PHB + XGE race-specific)
- **AI Dungeon Master (DSPy-powered)** — LLM-powered DM that narrates, reacts, adjudicates rules, and improvises based on your actions. Uses DSPy for quest detection, NPC mood tracking, game flags, and structured skill-check resolution.
- **Streaming Narration** — Real-time DM text with a typing-cursor effect for immersive storytelling
- **Combat System** — Initiative tracking, turn order, attacks, damage rolls, saving throws, conditions, legendary actions, and enemy stat blocks
- **Spell System** — 108 spells across levels 0-9 with proper slot management, cantrip scaling, concentration tracking, and effect resolution
- **Inventory Management** — Weapons, armor, potions, scrolls, equipment with AC calculation, attunement slots, and stacking
- **XP & Leveling** — Automatic level-ups with HP growth, ability score improvements, and class feature tracking (including subclass selection at level 3)
- **World Exploration** — Visual region map with fog-of-war, overland travel, and terrain-based encounter rates
- **Save/Load** — Named game save slots that preserve all character state, story progress, and world state

### Advanced Mechanics
- **Multiclassing** — Characters can have up to 2 classes with per-class level tracking and proper HP/proficiency calculation
- **Feat System** — 53 feats including all PHB + XGE race-specific feats with prerequisites and effects (Sharpshooter, Great Weapon Master, Alert, Tough, etc.)
- **Conditions & Status Effects** — All 14 DnD 5e conditions with proper mechanical effects (blinded, charmed, frightened, exhausted, etc.)
- **Rest System** — Short rest (hit dice) and long rest (full HP recovery, slot recovery, condition clearing, exhaustion reduction)
- **Saving Throws** — Per-ability saves with class proficiency, feat integration, and skill-based bonuses
- **Encounter Difficulty** — CR-based XP budgets, party difficulty analysis, and 116 enemy templates across all CRs
- **Context Management** — Smart story summarization (DSPy-powered) to manage LLM context windows across long sessions
- **World State Persistence** — NPC relationships (trust/mood tracking), faction reputation, quest tracking, game flags for branching narrative
- **Environmental Systems** — Weather, lighting, terrain types, temperature effects, and environmental condition integration
- **Exhaustion & Starvation/Dehydration** — Survival mechanics with progressive effects and recovery
- **Mounts & Vehicles** — Mount rules, vehicle travel, and mounted combat
- **Disease & Poison Tracking** — Condition afflictions with duration, saves, and cure mechanics
- **Language System** — 18 language families for character background and communication
- **Alignment System** — 9 DnD alignments with in-game character sheet display
- **Character Backgrounds** — 18 backgrounds with skill proficiencies and feature integration
- **Tool Proficiencies** — Tool-based skill checks with proficiency bonuses

### DSPy-Powered Features
All LLM interactions are mediated by DSPy for structured, reliable outputs:
- **Quest Detection & Quest Log** — Automatic quest detection in DM narration + in-game quest log UI with status tracking (active/completed/failed)
- **NPC Mood Tracking** — Detects NPC attitude changes (positive/negative/neutral) and stores relationships in world state
- **Game Flags** — Automatic detection of narrative flags for branching story state (e.g., `met_king`, `found_secret_passage`)
- **Action Suggestions** — Contextually appropriate action suggestions rendered as clickable chips in the game view
- **Skill Check Resolution** — Structured mechanical outcomes for freeform player actions (degree, XP gained, stat changes, items)

### Content
- **108 Spells** — Including 20 iconic PHB/XGE spells (Chill Touch, Poison Spray, Shield, Mage Armor, Bless, Command, Hunter's Mark, etc.)
- **116 Enemies** — From CR 0 to CR 10+ (Goblins, Skeletons, Owlbears, Dragons, Giants, Devils, etc.)
- **53 Feats** — PHB + XGE race-specific feats
- **47 Tools** — Tool proficiencies with skill integration
- **18 Backgrounds** — Character backgrounds with skill proficiencies and features
- **9 Alignments** — DnD 5e alignments
- **18 Language Systems** — Language families for communication mechanics
- **19 Mounts/Vehicles** — Mounts and vehicles for overland travel
- **15 Traps** — Trap and hazard mechanics
- **27 Subclasses** — Subclass system with level 3 selection
- **6 Legendary Creatures** — Legendary actions and lair actions (MM p.11)
- **3 Starter Adventures** — Curated one-shot worlds playable without an LLM key (Cursed Mines of Emberdeep, Whispering Moor, Shattered Spires)

### AI-Powered Features
- **AI-Generated Images** — Provider-agnostic image generation for scenes and NPCs (configurable via `IMAGE_PROVIDER` env var)
- **In-Game Image Studio** — Visual panel for generating and viewing scene/NPC images with prompts
- **Voice Narration (TTS)** — Provider-agnostic text-to-speech for DM narration (OpenAI, Anthropic, or **on-device via mlx-audio/Kokoro** on Apple Silicon). Per-NPC voice assignment, auto-narrate toggle, streaming/chunked playback.
- **Local TTS (Zero-Config on Apple Silicon)** — On-device synthesis using Kokoro-82M model via Apple's MLX framework. No cloud API key required; automatic fallback to cloud providers on other platforms.
- **Per-NPC Voice Assignment** — Assign distinct TTS voices to named NPCs for in-character dialogue

### Frontend
- **Responsive Design** — Mobile-friendly with fluid layouts and themed components
- **Animations** — Smooth transitions, fade-ins, slide-ins, and visual feedback
- **Visual Map** — Terrain-tinted regions with fog-of-war, pan/zoom, and animated travel routes
- **Polished UI** — Color-coded HP bars, combat tracker, condition badges, and collapsible sidebar panels
- **In-Game Panels** — Quest log, feats, mounts, legendary actions, spells, exhaustion, saving throws, alignment, languages, backgrounds, environment, and more
- **Frontend Bundle Optimization** — 43% bundle reduction via dynamic imports (500 KB → 286 KB)

## Tech Stack

- **Frontend:** React 18 + Vite + TypeScript + TailwindCSS + Zustand
- **Backend:** Python FastAPI + SQLAlchemy + SQLite
- **LLM:** DSPy-mediated, provider-agnostic (OpenAI, Anthropic, or OpenAI-compatible local models)
- **Package Manager:** uv (Python), npm (frontend)

## Quick Start

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — the Python package manager (install via the [official installer](https://docs.astral.sh/uv/getting-started/installation/) or `pipx install uv`)
- Node.js 18+
- An LLM API key (OpenAI, Anthropic, or OpenAI-compatible local model). Optional for curated starter adventures (playable without a key).

### 1. Clone the Repository
```bash
git clone <your-repo-url>
cd dnd-llm-game
```

### 2. Backend Setup

```bash
# From the project root — create the virtualenv and install runtime + dev deps
uv sync

# Set up environment variables at the project root
cp .env.example .env
# Edit .env at the project root and add your LLM_API_KEY
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Build for production
npm run build

# Or run development server
npm run dev
```

### 4. Run the Game

```bash
# Terminal 1: Start backend (from the project root)
uv run backend

# Terminal 2: Start frontend (if using dev server)
cd frontend
npm run dev
```

Then open your browser to `http://localhost:5173` (dev) or `http://localhost:8000/static/` (production).

> **Backend port:** The Vite dev server proxies `/api` to `http://localhost:8000`
> by default (matching `.env.example`'s `PORT`). If your backend runs on a different
> port (the project-root `.env` `PORT`), start the frontend with that origin, e.g.
> `API_URL=http://localhost:8001 npm run dev` (run from `frontend/`), then reload
> http://localhost:5173. Restart `npm run dev` after changing `API_URL` — proxy
> config is not hot-reloaded.

### Play Without an LLM Key

The game includes 3 curated starter adventures (Cursed Mines of Emberdeep, Whispering Moor, Shattered Spires) that are fully playable without an LLM API key. Select one from the adventure picker at character creation.

## Configuration

The LLM provider is configured via environment variables in the project-root `.env`:

```env
# Required
LLM_PROVIDER=openai  # "openai", "anthropic", or "openai-compatible"
LLM_MODEL=gpt-4o
LLM_API_KEY=your-api-key-here

# Optional (for OpenAI-compatible local models like Ollama)
# LLM_BASE_URL=http://localhost:11434/v1

# Optional — AI-generated images (provider-agnostic)
IMAGE_PROVIDER=openai
IMAGE_MODEL=dall-e-3
IMAGE_API_KEY=your-api-key-here  # Falls back to LLM_API_KEY

# Optional — Voice narration (TTS, provider-agnostic)
TTS_PROVIDER=openai
TTS_MODEL=tts-1
TTS_API_KEY=your-api-key-here  # Falls back to LLM_API_KEY

# Server (optional — defaults shown)
# HOST=0.0.0.0
# PORT=8000
# RELOAD=true
```

### Supported LLM Providers

- **OpenAI:** Set `LLM_PROVIDER=openai` and `LLM_API_KEY` to your OpenAI key
- **Anthropic:** Set `LLM_PROVIDER=anthropic` and `LLM_API_KEY` to your Anthropic key
- **Local Models (Ollama, LM Studio, etc.):** Set `LLM_PROVIDER=openai-compatible`, `LLM_MODEL` to the model name, and `LLM_BASE_URL` to the endpoint

### Supported TTS Providers

- **OpenAI:** Set `TTS_PROVIDER=openai` and `TTS_API_KEY` to your OpenAI key
- **Any OpenAI-compatible endpoint:** Set `TTS_BASE_URL` to the endpoint (e.g., a local TTS server)

## Development

### Running Tests

```bash
# Backend tests (game engine: dice, combat, spells, leveling, …) — from the project root
uv run pytest -v

# Check test coverage
uv run pytest --cov=app --cov-report=html

# Frontend tests (React component integration tests via Vitest)
cd frontend
npm test                 # run once
npm run test:watch       # watch mode
```

### Type Checking (Frontend)

```bash
cd frontend
npx tsc --noEmit
```

### Project Structure

```
dnd-llm-game/
├── frontend/          # React app
│   ├── src/
│   │   ├── components/  # Reusable UI components
│   │   ├── views/       # Page-level components (Home, Game, CharacterCreation)
│   │   ├── stores/      # Zustand state management
│   │   └── types/       # TypeScript type definitions
│   └── package.json
├── backend/           # FastAPI server
│   ├── app/
│   │   ├── api/        # REST API endpoints
│   │   ├── engine/     # Game logic & rules (dice, combat, spells, etc.)
│   │   ├── llm/        # LLM orchestration and DSPy signatures/modules
│   │   ├── models/     # Database models
│   │   └── prompts/    # DM prompt templates (legacy — migrated to DSPy)
│   └── tests/          # Test suite
├── pyproject.toml     # uv project definition and the `backend` console script
├── .env               # Unified environment variables (gitignored; copy from .env.example)
├── DESIGN.md          # Architecture and design decisions
├── AGENTS.md          # Development guidelines and priorities
├── PROGRESS.md        # Development tracker with detailed completion status
└── docs/              # Research and design docs for ongoing features
```

## API Documentation

Once the backend is running, visit `http://localhost:8000/docs` for interactive API documentation (Swagger UI).

## Game Rules Coverage

The game implements comprehensive DnD 5e mechanics:

- ✅ Character creation (all 12 core classes + 27 subclasses)
- ✅ Ability scores (point buy system)
- ✅ Combat (initiative, attacks, damage, advantage/disadvantage, legendary actions)
- ✅ Saving throws (all 6 abilities with class proficiency and skill-based bonuses)
- ✅ Spells (108 spells, cantrips + levels 1-9, proper slot management, concentration, upcasting)
- ✅ Conditions (all 14 core conditions with mechanical effects, including exhaustion levels 1-6)
- ✅ Multiclassing (2-class limit with proper prerequisites, HP, and proficiency calculation)
- ✅ Feats (53 feats including PHB + XGE race-specific feats)
- ✅ Equipment (weapons, armor, AC calculation, attunement, tool proficiencies)
- ✅ Leveling (XP thresholds, HP growth, ASIs, subclass selection)
- ✅ Resting (short rest with hit dice, long rest recovery, condition clearing, exhaustion reduction)
- ✅ Environmental effects (weather, lighting, terrain, temperature)
- ✅ Survival mechanics (exhaustion, starvation, dehydration)
- ✅ Mounts & vehicles (mounted movement, combat, vehicle travel)
- ✅ Disease & poison (afflictions with saves, durations, cure conditions)
- ✅ Social interactions (3rd pillar — NPC mood, reputation, relationships)

## Current Status

**Version:** 0.1.0 (MVP + Advanced Features Complete)

**Test Suite:** 2647 backend tests passing + 163 frontend tests passing = **2810 total**, 0 failures ✅

**Core Features:** ✅ All MVP features implemented ✅ Advanced features complete ✅ DSPy migration complete ✅ AI features (images, TTS with local support) operational ✅ Local TTS via mlx-audio (Kokoro) complete

**Known Limitations:**
- Single-player only (multiplayer not yet implemented — AGENTS.md priority #13)

## Future Plans

See [DESIGN.md](DESIGN.md) for the full architecture, [PROGRESS.md](PROGRESS.md) for detailed progress tracking, and `docs/` for research on upcoming features:

**In Progress / Staged:**
- **DM Function Calling (Phase 1)** — DM calls `roll_dice()` for real dice rolls + check prompt UI. ✅ **COMPLETE** — see `docs/DM_FUNCTION_CALLING_RESEARCH.md`
- **Local TTS (mlx-audio)** — ✅ **COMPLETE** — On-device TTS via Apple MLX with Kokoro model for zero-config voice narration. Default on Apple Silicon; automatic fallback to cloud providers on other platforms.

**Planned:**
- Multiplayer / party-based play
- More homebrew content tools
- Advanced DSPy patterns (context-specific narration signatures, module composition)

## Contributing

This is a personal project, but feel free to open issues or pull requests if you'd like to contribute!

## License

MIT License — feel free to use this for your own projects.

## Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) for the backend
- [React](https://react.dev/) for the frontend
- [Vite](https://vitejs.dev/) for the build tool
- [TailwindCSS](https://tailwindcss.com/) for styling
- [Zustand](https://zustand-demo.pmnd.rs/) for state management
- [DSPy](https://dspy.ai/) for LLM mediation and structured outputs
- DnD 5e rules by Wizards of the Coast