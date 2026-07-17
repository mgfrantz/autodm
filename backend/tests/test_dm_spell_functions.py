"""
Tests for the DM-callable spell function (Phase 3) — ``dm_cast_spell`` wraps
``Spellbook.cast()`` and produces a ``spell_cast`` GameEvent.

Dice rolls are mocked where deterministic hit/miss/damage outcomes are needed.
"""
from unittest.mock import patch

import pytest

from app.engine.dice import RollResult
from app.engine.game_events import GameEvent, GameEventType
from app.engine.dm_functions import dm_cast_spell
from app.engine.spells import Spellbook


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wizard_book() -> Spellbook:
    """A level-3 wizard (PREPARED caster) with a mix of spell kinds.

    - fire_bolt:  attack-roll cantrip (evocation, 1d10 fire)
    - sacred_flame: saving-throw cantrip (dex save, 1d8 radiant)
    - magic_missile: auto-damage level-1 spell (force)
    - cure_wounds: healing level-1 spell
    """
    return Spellbook(
        char_class="wizard",
        level=3,
        known_spells=["fire_bolt", "sacred_flame"],
        prepared_spells=["magic_missile", "cure_wounds"],
        slots_used=[0] * 9,
    )


def _d20(total: int, nat: int | None = None) -> RollResult:
    """Build a RollResult for a mocked d20 roll."""
    rolls = [nat if nat is not None else total]
    return RollResult(rolls=rolls, modifier=0, total=total, description="d20")


# ===========================================================================
# Attack-roll spells
# ===========================================================================

class TestDmCastSpellAttackRoll:
    """dm_cast_spell resolves attack-roll spells (d20 vs AC)."""

    def test_attack_roll_hit(self):
        book = _wizard_book()
        with patch("app.engine.spells.roll_d20", return_value=_d20(24, nat=18)), \
             patch("app.engine.spells.roll_dice", return_value=RollResult(
                 rolls=[10], modifier=0, total=10, description="1d10")):
            event = dm_cast_spell(book, "fire_bolt", caster_mod=4, target_ac=12)
        assert event.type == GameEventType.SPELL_CAST
        assert event.data["success"] is True
        assert event.data["hit"] is True
        assert event.data["attack_total"] == 24
        assert event.data["damage"] == 10
        assert event.data["damage_type"] == "fire"
        assert event.data["school"] == "evocation"
        # Cantrip: no slot expended.
        assert event.data["slot_level"] is None

    def test_attack_roll_miss(self):
        book = _wizard_book()
        with patch("app.engine.spells.roll_d20", return_value=_d20(8, nat=2)):
            event = dm_cast_spell(book, "fire_bolt", caster_mod=4, target_ac=12)
        assert event.data["success"] is True  # the *cast* succeeded; the attack missed
        assert event.data["hit"] is False
        assert event.data["damage"] == 0

    def test_cantrip_does_not_consume_slot(self):
        book = _wizard_book()
        before = book.slots_overview()
        with patch("app.engine.spells.roll_d20", return_value=_d20(24, nat=18)):
            dm_cast_spell(book, "fire_bolt", caster_mod=4, target_ac=10)
        after = book.slots_overview()
        assert before == after  # no slots changed


# ===========================================================================
# Saving-throw spells
# ===========================================================================

class TestDmCastSpellSave:
    """dm_cast_spell resolves saving-throw spells (target rolls save)."""

    def test_save_spell_made_save_half_damage(self):
        book = _wizard_book()
        # sacred_flame: dex save, DC = 8 + prof(2) + mod(4) = 14
        with patch("app.engine.spells.roll_dice", return_value=RollResult(
                rolls=[8], modifier=0, total=8, description="1d8")):
            event = dm_cast_spell(
                book, "sacred_flame", caster_mod=4, target_save_total=20,
            )
        assert event.data["success"] is True
        assert event.data["made_save"] is True
        assert event.data["half_damage"] is True
        assert event.data["damage"] == 4  # 8 // 2
        assert event.data["save_dc"] == 14
        assert event.data["save_ability"] == "dex"

    def test_save_spell_failed_save_full_damage(self):
        book = _wizard_book()
        with patch("app.engine.spells.roll_dice", return_value=RollResult(
                rolls=[8], modifier=0, total=8, description="1d8")):
            event = dm_cast_spell(
                book, "sacred_flame", caster_mod=4, target_save_total=5,
            )
        assert event.data["made_save"] is False
        assert event.data["half_damage"] is False
        assert event.data["damage"] == 8  # full


# ===========================================================================
# Auto-damage / healing spells
# ===========================================================================

