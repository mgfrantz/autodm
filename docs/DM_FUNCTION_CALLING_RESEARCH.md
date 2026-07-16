# Design Research: DM Function Calling (Agent-Based Game State Interaction)

> **Status:** Phase 1 IMPLEMENTED ✅ — dice rolling + check prompts are live
> **Created:** 2025-07-13
> **Theme:** Evolve the DM LLM from a pure narrator into a tool-calling agent
> that interacts with coded game mechanics through structured function calls.
> This is an **ongoing research theme** — revisit and expand iteratively.

## The Problem

Currently the DM (via DSPy `DMNarration`) generates free-form text. The coded
game engine (spells, inventory, combat, dice) lives in the backend but is
**decoupled** from LLM narration. This creates a split-brain:

- The LLM says *"you cast Fireball"* — but the spell engine doesn't fire; no
  slot is consumed, no damage is calculated, no save is rolled
- The LLM says *"you roll a 15 on your attack"* — but that number is fabricated
  text, not a real random roll
- The LLM says *"the goblin drops a potion"* — but inventory never updates
- Players can type free-form actions, but the LLM resolution is text-only;
  mechanical outcomes (conditions, HP, loot) require manual UI clicks

**The goal:** Let the DM *call functions* to interact with game state, and let
those function results flow back into the narration. Dice rolls become real.
Spells actually fire. Inventory actually changes.

---

## Proposed Architecture: Tool-Calling DM

### Core Idea
Instead of the current flow:
```
Player Action → DMNarration(prompt) → Narration Text (with fabricated outcomes)
```

Evolve to:
```
Player Action → DM Agent (reasons + calls game functions) → Function Results
             → DMNarration(results as context) → Narration Text (with real outcomes)
```

### Key Functions the DM Should Be Able to Call

#### 1. Dice Rolling (highest priority — most jarring when faked)
```python
roll_dice(notation: str, modifier: int = 0, advantage: bool = False) → RollResult
# e.g. roll_dice("d20", 5, advantage=True) → {rolls: [18, 12], result: 23, ...}
```
- **Never** let the LLM invent a dice result
- DM calls this when narrating a check, attack, save, or damage roll
- The *result* flows into the narration: *"You roll an 18+5=23 — a critical hit!"*

#### 2. Spell Casting
```python
cast_spell(spell_id: str, target_id: str | None, level: int) → CastResult
# Resolves via existing spell engine: slot consumed, damage rolled, save DC set,
# concentration started, conditions applied
```
- DM or player declares a cast → function resolves it mechanically → narration
  describes the outcome using real damage/DC numbers

#### 3. Inventory Operations
```python
give_item(item_id: str, qty: int) → ItemResult
remove_item(item_id: str, qty: int) → ItemResult
# DM awards loot, NPC gives item, item consumed on use
```

#### 4. Combat State
```python
# Already coded in the combat engine — expose to DM as functions
attack(attacker_id, target_id, weapon_id) → AttackResult
apply_condition(target_id, condition, duration) → ConditionResult
deal_damage(target_id, amount, damage_type) → DamageResult
heal(target_id, amount) → HealResult
```

#### 5. Story / World State (lower priority but enables branching narrative)
```python
set_story_flag(key: str, value: bool) → Ack
update_npc_relationship(npc_id: str, delta: int) → Ack
offer_quest(quest_id: str) → Ack
```

---

## DSPy Implementation Approaches to Research

### Option A: DSPy ReAct Agent
DSPy's `ReAct` module gives the LLM a toolset and lets it reason-act-observe in
a loop. The DM would be a `ReAct` agent with game functions as tools:

```python
class DMAgent(dspy.ReAct):
    """DM that can roll dice, cast spells, manage inventory via tools."""
    pass
# tools = [roll_dice, cast_spell, give_item, attack, ...]
```

**Pros:** Native DSPy pattern, automatic tool-selection, iterative reasoning
**Cons:** Multiple LLM calls per turn (reason → act → observe → narrate), higher
latency/cost, harder to stream narration

### Option B: Structured Output Signature (extension of current approach)
Add a `game_actions: list[GameAction]` output field to the narration signature.
The backend parses the actions, resolves them via the engine, then either:
- Re-narrates with results as context (two-pass), or
- Streams narration with action results interpolated

```python
class DMActionableNarration(dspy.Signature):
    """..."""
    context = dspy.InputField()
    player_action = dspy.InputField()
    narration = dspy.OutputField(desc="Story text, referencing real outcomes")
    game_actions = dspy.OutputField(desc="Structured actions to resolve mechanically")
```

**Pros:** Single LLM call, simpler streaming, closer to current architecture
**Cons:** LLM must anticipate all outcomes in one shot; less flexible reasoning

### Option C: Hybrid (RECOMMENDED to research)
1. DM first outputs a **narration plan** with structured `game_actions`
2. Backend resolves actions (dice, spells, inventory) via the engine
3. Backend feeds results back as context for a **final narration pass**

```
Pass 1: Player action → DM reasons → outputs {actions: [roll d20, cast spell]}
Pass 2: Backend resolves → {attack_hit: true, damage: 24} → DM narrates with real numbers
```

**Pros:** Real mechanical outcomes, still streamable (stream pass 2), reasonable
cost (2 calls), keeps narration grounded in actual game state
**Cons:** Slightly more complex pipeline

---

## Open Questions (Research Directions)

1. **Streaming** — how to maintain the streaming TTS narration pipeline when
   function calls need to resolve first? Can we stream pass 2 while pass 1
   is quick/silent?

2. **Player agency** — should the player also trigger function calls (via UI
   buttons for spells/items), or should all resolution flow through the DM?
   Likely both: UI buttons for known actions, DM for narrative resolution.

3. **State visibility** — what game state does the DM need to "see" to make
   good function-call decisions? (character sheet, enemy stats, inventory,
   current conditions, available spells)

4. **DSPy tool definitions** — how to define game functions as DSPy tools?
   `dspy.Tool` wrapping backend engine functions? Typed signatures?

