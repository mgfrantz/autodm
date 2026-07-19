# Dev Agent Report — DM Function Calling Cross-Phase Polish (Player as AoE Target)

**Date:** 2026-07-18
**Run type:** Scheduled dev-agent cron (hourly)
**Status:** ✅ Complete — feature shipped, suite green, pushed to develop

---

## Summary

The DM Function Calling roadmap was already complete (Phases 1–5, 3.5a, 3.5b,
UI polish). The post-roadmap NEXT SESSION DIRECTIVE flagged one concrete
**cross-phase polish** item: *"concentration checks triggered by AoE spell
damage on the player."* This run closes that item.

**The gap:** the `cast_spell_aoe` game-action pipeline only resolved targets
that were encounter combatants. The literal `"player"` target_id was silently
dropped (logged "not in roster; skipping"), so:
- the player could never take AoE damage through the multi-target path, and
- no concentration check fired on such damage.

This was **inconsistent** with the plain `damage` action, which already routes
`target_id == "player"` → `character.current_hp` and fires concentration checks.

**The fix:** `"player"` is now a valid entry in `cast_spell_aoe`'s
`target_ids`. The player's save is rolled with their *real* save proficiency,
damage routes to `character.current_hp` (not a combatant), and a real
concentration check fires when the player is concentrating — identical to the
plain `damage` action's player path.

## Files changed

### Backend (feature)
- **`backend/app/api/game.py`**
  - New `_character_save_total(character, save_ability)` helper — companion to
    `_combatant_save_total`, but uses the character's real save proficiency
    (`calculate_save_bonus`: ability mod + proficiency bonus when proficient),
    not monsters' ability-mod-only approximation. Defensive fallback on error.
  - `cast_spell_aoe` resolution branch: `"player"` is now a valid target_id.
    Builds a per-target spec from `_character_save_total` and tracks it with a
    parallel `is_player_target` flag. On a successful cast, player damage
    routes to `character.current_hp` and fires `_fire_concentration_check` when
    the player is concentrating. Mixed targets (player + combatants) resolve
    correctly; the `is_player` flag disambiguates even when the player shares a
    name with a player-side combatant.
- **`backend/app/llm/dspy_signatures.py`** — `DMActionableNarration` docstring
  now tells the DM `"player"` is valid in `cast_spell_aoe`'s `target_ids` for
  blast-radius coverage (enemy AoE, trap, own miscast).

### Tests (+5 backend)
- **`backend/tests/test_spell_aoe_events_api.py`** — new
  `TestPlayerAsAoeTarget` class:
  1. player fails save → full damage + HP reduced on Character (28→8)
  2. player makes save → half damage + `made_save`/`half_damage` flags
  3. player concentrating + AoE damage → concentration check event fires
  4. mixed targets (player + goblin) → both damaged via correct paths
     (Character HP + encounter combatant HP)
  5. streaming endpoint routes player AoE damage too

### Docs
- **`PROGRESS.md`** — test count 3187→3192; new "✅ COMPLETED: Cross-Phase
  Polish" section; NEXT SESSION DIRECTIVE marks the item DONE.
- **`README.md`** — test count 3187→3192 (3580→3585 total); new entry in
  Recently Completed.
- **`docs/DM_FUNCTION_CALLING_RESEARCH.md`** — status header notes the
  cross-phase polish is IMPLEMENTED.

## Why no frontend changes
The player-AoE-damage path emits a standard `damage` GameEvent (rendered by the
existing `DamageCard`) and the concentration check emits a `concentration`
GameEvent (rendered by `ConcentrationCard`). Both inline cards handle the new
event flow unchanged.

## Verification
- ✅ `uv run pytest` — **3192 backend tests passing** (was 3187, +5), 0 failures
- ✅ `npm test` — **393 frontend tests passing** (unchanged, no FE changes)
- ✅ `npx tsc --noEmit` — clean
- ✅ Registry drift check — all counts match README/PROGRESS (170 spells, 135
  enemies, 53 feats, 47 tools, 29 subclasses, 18 backgrounds/mounts/languages,
  14 traps, 9 alignments, 6 legendary, 3 adventures); zero duplicate names/ids.

## Commit
`feat: DM function calling cross-phase polish — player as AoE target`

## Next run
The roadmap remains complete. The NEXT SESSION DIRECTIVE's remaining open items
(needing Mike's green-light before implementation):
- **Story State (Phase 6)** — `set_story_flag` / `offer_quest` as explicit
  game_actions (we already have quest detection + game flags via DSPy).
- **Cross-phase polish (remaining)** — advantage/disadvantage on AoE saves.
- **Hardening** — any edge cases surfaced by playtesting.

Standing tasks: keep the suite green, watch for README/PROGRESS drift, pick up
quick fixes / content registry expansions if surfaced.
