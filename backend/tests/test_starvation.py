"""
Tests for the starvation/dehydration engine — DnD 5e food & water survival rules.

Covers:
- Daily needs lookup and the 'hot' doubling of water need.
- Food grace period (3 + CON mod, min 1) and the reset-on-eating behaviour.
- Automatic starvation exhaustion beyond the grace period.
- Dehydration: less-than-half → automatic exhaustion; half → DC 15 CON save
  (success suppresses, failure inflicts) with injectable rolls.
- Exhaustion projection: clamping to 0–6 and death at 6.
- SurvivalState round-trip serialisation and deficit_summary.
- Determinism under test (save_roll + roller injection).
"""
import pytest

from app.engine import starvation as stv
from app.engine.exhaustion import MAX_EXHAUSTION


# --------------------------------------------------------------------------- #
# Daily needs / helpers
# --------------------------------------------------------------------------- #

class TestNeeds:
    def test_daily_needs_temperate(self):
        n = stv.daily_needs(hot=False)
        assert n == {"food": stv.DAILY_FOOD_LBS, "water": stv.DAILY_WATER_GAL}

    def test_daily_needs_hot_doubles_water(self):
        n = stv.daily_needs(hot=True)
        assert n["water"] == stv.HOT_WATER_GAL
        assert n["food"] == stv.DAILY_FOOD_LBS

    @pytest.mark.parametrize("temp,expected", [
        ("normal", False),
        ("cold", False),
        ("heat", True),
        ("extreme_heat", True),
        ("HEAT", True),  # case-insensitive
        ("", False),
    ])
    def test_is_hot(self, temp, expected):
        assert stv.is_hot(temp) is expected

    def test_food_grace_days(self):
        assert stv.food_grace_days(0) == 3
        assert stv.food_grace_days(2) == 5
        assert stv.food_grace_days(-1) == 2
        assert stv.food_grace_days(-5) == 1  # minimum 1
        assert stv.food_grace_days(5) == 8


# --------------------------------------------------------------------------- #
# Well-fed baseline
# --------------------------------------------------------------------------- #

class TestWellFed:
    def test_full_intake_no_exhaustion_and_resets(self):
        state = stv.SurvivalState(days_without_food=2, days_without_water=2)
        r = stv.advance_day(
            state, food_lbs=1, water_gal=1, con_modifier=0, current_exhaustion=0
        )
        assert r.food_intake_ok is True
        assert r.water_intake_ok is True
        assert r.exhaustion_added == 0
        assert r.state.days_without_food == 0   # reset
        assert r.state.days_without_water == 0  # reset
        assert r.died is False

    def test_does_not_mutate_input_state(self):
        state = stv.SurvivalState(days_without_food=1)
        stv.advance_day(state, food_lbs=0, water_gal=1, con_modifier=0)
        # The caller's state object is untouched (engine works on a copy).
        assert state.days_without_food == 1


# --------------------------------------------------------------------------- #
# Starvation (food)
# --------------------------------------------------------------------------- #

class TestStarvation:
    def test_within_grace_no_exhaustion(self):
        # CON +0 → grace 3; three days without food is fine.
        state = stv.SurvivalState()
        for _ in range(3):
            r = stv.advance_day(state, food_lbs=0, water_gal=1, con_modifier=0)
            assert r.exhaustion_from_food == 0
            state = r.state
        assert state.days_without_food == 3

    def test_beyond_grace_inflicts_exhaustion(self):
        # Day 4 (days_without_food=4 > grace 3) → 1 exhaustion.
        state = stv.SurvivalState()
        total = 0
        added = 0
        for day in range(1, 5):
            r = stv.advance_day(
                state, food_lbs=0, water_gal=1, con_modifier=0,
                current_exhaustion=total,
            )
            state = r.state
            total = r.new_exhaustion
            if day == 4:
                added = r.exhaustion_from_food
        assert added == 1
        assert total == 1

    def test_eating_resets_counter(self):
        # Two days without, then a full meal resets to zero.
        state = stv.SurvivalState()
        r = stv.advance_day(state, food_lbs=0, water_gal=1, con_modifier=0)
        r = stv.advance_day(r.state, food_lbs=0, water_gal=1, con_modifier=0)
        assert r.state.days_without_food == 2
        r = stv.advance_day(r.state, food_lbs=1, water_gal=1, con_modifier=0)
        assert r.state.days_without_food == 0
        assert r.exhaustion_from_food == 0

    def test_high_con_extends_grace(self):
        # CON +4 → grace 7; day 7 still fine, day 8 inflicts.
        con = 4
        state = stv.SurvivalState()
        for day in range(1, 8):  # days 1..7 within grace 7
            r = stv.advance_day(
                state, food_lbs=0, water_gal=1, con_modifier=con
            )
            assert r.exhaustion_from_food == 0
            state = r.state
        # Day 8 → beyond grace.
        r = stv.advance_day(state, food_lbs=0, water_gal=1, con_modifier=con)
        assert r.exhaustion_from_food == 1


