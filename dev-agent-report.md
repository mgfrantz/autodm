# Dev Agent Report — Phase 3.5b (AoE Multi-Target Spell Resolution)

**Date:** 2026-07-17
**Commit:** `178b6ac`
**Status:** ✅ COMPLETE — full DM Function Calling roadmap now done

## What shipped

Phase 3.5b closes the spell system's last mechanical gap: the DM can now cast
**one spell at multiple combatants** in a single action. Fireball hitting three
goblins consumes **one 3rd-level slot**, rolls damage **once**, and resolves a
**separate saving throw per target** — exactly PHB p.204 ("If a spell deals
damage to more than one target at the same time, roll the damage once for all of
them").

### The problem this solves

Before Phase 3.5b, the DM could only emit single-target `cast_spell` actions.
For an AoE spell like Fireball, the DM was forced to either:
1. Hit one goblin (the others take nothing — mechanically wrong), or
2. Emit N `cast_spell` actions (one per goblin) — which burned N slots and rolled
   N independent damage pools (also wrong).

### The architectural insight

Phase 3's `Spellbook.cast()` **fuses** slot-consumption and effect-resolution.
That coupling breaks for AoE. The fix: **split** the two concerns without
touching `cast()` (zero risk to Phase 3):

| Concern | Phase 3 (single-target) | Phase 3.5b (AoE) |
|---------|-------------------------|------------------|
| Slot consumed by | `Spellbook.cast()` (fused) | new `Spellbook.prepare_cast()` (slot only) |
| Effect resolved by | `cast()` → `resolve_spell_effect()` (once) | `resolve_spell_aoe_target()` per target |
| Damage roll | once (inside `cast()`) | once (handler rolls `spell.roll_damage()`, passes to every per-target resolver) |
| Save roll | one target's save | **N independent saves** |

The handler emits **one summary `spell_cast` event** (`is_aoe=True`,
`target_count`, `total_damage`, no HP bar) followed by **N `damage` events**
(one per target, each with that target's HP bar + save outcome).

## Files changed

### Backend (Steps 1-6)
1. **`backend/app/engine/spells.py`** (+164 lines)
   - `Spellbook.prepare_cast()` — validate + consume slot WITHOUT resolving the
     effect (near-exact copy of `cast()`'s front half, returns `effect=None`).
   - `resolve_spell_aoe_target()` — per-target resolver against pre-rolled full
     damage; save → half, fail → full.
2. **`backend/app/engine/dm_functions.py`** (+167 lines)
   - `dm_cast_spell_aoe()` — one slot via `prepare_cast`, one damage roll,
     per-target `resolve_spell_aoe_target`, returns
     `(summary_spell_cast_event, per_target_results)`. Defensive try/except.
3. **`backend/app/engine/game_events.py`** (+39 lines)
   - `spell_cast()` factory extended with optional `is_aoe`, `target_count`,
     `total_damage` params.
   - `damage()` factory extended with optional `made_save`, `half_damage`
     (None for non-spell damage → unchanged render).
4. **`backend/app/api/game.py`** (+169 lines)
   - `_AOE_SPELL_ACTION` constant, `_norm_spell_id()` helper.
   - `cast_spell_aoe` handler in `_resolve_game_actions()`: build target_specs
     from encounter, call `dm_cast_spell_aoe`, apply per-target `take_damage`,
     emit per-target DAMAGE events with save outcome, concentration coupling
     for AoE concentration spells. `has_spell` detection extended.
5. **`backend/app/llm/dspy_signatures.py`** (+18 lines)
   - `DMActionableNarration` docstring + function enum + args schema expanded
     with AoE guidance (`cast_spell_aoe` with `target_ids: [...]`).

### Frontend (Steps 7-10)
6. **`frontend/src/types/index.ts`** — `is_aoe?`, `target_count?`,
   `total_damage?` added to `GameEventData` (all optional — backward compatible).
7. **`frontend/src/utils/gameEvents.ts`**
   - New `spellAoeSummary()` helper.
   - `summarizeEvent` spell_cast branch dispatches to AoE variant when
     `d.is_aoe`.
   - `damageSummary()` gains optional `madeSave` param → appends "(saved — half)".
8. **`frontend/src/components/SpellCastCard.tsx`** — New AoE summary mode:
   🎯 icon, "Hits N targets" badge, total-damage badge, save DC badge, slot
   badge, **no HP bar** (per-target HP lives in follow-up DamageCards). Failed
   AoE casts still render the muted failed card.
9. **`frontend/src/components/DamageCard.tsx`** — Optional save-outcome badge:
   "🛡️ Saved (half damage)" (amber) or "💫 Failed save" (emerald). Absent for
   non-spell damage.

### Docs
- `docs/DM_FUNCTION_CALLING_RESEARCH.md` — Phase 3.5b status → IMPLEMENTED ✅;
  verification checklist all checked.
- `PROGRESS.md` — COMPLETED section added, status tags, test counts,
  NEXT SESSION DIRECTIVE → roadmap complete.
- `README.md` — Phase 3.5b feature bullet, test counts (3284 total), removed
  from "Planned".

## Tests

### Backend — +38 (2891 total)
- **`test_spell_aoe.py`** (NEW, 14) — `prepare_cast` (success, cantrip, no
  slots, unknown, non-caster, component-blocked, slot actually consumed, does
  NOT resolve effect); `resolve_spell_aoe_target` (save pass = half, fail =
  full, no-save = full).
- **`test_dm_spell_aoe_functions.py`** (NEW, 10) — `dm_cast_spell_aoe`: one
  slot consumed, per-target saves, total_damage summation, failed cast, empty
  targets, serialization.
- **`test_spell_aoe_events_api.py`** (NEW, 14) — `/action` Fireball at 3
  goblins: one slot + persisted, one summary `spell_cast` (`is_aoe=True`),
  three `damage` events with per-target `made_save`, combatant HP reduced,
  concentration not started (Fireball), streaming emits + parses SSE, AoE
  concentration spell starts concentration, graceful degradation (no encounter /
  empty target_ids).
- **`test_game_events.py`** (+2) — `spell_cast` AoE fields round-trip.

### Frontend — +19 (393 total)
- **`gameEvents.test.ts`** (+8) — `spellAoeSummary` (4), `summarizeEvent` AoE
  branch (1), `damageSummary` save badge (3).
- **`SpellCastCard.test.tsx`** (+8) — AoE mode: header, target-count badge,
  total-damage badge, save DC badge, slot badge, no HP bar, failed AoE, dismiss.
- **`DamageCard.test.tsx`** (+3) — saved badge, failed-save badge, absent badge.

## Verification

- ✅ `uv run pytest` — **2891 backend tests passing** (was 2853, +38)
- ✅ `npx tsc --noEmit` — no type errors
- ✅ `npm run build` — clean production build (main bundle 340 KB)
- ✅ `npm test` — **393 frontend tests passing** (was 374, +19)
- ✅ `git push origin develop` — pushed (`ab74e3d..178b6ac`)

## Roadmap status — ALL PHASES COMPLETE ✅

- ✅ Phase 1 — Dice + Check Prompts
- ✅ Phase 2 — Combat Resolution
- ✅ Phase 3 — Spell Casting
- ✅ Phase 4 — Inventory Operations
- ✅ Phase 5 — Condition Application
- ✅ Phase 3.5a — Concentration Tracking
- ✅ Phase 3.5b — AoE Multi-Target Spell Resolution
- ✅ UI Polish — Dice tumble + HP-bar shake + collapsed-by-default old events

The DM is now a full tool-calling agent. No further DM Function Calling phases
are scheduled.

## Next run

No outstanding DM Function Calling work. The dev agent should:
- Keep the full suite green (`uv run pytest`, `npm test`)
- Watch for README/PROGRESS drift and sync them
- Pick up any quick fixes / content registry expansions if surfaced
- Consider drafting a Phase 6 design doc (Story State — `set_story_flag` /
  `offer_quest` as explicit game_actions) only if Mike green-lights it
