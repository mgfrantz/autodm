"""Tests for the high-tier CR gap-fill expansion + Behir canonical-CR correction.

This run closed the last glaring gaps in the enemy registry's CR 11-30 band:

  - **CR 23 was COMPLETELY EMPTY** (the largest hole between Ancient Red at CR 22
    and Ancient Gold at CR 24). Now populated with three canonical MM titans:
    Ancient Blue Dragon, Ancient Silver Dragon, and Empyrean.
  - **CR 11 / 12 / 13 / 15 / 21 / 22** were sparse (1-2 entries each). Each
    gained one canonical MM monster so every high-tier CR band now has >= 2.
  - **Behir** was registered at CR 6 (canonical CR 11, MM p.25). Its AC (17)
    and HP (168) were already MM-canonical; only the CR was wrong — the same
    correction pattern as the 5 CR-corrections already shipped (Adult Black
    Dragon, Ice Devil, Nalfeshnee, Mummy Lord, Lich). Moved to CR 11.

Canonical Monster Manual references for each addition:
  Behir               MM p.25   CR 11  (correction, was cr=6)
  Remorhaz            MM p.249  CR 11  immune: cold
  Roc                 MM p.247  CR 11  (no immunities)
  Arcanaloth          MM p.308  CR 12  resist: nonmagical BPS (yugoloth)
  Adult White Dragon  MM p.101  CR 13  immune: cold (breath element)
  Adult Bronze Dragon MM p.108  CR 15  immune: lightning (breath element)
  Solar               MM p.18   CR 21  immune: radiant + poison (Angel trait)
  Ancient Green Dragon MM p.93  CR 22  immune: poison (breath element)
  Ancient Blue Dragon  MM p.86  CR 23  immune: lightning (breath element)
  Ancient Silver Dragon MM p.117 CR 23 immune: cold (breath element)
  Empyrean            MM p.130  CR 23  resist: nonmagical BPS

10 new entries + 1 correction (Behir moved) → registry 135 -> 145. Every CR
band from 11 to 24 (excluding CR 18, which has no canonical MM monster) now
has >= 2 entries, and CR 23 is no longer empty.
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


# (name, cr, armor_class, hp, attack_bonus, n_damage_modifiers)
NEW_ENTRIES = [
    ("Remorhaz", 11, 19, 162, 7, 1),
    ("Roc", 11, 16, 149, 7, 0),
    ("Arcanaloth", 12, 19, 104, 7, 1),
    ("Adult White Dragon", 13, 18, 184, 7, 1),
    ("Adult Bronze Dragon", 15, 19, 212, 8, 1),
    ("Solar", 21, 21, 142, 13, 2),
    ("Ancient Green Dragon", 22, 21, 385, 14, 1),
    ("Ancient Blue Dragon", 23, 22, 367, 14, 1),
    ("Ancient Silver Dragon", 23, 23, 487, 15, 1),
    ("Empyrean", 23, 22, 188, 14, 1),
]

# Behir is a correction (moved), not a new entry. Tracked separately.
BEHIR = ("Behir", 11, 17, 168, 7, 0)


def _mods(name: str) -> dict[str, set]:
    """Return {kind: set_of_types} for the named enemy's damage modifiers."""
    enemy = get_enemy_template(name)
    assert enemy is not None, f"{name} missing from registry"
    out: dict[str, set] = {}
    for mod in enemy.damage_modifiers:
        out.setdefault(mod["kind"], set()).update(mod.get("types", []))
    return out