5. **Roll-first vs narrate-first** — should the DM decide what to roll, call the
   roll function, then narrate? Or narrate the attempt, roll, then narrate the
   outcome? (Probably roll-first for mechanical correctness.)

6. **Error handling** — what if the DM calls `cast_spell("fireball")` but the
   character has no spell slots? The function should return an error that the
   DM can narrate ("You reach for the weave, but your reserves are spent...").

7. **Existing engine coverage** — the backend already has robust spell, combat,
   inventory, and condition engines. The work is primarily about *exposing*
   these as DM-callable tools, not building new mechanics.

---

## Migration Path (Conceptual, Not Started)

| Phase | Scope | Deliverable |
|-------|-------|-------------|
| **1. Dice** | DM calls `roll_dice()` for all checks/saves/attacks | Real dice in narration |
| **2. Combat** | DM calls `attack()` / `deal_damage()` | Real combat resolution |
| **3. Spells** | DM calls `cast_spell()` | Real spell mechanics |
| **4. Inventory** | DM calls `give_item()` / `remove_item()` | Real loot/trade |
| **5. Story State** | DM calls `set_story_flag()` / `offer_quest()` | Branching narrative |

Phase 1 (dice) is the highest-value, lowest-risk starting point — it's a single
function with no complex state management, and it immediately makes the game
feel more legitimate.

---

## Game Event UI Layer

> Added 2025-07-13 — Mike wants visible UI elements for dice rolls, checks,
> and other common game events, not just text narration.

### The Vision

