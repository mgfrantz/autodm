"""
Tests for the Phase 3.5b AoE spell-resolution primitives:

- ``Spellbook.prepare_cast`` — validate + consume ONE slot WITHOUT resolving
  the effect (the AoE enabler that splits slot-consumption from resolution).
- ``resolve_spell_aoe_target`` — resolve one AoE target's outcome against a
  shared (pre-rolled) damage roll, per PHB p.204.
"""
import pytest

from app.engine.spells import (
    Spellbook,
    resolve_spell_aoe_target,
    get_spell,
    Spell,
)


def _spell(spell_id: str) -> Spell:
    """Look up a spell, failing the test if it isn't registered."""
    s = get_spell(spell_id)
    assert s is not None, f"spell '{spell_id}' not registered"
    return s


# ---------------------------------------------------------------------------
# Spellbook.prepare_cast
# ---------------------------------------------------------------------------

class TestPrepareCast:
    """prepare_cast consumes exactly one slot and does NOT resolve the effect."""

    def _book(self, prepared=("fireball",), slots_used=None):
        return Spellbook(
            char_class="wizard", level=5,
            known_spells=["fire_bolt"],
            prepared_spells=list(prepared),
            slots_used=slots_used or [0] * 9,
        )

    def test_success_consumes_one_slot_and_returns_no_effect(self):
        book = self._book()
        oc = book.prepare_cast("fireball", slot_level=3)
        assert oc.success is True
        assert oc.spell is not None and oc.spell.name == "Fireball"
        assert oc.slot_level == 3
        assert oc.effect is None  # the whole point: no resolution
        # Wizard L5 has two 3rd-level slots → one remaining.
        assert book.available_slots(3) == 1

    def test_auto_picks_lowest_available_slot(self):
        book = self._book()
        oc = book.prepare_cast("fireball")  # no slot_level → auto
        assert oc.success is True
        # Fireball is level 3 → lowest available L3+ slot is 3.
        assert oc.slot_level == 3
        assert book.available_slots(3) == 1

    def test_cantrip_consumes_no_slot(self):
        book = self._book(prepared=[])
        # fire_bolt is a known cantrip.
        oc = book.prepare_cast("fire_bolt")
        assert oc.success is True
        assert oc.slot_level == 0
        # No slots of any level consumed.
        assert all(book.slots_used(lvl) == 0 for lvl in range(1, 10))

    def test_unknown_spell_fails_without_consuming(self):
        book = self._book()
        oc = book.prepare_cast("definitely_not_real")
        assert oc.success is False
        assert "Unknown" in oc.message
        assert all(book.slots_used(lvl) == 0 for lvl in range(1, 10))

    def test_non_caster_fails(self):
        book = Spellbook(char_class="fighter", level=5)
        oc = book.prepare_cast("fireball")
        assert oc.success is False
        assert "cannot cast" in oc.message.lower()

    def test_not_known_or_prepared_fails(self):
        book = self._book(prepared=("burning_hands",))  # fireball not prepared
        oc = book.prepare_cast("fireball")
        assert oc.success is False
        assert "not available" in oc.message.lower()
        assert all(book.slots_used(lvl) == 0 for lvl in range(1, 10))

    def test_no_slots_available_fails_without_consuming(self):
        # Wizard L5 has two L3 slots and NO L4+ slots; exhaust L3.
        slots = [0, 0, 2, 0, 0, 0, 0, 0, 0]
        book = self._book(slots_used=slots)
        oc = book.prepare_cast("fireball", slot_level=3)
        assert oc.success is False
        # No L3+ slot is available at all → generic "no slots" message.
        assert "No spell slots available" in oc.message
        # No additional slot consumed.
        assert book.slots_used(3) == 2

    def test_requested_slot_full_but_higher_available_fails(self):
        """If the requested slot is full but a higher one is free, the cast
        still refuses (caller asked for a specific slot that's unavailable)."""
        # Wizard L7 has 3 L3 slots + 1 L4 slot; exhaust L3, leave L4 free.
        book = Spellbook(
            char_class="wizard", level=7, known_spells=["fire_bolt"],
            prepared_spells=["fireball"], slots_used=[0, 0, 3, 0, 0, 0, 0, 0, 0],
        )
        assert book.max_slots(4) >= 1  # L7 wizard has a L4 slot
        assert book.available_slots(3) == 0
        oc = book.prepare_cast("fireball", slot_level=3)
        assert oc.success is False
        assert "No level-3 slots available" in oc.message
        # The free L4 slot is NOT silently consumed.
        assert book.slots_used(4) == 0

    def test_no_slots_at_or_above_level_fails(self):
        # Exhaust every slot.
        slots = [4, 3, 2, 0, 0, 0, 0, 0, 0]  # L1+L2+L3 full for a L5 wizard
        book = self._book(slots_used=slots)
        oc = book.prepare_cast("fireball")  # needs a L3+ slot
        assert oc.success is False
        assert "No spell slots available" in oc.message

    def test_component_blocked_by_condition_fails(self):
        # burning_hands needs V,S → somatic blocked by paralyzed/stunned.
        book = self._book(prepared=("burning_hands",))
        oc = book.prepare_cast("burning_hands", slot_level=1,
                               active_conditions=["paralyzed"])
        assert oc.success is False
        # No slot consumed on failure.
        assert book.slots_used(1) == 0

    def test_accepts_spell_name_with_spaces(self):
        book = self._book()
        oc = book.prepare_cast("Fireball", slot_level=3)
        assert oc.success is True
        assert oc.spell is not None
        assert oc.spell.name == "Fireball"


