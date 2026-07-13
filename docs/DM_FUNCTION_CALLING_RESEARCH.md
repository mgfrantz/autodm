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

## Related Documents
- `docs/DSPY_TEXT_GAME_REFERENCE.md` — DSPy text game tutorial analysis;
  `ActionResolver` signature (structured skill-check resolution) is directly
  relevant to this effort
- `PROGRESS.md` — "Quest detection in dialogue" already implemented some of
  the structured-output groundwork (quest detection fields in narration)
- `DESIGN.md` — current architecture and data models

## Changelog
- 2025-07-13: Initial brainstorm, staged as ongoing research theme by Mike
