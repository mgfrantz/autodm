# DnD LLM Game

A browser-based single-player Dungeons & Dragons game where an LLM acts as the Dungeon Master. The AI generates complete worlds, campaigns, and encounters, then guides you through them with dynamic narration, combat, and decision-making — all tailored to your character.

## Features

### Core Gameplay
- **Full DnD 5e Character Creation** — Race, class (all 12 core classes), abilities, background, multiclassing support, and feat system (67 feats including PHB + XGE race-specific + Tasha's Cauldron of Everything)
- **AI Dungeon Master (DSPy-powered)** — LLM-powered DM that narrates, reacts, adjudicates rules, and improvises based on your actions. Uses DSPy for quest detection, NPC mood tracking, game flags, and structured skill-check resolution.
- **Streaming Narration** — Real-time DM text with a typing-cursor effect for immersive storytelling
- **Combat System** — Initiative tracking, turn order, attacks, damage rolls, saving throws, conditions, legendary actions, and enemy stat blocks
- **Spell System** — 327 spells across levels 0-9 (all eleven PHB spell tiers now PHB-complete) with proper slot management, cantrip scaling, concentration tracking, and effect resolution
- **Inventory Management** — Weapons, armor, potions, scrolls, equipment with AC calculation, attunement slots, and stacking
- **XP & Leveling** — Automatic level-ups with HP growth, ability score improvements, and class feature tracking (including subclass selection at level 3)
- **World Exploration** — Visual region map with fog-of-war, overland travel, and terrain-based encounter rates
- **Save/Load** — Named game save slots that preserve all character state, story progress, and world state

### Advanced Mechanics
- **Multiclassing** — Characters can have up to 2 classes with per-class level tracking and proper HP/proficiency calculation
- **Feat System** — 67 feats including all PHB + XGE race-specific feats + Tasha's Cauldron of Everything feats with prerequisites and effects (Sharpshooter, Great Weapon Master, Alert, Tough, Fey Touched, Shadow Touched, Crusher/Piercer/Slasher, Skill Expert, etc.)
- **Conditions & Status Effects** — All 14 DnD 5e conditions with proper mechanical effects (blinded, charmed, frightened, exhausted, etc.)
- **Rest System** — Short rest (hit dice) and long rest (full HP recovery, slot recovery, condition clearing, exhaustion reduction)
- **Saving Throws** — Per-ability saves with class proficiency, feat integration, and skill-based bonuses
- **Encounter Difficulty** — CR-based XP budgets, party difficulty analysis, and 169 enemy templates across all CRs (0–30)
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
- **327 Spells** — Including 20 iconic PHB/XGE spells (Chill Touch, Poison Spray, Shield, Mage Armor, Bless, Command, Hunter's Mark, etc.) for levels 0-3, 25 iconic high-level SRD spells for levels 4-9 (Banishment, Dominate Person, Circle of Death, Delayed Blast Fireball, Antimagic Field, Mass Heal, Prismatic Wall, etc.), 6 PHB level-9 spells completing the tier (Astral Projection, Gate, Imprisonment, Shapechange, Storm of Vengeance, Weird), 15 PHB level 7 & 8 spells rounding both tiers to 18/18 (Divine Word, Etherealness, Mordenkainen's Magnificent Mansion, Mordenkainen's Sword, Project Image, Sequester, Symbol, Animal Shapes, Antipathy/Sympathy, Clone, Control Weather, Demiplane, Glibness, Holy Aura, Telepathy), 16 iconic PHB level-1 spells expanding the most-played tier (Alarm, Comprehend Languages, Disguise Self, False Life, Find Familiar, Fog Cloud, Hellish Rebuke, Identify, Inflict Wounds, Longstrider, Protection from Evil and Good, Ray of Sickness, Sanctuary, Speak with Animals, Tasha's Hideous Laughter, Witch Bolt), 16 more PHB level-1 spells completing the tier to full PHB coverage (Animal Friendship, Color Spray, Compelled Duel, Create or Destroy Water, Detect Evil and Good, Detect Poison and Disease, Expeditious Retreat, Feather Fall, Goodberry, Heroism, Jump, Purify Food and Drink, Silent Image, Tenser's Floating Disk, Unseen Servant, Wrathful Smite), 19 PHB level-6 spells completing that tier to full PHB coverage (Arcane Gate, Blade Barrier, Conjure Fey, Contingency, Create Undead, Drawmij's Instant Summons, Eyebite, Find the Path, Guards and Wards, Magic Jar, Mass Suggestion, Move Earth, Otiluke's Freezing Sphere, Planar Ally, Programmed Illusion, Transport via Plants, Wall of Thorns, Wind Walk, Word of Recall), 20 iconic PHB level-2 spells expanding the tier (Moonbeam, Flame Blade, Spiritual Weapon, Heat Metal, Spike Growth, Phantasmal Force, Crown of Madness, Calm Emotions, Enlarge/Reduce, Levitate, Darkness, Silence, Blur, Barkskin, Detect Thoughts, See Invisibility, Darkvision, Knock, Augury, Pass Without Trace), 19 PHB level-2 spells completing the tier to full PHB coverage, 26 PHB level-3 spells completing the tier to full PHB coverage (Glyph of Warding, Bestow Curse, Slow, Sleet Storm, Vampiric Touch, Wind Wall, Animate Dead, Beacon of Hope, Clairvoyance, Conjure Animals, Create Food and Water, Crusader's Mantle, Daylight, Elemental Weapon, Feign Death, Gaseous Form, Plant Growth, Protection from Energy, Remove Curse, Sending, Speak with Dead, Speak with Plants, Tiny Hut, Tongues, Water Breathing, Water Walk), 16 PHB level-4 spells completing the tier to full PHB coverage (Wall of Fire, Sickening Radiance, Compulsion, Otiluke's Resilient Sphere, Arcane Eye, Conjure Minor Elementals, Control Water, Divination, Fabricate, Giant Insect, Guardian of Faith, Hallucinatory Terrain, Leomund's Secret Chest, Locate Creature, Mordenkainen's Faithful Hound, Stone Shape), and 26 PHB level-5 spells completing the tier to full PHB coverage (Destructive Wave, Conjure Volley, Contagion, Modify Memory, Telekinesis, Planar Binding, Geas, Seeming, Awaken, Banishing Smite, Circle of Power, Commune, Commune with Nature, Conjure Elemental, Contact Other Plane, Creation, Dispel Evil and Good, Dream, Hallow, Legend Lore, Passwall, Raise Dead, Reincarnate, Swift Quiver, Teleportation Circle, Tree Stride), and 15 PHB cantrips completing the cantrip tier to full PHB coverage (Produce Flame, Thorn Whip, Blade Ward, Dancing Lights, Druidcraft, Friends, Guidance, Mending, Message, Prestidigitation, Resistance, Shillelagh, Spare the Dying, Thaumaturgy, True Strike). **All eleven PHB spell tiers (0-9, cantrips through level 9) are now PHB-complete — the full Player's Handbook spell roster is registered.**
- **169 Enemies** — From CR 0 to CR 30 (Goblins, Skeletons, Owlbears, Dragons, Giants, Devils, Beholder, Tarrasque, etc.). Every CR band 11–24 now has ≥2 entries; the chromatic & metallic dragon family is canonical-complete at adult + ancient tiers (Adult White/Bronze, Ancient Green/Blue/Silver, plus Solar, Empyrean, Remorhaz, Roc, Arcanaloth). The iconic-monster gap is now closed: Orc, Gnoll, Ghoul, Shadow, Specter, Wraith, Banshee, Mimic, Displacer Beast, Manticore, Hell Hound, Doppelganger, Griffon, Unicorn, Water Elemental, Wyvern, Mind Flayer, Aboleth, the full Golem family (Flesh/Clay/Stone/Iron), Purple Worm, Ettin, and Treant are all registered (145→169).
- **67 Feats** — PHB + XGE race-specific + Tasha's Cauldron of Everything
- **47 Tools** — Tool proficiencies with skill integration
- **18 Backgrounds** — Character backgrounds with skill proficiencies and features
- **9 Alignments** — DnD 5e alignments
- **18 Language Systems** — Language families for communication mechanics
- **18 Mounts/Vehicles** — Mounts and vehicles for overland travel
- **14 Traps** — Trap and hazard mechanics
- **40 Subclasses** — Full PHB subclass coverage across all twelve core classes (PHB-complete): 7 Cleric domains, 8 Wizard schools, 3 each for Fighter/Monk/Paladin/Rogue/Warlock, 2 each for Barbarian/Bard/Druid/Ranger/Sorcerer
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

- ✅ Character creation (all 12 core classes + 40 subclasses — full PHB coverage)
- ✅ Ability scores (point buy system)
- ✅ Combat (initiative, attacks, damage, advantage/disadvantage, legendary actions)
- ✅ Saving throws (all 6 abilities with class proficiency and skill-based bonuses)
- ✅ Spells (327 spells, cantrips + levels 1-9, proper slot management, concentration, upcasting)
- ✅ Conditions (all 14 core conditions with mechanical effects, including exhaustion levels 1-6)
- ✅ Multiclassing (2-class limit with proper prerequisites, HP, and proficiency calculation)
- ✅ Feats (67 feats including PHB + XGE race-specific + Tasha's Cauldron of Everything feats)
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

**Test Suite:** 4523 backend tests passing + 393 frontend tests passing = **4916 total**, 0 failures ✅

**Core Features:** ✅ All MVP features implemented ✅ Advanced features complete ✅ DSPy migration complete ✅ AI features (images, TTS with local support) operational ✅ Local TTS via mlx-audio (Kokoro) complete

**Known Limitations:**
- Single-player only (multiplayer not yet implemented — AGENTS.md priority #13)

## Future Plans

See [DESIGN.md](DESIGN.md) for the full architecture, [PROGRESS.md](PROGRESS.md) for detailed progress tracking, and `docs/` for research on upcoming features:

### Recently Completed
- **Iconic Trap Registry Expansion (18 traps → 14→32)** — Closed the trap registry's **iconic-trap gap** — the last content registry still modelled at only its bare sample size (the 14 DMG Chapter 5 sample traps). The catalogue was already PHB-complete for spells/subclasses/feats and canonical-complete for enemies, but many of the *most-played* iconic traps were absent (Spiked Pit, Arrow Trap, Crushing Wall, Falling Block, Spear Trap, Ceiling Spikes, Explosive Rune, Lightning Trap, Acid Spray, Freezing Trap, Wailing Trap, Web Trap, etc.). Added **18 canonical / iconic traps** inline into their proper type sections: **10 mechanical traps** (Spiked Pit — 1d6 fall + 1d10 piercing; Arrow Trap — 2d10 piercing Dex DC 15; Crushing Wall — 8d10 bludgeoning Str DC 20 DEADLY; Falling Block — 4d10 Dex DC 15; Falling Portcullis — 2d10 slashing + restrained; Weak Floor — 1d6 fall; Spear Trap — 3d8 piercing; Tripwire Crossbow — 1d10 Dex DC 13 negate; Ceiling Spikes — 3d10 piercing; Spinning Blade — 3d6 slashing + prone) and **8 magical traps** (Explosive Rune — 6d6 fire; Lightning Trap — 8d6 lightning; Acid Spray Trap — 4d6 acid; Freezing Trap — 4d6 cold + restrained; Wailing Trap — 8d8 thunder + deafened DEADLY; Web Trap — restrained; **Summoning Trap** and **Telekinesis Trap**). Severity bands follow DMG ch.5 guidance throughout (setback DC 10–11, dangerous DC 12–19, deadly DC 18–20+) and damage scales with severity. **Secondary win:** the `TrapEffectType.SUMMON` and `TELEKINESIS` enums were previously *declared but exercised by zero traps* — the new Summoning Trap and Telekinesis Trap are the first registry entries to use them, so every `TrapEffectType` value is now backed by at least one entry. +200 backend tests (4523 total). ✅ **COMPLETE**

- **Iconic Monster Manual Enemy Registry Gap-Fill (24 monsters → 145→169)** — Closed the registry's **iconic-monster gap**. The catalogue was PHB-complete for spells/subclasses/feats and canonical-complete for the dragon family, but was missing many of the *most-played* Monster Manual monsters. Added **24 canonical MM monsters inline into their proper CR bands**: **humanoid staples** (Orc, Gnoll), **undead** (Ghoul, Specter, Wraith, Banshee), **iconic aberrations** (Mind Flayer/Illithid, Aboleth — both glaring omissions), the **full Golem family** (Flesh/Clay/Stone/Iron — constructs were entirely absent), **monstrosities/beasts** (Mimic, Displacer Beast, Manticore, Doppelganger, Wyvern, Griffon, Purple Worm, Ettin, Treant), and **fiends/elementals/celestials** (Hell Hound, Unicorn, Water Elemental). CR/AC/HP follow the printed MM stat blocks; damage immunities/resistances are canonical per MM (golems immune to nonmagical BPS + their type immunities, undead immune to poison + resist nonmagical BPS, etc.). The enemy registry now stands at **169 templates** (CRs 0–30), and `get_enemies_by_cr()` now returns iconic monsters at every populated tier. +167 backend tests (4323 total). ✅ **COMPLETE**

- **Tasha's Cauldron of Everything Feat Expansion (14 feats → 53→67)** — Extended the feat registry with the canonical TCoE feat set (p.79-91), the natural next expansion after the existing "PHB + XGE race-specific" roster. Added **all 14 canonical Tasha's feats**: **10 TCoE "half-feats"** (grant a +1 to a chosen ability — the TCoE design philosophy): Chef (+1 CON/WIS — rest treats for temp HP), Crusher (+1 STR/CON — bludgeoning hit push + crit advantage), Fey Touched (+1 INT/WIS/CHA — Misty Step + a 1st-level divination/enchantment spell), Gunner (+1 DEX — firearm proficiency), Piercer (+1 STR/DEX/CON — piercing reroll + crit extra die), Shadow Touched (+1 INT/WIS/CHA — Invisibility + a 1st-level illusion/necromancy spell), Skill Expert (+1 any — proficiency + expertise), Slasher (+1 STR/DEX — slashing speed reduction + crit disadvantage), Telekinetic (+1 INT/WIS/CHA — Mage Hand + bonus-action shove), Telepathic (+1 INT/WIS/CHA — 60-ft telepathy + bonus-action Detect Thoughts); and **4 TCoE special feats** (no ability bump): Eldritch Adept (Eldritch Invocation, requires caster), Fighting Initiate (a Fighting Style), Metamagic Adept (2 Metamagic options + 2 sorcery points, requires sorcerer), Poisoner (bonus-action poison + 2d8 rider). Canonical mechanics throughout: half-feat ability choices are exact per TCoE, prerequisites match TCoE exactly (Eldritch Adept = caster-gate, Metamagic Adept = sorcerer-gate, the rest ungated), all free-form effects modelled as structured `combat_modifiers`, and source attribution is `"Tasha's Cauldron of Everything"` for all 14 so the feat-source system and in-game feats panel display the correct origin. The feat registry now stands at **67 feats** (39 PHB + 14 XGE + 14 TCoE). +27 backend tests (4156 total). ✅ **COMPLETE**

- **PHB Subclass Completion (11 subclasses → all twelve core classes now PHB-complete, 29→40)** — Closed the registry's subclass gap — the last non-PHB-canonical content registry after the catalogue-wide PHB spell completeness effort finished at every tier. The engine previously modelled a *representative* 29 subclasses (2–3 per core class); the Player's Handbook ships a canonical **40** across the twelve core classes. Added **all 11 missing PHB subclasses** so **every Player's Handbook subclass is now modelled** (29 → 40 = full PHB coverage): **4 Cleric Divine Domains** (Light — Warding Flare / Radiance of the Dawn / Corona of Light; Nature — Acolyte of Nature / Charm Animals and Plants / Dampen Elements; Tempest — Wrath of the Storm / Destructive Wrath / Thunderbolt Strike / Stormborn; Trickery — Blessing of the Trickster / Invoke Duplicity / Cloak of Shadows / Improved Duplicity), **1 Monk Monastic Tradition** (Way of the Four Elements — Ki-fueled elemental disciplines), and **6 Wizard Arcane Traditions / Schools** (Conjuration, Divination, Enchantment, Illusion, Necromancy, Transmutation — Savant + the signature level-2/6/10/14 features for each). Canonical mechanics throughout: feature progressions land at the PHB choice-tier stops (cleric domains 1/2/6/8/17; monk 3/6/11/17; wizard 2/6/10/14); every new cleric domain grants Divine Strike at 8 with its canonical damage rider (radiant/cold-fire-lightning/thunder/poison); every new wizard school grants Savant at 2; names match PHB exactly. The subclass registry now stands at **40 subclasses** — `{barbarian:2, bard:2, cleric:7, druid:2, fighter:3, monk:3, paladin:3, ranger:2, rogue:3, sorcerer:2, warlock:3, wizard:8}` — **ALL TWELVE CORE CLASSES ARE NOW PHB-COMPLETE**, with **no remaining non-canonical subclass counts**. Also hardened a latent flaky attack-roll test (`test_thorn_whip_attacks_hit_and_miss` in `test_spell_cantrip_completion.py` — d20+7 vs AC 10 has a 15% miss chance) via the established `_force_d20` monkeypatch pattern. +185 backend tests (4129 total). ✅ **COMPLETE**
- **PHB Cantrip-Tier Completion (15 spells → cantrips now PHB-complete, 14→29 — ALL ELEVEN SPELL TIERS 0–9 NOW PHB-COMPLETE)** — Closed the catalogue's *final* remaining tier gap. After all ten *leveled* tiers (1–9) reached PHB coverage, the cantrip tier was the only non-canonical count left (was 14; PHB has 27). Added **all 15 missing PHB cantrips** so **every Player's Handbook cantrip is now registered** (level 0: 14 → 29 = 27 PHB + Toll the Dead [XGE] + Mind Sliver [Tasha's]). The additions cover all three cantrip resolution paths: **attack-roll cantrips** (Produce Flame — 1d8 fire, thrown 30 ft, doubles as a light source; Thorn Whip — 1d6 piercing, 30 ft melee spell attack, pulls target up to 10 ft closer), and **utility/buff cantrips** (Blade Ward, Dancing Lights, Druidcraft, Friends, Guidance, Mending, Message, Prestidigitation, Resistance, Shillelagh, Spare the Dying, Thaumaturgy, True Strike). Canonical mechanics throughout: concentration set only where PHB specifies (Dancing Lights, Guidance, Resistance, True Strike); cantrip damage scaling is automatic via `cantrip_dice_multiplier` (1d8→2d8→3d8→4d8 at caster levels 5/11/17); material components documented per PHB (Thorn Whip, Mending, Message, Resistance, Shillelagh, Dancing Lights, Friends); Shillelagh is the only bonus-action cantrip; Friends' range is `self` per PHB. The spell catalogue now stands at **327 spells** and **all eleven tiers (0–9) are PHB-complete** — the full Player's Handbook spell roster (cantrips through level 9) is now registered, with **no remaining non-canonical spell counts**. +60 backend tests (3944 total). ✅ **COMPLETE**

- **PHB Level-5 Spell Completion (26 spells → level 5 now PHB-complete, 13→39 — ALL TEN LEVELED TIERS 1–9 NOW PHB-COMPLETE)** — Closed the last *leveled* tier with room to grow. After levels 1, 2, 3, 4, 6, 7/8/9 all reached PHB coverage, **level 5 was the final leveled tier below PHB coverage** (was 13; PHB has ~39). Added **all 26 missing PHB 5th-level spells** so **every Player's Handbook 5th-level spell is now registered** (level 5: 13 → 39). The additions cover all resolution paths: **save-spell with damage** (Destructive Wave — Con, 5d8 thunder + prone, +1d8/slot, radiant rider documented; Conjure Volley — Dex, 8d8 piercing, 40-ft cone, +1d8/slot), **save-debuff** (Contagion — Con touch 7-day disease; Modify Memory — Wis concentration; Telekinesis — Str concentration; Planar Binding — Cha concentration 1-hour cast; Geas — Wis 30-day no-concentration 5d10 psychic rider; Seeming — Cha 8-hour no-concentration disguise), and **utility/buff/ritual** (Awaken 8-hour cast, Banishing Smite concentration smite, Circle of Power concentration aura, Commune ritual, Commune with Nature ritual, Conjure Elemental concentration summon, Contact Other Plane ritual self-risk documented, Creation illusion, Dispel Evil and Good concentration abjuration, Dream illusion, Hallow 24-hour cast, Legend Lore, Passwall, Raise Dead 1-hour cast, Reincarnate 1-hour cast, Swift Quiver concentration, Teleportation Circle, Tree Stride concentration). Canonical mechanics throughout (Awaken 8-hour / Planar Binding 1-hour / Hallow 24-hour casts preserved, Geas/Seeming/Contagion no-concentration signatures, ritual tags on Commune/Commune with Nature/Contact Other Plane, Creation & Dream as illusions, Contact Other Plane's caster self-risk documented rather than dice-modeled). The catalogue now stands at **312 spells**, and **ALL TEN LEVELED PHB SPELL TIERS (1-9) are PHB-complete — the full Player's Handbook leveled spell roster is registered.** +89 backend tests. ✅ **COMPLETE**

- **PHB Level-4 Spell Completion (16 spells → level 4 now PHB-complete, 14→30)** — Closed the catalogue's thinnest remaining *leveled* tier relative to the Player's Handbook. After levels 1, 2, 3, 6, 7/8/9 all reached PHB coverage, **level 4 was the last leveled tier below PHB coverage** (was 14; PHB has 30). Added **all 16 missing PHB 4th-level spells** so **every Player's Handbook 4th-level spell is now registered** (level 4: 14 → 30). The additions cover all resolution paths: **save-spell with damage** (Wall of Fire — Dex, 5d8 fire, +1d8/slot; Sickening Radiance — Con, 4d10 radiant, +1d10/slot, exhaustion-on-fail), **save-debuff** (Compulsion — Wis forced movement; Otiluke's Resilient Sphere — Dex encase/restrain), and **utility/buff/ritual** (Arcane Eye 1-min scrying sensor, Conjure Minor Elementals, Control Water, Divination ritual, Fabricate 10-min craft, Giant Insect, Guardian of Faith 8-hour no-concentration, Hallucinatory Terrain 24-hour no-concentration, Leomund's Secret Chest ritual, Locate Creature, Mordenkainen's Faithful Hound 8-hour no-concentration, Stone Shape). Canonical mechanics throughout (Guardian-of-Faith/Hallucinatory-Terrain/Mordenkainen's-Faithful-Hound no-concentration signatures, ritual tags on Divination & Leomund's Secret Chest, +1d8/+1d10 upcast math, effect-in-description for the two special-resolution spells). The catalogue now stands at **286 spells**, and **eight of the ten iconic PHB spell tiers (1, 2, 3, 4, 6, 7, 8, 9) are PHB-complete**. Also eliminated a latent flaky attack-roll test (Flame Blade / Spiritual Weapon crit-flake) via the `_force_d20` pattern — the full suite is now stable across consecutive runs. +59 backend tests. ✅ **COMPLETE**

- **PHB Level-3 Spell Completion (26 spells → level 3 now PHB-complete, 13→39)** — Closed the catalogue's thinnest remaining tier relative to the Player's Handbook. After levels 1, 2, 6, 7/8/9 all reached PHB coverage, **level 3 was the thinnest tier left** (was 13; PHB has ~35). Added **all 26 missing PHB 3rd-level spells** so **every PHB 3rd-level spell is now registered** (level 3: 13 → 39). The additions cover all resolution paths: **save-spell with damage** (Glyph of Warding — Dex, 5d8, +1d8/slot, 1-hour cast trap), **save-debuff** (Bestow Curse — Wis touch; Slow — Wis 40-ft cube; Sleet Storm — Dex cylinder), **attack-roll** (Vampiric Touch — melee spell attack, 3d6 necrotic, heal half, +1d6/slot), **damage zone** (Wind Wall — 3d8 bludgeoning, **no upcast** — the deliberate PHB-canonical exception), and **utility/buff/ritual** (Animate Dead, Beacon of Hope, Clairvoyance ritual+concentration, Conjure Animals, Create Food and Water, Crusader's Mantle Paladin signature, Daylight no-concentration, Elemental Weapon, Feign Death ritual, Gaseous Form, Plant Growth, Protection from Energy, Remove Curse, Sending, Speak with Dead, Speak with Plants, Tiny Hut ritual no-concentration, Tongues no-concentration, Water Breathing ritual no-concentration, Water Walk ritual no-concentration). Canonical mechanics throughout (Daylight/Tongues/Tiny-Hut/Water-Breathing/Water-Walk no-concentration signatures, Clairvoyance ritual+concentration overlap, 1-hour Glyph cast, +1d8/+1d6 upcast math, Wind Wall's flat 3d8 across slots). The catalogue now stands at **270 spells**, and **all seven iconic PHB spell tiers (1, 2, 3, 6, 7, 8, 9) are PHB-complete**. +91 backend tests. ✅ **COMPLETE**

- **PHB Level-2 Spell Completion (19 spells → level 2 now PHB-complete, 36→55)** — Finished the catalogue-wide "PHB completeness" effort at the most-played tier. After the level-2 *expansion* (16→36) landed, level 2 was the only non-PHB-complete tier remaining. Added the **final 19 PHB 2nd-level spells** so **every PHB level-2 spell is now registered** (level 2: 36 → 55). The additions cover all resolution paths: **save-spell with damage** (Cordon of Arrows — Dex, 1d6 piercing, +1d6/slot), **save-debuff** (Gust of Wind — Str push 15 ft; Enthrall — Wis, **no concentration** PHB signature; Zone of Truth — Cha can't-lie), **healing** (Prayer of Healing — 2d8+mod to up to 6 creatures, 10-minute cast, Cleric signature, +1d8/slot), and **utility/buff/ritual** (Alter Self, Animal Messenger ritual, Arcane Lock permanent, Beast Sense ritual+concentration overlap, Continual Flame permanent, Find Steed 10-min Paladin summon, Find Traps, Gentle Repose ritual 10-day, Locate Object concentration, Magic Mouth ritual 1-min, Magic Weapon concentration, Protection from Poison 1-hour no-concentration, Rope Trick concentration, Warding Bond 1-hour no-concentration signature). Canonical mechanics throughout (Enthrall/Warding Bond/Protection-from-Poison no-concentration, Beast Sense ritual+concentration, 10-minute casts preserved, +1d6/+1d8 upcast math). The catalogue now stands at **244 spells**, and **all six iconic PHB spell tiers (1, 2, 6, 7, 8, 9) are PHB-complete**. +68 backend tests. ✅ **COMPLETE**

- **PHB Level-2 Spell Expansion (20 spells → level 2 now 16→36)** — Began the level-2 tier of the catalogue-wide "PHB completeness" effort. After levels 1, 6, 7/8/9, the high-tier enemy registry, and the 5 CR-corrections all landed, **level 2 was the thinnest remaining tier relative to the Player's Handbook** (was 16; PHB has ~54). Added **20 iconic PHB 2nd-level spells** across all resolution paths: **save-for-half damage** (Moonbeam — 2d10 radiant, +1d10/slot), **attack-roll** (Flame Blade — 3d6 fire, +1d6/slot; Spiritual Weapon — 1d8 force, no concentration, +1d8/slot), **direct damage** (Heat Metal — 2d8 fire, +1d8/slot; Spike Growth — 2d4 piercing zone), **save-spell with damage** (Phantasmal Force — Int save, 1d6 psychic), **save-debuff** (Crown of Madness, Calm Emotions, Enlarge/Reduce, Levitate), and **utility/buff/ritual** (Darkness, Silence, Blur, Barkskin, Detect Thoughts, See Invisibility, Darkvision, Knock, Augury, Pass Without Trace). PHB-canonical concentration flags throughout (Spiritual Weapon, Silence, and See Invisibility correctly have **no** concentration); ritual flags on Silence/Darkvision/Augury. The catalogue now stands at **225 spells**.

- **PHB Level-6 Spell Completion (19 spells → level 6 now PHB-complete)** — Closed the catalogue's thinnest tier relative to the Player's Handbook. Levels 1, 7/8/9, the high-tier enemy registry, and the 5 CR-corrections had all landed; **level 6 was the last glaring gap** (was 12; PHB has 31). Added all 19 missing PHB 6th-level spells so **every PHB 6th-level spell is now registered** (level 6: 12 → 31). The additions cover all resolution paths: **damage / save-for-half** (Blade Barrier 6d10 slashing, Otiluke's Freezing Sphere 10d6 cold +1d6/slot, Wall of Thorns 7d8 slashing +1d8/slot — both concentration walls), **save-debuff** (Eyebite Wis concentration with three modes, Magic Jar Cha possession, Mass Suggestion Wis concentration up to 12 targets), and **utility / buff / ritual / summon** (Arcane Gate, Conjure Fey, Contingency, Create Undead, Drawmij's Instant Summons ritual, Find the Path, Guards and Wards, Move Earth, Planar Ally, Programmed Illusion, Transport via Plants, Wind Walk, Word of Recall). Canonical mechanics throughout: schools per PHB p.225-238, concentration on the 7 concentration spells, ritual only on Drawmij's Instant Summons, Move Earth's iconic 2-hour casting time, and Contingency's signature 10-day duration without concentration preserved. Spell registry now: 186 → **205 spells**. +66 backend tests. ✅ **COMPLETE**

- **High-Tier Enemy Registry Gap-Fill (CR 23 populated, 135→145 enemies)** — Closed the last glaring gaps in the enemy registry's CR 11-30 band. **CR 23 was completely empty** (the largest hole between Ancient Red at CR 22 and Ancient Gold at CR 24); now populated with three canonical MM titans: Ancient Blue Dragon, Ancient Silver Dragon, Empyrean. Sparse bands (CR 11/12/13/15/21/22) each gained one canonical MM monster so every high-tier CR band now has ≥2 entries. **Behir** moved CR 6→11 (canonical MM p.25 — its AC/HP were already canonical, only the CR was wrong; same correction pattern as the 5 CR-corrections already shipped). 10 new entries: Remorhaz (CR 11, immune cold), Roc (CR 11), Arcanaloth (CR 12, yugoloth resist nonmagical BPS), Adult White Dragon (CR 13, immune cold), Adult Bronze Dragon (CR 15, immune lightning), Solar (CR 21, immune radiant+poison via Angel trait), Ancient Green Dragon (CR 22, immune poison), Ancient Blue Dragon (CR 23, immune lightning), Ancient Silver Dragon (CR 23, immune cold), Empyrean (CR 23, resist nonmagical BPS). Chromatic & metallic dragons use the existing single-breath-element-immunity convention — the dragon family is now canonical-complete at adult + ancient tiers. CR 18 left intentionally empty (Demilich's 20 HP at CR 18 is too unusual for the simplified template); CRs 25-29 correctly empty (MM has no monsters there, jumping straight to the CR 30 Tarrasque). Registry 135→**145 enemies**. +106 backend tests. ✅ **COMPLETE**

- **PHB Level-1 Spell Completion (16 spells → level 1 now PHB-complete)** — Finished the catalogue-wide "PHB completeness" effort at the most-played tier. Levels 7/8/9 were completed first, then the level-1 *expansion* (+16 iconic spells), and this run adds the **remaining** iconic PHB level-1 spells so **every PHB level-1 spell is now registered** (level 1: 37 → 53). The 16 additions cover all resolution paths: **save-debuff** (Animal Friendship, Compelled Duel), **healing** (Goodberry — ten berries × 1 HP modelled as 10d1 = 10 total healing capacity), and **utility/buff/ritual** (Color Spray, Create or Destroy Water, Detect Evil and Good, Detect Poison and Disease, Expeditious Retreat, Feather Fall, Heroism, Jump, Purify Food and Drink, Silent Image, Tenser's Floating Disk, Unseen Servant, Wrathful Smite). Correct-mechanics decisions throughout: non-standard-resolution spells (Color Spray HP-threshold, Heroism per-turn temp-HP, Wrathful Smite weapon-hit rider, Silent Image Investigation check) use the established "effects-in-description" convention (mirrors Sleep/Hunter's Mark/Hex/Bless/Disguise Self) rather than faking dice; schools are canonical PHB; concentration + ritual flags set per PHB. Spell registry now: 170 → **186 spells**. +55 backend tests. ✅ **COMPLETE**

- **Enemy CR-Correction — 5 Iconic MM Monsters Moved to Canonical CR** — Fixed a **data-correctness bug**: five iconic canonical Monster Manual entries were registered but at the **wrong challenge rating** (their AC/HP already matched the MM stat block, only the `cr` field was wrong). Adult Black Dragon cr=7→**14**, Ice Devil cr=8→**14**, Nalfeshnee cr=10→**14** (hp 212→184), Mummy Lord cr=10→**15**, Lich cr=10→**21**. The wrong CR broke `get_enemies_by_cr()` lookups, understated XP rewards (derived from CR), skewed encounter-difficulty math, and left the **CR 14 / 15 / 21 bands completely empty** despite the monsters "existing" at lower CRs. Moving them populates those bands **without adding any entries** (registry total unchanged at 135; source CR 7/8/10 bands stay well-populated). Each now carries its canonical MM damage immunities (Adult Black Dragon→acid; Ice Devil→cold+poison; Nalfeshnee→fire+poison; Mummy Lord→necrotic+poison; Lich→necrotic+poison). Also resolves a cross-registry contradiction: the legendary-creature registry (`engine/legendary.py`) already documented the Lich at CR 21 while the encounter-builder had it at CR 10 — both now agree. +59 backend tests. ✅ **COMPLETE**

- **DM Function Calling — Cross-Phase Polish: Condition/Exhaustion-Aware Spell Saves** — Closed the last remaining post-roadmap polish item ("advantage/disadvantage on AoE saves"). The DM-resolved spell-save paths (`_combatant_save_total` / `_character_save_total`) previously rolled a plain d20 and ignored the PHB save modifiers the coded `saving_throws` engine already implements — so a paralyzed creature caught in a Fireball could "make" its Dex save, a restrained creature had no Dex-save disadvantage, and an exhausted (3+) creature had no all-save disadvantage. A new `_roll_save_total` helper now mirrors `engine.saving_throws.check_save_auto_fail` / `check_save_disadvantage` (single source of truth): paralyzed/petrified/unconscious creatures auto-fail Str/Dex saves, Restrained → Dex-save disadvantage, Exhaustion 3+ → all-save disadvantage. Combatants read their own `.conditions`/`.exhaustion`; the player's conditions (`game_state["conditions"]`) and exhaustion (`game_state["exhaustion"]`) are threaded into the AoE call site. Also fixed a **latent bug**: combatants always saved at +0 because the ability-name lookup used the full form (`"dexterity"`) against a dict keyed by the short form (`"dex"`); normalization via `_ABILITY_TO_COLUMN.get(raw, raw)` fixes both the lookup and the rule checks. Benefits both single-target `cast_spell` and AoE `cast_spell_aoe`. +22 backend tests. No frontend changes (existing DamageCard/SpellCastCard render the corrected `made_save`/`half_damage` flags unchanged). ✅ **COMPLETE**

- **DM Function Calling — Cross-Phase Polish: Player as AoE Target** — Closed the post-roadmap polish item ("concentration checks triggered by AoE spell damage on the player"). The `cast_spell_aoe` pipeline previously only resolved targets that were encounter combatants — the literal `"player"` target_id was silently dropped, so the player could never take AoE damage through the multi-target path and no concentration check fired (inconsistent with the plain `damage` action). Now `"player"` is a valid `target_ids` entry: a new `_character_save_total` helper rolls the player's save with their *real* save proficiency (ability mod + proficiency bonus), player damage routes to `character.current_hp` (not a combatant), and a real concentration check fires when the player is concentrating — identical to the plain `damage` action's player path. Mixed targets (player + combatants) resolve correctly, and the `DMActionableNarration` docstring now tells the DM that `"player"` is valid for AoE blast-radius coverage (enemy AoE, trap, own miscast). +5 backend tests. No frontend changes (the existing DamageCard/ConcentrationCard render the standard `damage`/`concentration` GameEvents). ✅ **COMPLETE**

- **Iconic PHB Level-1 Spell Expansion (16 spells)** — With levels 7/8/9 now PHB-complete, this run extends the same treatment down to the most-played tier. Added **16 iconic PHB level-1 spells** covering all five effect-resolution paths: **attack-roll** (Inflict Wounds, Ray of Sickness, Witch Bolt), **save-for-half damage** (Hellish Rebuke), **save-debuff** (Tasha's Hideous Laughter, Sanctuary), **healing/temp-HP** (False Life), and **utility/buff** (Alarm, Comprehend Languages, Disguise Self, Find Familiar, Fog Cloud, Identify, Longstrider, Protection from Evil and Good, Speak with Animals). Correct mechanics throughout: melee/ranged spell attacks where applicable, canonical save abilities (Dex/Wis), concentration flags (Fog Cloud, Protection from Evil and Good, Speak with Animals, Tasha's Hideous Laughter, Witch Bolt), ritual tags (Alarm, Comprehend Languages, Find Familiar, Identify, Speak with Animals), and False Life's 1d4+4 temp HP modeled on the healing path with +5/level upcasting. Spell registry now: 154 → **170 spells**, level 1: 21 → 37 (approaching PHB completeness). +55 backend tests. ✅ **COMPLETE**
- **PHB Level 7 & 8 Spell Roster Completion (18/18 each)** — Closed the spell catalogue's second-to-last documented gap (the level-9 tier was already complete). Added **15 iconic PHB spells** — **7 at level 7** (Divine Word, Etherealness, Mordenkainen's Magnificent Mansion, Mordenkainen's Sword, Project Image, Sequester, Symbol) and **8 at level 8** (Animal Shapes, Antipathy/Sympathy, Clone, Control Weather, Demiplane, Glibness, Holy Aura, Telepathy) — so that **every Player's Handbook 7th- and 8th-level spell is now registered** (levels 7 & 8: 11 → 18 each). Correct mechanics throughout: Mordenkainen's Sword uses the attack-roll path (3d10 force), Symbol/Holy Aura/Antipathy-Sympathy/Divine Word are save-debuff spells (correct default saves), and the 10 utility/buff spells carry no dice (effects in description, matching Astral Projection/Gate/Shapechange). Spell registry now: 139 → **154 spells**, every tier ≥12. By level: `{0:14, 1:21, 2:16, 3:13, 4:14, 5:13, 6:12, 7:18, 8:18, 9:15}`. +54 backend tests. ✅ **COMPLETE**
- **High-Tier Enemy Registry Expansion (CR 11-30) + Werewolf Dedup** — The enemy registry previously stopped at CR 10, leaving high-level parties (15-20) with no true solo threats. Added **17 iconic Monster Manual high-tier entries spanning CR 11-30**: Beholder (CR 13), Storm Giant, Rakshasa, Vampire, Adult Blue/Silver/Red/Gold Dragons (CR 16-17), Balor (CR 19), Pit Fiend, Ancient White/Red/Gold Dragons (CR 20-24), and the **Tarrasque (CR 30)** as the new apex entry — each with its canonical damage immunities. Also fixed a duplicate-key data bug: **Werewolf was registered twice** (CR 2 and CR 5, dict-key collision — the CR 5 entry silently overwrote the CR 2 one). Consolidated to a single MM-correct Werewolf (CR 3) retaining the silvered-weapon-bypass immunity, and filled the freed CR 2/CR 5 slots with Saber-Toothed Tiger and Troll. Registry now spans the full CR 0-30 range (116 → 135 enemies). +89 backend tests. ✅ **COMPLETE**
- **Level-9 Spell Roster Completion (PHB 15/15)** — Rounded out the spell catalogue's last thin tier. Added 6 iconic PHB level-9 spells (Astral Projection, Gate, Imprisonment, Shapechange, Storm of Vengeance, Weird) so that **every Player's Handbook 9th-level spell is now registered** (level 9: 9 → 15). Correct mechanics throughout: utility/buff spells (Astral Projection, Gate, Shapechange) modeled like Wall of Force/True Polymorph, Storm of Vengeance uses its signature 10d6 lightning strike (Con save, concentration) with the full escalating-storm text in the description, Weird is 4d8 psychic (Wis save, concentration), and Imprisonment uses the canonical burial Str save with all six prison variants documented. +23 backend tests. ✅ **COMPLETE**
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