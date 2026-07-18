"""Tests for the high-tier (CR 11-30) enemy registry expansion + Werewolf dedup.

Covers:
- The previously empty CR 11-30 band now has iconic solo threats
  (Beholder, Adult Red Dragon, Tarrasque, ...) for parties 15-20.
- The Werewolf duplicate-key bug is fixed: exactly one canonical
  Werewolf (MM CR 3) survives — the CR 2 / CR 5 collisions are gone.
- Each new monster resolves to a valid combat stat block (to_dict)
  and the documented CR→XP value.
"""
from __future__ import annotations

import pytest

from app.engine.encounters import (
    COMMON_ENEMIES,
    CR_TO_XP,
    EnemyTemplate,
    cr_to_xp,
    get_enemy_template,
    get_enemies_by_cr,
    list_enemy_templates,
)


# (name, cr, armor_class, hp, attack_bonus)
NEW_HIGH_CR_ENEMIES = [
    ("Dao", 11, 18, 120, 9),
    ("Gynosphinx", 11, 17, 136, 8),
    ("Erinyes", 12, 18, 153, 9),
    ("Beholder", 13, 18, 180, 5),
    ("Storm Giant", 13, 16, 230, 12),
    ("Rakshasa", 13, 16, 84, 6),
    ("Vampire", 13, 16, 144, 7),
    ("Adult Blue Dragon", 16, 19, 243, 12),
    ("Adult Silver Dragon", 16, 19, 290, 12),
    ("Adult Red Dragon", 17, 19, 297, 14),
    ("Adult Gold Dragon", 17, 19, 297, 14),
    ("Balor", 19, 19, 262, 14),
    ("Pit Fiend", 20, 19, 300, 14),
    ("Ancient White Dragon", 20, 20, 333, 14),
    ("Ancient Red Dragon", 22, 22, 546, 17),
    ("Ancient Gold Dragon", 24, 22, 546, 17),
    ("Tarrasque", 30, 25, 676, 19),
]


class TestWerewolfDedup:
    """Regression guard for the duplicate Werewolf key bug."""

    def test_werewolf_registered_exactly_once(self):
        names = list_enemy_templates()
        assert names.count("Werewolf") == 1

    def test_werewolf_is_mm_canonical_cr3(self):
        wolf = get_enemy_template("Werewolf")
        assert wolf is not None
        assert wolf.cr == 3  # MM canonical CR
        assert wolf.hp == 58
        assert wolf.armor_class == 12

    def test_werewolf_retains_silver_bypassed_immunity(self):
        wolf = get_enemy_template("Werewolf")
        assert wolf is not None
        # The MM lycanthrope immunity: immune to nonmagical BPS, bypassed by
        # silvered weapons. to_dict() expands this to the 3 physical types.
        bps = {"bludgeoning", "piercing", "slashing"}
        matching = [
            m for m in wolf.damage_modifiers
            if m.get("kind") == "immunity" and bps.issubset(set(m.get("types", [])))
        ]
        assert len(matching) == 1, wolf.damage_modifiers
        assert matching[0].get("bypassed_by_magic") is True
        assert matching[0].get("bypassed_by_silver") is True

    def test_no_duplicate_names_anywhere_in_registry(self):
        """Every name in the dict literal must be unique — no silent overwrites."""
        names = list_enemy_templates()
        assert len(names) == len(set(names))