# ---------------------------------------------------------------------------
# resolve_spell_aoe_target
# ---------------------------------------------------------------------------

class TestResolveSpellAoeTarget:
    """Per-target AoE resolution against a shared damage roll (PHB p.204)."""

    def test_save_pass_yields_half_damage(self):
        fireball = _spell("fireball")
        res = resolve_spell_aoe_target(
            fireball, slot_level=3, full_damage=30,
            target_save_total=20, spell_save_dc=15,
        )
        assert res.made_save is True
        assert res.half_damage is True
        assert res.damage == 15
        assert res.damage_type == "fire"

    def test_save_fail_yields_full_damage(self):
        fireball = _spell("fireball")
        res = resolve_spell_aoe_target(
            fireball, slot_level=3, full_damage=30,
            target_save_total=5, spell_save_dc=15,
        )
        assert res.made_save is False
        assert res.half_damage is False
        assert res.damage == 30

    def test_no_save_total_applies_full_damage(self):
        fireball = _spell("fireball")
        res = resolve_spell_aoe_target(
            fireball, slot_level=3, full_damage=27,
            target_save_total=None, spell_save_dc=15,
        )
        assert res.made_save is None
        assert res.damage == 27
        assert res.half_damage is False

    def test_half_damage_rounds_down(self):
        fireball = _spell("fireball")
        res = resolve_spell_aoe_target(
            fireball, slot_level=3, full_damage=29,
            target_save_total=20, spell_save_dc=15,
        )
        assert res.damage == 14  # 29 // 2

    def test_all_targets_share_one_damage_value(self):
        """The same full_damage feeds every target (one roll, N saves)."""
        fireball = _spell("fireball")
        full = 28
        results = [
            resolve_spell_aoe_target(fireball, 3, full, t, 15)
            for t in (20, 4, 20)  # save, fail, save
        ]
        # Savers take half (14), failer takes full (28). All ≤ full.
        assert results[0].damage == 14
        assert results[1].damage == 28
        assert results[2].damage == 14
        assert all(r.damage <= full for r in results)

    def test_auto_damage_no_save_full_to_each(self):
        """A non-save damage AoE deals full damage with no save outcome."""
        # Build a minimal auto-damage spell via the registry is awkward; use a
        # save-less damaging spell if one exists, else skip gracefully.
        missile = get_spell("magic_missile")
        if missile is None or missile.save_ability is not None:
            pytest.skip("No auto-damage spell available for this assertion")
        res = resolve_spell_aoe_target(
            missile, slot_level=1, full_damage=10,
            target_save_total=None, spell_save_dc=None,
        )
        assert res.damage == 10
        assert res.made_save is None

    def test_zero_damage_spell_returns_zero(self):
        """A non-damaging AoE (e.g. an area debuff) deals no damage."""
        # Hold Person has a save but no damage dice.
        hold = get_spell("hold_person")
        if hold is None:
            pytest.skip("hold_person not registered")
        res = resolve_spell_aoe_target(
            hold, slot_level=3, full_damage=0,
            target_save_total=20, spell_save_dc=15,
        )
        assert res.damage == 0
        assert res.made_save is True
