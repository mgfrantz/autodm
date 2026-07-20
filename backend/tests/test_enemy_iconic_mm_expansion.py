"""Tests for the iconic-Monster-Manual enemy registry gap-fill expansion.

This run closed the registry's **iconic-monster gap** — the catalogue was
PHB-complete for spells, subclasses, and feats, and canonical-complete for the
dragon family at every CR tier, but was missing many of the most-played
Monster Manual monsters (Orc, Gnoll, Ghoul, Mimic, Mind Flayer, Aboleth, the
entire Golem family, Purple Worm, etc.). It adds **24 canonical MM monsters**
inline into their proper CR bands (registry 145 → 169).

Canonical Monster Manual references for each addition:

  Humanoids / undead staples
    Orc                 MM p.246  CR 1/2  (no immunities)
    Gnoll               MM p.163  CR 1/2  (no immunities)
    Ghoul               MM p.148  CR 1    immune: poison
    Specter             MM p.279  CR 1    immune: poison; resist nonmagical BPS

  Monstrosities / aberrations
    Mimic               MM p.220  CR 2    immune: acid
    Griffon             MM p.174  CR 2    (no immunities)
    Displacer Beast     MM p.81   CR 3    (no immunities)
    Manticore           MM p.213  CR 3    (no immunities)
    Hell Hound          MM p.182  CR 3    immune: fire
    Doppelganger        MM p.82   CR 3    (no immunities)
    Banshee             MM p.23   CR 4    immune: necrotic + poison; resist nmg BPS
    Ettin               MM p.132  CR 4    (no immunities)
    Wraith              MM p.302  CR 5    immune: cold + necrotic + poison; resist nmg BPS
    Unicorn             MM p.293  CR 5    (no immunities)
    Water Elemental     MM p.125  CR 5    immune: poison; resist acid
    Wyvern              MM p.303  CR 6    (no immunities)
    Mind Flayer         MM p.221  CR 7    (no immunities — iconic aberration)
    Purple Worm         MM p.255  CR 15   (no immunities)

  Constructs / plant (Golem family + Treant)
    Flesh Golem         MM p.169  CR 5    immune: nonmagical BPS + lightning + poison
    Clay Golem          MM p.168  CR 9    immune: nonmagical BPS + acid + poison
    Treant              MM p.289  CR 9    (no immunities)
    Stone Golem         MM p.170  CR 10   immune: nonmagical BPS + poison + psychic
    Iron Golem          MM p.170  CR 16   immune: nonmagical BPS + fire + poison

  Aberration (high CR)
    Aboleth             MM p.13   CR 10   (no immunities)

CR/AC/HP follow the printed MM stat blocks; ``attack_bonus`` is the monster's
primary-attack to-hit (Str/Dex mod + proficiency by CR), matching the
registry's existing convention (e.g. Tarrasque Str 30 + prof +9 = +19). 24 new
entries → registry 145 -> 169.
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
    # CR 1/2 — iconic humanoid staples
    ("Orc", 1 / 2, 13, 15, 5, 0),
    ("Gnoll", 1 / 2, 15, 22, 4, 0),
    # CR 1 — iconic undead staples
    ("Ghoul", 1, 12, 12, 2, 1),
    ("Specter", 1, 12, 22, 4, 2),
    # CR 2 — iconic trap-monster + mount
    ("Mimic", 2, 12, 58, 5, 1),
    ("Griffon", 2, 12, 59, 5, 0),
    # CR 3 — iconic gap-fill
    ("Displacer Beast", 3, 13, 85, 6, 0),
    ("Manticore", 3, 14, 68, 5, 0),
    ("Hell Hound", 3, 15, 45, 5, 1),
    ("Doppelganger", 3, 14, 52, 6, 0),
    # CR 4 — undead + giant
    ("Banshee", 4, 12, 58, 6, 3),
    ("Ettin", 4, 13, 85, 7, 0),
    # CR 5 — undead + celestial + elemental + construct
    ("Wraith", 5, 13, 67, 6, 4),
    ("Unicorn", 5, 12, 67, 7, 0),
    ("Water Elemental", 5, 14, 114, 7, 2),
    ("Flesh Golem", 5, 9, 93, 7, 3),
    # CR 6 — dragon-kin
    ("Wyvern", 6, 13, 110, 7, 0),
    # CR 7 — iconic aberration
    ("Mind Flayer", 7, 15, 71, 7, 0),
    # CR 9 — construct + plant
    ("Clay Golem", 9, 14, 133, 9, 3),
    ("Treant", 9, 13, 138, 10, 0),
    # CR 10 — iconic aberration + construct
    ("Aboleth", 10, 17, 135, 9, 0),
    ("Stone Golem", 10, 17, 178, 10, 3),
    # CR 15 — iconic monstrosity
    ("Purple Worm", 15, 18, 247, 14, 0),
    # CR 16 — apex construct (completes golem family)
    ("Iron Golem", 16, 19, 210, 12, 3),
]

# Monsters that deliberately carry no damage modifiers (MM lists none).
NO_MOD_MONSTERS = [
    "Orc", "Gnoll", "Griffon", "Displacer Beast", "Manticore", "Doppelganger",
    "Ettin", "Unicorn", "Wyvern", "Mind Flayer", "Treant", "Aboleth",
    "Purple Worm",
]


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

    @pytest.mark.parametrize("name,cr,ac,hp,atk,n_mods", NEW_ENTRIES)
    def test_stat_block_matches_canonical_mm(self, name, cr, ac, hp, atk, n_mods):
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

    @pytest.mark.parametrize("name,cr,ac,hp,atk,n_mods", NEW_ENTRIES)
    def test_xp_value_derived_from_cr(self, name, cr, ac, hp, atk, n_mods):
        enemy = get_enemy_template(name)
        assert enemy is not None
        # xp_value is derived from cr in __post_init__
        assert enemy.xp_value == CR_TO_XP[cr]
        assert cr_to_xp(cr) == CR_TO_XP[cr]

    @pytest.mark.parametrize("name,cr,ac,hp,atk,n_mods", NEW_ENTRIES)
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

    @pytest.mark.parametrize("name,cr,ac,hp,atk,n_mods", NEW_ENTRIES)
    def test_appears_in_correct_cr_lookup(self, name, cr, ac, hp, atk, n_mods):
        """get_enemies_by_cr(cr) must surface every new entry at its CR."""
        matches = {m.name for m in get_enemies_by_cr(cr)}
        assert name in matches, f"{name} not found in get_enemies_by_cr({cr})"

    def test_no_duplicate_keys(self):
        """All 24 new entries are distinct registry keys (no shadowing)."""
        names = [entry[0] for entry in NEW_ENTRIES]
        assert len(names) == len(set(names)), "duplicate names in NEW_ENTRIES"


class TestCanonicalDamageModifiers:
    """Iconic monsters carry their canonical MM damage immunities/resistances."""

    @pytest.mark.parametrize(
        "name,kind,types",
        [
            # Undead: immune to poison (undead trait).
            ("Ghoul", "immunity", "poison"),
            ("Specter", "immunity", "poison"),
            ("Banshee", "immunity", "necrotic"),
            ("Banshee", "immunity", "poison"),
            ("Wraith", "immunity", "cold"),
            ("Wraith", "immunity", "necrotic"),
            ("Wraith", "immunity", "poison"),
            # Mimic — immune to acid (Adhesive/immune acid, MM p.220).
            ("Mimic", "immunity", "acid"),
            # Hell Hound — immune to fire (MM p.182).
            ("Hell Hound", "immunity", "fire"),
            # Water elemental — immune to poison (elemental trait, MM p.125).
            ("Water Elemental", "immunity", "poison"),
            # Golems — type immunities (MM p.168-170).
            ("Flesh Golem", "immunity", "lightning"),
            ("Flesh Golem", "immunity", "poison"),
            ("Clay Golem", "immunity", "acid"),
            ("Clay Golem", "immunity", "poison"),
            ("Stone Golem", "immunity", "poison"),
            ("Stone Golem", "immunity", "psychic"),
            ("Iron Golem", "immunity", "fire"),
            ("Iron Golem", "immunity", "poison"),
        ],
    )
    def test_immunity_present(self, name, kind, types):
        mods = _mods(name)
        assert kind in mods, f"{name} has no '{kind}' modifier: {mods}"
        assert types in mods[kind], f"{name} {kind} missing {types}: {mods}"

    @pytest.mark.parametrize(
        "name,types",
        [
            # Undead resist nonmagical BPS (incorporeal / spectral).
            ("Specter", "bludgeoning"),
            ("Specter", "piercing"),
            ("Specter", "slashing"),
            ("Banshee", "bludgeoning"),
            ("Banshee", "piercing"),
            ("Banshee", "slashing"),
            ("Wraith", "bludgeoning"),
            ("Wraith", "piercing"),
            ("Wraith", "slashing"),
        ],
    )
    def test_undead_resist_nonmagical_bps(self, name, types):
        mods = _mods(name)
        assert "resistance" in mods, f"{name} has no resistance: {mods}"
        assert types in mods["resistance"], f"{name} resist missing {types}: {mods}"

    def test_water_elemental_resists_acid_regular(self):
        """Water elemental resists acid (MM p.125) — a plain resistance."""
        enemy = get_enemy_template("Water Elemental")
        assert enemy is not None
        acid_resists = [
            m for m in enemy.damage_modifiers
            if m["kind"] == "resistance" and "acid" in m.get("types", [])
        ]
        assert acid_resists, "Water Elemental should resist acid"
        # Not a "nonmagical only" qualifier — acid resistance is unconditional.
        assert acid_resists[0].get("bypassed_by_magic") is not True

    @pytest.mark.parametrize(
        "name",
        ["Flesh Golem", "Clay Golem", "Stone Golem", "Iron Golem"],
    )
    def test_golems_immune_nonmagical_bps(self, name):
        """Every golem is immune to nonmagical bludgeoning/piercing/slashing (MM)."""
        enemy = get_enemy_template(name)
        assert enemy is not None
        bps_immunity = [
            m for m in enemy.damage_modifiers
            if m["kind"] == "immunity" and "bludgeoning" in m.get("types", [])
        ]
        assert bps_immunity, f"{name} missing nonmagical-BPS immunity"
        mod = bps_immunity[0]
        # Nonmagical BPS immunity is bypassed by magic.
        assert mod.get("bypassed_by_magic") is True
        assert {"bludgeoning", "piercing", "slashing"}.issubset(set(mod["types"]))

    @pytest.mark.parametrize(
        "name",
        ["Specter", "Banshee", "Wraith"],
    )
    def test_undead_nonmagical_bps_resistance_bypassed_by_magic(self, name):
        """Undead nonmagical-BPS resistance is bypassed by magic (per MM)."""
        enemy = get_enemy_template(name)
        assert enemy is not None
        bps_resist = [
            m for m in enemy.damage_modifiers
            if m["kind"] == "resistance" and "bludgeoning" in m.get("types", [])
        ]
        assert bps_resist, f"{name} missing nonmagical-BPS resistance"
        assert bps_resist[0].get("bypassed_by_magic") is True

    @pytest.mark.parametrize("name", NO_MOD_MONSTERS)
    def test_has_no_damage_modifiers(self, name):
        """These MM monsters list no damage immunities/resistances/vulnerabilities."""
        enemy = get_enemy_template(name)
        assert enemy is not None
        assert enemy.damage_modifiers == [], f"{name} should have no damage modifiers"


class TestGolemFamily:
    """The four classic golems are now all present at their canonical CRs."""

    GOLEM_CR = {
        "Flesh Golem": 5,
        "Clay Golem": 9,
        "Stone Golem": 10,
        "Iron Golem": 16,
    }

    def test_all_four_golems_present(self):
        for name in self.GOLEM_CR:
            assert get_enemy_template(name) is not None, f"{name} missing"

    @pytest.mark.parametrize("name,cr", list(GOLEM_CR.items()))
    def test_golem_canonical_cr(self, name, cr):
        enemy = get_enemy_template(name)
        assert enemy is not None
        assert enemy.cr == cr, f"{name} CR {enemy.cr} != canonical {cr}"

    def test_golem_hp_scales_with_tier(self):
        """Golem HP increases across the family (Flesh < Clay < Stone < Iron)."""
        hps = {
            n: get_enemy_template(n).hp
            for n in self.GOLEM_CR
            if get_enemy_template(n)
        }
        assert hps["Flesh Golem"] < hps["Clay Golem"] < hps["Stone Golem"] < hps["Iron Golem"]


class TestIconicAberrations:
    """The two most iconic aberrations (Mind Flayer, Aboleth) are now registered."""

    def test_mind_flayer_canonical(self):
        mf = get_enemy_template("Mind Flayer")
        assert mf is not None
        assert mf.cr == 7  # MM p.221
        assert mf.armor_class == 15
        assert mf.hp == 71

    def test_aboleth_canonical(self):
        ab = get_enemy_template("Aboleth")
        assert ab is not None
        assert ab.cr == 10  # MM p.13
        assert ab.armor_class == 17
        assert ab.hp == 135


class TestCRBandPopulation:
    """Every CR band touched by this expansion gained its expected entries."""

    @pytest.mark.parametrize(
        "cr,expected_min",
        [
            (1 / 2, 8),  # +Orc, +Gnoll
            (1, 10),     # +Ghoul, +Specter
            (2, 12),     # +Mimic, +Griffon
            (3, 15),     # +Displacer Beast, Manticore, Hell Hound, Doppelganger
            (4, 12),     # +Banshee, +Ettin
            (5, 14),     # +Wraith, Unicorn, Water Elemental, Flesh Golem
            (6, 10),     # +Wyvern
            (7, 10),     # +Mind Flayer
            (9, 12),     # +Clay Golem, +Treant
            (10, 9),     # +Aboleth, +Stone Golem
            (15, 3),     # +Purple Worm
            (16, 3),     # +Iron Golem
        ],
    )
    def test_band_meets_floor(self, cr, expected_min):
        matches = get_enemies_by_cr(cr)
        assert len(matches) >= expected_min, (
            f"CR {cr} band has {len(matches)} entries, expected >= {expected_min}"
        )


class TestRegistryTotal:
    """The registry grew by exactly 24 entries (145 -> 169)."""

    def test_registry_grew_to_169(self):
        assert len(COMMON_ENEMIES) == 169, (
            f"registry size {len(COMMON_ENEMIES)} != 169 (expected 145 + 24)"
        )

    def test_all_new_entries_listed(self):
        listed = set(list_enemy_templates())
        for entry in NEW_ENTRIES:
            assert entry[0] in listed, f"{entry[0]} not in list_enemy_templates()"
