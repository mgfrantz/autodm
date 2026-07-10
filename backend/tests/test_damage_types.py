"""Tests for the damage-type modifier engine (resistance/immunity/vulnerability)."""

from app.engine import damage_types as dt
from app.engine.damage_types import (
    BPS,
    DAMAGE_TYPES,
    DamageModifier,
    DamageModifierSet,
    compute_damage,
    damage_multiplier,
    immune,
    immune_nonmagical_bps,
    resist,
    resist_nonmagical_bps,
    summary_for_dm,
    vuln,
)


# --------------------------------------------------------------------------- #
# Vocabulary & normalization
# --------------------------------------------------------------------------- #


def test_damage_types_includes_all_thirteen_phb_types():
    assert len(DAMAGE_TYPES) == 13
    for t in ("acid", "fire", "force", "psychic", "thunder"):
        assert t in DAMAGE_TYPES


def test_bps_is_the_three_physical_types():
    assert set(BPS) == {"bludgeoning", "piercing", "slashing"}


def test_normalize_type_is_case_insensitive():
    assert dt.normalize_type("Fire") == "fire"
    assert dt.normalize_type("  Slashing ") == "slashing"
    assert dt.normalize_type("") == ""


# --------------------------------------------------------------------------- #
# Constructor helpers
# --------------------------------------------------------------------------- #


def test_resist_helper_single_and_multi():
    r = resist("fire")
    assert r.kind == "resistance"
    assert r.types == ("fire",)
    assert r.covers("fire")

    r2 = resist(["fire", "cold"])
    assert r2.types == ("fire", "cold")
    assert r2.covers("cold")


def test_resist_helper_string_csv_split():
    r = resist("bludgeoning, piercing, slashing")
    assert r.types == ("bludgeoning", "piercing", "slashing")


def test_immune_and_vuln_helpers():
    assert immune("poison").kind == "immunity"
    assert vuln("fire").kind == "vulnerability"


def test_resist_nonmagical_bps_helper():
    r = resist_nonmagical_bps()
    assert r.kind == "resistance"
    assert set(r.types) == set(BPS)
    assert r.bypassed_by_magic is True
    assert r.bypassed_by_silver is False


def test_immune_nonmagical_bps_lycanthrope():
    m = immune_nonmagical_bps(silver_bypasses=True)
    assert m.bypassed_by_magic is True
    assert m.bypassed_by_silver is True


def test_invalid_kind_raises():
    import pytest

    with pytest.raises(ValueError):
        DamageModifier(("fire",), "absorption")


def test_empty_types_raises():
    import pytest

    with pytest.raises(ValueError):
        DamageModifier((), "resistance")


# --------------------------------------------------------------------------- #
# Applies / bypass logic
# --------------------------------------------------------------------------- #


def test_unqualified_resistance_always_applies():
    r = resist("fire")
    assert r.applies("fire")
    assert r.applies("fire", magical=True)  # magic does NOT bypass unqualified
    assert not r.applies("cold")


def test_nonmagical_resistance_bypassed_by_magic():
    r = resist_nonmagical_bps()
    assert r.applies("slashing")                # nonmagical weapon hit
    assert not r.applies("slashing", magical=True)  # magic weapon bypasses


def test_lycanthrope_immunity_bypassed_by_silver_or_magic():
    m = immune_nonmagical_bps(silver_bypasses=True)
    assert m.applies("piercing")                          # plain weapon
    assert not m.applies("piercing", magical=True)        # magic weapon
    assert not m.applies("piercing", silvered=True)       # silvered weapon
    assert not m.applies("piercing", magical=True, silvered=True)


def test_fiend_resistance_not_bypassed_by_silver():
    # Fiends resist BPS from nonmagical attacks; silvered-but-nonmagical does
    # NOT bypass (only magic does).
    r = resist_nonmagical_bps()
    assert r.applies("bludgeoning", silvered=True)
    assert not r.applies("bludgeoning", magical=True)


# --------------------------------------------------------------------------- #
# Core compute_damage
# --------------------------------------------------------------------------- #


def test_no_modifiers_returns_unchanged():
    assert compute_damage(25, "fire", None) == 25
    assert compute_damage(25, "fire", DamageModifierSet()) == 25


def test_immunity_returns_zero():
    mods = DamageModifierSet.of(immune("poison"))
    assert compute_damage(40, "poison", mods) == 0


def test_resistance_halves_rounded_down():
    mods = DamageModifierSet.of(resist("fire"))
    assert compute_damage(25, "fire", mods) == 12   # 25 // 2
    assert compute_damage(24, "fire", mods) == 12
    assert compute_damage(1, "fire", mods) == 0


def test_vulnerability_doubles():
    mods = DamageModifierSet.of(vuln("fire"))
    assert compute_damage(10, "fire", mods) == 20


def test_resistance_then_vulnerability_order():
    # PHB p.197: resistance then vulnerability. 25 -> halve (12) -> double (24).
    mods = DamageModifierSet.of(resist("fire"), vuln("fire"))
    assert compute_damage(25, "fire", mods) == 24


def test_immunity_wins_over_resistance_and_vulnerability():
    mods = DamageModifierSet.of(resist("fire"), immune("fire"), vuln("fire"))
    assert compute_damage(100, "fire", mods) == 0


def test_nonmagical_resistance_only_affects_nonmagical():
    mods = DamageModifierSet.of(resist_nonmagical_bps())
    assert compute_damage(20, "slashing", mods) == 10        # plain weapon
    assert compute_damage(20, "slashing", mods, magical=True) == 20  # magic weapon


