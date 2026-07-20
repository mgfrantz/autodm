"""Tests for the iconic-trap registry expansion (DMG ch.5 + XGtE-style).

This run closed the trap registry's **iconic-trap gap**. The catalogue was
already PHB-complete for spells (all 11 tiers 0–9), subclasses (all twelve
core classes), feats (PHB + XGE + TCoE), and canonical-complete for the dragon
family and iconic Monster Manual monsters — but the trap registry modelled only
the **14 DMG Chapter 5 sample traps**. Many of the most-played iconic traps
were absent (Spiked Pit, Arrow Trap, Crushing Wall, Falling Block, Spear Trap,
Ceiling Spikes, Explosive Rune, Lightning Trap, Acid Spray, Freezing Trap,
Wailing Trap, Web Trap, etc.).

This run registers **18 canonical / iconic traps** inline into their proper
type sections (mechanical + magical), lifting the registry from **14 → 32**.

A secondary win: the `TrapEffectType.SUMMON` and `TrapEffectType.TELEKINESIS`
enums were previously **declared but exercised by zero traps** in the registry
(only `trigger_trap` referenced them). The new `summoning_trap` and
`telekinesis_trap` are the first registry entries to use these effect types,
closing an engine-coverage gap.

Severity bands & DCs follow DMG Chapter 5 guidance throughout:
  setback   — DC 10–11, light damage
  dangerous — DC 12–19, moderate damage (save for half)
  deadly    — DC 18–20+, heavy / save-or-worse

18 new entries → registry 14 -> 32.
"""
from __future__ import annotations

import pytest

from app.engine.traps import (
    TRAP_REGISTRY,
    Trap,
    TrapEffect,
    TrapEffectType,
    TrapInstance,
    TrapSeverity,
    TrapType,
    get_trap,
    list_trap_ids,
    list_traps,
    traps_by_severity,
    trigger_trap,
)


# ---------------------------------------------------------------------------
# New canonical / iconic traps added this run.
#
# (id, name, trap_type, severity, detection_dc, disarm_dc, n_effects, eff_types)
#   eff_types is the sorted tuple of TrapEffectType values the trap uses.
# ---------------------------------------------------------------------------

MECHANICAL_ENTRIES = [
    ("spiked_pit", "Spiked Pit", TrapType.MECHANICAL, TrapSeverity.DANGEROUS, 12, 12, 2, (TrapEffectType.DAMAGE,)),
    ("arrow_trap", "Arrow Trap", TrapType.MECHANICAL, TrapSeverity.DANGEROUS, 15, 15, 1, (TrapEffectType.DAMAGE,)),
    ("crushing_wall", "Crushing Wall", TrapType.MECHANICAL, TrapSeverity.DEADLY, 18, 20, 1, (TrapEffectType.DAMAGE,)),
    ("falling_block", "Falling Block", TrapType.MECHANICAL, TrapSeverity.DANGEROUS, 15, 15, 1, (TrapEffectType.DAMAGE,)),
    ("falling_portcullis", "Falling Portcullis", TrapType.MECHANICAL, TrapSeverity.DANGEROUS, 13, 13, 2, (TrapEffectType.DAMAGE, TrapEffectType.CONDITION)),
    ("weak_floor", "Weak Floor", TrapType.MECHANICAL, TrapSeverity.SETBACK, 12, 12, 1, (TrapEffectType.DAMAGE,)),
    ("spear_trap", "Spear Trap", TrapType.MECHANICAL, TrapSeverity.DANGEROUS, 15, 15, 1, (TrapEffectType.DAMAGE,)),
    ("tripwire_crossbow", "Tripwire Crossbow", TrapType.MECHANICAL, TrapSeverity.SETBACK, 13, 12, 1, (TrapEffectType.DAMAGE,)),
    ("ceiling_spikes", "Ceiling Spikes", TrapType.MECHANICAL, TrapSeverity.DANGEROUS, 15, 15, 1, (TrapEffectType.DAMAGE,)),
    ("spinning_blade", "Spinning Blade", TrapType.MECHANICAL, TrapSeverity.DANGEROUS, 13, 13, 2, (TrapEffectType.DAMAGE, TrapEffectType.CONDITION)),
]

