"""
Tests for the downtime activities engine (PHB ch.8 + XGE ch.2).

Pure-engine tests: no DB, no LLM. All dice are forced for determinism.
"""
import pytest

from app.engine import downtime as dt


# --------------------------------------------------------------------------- #
# Registry / definitions
# --------------------------------------------------------------------------- #

class TestActivityRegistry:
    def test_all_eleven_activities_present(self):
        ids = set(dt.DOWNTIME_ACTIVITIES)
        assert ids == {
            "carousing", "crime", "gambling", "pit_fighting", "research",
            "relaxation", "crafting", "profession", "work", "training",
            "religion",
        }

    def test_list_activities_is_sorted_and_complete(self):
        activities = dt.list_activities()
        assert len(activities) == 11
        # Sorted by (category, name).
        keys = [(a.category, a.name) for a in activities]
        assert keys == sorted(keys)

    def test_get_activity_case_insensitive(self):
        a = dt.get_activity("Carousing")
        assert a is not None
        assert a.id == "carousing"

    def test_get_activity_unknown_returns_none(self):
        assert dt.get_activity("partying") is None
        assert dt.get_activity("") is None

    def test_each_activity_has_required_fields(self):
        for a in dt.DOWNTIME_ACTIVITIES.values():
            assert a.id and a.name and a.source in {"PHB", "XGE"}
            assert a.category
            assert a.description
            assert a.min_days >= 1

    def test_downtime_summary_for_dm(self):
        s = dt.downtime_summary_for_dm("carousing")
        assert "Carousing" in s and "XGE" in s
        assert dt.downtime_summary_for_dm("nope") == ""


# --------------------------------------------------------------------------- #
# Result helpers
# --------------------------------------------------------------------------- #

class TestResultDataclass:
    def test_earned_and_spent(self):
        r = dt.DowntimeResult(activity="x", days=1, gold_delta=150)
        assert r.earned == 150 and r.spent == 0
        r2 = dt.DowntimeResult(activity="x", days=1, gold_delta=-50)
        assert r2.earned == 0 and r2.spent == 50
        assert r2.gold_delta == -50

    def test_to_dict_roundtrip(self):
        r = dt.DowntimeResult(
            activity="x", days=3, gold_delta=-10, narration="hi",
            complication="bad", details={"a": 1},
        )
        d = r.to_dict()
        assert d["activity"] == "x"
        assert d["days"] == 3
        assert d["gold_delta"] == -10
        assert d["details"] == {"a": 1}


# --------------------------------------------------------------------------- #
# Complication helpers
# --------------------------------------------------------------------------- #

class TestComplicationHelpers:
    def test_complication_triggered_only_on_one(self):
        assert dt._complication_triggered(1) is True
        for v in (2, 3, 4, 5, 6):
            assert dt._complication_triggered(v) is False

    def test_pick_complication_maps_d20_modulo(self):
        table = ("a", "b", "c", "d")
        # d20 1..4 -> idx 0..3; d20 5..8 -> idx 0..3 again (mod 4)
        assert dt._pick_complication(table, 1) == "a"
        assert dt._pick_complication(table, 4) == "d"
        assert dt._pick_complication(table, 5) == "a"

    def test_parse_complication_save_with_tag(self):
        body, dc, ab = dt._parse_complication_save(
            "[DC10 Con] You heave all night."
        )
        assert body == "You heave all night."
        assert dc == 10 and ab == "con"

    def test_parse_complication_save_without_tag(self):
        body, dc, ab = dt._parse_complication_save("A new friend appears.")
        assert body == "A new friend appears."
        assert dc == 0 and ab == ""


# --------------------------------------------------------------------------- #
# Carousing
# --------------------------------------------------------------------------- #