# --------------------------------------------------------------------------- #
# Dehydration (water)
# --------------------------------------------------------------------------- #

class TestDehydration:
    def test_less_than_half_is_automatic(self):
        # 0 water (< 0.5 of need 1) → automatic exhaustion, no save.
        r = stv.advance_day(
            stv.SurvivalState(), food_lbs=1, water_gal=0, con_modifier=0
        )
        assert r.water_intake_ok is False
        assert r.water_half_or_more is False
        assert r.exhaustion_from_water == 1
        assert r.thirst_save_success is None  # no save rolled
        assert r.thirst_save_dc is None

    def test_half_rations_save_failure_inflicts(self):
        r = stv.advance_day(
            stv.SurvivalState(), food_lbs=1, water_gal=0.5,
            con_modifier=0, save_roll=1,  # 1 + 0 < 15
        )
        assert r.water_half_or_more is True
        assert r.water_intake_ok is False
        assert r.thirst_save_dc == stv.THIRST_SAVE_DC
        assert r.thirst_save_success is False
        assert r.exhaustion_from_water == 1

    def test_half_rations_save_success_suppresses(self):
        r = stv.advance_day(
            stv.SurvivalState(), food_lbs=1, water_gal=0.5,
            con_modifier=0, save_roll=20,  # 20 + 0 >= 15
        )
        assert r.thirst_save_success is True
        assert r.exhaustion_from_water == 0
        assert r.exhaustion_added == 0

    def test_save_uses_explicit_bonus(self):
        # CON +1 but explicit save_bonus = +4 (proficient save): roll 11 + 4 = 15.
        r = stv.advance_day(
            stv.SurvivalState(), food_lbs=1, water_gal=0.5,
            con_modifier=1, save_bonus=4, save_roll=11,
        )
        assert r.thirst_save_bonus == 4
        assert r.thirst_save_success is True
        assert r.exhaustion_from_water == 0

    def test_save_default_bonus_is_con_modifier(self):
        r = stv.advance_day(
            stv.SurvivalState(), food_lbs=1, water_gal=0.5,
            con_modifier=2, save_roll=13,  # 13 + 2 = 15 >= 15
        )
        assert r.thirst_save_bonus == 2
        assert r.thirst_save_success is True

    def test_hot_doubles_water_need(self):
        # In hot weather 1 gallon is exactly half of the 2-gallon need → save.
        r = stv.advance_day(
            stv.SurvivalState(), food_lbs=1, water_gal=1,
            hot=True, con_modifier=0, save_roll=20,
        )
        assert r.water_needed == stv.HOT_WATER_GAL
        assert r.water_intake_ok is False
        assert r.water_half_or_more is True  # 1 >= 2/2
        assert r.thirst_save_dc == stv.THIRST_SAVE_DC

    def test_hot_full_intake_no_save(self):
        r = stv.advance_day(
            stv.SurvivalState(), food_lbs=1, water_gal=2,
            hot=True, con_modifier=0,
        )
        assert r.water_intake_ok is True
        assert r.exhaustion_from_water == 0

    def test_roller_injection_is_deterministic(self):
        calls: list[int] = []

        def fake_roller(bonus: int) -> int:
            calls.append(bonus)
            return 5 + bonus  # total

        r = stv.advance_day(
            stv.SurvivalState(), food_lbs=1, water_gal=0.5,
            con_modifier=0, roller=fake_roller,  # 5 + 0 < 15 → fail
        )
        assert calls == [0]
        assert r.thirst_save_roll == 5
        assert r.thirst_save_success is False
        assert r.exhaustion_from_water == 1


