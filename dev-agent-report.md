# Dev Agent Report — PHB Level-6 Spell Completion

**Date:** 2026-07-19
**Run type:** Scheduled cron (DM Function Calling roadmap complete; content/registry expansion pass)
**Status:** ✅ COMPLETE — all checks green, committed and pushed

---

## Summary

The DM Function Calling roadmap has been complete since 2026-07-17. Per the
standing directive ("pick up any quick fixes / content registry expansions if
surfaced"), this run surveyed the spell catalogue for the next PHB-completeness
gap and closed it: **Level 6 was the thinnest tier relative to the Player's
Handbook** (12 of 31 PHB spells registered — the worst coverage ratio of any
tier). This run registers all **19 missing PHB 6th-level spells**, lifting the
tier to 31/31 PHB-complete and the catalogue to **205 spells**.

This is the same PHB-completeness treatment that levels 7/8/9, level 1, the
high-tier enemy registry, and the 5 CR-corrections already received. It follows
the established file-level pattern (3 resolution-path groups, effects-in-
description convention for non-standard mechanics, parametrized test file
mirroring `test_spell_level7_8_completion.py`).

---

## What shipped

### 19 new spells (`backend/app/engine/spells.py`)
Grouped by resolution path, all canonical PHB p.225-238:

- **Damage / save-for-half (3):**
  - `Blade Barrier` — 6d10 slashing, Dex save, concentration, 10-min wall
  - `Otiluke's Freezing Sphere` — 10d6 cold, Dex save, **+1d6/slot upcast**
  - `Wall of Thorns` — 7d8 slashing, Dex save, **+1d8/slot upcast**, concentration

- **Save-debuff, no damage (3):**
  - `Eyebite` — Wis save, concentration; three modes (Asleep/Sickened/Panicked) in description
  - `Magic Jar` — Cha save; possession mechanic in description
  - `Mass Suggestion` — Wis save, concentration; up to 12 targets

- **Utility / buff / ritual / summon (13):**
  - `Arcane Gate` (concentration portal pair)
  - `Conjure Fey` (concentration summon)
  - `Contingency` (10-day delayed trigger — no concentration, PHB exception)
  - `Create Undead` (no-concentration summon)
  - `Drawmij's Instant Summons` (ritual — only new ritual in the batch)
  - `Find the Path` (concentration divination)
  - `Guards and Wards` (24-hour multi-ward)
  - `Move Earth` (iconic **2-hour** casting time)
  - `Planar Ally` (bargained summon)
  - `Programmed Illusion` (Investigation check, not a save)
  - `Transport via Plants` (plant-gate)
  - `Wind Walk` (party mist-form, 300 ft fly)
  - `Word of Recall` (sanctuary teleport)

### Test file (`backend/tests/test_spell_level6_completion.py`, NEW, 66 tests)
Mirrors `test_spell_level7_8_completion.py`:
- Registry distribution (total ≥205, level 6 ≥31, no-dup, no-key-collision guards)
- **PHB roster completeness** — asserts all 31 PHB 6th-level spells are registered
- Parametrized registration-shape (name/level/school for all 19)
- Per-spell mechanical correctness — damage dice + save + concentration +
  upcasting on the 3 damage spells; save ability + concentration + no-damage
  on the 3 save-debuff spells; casting time / duration / range / ritual-flag /
  concentration-flag on all 13 utility spells (including Move Earth's 2-hour
  cast and Contingency's 10-day duration)
- Effect resolution — damage range + save outcome for the damage spells,
  made_save for the save-debuff spells, "takes effect" path for all 13 utility
- Upcasting math — dice count grows by the configured `at_higher_levels_dice`
  per slot level (deterministic — no flaky random-value assertions)

### Docs
- `PROGRESS.md` — status line counts (186→205 spells, 3438→3504 backend
  tests, +PHB LEVEL-6 SPELL COMPLETION (12→31) tag) and a new
  `## ✅ COMPLETED: PHB Level-6 Spell Completion` section at the top with the
  full file-level breakdown, correct-mechanics decisions, and tier snapshot.
- `README.md` — three count bumps (Spell System feature line, Game Rules
  Coverage line, Test Suite line: 3438→3504 / 3831→3897 total), the Content
  bullet (186→205 spells, updated tier snapshot), and a new "Recently
  Completed" entry.

---

## Verification

| Check | Result |
|-------|--------|
| `uv run pytest` | ✅ **3504 backend tests passing** (+66), 0 failures |
| `npm test` | ✅ **393 frontend tests passing** (no frontend changes) |
| `npx tsc --noEmit` | ✅ clean |
| `npm run build` | ✅ clean (2.42s) |

Pre-existing floor guards (`test_spell_level1_completion.py` ≥186,
`test_spell_level7_8_completion.py` ≥154, `test_spell_high_level_expansion.py`
≥133) all still pass — they use `>=` floors, so additions don't break them.

### One flaky test caught and fixed
The first suite run flagged `TestUpcasting::test_otilukes_freezing_sphere_upcast_adds_dice`
as failing — but only in the full-suite run, not in isolation. Root cause: the
original assertion compared two random `roll_damage()` results
(`assert upcast - base >= 2`), which is wrong because dice are random (a max-
roll base can exceed a min-roll upcast). Replaced with a deterministic dice-
count math assertion (the actual invariant we care about). Same lesson as the
flaky-test fix in `c72b96a` (Mordenkainen's Sword attack-roll).

---

## Spell tier snapshot after this run

```
{0:14, 1:53, 2:16, 3:13, 4:14, 5:13, 6:31, 7:18, 8:18, 9:15}  →  TOTAL: 205
```

- **PHB-complete tiers:** 1 (53), 6 (31), 7 (18), 8 (18), 9 (15) — five of ten
- **Every tier ≥ 13** (was ≥12; level 6 lifted the floor)
- Level 6 (31) is now the **second-densest tier** behind level 1 (53),
  reflecting PHB's own weight at the level where wizard/sorcerer/cleric lists
  all hit signature spells (Disintegrate, Heal, Chain Lightning, Word of
  Recall, Heroes' Feast).
- Remaining non-canonical tiers (0, 2-5) are curated subsets, not exhaustive —
  level 3 (13) and level 5 (13) are the next-thinnest if a future run wants to
  continue toward PHB completeness.

---

## Architectural decisions worth recording

1. **Eyebite as Wis-save concentration** — PHB p.238 specifies a Wisdom save
   on each turn's target (not "no save" as is sometimes misremembered). All
   three modes (Asleep/Sickened/Panicked) flow through the same Wis save.
2. **Magic Jar as Cha-save** — possession is governed by a Charisma save; the
   body/jar mechanic lives in the description (mirrors how Symbol, Divine Word,
   Hold Person, etc. handle multi-mode effects).
3. **Contingency is the canonical no-concentration long-duration exception** —
   10-day duration with `concentration=False`. This is intentional PHB design
   (the stored spell is released by a trigger, not maintained by concentration)
   and is now preserved in the registry rather than normalized to a
   concentration spell.
4. **Move Earth's 2-hour casting time** is the longest cast in the catalogue
   and a recognizable PHB signature — preserved as-is.
5. **No new rituals beyond Drawmij's Instant Summons** — the other 18 spells
   are non-ritual per PHB.

---

## What the next run should pick up

Per the standing post-roadmap directive ("Keep the full suite green; watch for
README/PROGRESS drift; pick up any quick fixes / content registry expansions if
surfaced"):

1. **Suite health** — green now (3504 BE + 393 FE). Re-verify on next run.
2. **README/PROGRESS drift** — synced this run (counts bumped in 4 places,
   completion section + Recently Completed entry added). Check again next run.
3. **Content registry candidates** (if a future run wants to continue):
   - **PHB level-3 completion** — level 3 currently 13/41 (the next-thinnest
     tier relative to PHB; PHB has 41 level-3 spells including Animate Dead,
     Bestow Curse, Clairvoyance, Counterspell is already in, Crusader's Mantle,
     Dispel Magic is already in, Elemental Weapon, Fear is in, Feign Death,
     Gaseous Form, Glyph of Warding, Haste is in, Lightning Bolt is in, Mass
     Healing Word is in, Meld into Stone, Nondetection, Phantom Steed, Plant
     Growth, Protection from Energy, Remove Curse, Revivify is in, Sending,
     Sleet Storm, Speak with Dead, Spirit Guardians is in, Stinking Cloud is
     in, Tongues, Vampiric Touch, Water Walk, Wind Wall, etc.)
   - **PHB level-5 completion** — level 5 currently 13/~25 (also thin)
   - **PHB level-2 completion** — level 2 currently 16/34
   - **PHB level-4 completion** — level 4 currently 14/25
   - **Cantrip expansion** — level 0 currently 14 (curated subset of ~46 PHB)
4. **No DM Function Calling work is pending** — the roadmap is complete. The
   only outstanding roadmap item is **Phase 6 (Story State)**, which is held
   until Mike explicitly green-lights it.

---

## Commit

`feat: PHB level-6 spell completion — 19 iconic spells (186→205, level 6: 12→31)`

Files: `backend/app/engine/spells.py`, `backend/tests/test_spell_level6_completion.py` (new),
`PROGRESS.md`, `README.md`. Pushed to `develop`.