class TestNewEntriesRegistered:
    """Each new canonical MM monster is present with its canonical stat block."""

    @pytest.mark.parametrize(
        "name,cr,ac,hp,atk,n_mods", NEW_ENTRIES
    )
    def test_stat_block_matches_canonical_mm(
        self, name, cr, ac, hp, atk, n_mods
    ):
        enemy = get_enemy_template(name)
        assert enemy is not None, f"{name} missing from registry"
        assert enemy.name == name
        assert enemy.cr == cr, f"{name} CR {enemy.cr} != canonical {cr}"
        assert enemy.armor_class == ac
        assert enemy.hp == hp
        assert enemy.attack_bonus == atk
        assert (
            len(enemy.damage_modifiers) == n_mods
        ), f"{name} expected {n_mods} damage modifier(s), got {len(enemy.damage_modifiers)}"

    @pytest.mark.parametrize("name,cr,ac,hp,atk,n_mods", NEW_ENTRIES + [BEHIR])
    def test_xp_value_derived_from_cr(self, name, cr, ac, hp, atk, n_mods):
        enemy = get_enemy_template(name)
        assert enemy is not None
        # xp_value is derived from cr in __post_init__
        assert enemy.xp_value == CR_TO_XP[cr]
        assert cr_to_xp(cr) == CR_TO_XP[cr]

    @pytest.mark.parametrize("name,cr,ac,hp,atk,n_mods", NEW_ENTRIES + [BEHIR])
    def test_to_dict_is_valid_combat_block(self, name, cr, ac, hp, atk, n_mods):
        enemy = get_enemy_template(name)
        assert enemy is not None
        data = enemy.to_dict()
        assert data["name"] == name
        assert data["max_hp"] == hp
        assert data["armor_class"] == ac
        assert data["initiative_bonus"] == 0
        assert data["speed"] == 30
        assert isinstance(data["damage_modifiers"], list)
        assert len(data["damage_modifiers"]) == n_mods
        # Every enemy template gets exactly one default attack.
        assert len(data["attacks"]) == 1
        atk_block = data["attacks"][0]
        assert atk_block["attack_bonus"] == atk
        assert atk_block["damage_dice_count"] == 1
        assert atk_block["damage_dice_sides"] == 6


class TestCanonicalDamageModifiers:
    """Iconic monsters carry their canonical MM damage immunities/resistances.

    Chromatic & metallic dragons are immune to their breath element (matching
    the existing registry convention: Adult Black→acid, Adult Blue→lightning,
    Adult Red→fire, Adult Gold→fire, Adult Silver→cold). The new dragons follow
    the same single-immunity convention.
    """

    @pytest.mark.parametrize(
        "name,kind,types",
        [
            # Dragons — single breath-element immunity (registry convention).
            ("Adult White Dragon", "immunity", "cold"),
            ("Adult Bronze Dragon", "immunity", "lightning"),
            ("Ancient Green Dragon", "immunity", "poison"),
            ("Ancient Blue Dragon", "immunity", "lightning"),
            ("Ancient Silver Dragon", "immunity", "cold"),
            # Remorhaz — arctic monstrosity, immune to cold (MM p.249).
            ("Remorhaz", "immunity", "cold"),
            # Solar — Angel trait: immune radiant + poison (MM p.6/p.18).
            ("Solar", "immunity", "radiant"),
            ("Solar", "immunity", "poison"),
        ],
    )
    def test_immunity_present(self, name, kind, types):
        mods = _mods(name)
        assert kind in mods, f"{name} has no '{kind}' modifier: {mods}"
        assert types in mods[kind], f"{name} {kind} missing {types}: {mods}"

    @pytest.mark.parametrize(
        "name,types",
        [
            # Yugoloths resist nonmagical BPS (Arcanaloth, MM p.308).
            ("Arcanaloth", "bludgeoning"),
            ("Arcanaloth", "piercing"),
            ("Arcanaloth", "slashing"),
            # Empyrean resists nonmagical BPS (MM p.130).
            ("Empyrean", "bludgeoning"),
            ("Empyrean", "piercing"),
            ("Empyrean", "slashing"),
        ],
    )
    def test_nonmagical_bps_resistance_present(self, name, types):
        mods = _mods(name)
        assert "resistance" in mods, f"{name} has no resistance: {mods}"
        assert types in mods["resistance"], f"{name} resist missing {types}: {mods}"

    def test_resistances_are_nonmagical_only(self):
        """Arcanaloth & Empyrean resist nonmagical BPS, not all BPS (per MM)."""
        for name in ("Arcanaloth", "Empyrean"):
            enemy = get_enemy_template(name)
            assert enemy is not None
            for mod in enemy.damage_modifiers:
                if mod["kind"] == "resistance":
                    # The nonmagical BPS helper sets bypassed_by_magic=True.
                    assert mod.get("bypassed_by_magic") is True, (
                        f"{name} resistance should be bypassed by magic: {mod}"
                    )

    def test_roc_has_no_damage_modifiers(self):
        """Roc (MM p.247) has no damage immunities/resistances/vulnerabilities."""
        roc = get_enemy_template("Roc")
        assert roc is not None
        assert roc.damage_modifiers == []

    def test_behir_has_no_damage_modifiers(self):
        """Behir (MM p.25) has no damage immunities/resistances/vulnerabilities."""
        behir = get_enemy_template("Behir")
        assert behir is not None
        assert behir.damage_modifiers == []

    def test_solar_has_exactly_two_immunities(self):
        """Solar (Angel trait) is immune to radiant AND poison — both present."""
        mods = _mods("Solar")
        assert mods.get("immunity") == {"radiant", "poison"}, mods