When the DM resolves an action via function calls, the results should render as
**structured UI elements** in the game log — not just prose. Players should
*see* the dice, the modifiers, the DC, the outcome. This builds trust ("the
roll was real, not fabricated") and makes the game feel like a virtual tabletop.

### Proposed UI Event Components

#### 1. 🎲 Dice Roll Card
Every time `roll_dice()` fires, render a card inline in the narrative log:
```
┌────────────────────────────────────┐
│  🎲 Perception Check               │
│  [d20] 18 + 3 (WIS) = 21           │
│  DC 15 → ✅ Success                │
└────────────────────────────────────┘
```
- Animated dice tumble before settling on the result
- Shows: die type, raw roll, modifier breakdown (stat + proficiency), total,
  DC (if applicable), pass/fail
- Colour-coded: green ✅ success, red ❌ fail, gold ✦ crit
- Supports advantage/disadvantage (shows both rolls, strikes through the unused)
- Stackable for multi-roll events (e.g. sneak attack: d20 + 6d6)

#### 2. ⚔️ Attack / Damage Card
When combat resolves via `attack()` / `deal_damage()`:
```
┌────────────────────────────────────┐
│  ⚔️ Longsword Attack vs Goblin     │
│  [d20] 17 + 5 = 22 vs AC 15 → HIT │
│  💥 8 slashing damage              │
│  Goblin: 14 → 6 HP                 │
└────────────────────────────────────┘
```

#### 3. 🔮 Spell Cast Card
When `cast_spell()` fires:
```
┌────────────────────────────────────┐
│  🔮 Fireball (3rd-level)           │
│  8d6 fire damage → 31              │
│  Goblin: save DC 15 → ❌ Failed    │
│  Goblin takes 31 damage → ☠️ DEAD  │
│  Slot consumed: 3rd-level (2 left) │
└────────────────────────────────────┘
```

#### 4. 🎒 Inventory Change Notification
When `give_item()` / `remove_item()` fires:
```
┌────────────────────────────────────┐
│  🎒 +1 Health Potion acquired      │
│  From: Goblin loot                 │
└────────────────────────────────────┘
```
- Toast-style or inline; click to inspect item

#### 5. 📊 Condition / Status Applied
When `apply_condition()` fires:
```
┌────────────────────────────────────┐
│  📊 Goblin is now POISONED         │
│  Duration: 1 minute (10 rounds)    │
└────────────────────────────────────┘
```

#### 6. 📜 Check Prompt (DM-initiated)
When the DM calls for a check the player must roll:
```
┌────────────────────────────────────┐
│  📜 The DM calls for a roll!       │
│  "Roll a Perception check"         │
│  [🎲 Roll] button                  │
└────────────────────────────────────┘
```
- Player clicks the button → real dice roll → result card renders
- DM narrates the outcome based on the real result

### Architecture: Event Stream

Function-call results produce structured **game events** that flow to the
frontend alongside (or interleaved with) the narration stream:

```
Backend:
  DM calls roll_dice("d20", modifier=3)
    → GameEvent { type: "dice_roll", label: "Perception", die: "d20",
                   raw: 18, modifier: 3, total: 21, dc: 15, success: true }
    → GameEvent { type: "damage", target: "Goblin", amount: 8, ... }

Frontend:
  NarrationStream ← SSE text chunks (as today)
  GameEventStream ← SSE structured events (new)
    → Rendered as inline UI cards between narration paragraphs
```

This is a **second SSE channel** (or typed events within the existing stream)
that the frontend renders as rich UI components, interleaved with narration.

### Design Principles for Event UI
- **Inline, not modal** — events appear in the narrative log flow, not as popups
- **Trust-building** — always show the raw die, modifiers, and DC so players
  know the roll was real
- **Animated but fast** — dice tumble for ~500ms, don't slow down gameplay
- **Stackable** — multi-die rolls (damage, advantage) show all dice at once
- **Themable** — match the parchment/fantasy aesthetic (gold for crits, blood
  red for failures, arcane purple for spells)
- **Collapsed by default for old events** — recent events expanded, older ones
  collapse to a one-line summary to keep the log readable

### Open Questions (UI)
1. **SSE protocol** — separate channel for events, or typed markers in the
   existing narration stream? (e.g. `[EVENT:dice_roll {...}]` sentinel)
2. **Animation budget** — how much animation is too much? Dice tumble yes, but
   should damage cards "shake" the HP bar? (Probably yes — fun feedback)
3. **Player-initiated vs DM-initiated** — when a player clicks "Cast Fireball"
   in the Spells panel, should the same event UI render? (Yes — unified)
4. **History/replay** — should old event cards be expandable for review during
   long sessions? (Probably yes — collapsed by default)
5. **Mobile layout** — cards need to work on narrow screens (stack vertically)

---

## Updated Migration Path

| Phase | Scope | Backend | Frontend UI |
|-------|-------|---------|-------------|
| **1. Dice** | DM calls `roll_dice()` | Dice engine + event emission | Dice roll card component |
| **1b. Check Prompts** | DM calls for player check | Check request event | Roll button card |
| **2. Combat** | DM calls `attack()` / `deal_damage()` | Combat resolution + events | Attack/damage cards |
| **3. Spells** | DM calls `cast_spell()` | Spell engine + events | Spell cast card |
| **4. Inventory** | DM calls `give_item()` / `remove_item()` | Inventory update + events | Loot notification |
| **5. Conditions** | DM calls `apply_condition()` | Condition engine + events | Status applied card |
| **6. Story State** | DM calls `set_story_flag()` / `offer_quest()` | World state update | Quest/narrative update |

Each phase now has **both** a backend function-calling component and a frontend
UI event component. Phase 1 (dice + check prompts) is the MVP — it delivers the
"real dice" feel and the first visible game event UI.

---

## Phase 1 Implementation Plan: Dice Rolling + Check Prompts

> **Status:** Staged for implementation — ready for dev agent execution
> **Scope:** DM calls `roll_dice()` for all checks/saves/attacks; check prompt
> UI lets the player click to roll when the DM calls for a check
> **Approach:** Option C (Hybrid) — DM outputs structured `game_actions` alongside
> narration; backend resolves via existing dice engine; results flow as
> `GameEvent` objects to frontend for rendering as inline UI cards

### Why Phase 1 First

- **Single function** (`roll_dice`) — no complex state management
- **Existing engine** — `backend/app/engine/dice.py` already has `RollResult`,
  `roll_dice(count, sides, modifier)`, `roll_d20(modifier, advantage, disadvantage)`,
  `ability_modifier()`, `proficiency_bonus()`. No new mechanics needed.
- **Immediate payoff** — real dice in narration + visible dice roll cards
  transforms the game feel from "text adventure" to "virtual tabletop"
- **Foundation** — establishes the GameEvent pipeline that all later phases
  (combat, spells, inventory, conditions) will reuse

---

### Architecture: The GameEvent Pipeline

```
Player Action
    ↓
DM Narration (DSPy) → narration text + game_actions: list[GameAction]
    ↓
Backend resolves each game_action via engine (dice.py)
    ↓
GameEvent objects produced (dice_roll, check_prompt, etc.)
    ↓
SSE stream: chunk events (narration text) → game_event events → done event
    ↓
Frontend renders narration text + inline GameEvent cards
```

**Key design decision:** Game events are emitted **after** narration streaming
completes, before the `done` event. This preserves the existing TTS streaming
pipeline (narration streams first, audio plays) and appends structured events
afterward. The frontend renders them inline below the narration.

For **check prompts** (DM calls for a player roll), the flow is:
1. DM narration includes a `request_check` game action
2. Backend emits a `check_prompt` GameEvent (no roll yet — waiting for player)
3. Frontend renders a `CheckPromptCard` with a 🎲 Roll button
4. Player clicks → `POST /{game_id}/resolve-check` with skill + DC
5. Backend rolls via dice engine → returns `RollResult` as a `dice_roll` GameEvent
6. Frontend renders the `DiceRollCard` with the real result
7. (Optional future: backend triggers a short DM re-narration with the result)

---

### Backend Implementation

#### 1. GameEvent System — `backend/app/engine/game_events.py` (NEW)

A typed event system that all function-call results flow through.

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class GameEventType(str, Enum):
    DICE_ROLL = "dice_roll"
    CHECK_PROMPT = "check_prompt"
    # Future: ATTACK, DAMAGE, SPELL_CAST, LOOT, CONDITION_APPLIED

@dataclass
class GameEvent:
    """A structured game event produced by DM function calls."""
    type: GameEventType
    label: str                    # "Perception Check", "Attack vs Goblin"
    data: dict[str, Any]          # Type-specific payload
    timestamp: str = ""           # ISO format, set at creation

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "label": self.label,
            "data": self.data,
            "timestamp": self.timestamp,
        }

    @classmethod
    def dice_roll(cls, label: str, rolls: list[int], modifier: int,
                  total: int, dc: int | None = None, success: bool | None = None,
                  advantage: bool = False, disadvantage: bool = False) -> "GameEvent":
        return cls(
            type=GameEventType.DICE_ROLL,
            label=label,
            data={
                "rolls": rolls, "modifier": modifier, "total": total,
                "dc": dc, "success": success,
                "advantage": advantage, "disadvantage": disadvantage,
            },
        )

    @classmethod
    def check_prompt(cls, skill: str, dc: int | None = None,
                     reason: str = "") -> "GameEvent":
        return cls(
            type=GameEventType.CHECK_PROMPT,
            label=f"{skill} Check",
            data={"skill": skill, "dc": dc, "reason": reason},
        )
```

**Tests** (`backend/tests/test_game_events.py`):
- `GameEvent` construction + `to_dict()` serialization
- `dice_roll()` factory produces correct type/label/data
- `check_prompt()` factory produces correct type/label/data
- Enum values are strings (JSON-serializable)
- Round-trip: `GameEvent.to_dict()` → JSON → parse → matches original

#### 2. DM-Callable Functions — `backend/app/engine/dm_functions.py` (NEW)

Thin wrappers around the existing dice engine that produce `GameEvent` objects.

```python
"""DM-callable game functions. Each wraps an existing engine function
and returns a GameEvent for the frontend."""
import random
from app.engine.dice import roll_d20, roll_dice as engine_roll_dice, RollResult
from app.engine.game_events import GameEvent

