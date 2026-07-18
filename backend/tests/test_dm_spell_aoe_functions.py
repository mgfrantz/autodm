"""
Tests for ``dm_cast_spell_aoe`` — the DM-callable AoE spell resolver.

Verifies the Phase 3.5b contract: ONE slot consumed, ONE damage roll, N
independent per-target saves, and a summary ``spell_cast`` event with
``is_aoe=True``. Uses deterministic damage by patching ``Spell.roll_damage``.
"""
from unittest.mock import patch

from app.engine.dm_functions import dm_cast_spell_aoe
from app.engine.game_events import GameEventType
from app.engine.spells import Spellbook


def _book(level=5, prepared=("fireball",)):
    return Spellbook(
        char_class="wizard", level=level,
        known_spells=["fire_bolt"],
        prepared_spells=list(prepared),
        slots_used=[0] * 9,
    )


class TestDmCastSpellAoe:
    def test_one_slot_consumed_per_target_saves(self):
        """3 targets, one slot, shared damage roll, per-target saves."""
        book = _book()
        with patch("app.engine.spells.Spell.roll_damage", return_value=30):
            summary, per_target = dm_cast_spell_aoe(
                spellbook=book, spell_id="fireball",
                target_specs=[
                    {"name": "Goblin A", "target_save_total": 20},  # save → half
                    {"name": "Goblin B", "target_save_total": 5},   # fail → full
                    {"name": "Goblin C", "target_save_total": 20},  # save → half
                ],
                slot_level=3, caster_mod=3,
            )
        # Exactly ONE slot consumed.
        assert book.available_slots(3) == 1  # wizard L5 has 2 L3 slots
        # Summary event.
        assert summary.type == GameEventType.SPELL_CAST
        assert summary.data["success"] is True
        assert summary.data["is_aoe"] is True
        assert summary.data["target_count"] == 3
        assert summary.data["slot_level"] == 3
        assert summary.data["save_dc"] == 14  # 8 + prof(3) + caster_mod(3)
        assert summary.data["save_ability"] == "dex"
        # total = 15 (half) + 30 (full) + 15 (half)
        assert summary.data["total_damage"] == 60
        # Per-target results.
        assert len(per_target) == 3
        names = {t["name"]: t for t in per_target}
        assert names["Goblin A"]["damage"] == 15
        assert names["Goblin A"]["made_save"] is True
        assert names["Goblin A"]["half_damage"] is True
        assert names["Goblin B"]["damage"] == 30
        assert names["Goblin B"]["made_save"] is False
        assert names["Goblin C"]["damage"] == 15

    def test_all_targets_share_one_damage_value(self):
        """The shared full-damage roll feeds every target."""
        book = _book()
        with patch("app.engine.spells.Spell.roll_damage", return_value=28):
            _, per_target = dm_cast_spell_aoe(
                spellbook=book, spell_id="fireball",
                target_specs=[
                    {"name": "A", "target_save_total": 20},
                    {"name": "B", "target_save_total": 20},
                ],
                slot_level=3, caster_mod=3,
            )
        # Both saved → both take 14 (28//2). Full damage was rolled once.
        assert all(t["damage"] == 14 for t in per_target)

    def test_failed_cast_no_slots_returns_failed_summary_and_empty(self):
        book = _book()
        # Exhaust all L3 slots (wizard L5 has 2).
        book._slots_used[2] = 2
        summary, per_target = dm_cast_spell_aoe(
            spellbook=book, spell_id="fireball",
            target_specs=[{"name": "Goblin", "target_save_total": 5}],
            slot_level=3, caster_mod=3,
        )
        assert summary.data["success"] is False
        assert "slot" in summary.data["message"].lower()
        assert per_target == []
        # is_aoe stays False on a failed pre-resolution cast.
        assert summary.data["is_aoe"] is False

    def test_empty_target_list_yields_zero_count_summary(self):
        book = _book()
        with patch("app.engine.spells.Spell.roll_damage", return_value=20):
            summary, per_target = dm_cast_spell_aoe(
                spellbook=book, spell_id="fireball",
                target_specs=[], slot_level=3, caster_mod=3,
            )
        # The slot IS consumed (cast happened), but no targets resolved.
        assert summary.data["success"] is True
        assert summary.data["is_aoe"] is True
        assert summary.data["target_count"] == 0
        assert summary.data["total_damage"] == 0
        assert per_target == []
        assert book.available_slots(3) == 1

    def test_unknown_spell_returns_failed_summary(self):
        book = _book()
        summary, per_target = dm_cast_spell_aoe(
            spellbook=book, spell_id="definitely_not_real",
            target_specs=[{"name": "X", "target_save_total": 5}],
            slot_level=3, caster_mod=3,
        )
        assert summary.data["success"] is False
        assert per_target == []

    def test_cantrip_aoe_consumes_no_slot(self):
        """A cantrip AoE (e.g. Acid Splash) consumes no slot."""
        # Acid Splash may not be registered; use fire_bolt (cantrip) which is.
        # fire_bolt is single-target in flavor but the engine treats it as a
        # cantrip — prepare_cast returns slot_level 0 and consumes nothing.
        book = _book()
        summary, _ = dm_cast_spell_aoe(
            spellbook=book, spell_id="fire_bolt",
            target_specs=[{"name": "A", "target_save_total": 20}],
            caster_mod=3,
        )
        assert summary.data["success"] is True
        assert summary.data["slot_level"] is None  # cantrip → None
        assert all(book.slots_used(lvl) == 0 for lvl in range(1, 10))

    def test_summary_event_serializes_to_dict(self):
        book = _book()
        with patch("app.engine.spells.Spell.roll_damage", return_value=24):
            summary, _ = dm_cast_spell_aoe(
                spellbook=book, spell_id="fireball",
                target_specs=[
                    {"name": "A", "target_save_total": 20},
                    {"name": "B", "target_save_total": 5},
                ],
                slot_level=3, caster_mod=3,
            )
        import json
        parsed = json.loads(json.dumps(summary.to_dict()))
        assert parsed["type"] == "spell_cast"
        assert parsed["data"]["is_aoe"] is True
        assert parsed["data"]["target_count"] == 2
        # total = 12 (half) + 24 (full)
        assert parsed["data"]["total_damage"] == 36

    def test_non_caster_returns_failed_summary(self):
        book = Spellbook(char_class="fighter", level=5)
        summary, per_target = dm_cast_spell_aoe(
            spellbook=book, spell_id="fireball",
            target_specs=[{"name": "A", "target_save_total": 5}],
            slot_level=3, caster_mod=0,
        )
        assert summary.data["success"] is False
        assert per_target == []

    def test_concentration_flag_not_set_by_dm_function(self):
        """dm_cast_spell_aoe does not itself start concentration; the API
        handler owns that coupling (mirrors dm_cast_spell). The summary event
        should not carry concentration_started from this function."""
        book = _book()
        with patch("app.engine.spells.Spell.roll_damage", return_value=20):
            summary, _ = dm_cast_spell_aoe(
                spellbook=book, spell_id="fireball",
                target_specs=[{"name": "A", "target_save_total": 5}],
                slot_level=3, caster_mod=3,
            )
        assert "concentration_started" not in summary.data