class TestCarousing:
    def test_cost_and_days_scale_with_workweeks(self):
        r = dt.carouse("middle", workweeks=2, d6=6)  # d6=6 → no complication
        assert r.days == 10            # 5 days/workweek
        assert r.gold_delta == -100    # 50 gp/week * 2
        assert r.details["tier"] == "middle"
        assert r.complication is None

    def test_tier_costs_match_xge(self):
        assert dt.carouse("lower").gold_delta == -10
        assert dt.carouse("middle").gold_delta == -50
        assert dt.carouse("upper").gold_delta == -250

    def test_unknown_tier_defaults_to_middle(self):
        assert dt.carouse("platinum").gold_delta == -50
        assert dt.carouse("platinum").details["tier"] == "middle"

    def test_complication_no_save_tag_when_present(self):
        # Force a complication (d6=1) and pick table entry with no save.
        # We iterate complication_d20 values until we hit a non-save entry.
        found_plain = False
        for d20 in range(1, 21):
            r = dt.carouse("lower", d6=1, complication_d20=d20)
            if r.complication and "DC" not in r.complication:
                found_plain = True
                break
        assert found_plain

    def test_complication_save_passed(self):
        # Lower-class table entry index 0 is a DC10 Con save.
        # d20 1 -> index 0 (len 6). save_modifier high to pass.
        r = dt.carouse("lower", d6=1, complication_d20=1,
                       save_modifier=20, save_roll=15)
        assert r.complication is not None
        assert "passed" in r.complication
        assert r.details["save_succeeded"] is True

    def test_complication_save_failed(self):
        r = dt.carouse("lower", d6=1, complication_d20=1,
                       save_modifier=-5, save_roll=2)
        assert r.complication is not None
        assert "failed" in r.complication
        assert r.details["save_succeeded"] is False
        assert r.details["save_roll"] == 2

    def test_no_complication_when_d6_not_one(self):
        r = dt.carouse("middle", d6=5)
        assert r.complication is None


# --------------------------------------------------------------------------- #
# Crime
# --------------------------------------------------------------------------- #

class TestCrime:
    def test_casing_fail_means_no_payout(self):
        r = dt.crime(casing_modifier=-5, casing_dc=20, casing_roll=1)
        assert r.details["casing_success"] is False
        assert r.details["payout"] == 0
        assert r.gold_delta == -100  # just the casing cost

    def test_perfect_heist_maxes_payout(self):
        r = dt.crime(
            casing_modifier=10, casing_dc=10, casing_roll=20,
            heist_modifier=10, heist_dc=10, heist_rolls=[20, 20, 20],
            max_payout=300,
        )
        assert r.details["casing_success"] is True
        assert r.details["heist_successes"] == 3
        assert r.details["payout"] == 300
        assert r.gold_delta == 200  # 300 payout - 100 cost

    def test_partial_heist_scales_payout(self):
        r = dt.crime(
            casing_modifier=10, casing_dc=10, casing_roll=15,
            heist_modifier=10, heist_dc=15, heist_rolls=[18, 5, 20],
            max_payout=300,
        )
        # successes: 18+10=28>=15 yes, 5+10=15>=15 yes, 20 auto yes -> 3
        assert r.details["heist_successes"] == 3

    def test_two_days_for_casing_plus_heist(self):
        r = dt.crime(casing_modifier=0, casing_dc=5, casing_roll=10)
        assert r.days == 10  # 2 workweeks

    def test_complication_on_d6_one(self):
        r = dt.crime(casing_modifier=0, casing_dc=5, casing_roll=10,
                     d6=1, complication_d20=1)
        assert r.complication is not None


# --------------------------------------------------------------------------- #
# Gambling
# --------------------------------------------------------------------------- #

class TestGambling:
    def test_all_wins_doubles_wager(self):
        r = dt.gamble(wager=100, modifier=10, dc=20, games=3, rolls=[20, 20, 20])
        # wins=3, losses=0 -> net = 100 * (3-0)/3 = 100
        assert r.gold_delta == 100
        assert r.details["wins"] == 3

    def test_all_losses_loses_wager(self):
        r = dt.gamble(wager=100, modifier=-5, dc=20, games=3, rolls=[1, 2, 3])
        assert r.details["wins"] == 0
        assert r.gold_delta == -100

    def test_break_even(self):
        r = dt.gamble(wager=100, modifier=0, dc=20, games=2, rolls=[20, 1])
        # wins=1, losses=1 -> net = 100*(1-1)/2 = 0
        assert r.gold_delta == 0

    def test_wager_clamped_to_zero(self):
        r = dt.gamble(wager=-50, modifier=0, dc=20, games=3, rolls=[1, 1, 1])
        assert r.gold_delta == 0
        assert r.details["wager"] == 0

    def test_complication(self):
        r = dt.gamble(wager=100, d6=1, complication_d20=2,
                      modifier=0, dc=20, games=1, rolls=[1])
        assert r.complication is not None