def dm_roll_d20(label: str, modifier: int = 0, advantage: bool = False,
                disadvantage: bool = False, dc: int | None = None) -> GameEvent:
    """Roll a d20 for a check, save, or attack. Returns a dice_roll GameEvent."""
    result = roll_d20(modifier=modifier, advantage=advantage,
                      disadvantage=disadvantage)
    success = None
    if dc is not None:
        success = result.total >= dc
    return GameEvent.dice_roll(
        label=label,
        rolls=result.rolls,
        modifier=result.modifier,
        total=result.total,
        dc=dc,
        success=success,
        advantage=advantage,
        disadvantage=disadvantage,
    )

def dm_roll_dice(label: str, count: int, sides: int, modifier: int = 0) -> GameEvent:
    """Roll arbitrary dice (e.g. 3d6 for damage). Returns a dice_roll GameEvent."""
    result = engine_roll_dice(count, sides, modifier)
    return GameEvent.dice_roll(
        label=label,
        rolls=result.rolls,
        modifier=result.modifier,
        total=result.total,
    )

def dm_request_check(skill: str, dc: int | None = None, reason: str = "") -> GameEvent:
    """The DM calls for a player-initiated check. Returns a check_prompt GameEvent."""
    return GameEvent.check_prompt(skill=skill, dc=dc, reason=reason)
```

**Tests** (`backend/tests/test_dm_functions.py`):
- `dm_roll_d20` produces correct GameEvent with rolls/total/modifier
- `dm_roll_d20` with DC sets `success` correctly
- `dm_roll_d20` with advantage produces 2 rolls
- `dm_roll_dice` produces correct roll count and total
- `dm_request_check` produces check_prompt event
- All functions use real randomness (not fabricated)

#### 3. DSPy Signature: Actionable Narration — `backend/app/llm/dspy_signatures.py` (MODIFY)

Add a new signature that extends `DMNarration` with structured game actions.
Keep the existing `DMNarration` unchanged for backward compatibility; the new
signature is used by the action endpoints (not start).

```python
class DMActionableNarration(dspy.Signature):
    """You are an expert Dungeon Master for a single-player DnD 5e game.

    In addition to narrating the scene, you output structured game_actions
    that the backend will resolve mechanically. This ensures dice rolls,
    checks, and other mechanical outcomes are REAL — not fabricated text.

    Rules for game_actions:
    - Include a roll_dice action whenever the outcome of an action is
      uncertain and warrants a check (attack, save, skill check, damage)
    - Use request_check when YOU (the DM) want the PLAYER to roll
      (e.g., "Roll a Perception check")
    - Do NOT fabricate dice results in the narration text — describe
      the ATTEMPT and let the backend resolve the outcome
    - If an action has a certain outcome, no game_action is needed
    - Reference the action's label in narration (e.g., "You attempt to
      pick the lock...") so the player knows what's being resolved

    Each game_action is a dict with:
    - "function": "roll_dice" | "request_check"
    - "label": short description (e.g., "Perception Check", "Lockpicking")
    - "args": function-specific arguments
      - roll_dice: {"sides": 20, "modifier": 3, "advantage": false,
                     "dc": 15, "disadvantage": false}
      - request_check: {"skill": "Perception", "dc": 15, "reason": "..."}
    """

    situation: str = dspy.InputField(desc="Full scene context: world, character state, recent events, player action")
    narration: str = dspy.OutputField(desc="Vivid narration of the scene. Describe attempts and outcomes — but for uncertain actions, describe the ATTEMPT and let game_actions resolve the result. Do NOT state specific dice numbers.")
    game_actions: list[dict] = dspy.OutputField(desc="Structured actions to resolve mechanically. Empty list if no mechanical resolution needed.")
```

#### 4. DSPy Module — `backend/app/llm/dspy_modules.py` (MODIFY)

Add `DMActionableNarrationModule` following the exact same singleton pattern
as `DMNarrationModule`.

```python
class DMActionableNarrationModule(dspy.Module):
    """Generate DM narration with structured game actions for mechanical resolution."""

    def __init__(self):
        super().__init__()
        self.generate = dspy.ChainOfThought(DMActionableNarration)

    def forward(self, *, situation):
        try:
            return self.generate(situation=situation)
        except Exception as e:
            logger.error(f"DM actionable narration failed: {e}")
            return dspy.Prediction(narration="", game_actions=[])

# Singleton
_dm_actionable_narration: DMActionableNarrationModule | None = None

def get_dm_actionable_narration_module() -> DMActionableNarrationModule:
    global _dm_actionable_narration
    if _dm_actionable_narration is None:
        _dm_actionable_narration = DMActionableNarrationModule()
    return _dm_actionable_narration
```

#### 5. Resolution Pipeline — `backend/app/api/game.py` (MODIFY)

Add a helper that resolves game_actions into GameEvents:

```python
def _resolve_game_actions(game_actions: list[dict]) -> list[GameEvent]:
    """Resolve DM-emitted game_actions into GameEvents via the engine."""
    from app.engine.dm_functions import dm_roll_d20, dm_roll_dice, dm_request_check
    events: list[GameEvent] = []
    for action in game_actions or []:
        func = action.get("function", "")
        label = action.get("label", "Unknown")
        args = action.get("args", {})
        try:
            if func == "roll_dice":
                sides = args.get("sides", 20)
                modifier = args.get("modifier", 0)
                dc = args.get("dc")
                advantage = args.get("advantage", False)
                disadvantage = args.get("disadvantage", False)
                if sides == 20:
                    events.append(dm_roll_d20(label, modifier, advantage,
                                               disadvantage, dc))
                else:
                    count = args.get("count", 1)
                    events.append(dm_roll_dice(label, count, sides, modifier))
            elif func == "request_check":
                events.append(dm_request_check(
                    skill=args.get("skill", "Unknown"),
                    dc=args.get("dc"),
                    reason=args.get("reason", ""),
                ))
        except Exception as e:
            logger.error(f"Failed to resolve game action {func}: {e}")
    return events
