# PROGRESS.md — DnD LLM Game Development Tracker

## Status: MVP SCAFFOLD COMPLETE ✅ VERIFIED ✅ STREAMING ✅ COMBAT ENGINE ✅ INVENTORY ✅ SPELLS ✅ LEVELING ✅ MAP/NAVIGATION ✅ SAVE/LOAD ✅ FRONTEND POLISH ✅ CONTEXT MANAGEMENT ✅ WORLD STATE PERSISTENCE ✅

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
|- [x] **Add combat engine** — initiative tracker, turn order, enemy stats
  - `Combatant` (HP/damage/conditions/enemy stats), `Attack` (crit doubling)
  - `Encounter` (initiative roll, deterministic turn order, round cycling,
    active/winner detection, `resolve_attack` d20-vs-AC with nat1/nat20)
  - JSON serialization for persistence; 27 combat tests (95 total)
- [x] **Add inventory management** — items, equipment, loot
  - `Item` (type, stats, value, weight, uses, quantity)
  - `Inventory` (add/remove, equip/unequip, use consumables)
  - Armor types with AC calculation (Light/Medium/Heavy/Shield)
  - Item stacking for consumables
  - Starting equipment by class (fighter, wizard, rogue, etc.)
  - Inventory API endpoints for CRUD operations
  - 36 inventory tests (131 total)

|- [x] **Add spell system** — spell slots, known spells per class
  - Spells engine with DnD 5e mechanics (cantrips, levels 1-9, schools)
  - Spellbook: known/prepared spells, slot tracking, casting
  - Caster profiles: full/half/third casters, known vs prepared styles
  - Starting spells per class (wizard, sorcerer, cleric, druid, bard, warlock, paladin, ranger)
  - Spell registry with ~20 common spells (fire bolt, magic missile, fireball, cure wounds, etc.)
  - Effect resolution: attack-roll, saving-throw, healing, direct damage
  - Cantrip scaling (extra dice at 5/11/17) and upcasting support
  - Long rest slot recovery
  - Spells API: get, initialize, learn, prepare, cast, rest
  - 65 spell tests (206 total)

|- [x] **Add XP/leveling** — automatic level-up, stat increases
  - `leveling.py` engine: DnD 5e XP threshold table (levels 1-20),
    level-for-XP resolution, level progress (XP into level, % to next)
  - HP growth (fixed-average hit die + CON mod per level, optional rolled);
    class hit-die table
  - Ability Score Improvements: standard 4/8/12/16/19, Fighter +6/+14,
    Rogue +10; ASI instance = 2 points (one +2 or two +1s), capped at 20
  - Class-feature milestone table (core 12 classes) for narration/UI
  - Leveling API: progress, award-xp (auto level-up + HP), apply-asi
    (+CON retroactively raises max HP), features
  - Character model: xp + asi_used columns; surfaced in CharacterResponse
  - Combat API: enemy kills award XP with auto level-up (HP reflected in-combat)
  - 81 leveling tests (287 total)

|- [x] **Add map/region navigation** — visual region explorer + overland travel
  - `navigation.py` engine: derives a connected region graph from world data
    (auto-layout coordinates, nearest-neighbour + bridge connectivity, terrain
    classification by keywords, terrain-based encounter rates)
  - `WorldMap`/`RegionNode`/`TravelResult` dataclasses; deterministic layout so
    only player position (current region + visited) is persisted
  - Overland travel: adjacency validation, distance-based travel hours,
    random encounters drawn from destination dangers
  - Navigation API: `GET /navigation/{id}/map`, `/regions`, `POST /travel`
    (persists position + `location`/`visited_locations` used elsewhere)
  - Frontend `WorldMap` component: SVG node graph with travel roads, pulsing
    current location, reachable/visited/unknown states, region detail panel
  - GameView: Map button + overlay modal; travel outcomes logged to story
  - World schema: optional region terrain/coordinates/connections for richer maps
  - 52 navigation tests (339 total)

|- [x] **Add save/load** — named snapshots with full state restoration
  - `SaveSlot` model: frozen point-in-time snapshot of the full mutable game
    state (character_snapshot + game_state + story_log + current_act),
    cascade-deletes with its GameSave
  - The key gap this closes: character state (HP, XP, level, ability scores,
    inventory, spells) is mutated directly on the Character row during play;
    a SaveSlot captures a copy so loading writes it back, rewinding the game
  - `app/api/saves.py` router: `POST /save` (create), `GET /saves` (list),
    `GET /saves/{id}` (detail), `POST /load/{id}` (restore), `DELETE /saves/{id}`
  - `capture_character_snapshot` / `apply_character_snapshot` helpers round-trip
    mutable fields; inventory/spells parsed to structured form in the snapshot
  - Frontend: `SaveSlotSummary`/`LoadSaveResult` types + API client; `setStory`
    action in Zustand for clean story resets; GameView 💾 Save button + Save/Load
    overlay modal (create, load, delete, character-state previews per slot)
  - 18 save/load tests (357 total)

|- [x] **Add frontend polish** — animations, responsive design, color fixes
  - Expanded Tailwind palette (leaf green, more arcane/blood shades, gold
    accent) — fixed HP bars, DM typing cursor, and save buttons that referenced
    previously-undefined colors (silent no-style bugs)
  - Animation system: fade-in / slide-up / slide-in-right / scale-in /
    overlay-in / glow-pulse keyframes + skeleton shimmer, registered as
    `animate-*` Tailwind utilities
  - Applied across all views: staggered view entrances, story entries slide
    in as appended, modals fade+scale, combat banner pulses, combat tracker
    slides in on combat start
  - Responsive: mobile-friendly card grids (Home), collapsible header labels,
    fluid padding, single-column tone grid, themed range sliders
  - Themed scrollbars, button hover-lift/active-press, color-graded HP bar
    with smooth transition, polished XP/Act badges; respects reduced-motion
  - Verified: `tsc --noEmit` clean, `vite build` passes (107 modules)

||- [x] **Add context window management** — smart story summarization
  - `ContextManager` engine with configurable thresholds (default: 20 entries triggers summary)
  - `StorySummary` dataclass: narrative summary, NPCs met, key locations, active/completed quests, current act, metadata
  - JSON serialization for database storage in new `story_summary` column
  - Auto-generates summaries when threshold reached, merges with existing summaries
  - Builds context from summary + recent raw entries (keeps last N entries)
  - Updated GameSave and SaveSlot models with `story_summary` column
  - Updated game API (`/action` and `/action/stream`) to use context manager
  - Updated save/load API to preserve story_summary
  - Migration script for new column
  - 16 context management tests (373 total)

||- [x] **Add world state persistence** — NPC relationship tracking, faction reputation
  - `NPCRelationship` dataclass: attitude (hostile/devoted), trust (-100 to 100), interaction history
  - `FactionReputation` dataclass: standing (hated/revered), reputation, quest completion/failure tracking
  - `WorldState` manager: persist in game_state JSON, backward compatible
  - 7 API endpoints: get world state, update NPC/faction, complete/fail quests, DM context summary
  - All changes persist to game_state JSON field in GameSave
  - 41 new tests (29 engine + 12 API), all passing
  - Total: 414 tests

## Next Priorities
- [ ] **[NEW FEATURE TO BE DEFINED]**

## How to Use This File
When you (the agent) work on the project:
1. Read this file first
2. Pick the top unchecked item from "Next Priorities"
3. Implement it
4. Test it
5. Move it to "Completed" and commit
6. Report what you did
