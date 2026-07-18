# Dev Agent Report — Doc-Drift Audit & Fix (2026-07-18)

## Context

This was a scheduled cron run. The DM Function Calling roadmap is **complete**
(every phase shipped: dice, combat, spells, inventory, conditions, concentration,
AoE, UI polish). The standing directive for the post-roadmap steady-state is:

> keep the full suite green · watch for README/PROGRESS drift · pick up quick fixes
> / content registry expansions if surfaced

The previous run already produced a health-check report ("suite green, roadmap
complete, no drift"). Rather than emit a duplicate health check, this run
performed a **systematic content-registry audit** to verify the counts reported
in PROGRESS.md / README.md against the *actual* live registries — and found +
fixed real drift.

## Verification (suite still green)

| Check | Result |
|-------|--------|
| `uv run pytest` | **2902 passed**, 0 failures (12 third-party DSPy warnings, unchanged) |
| `frontend && npx tsc --noEmit` | **0 type errors** |
| `frontend && npm run build` | **clean** (main bundle 339.67 KB gzip 99.70 KB — unchanged) |
| `frontend && npm test` | **393 passed** (28 files) |
| Codebase TODO/FIXME/skip sweep | **0** markers in backend or frontend |

No regressions — the only source-code touch in this run was a single JSDoc
comment (no behaviour, no types).

## Content-Registry Audit — methodology

Loaded every engine registry in-process via `uv run python` and printed
`len(REGISTRY)` for each, then diffed against the numbers in the PROGRESS status
banner and README. (Git history was checked to determine whether each
discrepancy was a *regression* or a *doc error that had existed since the
feature was first written*.)

### Result

| Registry | Actual | Docs claimed | Verdict |
|----------|--------|--------------|---------|
| Spells | 108 | 108 | ✅ |
| Enemies | 116 | 116 | ✅ |
| Feats | 53 | 53 | ✅ |
| Tools | 47 | 47 | ✅ |
| Backgrounds | 18 | 18 | ✅ |
| Alignments | 9 | 9 | ✅ |
| Languages | 18 | 18 | ✅ |
| **Mounts** | **18** | 19 | ✏️ fixed |
| **Traps** | **14** | 15 | ✏️ fixed |
| **Subclasses** | **29** | 27 | ✏️ fixed |
| Legendary creatures | 6 | 6 | ✅ |
| Starter adventures | 3 | 3 | ✅ |

**All three discrepancies were doc errors, not regressions** — verified via git
history:

- **Mounts**: `MOUNT_REGISTRY` has had exactly 18 entries since its only
  creation commit (`82ca497`). The docs always said "19" (off-by-one).
- **Traps**: `TRAP_REGISTRY` has had exactly 14 entries since its only creation
  commit (`23acac3`). The docs always said "15" (off-by-one).
- **Subclasses**: `SUBCLASS_REGISTRY` has had exactly 29 entries since its only
  creation commit (`82ed4ac`) — even that commit's *message* wrongly claimed
  "27-subclass registry". The docs inherited the wrong number (off-by-two).
  The two under-counted subclasses are **Knowledge Domain** (cleric) and
  **School of Abjuration** (wizard).

So the game actually has *more* subclasses than advertised, and exactly the
right number of mounts/traps. Players were being under-sold.

## Files changed

- **`PROGRESS.md`** — 6 stale count references corrected:
  - status banner: `19 mounts/vehicles, 15 traps, 27 subclasses` → `18 / 14 / 29`
  - Mounts-panel narrative (×2): `19-mount` → `18-mount`
  - Mounts engine narrative (×1): `19-mount MOUNT_REGISTRY` → `18-mount`
  - DESIGN future-items checklist (×1): `19-mount registry` → `18-mount`
  - Traps narrative (×2): `15 DMG sample traps` + `15-trap registry` → `14`
- **`README.md`** — `all 12 core classes + 27 subclasses` → `+ 29 subclasses`
- **`frontend/src/components/MountsPanel.tsx`** — JSDoc `19-mount registry`
  → `18-mount registry` (the one source-code touch; comment only).

## Commit

`docs: fix stale content-registry counts in PROGRESS/README/MountsPanel (mounts 19→18, traps 15→14, subclasses 27→29)`

## Next run

- Suite is green, counts are now accurate, no further scheduled work.
- If Mike green-lights any of the open future directions (Phase 6 story-state
  `game_actions`, cross-phase AoE concentration/save polish), draft a design doc
  and pick it up. Until then: re-verify green + drift-watch on each run.