# --------------------------------------------------------------------------- #
# Exhaustion projection / death
# --------------------------------------------------------------------------- #

class TestProjection:
    def test_both_starve_in_one_day(self):
        # No food beyond grace AND no water → food + water exhaustion.
        state = stv.SurvivalState(days_without_food=4)  # already beyond grace 3
        r = stv.advance_day(
            state, food_lbs=0, water_gal=0, con_modifier=0, current_exhaustion=0
        )
        assert r.exhaustion_from_food == 1
        assert r.exhaustion_from_water == 1
        assert r.exhaustion_added == 2
        assert r.new_exhaustion == 2

    def test_clamps_to_six_and_death(self):
        # Already at 5; dehydration auto → 6 → death.
        r = stv.advance_day(
            stv.SurvivalState(), food_lbs=1, water_gal=0,
            con_modifier=0, current_exhaustion=5,
        )
        assert r.new_exhaustion == MAX_EXHAUSTION
        assert r.died is True

    def test_does_not_exceed_max(self):
        r = stv.advance_day(
            stv.SurvivalState(), food_lbs=0, water_gal=0,
            con_modifier=0, current_exhaustion=6,
        )
        assert r.new_exhaustion == MAX_EXHAUSTION
        assert r.died is True

    def test_messages_populated(self):
        r = stv.advance_day(
            stv.SurvivalState(), food_lbs=1, water_gal=0, con_modifier=0
        )
        assert any("dehydration" in m.lower() or "water" in m.lower() for m in r.messages)
        # Well-fed day gets a benign message.
        r2 = stv.advance_day(
            stv.SurvivalState(), food_lbs=1, water_gal=1, con_modifier=0
        )
        assert any("well" in m.lower() for m in r2.messages)


# --------------------------------------------------------------------------- #
# Serialisation + summary
# --------------------------------------------------------------------------- #

class TestSerialisation:
    def test_state_round_trip(self):
        s = stv.SurvivalState(days_without_food=3, days_without_water=1)
        d = s.to_dict()
        assert d == {"days_without_food": 3, "days_without_water": 1}
        s2 = stv.SurvivalState.from_dict(d)
        assert s2 == s

    def test_state_from_none_or_empty(self):
        assert stv.SurvivalState.from_dict(None) == stv.SurvivalState()
        assert stv.SurvivalState.from_dict({}) == stv.SurvivalState()

    def test_state_from_bad_data_is_safe(self):
        assert stv.SurvivalState.from_dict({"days_without_food": "oops"}) == stv.SurvivalState()
        assert stv.SurvivalState.from_dict({"days_without_food": -7}).days_without_food == 0

    def test_result_to_dict_keys(self):
        r = stv.advance_day(
            stv.SurvivalState(), food_lbs=0, water_gal=0, con_modifier=0
        )
        d = r.to_dict()
        for key in ("state", "exhaustion_added", "new_exhaustion", "died", "messages",
                    "thirst_save_dc", "water_needed"):
            assert key in d
        assert d["state"]["days_without_food"] == 1

    def test_deficit_summary(self):
        s = stv.SurvivalState(days_without_food=2, days_without_water=1)
        summ = stv.deficit_summary(s, con_modifier=0, hot=False)
        assert summ["food_grace_days"] == 3
        assert summ["food_days_until_exhaustion"] == 1  # 3 - 2
        assert summ["starving"] is False
        assert summ["dehydrated"] is True
        assert summ["daily_water_gal"] == stv.DAILY_WATER_GAL

        s_hot = stv.SurvivalState(days_without_food=5)
        summ_hot = stv.deficit_summary(s_hot, con_modifier=1, hot=True)
        assert summ_hot["food_grace_days"] == 4
        assert summ_hot["starving"] is True  # 5 > 4
        assert summ_hot["daily_water_gal"] == stv.HOT_WATER_GAL