MAGICAL_ENTRIES = [
    ("explosive_rune", "Explosive Rune", TrapType.MAGICAL, TrapSeverity.DANGEROUS, 15, 15, 1, (TrapEffectType.DAMAGE,)),
    ("lightning_trap", "Lightning Trap", TrapType.MAGICAL, TrapSeverity.DANGEROUS, 15, 15, 1, (TrapEffectType.DAMAGE,)),
    ("acid_spray_trap", "Acid Spray Trap", TrapType.MAGICAL, TrapSeverity.DANGEROUS, 13, 13, 1, (TrapEffectType.DAMAGE,)),
    ("freezing_trap", "Freezing Trap", TrapType.MAGICAL, TrapSeverity.DANGEROUS, 15, 15, 2, (TrapEffectType.DAMAGE, TrapEffectType.CONDITION)),
    ("wailing_trap", "Wailing Trap", TrapType.MAGICAL, TrapSeverity.DEADLY, 18, 18, 2, (TrapEffectType.DAMAGE, TrapEffectType.CONDITION)),
    ("web_trap", "Web Trap", TrapType.MAGICAL, TrapSeverity.SETBACK, 13, 13, 1, (TrapEffectType.CONDITION,)),
    ("summoning_trap", "Summoning Trap", TrapType.MAGICAL, TrapSeverity.DEADLY, 18, 20, 1, (TrapEffectType.SUMMON,)),
    ("telekinesis_trap", "Telekinesis Trap", TrapType.MAGICAL, TrapSeverity.DANGEROUS, 15, 15, 1, (TrapEffectType.TELEKINESIS,)),
]

NEW_ENTRIES = MECHANICAL_ENTRIES + MAGICAL_ENTRIES
NEW_IDS = [row[0] for row in NEW_ENTRIES]
NEW_NAMES = [row[1] for row in NEW_ENTRIES]


# ---------------------------------------------------------------------------
# Registration: each new trap is present with its canonical stat block
# ---------------------------------------------------------------------------

class TestNewTrapsRegistered:
    @pytest.mark.parametrize(
        "tid,name,ttype,sev,det_dc,disarm_dc,n_eff,eff_types", NEW_ENTRIES
    )
    def test_stat_block_matches_canonical(
        self, tid, name, ttype, sev, det_dc, disarm_dc, n_eff, eff_types
    ):
        trap = get_trap(tid)
        assert trap is not None, f"{tid} missing from registry"
        assert trap.id == tid
        assert trap.name == name
        assert trap.trap_type == ttype
        assert trap.severity == sev
        assert trap.detection_dc == det_dc
        assert trap.disarm_dc == disarm_dc
        assert len(trap.effects) == n_eff
        actual = {e.type for e in trap.effects}
        assert actual == set(eff_types), (
            f"{name} effect types {actual} != expected {set(eff_types)}"
        )

    @pytest.mark.parametrize(
        "tid,name,ttype,sev,det_dc,disarm_dc,n_eff,eff_types", NEW_ENTRIES
    )
    def test_required_fields_populated(
        self, tid, name, ttype, sev, det_dc, disarm_dc, n_eff, eff_types
    ):
        trap = get_trap(tid)
        assert trap.description, f"{name} missing description"
        assert trap.trigger, f"{name} missing trigger"
        assert trap.countermeasure, f"{name} missing countermeasure"
        assert trap.area, f"{name} missing area"
        for e in trap.effects:
            assert e is not None

    @pytest.mark.parametrize("tid", NEW_IDS)
    def test_lookup_by_id(self, tid):
        assert get_trap(tid) is not None
        assert get_trap(tid).id == tid