# --------------------------------------------------------------------------- #
# Pit fighting
# --------------------------------------------------------------------------- #

class TestPitFighting:
    def test_three_successes_top_purse(self):
        r = dt.pit_fight(modifier=10, dc=10, rolls=[15, 15, 15])
        assert r.details["successes"] == 3
        assert r.gold_delta == 500
        assert r.details["payout"] == 500

    def test_zero_successes_no_purse(self):
        r = dt.pit_fight(modifier=-5, dc=20, rolls=[1, 2, 3])
        assert r.details["successes"] == 0
        assert r.gold_delta == 0

    def test_payout_bands(self):
        # 1 success -> 50, 2 -> 150, 3 -> 500
        r1 = dt.pit_fight(modifier=10, dc=15, rolls=[20, 1, 1])
        assert r1.gold_delta == 50
        r2 = dt.pit_fight(modifier=10, dc=15, rolls=[20, 20, 1])
        assert r2.gold_delta == 150

    def test_complication(self):
        r = dt.pit_fight(modifier=10, dc=10, rolls=[20, 20, 20],
                            d6=1, complication_d20=1)
        assert r.complication is not None


# --------------------------------------------------------------------------- #
# Research
# --------------------------------------------------------------------------- #

class TestResearch:
    def test_all_successes_uncovers_facts(self):
        r = dt.research(modifier=10, dc=10, workweeks=2, roll=20)
        assert r.details["facts"] == 2
        assert r.details["false_leads"] == 0
        assert r.gold_delta == -(25 * 2)  # no extra

    def test_failures_cost_extra(self):
        r = dt.research(modifier=-5, dc=20, workweeks=2, roll=1)
        assert r.details["false_leads"] == 2
        # cost = 25*2 + 2*10 = 70
        assert r.gold_delta == -70

    def test_days_scale(self):
        assert dt.research(modifier=0, dc=10, workweeks=3, roll=20).days == 15


# --------------------------------------------------------------------------- #
# Relaxation
# --------------------------------------------------------------------------- #

class TestRelaxation:
    def test_cost_one_gp_per_day(self):
        r = dt.relax(days=5)
        assert r.gold_delta == -5

    def test_eases_one_exhaustion_after_a_week(self):
        r = dt.relax(days=5, current_exhaustion=3)
        assert r.details["exhaustion_delta"] == -1
        assert r.details["exhaustion_after"] == 2

    def test_no_ease_below_zero(self):
        r = dt.relax(days=5, current_exhaustion=0)
        assert r.details["exhaustion_delta"] == 0
        assert r.details["exhaustion_after"] == 0

    def test_short_rest_no_ease(self):
        r = dt.relax(days=2, current_exhaustion=2)
        assert r.details["exhaustion_delta"] == 0

    def test_clears_transient_conditions(self):
        r = dt.relax(days=5, current_exhaustion=0,
                     conditions=["frightened", "poisoned", "stunned"])
        assert set(r.details["cleared_conditions"]) == {"frightened", "poisoned"}
        assert "stunned" in r.details["remaining_conditions"]


# --------------------------------------------------------------------------- #
# Crafting
# --------------------------------------------------------------------------- #