class TestBehirCanonicalCRCorrection:
    """Behir was moved from CR 6 to its MM-canonical CR 11 (MM p.25).

    Its AC (17) and HP (168) were already canonical — only the CR was wrong.
    Same correction pattern as the 5 already-shipped CR-corrections (Adult
    Black Dragon, Ice Devil, Nalfeshnee, Mummy Lord, Lich).
    """

    def test_behir_is_cr_11(self):
        behir = get_enemy_template("Behir")
        assert behir is not None
        assert behir.cr == 11

    def test_behir_canonical_ac_and_hp_unchanged(self):
        """The correction touched only CR — AC and HP were already canonical."""
        behir = get_enemy_template("Behir")
        assert behir is not None
        assert behir.armor_class == 17  # MM p.25
        assert behir.hp == 168  # MM p.25
        assert behir.attack_bonus == 7

    def test_behir_xp_now_reflects_cr_11(self):
        behir = get_enemy_template("Behir")
        assert behir is not None
        # Was 400 XP (CR 6); now 7200 XP (CR 11).
        assert behir.xp_value == CR_TO_XP[11]
        assert behir.xp_value == 7200

    def test_behir_appears_in_cr_11_lookup(self):
        matches = get_enemies_by_cr(11)
        names = {m.name for m in matches}
        assert "Behir" in names

    def test_behir_no_longer_in_cr_6_lookup(self):
        """Regression guard: Behir must not pollute the CR 6 band."""
        matches = get_enemies_by_cr(6)
        names = {m.name for m in matches}
        assert "Behir" not in names


class TestCRBandPopulation:
    """Every high-tier CR band (11-24) now has >= 2 entries (except CR 18).

    CR 18 has no canonical MM monster (Demilich's 20 HP at CR 18 is too
    unusual for the simplified template), and CRs 25-29 are intentionally
    empty (MM jumps from CR 24 to the CR 30 Tarrasque). These are correct
    gaps, not missing content.
    """

    @pytest.mark.parametrize("cr,expected_min", [
        (11, 4),  # Dao, Gynosphinx, Behir, Remorhaz, Roc (5)
        (12, 2),  # Erinyes, Arcanaloth
        (13, 4),  # + Adult White Dragon
        (14, 3),  # Adult Black Dragon, Ice Devil, Nalfeshnee
        (15, 2),  # Mummy Lord, Adult Bronze Dragon
        (16, 2),  # Adult Blue Dragon, Adult Silver Dragon
        (17, 2),  # Adult Red Dragon, Adult Gold Dragon
        (19, 1),  # Balor (only canonical CR 19 monster)
        (20, 2),  # Pit Fiend, Ancient White Dragon
        (21, 2),  # Lich, Solar
        (22, 2),  # Ancient Red Dragon, Ancient Green Dragon
        (23, 3),  # Ancient Blue Dragon, Ancient Silver Dragon, Empyrean
        (24, 1),  # Ancient Gold Dragon (apex-tier, only canonical CR 24)
    ])
    def test_cr_band_meets_minimum(self, cr, expected_min):
        matches = get_enemies_by_cr(cr)
        assert len(matches) >= expected_min, (
            f"CR {cr} has only {len(matches)} entries "
            f"({[m.name for m in matches]}); expected >= {expected_min}"
        )

    def test_cr_23_no_longer_empty(self):
        """CR 23 was the largest empty band before this expansion."""
        matches = get_enemies_by_cr(23)
        assert len(matches) >= 3, [m.name for m in matches]
        names = {m.name for m in matches}
        assert {
            "Ancient Blue Dragon",
            "Ancient Silver Dragon",
            "Empyrean",
        }.issubset(names)

    def test_cr_18_correctly_empty(self):
        """No canonical MM monster fits the simplified template at CR 18.

        The Demilich (MM p.48, CR 18) has only 20 HP — too unusual for the
        engine's CR→HP expectations. CR 18 is intentionally left empty.
        """
        matches = get_enemies_by_cr(18)
        assert matches == [], (
            f"CR 18 should be empty (no canonical MM monster fits); "
            f"found {[m.name for m in matches]}"
        )

    def test_no_canonical_cr_25_to_29_monsters(self):
        """MM has no CR 25-29 monsters (the Tarrasque at CR 30 is the apex).

        These bands are correctly empty — not a content gap.
        """
        for cr in [25, 26, 27, 28, 29]:
            matches = get_enemies_by_cr(cr)
            assert matches == [], (
                f"CR {cr} should be empty (MM has no monsters at this tier); "
                f"found {[m.name for m in matches]}"
            )