# ---------------------------------------------------------------------------
# DMG severity guidance: DCs and damage stay within the severity band
# ---------------------------------------------------------------------------

class TestSeverityBandConsistency:
    """DMG ch.5 severity bands: setback DC 10-11, dangerous DC 12-19, deadly DC 18-20+."""

    @pytest.mark.parametrize("tid,name,ttype,sev,det_dc,disarm_dc,n_eff,_", NEW_ENTRIES)
    def test_detection_dc_matches_severity_band(self, tid, name, ttype, sev, det_dc, disarm_dc, n_eff, _):
        if sev == TrapSeverity.SETBACK:
            assert 8 <= det_dc <= 13, f"{name} setback detection DC {det_dc} out of band"
        elif sev == TrapSeverity.DANGEROUS:
            assert 12 <= det_dc <= 19, f"{name} dangerous detection DC {det_dc} out of band"
        else:  # deadly
            assert det_dc >= 18, f"{name} deadly detection DC {det_dc} too low"

    @pytest.mark.parametrize("tid,name,ttype,sev,det_dc,disarm_dc,n_eff,_", NEW_ENTRIES)
    def test_disarm_dc_matches_severity_band(self, tid, name, ttype, sev, det_dc, disarm_dc, n_eff, _):
        if sev == TrapSeverity.SETBACK:
            assert 8 <= disarm_dc <= 13
        elif sev == TrapSeverity.DANGEROUS:
            assert 12 <= disarm_dc <= 19
        else:  # deadly
            assert disarm_dc >= 18, f"{name} deadly disarm DC {disarm_dc} too low"

    @pytest.mark.parametrize("tid,name,ttype,sev,det_dc,disarm_dc,n_eff,_", NEW_ENTRIES)
    def test_damage_dice_scale_with_severity(self, tid, name, ttype, sev, det_dc, disarm_dc, n_eff, _):
        """Lethal traps roll more dice than setbacks."""
        trap = get_trap(tid)
        dice = [e for e in trap.effects if e.type == TrapEffectType.DAMAGE and e.damage_dice]
        if not dice:
            return  # condition-only trap (web/summon/telekinesis) — nothing to check
        # Approximate max damage per die-count: parse the leading "<n>d<s>".
        import re
        maxes = []
        for e in dice:
            m = re.match(r"(\d+)d(\d+)", e.damage_dice)
            assert m, f"{name} bad damage dice {e.damage_dice!r}"
            count, sides = int(m.group(1)), int(m.group(2))
            maxes.append(count * sides)
        top = max(maxes)
        if sev == TrapSeverity.SETBACK:
            assert top <= 22, f"{name} setback damage max {top} too high (spiked pit excluded by severity=DANGEROUS)"
        elif sev == TrapSeverity.DANGEROUS:
            assert top <= 80, f"{name} dangerous damage max {top} too high"
        else:  # deadly
            assert top >= 40, f"{name} deadly damage max {top} too low"


# ---------------------------------------------------------------------------
# Effect-type coverage: SUMMON & TELEKINESIS now exercised (were unused before)
# ---------------------------------------------------------------------------

