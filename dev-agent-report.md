# Dev Agent Report — DM Function Calling: Game Event UI Polish

**Date:** 2026-07-17
**Status:** ✅ COMPLETE — all three polish items shipped, full suite green
**Commit:** (see `git log`)
**Roadmap:** DM Function Calling item #7 (UI polish) — DONE. Only Phase 3.5b (AoE) remains.

---

## Summary

The DM function-calling roadmap (Phases 1–5 + 3.5a) was already complete. This run
delivered the remaining **UI polish** vision items from
`docs/DM_FUNCTION_CALLING_RESEARCH.md` ("Game Event UI Layer" /
"Design Principles for Event UI"):

1. **Dice tumble animation** — dice flicker through random faces (~480ms) then settle.
2. **HP-bar shake** — the HP bar shakes when damage lands.
3. **Collapsed-by-default for old events** — older event cards collapse to a one-liner.

This is a **pure frontend** pass — no new game_actions or backend mechanics. The
existing Phase 1–5 + 3.5a card system gains animation + a collapse mode. All new
logic is unit-tested.

## What shipped

### 1. Dice tumble animation
- **`frontend/src/utils/diceTumble.ts`** (NEW, pure helpers) — `clampSides`,
  `randomDieValue` (injectable RNG), `tumbleProgress`, `tumbleComplete`,
  `shouldTumble`, `prefersReducedMotion` (SSR/jsdom-safe), `DICE_TUMBLE_DURATION_MS`.
- **`frontend/src/hooks/useDiceTumble.ts`** (NEW) — `useDiceTumble(value)` (single)
  and `useDiceTumbleRolls(rolls)` (multi-roll, e.g. advantage). One
  `requestAnimationFrame` loop; settle to the true value. **Opt-in via `animate`
  prop** (default `false`) so tests render the settled value deterministically;
  respects `prefers-reduced-motion`.
- **`DiceRollCard.tsx`** — raw die value(s) tumble, then settle; the breakdown
  stays arithmetically consistent while tumbling and snaps to the stored total.
  Crit/advantage labels always use the *real* rolls. 🎲 glyph nudges while tumbling.
- **`AttackCard.tsx`** — the to-hit total tumbles like a rolling d20.

### 2. HP-bar shake
- **`frontend/tailwind.config.js`** — new `shake` keyframe + `animate-shake`
  (one-shot, ~450ms) and a `chevron-down` nudge. Both honour the existing
  `prefers-reduced-motion` global rule in `index.css`.
- **`DamageCard.tsx`** + **`AttackCard.tsx`** — HP bar gets `animate-shake` on
  mount when damage lands (AttackCard only shakes on a damaging hit).

### 3. Collapsed-by-default for old events
- **`utils/gameEvents.ts`** — new `eventIcon(event)`, `eventAccent(event)`
  (reuses per-type colour helpers), `shouldCollapse(index, total, recentCount)`.
- **`GameEventRenderer.tsx`** — new `collapsed` + `onToggleCollapse` props +
  `animate` forwarding. When collapsed, renders a compact, accent-coloured
  one-line summary (`CollapsedEventLine`) with an expand chevron + dismiss.
- **`GameView.tsx`** — events now carry a stable client-side `uid`
  (`TrackedGameEvent`) so collapse/expand overrides survive dismissals. Last
  `EXPAND_RECENT` (=2) events stay expanded; older ones collapse. Per-event
  expand/collapse overrides in two `Set`s, reset each turn.

## Tests added — +49 frontend (backend unchanged)

- `utils/__tests__/diceTumble.test.ts` (NEW, **23**) — all pure helpers.
- `hooks/__tests__/useDiceTumble.test.ts` (NEW, **8**) — deterministic paths + async settle.
- `components/__tests__/GameEventRenderer.test.tsx` (NEW, **7**) — collapse behaviour.
- `utils/__tests__/gameEvents.test.ts` (**+11**) — `eventIcon`, `eventAccent`, `shouldCollapse`.

## Verification

- ✅ `uv run pytest` — **2853 backend** passing (unchanged)
- ✅ `npx tsc --noEmit` — no type errors
- ✅ `npm run build` — clean production build (main bundle 337 KB)
- ✅ `npm test` — **374 frontend** passing (was 325, +49), 0 failures

## Files changed

New: `utils/diceTumble.ts`, `hooks/useDiceTumble.ts`, + 3 test files.
Modified: `tailwind.config.js`, `utils/gameEvents.ts`, `GameEventRenderer.tsx`,
`DiceRollCard.tsx`, `AttackCard.tsx`, `DamageCard.tsx`, `GameView.tsx`, README.md,
PROGRESS.md, `docs/DM_FUNCTION_CALLING_RESEARCH.md`.

## Architectural decisions

1. **Opt-in `animate` prop** — the tumble is gated behind `animate` (default
   `false`) so existing card tests, which assert exact breakdown strings like
   `'15 + 3 = 18'`, stay deterministic. The real app opts in via `GameView`.
2. **Single rAF hook** — `useDiceTumbleRolls` handles multi-roll (advantage) with
   one animation loop instead of N hooks, keeping React's rules-of-hooks happy.
3. **Stable uid tracking** — events get a client-side `uid` so collapse/expand
   overrides survive dismissal (which filters by index). Reset each turn.
4. **Pure logic in `utils/`** — per project convention, all testable logic
   (clamp/range/progress/collapse) lives in pure functions with their own tests;
   the hooks/components stay thin.
5. **`prefers-reduced-motion` honoured** everywhere (tumble skipped; global CSS
   disables the shake keyframe).

## What the next run should pick up

Only **Phase 3.5b (AoE multi-target spell resolution)** remains on the roadmap
(stretch). No detailed file-level plan exists yet — the next run should **draft
the Phase 3.5b implementation plan** in `docs/DM_FUNCTION_CALLING_RESEARCH.md`
(same depth as Phases 1–5/3.5a) before implementing, under the standing green-light.