```

**Integration into endpoints:**

For the **non-streaming** `/action` endpoint:
1. After DM narration, call `_resolve_game_actions(result.game_actions)`
2. Add `game_events: list[dict]` to the `DMResponse` model
3. Return events alongside narration

For the **streaming** `/action/stream` endpoint:
1. Stream narration as before (chunks)
2. After narration completes, resolve game_actions
3. Emit `game_event` SSE events (one per event) before the `done` event
4. Include events in the `done` payload too (for clients that batch)

```python
# In the streaming event_stream():
# ... after narration collected and persisted ...

game_events = _resolve_game_actions(result.game_actions)
for event in game_events:
    yield _sse({"type": "game_event", **event.to_dict()})

yield _sse({"type": "done", "action_suggestions": action_suggestions,
            "game_events": [e.to_dict() for e in game_events]})
```

**New endpoint for player-initiated check resolution:**
```python
@router.post("/{game_id}/resolve-check")
async def resolve_check(game_id: int, check: CheckRequest, db: Session = Depends(get_db)):
    """Resolve a player-initiated check (from a check_prompt GameEvent)."""
    # Load character to compute modifier
    save = db.query(GameSave).filter(GameSave.id == game_id).first()
    # ... compute modifier from character stats + proficiency ...
    event = dm_roll_d20(label=f"{check.skill} Check", modifier=modifier,
                        dc=check.dc)
    # Store result in game_state for DM context
    return event.to_dict()
```

#### 6. DMResponse Model Update — `backend/app/api/game.py` (MODIFY)

```python
class DMResponse(BaseModel):
    narration: str
    action_suggestions: list[str] = []
    choices: list[str] | None = None
    combat_active: bool = False
    roll_requested: bool = False
    skill_check_resolution: dict[str, Any] = {}
    game_events: list[dict[str, Any]] = []  # NEW — structured game events
```

---

### Frontend Implementation

#### 7. Types — `frontend/src/types/index.ts` (MODIFY)

```typescript
export type GameEventType = 'dice_roll' | 'check_prompt';

export interface GameEvent {
  type: GameEventType;
  label: string;
  data: {
    // dice_roll
    rolls?: number[];
    modifier?: number;
    total?: number;
    dc?: number | null;
    success?: boolean | null;
    advantage?: boolean;
    disadvantage?: boolean;
    // check_prompt
    skill?: string;
    reason?: string;
  };
  timestamp: string;
}

// Add to DMResponse:
//   game_events: GameEvent[];

// Add to StreamEvent:
//   type: 'chunk' | 'done' | 'error' | 'game_event';
//   game_events?: GameEvent[];
```

#### 8. API Client — `frontend/src/stores/api.ts` (MODIFY)

- Update `StreamEvent` type to include `'game_event'`
- Update `streamPlayerAction` to handle `game_event` events via a new
  `onGameEvent` callback
- Add `resolveCheck(gameId, skill, dc)` function for player-initiated rolls

#### 9. Utils — `frontend/src/utils/gameEvents.ts` (NEW)

Pure functions for event formatting (follows the `skillCheckResolution.ts` pattern):

- `formatRollResult(rolls, modifier, total)` → `"18 + 3 = 21"`
- `formatAdvantage(rolls, advantage, disadvantage)` → shows both dice, strikes unused
- `getSuccessLabel(success, dc)` → `"✅ Success"`, `"❌ Failure"`, `""`
- `getRollColor(success)` → Tailwind color class
- `isCritical(roll, sides)` → natural 20 / natural 1 detection
- `summarizeEvent(event)` → one-line summary for aria-labels

**Tests** (`frontend/src/utils/__tests__/gameEvents.test.ts`):
- Roll formatting (with/without modifier, multiple dice)
- Advantage/disadvantage display
- Success/failure labels
- Critical hit/miss detection
- Summary generation

#### 10. Components

##### `frontend/src/components/DiceRollCard.tsx` (NEW)

Renders a single dice roll event as an inline card:
```
┌────────────────────────────────────┐
│  🎲 Perception Check               │
│  [d20] 18 + 3 (WIS) = 21           │
│  DC 15 → ✅ Success                │
└────────────────────────────────────┘
```
- Color-coded: green success, red failure, gold critical
- Advantage: shows both rolls, strikes through the lower
- Purely presentational; uses `gameEvents.ts` utils
- Dismissible (like `SkillCheckResolutionCard`)

**Tests** (`DiceRollCard.test.tsx`): basic roll, with DC, advantage,
critical hit, critical miss, dismiss.

##### `frontend/src/components/CheckPromptCard.tsx` (NEW)

Renders a check prompt with a roll button:
```
┌────────────────────────────────────┐
│  📜 The DM calls for a roll!       │
│  "Roll a Perception check"         │
│  [🎲 Roll]                         │
└────────────────────────────────────┘
```
- Button triggers `resolveCheck()` API call
- On result, replaces itself with a `DiceRollCard`
- Shows DC if known, hidden if not

**Tests** (`CheckPromptCard.test.tsx`): renders prompt, roll button click,
shows result card after roll, error handling.

##### `frontend/src/components/GameEventRenderer.tsx` (NEW)

Dispatches a `GameEvent` to the right component:
- `dice_roll` → `<DiceRollCard />`
- `check_prompt` → `<CheckPromptCard />`
- Unknown types → null (forward-compatible)

#### 11. GameView Integration — `frontend/src/views/GameView.tsx` (MODIFY)

- Add `gameEvents: GameEvent[]` state
- In `handleAction`: capture events from streaming `game_event` SSE events
  and the `done` payload
- Render `<GameEventRenderer />` for each event inline after DM narration
- Clear events on next action (like `skillCheckResolution`)

---

### Test Plan Summary

| Layer | File | Tests |
|-------|------|-------|
| Engine | `test_game_events.py` | 6 — construction, serialization, factories, enum, round-trip |
| Engine | `test_dm_functions.py` | 6 — d20 roll, DC success, advantage, damage dice, check prompt, randomness |
| DSPy | `test_dm_actionable_narration.py` | 5 — signature exists, module init, successful narration+actions, graceful failure, singleton |
| API | `test_game_events_api.py` | 8 — non-streaming returns events, streaming emits game_event SSE, resolve-check endpoint, empty actions, multiple events, error handling, persistence, DMResponse shape |
| Frontend utils | `gameEvents.test.ts` | 8 — roll formatting, advantage, success labels, criticals, summary |
| Frontend components | `DiceRollCard.test.tsx` | 6 — basic, DC, advantage, crit hit, crit miss, dismiss |
| Frontend components | `CheckPromptCard.test.tsx` | 5 — render, roll click, result display, error, DC hidden |
| **Total** | | **~44 new tests** |

### Verification Checklist (for dev agent)
- [ ] `uv run pytest` — all existing tests still pass + new tests green
- [ ] `cd frontend && npx tsc --noEmit` — no type errors
- [ ] `cd frontend && npm run build` — clean build
- [ ] `cd frontend && npm test` — all frontend tests pass
- [ ] `PROGRESS.md` updated with completed work
- [ ] `DESIGN.md` updated if architecture changed
- [ ] Commit with `feat: DM function calling Phase 1 — dice rolling + check prompts`
- [ ] `git push origin develop`

### Key Design Decisions (locked in for Phase 1)
1. **Approach C (Hybrid)** — DM outputs game_actions, backend resolves, events flow to frontend
2. **New signature** (`DMActionableNarration`) rather than modifying `DMNarration` — preserves backward compat for `/start` endpoints
3. **Game events after narration stream** — doesn't break TTS pipeline
4. **GameEvent as typed dataclass** — extensible for future phases (combat, spells, etc.)
5. **Player-initiated checks via new endpoint** — `POST /{game_id}/resolve-check`
6. **Inline UI cards** — not modal, rendered in narrative log flow

### What Phase 1 Does NOT Include (deferred to later phases)
- Combat resolution via DM function calls (Phase 2)
- Spell casting via DM function calls (Phase 3)
- Inventory operations via DM function calls (Phase 4)
- Condition application via DM function calls (Phase 5)
- DM re-narration with resolved results (optional Phase 1 stretch)
- Dice animation (can be added later as progressive enhancement)
- Collapsing old events (can be added when log gets long)

---

## Phase 2 Implementation Plan — Combat Resolution via DM Function Calls

> **Status:** GREEN-LIT by Mike (2026-07-15) — executing. This is a concrete,
> file-level implementation plan for Phase 2, modelled on the Phase 1 plan above.
> The dev agent cron job is now directed to execute it.

### Goal

Extend the DM function-calling system so the DM can emit **combat**
`game_actions` (`attack`, `damage`, `roll_initiative`) that the backend
resolves via the real `Encounter` engine (`backend/app/engine/combat.py`).
Combat outcomes — hit/miss, critical, damage amount, remaining HP — flow as
typed `GameEvent` objects to the frontend and render as inline combat cards,
mirroring the Phase 1 dice/check card UX.

### Why Phase 2 Is Harder Than Phase 1

Phase 1 (dice rolling) was **stateless** — each `roll_dice` call produces an
independent `GameEvent` with no side effects. Combat is **stateful**:

| Aspect | Phase 1 (dice) | Phase 2 (combat) |
|--------|----------------|------------------|
| State | None (pure roll) | `Encounter` in `game_state["combat"]` |
| Side effects | None | HP changes, conditions, death, XP |
| Persistence | N/A | Encounter must be re-serialized & saved |
| Chaining | Independent events | Attack → damage → HP → death cascade |
| DM context | Just the roll label | Must know combatants, HP, turn order |

The core architectural change: `_resolve_game_actions()` must **load the
Encounter from game state, resolve combat actions against it, persist the
mutated encounter back**, and emit GameEvents with the results.

### Architecture: Stateful Resolution

```
DM narration (DMActionableNarration)
    │
    │  game_actions: [{function: "attack", ...}, {function: "damage", ...}]
    ▼
