"""Tests for the enemy CR-correction fix.

Five iconic canonical Monster Manual entries were previously registered at the
WRONG challenge rating — their AC (and, for 3 of them, HP) already matched the
MM canonical stat block, but the ``cr`` field was wrong. This broke
``get_enemies_by_cr`` lookups, awarded the wrong XP (derived from CR), skewed
encounter-difficulty math, and left the CR 14 / 15 / 21 bands completely empty
despite the canonical monsters "existing" at lower CRs.

The fix moves each to its MM-canonical CR:

  Adult Black Dragon  cr=7  -> 14   (MM p.88)   hp 147 -> 195
  Ice Devil (Gelugon) cr=8  -> 14   (MM p.80)   hp unchanged (180 ✓)
  Nalfeshnee          cr=10 -> 14   (MM p.56)   hp 212 -> 184
  Mummy Lord          cr=10 -> 15   (MM p.227)  hp unchanged (97 ✓)
  Lich                cr=10 -> 21   (MM p.202)  hp unchanged (135 ✓)

This also resolves an inconsistency: the legendary-creature registry
(``engine/legendary.py`` LICH preset) already documented the Lich at CR 21 —
both registries now agree.

Canonical damage immunities (each chromatic dragon is immune to its own breath
element; devils/demons to fire/cold/poison; undead to necrotic + poison) were
added to match the high-tier block's convention.

No entries were added or removed — total registry size is unchanged (135).
"""
from __future__ import annotations

import pytest

from app.engine.encounters import (
    COMMON_ENEMIES,
    CR_TO_XP,
    cr_to_xp,
    get_enemy_template,
    get_enemies_by_cr,
    list_enemy_templates,
)
from app.engine.legendary import get_legendary_creature

# (name, canonical_cr, armor_class, hp, attack_bonus)
CORRECTED_MONSTERS = [
    ("Adult Black Dragon", 14, 19, 195, 10),
    ("Ice Devil", 14, 18, 180, 8),
    ("Nalfeshnee", 14, 18, 184, 10),
    ("Mummy Lord", 15, 17, 97, 7),
    ("Lich", 21, 17, 135, 10),
]

# (name, kind, damage_type) — canonical MM immunities that must now be present.
CANONICAL_IMMUNITIES = [
    ("Adult Black Dragon", "immunity", "acid"),
    ("Ice Devil", "immunity", "cold"),
    ("Ice Devil", "immunity", "poison"),
    ("Nalfeshnee", "immunity", "fire"),
    ("Nalfeshnee", "immunity", "poison"),
    ("Mummy Lord", "immunity", "necrotic"),
    ("Mummy Lord", "immunity", "poison"),
    ("Lich", "immunity", "necrotic"),
    ("Lich", "immunity", "poison"),
]


def _mods(name: str) -> dict[str, set]:
    """Return {kind: set_of_types} for the named enemy's damage modifiers."""
    enemy = get_enemy_template(name)
    assert enemy is not None, f"{name} missing from registry"
    out: dict[str, set] = {}
    for mod in enemy.damage_modifiers:
        out.setdefault(mod["kind"], set()).update(mod.get("types", []))
    return out


class TestCorrectedChallengeRatings:
    """Each iconic monster now sits at its MM-canonical CR."""

    @pytest.mark.parametrize("name,cr,ac,hp,atk", CORRECTED_MONSTERS)
    def test_canonical_cr(self, name, cr, ac, hp, atk):
        enemy = get_enemy_template(name)
        assert enemy is not None, f"{name} missing from registry"
        assert enemy.cr == cr, f"{name} expected CR {cr}, got {enemy.cr}"

    @pytest.mark.parametrize("name,cr,ac,hp,atk", CORRECTED_MONSTERS)
    def test_canonical_ac_and_hp(self, name, cr, ac, hp, atk):
        enemy = get_enemy_template(name)
        assert enemy is not None
        assert enemy.armor_class == ac
        assert enemy.hp == hp

    @pytest.mark.parametrize("name,cr,ac,hp,atk", CORRECTED_MONSTERS)
    def test_attack_bonus_unchanged(self, name, cr, ac, hp, atk):
        """The CR/HP correction intentionally left attack_bonus as the existing
        baseline (consistent with the rest of the low/mid-CR registry, which
        uses tier-appropriate offensive baselines). Documenting it here so a
        future change is deliberate."""
        enemy = get_enemy_template(name)
        assert enemy is not None
        assert enemy.attack_bonus == atk

    @pytest.mark.parametrize("name,old_cr", [
        ("Adult Black Dragon", 7),
        ("Ice Devil", 8),
        ("Nalfeshnee", 10),
        ("Mummy Lord", 10),
        ("Lich", 10),
    ])
    def test_old_wrong_cr_is_gone(self, name, old_cr):
        """Regression guard: the previously-wrong CR is no longer recorded."""
        enemy = get_enemy_template(name)
        assert enemy is not None
        assert enemy.cr != old_cr, f"{name} still at the wrong CR {old_cr}"


class TestCanonicalImmunities:
    """Each corrected monster carries its canonical MM damage immunity."""

    @pytest.mark.parametrize("name,kind,types", CANONICAL_IMMUNITIES)
    def test_immunity_present(self, name, kind, types):
        mods = _mods(name)
        assert kind in mods, f"{name} has no '{kind}' modifier: {mods}"
        assert types in mods[kind], f"{name} {kind} missing {types}: {mods}"


