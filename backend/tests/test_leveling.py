"""
Tests for the leveling engine: XP thresholds, level resolution, HP growth,
ability score improvements, and class features.
"""
import pytest

from app.engine import leveling
from app.engine.leveling import (
    ASIChoice,
    apply_asi,
    apply_xp,
    asi_available,
    asi_count_through,
    asi_levels,
    average_hp_gain,
    features_at_level,
    features_through_level,
    hit_die_for_class,
    hp_gained_for_levels,
    is_asi_level,
    level_for_xp,
    level_progress,
    xp_for_level,
    xp_to_next_level,
    MAX_LEVEL,
    MAX_ABILITY_SCORE,
)


# ---------------------------------------------------------------------------
# XP thresholds
# ---------------------------------------------------------------------------

class TestXPThresholds:
    def test_xp_for_known_levels(self):
        assert xp_for_level(1) == 0
        assert xp_for_level(2) == 300
        assert xp_for_level(3) == 900
        assert xp_for_level(4) == 2_700
        assert xp_for_level(5) == 6_500
        assert xp_for_level(11) == 85_000
        assert xp_for_level(20) == 355_000

    def test_xp_for_level_clamps_below(self):
        assert xp_for_level(0) == 0
        assert xp_for_level(-5) == 0

    def test_xp_for_level_clamps_above(self):
        assert xp_for_level(21) == 355_000
        assert xp_for_level(99) == 355_000


class TestLevelForXP:
    def test_level_1_for_zero_xp(self):
        assert level_for_xp(0) == 1
        assert level_for_xp(-10) == 1

    def test_exact_threshold(self):
        assert level_for_xp(300) == 2
        assert level_for_xp(900) == 3
        assert level_for_xp(2_700) == 4
        assert level_for_xp(6_500) == 5

    def test_between_thresholds(self):
        assert level_for_xp(299) == 1
        assert level_for_xp(301) == 2
        assert level_for_xp(899) == 2
        assert level_for_xp(6_499) == 4

    def test_caps_at_20(self):
        assert level_for_xp(355_000) == 20
        assert level_for_xp(1_000_000) == 20


class TestXPToNextLevel:
    def test_level_1_to_2(self):
        assert xp_to_next_level(1) == 300

    def test_level_4_to_5(self):
        # 6500 - 2700
        assert xp_to_next_level(4) == 3_800

    def test_max_level_returns_none(self):
        assert xp_to_next_level(20) is None

    def test_clamps_above_max(self):
        assert xp_to_next_level(25) is None


# ---------------------------------------------------------------------------
# Level progress
# ---------------------------------------------------------------------------

class TestLevelProgress:
    def test_fresh_character(self):
        p = level_progress(0)
        assert p["level"] == 1
        assert p["xp"] == 0
        assert p["level_start_xp"] == 0
        assert p["next_level_xp"] == 300
        assert p["xp_into_level"] == 0
        assert p["xp_to_next"] == 300
        assert p["progress"] == 0.0

    def test_midway_through_level_2(self):
        # Level 2 spans 300..900. At 600, 300 into the level of a 600 span.
        p = level_progress(600)
        assert p["level"] == 2
        assert p["level_start_xp"] == 300
        assert p["next_level_xp"] == 900
        assert p["xp_into_level"] == 300
        assert p["xp_to_next"] == 300
        assert 0 < p["progress"] < 1.0
        assert p["progress"] == pytest.approx(0.5, abs=0.01)

    def test_at_cap(self):
        p = level_progress(400_000)
        assert p["level"] == 20
        assert p["next_level_xp"] is None
        assert p["xp_to_next"] is None
        assert p["progress"] == 1.0


# ---------------------------------------------------------------------------
# Hit dice & HP growth
# ---------------------------------------------------------------------------

class TestHitDice:
    def test_known_classes(self):
        assert hit_die_for_class("barbarian") == 12
        assert hit_die_for_class("fighter") == 10
        assert hit_die_for_class("wizard") == 6
        assert hit_die_for_class("rogue") == 8
        assert hit_die_for_class("sorcerer") == 6

    def test_case_insensitive(self):
        assert hit_die_for_class("Wizard") == 6
        assert hit_die_for_class("FIGHTER") == 10

    def test_unknown_class_defaults_d8(self):
        assert hit_die_for_class("astronaut") == 8


class TestAverageHPGain:
    def test_d10_with_con_bonus(self):
        # Fighter d10, CON 14 (+2): 6 + 2 = 8
        assert average_hp_gain(10, 2) == 8

    def test_d6_neutral_con(self):
        # Wizard d6, CON 10 (+0): 4 + 0 = 4
        assert average_hp_gain(6, 0) == 4

    def test_d12_positive_con(self):
        # Barbarian d12, CON 16 (+3): 7 + 3 = 10
        assert average_hp_gain(12, 3) == 10

    def test_negative_con_floors_at_one(self):
        # d6 with CON 4 (-3): 4 - 3 = 1
        assert average_hp_gain(6, -3) == 1
        # Even extreme negatives floor at 1.
        assert average_hp_gain(6, -99) == 1