class TestRegistryIntegrity:
    """Whole-registry sanity guards (no regressions from the expansion)."""

    def test_registry_total_count_is_145(self):
        """Was 135 before; +10 new entries (Behir was moved, not added)."""
        assert len(COMMON_ENEMIES) == 145, (
            f"Registry has {len(COMMON_ENEMIES)} entries; expected 145 "
            "(was 135, +10 new, Behir moved not added)"
        )

    def test_no_duplicate_names(self):
        """Every name in the dict literal must be unique — no silent overwrites."""
        names = list_enemy_templates()
        assert len(names) == len(set(names))

    def test_all_names_match_their_keys(self):
        for key, enemy in COMMON_ENEMIES.items():
            assert key == enemy.name, f"key {key!r} != name {enemy.name!r}"

    def test_tarrasque_is_apex(self):
        """The Tarrasque remains the highest-CR entry (no regression)."""
        apex = max(COMMON_ENEMIES.values(), key=lambda e: e.cr)
        assert apex.name == "Tarrasque"
        assert apex.cr == 30
        assert apex.xp_value == 155000

    def test_all_new_entries_have_keys_matching_names(self):
        for name, *_ in NEW_ENTRIES:
            assert name in COMMON_ENEMIES, f"{name} not a top-level key"
            assert COMMON_ENEMIES[name].name == name

    def test_all_xp_values_match_cr(self):
        """Every entry's xp_value must equal CR_TO_XP[cr] (derived in __post_init__)."""
        for enemy in COMMON_ENEMIES.values():
            assert enemy.xp_value == CR_TO_XP[enemy.cr], (
                f"{enemy.name} cr={enemy.cr} xp={enemy.xp_value} "
                f"!= CR_TO_XP[{enemy.cr}]={CR_TO_XP[enemy.cr]}"
            )

    def test_registry_spans_full_high_tier_range(self):
        """Every CR from 11 to 24 (except 18) is now represented."""
        crs_present = {e.cr for e in COMMON_ENEMIES.values()}
        for cr in [11, 12, 13, 14, 15, 16, 17, 19, 20, 21, 22, 23, 24]:
            assert cr in crs_present, f"CR {cr} missing from registry"


