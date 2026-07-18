# Dev Agent Report — High-Tier Enemy Registry Expansion (CR 11-30) + Werewolf Dedup

**Date:** 2026-07-18
**Run type:** Maintenance / content-registry expansion (DM Function Calling roadmap complete)
**Status:** ✅ COMPLETE — committed & pushed to develop

## Summary

The full DM Function Calling roadmap was already complete (Phases 1-5, 3.5,
3.5b, UI polish). The NEXT SESSION DIRECTIVE said to keep the suite green,
watch for doc drift, and pick up quick fixes / content registry expansions.
This run did two things surfaced by a registry audit:

1. **Bug fix — duplicate Werewolf key** (same class as the Thunderwave spell
   duplicate fixed earlier). `COMMON_ENEMIES` is a dict literal keyed by name;
   "Werewolf" appeared twice (CR 2 and CR 5), so the CR 5 entry silently
   overwrote the CR 2 one. The MM Werewolf is CR 3 (neither matched).
2. **Content gap — registry stopped at CR 10.** No enemies existed for CR
   11-30, leaving high-level parties (15-20) with no true solo threats. Added
   17 iconic Monster Manual high-tier entries spanning CR 11-30.

## Bug fix details

- Removed **both** Werewolf registrations.
- Added a single canonical **Werewolf (MM CR 3, AC 12, HP 58, atk +4)**
  retaining the lycanthrope nonmagical-BPS immunity (bypassed by silvered
  weapons).
- Filled the freed CR 2 slot with **Saber-Toothed Tiger** (MM CR 2) and the
  freed CR 5 slot with **Troll** (MM CR 5).
- Verified safe: `test_combat.py::test_lycanthrope_immunity_bypassed_by_silver_or_magic`
  builds its own standalone `Combatant` named "Werewolf" with hardcoded stats
  (does NOT pull from `COMMON_ENEMIES`), so it is unaffected.

## Content expansion — 17 iconic CR 11-30 monsters

| Name | CR | AC | HP | atk | Notable damage mods |
|------|----|----|----|----|---------------------|
| Dao | 11 | 18 | 120 | +9 | — |
| Gynosphinx | 11 | 17 | 136 | +8 | — |
| Erinyes | 12 | 18 | 153 | +9 | resist nonmagical BPS |
| Beholder | 13 | 18 | 180 | +5 | — |
| Storm Giant | 13 | 16 | 230 | +12 | — |
| Rakshasa | 13 | 16 | 84 | +6 | immune nonmagical BPS |
| Vampire | 13 | 16 | 144 | +7 | immune necrotic+poison, resist nonmagical BPS |
| Adult Blue Dragon | 16 | 19 | 243 | +12 | immune lightning |
| Adult Silver Dragon | 16 | 19 | 290 | +12 | immune cold |
| Adult Red Dragon | 17 | 19 | 297 | +14 | immune fire |
| Adult Gold Dragon | 17 | 19 | 297 | +14 | immune fire |
| Balor | 19 | 19 | 262 | +14 | immune fire+poison |
| Pit Fiend | 20 | 19 | 300 | +14 | immune fire+poison, resist nonmagical BPS |
| Ancient White Dragon | 20 | 20 | 333 | +14 | immune cold |
| Ancient Red Dragon | 22 | 22 | 546 | +17 | immune fire |
| Ancient Gold Dragon | 24 | 22 | 546 | +17 | immune fire |
| Tarrasque | 30 | 25 | 676 | +19 | immune fire+poison (apex) |

The engine already fully supported CR 0-30 (`CR_TO_XP` covers all CRs;
`cr_to_xp(20)==25000` was already tested). This purely filled the data gap.
Name conflicts avoided (e.g. existing "Adult Green Dragon" at CR 9,
"Ancient Bronze Dragon" at CR 9 were left untouched as pre-existing data
issues, out of scope).

## Registry result: 116 → 135 enemies

CR distribution now:
- CR 0: 3, CR 1/8: 5, CR 1/4: 5, CR 1/2: 6, CR 1: 8, CR 2: 10, CR 3: 11,
  CR 4: 10, CR 5: 10, CR 6: 10, CR 7: 10, CR 8: 10, CR 9: 10, CR 10: 10
- CR 11: 2, CR 12: 1, CR 13: 4, CR 16: 2, CR 17: 2, CR 19: 1, CR 20: 2,
  CR 22: 1, CR 24: 1, CR 30: 1

The Tarrasque is correctly the highest-CR entry. Full CR 0-30 range covered.

## Files changed

- `backend/app/engine/encounters.py` — dedup of two Werewolf entries; +1
  canonical CR-3 Werewolf, +1 Saber-Toothed Tiger (CR 2), +1 Troll (CR 5),
  +17 CR 11-30 iconic monsters with appropriate damage immunities/resistances.
- `backend/tests/test_enemy_high_cr_expansion.py` (NEW) — **89 tests**:
  Werewolf dedup regression (registered exactly once, MM CR 3, silvered-bypass
  immunity intact), whole-registry no-duplicate-names guard, each of the 17
  new monsters (registration shape, CR→XP correctness, valid `to_dict()`
  combat block), `get_enemies_by_cr` coverage at each new CR, registry
  total-count increase, full CR-range presence, apex-Tarrasque assertion,
  parametrized canonical-damage-immunity assertions, canonical-monster
  preservation.
- `PROGRESS.md` — status-line counts (3078 backend, 135 enemies), NEXT
  SESSION DIRECTIVE test-count note, new COMPLETED section.
- `README.md` — enemy counts (116→135), CR range (10+ → 0-30), test totals
  (3382→3471), new "Recently Completed" bullet.

## Verification

- ✅ `uv run pytest` — **3078 backend tests passing** (was 2989, +89), 0 failures
- ✅ `npx tsc --noEmit` — clean (frontend unchanged)
- ✅ `npm test` — 393 frontend tests passing (ran earlier this session; no
  frontend changes since)
- ✅ No regressions (encounters + combat suites fully green)

## Next run pickup

DM Function Calling roadmap is fully complete; no further phases scheduled.
The directive's standing instructions remain: keep suite green, sync README/
PROGRESS drift, pick up quick fixes / content expansions. Possible future
quick wins: add CR 14/15/18/21/23 monsters for even denser high-tier
coverage, or expand the spell/enemy registries further. No action required.
