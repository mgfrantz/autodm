# Design Research: DM Function Calling (Agent-Based Game State Interaction)

> **Status:** Brainstorming / Design Research — NOT YET IMPLEMENTED
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
