# Dev Agent Report — PHB Subclass Completion

**Run:** scheduled cron (dev agent)
**Date:** 2026-07-19
**Status:** ✅ COMPLETE — full PHB subclass coverage shipped, suite green

---

## Summary

The DM Function Calling roadmap is complete and all eleven PHB spell tiers
(0–9) are PHB-complete, so this run closed the **last remaining
non-PHB-canonical content registry: subclasses.** The engine previously
modelled a *representative* 29 subclasses (2–3 per core class); the Player's
Handbook ships a canonical **40** across the twelve core classes. This run
registered **all 11 missing PHB subclasses** so that **every Player's
Handbook subclass is now modelled** (29 → 40 = full PHB coverage), and
hardened a latent flaky attack-roll test that surfaced during verification.

## What shipped

### 1. PHB Subclass Completion (29 → 40 — all twelve core classes PHB-complete)

Added **11 missing PHB subclasses** to `backend/app/engine/subclasses.py`:

- **Cleric — 4 Divine Domains** (now 7/7 PHB): Light Domain, Nature Domain,
  Tempest Domain, Trickery Domain. Each lands features at the canonical
  Divine Domain stops (1/2/6/8/17), grants Divine Strike at 8 with its
  canonical damage rider (radiant / cold-fire-lightning / thunder / poison),
  and names Channel Divinity exactly per PHB.
- **Monk — 1 Monastic Tradition** (now 3/3 PHB): Way of the Four Elements —
  the Ki-discipline monk (Disciple of the Elements + iconic PHB discipline
  names documented).
- **Wizard — 6 Arcane Traditions / Schools** (now 8/8 PHB): School of
  Conjuration, Divination, Enchantment, Illusion, Necromancy, Transmutation.
  Each lands features at the canonical Arcane Tradition stops (2/6/10/14)
  and grants Savant at 2.

Per-class PHB-completeness snapshot (the milestone):
```
{barbarian:2, bard:2, cleric:7, druid:2, fighter:3, monk:3, paladin:3,
 ranger:2, rogue:3, sorcerer:2, warlock:3, wizard:8} = 40 total
```
**Every core class is now at its full PHB subclass count.** This was the
last non-PHB-canonical content registry after the catalogue-wide PHB spell
completeness effort finished at every tier.

### 2. Flaky-test hardening (bonus)

While running the full suite, `test_thorn_whip_attacks_hit_and_miss` (and
its sibling `test_produce_flame_attacks_hit_and_miss`) in
`test_spell_cantrip_completion.py` surfaced a **latent flake**: both used
`d20+7 vs AC 10`, which still misses on a natural 1/2/3 (15% chance). The
Thorn Whip test lost that coin-flip on the first suite run. Applied the
established `_force_d20` monkeypatch pattern (already used by the level-2 /
level-7-8 completion tests) to force deterministic hit/miss die faces.
Verified stable across 5× consecutive runs of the cantrip file. This is the
same flake class the PROGRESS log already recorded fixing for Flame Blade /
Spiritual Weapon.

## Files changed

- **`backend/app/engine/subclasses.py`** — 11 new `Subclass(...)` entries:
  4 appended to the Cleric (Divine Domain) block after Knowledge Domain,
  1 appended to the Monk (Monastic Tradition) block after Way of Shadow,
  6 appended to the Wizard (Arcane Tradition) block after School of
  Abjuration. Registry total 29 → 40. (No engine-logic changes — pure data
  registration following the existing pattern.)
- **`backend/tests/test_subclass_phb_completion.py`** (NEW, ~185 tests) —
  registry distribution (total ≥40, the all-twelve-classes-PHB-complete
  milestone, per-class PHB counts, no-dup guards), parametrized
  registration-shape (name/char_class/category/id for all 11),
  per-subclass mechanical correctness (feature progressions land at PHB
  stops; first feature at choice level; signature feature names present;
  cleric Divine Strike at 8; wizard Savant at 2; `to_dict` shape), lookups
  (case-insensitive get, class listing membership), validation (valid at
  choice level, rejects below choice level, `can_choose_subclass`), and
  DM-context helper sanity.
- **`backend/tests/test_spell_cantrip_completion.py`** — added the
  `_force_d20` helper to `TestEffectResolution` and wired it into both
  attack-roll hit/miss tests (Produce Flame + Thorn Whip), making them
  deterministic. No assertion changes.
- **`PROGRESS.md`** — new `## ✅ COMPLETED: PHB Subclass Completion`
  section at the top; updated status line (test count 3944→4129, subclass
  count 29→40 PHB-complete, new completion tag).
- **`README.md`** — synced: Content section (29→40 Subclasses PHB-complete),
  Game Rules Coverage (29→40 subclasses), Current Status test count
  (4337→4522 total), new "Recently Completed" entry for the subclass
  completion.

## Tests

- **Backend:** 4129 passing (was 3944) — **+185**. 0 failures.
- **Frontend:** 393 passing (unchanged — no frontend changes). 0 failures.
- **TypeScript:** `npx tsc --noEmit` clean.
- **Flake check:** cantrip effect-resolution tests stable across 5×
  consecutive runs (the `d20+7 vs AC 10` flake is eliminated).

## Verification commands run

```bash
uv run pytest                          # 4129 passed, 0 failures
cd frontend && npm test                # 393 passed, 0 failures
cd frontend && npx tsc --noEmit        # clean
# (cantrip file run 5× to confirm flake eliminated)
```

## Architectural decisions

- **Pure data registration, no engine-logic change.** The subclass engine
  already modelled the full lifecycle (choice level, validation, feature
  progression, DM-context summary). The 11 additions are pure data entries
  following the established `Subclass(...)` pattern — no new code paths,
  which is why the existing API + DM-context tests all pass unchanged.
- **Feature progressions follow PHB per choice tier.** Cleric domains:
  1/2/6/8/17 (Divine Domain, PHB p.56-61). Monk: 3/6/11/17 (Monastic
  Tradition, PHB p.77). Wizard: 2/6/10/14 (Arcane Tradition, PHB p.115).
  Every new subclass's first feature lands at the class's choice level —
  asserted by the test suite.
- **Divine Strike at 8 for all four new cleric domains** (every PHB domain
  gets it), each with its canonical damage rider matching PHB p.56-61.
- **Savant at 2 for all six new wizard schools** (every PHB school gets the
  gold/time-copying discount).
- **Names match PHB exactly** so the in-game subclass picker and the DM
  context line present canonical PHB labels.

## Next run should pick up

The DM Function Calling roadmap is complete and every content registry is
now PHB-canonical (spells 0–9, subclasses, the lot). Per the standing
NEXT SESSION DIRECTIVE in PROGRESS.md, until the next staged feature is
green-lit the dev agent should:

- Keep the full suite green (`uv run pytest`, `npm test`)
- Watch for README/PROGRESS drift and sync them
- Pick up any quick fixes / content registry expansions if surfaced

Candidate directions (require Mike's green-light before substantive work):
- **Multiplayer foundation (#13)** — party/session model + WebSocket
  fan-out (large, multi-session)
- **Phase 6 — Story State** — `set_story_flag` / `offer_quest` as explicit
  engine-resolved game_actions (quest detection + game flags already exist
  heuristically; wiring them as resolvable game_actions would make them
  engine-driven)

## Commit

`feat: PHB subclass completion — 11 subclasses (29→40, all twelve core classes now PHB-complete)`
