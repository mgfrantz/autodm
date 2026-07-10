"""
Tests for the Social Interaction engine (DMG ch.4/ch.8 NPC interaction rules).

Covers:
- Attitude normalization / rank / shift / trust-bridge mapping.
- Condition-driven advantage/disadvantage on social checks (charmed, frightened,
  poisoned, adv+disadv cancellation).
- Reaction roll (2d6 + CHA mod) → attitude band boundaries.
- Influence check: DC-by-attitude table, success improves one step, failure
  holds, fail-by-5+ worsens, nat 1 worsens, auto-success when already helpful,
  advantage/disadvantage wiring.
- Insight-vs-Deception contest: active and passive, detect/no-detect, the
  required-argument guard.
- DM summary helper.
"""
import pytest

from app.engine import social


# --------------------------------------------------------------------------- #
# Attitude scale + trust bridge
# --------------------------------------------------------------------------- #

class TestAttitudeScale:
    @pytest.mark.parametrize("att,rank", [
        ("hostile", 0), ("unfriendly", 1), ("indifferent", 2),
        ("friendly", 3), ("helpful", 4),
    ])
    def test_canonical_ranks(self, att, rank):
        assert social.attitude_rank(att) == rank

    @pytest.mark.parametrize("alias,canonical", [
        ("neutral", "indifferent"), ("devoted", "helpful"), ("hated", "hostile"),
        ("NEUTRAL", "indifferent"), ("Friendly", "friendly"),
    ])
    def test_aliases_normalized(self, alias, canonical):
        assert social.normalize_attitude(alias) == canonical

    def test_unknown_collapses_to_indifferent(self):
        assert social.normalize_attitude("baffled") == "indifferent"
        assert social.normalize_attitude("") == "indifferent"
        assert social.normalize_attitude(None) == "indifferent"

    def test_shift_attitude_friendly_and_hostile(self):
        assert social.shift_attitude("indifferent", +1) == "friendly"
        assert social.shift_attitude("indifferent", -1) == "unfriendly"
        assert social.shift_attitude("indifferent", +5) == "helpful"  # clamps

    def test_shift_clamps_at_boundaries(self):
        assert social.shift_attitude("hostile", -3) == "hostile"
        assert social.shift_attitude("helpful", +3) == "helpful"

    def test_attitude_at_rank(self):
        assert social.attitude_at_rank(0) == "hostile"
        assert social.attitude_at_rank(4) == "helpful"
        assert social.attitude_at_rank(-2) == "hostile"  # clamp
        assert social.attitude_at_rank(99) == "helpful"


class TestTrustBridge:
    def test_attitude_for_trust_boundaries(self):
        assert social.attitude_for_trust(-100) == "hostile"
        assert social.attitude_for_trust(-75) == "hostile"
        assert social.attitude_for_trust(-74) == "unfriendly"
        assert social.attitude_for_trust(-25) == "unfriendly"
        assert social.attitude_for_trust(-24) == "indifferent"
        assert social.attitude_for_trust(0) == "indifferent"
        assert social.attitude_for_trust(24) == "indifferent"
        assert social.attitude_for_trust(25) == "friendly"
        assert social.attitude_for_trust(74) == "friendly"
        assert social.attitude_for_trust(75) == "helpful"
        assert social.attitude_for_trust(100) == "helpful"

    def test_trust_for_attitude_round_trips_into_band(self):
        # Each attitude's midpoint trust maps back to that attitude.
        for att in social.ATTITUDE_LEVELS:
            mid = social.trust_for_attitude(att)
            assert social.attitude_for_trust(mid) == att


# --------------------------------------------------------------------------- #
# Condition effects
# --------------------------------------------------------------------------- #

class TestSocialCheckAdvantage:
    def test_charmed_grants_advantage(self):
        adv, disadv = social.social_check_advantage(["charmed"])
        assert adv is True and disadv is False

    def test_frightened_imposes_disadvantage(self):
        adv, disadv = social.social_check_advantage(["frightened"])
        assert adv is False and disadv is True

    def test_poisoned_imposes_disadvantage(self):
        adv, disadv = social.social_check_advantage(["poisoned"])
        assert disadv is True

    def test_advantage_and_disadvantage_cancel(self):
        adv, disadv = social.social_check_advantage(["charmed", "frightened"])
        assert adv is False and disadv is False

    def test_no_conditions(self):
        adv, disadv = social.social_check_advantage([])
        assert adv is False and disadv is False

    def test_none_conditions(self):
        adv, disadv = social.social_check_advantage(None)
        assert adv is False and disadv is False

    def test_unrelated_conditions_ignored(self):
        adv, disadv = social.social_check_advantage(["prone", "restrained"])
        # restrained IS a disadvantage condition
        assert disadv is True


