# DnD LLM Game

A browser-based single-player Dungeons & Dragons game where an LLM acts as the Dungeon Master. The AI generates complete worlds, campaigns, and encounters, then guides you through them with dynamic narration, combat, and decision-making — all tailored to your character.

## Features

### Core Gameplay
- **Full DnD 5e Character Creation** — Race, class (all 12 core classes), abilities, background, multiclassing support, and feat system
- **AI Dungeon Master** — LLM-powered DM that narrates, reacts, adjudicates rules, and improvises based on your actions
- **Streaming Narration** — Real-time DM text with a typing-cursor effect for immersive storytelling
- **Combat System** — Initiative tracking, turn order, attacks, damage rolls, saving throws, conditions, and enemy stat blocks
- **Spell System** — 88 spells across levels 0-9 with proper slot management, cantrip scaling, and effect resolution
- **Inventory Management** — Weapons, armor, potions, scrolls, equipment with AC calculation and stacking
- **XP & Leveling** — Automatic level-ups with HP growth, ability score improvements, and class feature tracking
- **World Exploration** — Visual region map with fog-of-war, overland travel, and terrain-based encounter rates
- **Save/Load** — Named game save slots that preserve all character state, story progress, and world state

### Advanced Mechanics
- **Multiclassing** — Characters can have up to 2 classes with per-class level tracking and proper HP/proficiency calculation
- **Feat System** — 23+ feats with prerequisites and effects (Sharpshooter, Great Weapon Master, Alert, Tough, etc.)
- **Conditions & Status Effects** — All 14 DnD 5e conditions with proper mechanical effects (blinded, charmed, frightened, etc.)
- **Rest System** — Short rest (hit dice) and long rest (full HP recovery, slot recovery, condition clearing)
- **Saving Throws** — Per-ability saves with class proficiency and feat integration
- **Encounter Difficulty** — CR-based XP budgets, party difficulty analysis, and 116 enemy templates across all CRs
- **Context Management** — Smart story summarization to manage LLM context windows
- **World State Persistence** — NPC relationships, faction reputation, quest tracking

### Content
- **88 Spells** — Covering all schools and levels 0-9
- **116 Enemies** — From CR 0 to CR 10+ (Goblins, Skeletons, Owlbears, Dragons, Giants, Devils, etc.)
- **23 Feats** — Core DnD 5e feats with proper prerequisites
- **Homebrew Support** — Create and use custom items

### Frontend
- **Responsive Design** — Mobile-friendly with fluid layouts and themed components
- **Animations** — Smooth transitions, fade-ins, slide-ins, and visual feedback
- **Visual Map** — Terrain-tinted regions with fog-of-war, pan/zoom, and animated travel routes
- **Polished UI** — Color-coded HP bars, combat tracker, condition badges, and more

## Tech Stack

- **Frontend:** React 18 + Vite + TypeScript + TailwindCSS + Zustand
- **Backend:** Python FastAPI + SQLAlchemy + SQLite
- **LLM:** Provider-agnostic (OpenAI, Anthropic, or OpenAI-compatible local models)

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- An LLM API key (OpenAI, Anthropic, or OpenAI-compatible local model)

### 1. Clone the Repository
```bash
git clone <your-repo-url>
cd dnd-llm-game
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env and add your LLM_API_KEY
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
# Terminal 1: Start backend
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Terminal 2: Start frontend (if using dev server)
cd frontend
npm run dev
```

Then open your browser to `http://localhost:5173` (dev) or `http://localhost:8000/static/` (production).

## Configuration

The LLM provider is configured via environment variables in `backend/.env`:

```env
# Required
LLM_PROVIDER=openai  # "openai", "anthropic", or "openai-compatible"
LLM_MODEL=gpt-4o
LLM_API_KEY=your-api-key-here

# Optional (for OpenAI-compatible local models like Ollama)
# LLM_BASE_URL=http://localhost:11434/v1
```

### Supported LLM Providers

- **OpenAI:** Set `LLM_PROVIDER=openai` and `LLM_API_KEY` to your OpenAI key
- **Anthropic:** Set `LLM_PROVIDER=anthropic` and `LLM_API_KEY` to your Anthropic key
- **Local Models (Ollama, LM Studio, etc.):** Set `LLM_PROVIDER=openai-compatible`, `LLM_MODEL` to the model name, and `LLM_BASE_URL` to the endpoint

## Development

### Running Tests

```bash
# Backend tests
cd backend
source venv/bin/activate
pytest tests/ -v

# Check test coverage
pytest tests/ --cov=app --cov-report=html
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
│   │   ├── llm/        # LLM orchestration and prompts
│   │   ├── models/     # Database models
│   │   └── prompts/    # DM prompt templates
│   ├── tests/          # Test suite (749 passing tests)
│   └── requirements.txt
├── DESIGN.md          # Architecture and design decisions
├── AGENTS.md          # Development guidelines and priorities
└── PROGRESS.md        # Development tracker
```

## API Documentation

Once the backend is running, visit `http://localhost:8000/docs` for interactive API documentation (Swagger UI).

## Game Rules Coverage

The game implements core DnD 5e mechanics:

- ✅ Character creation (all 12 core classes)
- ✅ Ability scores (point buy system)
- ✅ Combat (initiative, attacks, damage, advantage/disadvantage)
- ✅ Saving throws (all 6 abilities with class proficiency)
- ✅ Spells (cantrips + levels 1-9, proper slot management)
- ✅ Conditions (all 14 core conditions with mechanical effects)
- ✅ Multiclassing (2-class limit with proper prerequisites)
- ✅ Feats (23+ core feats)
- ✅ Equipment (weapons, armor, AC calculation)
- ✅ Leveling (XP thresholds, HP growth, ASIs)
- ✅ Resting (short rest with hit dice, long rest recovery)

## Current Status

**Version:** 0.1.0 (MVP Complete)

**Test Suite:** 749 passing, 0 failing ✅

**Core Features:** ✅ All MVP features implemented

**Known Limitations:**
- Single-player only (multiplayer not yet implemented)
- No voice narration (future feature)
- No AI-generated images (future feature)

## Future Plans

See [DESIGN.md](DESIGN.md) for the full roadmap. Planned future features include:

- AI-generated images for scenes and NPCs
- Voice narration / TTS for the DM
- Multiplayer / party-based play
- Visual dungeon maps
- More homebrew content tools

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
- DnD 5e rules by Wizards of the Coast