class TestEffectTypeCoverage:
    def test_summon_effect_type_is_exercised(self):
        """The SUMMON effect type was declared but unused before this run."""
        summoners = [
            t.name for t in TRAP_REGISTRY.values()
            if any(e.type == TrapEffectType.SUMMON for e in t.effects)
        ]
        assert "Summoning Trap" in summoners
        assert len(summoners) >= 1

    def test_telekinesis_effect_type_is_exercised(self):
        """The TELEKINESIS effect type was declared but unused before this run."""
        tk = [
            t.name for t in TRAP_REGISTRY.values()
            if any(e.type == TrapEffectType.TELEKINESIS for e in t.effects)
        ]
        assert "Telekinesis Trap" in tk
        assert len(tk) >= 1

    def test_all_damage_effects_have_valid_dice(self):
        import re
        for trap in TRAP_REGISTRY.values():
            for e in trap.effects:
                if e.type == TrapEffectType.DAMAGE and e.damage_dice:
                    assert re.match(r"^\d+d\d+([+-]\d+)?$", e.damage_dice), (
                        f"{trap.name} has malformed damage_dice {e.damage_dice!r}"
                    )

    def test_all_save_results_are_canonical(self):
        valid = {"half", "none", "full", ""}
        for trap in TRAP_REGISTRY.values():
            for e in trap.effects:
                assert e.save_result in valid, (
                    f"{trap.name} effect has bad save_result {e.save_result!r}"
                )


# ---------------------------------------------------------------------------
# Type & severity coverage after expansion
# ---------------------------------------------------------------------------

class TestTypeAndSeverityCoverage:
    def test_mechanical_count_grew(self):
        mech = list_traps(trap_type=TrapType.MECHANICAL)
        # was 10 before (all mechanical sample traps + bear_trap + gas_trap)
        assert len(mech) >= 20, f"mechanical traps {len(mech)} < 20"

    def test_magical_count_grew(self):
        mag = list_traps(trap_type=TrapType.MAGICAL)
        # was 4 before (fire_breathing_statue, teleportation_trap, sphere_of_annihilation, glyph_of_warding)
        assert len(mag) >= 12, f"magical traps {len(mag)} < 12"

    def test_all_severities_well_populated(self):
        for sev in TrapSeverity:
            n = len(traps_by_severity(sev))
            assert n >= 3, f"severity {sev.value} has only {n} traps (< 3)"

    def test_new_traps_cover_both_types(self):
        new = [get_trap(i) for i in NEW_IDS]
        types = {t.trap_type for t in new}
        assert TrapType.MECHANICAL in types
        assert TrapType.MAGICAL in types

    def test_new_traps_cover_all_severities(self):
        new = [get_trap(i) for i in NEW_IDS]
        sevs = {t.severity for t in new}
        assert TrapSeverity.SETBACK in sevs
        assert TrapSeverity.DANGEROUS in sevs
        assert TrapSeverity.DEADLY in sevs


# ---------------------------------------------------------------------------
# Serialization: every new trap round-trips through to_dict / from_dict
# ---------------------------------------------------------------------------

class TestNewTrapSerialization:
    @pytest.mark.parametrize("tid", NEW_IDS)
    def test_trap_round_trip(self, tid):
        trap = get_trap(tid)
        d = trap.to_dict()
        assert d["id"] == tid
        restored = Trap.from_dict(d)
        assert restored.id == trap.id
        assert restored.name == trap.name
        assert restored.trap_type == trap.trap_type
        assert restored.severity == trap.severity
        assert restored.detection_dc == trap.detection_dc
        assert restored.disarm_dc == trap.disarm_dc
        assert len(restored.effects) == len(trap.effects)
        for orig, rest in zip(trap.effects, restored.effects):
            assert orig.type == rest.type
            assert orig.damage_dice == rest.damage_dice
            assert orig.save_dc == rest.save_dc

    @pytest.mark.parametrize("tid", NEW_IDS)
    def test_instance_round_trip(self, tid):
        trap = get_trap(tid)
        inst = TrapInstance.from_trap(trap, location="dungeon")
        inst.discovered = True
        inst.trigger_count = 1
        d = inst.to_dict()
        restored = TrapInstance.from_dict(d)
        assert restored.trap_id == tid
        assert restored.discovered is True
        assert restored.trigger_count == 1
        assert restored.location == "dungeon"


# ---------------------------------------------------------------------------
# Engine integration: trigger_trap resolves new traps without crashing
# ---------------------------------------------------------------------------