# --------------------------------------------------------------------------- #
# Reaction roll
# --------------------------------------------------------------------------- #

class TestReactionRoll:
    def test_low_roll_hostile(self):
        r = social.reaction_roll(0, reaction_dice=(2, 3))  # total 5
        assert r.total == 5
        assert r.attitude == "hostile"

    def test_high_roll_helpful(self):
        r = social.reaction_roll(4, reaction_dice=(6, 6))  # 12 + 4 = 16
        assert r.total == 16
        assert r.attitude == "helpful"

    def test_midband_indifferent(self):
        # 9-12 inclusive is indifferent
        r = social.reaction_roll(0, reaction_dice=(5, 5))  # 10
        assert r.attitude == "indifferent"
        r2 = social.reaction_roll(0, reaction_dice=(4, 5))  # 9
        assert r2.attitude == "indifferent"

    def test_unfriendly_band(self):
        r = social.reaction_roll(0, reaction_dice=(3, 4))  # 7
        assert r.attitude == "unfriendly"

    def test_friendly_band(self):
        r = social.reaction_roll(2, reaction_dice=(6, 5))  # 11 + 2 = 13
        assert r.attitude == "friendly"

    def test_charisma_modifier_applies(self):
        r = social.reaction_roll(3, reaction_dice=(4, 4))  # 8 + 3 = 11
        assert r.total == 11
        assert r.modifier == 3

    def test_rolls_stored(self):
        r = social.reaction_roll(0, reaction_dice=(2, 5))
        assert r.rolls == [2, 5]

    def test_random_roll_works(self):
        r = social.reaction_roll(0)
        assert 2 <= r.total <= 12
        assert r.attitude in social.ATTITUDE_LEVELS

    def test_to_dict(self):
        r = social.reaction_roll(1, reaction_dice=(3, 3))
        d = r.to_dict()
        assert d["total"] == 7
        assert d["rolls"] == [3, 3]
        assert "attitude" in d


# --------------------------------------------------------------------------- #
# Influence check
# --------------------------------------------------------------------------- #

class TestInfluenceCheck:
    def test_hostile_dc20_success_improves(self):
        res = social.influence_check(
            skill="persuasion", skill_modifier=5,
            current_attitude="hostile", roll=15,  # 15+5=20 >= 20
        )
        assert res.dc == 20
        assert res.success is True
        assert res.new_attitude == "unfriendly"
        assert res.worsened is False
        assert res.trust_delta == social.ATTITUDE_STEP_TRUST_DELTA

    def test_hostile_dc20_failure_holds(self):
        res = social.influence_check(
            skill="persuasion", skill_modifier=2,
            current_attitude="hostile", roll=10,  # 12 < 20, fail by 8 >= 5
        )
        # fail by 8 → worsens
        assert res.success is False
        assert res.worsened is True
        assert res.new_attitude == "hostile"  # can't go below hostile

    def test_failure_by_less_than_margin_holds_attitude(self):
        # DC 20, total 17 (roll 14 + 3) → fail by 3 < 5 → holds
        res = social.influence_check(
            skill="persuasion", skill_modifier=3,
            current_attitude="hostile", roll=14,
        )
        assert res.success is False
        assert res.worsened is False
        assert res.new_attitude == "hostile"

    def test_indifferent_dc15(self):
        res = social.influence_check(
            skill="persuasion", skill_modifier=5,
            current_attitude="indifferent", roll=10,  # 15 >= 15
        )
        assert res.dc == 15
        assert res.success is True
        assert res.new_attitude == "friendly"

    def test_friendly_dc10(self):
        res = social.influence_check(
            skill="persuasion", skill_modifier=0,
            current_attitude="friendly", roll=10,  # 10 >= 10
        )
        assert res.dc == 10
        assert res.success is True
        assert res.new_attitude == "helpful"

    def test_helpful_auto_success_no_check(self):
        res = social.influence_check(
            skill="persuasion", skill_modifier=0,
            current_attitude="helpful", roll=1,
        )
        assert res.auto_success is True
        assert res.success is True
        assert res.new_attitude == "helpful"
        assert res.trust_delta == 0

    def test_nat1_worsens_even_when_margin_disabled(self):
        # RAW: a natural 1 does NOT auto-fail an ability check, but the DM
        # worsen option treats nat 1 as a guaranteed worsen — *independent* of
        # the fail-margin threshold. Here the roll (1 < DC 10) fails outright,
        # and nat1 forces the worsen even though fail_margin disables it.
        res = social.influence_check(
            skill="persuasion", skill_modifier=0,
            current_attitude="friendly", roll=1,
            fail_margin_for_worsen=99,
        )
        assert res.success is False
        assert res.worsened is True
        assert res.new_attitude == "indifferent"

    def test_nat1_success_does_not_worsen(self):
        # RAW: nat 1 on an ability check is not an auto-fail. A high enough
        # modifier still succeeds and does not worsen the attitude.
        res = social.influence_check(
            skill="persuasion", skill_modifier=20,
            current_attitude="friendly", roll=1,  # 1+20=21 >= DC 10 → success
        )
        assert res.success is True
        assert res.worsened is False
        assert res.new_attitude == "helpful"

    def test_nat1_at_hostile_clamps(self):
        res = social.influence_check(
            skill="intimidation", skill_modifier=0,
            current_attitude="hostile", roll=1,
        )
        assert res.worsened is True
        assert res.new_attitude == "hostile"  # floor

    def test_disable_worsen_with_large_margin(self):
        # Use a non-nat1 roll so the fail-margin rule (not nat1) controls it.
        res = social.influence_check(
            skill="persuasion", skill_modifier=0,
            current_attitude="indifferent", roll=2,  # 2 < 15 → fail by 13
            fail_margin_for_worsen=99,
        )
        assert res.worsened is False
        assert res.new_attitude == "indifferent"

    def test_charmed_condition_grants_advantage(self):
        # With advantage, a non-forced roll can't be tested deterministically;
        # use a forced roll + assert the advantage flag is set.
        res = social.influence_check(
            skill="persuasion", skill_modifier=5,
            current_attitude="indifferent", roll=10,
            conditions=["charmed"],
        )
        assert res.advantage is True
        assert res.disadvantage is False

    def test_frightened_condition_imposes_disadvantage(self):
        res = social.influence_check(
            skill="persuasion", skill_modifier=5,
            current_attitude="indifferent", roll=10,
            conditions=["frightened"],
        )
        assert res.disadvantage is True

    def test_forced_advantage_override(self):
        res = social.influence_check(
            skill="intimidation", skill_modifier=5,
            current_attitude="indifferent", roll=10,
            forced_advantage=True,
        )
        assert res.advantage is True

    def test_intimidation_skill_recorded(self):
        res = social.influence_check(
            skill="intimidation", skill_modifier=5,
            current_attitude="unfriendly", roll=10,  # 15 >= 15
        )
        assert res.skill == "intimidation"
        assert res.success is True
        assert res.new_attitude == "indifferent"

    def test_to_dict(self):
        res = social.influence_check(
            skill="persuasion", skill_modifier=3,
            current_attitude="friendly", roll=10,
        )
        d = res.to_dict()
        assert d["dc"] == 10
        assert d["total"] == 13
        assert d["success"] is True