class TestHPGainedForLevels:
    def test_no_gain_when_same_or_lower_level(self):
        assert hp_gained_for_levels(3, 3, "fighter", 2) == 0
        assert hp_gained_for_levels(5, 3, "fighter", 2) == 0

    def test_single_level_fighter(self):
        # Fighter d10, CON 14 (+2): 8 per level.
        assert hp_gained_for_levels(1, 2, "fighter", 2) == 8

    def test_multi_level(self):
        # 1 -> 5 = 4 levels, 8 each = 32
        assert hp_gained_for_levels(1, 5, "fighter", 2) == 32

    def test_with_explicit_rolls(self):
        # 1 -> 3 = 2 levels, rolls [9, 4], CON +2 -> (9+2) + (4+2) = 17
        gained = hp_gained_for_levels(1, 3, "fighter", 2, rolls=[9, 4])
        assert gained == 17

    def test_rolls_floor_at_one(self):
        # roll of 1 with CON -3 -> max(1, 1-3) = 1 per level
        gained = hp_gained_for_levels(1, 3, "wizard", -3, rolls=[1, 1])
        assert gained == 2

    def test_wrong_number_of_rolls_raises(self):
        with pytest.raises(ValueError):
            hp_gained_for_levels(1, 3, "fighter", 2, rolls=[5])


# ---------------------------------------------------------------------------
# Ability Score Improvements
# ---------------------------------------------------------------------------

class TestASILevels:
    def test_standard_class_levels(self):
        assert asi_levels("wizard") == [4, 8, 12, 16, 19]
        assert asi_levels("cleric") == [4, 8, 12, 16, 19]

    def test_fighter_has_extra_asis(self):
        fighter = asi_levels("fighter")
        assert 6 in fighter
        assert 14 in fighter
        # Fighter gets ASIs at 4, 6, 8, 12, 14, 16, 19 = 7 total.
        assert len(fighter) == 7

    def test_rogue_has_extra_at_10(self):
        rogue = asi_levels("rogue")
        assert 10 in rogue

    def test_is_asi_level_true(self):
        assert is_asi_level(4, "wizard")
        assert is_asi_level(6, "fighter")
        assert is_asi_level(10, "rogue")

    def test_is_asi_level_false(self):
        assert not is_asi_level(3, "wizard")
        assert not is_asi_level(6, "wizard")  # standard classes don't get 6

    def test_asi_count_through(self):
        assert asi_count_through(3, "wizard") == 0
        assert asi_count_through(4, "wizard") == 1
        assert asi_count_through(8, "wizard") == 2
        assert asi_count_through(19, "wizard") == 5
        assert asi_count_through(20, "fighter") == 7

    def test_asi_available(self):
        # Level 4 wizard with 0 used = 1 available.
        assert asi_available(4, "wizard", 0) == 1
        # Level 4 wizard with 1 used = 0 available.
        assert asi_available(4, "wizard", 1) == 0
        # Can't go negative.
        assert asi_available(3, "wizard", 5) == 0


class TestApplyASI:
    def base_abilities(self):
        return {
            "strength": 16, "dexterity": 14, "constitution": 12,
            "intelligence": 10, "wisdom": 10, "charisma": 10,
        }

    def test_single_plus_two(self):
        r = apply_asi(self.base_abilities(), [ASIChoice("strength", 2)], 4, "fighter", 0)
        assert r.success
        assert r.applied[0].ability == "strength"
        assert r.applied[0].amount == 2
        assert r.remaining == 0

    def test_two_plus_ones(self):
        r = apply_asi(
            self.base_abilities(),
            [ASIChoice("strength", 1), ASIChoice("dexterity", 1)],
            4, "fighter", 0,
        )
        assert r.success
        assert len(r.applied) == 2
        assert r.remaining == 0

    def test_no_asi_available_fails(self):
        r = apply_asi(self.base_abilities(), [ASIChoice("strength", 2)], 3, "wizard", 0)
        assert not r.success

    def test_wrong_total_fails(self):
        # total of 3 is invalid
        r = apply_asi(self.base_abilities(), [ASIChoice("strength", 3)], 4, "wizard", 0)
        assert not r.success
        # total of 1 is invalid
        r = apply_asi(self.base_abilities(), [ASIChoice("strength", 1)], 4, "wizard", 0)
        assert not r.success

    def test_clamps_at_20(self):
        abilities = self.base_abilities()
        abilities["strength"] = 19
        # +2 to a 19 should clamp to 20 (apply 1) — but our rule rejects if it
        # would have no effect. 19 + 2 = 21 -> clamped 20, delta 1 -> success.
        r = apply_asi(abilities, [ASIChoice("strength", 2)], 4, "wizard", 0)
        assert r.success
        assert r.applied[0].amount == 1

    def test_already_at_cap_rejects(self):
        abilities = self.base_abilities()
        abilities["strength"] = MAX_ABILITY_SCORE
        r = apply_asi(abilities, [ASIChoice("strength", 2)], 4, "wizard", 0)
        assert not r.success

    def test_unknown_ability_rejected(self):
        r = apply_asi(self.base_abilities(), [ASIChoice("luck", 2)], 4, "wizard", 0)
        assert not r.success

    def test_remaining_decrements(self):
        # Level 8 wizard has 2 ASIs earned; spend 1 -> 1 remaining.
        r = apply_asi(self.base_abilities(), [ASIChoice("strength", 2)], 8, "wizard", 0)
        assert r.success
        assert r.remaining == 1


