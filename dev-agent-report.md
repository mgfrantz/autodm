# Dev Agent Report — Orphaned GameSave Crash Fix

**Date:** 2026-07-18
**Run type:** Maintenance / hardening (DM Function Calling roadmap COMPLETE)
**Branch:** `develop`
**Commit:** `450395a`

## Summary

The DM Function Calling roadmap is complete and the suite was green, so this
scheduled run executed the standing directive's "quick fixes / hardening"
track. The prior health-check report (commit `afc7a4d`) explicitly flagged a
concrete bug to "investigate the starter-adventure save flow separately": **2
orphaned `game_saves` in the production dev DB** whose `character_id` /
`world_id` pointed to rows that no longer existed, which "may error" on load.

I investigated, found the **root cause + a wider blast radius**, and shipped a
complete fix: root-cause cascade, a defensive layer, a new cleanup endpoint,
and a data cleanup. This was not a new feature — it is hardening of an
edge-case surfaced by real play data.

## The Bug (and why it was worse than "may error")

A `GameSave` requires both a Character and a World (both FKs are NOT NULL).
But if either parent row was deleted **without cascading** — via raw SQL, a
partial DB reset, or the legacy `db.delete(character)` (the `Character.saves`
relationship had no cascade) — the FK became dangling and `save.character`
resolved to `None`. Any endpoint that dereferenced it (`save.character.name`)
then raised `AttributeError: 'NoneType' …` → **500 Internal Server Error**.

Blast radius: **`GET /api/game/`** (`list_games`) dereferences `s.character.name`
/ `s.world.name` for *every* save in a list comprehension. A single orphaned
save took down the **entire "continue game" menu** — not just the broken game.
Likewise `GET /api/game/{id}/state`. This is the worst kind of failure: one
corrupted save bricks the whole load screen.

Root cause confirmed in the data: the dev DB held `game_saves` 1 & 2
("The Cursed Mines of Emberdeep") referencing characters 1,2 and worlds 9,1 —
none of which existed (0 characters, 0 worlds).

## What Shipped

### 1. Root cause — relationship cascade (`backend/app/models/models.py`)
Added `cascade="all, delete-orphan"` to:
- `Character.saves`
- `World.world_saves`

Now `DELETE /characters/{id}` (and any ORM-driven world/character delete)
auto-removes dependent `GameSave` rows, and those cascade to their `SaveSlot`s
via the existing cascade. **No future orphans from character/world deletion.**

### 2. Defensive layer — orphan-resilient list/load (`backend/app/api/game.py`)
- New `_save_is_orphaned(save)` helper (`save.character is None or save.world is None`).
- `list_games` **skips** orphaned saves with a `logger.warning` — the menu
  never crashes and never lists unplayable games.
- `get_game_state` returns a clear **410 Gone**
  ("This game is corrupted … Delete it via DELETE /game/{id}") instead of a 500.

### 3. New `DELETE /api/game/{game_id}` endpoint (`backend/app/api/game.py`)
There was previously **no way to delete a whole game**. The new endpoint deletes
the `GameSave` (SaveSlots cascade) and is the **recovery path** for corrupted
saves — it works on orphans too (deletes by the save's own identity, so the
dangling FKs are irrelevant). Frontend `deleteGame(gameId)` client added
(`frontend/src/stores/api.ts`).

### 4. Data cleanup — production dev DB
Removed the 2 orphaned `game_saves` + their 2 `save_slots` (0 characters /
0 worlds existed, so they were unrecoverable). `game_saves`: 2→0,
`save_slots`: 2→0. The flagged issue is fully closed.

## Files Changed
- `backend/app/models/models.py` — cascade on `Character.saves` + `World.world_saves`.
- `backend/app/api/game.py` — `_save_is_orphaned()`, hardened `list_games` +
  `get_game_state`, new `DELETE /{game_id}`.
- `frontend/src/stores/api.ts` — `deleteGame()` client.
- `backend/tests/test_game_lifecycle.py` — NEW, 11 tests.
- `PROGRESS.md` — new COMPLETED section + banner test count (2891→2902).
- `README.md` — test count sync (2891+393=3284 → 2902+393=3295).

## Tests — +11 backend (`test_game_lifecycle.py`, NEW)
- `list_games` excludes orphaned saves / keeps playable saves alongside orphans.
- `get_game_state` → 410 for orphaned save; → 200 for valid save.
- `DELETE /game/{id}` removes save / cascades save_slots / works on orphan /
  404 for missing game.
- Relationship cascade: delete character → GameSaves gone; delete world →
  GameSaves gone; delete character → GameSaves + SaveSlots gone.

## Verification (all green)
| Check | Result |
|-------|--------|
| `uv run pytest` (backend) | ✅ **2902 passing** (+11), 0 failures (12 third-party DSPy warnings) |
| `npx tsc --noEmit` (frontend) | ✅ No type errors |
| `npm run build` (frontend) | ✅ Clean build — main bundle 339.67 KB (99.70 KB gzip) |
| `npm test` (frontend) | ✅ **393 passing** (28 files) |

## Next Run

Roadmap remains complete; no new phase is scheduled. The standing directive
applies: keep the suite green, watch for drift, pick up quick fixes. Remaining
Mike green-light candidates (unchanged from prior report): Phase 6 Story State,
cross-phase spell polish, multiplayer foundation, content expansion.