class TestXpMatchesCorrectedCR:
    """XP (derived from CR in __post_init__) now matches the corrected CR."""

    @pytest.mark.parametrize("name,cr,ac,hp,atk", CORRECTED_MONSTERS)
    def test_xp_value_matches_cr(self, name, cr, ac, hp, atk):
        enemy = get_enemy_template(name)
        assert enemy is not None
        assert enemy.xp_value == CR_TO_XP[cr]
        assert cr_to_xp(cr) == CR_TO_XP[cr]

    def test_specific_canonical_xp_values(self):
        for name, expected in [
            ("Adult Black Dragon", 11500),
            ("Ice Devil", 11500),
            ("Nalfeshnee", 11500),
            ("Mummy Lord", 13000),
            ("Lich", 33000),
        ]:
            enemy = get_enemy_template(name)
            assert enemy is not None
            assert enemy.xp_value == expected


class TestCRBandPopulation:
    """The previously-empty CR 14 / 15 / 21 bands are now populated by the
    corrected canonical monsters (no new entries needed — the monsters already
    existed, just at the wrong CR)."""

    def test_cr14_has_three_canonical_entries(self):
        matches = get_enemies_by_cr(14)
        names = {m.name for m in matches}
        assert {"Adult Black Dragon", "Ice Devil", "Nalfeshnee"}.issubset(names)

    def test_cr15_has_mummy_lord(self):
        matches = get_enemies_by_cr(15)
        names = {m.name for m in matches}
        assert "Mummy Lord" in names

    def test_cr21_has_lich(self):
        matches = get_enemies_by_cr(21)
        names = {m.name for m in matches}
        assert "Lich" in names

    @pytest.mark.parametrize("cr", [14, 15, 21])
    def test_cr_band_no_longer_empty(self, cr):
        assert len(get_enemies_by_cr(cr)) >= 1, f"CR {cr} is empty again"


class TestNoRegressionOnSourceBands:
    """Removing the 5 misfiled monsters from CR 7 / 8 / 10 must not empty those
    bands — they each had many other residents."""

    @pytest.mark.parametrize("cr", [7, 8, 10])
    def test_source_band_still_populated(self, cr):
        matches = get_enemies_by_cr(cr)
        assert len(matches) >= 5, (
            f"CR {cr} depopulated after the correction: {len(matches)} left"
        )

    def test_cr7_residents_intact(self):
        names = {m.name for m in get_enemies_by_cr(7)}
        # canonical CR 7 monsters that must remain
        for n in ["Bodak", "Bone Devil", "Couatl", "Fire Giant"]:
            assert n in names, f"{n} dropped from CR 7"

    def test_cr8_residents_intact(self):
        names = {m.name for m in get_enemies_by_cr(8)}
        for n in ["Medusa", "Hezrou", "Glabrezu"]:
            assert n in names, f"{n} dropped from CR 8"

    def test_cr10_residents_intact(self):
        names = {m.name for m in get_enemies_by_cr(10)}
        for n in ["Young Gold Dragon", "Marilith", "Barbed Devil"]:
            assert n in names, f"{n} dropped from CR 10"


class TestLichRegistryConsistency:
    """The encounters.py Lich and the legendary.py Lich boss preset must agree
    on CR — they previously contradicted (10 vs 21)."""

    def test_encounters_lich_cr_matches_legendary_lich_cr(self):
        enc_lich = get_enemy_template("Lich")
        leg_lich = get_legendary_creature("lich")
        assert enc_lich is not None
        assert leg_lich is not None
        assert enc_lich.cr == leg_lich.cr == 21

    def test_encounters_lich_hp_matches_legendary_lich_hp(self):
        enc_lich = get_enemy_template("Lich")
        leg_lich = get_legendary_creature("lich")
        assert enc_lich is not None
        assert leg_lich is not None
        # Both use the MM canonical 135 HP.
        assert enc_lich.hp == leg_lich.max_hp == 135

    def test_encounters_lich_ac_matches_legendary_lich_ac(self):
        enc_lich = get_enemy_template("Lich")
        leg_lich = get_legendary_creature("lich")
        assert enc_lich is not None
        assert leg_lich is not None
        assert enc_lich.armor_class == leg_lich.armor_class == 17


class TestRegistryIntegrityPreserved:
    """The correction moved entries, it did not add or remove any."""

    def test_total_count_unchanged(self):
        # 135 before and after — no entries lost to a key collision.
        assert len(COMMON_ENEMIES) == 135

    def test_no_duplicate_names(self):
        names = list_enemy_templates()
        assert len(names) == len(set(names))

    def test_all_keys_match_names(self):
        for key, enemy in COMMON_ENEMIES.items():
            assert key == enemy.name, f"key {key!r} != name {enemy.name!r}"

    def test_tarrasque_still_apex(self):
        apex = max(COMMON_ENEMIES.values(), key=lambda e: e.cr)
        assert apex.name == "Tarrasque"
        assert apex.cr == 30

    @pytest.mark.parametrize("name,cr,ac,hp,atk", CORRECTED_MONSTERS)
    def test_corrected_to_dict_is_valid_combat_block(self, name, cr, ac, hp, atk):
        enemy = get_enemy_template(name)
        assert enemy is not None
        data = enemy.to_dict()
        assert data["name"] == name
        assert data["max_hp"] == hp
        assert data["armor_class"] == ac
        assert isinstance(data["damage_modifiers"], list)
        assert len(data["damage_modifiers"]) >= 1  # all now carry immunities
        assert len(data["attacks"]) == 1