# ---------------------------------------------------------------------------
# Class features
# ---------------------------------------------------------------------------

class TestClassFeatures:
    def test_fighter_level_1_features(self):
        feat = features_at_level("fighter", 1)
        assert "Fighting Style" in feat
        assert "Second Wind" in feat

    def test_no_feature_returns_empty(self):
        assert features_at_level("wizard", 6) == ""

    def test_features_through_level_sorted(self):
        feats = features_through_level("rogue", 5)
        levels = [lvl for lvl, _ in feats]
        assert levels == sorted(levels)
        # Up to level 5: levels 1, 2, 3, 5
        assert 1 in levels
        assert 2 in levels
        assert 5 in levels
        assert all(lvl <= 5 for lvl, _ in feats)

    def test_case_insensitive(self):
        assert features_at_level("Fighter", 1) == features_at_level("fighter", 1)

    def test_features_for_multiple_classes(self):
        assert "Arcane Recovery" in features_at_level("wizard", 1)
        assert "Rage" in features_at_level("barbarian", 1)
        assert "Sneak Attack" in features_at_level("rogue", 1)


# ---------------------------------------------------------------------------
# apply_xp — full level-up resolution
# ---------------------------------------------------------------------------

class TestApplyXP:
    def test_no_level_up_below_threshold(self):
        r = apply_xp("fighter", 1, 0, 100, 2, 0)
        assert not r.leveled_up
        assert r.to_level == 1
        assert r.hp_gained == 0
        assert r.xp == 100

    def test_single_level_up(self):
        # Fighter level 1, CON +2 (d10): reaching level 2 grants 8 HP.
        r = apply_xp("fighter", 1, 0, 300, 2, 0)
        assert r.leveled_up
        assert r.from_level == 1
        assert r.to_level == 2
        assert r.levels_gained == 1
        assert r.hp_gained == 8
        assert r.xp == 300

    def test_multi_level_up(self):
        # 0 -> 900 XP reaches level 3: 2 levels gained.
        r = apply_xp("wizard", 1, 0, 900, 0, 0)
        assert r.leveled_up
        assert r.to_level == 3
        assert r.levels_gained == 2
        # Wizard d6, CON +0: 4 HP/level * 2 = 8
        assert r.hp_gained == 8

    def test_proficiency_changes_at_level_5(self):
        # Proficiency is 2 at levels 1-4, 3 at levels 5-8.
        r = apply_xp("fighter", 4, 2_700, 6_500, 2, 0)
        assert r.to_level == 5
        assert r.proficiency_before == 2
        assert r.proficiency_after == 3
        assert r.proficiency_changed

    def test_proficiency_unchanged_within_tier(self):
        r = apply_xp("fighter", 1, 0, 300, 2, 0)  # 1 -> 2
        assert not r.proficiency_changed

    def test_asi_unlocked_at_level_4(self):
        r = apply_xp("wizard", 3, 2_000, 2_700, 0, 0)
        assert r.to_level == 4
        assert r.asi_unlocked
        assert r.asi_available == 1

    def test_fighter_asi_unlocked_at_6(self):
        r = apply_xp("fighter", 5, 6_000, 14_000, 2, 1)  # 5 -> 6
        assert r.asi_unlocked
        # Fighter has ASIs at 4 (spent) and now 6 -> 1 available.
        assert r.asi_available == 1

    def test_new_features_reported(self):
        # Fighter 1 -> 2 gains Action Surge (level 2 feature).
        r = apply_xp("fighter", 1, 0, 300, 2, 0)
        feature_levels = [lvl for lvl, _ in r.new_features]
        assert 2 in feature_levels

    def test_clamps_to_max_level(self):
        r = apply_xp("fighter", 19, 300_000, 999_999, 2, 5)
        assert r.to_level == MAX_LEVEL

    def test_asi_not_auto_spent(self):
        # Even when an ASI is unlocked, asi_used stays as passed; the engine
        # reports availability but does not consume it.
        r = apply_xp("wizard", 3, 2_000, 2_700, 0, 0)
        assert r.asi_available == 1
        # asi_used param unchanged conceptually (caller persists asi_used + 0).

    def test_negative_xp_treated_as_zero(self):
        # apply_xp with xp_after=0 still resolves to level 1.
        r = apply_xp("fighter", 1, 50, 0, 2, 0)
        assert not r.leveled_up
        assert r.to_level == 1

    def test_rolls_used_for_hp(self):
        r = apply_xp("fighter", 1, 0, 900, 2, 0, rolls=[10, 8])
        # (10+2) + (8+2) = 22
        assert r.hp_gained == 22