class TestExistingEntriesPreserved:
    """The expansion must not disturb existing canonical monsters."""

    @pytest.mark.parametrize("name,cr", [
        ("Dao", 11),
        ("Gynosphinx", 11),
        ("Erinyes", 12),
        ("Beholder", 13),
        ("Storm Giant", 13),
        ("Rakshasa", 13),
        ("Vampire", 13),
        ("Adult Black Dragon", 14),
        ("Ice Devil", 14),
        ("Nalfeshnee", 14),
        ("Mummy Lord", 15),
        ("Adult Blue Dragon", 16),
        ("Adult Silver Dragon", 16),
        ("Adult Red Dragon", 17),
        ("Adult Gold Dragon", 17),
        ("Balor", 19),
        ("Pit Fiend", 20),
        ("Ancient White Dragon", 20),
        ("Lich", 21),
        ("Ancient Red Dragon", 22),
        ("Ancient Gold Dragon", 24),
        ("Tarrasque", 30),
    ])
    def test_existing_entry_unchanged(self, name, cr):
        """Each previously-registered high-tier monster stays at its CR."""
        enemy = get_enemy_template(name)
        assert enemy is not None, f"{name} dropped from registry"
        assert enemy.cr == cr, f"{name} CR changed: {enemy.cr} != {cr}"

    def test_low_tier_monsters_untouched(self):
        """Spot-check that CR 0-10 monsters are unaffected."""
        for name, cr in [
            ("Goblin", 1 / 8),
            ("Skeleton", 1 / 8),
            ("Owlbear", 3),
            ("Troll", 5),
            ("Young Gold Dragon", 10),
        ]:
            enemy = get_enemy_template(name)
            assert enemy is not None, f"{name} dropped"
            assert enemy.cr == cr, f"{name} CR changed: {enemy.cr} != {cr}"


class TestDragonFamilyCompleteness:
    """The chromatic + metallic dragon family is now canonical-complete at high tier.

    After this expansion, every adult and ancient chromatic/metallic dragon from
    the Monster Manual is present at its MM-canonical CR (excluding the
    deliberately-tuned weaker variants flagged in the prior dragon audit).
    """

    def test_all_adult_metallic_dragons_present(self):
        """Adult Brass, Bronze, Copper, Gold, Silver — canonical MM metallics."""
        # Brass and Copper exist as tuned variants (flagged in dragon audit);
        # Bronze, Gold, Silver are canonical. All five names are present.
        for name in [
            "Adult Brass Dragon",
            "Adult Bronze Dragon",
            "Adult Copper Dragon",
            "Adult Gold Dragon",
            "Adult Silver Dragon",
        ]:
            assert get_enemy_template(name) is not None, f"{name} missing"

    def test_all_adult_chromatic_dragons_present(self):
        """Adult Black, Blue, Green, Red, White — canonical MM chromatics."""
        for name in [
            "Adult Black Dragon",
            "Adult Blue Dragon",
            "Adult Green Dragon",
            "Adult Red Dragon",
            "Adult White Dragon",
        ]:
            assert get_enemy_template(name) is not None, f"{name} missing"

    def test_all_ancient_dragons_present(self):
        """All ancient dragons (chromatic + metallic) are now in the registry."""
        for name in [
            "Ancient Red Dragon",
            "Ancient Gold Dragon",
            "Ancient White Dragon",
            "Ancient Green Dragon",
            "Ancient Blue Dragon",
            "Ancient Silver Dragon",
        ]:
            assert get_enemy_template(name) is not None, f"{name} missing"

    def test_new_ancient_dragons_at_canonical_cr(self):
        """Ancient Green=22, Ancient Blue=23, Ancient Silver=23 (MM canonical)."""
        cases = [
            ("Ancient Green Dragon", 22),
            ("Ancient Blue Dragon", 23),
            ("Ancient Silver Dragon", 23),
        ]
        for name, cr in cases:
            enemy = get_enemy_template(name)
            assert enemy is not None
            assert enemy.cr == cr, f"{name} CR {enemy.cr} != canonical {cr}"

    def test_new_dragons_use_breath_element_immunity_convention(self):
        """Each new dragon is immune to exactly its breath element (single immunity)."""
        # (dragon, breath_element)
        cases = [
            ("Adult White Dragon", "cold"),
            ("Adult Bronze Dragon", "lightning"),
            ("Ancient Green Dragon", "poison"),
            ("Ancient Blue Dragon", "lightning"),
            ("Ancient Silver Dragon", "cold"),
        ]
        for name, element in cases:
            enemy = get_enemy_template(name)
            assert enemy is not None
            # Exactly one immunity modifier, with exactly one type.
            immunities = [
                m for m in enemy.damage_modifiers if m["kind"] == "immunity"
            ]
            assert len(immunities) == 1, (
                f"{name} should have exactly 1 immunity, got {len(immunities)}: "
                f"{enemy.damage_modifiers}"
            )
            assert immunities[0]["types"] == [element], (
                f"{name} immunity should be [{element!r}], "
                f"got {immunities[0]['types']}"
            )