class TestDmCastSpellAutoAndHealing:
    """dm_cast_spell resolves auto-damage (Magic Missile) and healing spells."""

    def test_magic_missile_auto_damage(self):
        book = _wizard_book()
        with patch("app.engine.spells.roll_dice", return_value=RollResult(
                rolls=[3, 3, 3], modifier=0, total=9, description="3d4+3")):
            event = dm_cast_spell(book, "magic_missile", caster_mod=4)
        assert event.data["success"] is True
        assert event.data["damage"] == 9
        assert event.data["damage_type"] == "force"
        assert event.data["hit"] is None  # no attack roll
        assert event.data["made_save"] is None  # no save
        # Level-1 slot consumed.
        assert event.data["slot_level"] == 1
        assert book.slots_used(1) == 1

    def test_cure_wounds_healing(self):
        book = _wizard_book()
        with patch("app.engine.spells.roll_dice", return_value=RollResult(
                rolls=[8], modifier=0, total=8, description="1d8")):
            event = dm_cast_spell(book, "cure_wounds", caster_mod=4)
        assert event.data["success"] is True
        assert event.data["healing"] == 8
        assert event.data["damage"] == 0
        assert event.data["slot_level"] == 1
        assert book.slots_used(1) == 1

    def test_leveled_spell_consumes_slot(self):
        book = _wizard_book()
        with patch("app.engine.spells.roll_dice", return_value=RollResult(
                rolls=[3], modifier=0, total=3, description="1d4")):
            dm_cast_spell(book, "magic_missile", caster_mod=4)
        # A real level-1 slot was expended.
        assert book.available_slots(1) == 3  # started at 4


# ===========================================================================
# Failed casts
# ===========================================================================

class TestDmCastSpellFailures:
    """dm_cast_spell surfaces failed casts as first-class events."""

    def test_unknown_spell(self):
        book = _wizard_book()
        event = dm_cast_spell(book, "definitely_not_a_spell")
        assert event.type == GameEventType.SPELL_CAST
        assert event.data["success"] is False
        assert "Unknown" in event.data["message"]
        assert event.data["damage"] == 0

    def test_no_slots_available(self):
        # Exhaust every slot first.
        book = _wizard_book()
        book._slots_used = list(book._max_slots)  # all used
        event = dm_cast_spell(book, "cure_wounds", caster_mod=4)
        assert event.data["success"] is False
        assert "slot" in event.data["message"].lower() or "no" in event.data["message"].lower()

    def test_component_blocked_by_condition(self):
        # cure_wounds has V, S components; 'stunned' blocks verbal.
        book = _wizard_book()
        event = dm_cast_spell(
            book, "cure_wounds", caster_mod=4, active_conditions=["stunned"],
        )
        assert event.data["success"] is False
        assert event.data["message"]  # non-empty reason

    def test_failed_cast_label_indicates_failure(self):
        book = _wizard_book()
        event = dm_cast_spell(book, "nope")
        assert "failed" in event.label.lower()

    def test_attack_spell_without_target_is_defensive(self):
        """dm_cast_spell never raises for an attack spell lacking a target."""
        book = _wizard_book()
        # No target_ac for an attack-roll spell — must not raise.
        event = dm_cast_spell(book, "fire_bolt", caster_mod=4)
        assert event.type == GameEventType.SPELL_CAST
        assert event.data["success"] is False


# ===========================================================================
# Event shape / serialization
# ===========================================================================

class TestDmCastSpellEventShape:
    """The returned event is well-formed and JSON-serializable."""

    def test_slots_remaining_included_on_success(self):
        book = _wizard_book()
        with patch("app.engine.spells.roll_dice", return_value=RollResult(
                rolls=[8], modifier=0, total=8, description="1d8")):
            event = dm_cast_spell(book, "cure_wounds", caster_mod=4)
        assert event.data["slots_remaining"] is not None
        assert isinstance(event.data["slots_remaining"], list)

    def test_slots_remaining_none_on_failure(self):
        book = _wizard_book()
        event = dm_cast_spell(book, "nope")
        assert event.data["slots_remaining"] is None

    def test_event_is_json_serializable(self):
        import json
        book = _wizard_book()
        with patch("app.engine.spells.roll_d20", return_value=_d20(24, nat=18)):
            event = dm_cast_spell(book, "fire_bolt", caster_mod=4, target_ac=10)
        # Should not raise.
        parsed = json.loads(json.dumps(event.to_dict()))
        assert parsed["type"] == "spell_cast"
        assert parsed["data"]["spell_name"] == "Fire Bolt"