def test_lycanthrope_full_immunity():
    mods = DamageModifierSet.of(immune_nonmagical_bps(silver_bypasses=True))
    assert compute_damage(30, "piercing", mods) == 0       # plain
    assert compute_damage(30, "piercing", mods, magical=True) == 30
    assert compute_damage(30, "piercing", mods, silvered=True) == 30
    # Non-BPS damage still lands fully.
    assert compute_damage(30, "fire", mods) == 30


def test_non_matching_type_unaffected():
    mods = DamageModifierSet.of(resist("fire"))
    assert compute_damage(20, "cold", mods) == 20


def test_zero_or_negative_input_is_zero():
    mods = DamageModifierSet.of(vuln("fire"))
    assert compute_damage(0, "fire", mods) == 0
    assert compute_damage(-5, "fire", mods) == 0


def test_multiple_resistances_do_not_stack():
    # Two separate resistance entries for the same type = one halving.
    mods = DamageModifierSet.of(resist("fire"), resist("fire"))
    assert compute_damage(20, "fire", mods) == 10  # not 5


# --------------------------------------------------------------------------- #
# damage_multiplier helper
# --------------------------------------------------------------------------- #


def test_multiplier_values():
    assert damage_multiplier("fire", DamageModifierSet.of(immune("fire"))) == 0.0
    assert damage_multiplier("fire", DamageModifierSet.of(resist("fire"))) == 0.5
    assert damage_multiplier("fire", DamageModifierSet.of(vuln("fire"))) == 2.0
    assert damage_multiplier("fire", DamageModifierSet()) == 1.0
    assert damage_multiplier(
        "fire", DamageModifierSet.of(resist("fire"), vuln("fire"))
    ) == 1.0


# --------------------------------------------------------------------------- #
# Serialization round-trips
# --------------------------------------------------------------------------- #


def test_damage_modifier_round_trip():
    m = resist_nonmagical_bps()
    d = m.to_dict()
    assert d["types"] == ["bludgeoning", "piercing", "slashing"]
    assert d["kind"] == "resistance"
    assert d["bypassed_by_magic"] is True
    m2 = DamageModifier.from_dict(d)
    assert m2 == m


def test_damage_modifier_set_round_trip():
    mods = DamageModifierSet.of(
        immune("poison"),
        resist_nonmagical_bps(),
        vuln("fire"),
    )
    data = mods.to_dict()
    restored = DamageModifierSet.from_dict(data)
    assert restored.to_dict() == data
    # Behavior preserved.
    assert compute_damage(20, "poison", restored) == 0
    assert compute_damage(20, "slashing", restored) == 10
    assert compute_damage(20, "slashing", restored, magical=True) == 20
    assert compute_damage(10, "fire", restored) == 20


def test_from_lists_accepts_bare_strings_and_dicts():
    mods = DamageModifierSet.from_lists(
        resistances=["fire", {"types": ["cold"], "kind": "resistance"}],
        immunities=["poison"],
        vulnerabilities=["fire"],
    )
    assert compute_damage(20, "fire", mods) == 20  # resist+vuln cancel per order
    assert compute_damage(20, "poison", mods) == 0
    assert compute_damage(20, "cold", mods) == 10


def test_from_dict_tolerates_grouped_shape():
    grouped = {
        "resistances": ["fire"],
        "immunities": ["poison"],
        "vulnerabilities": ["cold"],
    }
    mods = DamageModifierSet.from_dict(grouped)
    assert compute_damage(20, "fire", mods) == 10
    assert compute_damage(20, "poison", mods) == 0
    assert compute_damage(10, "cold", mods) == 20


def test_from_dict_none_is_empty():
    assert DamageModifierSet.from_dict(None).is_empty


# --------------------------------------------------------------------------- #
# DM summary
# --------------------------------------------------------------------------- #


def test_summary_empty_for_no_modifiers():
    assert summary_for_dm(None) == ""
    assert summary_for_dm(DamageModifierSet()) == ""


def test_summary_formats_all_three_groups():
    mods = DamageModifierSet.of(
        resist("fire"),
        immune("poison"),
        vuln("cold"),
    )
    s = summary_for_dm(mods)
    assert "Resist" in s and "fire" in s
    assert "Immune" in s and "poison" in s
    assert "Vuln" in s and "cold" in s


def test_summary_folds_bps_and_notes_qualifier():
    mods = DamageModifierSet.of(resist_nonmagical_bps())
    s = summary_for_dm(mods)
    assert "bludgeoning/piercing/slashing" in s
    assert "nonmagical" in s


def test_summary_lycanthrope_double_qualifier():
    mods = DamageModifierSet.of(immune_nonmagical_bps(silver_bypasses=True))
    s = summary_for_dm(mods)
    assert "nonmagical & nonsilvered" in s


# --------------------------------------------------------------------------- #
# Inspection helpers
# --------------------------------------------------------------------------- #


def test_grouped_accessors():
    mods = DamageModifierSet.of(resist("fire"), immune("poison"), vuln("cold"))
    assert len(mods.resistances()) == 1
    assert len(mods.immunities()) == 1
    assert len(mods.vulnerabilities()) == 1
    assert mods.has_any("fire")
    assert not mods.has_any("force")
    assert len(mods) == 3
    assert bool(mods) is True