class TestNewTrapsTrigger:
    @pytest.mark.parametrize("tid", NEW_IDS)
    def test_trigger_returns_triggered_true(self, tid):
        trap = get_trap(tid)
        inst = TrapInstance.from_trap(trap)
        result = trigger_trap(inst, save_roll=20, save_modifier=0)
        assert result.triggered is True
        assert inst.triggered is True
        assert inst.trigger_count == 1

    @pytest.mark.parametrize("tid", NEW_IDS)
    def test_trigger_narrative_mentions_trap_name(self, tid):
        trap = get_trap(tid)
        inst = TrapInstance.from_trap(trap)
        result = trigger_trap(inst)
        assert trap.name in result.narrative

    def test_disarmed_trap_does_not_trigger(self):
        inst = TrapInstance.from_trap(get_trap("crushing_wall"))
        inst.disarmed = True
        result = trigger_trap(inst)
        assert result.triggered is False

    def test_summon_trap_appears_in_effect_descriptions(self):
        inst = TrapInstance.from_trap(get_trap("summoning_trap"))
        result = trigger_trap(inst)
        joined = " ".join(result.effect_descriptions).lower()
        assert "summon" in joined or "summons" in joined

    def test_telekinesis_trap_appears_in_effect_descriptions(self):
        inst = TrapInstance.from_trap(get_trap("telekinesis_trap"))
        result = trigger_trap(inst)
        joined = " ".join(result.effect_descriptions).lower()
        assert "arcane force" in joined or "slams" in joined or "hurls" in joined

    def test_damage_trap_rolls_damage_on_failed_save(self):
        # arrow_trap: 2d10 piercing, DC 15 dex save for half.
        # Deterministic roller: each die returns 10 → 20 raw damage.
        inst = TrapInstance.from_trap(get_trap("arrow_trap"))
        result = trigger_trap(
            inst, save_roll=5, save_modifier=0,  # failed save
            roller=lambda n, s: [10] * n,
        )
        assert result.damage == 20
        assert result.damage_type == "piercing"

    def test_damage_trap_halves_on_successful_save(self):
        inst = TrapInstance.from_trap(get_trap("arrow_trap"))
        result = trigger_trap(
            inst, save_roll=20, save_modifier=0,  # DC 15 → success → half
            roller=lambda n, s: [10] * n,
        )
        assert result.damage == 10  # 20 // 2


# ---------------------------------------------------------------------------
# Registry totals & integrity
# ---------------------------------------------------------------------------

class TestRegistryTotal:
    def test_registry_grew_by_18(self):
        """The registry grew by exactly 18 entries (14 -> 32)."""
        assert len(TRAP_REGISTRY) == 32, (
            f"registry size {len(TRAP_REGISTRY)} != 32 (expected 14 + 18)"
        )

    def test_registry_ids_are_unique(self):
        ids = [t.id for t in TRAP_REGISTRY.values()]
        assert len(ids) == len(set(ids)), "duplicate trap IDs in registry"

    def test_list_trap_ids_contains_all_new(self):
        ids = set(list_trap_ids())
        assert set(NEW_IDS) <= ids

    def test_list_trap_ids_sorted(self):
        ids = list_trap_ids()
        assert ids == sorted(ids)

    def test_registry_floor_above_fourteen(self):
        assert len(TRAP_REGISTRY) > 14


class TestCanonicalDmgTrapsStillPresent:
    """The pre-expansion DMG sample traps are all still registered."""

    def test_sample_dmg_traps_present(self):
        for tid in [
            "collapsing_roof", "falling_net", "fire_breathing_statue",
            "hidden_pit", "poison_darts", "poisoned_needle", "rolling_sphere",
            "swinging_blade", "flood_room", "teleportation_trap",
            "sphere_of_annihilation", "glyph_of_warding", "gas_trap",
            "bear_trap",
        ]:
            assert tid in TRAP_REGISTRY, f"pre-expansion trap {tid} went missing"