class TestCrafting:
    def test_no_proficiency_blocks_crafting(self):
        r = dt.craft(50, days=5, proficiency_required=True, has_proficiency=False)
        assert r.gold_delta == 0
        assert r.details["complete"] is False
        assert r.details["reason"] == "no_proficiency"

    def test_progress_accumulates(self):
        r = dt.craft(50, days=5, progress_before=0)
        # materials = 25 up front, progress = 25
        assert r.details["starting"] is True
        assert r.details["progress_now"] == 25
        assert r.details["materials"] == 25
        assert r.gold_delta == -25
        assert r.details["complete"] is False

    def test_completion_produces_item(self):
        r = dt.craft(50, days=10, progress_before=0)
        # materials 25 (starting), +50 value on completion
        assert r.details["complete"] is True
        assert r.gold_delta == 25  # -25 + 50

    def test_continuation_no_double_materials(self):
        # Second period: not starting, so no materials charge.
        r = dt.craft(50, days=10, progress_before=25)
        assert r.details["starting"] is False
        assert r.details["materials"] == 0
        # progress 25 + 50 = 75 >= 50 -> complete, +50 value
        assert r.details["complete"] is True
        assert r.gold_delta == 50

    def test_materials_rounded_up(self):
        # value 51 -> materials = 26
        r = dt.craft(51, days=0, progress_before=0)
        assert r.details["materials"] == 26


# --------------------------------------------------------------------------- #
# Practicing a profession
# --------------------------------------------------------------------------- #

class TestProfession:
    def test_proficient_earns_d25_per_week(self):
        r = dt.practice_profession(workweeks=2, tool_proficiency=True, d25=20)
        assert r.gold_delta == 40  # 20 each week
        assert r.details["lifestyle"] == "comfortable"
        assert r.details["rolls"] == [20, 20]

    def test_unproficient_falls_back_to_work(self):
        r = dt.practice_profession(workweeks=2, tool_proficiency=False)
        assert r.gold_delta == 10  # 5 gp/week modest
        assert r.details["lifestyle"] == "modest"


class TestWork:
    def test_modest_earnings(self):
        r = dt.work(workweeks=3)
        assert r.gold_delta == 15
        assert r.details["lifestyle"] == "modest"


# --------------------------------------------------------------------------- #
# Training
# --------------------------------------------------------------------------- #

class TestTraining:
    def test_partial_progress(self):
        r = dt.train("thieves_tools", days=50, progress_before=0)
        assert r.details["complete"] is False
        assert r.details["progress_now"] == 50
        assert r.gold_delta == -50  # 1 gp/day
        assert "to go" in r.narration

    def test_completion_grants_proficiency(self):
        r = dt.train("elvish", days=250, progress_before=0, target_kind="language")
        assert r.details["complete"] is True
        assert "Completed" in r.narration
        assert r.gold_delta == -250

    def test_cumulative_completion(self):
        r = dt.train("brewers_supplies", days=50, progress_before=210)
        assert r.details["complete"] is True
        assert r.details["progress_now"] == 250


# --------------------------------------------------------------------------- #
# Religion
# --------------------------------------------------------------------------- #

class TestReligion:
    def test_success_eases_exhaustion(self):
        r = dt.religion(modifier=10, dc=10, current_exhaustion=2, roll=20)
        assert r.details["success"] is True
        assert r.details["exhaustion_delta"] == -1
        assert r.gold_delta == -5  # donation

    def test_failure_no_ease(self):
        r = dt.religion(modifier=-5, dc=20, current_exhaustion=2, roll=1)
        assert r.details["success"] is False
        assert r.details["exhaustion_delta"] == 0

    def test_no_ease_at_zero(self):
        r = dt.religion(modifier=10, dc=10, current_exhaustion=0, roll=20)
        assert r.details["exhaustion_delta"] == 0


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

class TestResolveDispatch:
    def test_dispatch_by_id(self):
        r = dt.resolve("work", workweeks=2)
        assert r.activity == "work"
        assert r.gold_delta == 10

    def test_dispatch_unknown_raises(self):
        with pytest.raises(ValueError):
            dt.resolve("skydiving")

    def test_dispatch_filters_unknown_kwargs(self):
        # carouse doesn't accept an unrelated kwarg; dispatch should filter it.
        r = dt.resolve("carousing", tier="lower", bogus=123)
        assert r.gold_delta == -10

    def test_dispatch_passes_kwargs_through(self):
        r = dt.resolve("gambling", wager=200, modifier=10, dc=20,
                       games=3, rolls=[20, 20, 20])
        assert r.gold_delta == 200