_resolve_game_actions(game_actions, game_state)
    │
    │  1. Separate stateless (roll_dice, request_check) from stateful (attack, damage) actions
    │  2. If stateful actions exist, load Encounter.from_dict(game_state["combat"])
    │  3. Resolve each combat action via the Encounter engine
    │  4. Serialize the mutated encounter back into game_state["combat"]
    │  5. Return (events, updated_game_state)
    ▼
GameEvents flow as SSE → frontend renders AttackCard / DamageCard
```

**Signature change:** `_resolve_game_actions(game_actions, game_state) -> tuple[list[GameEvent], dict]`

### New GameEvent Types (`game_events.py`)

```python
class GameEventType(str, Enum):
    # Phase 1
    DICE_ROLL = "dice_roll"
    CHECK_PROMPT = "check_prompt"
    # Phase 2
    ATTACK = "attack"          # a single attack roll + damage
    DAMAGE = "damage"          # standalone damage (trap, spell AoE, falling)
    INITIATIVE = "initiative"  # initiative roll results
```

New factory classmethods on `GameEvent`:

```python
@classmethod
def attack(cls, label, attacker, target, attack_total, ac, hit, critical,
           critical_miss, damage, damage_type, target_remaining_hp, target_max_hp):
    """Create an ``attack`` event with full to-hit + damage resolution."""

@classmethod
def damage(cls, label, target, amount, damage_type, target_remaining_hp, target_max_hp):
    """Create a ``damage`` event (standalone damage application)."""

@classmethod
def initiative(cls, combatants):
    """Create an ``initiative`` event — combatants is [{name, initiative, side}, ...] in turn order."""
```

### New DM-Callable Functions (`dm_functions.py`)

These take the live `Encounter` object (loaded by the resolver) so they can
call engine methods directly. Each returns a `GameEvent` (or list for
initiative).

```python
def dm_attack(encounter: Encounter, attacker_id: str, target_id: str,
              attack_index: int = 0, advantage: bool = False,
              disadvantage: bool = False) -> GameEvent:
    """Resolve an attack via encounter.resolve_attack().
    Looks up Combatant objects by id, selects the Attack by index,
    and returns an ``attack`` GameEvent with full resolution."""