class TestHighTierExpansion:
    """The CR 11-30 band (previously empty) now has iconic monsters."""

    @pytest.mark.parametrize("name,cr,ac,hp,atk", NEW_HIGH_CR_ENEMIES)
    def test_each_new_monster_registered(self, name, cr, ac, hp, atk):
        enemy = get_enemy_template(name)
        assert enemy is not None, f"{name} missing from registry"
        assert enemy.cr == cr
        assert enemy.armor_class == ac
        assert enemy.hp == hp
        assert enemy.attack_bonus == atk

    @pytest.mark.parametrize("name,cr,ac,hp,atk", NEW_HIGH_CR_ENEMIES)
    def test_each_new_monster_xp_matches_cr(self, name, cr, ac, hp, atk):
        enemy = get_enemy_template(name)
        assert enemy is not None
        # xp_value is derived from cr in __post_init__
        assert enemy.xp_value == CR_TO_XP[cr]
        assert cr_to_xp(cr) == CR_TO_XP[cr]

    @pytest.mark.parametrize("name,cr,ac,hp,atk", NEW_HIGH_CR_ENEMIES)
    def test_each_new_monster_to_dict_is_valid_combat_block(self, name, cr, ac, hp, atk):
        enemy = get_enemy_template(name)
        assert enemy is not None
        data = enemy.to_dict()
        assert data["name"] == name
        assert data["max_hp"] == hp
        assert data["armor_class"] == ac
        assert data["initiative_bonus"] == 0
        assert data["speed"] == 30
        assert isinstance(data["damage_modifiers"], list)
        assert len(data["attacks"]) == 1
        atk_block = data["attacks"][0]
        assert atk_block["attack_bonus"] == atk
        assert atk_block["damage_dice_count"] == 1
        assert atk_block["damage_dice_sides"] == 6

    @pytest.mark.parametrize("cr", [11, 12, 13, 16, 17, 19, 20, 22, 24, 30])
    def test_get_enemies_by_cr_returns_new_entries(self, cr):
        matches = get_enemies_by_cr(cr)
        assert len(matches) >= 1, f"CR {cr} has no enemies"
        # At least one of the new high-tier monsters must be present.
        expected_names = {n for n, c, *_ in NEW_HIGH_CR_ENEMIES if c == cr}
        actual_names = {m.name for m in matches}
        assert expected_names.issubset(actual_names), (cr, expected_names, actual_names)

    def test_registry_total_count_increased(self):
        # Was 116 effective (one dup key). Expansion + dedup bring it well above.
        assert len(COMMON_ENEMIES) >= 133

    def test_registry_spans_full_cr_range_now(self):
        crs_present = {e.cr for e in COMMON_ENEMIES.values()}
        # The high tier (11-30) must be represented at all the new CRs.
        for cr in [11, 12, 13, 16, 17, 19, 20, 22, 24, 30]:
            assert cr in crs_present, f"CR {cr} missing from registry"

    def test_registry_has_no_fractional_cr_above_zero(self):
        # Sanity: fractional CRs are only the sub-1 fractions.
        for e in COMMON_ENEMIES.values():
            if e.cr != int(e.cr):
                assert e.cr < 1, f"Unexpected fractional CR >= 1: {e.name} cr={e.cr}"

    def test_all_enemy_names_match_their_keys(self):
        for key, enemy in COMMON_ENEMIES.items():
            assert key == enemy.name, f"key {key!r} != name {enemy.name!r}"

    def test_tarrasque_is_apex(self):
        """The Tarrasque is the highest-CR entry in the registry."""
        apex = max(COMMON_ENEMIES.values(), key=lambda e: e.cr)
        assert apex.name == "Tarrasque"
        assert apex.cr == 30
        assert apex.xp_value == 155000


class TestDamageModifiersOnNewEntries:
    """Iconic high-tier monsters carry their canonical damage immunities."""

    def _mods(self, name: str) -> dict:
        """Return {kind: set_of_types} for quick assertions."""
        enemy = get_enemy_template(name)
        assert enemy is not None
        out: dict[str, set] = {}
        for mod in enemy.damage_modifiers:
            out.setdefault(mod["kind"], set()).update(mod.get("types", []))
        return out

    @pytest.mark.parametrize(
        "name,kind,types",
        [
            ("Rakshasa", "immunity", "bludgeoning"),
            ("Vampire", "immunity", "necrotic"),
            ("Vampire", "immunity", "poison"),
            ("Adult Blue Dragon", "immunity", "lightning"),
            ("Adult Silver Dragon", "immunity", "cold"),
            ("Adult Red Dragon", "immunity", "fire"),
            ("Adult Gold Dragon", "immunity", "fire"),
            ("Balor", "immunity", "fire"),
            ("Balor", "immunity", "poison"),
            ("Pit Fiend", "immunity", "fire"),
            ("Pit Fiend", "immunity", "poison"),
            ("Ancient White Dragon", "immunity", "cold"),
            ("Ancient Red Dragon", "immunity", "fire"),
            ("Ancient Gold Dragon", "immunity", "fire"),
            ("Tarrasque", "immunity", "fire"),
            ("Tarrasque", "immunity", "poison"),
        ],
    )
    def test_canonical_immunity_present(self, name, kind, types):
        mods = self._mods(name)
        assert kind in mods, f"{name} has no '{kind}' modifier: {mods}"
        assert types in mods[kind], f"{name} {kind} missing {types}: {mods}"


class TestExistingPreserved:
    """The reworked CR 2 / CR 5 slots remain populated after the Werewolf fix."""

    def test_saber_toothed_tiger_fills_cr2_slot(self):
        tiger = get_enemy_template("Saber-Toothed Tiger")
        assert tiger is not None
        assert tiger.cr == 2

    def test_troll_fills_cr5_slot(self):
        troll = get_enemy_template("Troll")
        assert troll is not None
        assert troll.cr == 5

    def test_canonical_monsters_still_present(self):
        for name in ["Goblin", "Skeleton", "Ogre", "Owlbear", "Lich", "Nalfeshnee"]:
            assert name in COMMON_ENEMIES, f"{name} dropped from registry"
