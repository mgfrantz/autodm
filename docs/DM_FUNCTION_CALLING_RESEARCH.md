# Design Research: DM Function Calling (Agent-Based Game State Interaction)

> **Status:** Phase 1 IMPLEMENTED ✅ — dice rolling + check prompts are live
> Phase 2 IMPLEMENTED ✅ — combat resolution (attack/damage/initiative) is live
> Phase 3 IMPLEMENTED ✅ — spell casting (cast_spell, dual-state coupling) is live
> Phase 4 IMPLEMENTED ✅ — inventory operations (give_item/remove_item/equip_item/use_item) are live
> Phase 5 IMPLEMENTED ✅ — condition application (apply_condition/remove_condition) is live
> Phase 3.5 IMPLEMENTED ✅ — concentration tracking (reactive hooks + Con-save checks) is live
> Phase 3.5b IMPLEMENTED ✅ — AoE multi-target spell resolution (cast_spell_aoe) is live
> UI polish IMPLEMENTED ✅ — dice tumble (~480ms), HP-bar shake, collapsed-by-default old event cards are live (roadmap item #7)
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
- **Animated but fast** — dice tumble for ~500ms, don't slow down gameplay ✅ DONE (dice tumble ~480ms via `useDiceTumble`, `prefers-reduced-motion`-aware)
- **Stackable** — multi-die rolls (damage, advantage) show all dice at once
- **Themable** — match the parchment/fantasy aesthetic (gold for crits, blood
  red for failures, arcane purple for spells)
- **Collapsed by default for old events** — recent events expanded, older ones
  collapse to a one-line summary to keep the log readable ✅ DONE (last 2 stay expanded; click to re-expand; stable per-event uid tracking)

### Animation Budget (resolved)
- **Dice tumble** — YES, implemented: the raw die value flickers through random
  faces for ~480ms then settles (`utils/diceTumble.ts` + `useDiceTumble` hook).
  Opt-in via an `animate` prop so tests render the settled value deterministically.
- **HP-bar shake** — YES, implemented: the HP bar in AttackCard (on a damaging
  hit) and DamageCard plays a one-shot `animate-shake` on mount. Both honour the
  global `prefers-reduced-motion` rule in `index.css`.

### Open Questions (UI)
1. **SSE protocol** — separate channel for events, or typed markers in the
   existing narration stream? (e.g. `[EVENT:dice_roll {...}]` sentinel)
2. **Animation budget** — ~~how much animation is too much? Dice tumble yes, but
   should damage cards "shake" the HP bar?~~ ✅ RESOLVED — dice tumble (~480ms)
   AND HP-bar shake both shipped; both gated by `prefers-reduced-motion`.
3. **Player-initiated vs DM-initiated** — when a player clicks "Cast Fireball"
   in the Spells panel, should the same event UI render? (Yes — unified)
4. **History/replay** — ~~should old event cards be expandable for review during
   long sessions?~~ ✅ RESOLVED — older event cards collapse to a one-line
   summary by default and re-expand on click (collapsed-by-default polish).
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

## Phase 3 Implementation Plan — Spell Casting via DM Function Calls

> **Status:** ✅ IMPLEMENTED (2026-07-16). The dev agent shipped the full 9-step
> plan — `dm_cast_spell()`, `SPELL_CAST` GameEvent, dual-state resolution
> (Spellbook slot + Encounter HP), `_available_spells_for_dm` roster,
> `SpellCastCard` component, and +33 backend / +28 frontend tests. See the
> "COMPLETED: DM Function Calling — Phase 3" section in `PROGRESS.md`.

### Goal

Extend the DM function-calling system so the DM can emit **spell-casting**
`game_actions` (`cast_spell`) that the backend resolves via the real spell
engine (`backend/app/engine/spells.py`). When a player or NPC casts a spell —
*Fire Bolt*, *Cure Wounds*, *Fireball* — the backend consumes the real spell
slot, rolls the real damage/healing via the existing engine, and the outcome
flows as a typed `SPELL_CAST` `GameEvent` to the frontend, rendering as an
inline **SpellCastCard** that mirrors the Phase 1/2 card UX.

The DM describes the *intent* ("the wizard hurls a Fire Bolt at the goblin");
the engine resolves the *mechanics* (slot consumed, attack roll, save DC,
damage). The DM never fabricates spell outcomes.

### Why Phase 3 Is Harder Than Phase 2

Phase 2 (combat) was stateful against **one** store (`game_state["combat"]`).
Spell casting touches **two** stateful stores:

| Aspect | Phase 2 (combat) | Phase 3 (spells) |
|--------|------------------|------------------|
| Slot state | Encounter in `game_state["combat"]` | Spellbook on **`character.spells`** (JSON column) |
| Source of truth | `game_state["combat"]` | `character.spells` (also read/written by the Spells panel + `/cast` endpoint) |
| Cross-store coupling | None | A combat spell's damage must also reduce combatant HP in the Encounter |
| DM context needed | Combatant roster | Available spells (name, level, school) + remaining slots |
| Persistence target | `game_state["combat"]` → `GameSave.game_state` | `character.spells` → `Character.spells` |

The core architectural change: `_resolve_game_actions()` must now also receive
the **Character** object (the Spellbook's home), cast through `Spellbook.cast()`
(which consumes a slot), and persist the mutated Spellbook back to
`character.spells`. When the spell deals damage to a combatant in an active
Encounter, that damage also flows into `game_state["combat"]`.

### Architecture: Dual-State Resolution

```
DM narration (DMActionableNarration)
    │
    │  game_actions: [{function: "cast_spell", args: {spell_id, target_id, slot_level}}]
    ▼
_resolve_game_actions(game_actions, game_state, character)
    │
    │  1. Separate stateless (roll_dice, request_check),
    │     combat (attack, damage, roll_initiative), and spell (cast_spell) actions
    │  2. If spell actions exist, load Spellbook.from_dict(json.loads(character.spells))
    │  3. For each cast_spell action:
    │     a. Derive caster_mod from the character's casting ability
    │     b. If a target_id is given and an Encounter is loaded, look up
    │        target_ac (attack spells) / target_save_total (save spells)
    │     c. Call spellbook.cast(spell_id, slot_level, caster_mod, ...) → CastOutcome
    │     d. If the spell dealt damage AND the target is an Encounter combatant,
    │        apply the damage to the Encounter (combatant.take_damage) + emit
    │        a follow-up DAMAGE event
    │  4. Persist mutated Spellbook back to character.spells
    │  5. Persist mutated Encounter back to game_state["combat"]
    ▼
GameEvents flow as SSE → frontend renders SpellCastCard (+ optional DamageCard)
```

**Signature change:** `_resolve_game_actions(game_actions, game_state, character=None) -> tuple[list[GameEvent], dict[str, Any]]`

The caller (`/action` and `/action/stream`) already has the `character` in
scope (`character = save.character`). After resolution, it persists
`character.spells` (a JSON column) the same way it already persists
`game_state`.

### Existing Engine (no new mechanics — pure exposure)

The spell engine is already comprehensive and unit-tested:

- **`Spell`** dataclass — name, level, school, `requires_attack_roll`,
  `save_ability`, damage/healing dice, upcasting (`at_higher_levels_dice`),
  cantrip scaling. `to_dict()` / `from_dict()` for serialization.
- **`SPELL_REGISTRY` + `get_spell(spell_id)`** — lookup by id
  (e.g. `fire_bolt`) or name (e.g. `Fire Bolt`). 108 spells registered.
- **`Spellbook`** — per-character book with slot accounting:
  - `cast(spell_id, slot_level, caster_mod, target_ac, target_save_total, active_conditions)` →
    `CastOutcome` (consumes a slot, resolves the effect via `resolve_spell_effect`)
  - `spell_attack_bonus`, `spell_save_dc` (derived from level + casting ability)
  - `available_slots(level)`, `slots_overview()`, `can_cast(spell_id)`
  - `to_dict()` / `from_dict()` — persistence (the source of truth is
    `character.spells` JSON)
- **`SpellEffectResult`** — outcome of effect resolution: `rolled_attack`,
  `hit`, `made_save`, `damage`, `healing`, `damage_type`, `half_damage`
- **`resolve_spell_effect(...)`** — handles attack-roll spells (d20 vs AC),
  saving-throw spells (half damage on save), direct-damage (Magic Missile),
  healing, and utility spells.

**The work is purely *exposing* `Spellbook.cast()` as a DM-callable function
and threading the result into the GameEvent pipeline — no new spell mechanics.**

### New GameEvent Type (`game_events.py`)

```python
class GameEventType(str, Enum):
    # Phase 1
    DICE_ROLL = "dice_roll"
    CHECK_PROMPT = "check_prompt"
    # Phase 2
    ATTACK = "attack"
    DAMAGE = "damage"
    INITIATIVE = "initiative"
    # Phase 3
    SPELL_CAST = "spell_cast"
```

New factory classmethod on `GameEvent`:

```python
@classmethod
def spell_cast(
    cls,
    label: str,
    spell_name: str,
    spell_id: str,
    level: int,                 # base spell level (0 = cantrip)
    school: str,
    slot_level: int | None,     # slot expended (None for cantrips / failed cast)
    success: bool,              # whether the cast succeeded
    attack_total: int | None,   # attack-roll spells only
    hit: bool | None,           # attack-roll spells only
    made_save: bool | None,     # saving-throw spells only
    save_dc: int | None,        # save spells
    save_ability: str | None,   # save spells ("dex", "wis", ...)
    damage: int,                # resolved damage (0 if none)
    healing: int,               # resolved healing (0 if none)
    damage_type: str,
    half_damage: bool,          # saved for half
    target: str,                # target name (or "" if self/utility)
    target_remaining_hp: int | None,   # if target is an encounter combatant
    target_max_hp: int | None,         # if target is an encounter combatant
    message: str,               # failure reason, or short outcome description
    slots_remaining: list[dict] | None = None,  # [{level, available}, ...] post-cast
) -> "GameEvent":
    """Create a ``spell_cast`` event with full resolution + HP tracking."""
```

### New DM-Callable Function (`dm_functions.py`)

```python
def dm_cast_spell(
    spellbook: Spellbook,
    spell_id: str,
    slot_level: int | None = None,
    caster_mod: int = 0,
    target_ac: int | None = None,
    target_save_total: int | None = None,
    active_conditions: list[str] | None = None,
) -> GameEvent:
    """Resolve a spell cast via spellbook.cast().

    Looks up the spell in the registry, consumes a slot, rolls the real
    damage/healing/attack, and returns a ``spell_cast`` GameEvent. If the cast
    fails (no slots, not known, component-blocked), returns a spell_cast event
    with ``success=False`` and a human-readable ``message``.

    Args:
        spellbook: The character's live Spellbook (consumes a slot on success).
        spell_id: Spell id or name (e.g. "fire_bolt", "Cure Wounds").
        slot_level: Desired slot level for upcasting (None = auto/lowest).
        caster_mod: Casting-ability modifier (INT/WIS/CHA).
        target_ac: Target AC for attack-roll spells.
        target_save_total: Target's save total for saving-throw spells.
        active_conditions: Caster's conditions (may block V/S components).

    Returns:
        A ``spell_cast`` GameEvent.
    """
```

### DSPy Signature Changes (`dspy_signatures.py`)

Expand `DMActionableNarration` docstring with spell-casting guidance:

```
- cast_spell: {"function": "cast_spell", "label": "Wizard casts Fire Bolt",
               "args": {"spell_id": "fire_bolt", "target_id": "goblin_1",
                        "slot_level": null}}
  Use for ANY spell cast — cantrip or leveled. The backend consumes the real
  slot, rolls the real attack/damage/save. Reference a real spell_id from the
  available-spells roster provided in the situation context.
  - slot_level: null (auto/lowest) or an int for upcasting.
  - target_id: a combatant id from the roster (for attack/save/damage spells),
    or omit for self/utility spells (Cure Wounds on self, Mage Armor, etc.).
```

The situation prompt must include the player's **available spells roster**
(name, id, level, school, one-line effect) + **remaining slots** per level, so
the DM references real spell IDs. (Mirrors the Phase 2 combatant roster.)

### Resolution Pipeline Changes (`api/game.py`)

1. **`_resolve_game_actions()` upgrade** — accept `character`:
   ```python
   def _resolve_game_actions(
       game_actions: list[dict],
       game_state: dict[str, Any],
       character: "Character | None" = None,
   ) -> tuple[list[GameEvent], dict[str, Any]]:
       # ... existing stateless + combat handling ...
       # NEW: spell handling
       has_spell = any(a.get("function") == "cast_spell" ...)
       spellbook = None
       if has_spell and character is not None:
           spellbook = _load_spellbook(character)   # reuse api/spells.py helper
       for action in ...:
           if func == "cast_spell":
               # derive caster_mod from character's casting ability
               # resolve target_ac/target_save_total from encounter if target_id given
               # dm_cast_spell(spellbook, ...) → event
               # if spell dealt damage to an encounter combatant → also apply + DAMAGE event
       if spellbook is not None:
           _save_spellbook(character, spellbook)    # persist back to character.spells
       if encounter is not None:
           game_state["combat"] = encounter.to_dict()
       return events, game_state
   ```
   The caller persists `character` (the `spells` column) via `db.commit()`.

2. **Call sites** — both `/action` and `/action/stream` pass `character`.

3. **Situation prompt** — add an available-spells roster (only for casters) so
   the DM can emit real `cast_spell` actions. Helper:
   `_available_spells_for_dm(character) -> str`.

4. **Error handling** — non-caster / unknown spell / no slots / component-blocked
   → `cast_spell` event with `success=False` + message (never crash). Same
   defensive pattern as Phase 1/2.

### Frontend Components

#### `SpellCastCard.tsx` (NEW)

```
┌────────────────────────────────────────────┐
│  🔮 Fire Bolt (Evocation cantrip)          │
│  [d20] 16 + 5 = 21 vs AC 14 → ✅ Hit      │
│  💥 10 fire damage                         │
│  Goblin HP: ████████░░ 14/22               │
└────────────────────────────────────────────┘
```
- School-themed accent colors (evocation=orange, necromancy=dark-green,
  abjuration=blue, illusion=purple, etc.) — reuse `damageTypeColor()` pattern
- Three resolution modes: attack-roll (d20 vs AC), saving-throw (DC + made/failed),
  auto (Magic Missile) / healing / utility
- HP bar when target is a combatant (reuse `hpBarData()`)
- Failed cast: muted card showing the reason ("No spell slots available")
- Dismissible (same pattern as Phase 1/2 cards)

#### Updates
- `GameEventRenderer.tsx` — dispatch `spell_cast` type
- `gameEvents.ts` — add `spellSchoolColor()`, `spellCastSummary()`
- `types/index.ts` — extend `GameEventData` with spell fields + add
  `'spell_cast'` to `GameEventType`

### File-Level Implementation Plan

| Step | File | Action | Details |
|------|------|--------|---------|
| 1 | `backend/app/engine/game_events.py` | MODIFY | Add `SPELL_CAST` to enum + `spell_cast()` factory classmethod |
| 2 | `backend/app/engine/dm_functions.py` | MODIFY | Add `dm_cast_spell()` wrapping `Spellbook.cast()` |
| 3 | `backend/app/llm/dspy_signatures.py` | MODIFY | Expand `DMActionableNarration` docstring with `cast_spell` guidance |
| 4 | `backend/app/api/game.py` | MODIFY | Upgrade `_resolve_game_actions(..., character=None)`; add `_available_spells_for_dm()` roster helper; thread `character` through both endpoints; spell-damage-to-encounter coupling |
| 5 | `frontend/src/types/index.ts` | MODIFY | Add spell fields to `GameEventData`; add `'spell_cast'` to `GameEventType` |
| 6 | `frontend/src/utils/gameEvents.ts` | MODIFY | Add `spellSchoolColor()`, `spellCastSummary()` |
| 7 | `frontend/src/components/SpellCastCard.tsx` | NEW | Inline spell cast card (attack/save/auto/healing modes + HP bar) |
| 8 | `frontend/src/components/GameEventRenderer.tsx` | MODIFY | Dispatch `spell_cast` event type |
| 9 | Tests | NEW/EXTEND | Backend: `test_dm_spell_functions.py`, `test_spell_events_api.py`; Frontend: `SpellCastCard.test.tsx`, `gameEvents.test.ts` additions |

### Test Plan

| Layer | File | Tests |
|-------|------|-------|
| Engine | `test_dm_functions.py` (extend) | `dm_cast_spell` attack-roll hit/miss; save spell half-damage; healing spell; auto-damage (Magic Missile); cantrip (no slot consumed); failed cast (no slots / unknown / component-blocked) |
| Engine | `test_game_events.py` (extend) | `spell_cast` factory serialization round-trip; enum value |
| API | `test_spell_events_api.py` (NEW) | `/action` with `cast_spell` game_action emits SPELL_CAST event; slot persisted to `character.spells`; spell damage reduces encounter combatant HP (+ DAMAGE event); streaming emits `game_event` SSE; non-caster → graceful skip; failed cast event has `success=False` |
| Frontend utils | `gameEvents.test.ts` (extend) | `spellSchoolColor` (8 schools); `spellCastSummary` (hit/miss/save/heal/fail) |
| Frontend components | `SpellCastCard.test.tsx` (NEW) | attack hit, attack miss, save half-damage, healing, failed cast, HP bar render, dismiss |
| **Total** | | **~25 new tests** |

### Verification Checklist (for dev agent)
- [ ] `uv run pytest` — all existing tests pass + new spell tests green
- [ ] `cd frontend && npx tsc --noEmit` — no type errors
- [ ] `cd frontend && npm run build` — clean build
- [ ] `cd frontend && npm test` — all frontend tests pass
- [ ] PROGRESS.md updated with completed work
- [ ] Commit with `feat: DM function calling Phase 3 — spell casting`
- [ ] `git push origin develop`

### Key Design Decisions (for Phase 3)
1. **Spellbook source of truth = `character.spells`** — not duplicated into `game_state`. The resolver loads/saves via the same `_load_spellbook` / `_save_spellbook` helpers the Spells API uses, keeping a single source of truth.
2. **`_resolve_game_actions` gains a `character` param** — needed to reach the Spellbook. Backward-compatible default `None`.
3. **Dual-state coupling** — a damage-dealing spell targeting an encounter combatant reduces both the Spellbook (slot) and the Encounter (HP). Resolved in order: cast → apply damage to encounter → emit SPELL_CAST + DAMAGE events.
4. **Casting mod derived, not DM-supplied** — the DM emits only `spell_id` + `target_id` + optional `slot_level`; the backend computes `caster_mod`, `spell_save_dc`, `target_ac`/`target_save_total` from real character + encounter data.
5. **DM never fabricates spell outcomes** — attack rolls, saves, damage, and healing all come from the engine.
6. **Failed casts are first-class events** — no slots / unknown spell / component-blocked render as a muted card with the reason, so the player sees *why* the cast failed.
7. **Graceful degradation** — non-caster / missing character → skip spell actions, log warning, still return Phase 1/2 events.
8. **Consistent inline UX** — SpellCastCard follows the same dismissible-inline pattern as the DiceRollCard / AttackCard.

### What Phase 3 Does NOT Include (deferred)
- Inventory operations via DM function calls (Phase 4)
- Condition application via DM function calls (Phase 5)
- Concentration tracking through the DM pipeline (the spell engine supports it; DM-callable exposure is a Phase 3.5 stretch)
- AoE spell resolution against multiple combatants in one call (Phase 3.5 — initial scope is single-target; multi-target can iterate over `cast_spell` actions or a future `cast_spell_aoe` function)
- Spell scroll / wand charge consumption (out of scope)

### Sub-phase Breakdown (optional, for phased rollout)

If Phase 3 is too large for a single run, it can be split:

- **Phase 3a (core):** `dm_cast_spell` + `SpellCastCard` for single-target
  attack/save/healing spells, slot consumption, `character.spells` persistence.
  The single most valuable spell bridge. (~15 tests)
- **Phase 3b (combat coupling):** spell-damage-to-encounter coupling (reduce
  combatant HP + follow-up DAMAGE event), available-spells roster in DM prompt,
  multi-target iteration. (~10 tests)

---

## Phase 4 Implementation Plan: Inventory Operations

> **Status:** IMPLEMENTED ✅ by Mike green-light (2026-07-17) — all 9 steps complete
> **Scope:** DM emits `give_item` / `remove_item` / `equip_item` / `use_item`
> game_actions; backend resolves via the real `Inventory` engine; results flow
> as `LOOT` GameEvent objects to inline `LootCard` components
> **Approach:** Same Option C (Hybrid) as Phases 1-3

### Why Phase 4 Now

- **All prior phases shipped** — dice, combat, and spells are all live with
  2723 backend + 234 frontend tests passing.
- **Inventory engine is robust** — `backend/app/engine/inventory.py` already has
  `Inventory.add_item()`, `remove_item()`, `equip_item()`, `unequip_item()`,
  `use_item()` with stacking, equip-slot exclusivity, consumable charges, and
  AC recalculation via the equipment engine. No new mechanics needed.
- **Inventory API is the persistence blueprint** — `_load_inventory()` /
  `_save_inventory()` / `_recalc_armor_class()` in `api/inventory.py` show
  exactly how to load from `character.inventory`, mutate, and persist.
- **Closes the loot loop** — the DM can narrate "the goblin drops a Health
  Potion" and the inventory *actually changes*, instead of requiring a manual
  UI click.

### The architectural insight (vs Phase 3)

Phase 3 (spells) was **dual-state**: Spellbook (`character.spells`) + Encounter
(`game_state["combat"]`). Phase 4 (inventory) is **single-state** but has two
**coupling side-effects**:

| Coupling | Trigger | Effect |
|----------|---------|--------|
| **AC recalc** | equip/unequip armor or shield | `character.armor_class` updated via `_recalc_armor_class()` |
| **HP heal** | use_item on a healing potion | `character.current_hp` increased (2d4+2) |

So `_resolve_game_actions()` loads the `Inventory` via `_load_inventory(character)`,
mutates it, applies side-effects (AC recalc / HP heal), and persists back via
`_save_inventory(character, inventory)` — same pattern as Phase 3's spellbook,
just with a different store and two coupling hooks instead of one.

### Game actions the DM can emit

| Action | Args | Effect |
|--------|------|--------|
| `give_item` | `{item_name, item_type, quantity, ...details}` | Create Item, add to inventory (stacking) |
| `remove_item` | `{item_id, quantity}` | Remove from inventory (item_id from INVENTORY_ROSTER) |
| `equip_item` | `{item_id}` | Equip existing item + AC recalc |
| `use_item` | `{item_id}` | Use consumable + apply effects (healing etc.) |

**`give_item` creates new items** — the DM provides enough detail to construct
an `Item` (name, type, quantity, and optionally damage_dice for weapons,
armor_type/bonus for armor, effect for potions). For potions, the `description`
field doubles as the effect description.

**`remove_item` / `equip_item` / `use_item` reference existing items** — the DM
uses `item_id` from the `INVENTORY_ROSTER` injected into the situation prompt
(mirrors `_combatant_roster_for_dm` / `_available_spells_for_dm`).

### Backend Implementation (Steps 1-4)

#### 1. `backend/app/engine/game_events.py` — Add LOOT event type

Add `LOOT = "loot"` to `GameEventType` enum + `loot()` factory classmethod:

```python
LOOT = "loot"

@classmethod
def loot(
    cls,
    label: str,
    operation: str,          # "gained" | "removed" | "used" | "equipped"
    item_name: str,
    item_type: str,          # weapon, armor, potion, scroll, misc, quest
    item_id: str,
    quantity: int = 1,
    rarity: str = "common",
    value: int = 0,
    source: str = "",        # "Goblin loot", "Merchant trade", etc.
    # Operation-specific fields
    healing: int | None = None,         # used: healing amount
    ac_after: int | None = None,        # equipped: new AC
    uses_remaining: int | None = None,  # used: charges left on item
    success: bool = True,
    message: str = "",      # failure reason if success=False
) -> "GameEvent":
```

Uncomment the `LOOT` line in the "Future phases" comment block.

#### 2. `backend/app/engine/dm_functions.py` — Add inventory functions

Add a `# --- Phase 4: Inventory functions ---` section with:

- **`dm_give_item(inventory, item_name, item_type, quantity=1, ...)`** —
  constructs an `Item` from the DM-supplied details (name, type, rarity, value,
  damage_dice for weapons, armor_type/bonus for armor, uses for consumables),
  calls `inventory.add_item()`, returns a `LOOT` event with `operation="gained"`.
  Handles item_type normalisation (case-insensitive), default rarity/value.

- **`dm_remove_item(inventory, item_id, quantity=1)`** — calls
  `inventory.remove_item()`, returns `LOOT` event with `operation="removed"`.
  Failed removal (item not found) → `success=False` event with message.

- **`dm_equip_item(inventory, item_id)`** — calls `inventory.equip_item()`,
  returns `LOOT` event with `operation="equipped"`. Includes `ac_after` field
  (caller fills in after AC recalc). Failed equip → `success=False`.

- **`dm_use_item(inventory, item_id)`** — calls `inventory.use_item()`, returns
  `LOOT` event with `operation="used"`. Includes `uses_remaining` and `healing`
  fields (caller fills in after applying healing effect). Failed use →
  `success=False` with the engine message.

All functions accept a live `Inventory` object (loaded by the caller from
`character.inventory`) and never crash — defensive try/except like `dm_cast_spell`.

#### 3. `backend/app/llm/dspy_signatures.py` — Expand DMActionableNarration

Add inventory guidance to the docstring:

```
- For INVENTORY operations:
  - Use give_item when the player ACQUIRES an item (loot, reward, purchase,
    gift). Args: {"item_name": "Health Potion", "item_type": "potion",
                  "quantity": 2}
  - Use remove_item when the player LOSES an item (consumed, stolen, given
    away, sacrificed). Reference the item_id from INVENTORY_ROSTER.
    Args: {"item_id": "...", "quantity": 1}
  - Use equip_item when the player or NPC equips gear (auto-equip found
    armor, don found weapon). Reference item_id from INVENTORY_ROSTER.
    Args: {"item_id": "..."}
  - Use use_item when a consumable is used (drink potion, read scroll).
    Reference item_id from INVENTORY_ROSTER.
    Args: {"item_id": "..."}
  - The DM should ONLY give items that make narrative sense. Don't spawn
    legendary items from thin air. Follow the scene's logic.
  - Available items are shown under INVENTORY_ROSTER (id, name, type, qty).
  - Optional give_item details: rarity, value, damage_dice (weapons),
    armor_type/bonus (armor), description (potions = effect text).
```

Add the new functions to the `function` enum and `args` schema:

```
"function": "roll_dice" | "request_check" | "attack" | "damage" |
            "roll_initiative" | "cast_spell" |
            "give_item" | "remove_item" | "equip_item" | "use_item"
```

#### 4. `backend/app/api/game.py` — Inventory resolution in `_resolve_game_actions`

- **Inventory loading**: When any inventory action (`give_item`, `remove_item`,
  `equip_item`, `use_item`) is present and a character is available, load via
  `_load_inventory(character)` (from `api.inventory`).

- **Inventory roster for DM**: Add `_inventory_for_dm(character)` helper that
  returns a formatted string listing current inventory items (id, name, type,
  qty, equipped, rarity). Empty if no inventory. Inject into the situation
  prompt alongside `_combatant_roster_for_dm` and `_available_spells_for_dm`.

- **Resolution**: Dispatch each inventory action:
  - `give_item`: call `dm_give_item(inventory, ...)` → LOOT event
  - `remove_item`: call `dm_remove_item(inventory, item_id, qty)` → LOOT event
  - `equip_item`: call `dm_equip_item(inventory, item_id)` → LOOT event,
    then `_recalc_armor_class(character, inventory)` → fill `ac_after`
  - `use_item`: call `dm_use_item(inventory, item_id)` → LOOT event,
    then apply healing if item name contains "healing" (2d4+2 like the API),
    fill `healing` field

- **Persistence**: After resolving all actions, if inventory was loaded and
  mutated, call `_save_inventory(character, inventory)`. The caller's existing
  `db.commit()` persists it.

- **Graceful degradation**: Missing character or inventory load failure → skip
  inventory actions, log warning, still return Phase 1-3 events (same pattern
  as spell casting graceful degradation).

### Frontend (Steps 5-8)

#### 5. `frontend/src/types/index.ts` — Add loot event type

- Add `'loot'` to `GameEventType`
- Add loot fields to `GameEventData`: `operation`, `item_name`, `item_type`,
  `item_id`, `quantity`, `rarity`, `value`, `source`, `healing`, `ac_after`,
  `uses_remaining`, `success`, `message`

#### 6. `frontend/src/utils/gameEvents.ts` — Loot utilities

- `itemRarityColor(rarity)` — Tailwind classes per rarity tier:
  common=gray, uncommon=green, rare=blue, very_rare=purple, legendary=gold
- `lootSummary(event)` — one-liner per operation:
  - gained: "+2 Health Potion acquired"
  - removed: "1 Longsword consumed"
  - equipped: "Equipped Chain Mail"
  - used: "Used Health Potion (+8 HP healed)"
  - failed: "Failed: item not found"
- `lootIcon(item_type)` — emoji per type: ⚔️ weapon, 🛡️ armor, 🧪 potion,
  📜 scroll, 📦 misc, 🗝️ quest
- Update `summarizeEvent()` to dispatch `loot`

#### 7. `frontend/src/components/LootCard.tsx` (NEW)

Inline inventory change card:
- Rarity-themed accent colours (gray→gold gradient by rarity)
- Operation icons: 🎁 gained, ❌ removed, ⚔️ equipped, 🧪 used
- Quantity badge for stackable items
- Healing indicator (green +N HP) when `healing` is present
- AC indicator (🛡️ AC 16) when `ac_after` is present
- Failed operation: muted card with reason
- Source label ("From: Goblin loot") when present
- Dismissible (same pattern as DiceRollCard / SpellCastCard)

#### 8. `frontend/src/components/GameEventRenderer.tsx`

Dispatch `loot` event type to `LootCard`.

### Tests (Step 9) — ~25 backend, ~15 frontend

#### Backend tests

**`backend/tests/test_dm_inventory_functions.py`** (NEW, ~14 tests):
- `dm_give_item` creates Item, adds to inventory, returns LOOT event with
  `operation="gained"`
- `dm_give_item` with weapon details (damage_dice), armor details (armor_type),
  potion details (uses)
- `dm_give_item` stacks consumables
- `dm_remove_item` reduces quantity, returns LOOT event with `operation="removed"`
- `dm_remove_item` failure (item not found) → `success=False`
- `dm_equip_item` equips weapon, returns LOOT event with `operation="equipped"`
- `dm_equip_item` equips armor (body + shield exclusivity)
- `dm_equip_item` failure (not equippable / not found) → `success=False`
- `dm_use_item` consumes charge, returns LOOT event with `operation="used"`
- `dm_use_item` on depleted item → `success=False`
- `dm_use_item` on non-consumable → `success=False`

**`backend/tests/test_inventory_events_api.py`** (NEW, ~11 tests):
- `/action` with `give_item` game_action → LOOT event emitted + item persisted
  to `character.inventory`
- `give_item` with quantity > 1 → stacking
- `give_item` with weapon/armor details → proper Item construction
- `/action` with `remove_item` → item removed from `character.inventory`
- `/action` with `equip_item` → item equipped + AC recalculated
- `/action` with `use_item` on healing potion → HP increased + healing in event
- `/action` streaming emits `game_event` SSE for loot
- INVENTORY_ROSTER present in DM situation prompt
- Missing character → graceful skip + warning
- Failed give_item (invalid item_type) → `success=False` event

**`backend/tests/test_game_events.py`** (extended):
- `loot` factory serialization round-trip
- `LOOT` enum value
- Default fields

#### Frontend tests

**`frontend/src/components/__tests__/LootCard.test.tsx`** (NEW, ~10 tests):
- Gained item card (rarity colors, quantity badge)
- Removed item card (muted styling)
- Equipped item card (AC indicator)
- Used item card (healing indicator)
- Failed operation (muted card with reason)
- Different item types (weapon, armor, potion icons)
- Rarity tier color variations
- Dismissible
- No-callback render
- Source label display

**`frontend/src/utils/__tests__/gameEvents.test.ts`** (extended):
- `itemRarityColor` (5 rarity tiers)
- `lootSummary` (5 operations + failure)
- `lootIcon` (6 item types)

### Key Architectural Decisions

- **Inventory source of truth = `character.inventory`** — not duplicated into
  game_state. Load/save via `_load_inventory` / `_save_inventory` (same helpers
  the Inventory API uses).
- **`_resolve_game_actions` loads inventory** when inventory actions present —
  backward-compatible (no change to existing action types).
- **AC coupling** — equip/unequip triggers `_recalc_armor_class()` (same as the
  Inventory API `equip_item` / `unequip_item` endpoints).
- **HP coupling** — `use_item` on healing potions increases `character.current_hp`
  (same 2d4+2 formula as the Inventory API `use_item` endpoint).
- **DM never fabricates inventory** — the DM describes the narrative ("the goblin
  drops a glowing potion") and emits a `give_item` action; the engine creates
  the real Item and persists it.
- **give_item creates new items** — DM provides construction details; the engine
  normalises and validates.
- **remove/equip/use reference existing item_ids** — from the INVENTORY_ROSTER
  in the DM situation prompt.
- **Failed operations are first-class events** — render as a muted LootCard with
  the reason.
- **Graceful degradation** — missing character / inventory load failure → skip
  inventory actions, log warning, still return Phase 1-3 events.
- **Consistent inline UX** — LootCard follows the same dismissible-inline pattern
  as DiceRollCard / AttackCard / SpellCastCard.

### What Phase 4 Does NOT Include (deferred)

- Condition application via DM function calls (Phase 5)
- Loot engine integration (DM emits `give_item` with specific items; generating
  random loot from CR/loot tables is a Phase 4.5 stretch)
- Trading / economy via DM function calls (shop transactions stay via the Shop API)
- Attunement via DM function calls (the attunement engine exists; DM-callable
  exposure is a future enhancement)

### Sub-phase Breakdown (optional, for phased rollout)

If Phase 4 is too large for a single run, it can be split:

- **Phase 4a (core):** `dm_give_item` + `dm_remove_item` + `LootCard` for
  gained/removed operations. The single most valuable inventory bridge —
  closes the loot loop. (~12 tests)
- **Phase 4b (equip + use):** `dm_equip_item` (AC coupling) + `dm_use_item`
  (HP healing coupling). (~13 tests)

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
- 2026-07-16: **Phase 2 IMPLEMENTED** — all 12 steps complete (backend +
  frontend). 2690 backend + 206 frontend tests passing. DM emits
  attack/damage/roll_initiative game_actions; backend resolves via the real
  Encounter engine; results flow as ATTACK/DAMAGE/INITIATIVE GameEvents and
  render as inline AttackCard/DamageCard/InitiativeCard components.
- 2026-07-16: **Phase 3 GREEN-LIT by Mike** — dev agent cron directive updated
  to execute the Phase 3 spell casting plan. Status changed from STAGED to
  EXECUTING. The DM will gain `cast_spell` game_actions resolved via the real
  Spellbook engine.
- 2026-07-16: **Phase 3 STAGED** — added concrete, file-level implementation
  plan for spell casting via DM function calls. Key insight: unlike Phase 2's
  single-state Encounter, spell casting touches **two** stateful stores — the
  Spellbook on `character.spells` (slot consumption) AND the Encounter in
  `game_state["combat"]` (combat spell damage). `_resolve_game_actions` gains a
  `character` param to reach the Spellbook. Plan covers new SPELL_CAST
  GameEvent type, `dm_cast_spell()` wrapping `Spellbook.cast()`, DSPy signature
  expansion, dual-state resolution pipeline, and a SpellCastCard component.
  ~25 new tests. Includes optional sub-phase breakdown (3a: core single-target,
  3b: combat coupling). Awaiting Mike's green-light.
- 2026-07-16: **Phase 3 IMPLEMENTED** — all 9 steps complete (backend +
  frontend). 2723 backend + 234 frontend tests passing. The DM now emits
  `cast_spell` game_actions resolved via the real `Spellbook.cast()` engine.
  Key delivery: `SPELL_CAST` GameEvent type + `spell_cast()` factory,
  `dm_cast_spell()` DM-callable function, dual-state resolution in
  `_resolve_game_actions(character=...)` (Spellbook slot consumption +
  Encounter HP coupling with follow-up DAMAGE event), `_available_spells_for_dm`
  roster injected into the DM situation prompt, `SpellCastCard` component
  (school-themed colors, attack/save/auto/heal modes, HP bar, failed-cast
  rendering), and `GameEventRenderer` dispatch. +33 backend / +28 frontend
  tests.

- 2026-07-17: **Phase 4 GREEN-LIT by Mike** — dev agent cron directive updated
  to execute the Phase 4 inventory operations plan. Status changed from STAGED
  to EXECUTING. The DM will gain `give_item` / `remove_item` / `equip_item` /
  `use_item` game_actions resolved via the real `Inventory` engine.
- 2026-07-17: **Phase 4 STAGED** — added concrete, file-level implementation
  plan for inventory operations via DM function calls. Key insight: Phase 4 is
  single-state (`character.inventory`) but has two coupling side-effects (AC
  recalc on equip, HP heal on use). `_resolve_game_actions` loads the Inventory
  via `_load_inventory(character)` and persists via `_save_inventory`. Plan
  covers new `LOOT` GameEvent type, 4 DM-callable inventory functions wrapping
  `Inventory.add_item()` / `remove_item()` / `equip_item()` / `use_item()`,
  DSPy signature expansion, `_inventory_for_dm` roster helper, and a
  `LootCard` component (rarity-themed colors, operation icons, AC/healing
  indicators). ~25 backend / ~15 frontend tests. Awaiting Mike's green-light.
- 2026-07-17: **Phase 4 IMPLEMENTED** — all 9 steps complete (backend +
  frontend). 2763 backend + 261 frontend tests passing. The DM now emits
  `give_item` / `remove_item` / `equip_item` / `use_item` game_actions
  resolved via the real `Inventory` engine. Key delivery: `LOOT` GameEvent
  type + `loot()` factory, 4 DM-callable inventory functions (`dm_give_item`,
  `dm_remove_item`, `dm_equip_item`, `dm_use_item`) with item-type/rarity/
  armor/dice normalisation, single-state resolution in
  `_resolve_game_actions` (load via `_load_inventory`, mutate, persist via
  `_save_inventory`) with AC recalc on equip (`_recalc_armor_class`) and HP
  heal on use_item (2d4+2), `_inventory_for_dm` roster injected into the DM
  situation prompt, `LootCard` component (rarity-themed colors, operation
  icons, quantity/value/healing/AC/uses indicators, failed-operation card,
  source provenance), and `GameEventRenderer` dispatch. +40 backend /
  +27 frontend tests.

- 2026-07-17: **Phase 5 STAGED** — added concrete, file-level implementation
  plan for condition application via DM function calls. Key insight: Phase 5 is
  **dual-state** like Phase 3, but the duality is *player vs combatant* rather
  than *spellbook vs encounter*. Player conditions live in
  `game_state["conditions"]` (flat name list) — not on a combatant object — so
  a lightweight `_PlayerConditionState` adapter bridges `game_state` to the
  conditions engine, with a parallel `game_state["condition_durations"]` dict
  for timed conditions. Combatant conditions live on the Combatant object.
  Plan covers new `CONDITION_APPLIED` GameEvent type, `dm_apply_condition` /
  `dm_remove_condition` wrapping the conditions engine, DSPy signature
  expansion, dual-state resolution pipeline, `_conditions_for_dm` roster, and a
  `ConditionCard` component (severity-themed colors, duration indicator, effect
  flags). ~25 backend / ~15 frontend tests.

## Phase 5 Implementation Plan: Condition Application

> **Status:** GREEN-LIT by standing green-light (2026-07-17) — EXECUTING
> **Scope:** DM emits `apply_condition` / `remove_condition` game_actions;
> backend resolves via the real conditions engine (`conditions.py`);
> results flow as `CONDITION_APPLIED` GameEvent objects to inline
> `ConditionCard` components
> **Approach:** Same Option C (Hybrid) as Phases 1-4

### Why Phase 5 Now

- **All prior phases shipped** — dice, combat, spells, and inventory are all
  live with 2763 backend + 261 frontend tests passing.
- **Conditions engine is robust** — `backend/app/engine/conditions.py` already
  defines all 14 core DnD 5e conditions (blinded, charmed, deafened, frightened,
  grappled, incapacitated, invisible, paralyzed, petrified, poisoned, prone,
  restrained, stunned, unconscious) with `apply_condition()`,
  `remove_condition()`, `tick_conditions()`, `has_condition()`,
  `get_condition_info()`, and full combat-effect query helpers (advantage,
  disadvantage, incapacitation, auto-crit, damage resistance, speed zero). No
  new mechanics needed.
- **Combatants already support conditions** — the `Combatant` class has
  `conditions` + `condition_durations` fields, with `apply_condition()` /
  `remove_condition()` / `has_condition()` methods that delegate to the engine.
  The existing combat API (`POST /combat/conditions/{combatant_id}`) already
  applies/removes conditions on encounter combatants.
- **Player conditions are already stored** — `game_state["conditions"]` holds
  the player's active conditions (read by the social, rest, and spell systems).
- **Closes the status-effect loop** — the DM can narrate "the ghoul's claws
  rend your flesh — you are paralyzed" and the condition *actually applies*,
  with mechanical effects in subsequent combat, instead of being flavor text.

### The architectural insight (vs Phase 4)

Phase 4 (inventory) was **single-state** (`character.inventory`). Phase 5
(conditions) is **dual-state** like Phase 3 — but the duality is **player vs
combatant**, not spellbook vs encounter:

| Store | Holds | Source of truth |
|-------|-------|-----------------|
| Player | the character's conditions | `game_state["conditions"]` (flat name list) |
| Combatant | a monster's/NPC's conditions | Combatant object inside `game_state["combat"]` |

The conditions engine operates on any "combatant-like" object exposing
`.conditions` (list[str]) and `.condition_durations` (dict[str,int]). The
Combatant class already satisfies this. But the player's conditions live in
`game_state` as a bare name list — **not** on a combatant object. So a
lightweight `_PlayerConditionState` adapter bridges `game_state` to the engine:

```python
class _PlayerConditionState:
    def __init__(self, name, conditions, condition_durations):
        self.name = name
        self.conditions = conditions           # list[str] from game_state
        self.condition_durations = condition_durations  # dict from game_state
```

After mutation, the adapter's `.conditions` and `.condition_durations` sync
back to `game_state["conditions"]` / `game_state["condition_durations"]`. A
new parallel `game_state["condition_durations"]` dict stores timed durations
for the player (the historical `game_state["conditions"]` only stored names;
backward-compatible since existing readers treat it as a flat list).

### Game actions the DM can emit

| Action | Args | Effect |
|--------|------|--------|
| `apply_condition` | `{condition, target, duration?}` | Apply a condition to player or combatant |
| `remove_condition` | `{condition, target}` | Remove a condition from player or combatant |

- **`condition`** — one of the 14 core DnD 5e conditions (case-insensitive).
  Unknown conditions → `success=False` event with a message.
- **`target`** — `"player"` (or omitted → defaults to player) or a combatant ID
  from the `COMBATANT_ROSTER`. When combat is active and the target resolves to
  a combatant, the condition is applied to the Combatant object (and persists in
  the encounter). Otherwise it applies to the player.
- **`duration`** — optional rounds (e.g. `3` = "for 3 rounds"). Omitted →
  permanent until removed.

### Backend Implementation (Steps 1-4)

#### 1. `backend/app/engine/game_events.py` — Add CONDITION_APPLIED event type

Add `CONDITION_APPLIED = "condition_applied"` to `GameEventType` + factory:

```python
CONDITION_APPLIED = "condition_applied"

@classmethod
def condition_applied(
    cls,
    label: str,
    operation: str,          # "applied" | "removed"
    condition: str,          # e.g. "poisoned"
    target: str,             # display name ("Player", "Goblin")
    target_type: str = "player",  # "player" | "combatant"
    duration: int | None = None,  # rounds remaining (None = permanent)
    description: str = "",   # mechanical effect text
    success: bool = True,
    message: str = "",       # failure reason
) -> "GameEvent":
```

#### 2. `backend/app/engine/dm_functions.py` — Add condition functions

Add a `# --- Phase 5: Condition functions ---` section:

- **`dm_apply_condition(target, condition, duration=None)`** — wraps
  `conditions.apply_condition(target, condition, duration)`. Returns a
  `CONDITION_APPLIED` event with `operation="applied"`. Invalid condition →
  `success=False`. Includes `get_condition_info()` description.

- **`dm_remove_condition(target, condition)`** — wraps
  `conditions.remove_condition(target, condition)`. Returns a
  `CONDITION_APPLIED` event with `operation="removed"`. Not present →
  `success=False`.

Both accept any "combatant-like" object (Combatant or `_PlayerConditionState`)
and never crash — defensive try/except. A `_norm_condition()` helper
normalises DM-supplied condition strings (lowercase, spaces→underscores, plurals).

#### 3. `backend/app/llm/dspy_signatures.py` — Expand DMActionableNarration

Add condition guidance to the docstring: `apply_condition` /
`remove_condition` with `{condition, target, duration?}`. List the 14 valid
conditions. Target is `"player"` or a combatant ID. Add both functions to the
function list + args schema.

#### 4. `backend/app/api/game.py` — Resolution pipeline + roster helper

- Add `_CONDITION_ACTIONS = ("apply_condition", "remove_condition")`.
- Add `_PlayerConditionState` adapter class.
- Add `_conditions_for_dm(game_state, character)` roster helper — lists the
  player's active conditions + combatant conditions (if combat active), so the
  DM knows what to remove. Mirrors the other roster helpers.
- In `_resolve_game_actions`: detect condition actions; for player, build the
  adapter from game_state, mutate, sync back; for combatant, find the combatant
  in the encounter. The encounter persistence (existing) handles combatant
  conditions; the game_state persistence (existing) handles player conditions.

### Frontend (Steps 5-8)

#### 5. `types/index.ts` — Add condition_applied type + fields

Add `'condition_applied'` to `GameEventType`. Add to `GameEventData`:
`condition`, `target`, `target_type`, `duration`, `description`.

#### 6. `utils/gameEvents.ts` — Condition helpers

Add `conditionColor()` (severity tier), `conditionIcon()` (per condition),
`conditionSummary()` (one-liner). Update `summarizeEvent()`.

#### 7. `components/ConditionCard.tsx` (NEW)

Inline condition card: condition name + icon, target name, operation badge
(applied/removed), duration indicator (e.g. "3 rounds" / "permanent"),
mechanical effect description, severity color theming. Failed → muted card.

#### 8. `components/GameEventRenderer.tsx` — Dispatch condition_applied.

### Test Plan (Step 9) — ~25 backend, ~15 frontend

- **`test_dm_condition_functions.py`** (NEW) — `dm_apply_condition` (valid,
  invalid, duration, already-present, description), `dm_remove_condition`
  (present, absent), event serialization.
- **`test_condition_events_api.py`** (NEW) — `/action` with `apply_condition`
  on player (event + game_state persistence), on combatant (event + encounter
  persistence), `remove_condition` on both, failed (invalid condition),
  streaming emits events + persists.
- **`test_game_events.py`** (extended) — `condition_applied` factory round-trip.
- **`gameEvents.test.ts`** (extended) — `conditionColor`, `conditionIcon`,
  `conditionSummary`, `summarizeEvent` dispatch.
- **`ConditionCard.test.tsx`** (NEW) — applied, removed, duration, failed,
  dismiss.

---

## Phase 3.5 Implementation Plan: Concentration Tracking + AoE

> **Status:** IMPLEMENTED ✅ (2026-07-17) — concentration tracking is live
> **Scope:** Wire the fully-built `concentration.py` engine into the DM
> function-calling pipeline, and lay groundwork for multi-target (AoE) spell
> resolution.
> **Approach:** Same Option C (Hybrid) as Phases 1-5

### Why Phase 3.5 Now

- **The concentration engine already exists** —
  `backend/app/engine/concentration.py` implements the full PHB p.203-204 rules:
  `ConcentrationState` (spell_name/spell_id/is_concentrating), `start_concentration()`,
  `end_concentration()`, `check_concentration()` (Con save vs DC 10 or half-damage),
  `calculate_concentration_dc()`, `should_break_concentration()` (incapacitating
  conditions), `can_concentrate()`. **But `game.py` has ZERO concentration
  references** — the engine is completely disconnected from the DM pipeline.
- **`Spell.concentration` flag exists but is unused during casting** — the
  spell registry marks ~40 concentration spells (Shield, Hold Person, Bless,
  Hunter's Mark, Faerie Fire, Invisibility, Haste, etc.), but `Spellbook.cast()`
  never starts/stops concentration.
- **All prior phases shipped** — Phases 1-5 are live with 2811 backend + 293
  frontend tests. The pattern is established.
- **Highest-impact gap** — concentration is the spell system's most visible
  mechanical omission: a wizard casts Hold Person, but nothing tracks that
  they're concentrating, nothing breaks it when they take damage, and casting
  a second concentration spell doesn't end the first.

### The architectural insight (vs Phase 5)

Phase 5 (conditions) was **dual-state**: player conditions in `game_state` +
combatant conditions on the `Combatant` object. Phase 3.5 (concentration) is
**single-state** — only the *player caster* concentrates (monsters/NPCs cast
through the same spell engine but the DM pipeline tracks player concentration).
The state lives in one store:

| Store | Holds | Source of truth |
|-------|-------|-----------------|
| `game_state["concentration"]` | the player's concentration state | `ConcentrationState.to_dict()` |

Concentration is **reactive** — it changes as a *side-effect* of other actions,
not (only) as a direct action. This is the key difference from Phases 1-5,
where each phase added direct game_actions. Phase 3.5 adds coupling hooks into
*existing* action handlers:

| Trigger | Hook location | Effect |
|---------|---------------|--------|
| Cast a concentration spell | `cast_spell` handler (after success) | Start concentration; auto-end previous |
| Incapacitating condition on player | `apply_condition` handler (after success) | Break concentration (`should_break_concentration`) |
| Player takes damage | `damage` handler (new player-target path) | Con-save concentration check |
| DM ends concentration | new `end_concentration` action | End concentration |

### Sub-phase split

- **Phase 3.5a — Concentration Tracking (this implementation):** all four
  triggers above, `CONCENTRATION` GameEvent, `ConcentrationCard`, player-damage
  path, concentration roster in DM prompt. Self-contained and shippable.
- **Phase 3.5b — AoE Spell Resolution (future):** multi-target `cast_spell`
  with `target_ids: [...]`, per-target save rolls, multiple DAMAGE events,
  single slot consumption. Deferred — concentration is the higher-value piece.

### Game actions the DM can emit

| Action | Args | Effect |
|--------|------|--------|
| `end_concentration` | `{reason?}` | Player voluntarily drops / spell ends naturally |

Concentration also changes **reactively** (no direct action) via the cast /
condition / damage hooks.

### Backend Implementation

#### 1. `backend/app/engine/game_events.py` — Add CONCENTRATION event

Add `CONCENTRATION = "concentration"` to `GameEventType`. Add factory:

```python
@classmethod
def concentration(
    cls,
    label: str,
    operation: str,          # "started" | "broken" | "ended" | "check_passed" | "check_failed"
    spell_name: str = "",
    spell_id: str = "",
    reason: str = "",        # why it changed
    # Concentration-check fields (operation in check_passed/check_failed):
    damage_taken: int | None = None,
    concentration_dc: int | None = None,
    roll_total: int | None = None,
    success: bool = True,    # False only if the operation itself failed
    message: str = "",
) -> "GameEvent":
```

#### 2. `backend/app/engine/dm_functions.py` — Add concentration functions

Add a `# --- Phase 3.5: Concentration functions ---` section:

- **`dm_start_concentration(spell_name, spell_id)`** — wraps
  `concentration.start_concentration()`. Returns a `CONCENTRATION` event
  (`operation="started"`).
- **`dm_end_concentration(reason="")`** — wraps `concentration.end_concentration()`.
  Returns a `CONCENTRATION` event (`operation="ended"`).
- **`dm_check_concentration(state, damage_taken, con_score, prof_bonus, con_proficient)`** —
  wraps `concentration.check_concentration()`. Returns a `CONCENTRATION` event
  (`operation="check_passed"` or `"check_failed"`). On failure, concentration
  is lost — the caller clears `game_state["concentration"]`.

All never crash — defensive try/except.

#### 3. `backend/app/llm/dspy_signatures.py` — Expand DMActionableNarration

Add concentration guidance: the DM should emit `end_concentration` when a
player drops concentration or a spell ends naturally. Note that concentration
starts/breaks automatically (no action needed) — the engine handles it. Add
`end_concentration` to the function list + args schema.

#### 4. `backend/app/api/game.py` — Resolution hooks + roster

- Add `_CONCENTRATION_ACTION = "end_concentration"`.
- Add `_concentration_for_dm(game_state, character)` roster helper — shows the
  player's active concentration (spell name/id) so the DM knows what's active.
  Mirrors `_conditions_for_dm`. Injected into both `/action` and `/action/stream`
  situation prompts.
- **cast_spell hook:** after a successful cast of a concentration spell
  (`spell.concentration == True`):
  - If `game_state["concentration"]` shows active concentration → end it (emit
    `CONCENTRATION` event `operation="ended"`, reason "Replaced by new spell").
  - Start new concentration → persist `game_state["concentration"]`.
  - Augment the spell_cast event with `concentration_started: True`.
- **apply_condition hook:** after applying an incapacitating condition
  (stunned/paralyzed/petrified/unconscious) to the **player** target:
  - If concentrating → `should_break_concentration()` → break it. Emit
    `CONCENTRATION` event `operation="broken"`, reason = condition name.
    Clear `game_state["concentration"]`.
- **damage hook (new player-target path):** when a `damage` action targets
  `"player"` (target_id == "player" or no encounter):
  - Apply damage to `character.current_hp` (min 0).
  - Emit a `DAMAGE` event with the player's HP (player as target).
  - If concentrating → fire `dm_check_concentration()`. On failure, emit
    `CONCENTRATION` event `operation="check_failed"` + clear concentration.
    On success, emit `CONCENTRATION` event `operation="check_passed"`.
- **end_concentration action:** clear `game_state["concentration"]`, emit
  `CONCENTRATION` event `operation="ended"`.

### Frontend (Steps 5-8)

#### 5. `types/index.ts` — Add concentration type + fields

Add `'concentration'` to `GameEventType`. Add to `GameEventData`:
`operation`, `spell_name`, `spell_id`, `reason`, `damage_taken`,
`concentration_dc`, `roll_total`.

#### 6. `utils/gameEvents.ts` — Concentration helpers

Add `concentrationColor()` (by operation: started=indigo, broken=red,
ended=stone, check_passed=green, check_failed=amber), `concentrationIcon()`
(🧠 for concentration, ✅/❌ for checks), `concentrationSummary()` (one-liner
per operation). Update `summarizeEvent()`.

#### 7. `components/ConcentrationCard.tsx` (NEW)

Inline concentration card:
- Operation-themed accent colours
- Spell name + 🧠 icon
- Operation badge (✨ Started / 💥 Broken / 🛑 Ended / ✅ Concentration Held / ⚠️ Concentration Lost)
- For checks: damage taken, DC, roll total, Con save breakdown
- Reason text (why concentration changed)
- Dismissible (same pattern as all other cards)

#### 8. `components/GameEventRenderer.tsx` — Dispatch concentration.

### Test Plan (Step 9) — ~30 backend, ~20 frontend

- **`test_dm_concentration_functions.py`** (NEW) — `dm_start_concentration`,
  `dm_end_concentration`, `dm_check_concentration` (pass/fail/no-concentration/
  zero-damage), event serialization.
- **`test_concentration_events_api.py`** (NEW) — `/action` with cast_spell of a
  concentration spell (starts concentration + persists to game_state), casting a
  second concentration spell (auto-ends first), apply_condition of stunned to
  player (breaks concentration), damage to player (triggers check), explicit
  end_concentration, streaming emits events + persists, concentration roster
  helper.
- **`test_game_events.py`** (extended) — `concentration` factory round-trip.
- **`gameEvents.test.ts`** (extended) — `concentrationColor`, `concentrationIcon`,
  `concentrationSummary`, `summarizeEvent` dispatch.
- **`ConcentrationCard.test.tsx`** (NEW) — started, broken, ended, check_passed,
  check_failed, dismiss.

### Key Design Decisions

1. **Player-only concentration** — the DM pipeline tracks the *player caster's*
   concentration in `game_state["concentration"]`. Monster/NPC concentration is
   out of scope (they cast through the spell engine but the DM narrates their
   spells; the Encounter doesn't track monster concentration state).
2. **Concentration is reactive** — unlike Phases 1-5 (direct actions),
   concentration mostly changes as a *side-effect* of cast/condition/damage
   actions. The only direct action is `end_concentration` (voluntary drop).
3. **`game_state["concentration"]` = single source of truth** — a
   `ConcentrationState.to_dict()`. Backward-compatible: absent key = not
   concentrating.
4. **Auto-replace on new concentration cast** — per PHB p.203, casting a new
   concentration spell ends the previous one. The cast_spell hook handles this.
5. **Damage check uses the real Con save** — `check_concentration()` rolls a
   real d20 + Con mod + prof (if proficient) vs DC (10 or half-damage). The DM
   never fabricates the outcome.
6. **New player-damage path** — a `damage` action targeting `"player"` applies
   damage to `character.current_hp` and triggers the concentration check. This
   also closes a gap (the DM couldn't damage the player before).
7. **Graceful degradation** — missing character / no concentration state → skip
   hooks, log warning, still return prior-phase events.
8. **Consistent inline UX** — ConcentrationCard follows the dismissible-inline
   pattern of all Phase 1-5 cards.

### Verification Checklist

- [ ] `uv run pytest` — all tests pass (+~30 new)
- [ ] `npx tsc --noEmit` — no type errors
- [ ] `npm run build` — clean build
- [ ] `npm test` — all frontend tests pass (+~20 new)
- [ ] PROGRESS.md updated
- [ ] Commit `feat: DM function calling Phase 3.5 — concentration tracking`
- [ ] `git push origin develop`

### What Phase 3.5 Does NOT Include (deferred)

- AoE multi-target spell resolution (Phase 3.5b — implemented below)
- Monster/NPC concentration tracking (the Encounter doesn't persist monster
  concentration; would need a Combatant-level concentration field)
- Concentration spell duration timers (round-by-round tick-down; currently
  concentration persists until explicitly broken/ended)

---

## Phase 3.5b Implementation Plan: AoE Multi-Target Spell Resolution

> **Status:** GREEN-LIT by standing Mike green-light (2026-07-17) — executing.
> **Scope:** Let the DM cast one spell at multiple combatants in a single
> action — one slot consumed, one damage roll base, but **per-target saving
> throws** and per-target HP application. The classic case is Fireball hitting
> a cluster of goblins: each goblin rolls its own Dex save (some take full
> damage, some half), but only one 3rd-level slot is spent.
> **Approach:** Same Option C (Hybrid) as Phases 1-5/3.5a.

### Why Phase 3.5b Now (the problem it solves)

Today the DM can only emit **single-target** `cast_spell` actions. For an AoE
spell like Fireball the DM is forced to either:

1. Emit one `cast_spell` against one goblin (the others take nothing —
   mechanically wrong), or
2. Emit N `cast_spell` actions (one per goblin) — which **consumes N spell
   slots** and rolls N independent damage pools (also wrong; an AoE spell
   rolls its damage **once** and each target saves against that same damage).

Neither is correct 5e. Phase 3.5b adds a dedicated `cast_spell_aoe` action
that consumes **one slot**, rolls the spell damage **once**, then resolves a
**separate save per target** against that shared damage — exactly PHB p.204
("Each target makes a saving throw… If a spell deals damage to more than one
target at the same time, roll the damage once for all of them.").

### The architectural insight (vs Phase 3 single-target)

Phase 3's `dm_cast_spell` calls `Spellbook.cast()`, which **fuses two
concerns**: (a) consume a slot, and (b) resolve the effect once against one
target. That coupling is fine for single-target spells but **breaks for AoE**,
where one slot must feed N independent per-target resolutions.

The fix is to **split** slot-consumption from effect-resolution:

| Concern | Phase 3 (single-target) | Phase 3.5b (AoE) |
|---------|-------------------------|------------------|
| Slot consumed by | `Spellbook.cast()` (fused) | new `Spellbook.prepare_cast()` (slot only) |
| Effect resolved by | `Spellbook.cast()` → `resolve_spell_effect()` (once) | `resolve_spell_effect()` called **once per target** |
| Damage roll | once (inside `cast()`) | once (the spell's damage is rolled fresh per target by `resolve_spell_effect`; see note) |
| Save roll | one target's save | **N independent saves** (one per target) |

> **Note on "damage rolled once":** `resolve_spell_effect()` rolls
> `spell.roll_damage()` internally. For a faithful "roll once, apply to all"
> model we roll the **full** damage once and re-use it for every target,
> halving it per-target only when that target makes its save. This is
> implemented by rolling the base damage once in the handler and passing it
> through, rather than letting each per-target `resolve_spell_effect` call
> re-roll. (See Backend step 4 for the exact mechanism — a small
> `resolve_spell_aoe_target()` helper that takes the pre-rolled full damage.)

### Game action the DM can emit

| Action | Args | Effect |
|--------|------|--------|
| `cast_spell_aoe` | `{"spell_id": "fireball", "target_ids": ["goblin_1", "goblin_2", "goblin_3"], "slot_level": null}` | Cast one spell at multiple combatants — one slot, one damage roll, per-target saves |

`target_ids` is a list of combatant IDs from the `COMBATANT_ROSTER`. The
single-target `cast_spell` path is **untouched** (backward compatible).

### Backend Implementation

#### 1. `backend/app/engine/spells.py` — Add `Spellbook.prepare_cast()`

Extract the validation + slot-consumption half of `cast()` into a reusable
method that does NOT resolve the effect:

```python
def prepare_cast(
    self,
    spell_id: str,
    slot_level: Optional[int] = None,
    active_conditions: Optional[list[str]] = None,
) -> CastOutcome:
    """Validate + consume a spell slot WITHOUT resolving the effect.

    Returns a CastOutcome with ``spell`` + ``slot_level`` set and
    ``effect=None``. Use for AoE where the effect is resolved per-target via
    :func:`resolve_spell_effect` (or :func:`resolve_spell_aoe_target`).

    Mirrors the front half of :meth:`cast` exactly, so failure modes (unknown
    spell, non-caster, not known/prepared, component-blocked, no slots) are
    identical.
    """
```

`cast()` is left as-is (no refactor — avoid risk to Phase 3). `prepare_cast`
is a near-exact copy of the validation/slot block, returning
`CastOutcome(success=True, message="Prepared.", effect=None, slot_level=used_level, spell=spell)`.

#### 2. `backend/app/engine/spells.py` — Add `resolve_spell_aoe_target()` helper

A thin per-target resolver that takes the **pre-rolled full damage** (so all
targets share one damage pool, per PHB p.204) and a single target's save total:

```python
def resolve_spell_aoe_target(
    spell: Spell,
    slot_level: Optional[int],
    full_damage: int,
    target_save_total: Optional[int],
    spell_save_dc: Optional[int] = None,
) -> SpellEffectResult:
    """Resolve one AoE target's outcome against a shared damage roll.

    For save spells: made_save = target_save_total >= DC; damage = full//2 on
    a save, else full. For auto-damage AoE (Magic Missile multi-dart is
    single-target; not used here) damage = full. Attack-roll AoE is rare and
    not supported by this helper (fall back to resolve_spell_effect).
    """
```

This guarantees **one damage roll** feeds all targets (the handler rolls
`spell.roll_damage()` once and passes `full_damage` to every per-target call).

#### 3. `backend/app/engine/dm_functions.py` — Add `dm_cast_spell_aoe()`

```python
def dm_cast_spell_aoe(
    spellbook: Spellbook,
    spell_id: str,
    target_specs: list[dict],   # [{name, target_ac?, target_save_total?}, ...]
    slot_level: int | None = None,
    caster_mod: int = 0,
    active_conditions: list[str] | None = None,
) -> tuple[GameEvent, list[dict]]:
    """Resolve an AoE spell: one slot, one damage roll, per-target saves.

    Returns (summary_spell_cast_event, per_target_results) where
    per_target_results is a list of dicts:
      {name, damage, made_save, half_damage, damage_type}
    The caller applies damage to each encounter combatant's HP and emits the
    follow-up DAMAGE events (it owns the Encounter; dm_functions does not).
    """
```

Internally:
1. `spellbook.prepare_cast(spell_id, slot_level, active_conditions)` → on
   failure, return a failed `spell_cast` summary event + empty results.
2. Roll `full_damage = spell.roll_damage(spellbook.level, slot)` **once**.
3. For each target spec, call `resolve_spell_aoe_target(...)` → collect
   per-target `{name, damage, made_save, half_damage, damage_type}`.
4. Build the summary `spell_cast` event with `is_aoe=True`, `target_count`,
   `total_damage` (sum of per-target damage), `save_dc`, `save_ability`,
   `damage_type`, and `slots_remaining`. `target` = "" (no single HP bar).

Defensive try/except throughout (never crash the pipeline).

#### 4. `backend/app/api/game.py` — `cast_spell_aoe` handler in `_resolve_game_actions()`

Add `_AOE_SPELL_ACTION = "cast_spell_aoe"`. New `elif func == "cast_spell_aoe":`
branch (parallel to `cast_spell`):

- Same guards as `cast_spell` (character, spellbook, caster, spell_id).
- Read `target_ids = args.get("target_ids") or []`. If empty / no encounter →
  emit a failed `spell_cast` summary ("AoE spell requires target_ids and an
  active encounter.") and continue.
- Build `target_specs` by looking up each `target_id` in the encounter:
  `{name, target_save_total}` (via `_combatant_save_total`).
- Call `dm_cast_spell_aoe(...)`.
- Append the summary `spell_cast` event.
- For each per-target result with `damage > 0`: apply to the matching
  combatant (`take_damage`), then append a `DAMAGE` event carrying
  `made_save` + `half_damage` (so DamageCard can show save outcome) + the
  combatant's HP.
- **Concentration coupling:** if the AoE spell is a concentration spell and
  the cast succeeded, run the same concentration-start logic as `cast_spell`
  (auto-end previous + start new + persist `game_state["concentration"]`).
  Most AoE damage spells (Fireball, Lightning Bolt, Shatter, Burning Hands)
  are non-concentration, but Stinking Cloud / Cloudkill / Wall of Fire are —
  handle it correctly.
- `has_spell` detection extended to include `cast_spell_aoe` so the encounter
  loads for coupling.

#### 5. `backend/app/llm/dspy_signatures.py` — Expand `DMActionableNarration`

Add AoE guidance + `cast_spell_aoe` to the function list + args schema:

```
- For AoE SPELLS (Fireball, Lightning Bolt, Shatter, Burning Hands, etc. —
  any spell that affects multiple creatures in an area):
  - Use cast_spell_aoe to hit MULTIPLE combatants with ONE cast. This
    consumes ONE spell slot and rolls damage ONCE; each target rolls its own
    save. NEVER emit multiple cast_spell actions for one AoE spell (that
    would burn multiple slots).
  - Args: {"spell_id": "fireball",
           "target_ids": ["goblin_1", "goblin_2", "goblin_3"],
           "slot_level": null}
  - target_ids is a LIST of combatant IDs from COMBATANT_ROSTER. Use it for
    any spell whose description mentions an area (sphere, cone, line, radius,
    cylinder) or "each creature in".
```

Add `cast_spell_aoe` to the `function` enum and the args schema list.

#### 6. `backend/app/engine/game_events.py` — Extend `spell_cast` factory

Add optional AoE fields to `GameEvent.spell_cast()` (all optional, default
off, so existing single-target events are unchanged):

```python
is_aoe: bool = False,
target_count: int | None = None,
total_damage: int | None = None,
```

Stored in `data`. The factory already supports arbitrary fields via the
data dict, so this is additive.

### Frontend (Steps 7-10)

#### 7. `types/index.ts` — Add AoE fields to `GameEventData`

Add `is_aoe?: boolean`, `target_count?: number`, `total_damage?: number` to
the `spell_cast` section. Add `made_save?: boolean | null` and `half_damage?`
(already present) to the `damage` section so DamageCard can show save outcome.

#### 8. `utils/gameEvents.ts` — AoE summary helper

Add `spellAoeSummary(spellName, level, school, targetCount, totalDamage,
damageType, saveAbility, saveDc)` → e.g.
`"Fireball (3rd-level evocation) — hits 3 targets for 42 fire damage"`.
Update `summarizeEvent` to use it when `d.is_aoe`. Update `damageSummary` to
append "(saved — half)" when `made_save` is true.

#### 9. `components/SpellCastCard.tsx` — AoE summary mode

When `d.is_aoe` is true, render an AoE summary variant:
- Spell name + school + level + 🎯 icon
- "Hits **N** targets" badge + `💥 X <type> total damage`
- Save DC + ability badge (e.g., "DC 15 dex")
- Slot expended badge
- **No single HP bar** (multiple targets). Per-target HP lives in the
  follow-up DamageCards.
- Dismissible.

#### 10. `components/DamageCard.tsx` — Optional save-outcome badge

When `d.made_save !== undefined`, show a small badge:
- `made_save === true` → "🛡️ Saved (half damage)" (amber)
- `made_save === false` → "💫 Failed save" (the damage is full)

Backward compatible: existing damage events (no `made_save`) render unchanged.

### Test Plan (Step 11) — ~22 backend, ~12 frontend

- **`test_spell_aoe.py`** (NEW, engine) — `Spellbook.prepare_cast` (success,
  cantrip, no slots, unknown, non-caster, component-blocked; slot actually
  consumed; does NOT resolve effect). `resolve_spell_aoe_target` (save pass =
  half, save fail = full, no-save = full, auto-damage).
- **`test_dm_spell_aoe_functions.py`** (NEW) — `dm_cast_spell_aoe`: one slot
  consumed, per-target saves, total_damage summation, failed cast (no slots),
  empty target list, serialization of summary event.
- **`test_spell_aoe_events_api.py`** (NEW) — `/action` with `cast_spell_aoe`
  Fireball at 3 goblins: one slot consumed + persisted, one `spell_cast`
  summary (`is_aoe=True`, `target_count=3`), three `damage` events with
  per-target `made_save`, combatant HP reduced, concentration not started
  (Fireball non-concentration), streaming emits + parses SSE, AoE
  concentration spell starts concentration, graceful degradation (no
  encounter / empty target_ids → failed summary event).
- **`test_game_events.py`** (extended) — `spell_cast` AoE fields round-trip.
- **`gameEvents.test.ts`** (extended) — `spellAoeSummary`, `summarizeEvent`
  AoE branch, `damageSummary` save badge.
- **`SpellCastCard.test.tsx`** (extended) — AoE mode renders target count +
  total damage + no HP bar.
- **`DamageCard.test.tsx`** (extended) — save badge (saved/failed/absent).

### Key Design Decisions

1. **New `cast_spell_aoe` action (not extending `cast_spell`)** — keeps the
   single-target path untouched (zero risk to Phase 3) and makes the DM's
   intent explicit. Matches the design doc's earlier "future `cast_spell_aoe`
   function" hint.
2. **Split slot-consumption from resolution** — new `Spellbook.prepare_cast()`
   consumes the slot; per-target `resolve_spell_aoe_target()` resolves. This
   is the key enabler. `cast()` is NOT refactored (avoid Phase 3 risk).
3. **One damage roll, N saves** — per PHB p.204, AoE damage is rolled once
   and each target saves against it. The handler rolls `full_damage` once and
   passes it to every per-target resolver.
4. **One summary event + N damage events** — the `spell_cast` summary shows
   the cast (slot, DC, total damage, target count, no HP bar); each
   per-target `damage` event shows that target's HP bar + save outcome. This
   reuses the Phase 2 DamageCard and the Phase 3 SpellCastCard (extended).
5. **Concentration coupling preserved** — AoE concentration spells start
   concentration once (same logic as single-target). Most AoE damage spells
   are non-concentration, but the path is correct.
6. **Player excluded from enemy AoE** — the DM targets enemy clusters; the
   player is a valid `target_id` too (a monster's AoE could hit the player),
  handled by the same per-target path (player HP via `character.current_hp`).
7. **Graceful degradation** — missing character/spellbook/encounter, empty
   `target_ids`, unknown target IDs → failed summary event, no crash.
8. **Backward compatible** — all new fields optional; existing single-target
   `cast_spell` events and cards render unchanged.

### Verification Checklist

- [x] `uv run pytest` — all tests pass (2891, +~38 AoE)
- [x] `npx tsc --noEmit` — no type errors
- [x] `npm run build` — clean build
- [x] `npm test` — all frontend tests pass (393, +19 AoE)
- [x] PROGRESS.md updated
- [x] Commit `feat: DM function calling Phase 3.5b — AoE multi-target spell resolution`
- [x] `git push origin develop`