# --------------------------------------------------------------------------- #
# Insight check
# --------------------------------------------------------------------------- #

class TestInsightCheck:
    def test_active_contest_detect(self):
        res = social.insight_check(
            insight_modifier=5, npc_deception_total=15,
            insight_roll=11,  # 11+5=16 >= 15
        )
        assert res.contested is True
        assert res.detected is True
        assert res.insight_total == 16
        assert res.deception_total == 15

    def test_active_contest_miss(self):
        res = social.insight_check(
            insight_modifier=2, npc_deception_total=18,
            insight_roll=10,  # 12 < 18
        )
        assert res.detected is False

    def test_passive_deception(self):
        res = social.insight_check(
            insight_modifier=5, npc_passive_deception=14,
            insight_roll=9,  # 14 >= 14
        )
        assert res.contested is False
        assert res.detected is True

    def test_passive_deception_miss(self):
        res = social.insight_check(
            insight_modifier=2, npc_passive_deception=15,
            insight_roll=10,  # 12 < 15
        )
        assert res.detected is False

    def test_requires_a_deception_value(self):
        with pytest.raises(ValueError):
            social.insight_check(insight_modifier=5)

    def test_random_roll(self):
        res = social.insight_check(
            insight_modifier=0, npc_passive_deception=10,
        )
        assert res.insight_roll is not None
        assert 1 <= res.insight_roll <= 20

    def test_to_dict(self):
        res = social.insight_check(
            insight_modifier=3, npc_deception_total=12,
            insight_roll=10,
        )
        d = res.to_dict()
        assert d["insight_total"] == 13
        assert d["contested"] is True


# --------------------------------------------------------------------------- #
# DM summary helper
# --------------------------------------------------------------------------- #

class TestSummary:
    def test_summary_with_improve_dc(self):
        s = social.npc_interaction_summary("Captain Aldric", "unfriendly", trust=-40)
        assert "Captain Aldric" in s
        assert "unfriendly" in s
        assert "DC 15" in s
        assert "indifferent" in s

    def test_summary_helpful_no_dc(self):
        s = social.npc_interaction_summary("Mira", "helpful")
        assert "cooperative" in s
        assert "helpful" in s

    def test_summary_alias_attitude(self):
        s = social.npc_interaction_summary("Guard", "neutral")
        assert "indifferent" in s  # neutral → indifferent
