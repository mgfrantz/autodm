# DSPy Text-Based AI Game — Reference & Pattern Analysis

**Source:** <https://dspy.ai/tutorials/ai_text_game/>  
**Purpose:** Design pattern reference for gameplay and game management. Not a direct
architecture to adopt — our game is far more sophisticated — but a source of
targeted ideas for future enhancement, especially as we continue refining the
DSPy integration.

---

## Tutorial Overview

The DSPy tutorial builds a simple interactive text adventure ("Mystic Realm
Adventure") with three core DSPy signatures:

| Signature | Purpose |
|---|---|
| `StoryGenerator` | Dynamic scene generation (description, actions, NPCs, items) |
| `DialogueGenerator` | NPC dialogue with mood tracking + quest detection |
| `ActionResolver` | Action resolution with structured outcomes (success, stat changes, items, XP) |

These are composed in a `GameAI(dspy.Module)` that orchestrates the three
`ChainOfThought` calls.

---

## Useful Design Patterns (for our game)

### 1. Quest Detection in Dialogue ⭐ HIGH VALUE

**Tutorial pattern:** The `DialogueGenerator` signature outputs
`quest_offered: bool` and `information_revealed: str`. Every NPC dialogue
automatically signals whether a quest hook was introduced.

**Why it matters for us:** Our DM narration currently produces prose. We have a
social interaction system but no automatic quest tracking. Adding a quest-
detection output to dialogue/narration could feed a quest log UI and drive
branching story state.

**How to apply:** Add a `QuestDetection` or enhance `DMNarration` with optional
quest-flag outputs. Store detected quests in game state for the quest log panel.

### 2. NPC Mood / Relationship Tracking ⭐ HIGH VALUE

**Tutorial pattern:** NPC dialogue returns `mood_change: positive/negative/neutral`.
The game can track evolving NPC dispositions based on player choices.

**Why it matters for us:** Our NPCs are static. We have per-NPC TTS voices but no
relationship system. Tracking mood/reputation per NPC could unlock dynamic
dialogue (allies become hostile, merchants offer discounts, etc.).

**How to apply:** Extend `game_state["npcs"]` with a mood/relationship field.
Feed it back into narration context so the DM adapts NPC behavior.

### 3. Structured Action Resolution ⭐ MEDIUM VALUE

**Tutorial pattern:** `ActionResolver` returns structured fields:
`success: bool`, `stat_changes: dict[str,int]`, `items_gained: list[str]`,
`experience_gained: int`. Actions produce concrete mechanical outcomes, not just
narration.

**Why it matters for us:** Our DM narration is purely narrative — mechanical
outcomes (damage, XP, items) come from the rules engine. But for non-combat
skill checks (persuasion, investigation, etc.), a structured AI-driven resolution
could complement the rules engine, especially for open-ended player actions that
don't map to a specific 5e mechanic.

**How to apply:** Consider a `SkillCheckResolver` signature for freeform
exploration/social actions that don't fit the standard rules engine. Output
success/failure + mechanical consequences, then narrate the outcome separately.

### 4. Scene-Aware Action Generation ⭐ MEDIUM VALUE

**Tutorial pattern:** `StoryGenerator` outputs `available_actions: list[str]` —
contextually appropriate actions generated per scene, not a static menu.

**Why it matters for us:** Our action input is free-text. While that's more
flexible, we could offer AI-suggested actions as quick-pick buttons alongside
the free-text field. This improves UX for players who aren't sure what to do.

**How to apply:** Add an `available_actions` output to DM narration or a separate
`ActionSuggester` signature. Render as clickable suggestion chips in the
frontend.

### 5. Game Flags for Branching Narrative State ⭐ MEDIUM VALUE

**Tutorial pattern:** `GameContext` has a `game_flags: dict[str, bool]` for
tracking story state (e.g., `"met_king": True`, `"saved_village": False`).

**Why it matters for us:** Our world state persistence tracks some state, but a
simple, extensible flag system would make branching narratives manageable. The DM
can set/clear flags through narration, and future narrations can check them.

**How to apply:** Add `story_flags: dict[str, bool]` to `game_state`. Have the
DM narration signature output flags to set/clear. Feed existing flags into
narration context so the DM maintains narrative continuity.

### 6. Multi-Signature DM Module ⭐ DESIGN PATTERN

**Tutorial pattern:** Rather than one monolithic DM, the tutorial uses three
specialized signatures (`StoryGenerator`, `DialogueGenerator`, `ActionResolver`)
composed in a single module.

**Why it matters for us:** We currently have one `DMNarration` signature that
handles everything — game start, player actions, combat narration. As we add
features (quest detection, NPC mood, action suggestions), splitting into
specialized signatures would keep each focused. However, our monolithic approach
is simpler and works well for pure narration. The split pattern becomes valuable
when we need structured outputs that differ by context.

**How to apply:** Consider context-specific narration signatures rather than
overloading `DMNarration`:
- `GameStartNarration` (world intro)
- `CombatNarration` (battle flavor)
- `ExplorationNarration` (discovery/interaction)
- `SocialNarration` (dialogue/NPC interaction)

Each can have tailored outputs (combat narration → no quest flags; social
narration → mood + quest detection).

### 7. Dynamic Difficulty Heuristic ⭐ LOW VALUE (we have rules engine)

**Tutorial pattern:** `resolve_action()` has a keyword heuristic for difficulty:
fight/attack → hard, look/examine → easy, else medium.

**Why it matters for us:** Our 5e rules engine handles this properly with CR,
DC, and proficiency. This pattern is too simple for our needs. **Skip.**

### 8. Story Progress Counter ⭐ LOW VALUE (we have richer tracking)

**Tutorial pattern:** A simple integer `story_progress` that increments with each
action and scales narrative intensity.

**Why it matters for us:** Our `campaign_arc` and act tracking is more
sophisticated. **Already have better.**

---

## DSPy-Specific Patterns for the Migration

### Module Composition Pattern

```python
class GameAI(dspy.Module):
    def __init__(self):
        super().__init__()
        self.story_gen = dspy.ChainOfThought(StoryGenerator)
        self.dialogue_gen = dspy.ChainOfThought(DialogueGenerator)
        self.action_resolver = dspy.ChainOfThought(ActionResolver)
```

This confirms our existing approach (`CharacterCreationModule`,
`WorldGenerationModule`, `DMNarrationModule`, `StorySummaryModule` all use
`dspy.ChainOfThought` wrappers). ✅ Already aligned.

### Graceful Failure Pattern

The tutorial doesn't show explicit failure handling, but our modules already
catch failures and return empty Predictions — which is a best practice the
tutorial omits. ✅ We're ahead here.

### Input/Output Field Design

The tutorial signatures use concise `desc=` strings that guide the LLM without
being prescriptive. Our signatures already follow this pattern well. The tutorial's
`recent_actions: str` input (passing the player's last action as context) is
worth noting — it helps the LLM maintain narrative continuity. We do this through
our story log + context summarization, which is more scalable.

---

## Summary: Priority for Adoption

| Pattern | Value | Effort | Priority |
|---|---|---|---|
| Quest detection in dialogue | High | Medium | ✅ DONE |
| NPC mood/relationship tracking | High | Medium | ✅ DONE |
| Game flags for branching state | Medium | Low | ✅ DONE |
| Scene-aware action suggestions | Medium | Low | ✅ DONE |
| Structured skill-check resolution | Medium | High | ✅ DONE |
| Context-specific narration signatures | Design | Medium | 📋 Later |
| Dynamic difficulty heuristic | Low | — | ⏭️ Skip |
| Story progress counter | Low | — | ⏭️ Skip |