def dm_apply_damage(encounter: Encounter, target_id: str, amount: int,
                    damage_type: str = "slashing") -> GameEvent:
    """Apply direct damage to a combatant (no to-hit roll).
    Handles death at 0 HP. Returns a ``damage`` GameEvent."""

def dm_roll_initiative(encounter: Encounter) -> GameEvent:
    """Roll initiative for all combatants via encounter.roll_initiative().
    Returns an ``initiative`` GameEvent with the full turn order."""
```

### DSPy Signature Changes (`dspy_signatures.py`)

**Approach: Expand `DMActionableNarration.game_actions`** (recommended)

Add new function types to the existing signature's docstring guidance:

```
- attack: {"function": "attack", "label": "Goblin strikes with scimitar",
           "args": {"attacker_id": "goblin_1", "target_id": "player",
                    "attack_index": 0}}
- damage: {"function": "damage", "label": "Fireball engulfs the goblins",
           "args": {"target_id": "goblin_1", "amount": 28, "damage_type": "fire"}}
```

The combatant IDs (`goblin_1`, `player`, etc.) must be provided to the DM in
the situation prompt (from `game_state["combat"]`). The DM references these
IDs in game_actions so the backend knows who attacks whom.

**Considered & deferred:** A separate `DMCombatNarration` signature with
richer combat outputs (tactical positioning, multi-attack, legendary
actions). Not justified for the initial combat bridge — the expanded
`DMActionableNarration` is sufficient. Revisit in Phase 2.5 if the combat
guidance grows complex.

### Resolution Pipeline Changes (`api/game.py`)

1. **`_resolve_game_actions()` upgrade** — accept `game_state`, load encounter,
   resolve combat actions, persist:
   ```python
   def _resolve_game_actions(
       game_actions: list[dict],
       game_state: dict[str, Any],
   ) -> tuple[list[GameEvent], dict[str, Any]]:
       events: list[GameEvent] = []
       has_combat = any(
           a.get("function") in ("attack", "damage", "roll_initiative")
           for a in game_actions if isinstance(a, dict)
       )
       encounter = None
       if has_combat and game_state.get("combat"):
           try:
               encounter = Encounter.from_dict(game_state["combat"])
           except Exception as e:
               logger.error(f"Failed to load encounter: {e}")
       for action in game_actions or []:
           # Phase 1 actions (stateless) — unchanged
           # Phase 2 actions (stateful) — pass encounter
           ...
       # Persist encounter back if it was loaded
       if encounter is not None:
           game_state["combat"] = encounter.to_dict()
       return events, game_state
   ```

2. **Call sites** — both `/action` and `/action/stream` pass `game_state`
   and use the returned updated state for persistence.

3. **Situation prompt** — include combatant roster (id, name, side, HP, AC)
   in the DM situation context so the DM can reference IDs in game_actions.

4. **Error handling** — missing/malformed encounter → skip combat actions,
   log warning, never crash (same defensive pattern as Phase 1).

### Frontend Components

#### `AttackCard.tsx` (NEW)

```
┌────────────────────────────────────────┐
│  ⚔️ Goblin → Player                    │
│  [d20] 14 + 4 = 18 vs AC 16 → ✅ Hit  │
│  Damage: 7 slashing                    │
│  Player HP: ████████░░ 9/12            │
└────────────────────────────────────────┘
```
- Color-coded: green hit, red miss, gold crit, dark-red crit-miss
- Damage type icon/label
- Target HP bar (current/max)
- Dismissible

#### `DamageCard.tsx` (NEW)

```
┌────────────────────────────────────────┐
│  💥 Fireball hits Goblin               │
│  28 fire damage                        │
│  Goblin HP: ██░░░░░░░░ 4/30            │
└────────────────────────────────────────┘
```

#### `InitiativeCard.tsx` (NEW)

```
┌────────────────────────────────────────┐
│  🎯 Initiative Order                   │
│  1. Player (18)  2. Goblin (12)        │
└────────────────────────────────────────┘
```

#### Updates

- `GameEventRenderer.tsx` — dispatch `attack`, `damage`, `initiative` types
- `gameEvents.ts` — add formatting helpers (`damageTypeColor`, `hpBarData`,
  `attackSummary`, `damageSummary`)
- `types/index.ts` — extend `GameEventData` with combat fields
  (`attacker`, `target`, `attack_total`, `ac`, `hit`, `critical`, `damage`,
  `damage_type`, `target_remaining_hp`, `target_max_hp`, `combatants`)

### File-Level Implementation Plan

| Step | File | Action | Details |
|------|------|--------|---------|
| 1 | `backend/app/engine/game_events.py` | MODIFY | Add `ATTACK`, `DAMAGE`, `INITIATIVE` to `GameEventType` + factory classmethods |
| 2 | `backend/app/engine/dm_functions.py` | MODIFY | Add `dm_attack()`, `dm_apply_damage()`, `dm_roll_initiative()` — wrap `Encounter` engine |
| 3 | `backend/app/llm/dspy_signatures.py` | MODIFY | Expand `DMActionableNarration` docstring with combat action guidance + combatant ID convention |
| 4 | `backend/app/api/game.py` | MODIFY | Upgrade `_resolve_game_actions(game_actions, game_state)` → stateful; add combatant roster to situation prompt; update both `/action` and `/action/stream` call sites |
| 5 | `frontend/src/types/index.ts` | MODIFY | Add combat fields to `GameEventData`; add `'attack' \| 'damage' \| 'initiative'` to `GameEventType` |
| 6 | `frontend/src/utils/gameEvents.ts` | MODIFY | Add `damageTypeColor()`, `hpBarData()`, `attackSummary()`, `damageSummary()` |
| 7 | `frontend/src/components/AttackCard.tsx` | NEW | Inline attack result card with HP bar |
| 8 | `frontend/src/components/DamageCard.tsx` | NEW | Inline damage card with HP bar |
| 9 | `frontend/src/components/InitiativeCard.tsx` | NEW | Initiative order list |
| 10 | `frontend/src/components/GameEventRenderer.tsx` | MODIFY | Dispatch new event types |
| 11 | Tests | NEW | Backend: `test_dm_combat_functions.py`, `test_combat_events_api.py`; Frontend: `AttackCard.test.tsx`, `DamageCard.test.tsx`, `gameEvents.test.ts` additions |

### Test Plan

| Layer | File | Tests |
|-------|------|-------|
| Engine | `test_dm_functions.py` (extend) | `dm_attack` hit, miss, crit, crit-miss; `dm_apply_damage` kills target; `dm_roll_initiative` returns order; unknown combatant IDs handled |
| Engine | `test_game_events.py` (extend) | `attack` factory serialization round-trip; `damage` factory; `initiative` factory; all new types in enum |
| API | `test_combat_events_api.py` (NEW) | `/action` with combat game_actions emits attack events; encounter persisted with updated HP; streaming emits `game_event` SSE for attacks; missing encounter → graceful skip; DMResponse includes combat events |
| Frontend utils | `gameEvents.test.ts` (extend) | `damageTypeColor` (fire/poison/cold/etc.); `hpBarData` (full/half/dead); `attackSummary`; `damageSummary` |
| Frontend components | `AttackCard.test.tsx` (NEW) | hit, miss, crit, crit-miss, HP bar render, dismiss |
| Frontend components | `DamageCard.test.tsx` (NEW) | damage display, HP bar, death indicator, dismiss |
| **Total** | | **~30 new tests** |

### Verification Checklist (for dev agent)
- [ ] `uv run pytest` — all existing tests pass + new combat tests green
- [ ] `cd frontend && npx tsc --noEmit` — no type errors
- [ ] `cd frontend && npm run build` — clean build
- [ ] `cd frontend && npm test` — all frontend tests pass
- [ ] `PROGRESS.md` updated with completed work
- [ ] Commit with `feat: DM function calling Phase 2 — combat resolution`
- [ ] `git push origin develop`

### Key Design Decisions (for Phase 2)
1. **Stateful resolution** — `_resolve_game_actions` now takes and returns `game_state`; combat actions mutate the live Encounter
2. **Encounter lives in `game_state["combat"]`** — no new persistence model; reuses existing serialization
3. **Combatant IDs in DM context** — the situation prompt includes a roster so the DM can reference combatants by stable ID
4. **Combat actions resolved in order** — state changes propagate between chained actions (attack damage applies before the next action)
5. **HP always visible** — every attack/damage event includes `target_remaining_hp` + `target_max_hp` for the HP bar
6. **DM describes intent, engine resolves** — the DM never fabricates attack rolls or damage; the `Encounter.resolve_attack()` does all rolling
7. **Consistent inline UX** — combat cards follow the same dismissible-inline pattern as Phase 1 dice/check cards
8. **Graceful degradation** — missing encounter → skip combat actions, log warning, still return Phase 1 events

### What Phase 2 Does NOT Include (deferred)
- Spell casting via DM function calls (Phase 3)
- Inventory operations via DM function calls (Phase 4)
- Condition application via DM function calls (Phase 5)
- Multi-attack / Extra Attack sequencing (Phase 2.5 — requires action economy tracking)
- Legendary actions / lair actions DM function calls (Phase 2.5)
- Tactical grid / positioning (not planned — narrative combat only)
- DM re-narration with resolved results (Phase 1 stretch, still optional)

### Sub-phase Breakdown (optional, for phased rollout)

If Phase 2 is too large for a single run, it can be split:

- **Phase 2a (core):** `dm_attack` + `AttackCard` — the single most valuable
  combat bridge. Get attacks flowing through the engine with HP tracking.
  (~15 tests)
- **Phase 2b (extensions):** `dm_apply_damage` + `dm_roll_initiative` +
  `DamageCard` + `InitiativeCard`. Adds standalone damage and initiative
  visualization. (~15 tests)

---

## Related Documents
- `docs/DSPY_TEXT_GAME_REFERENCE.md` — DSPy text game tutorial analysis;
  `ActionResolver` signature (structured skill-check resolution) is directly
  relevant to this effort
- `PROGRESS.md` — "Quest detection in dialogue" already implemented some of
  the structured-output groundwork (quest detection fields in narration)
- `DESIGN.md` — current architecture and data models

## Changelog
- 2025-07-13: Initial brainstorm, staged as ongoing research theme by Mike
- 2025-07-13: Added Game Event UI Layer — dice roll cards, check prompts,
  combat/spell/inventory event components, event stream architecture, updated
  migration path to include frontend UI per phase
- 2025-07-14: Added Phase 1 Implementation Plan — concrete file-level plan
  for dice rolling + check prompts (GameEvent system, DM-callable functions,
  DMActionableNarration DSPy signature, resolution pipeline, SSE protocol,
  frontend components). Staged for dev agent execution.
- 2025-07-14: **Phase 1 IMPLEMENTED** — all 14 steps complete. 2617 backend
  + 163 frontend tests passing. DM now outputs structured game_actions; backend
  resolves via real dice engine; GameEvent objects flow as SSE events to
  frontend and render as inline DiceRollCard / CheckPromptCard components.
  Added conftest autouse fixture for LLM call isolation in tests.
- 2025-07-14: **Phase 2 STAGED** — added concrete, file-level implementation
  plan for combat resolution via DM function calls. Key insight: combat is
  stateful (unlike Phase 1's stateless dice rolls), so `_resolve_game_actions`
  must load/mutate/persist the `Encounter` from `game_state["combat"]`. Plan
  covers new GameEvent types (`ATTACK`, `DAMAGE`, `INITIATIVE`), DM-callable
  combat functions wrapping `Encounter.resolve_attack()`, DSPy signature
  expansion for combat game_actions, stateful resolution pipeline, and 3 new
  frontend cards (AttackCard, DamageCard, InitiativeCard). ~30 new tests.
  Includes optional sub-phase breakdown (2a: attacks, 2b: damage+initiative).
- 2025-07-15: **Phase 2 GREEN-LIT by Mike** — dev agent cron directive updated
  to execute the Phase 2 plan. Status changed from STAGED to executing.
