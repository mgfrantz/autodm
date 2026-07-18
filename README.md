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

### DM Function Calling (Real Game Mechanics)
The DM doesn't just narrate — it calls real game engine functions. Results flow as typed `GameEvent` objects to inline UI cards:
- **Phase 1 (Dice + Checks)** — DM calls `roll_dice()` for real d20 rolls; renders inline DiceRollCard (color-coded by outcome, advantage/disadvantage support) and CheckPromptCard (DM calls for a roll → player clicks → real resolution)
- **Phase 2 (Combat Resolution)** — DM emits `attack`/`damage`/`roll_initiative` game actions resolved via the real `Encounter` engine. The DM never fabricates attack rolls or damage — it describes intent, the engine resolves. Results render as inline AttackCard (hit/miss/crit/fumble color-coding + HP bar), DamageCard (damage-type-themed colors + HP bar + death indicator), and InitiativeCard (turn order with player/enemy highlighting). Combat state is persisted to `game_state["combat"]`.
- **Phase 3 (Spell Casting)** — DM emits `cast_spell` game actions resolved via the real `Spellbook.cast()` engine. The backend consumes the real spell slot, rolls the real attack/save/damage, and flows a typed `SPELL_CAST` GameEvent. Touches two stateful stores — the Spellbook on `character.spells` (slot consumption) AND the Encounter in `game_state["combat"]` (combat spell damage) — so a damage spell targeting a combatant reduces both. Results render as an inline SpellCastCard with school-themed colors, attack-roll/save/auto-damage/healing resolution modes, HP bar, slot-level badge, and failed-cast (muted) rendering. The DM never fabricates spell outcomes.
- **Phase 4 (Inventory Operations)** — DM emits `give_item`/`remove_item`/`equip_item`/`use_item` game actions resolved via the real `Inventory` engine. The DM describes intent ("the goblin drops a glowing potion"); the engine creates real Items (stacking, equip-slot exclusivity) and persists them to `character.inventory`. Two coupling side-effects: equipping armor/shield recalculates Armor Class (`ac_after`), and using a healing potion restores HP (2d4+2). Results flow as a typed `LOOT` GameEvent and render as an inline LootCard with rarity-themed colors, operation badges (🎁 gained / 📤 removed / ⚔️ equipped / 🧪 used), quantity/value/healing/AC/uses indicators, source provenance, and failed-operation (muted) rendering. An `INVENTORY_ROSTER` (id/name/type/qty/equipped/rarity) is injected into the DM situation prompt so the DM can reference real item_ids.
- **Phase 5 (Conditions)** — DM emits `apply_condition`/`remove_condition` game actions resolved via the real conditions engine (`conditions.py`). The DM describes intent ("the ghoul's claws paralyze you"); the engine applies real DnD 5e conditions (all 14: blinded, charmed, deafened, frightened, grappled, incapacitated, invisible, paralyzed, petrified, poisoned, prone, restrained, stunned, unconscious) with durations. Dual-state resolution: player conditions persist to `game_state["conditions"]` (via a `_PlayerConditionState` adapter), combatant conditions persist on the Combatant object. Results flow as a typed `CONDITION_APPLIED` GameEvent and render as an inline ConditionCard with severity-themed colors (severe=red, moderate=amber), condition-specific emoji icons, duration badges, mechanical-effect descriptions, and failed-operation (muted) rendering.
- **Phase 3.5 (Concentration Tracking)** — The DM's spells now actually maintain concentration with real Constitution saves (PHB p.203-204), wired to the fully-built `concentration.py` engine. Unlike Phases 1-5, concentration is **reactive**: it changes as a side-effect of existing actions via coupling hooks — casting a concentration spell starts it (auto-ending any previous one), an incapacitating condition on the player breaks it, and a damage action targeting `"player"` triggers a real Con-save check (DC 10 or half-damage). The DM can also voluntarily `end_concentration`. Results flow as typed `CONCENTRATION` GameEvents (started/broken/ended/check_passed/check_failed) and render as inline ConcentrationCards (operation-themed colors, 🧠 icon, Con-save breakdown badges) — the DM never fabricates a concentration outcome.
- **Game Event UI Polish** — Inline event cards now *feel* like a virtual tabletop: dice **tumble** through random faces for ~480ms before settling on the real result (opt-in via `animate`, respects `prefers-reduced-motion`), the **HP bar shakes** when damage lands (AttackCard/DamageCard), and **older events collapse** to a one-line summary by default (the most recent stay expanded; click to re-expand) so a busy turn stays readable. All pure logic lives in `utils/` + `hooks/` and is unit-tested.
- **Phase 3.5b (AoE Spells)** — The DM can cast **one spell at multiple combatants** in a single action (`cast_spell_aoe`). Fireball hitting a cluster of goblins now consumes **one slot**, rolls damage **once**, and resolves a **separate saving throw per target** — exactly PHB p.204. The key architectural move: `Spellbook.prepare_cast()` (new) consumes the slot without resolving the effect, then `resolve_spell_aoe_target()` resolves each target against the shared damage. One summary `spell_cast` event (`is_aoe=True`, target count, total damage, no HP bar) + N follow-up `damage` events (each with that target's HP bar + save-outcome badge). Backward compatible — single-target `cast_spell` is untouched.

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
- **Polished UI** — Color-coded HP bars, combat tracker, condition badges, collapsible sidebar panels, dice-tumble animation, HP-bar shake, and collapsed-by-default old event cards
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

**Test Suite:** 2902 backend tests passing + 393 frontend tests passing = **3295 total**, 0 failures ✅

**Core Features:** ✅ All MVP features implemented ✅ Advanced features complete ✅ DSPy migration complete ✅ AI features (images, TTS with local support) operational ✅ Local TTS via mlx-audio (Kokoro) complete

**Known Limitations:**
- Single-player only (multiplayer not yet implemented — AGENTS.md priority #13)

## Future Plans

See [DESIGN.md](DESIGN.md) for the full architecture, [PROGRESS.md](PROGRESS.md) for detailed progress tracking, and `docs/` for research on upcoming features:

**Recently Completed:**
- **DM Function Calling (Phase 3.5b — AoE Multi-Target Spells)** — The DM can now cast **one spell at multiple combatants** in a single action (`cast_spell_aoe`). Fireball hitting three goblins consumes **one slot**, rolls damage **once**, and resolves a **separate saving throw per target** — exactly PHB p.204. The key architectural move: `Spellbook.prepare_cast()` (new) consumes the slot without resolving the effect, then `resolve_spell_aoe_target()` resolves each target against the shared damage roll. One summary `spell_cast` event + N follow-up `damage` events (each with HP bar + save-outcome badge). Single-target `cast_spell` is untouched (backward compatible). +38 backend + 19 frontend tests. ✅ **COMPLETE** — see `docs/DM_FUNCTION_CALLING_RESEARCH.md`
- **DM Function Calling — Game Event UI Polish** — Inline event cards now feel like a virtual tabletop. Dice **tumble** through random faces (~480ms) before settling on the real result (opt-in `animate` prop, `prefers-reduced-motion`-aware); the **HP bar shakes** when damage lands on AttackCard/DamageCard; and **older event cards collapse** to a one-line summary by default (most-recent stay expanded, click to re-expand) so a busy turn stays readable. New pure helpers (`utils/diceTumble.ts`, `eventIcon`/`eventAccent`/`shouldCollapse`) + a `useDiceTumble`/`useDiceTumbleRolls` hook; +49 frontend tests. ✅ **COMPLETE** — see `docs/DM_FUNCTION_CALLING_RESEARCH.md`
- **DM Function Calling (Phase 3.5 — Concentration Tracking)** — The DM's spells now actually maintain concentration with real Constitution saves (PHB p.203-204), wired to the fully-built `concentration.py` engine. Concentration is **reactive**: it starts on a concentration cast (auto-ending any previous one), breaks on an incapacitating condition, and a damage action targeting the player triggers a real Con-save check (DC 10 or half-damage). The DM can also voluntarily `end_concentration`. Results flow as typed `CONCENTRATION` GameEvents (started/broken/ended/check_passed/check_failed) and render as inline ConcentrationCards (operation-themed colors, Con-save breakdown) — the DM never fabricates a concentration outcome. ✅ **COMPLETE** — see `docs/DM_FUNCTION_CALLING_RESEARCH.md`
- **DM Function Calling (Phase 5 — Conditions)** — DM emits `apply_condition`/`remove_condition` game actions resolved via the real conditions engine. Dual-state resolution: player conditions persist to `game_state["conditions"]` via a `_PlayerConditionState` adapter (with parallel `condition_durations` for timed effects); combatant conditions persist on the Combatant object. All 14 core DnD 5e conditions supported with durations. Results render as inline ConditionCards (severity-themed colors, condition-specific icons, duration badges, mechanical-effect descriptions). ✅ **COMPLETE** — see `docs/DM_FUNCTION_CALLING_RESEARCH.md`
- **DM Function Calling (Phase 4 — Inventory Operations)** — DM emits `give_item`/`remove_item`/`equip_item`/`use_item` game actions resolved via the real `Inventory` engine. The DM describes intent; the engine creates real Items (stacking, equip-slot exclusivity) and persists them to `character.inventory`. Two coupling side-effects: equip recalculates Armor Class, and using a healing potion restores HP (2d4+2). An `INVENTORY_ROSTER` is injected into the DM prompt so the DM references real item_ids. Results flow as a typed `LOOT` GameEvent and render as an inline LootCard (rarity-themed colors, operation badges, quantity/value/healing/AC/uses indicators, failed-operation card). ✅ **COMPLETE** — see `docs/DM_FUNCTION_CALLING_RESEARCH.md`
- **DM Function Calling (Phase 3 — Spell Casting)** — DM emits `cast_spell` game actions resolved via the real `Spellbook.cast()` engine; the backend consumes the real spell slot and rolls the real attack/save/damage. Dual-state resolution couples the Spellbook (`character.spells`) with the Encounter (`game_state["combat"]`) so combat spell damage reduces combatant HP (+ follow-up DAMAGE event). Results flow as a typed SPELL_CAST GameEvent and render as an inline SpellCastCard (school-themed colors, attack/save/heal modes, HP bar, failed-cast rendering). ✅ **COMPLETE** — see `docs/DM_FUNCTION_CALLING_RESEARCH.md`
- **DM Function Calling (Phase 2 — Combat Resolution)** — DM emits `attack`/`damage`/`roll_initiative` game actions resolved via the real `Encounter` engine; results flow as typed GameEvents (ATTACK/DAMAGE/INITIATIVE) and render as inline AttackCard/DamageCard/InitiativeCard components with HP bars, hit/miss/crit colour-coding, and death indicators. ✅ **COMPLETE** — see `docs/DM_FUNCTION_CALLING_RESEARCH.md`
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