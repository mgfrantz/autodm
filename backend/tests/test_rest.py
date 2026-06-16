"""
Tests for the rest engine (short & long rests).

The engine is pure, so these are plain unit tests with deterministic rolls.
"""
from app.engine import rest as rest_engine
from app.engine.rest import (
    DieRoll,
    ShortRestResult,
    LongRestResult,
    LONG_REST_CLEARABLE_CONDITIONS,
    available_hit_dice,
    hit_die_size,
    is_clearable_by_long_rest,
    long_rest,
    long_rest_hit_dice_recovered,
    short_rest,
    total_hit_dice,
)


# --------------------------------------------------------------------------- #
# Hit-Dice pool helpers
# --------------------------------------------------------------------------- #

class TestHitDiceHelpers:
    def test_total_hit_dice_equals_level(self):
        assert total_hit_dice(1) == 1
        assert total_hit_dice(5) == 5
        assert total_hit_dice(20) == 20

    def test_total_hit_dice_min_one(self):
        assert total_hit_dice(0) == 1
        assert total_hit_dice(-3) == 1

    def test_available_hit_dice(self):
        # level 5, none used -> 5 available
        assert available_hit_dice(5, 0) == 5
        # level 5, 3 used -> 2 available
        assert available_hit_dice(5, 3) == 2
        # level 5, all used -> 0
        assert available_hit_dice(5, 5) == 0

    def test_available_hit_dice_clamps_negative_used(self):
        assert available_hit_dice(4, -2) == 4
        # used exceeds level -> 0 (not negative)
        assert available_hit_dice(3, 10) == 0

    def test_long_rest_recovers_half_min_one(self):
        # level 1 -> half = 0 -> min 1
        assert long_rest_hit_dice_recovered(1) == 1
        # level 4 -> 2
        assert long_rest_hit_dice_recovered(4) == 2
        # level 5 -> 2 (floor)
        assert long_rest_hit_dice_recovered(5) == 2
        # level 20 -> 10
        assert long_rest_hit_dice_recovered(20) == 10

    def test_hit_die_size_per_class(self):
        assert hit_die_size("wizard") == 6
        assert hit_die_size("fighter") == 10
        assert hit_die_size("barbarian") == 12
        assert hit_die_size("rogue") == 8
        # unknown class defaults to d8
        assert hit_die_size("commoner") == 8


# --------------------------------------------------------------------------- #
# Condition clearability
# --------------------------------------------------------------------------- #

class TestConditionClearing:
    def test_poisoned_is_clearable(self):
        assert is_clearable_by_long_rest("poisoned") is True
        assert is_clearable_by_long_rest("frightened") is True
        assert is_clearable_by_long_rest("prone") is True

    def test_non_restable_conditions_not_cleared(self):
        # incapacitating / permanent conditions are not cleared by rest
        assert is_clearable_by_long_rest("paralyzed") is False
        assert is_clearable_by_long_rest("petrified") is False
        assert is_clearable_by_long_rest("stunned") is False
        assert is_clearable_by_long_rest("unconscious") is False

    def test_unknown_condition_not_clearable(self):
        assert is_clearable_by_long_rest("not_a_real_condition") is False

    def test_clearable_set_is_modifiable(self):
        original = set(LONG_REST_CLEARABLE_CONDITIONS)
        try:
            assert is_clearable_by_long_rest("blinded") is True
        finally:
            # restore in case a test mutated it
            LONG_REST_CLEARABLE_CONDITIONS.clear()
            LONG_REST_CLEARABLE_CONDITIONS.update(original)


# --------------------------------------------------------------------------- #
# Short rest
# --------------------------------------------------------------------------- #

class TestShortRest:
    def test_basic_heal_with_explicit_rolls(self):
        # Fighter level 5 (d10), 20/50 HP, CON +2, spend 2 dice rolling 8 and 6
        result = short_rest(
            char_class="fighter", level=5, current_hp=20, max_hp=50,
            hit_dice_used=0, con_mod=2, rolls=[8, 6],
        )
        assert result.success is True
        assert result.hit_dice_spent == 2
        # die 1: 8 + 2 = 10 ; die 2: 6 + 2 = 8 -> 18 healed -> hp 38
        assert result.hp_after == 38
        assert result.hp_healed == 18

    def test_stops_spending_when_full(self):
        # 25/30 HP, each die heals a lot -> only one die needed
        result = short_rest(
            char_class="barbarian", level=10, current_hp=25, max_hp=30,
            hit_dice_used=0, con_mod=3, rolls=[12, 12, 12, 12],
        )
        assert result.success is True
        # room = 5, die heal = 12+3 = 15 -> clamped to 5
        assert result.hp_healed == 5
        assert result.hp_after == 30
        assert result.hit_dice_spent == 1

    def test_spends_multiple_dice_until_healed(self):
        # 10/30 HP, small rolls (1 each), CON 0 -> each die heals 1
        result = short_rest(
            char_class="fighter", level=10, current_hp=10, max_hp=30,
            hit_dice_used=0, con_mod=0, rolls=[1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        )
        assert result.success is True
        # need 20 HP of healing, each die = 1 -> 20 dice, but level 10 = 10 dice available
        assert result.hit_dice_spent == 10
        assert result.hp_healed == 10
        assert result.hp_after == 20
        assert result.hit_dice_available_after == 0

    def test_explicit_num_dice(self):
        # Spend exactly 2 dice even though more rolls supplied and HP not full.
        # num_dice takes precedence over rolls for the count.
        result = short_rest(
            char_class="wizard", level=5, current_hp=5, max_hp=30,
            hit_dice_used=0, con_mod=0, num_dice=2, rolls=[6, 6, 6, 6, 6],
        )
        assert result.success is True
        assert result.hit_dice_spent == 2
        assert result.hp_healed == 12  # 6 + 6
        assert result.hp_after == 17

    def test_num_dice_capped_at_available(self):
        # Ask for 5 dice but only 3 available
        result = short_rest(
            char_class="fighter", level=3, current_hp=1, max_hp=100,
            hit_dice_used=0, con_mod=0, num_dice=5, rolls=[10, 10, 10, 10, 10],
        )
        assert result.success is True
        assert result.hit_dice_spent == 3
        assert result.hp_healed == 30

    def test_already_full_hp(self):
        result = short_rest(
            char_class="fighter", level=5, current_hp=30, max_hp=30,
            hit_dice_used=0, con_mod=2, rolls=[8],
        )
        assert result.success is False
        assert "full HP" in result.message
        assert result.hit_dice_spent == 0
        assert result.hp_after == 30

    def test_no_hit_dice_available(self):
        result = short_rest(
            char_class="fighter", level=5, current_hp=1, max_hp=30,
            hit_dice_used=5, con_mod=2, rolls=[8],
        )
        assert result.success is False
        assert "No Hit Dice" in result.message
        assert result.hit_dice_spent == 0
        assert result.hp_after == 1

    def test_die_minimum_one_heal(self):
        # CON -3, roll 1 -> 1 + (-3) = -2 -> clamped to min 1
        result = short_rest(
            char_class="wizard", level=3, current_hp=1, max_hp=30,
            hit_dice_used=0, con_mod=-3, rolls=[1, 1],
        )
        assert result.success is True
        assert all(r.total == 1 for r in result.rolls)
        assert result.hp_healed == 2

    def test_con_mod_applied(self):
        # CON +4, roll 5 on d8 -> 9 heal
        result = short_rest(
            char_class="rogue", level=4, current_hp=1, max_hp=30,
            hit_dice_used=0, con_mod=4, rolls=[5],
        )
        assert result.success is True
        assert result.rolls[0].modifier == 4
        assert result.rolls[0].total == 9

    def test_rolls_have_correct_faces(self):
        result = short_rest(
            char_class="barbarian", level=5, current_hp=1, max_hp=100,
            hit_dice_used=0, con_mod=0, rolls=[7],
        )
        assert result.rolls[0].faces == 12  # barbarian d12

    def test_default_spend_until_full_or_exhausted(self):
        # No num_dice -> spend until full or pool exhausted
        result = short_rest(
            char_class="fighter", level=5, current_hp=1, max_hp=100,
            hit_dice_used=0, con_mod=0, rolls=[10, 10, 10, 10, 10],
        )
        assert result.success is True
        # 5 dice available, none bring us near full -> spend all 5
        assert result.hit_dice_spent == 5
        assert result.hp_healed == 50
        assert result.hit_dice_available_after == 0

    def test_to_dict_serialization(self):
        result = short_rest(
            char_class="fighter", level=5, current_hp=20, max_hp=30,
            hit_dice_used=0, con_mod=2, rolls=[8],
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["hit_dice_spent"] == 1
        assert isinstance(d["rolls"], list)
        assert set(d["rolls"][0].keys()) == {"faces", "roll", "modifier", "total"}
        assert d["hp_after"] == 30

    def test_zero_requested_dice(self):
        # Explicitly request 0 dice
        result = short_rest(
            char_class="fighter", level=5, current_hp=20, max_hp=30,
            hit_dice_used=0, con_mod=2, num_dice=0,
        )
        assert result.success is False
        assert result.hit_dice_spent == 0


# --------------------------------------------------------------------------- #
# Long rest
# --------------------------------------------------------------------------- #

class TestLongRest:
    def test_restores_full_hp(self):
        result = long_rest(
            char_class="fighter", level=5, current_hp=7, max_hp=40,
            hit_dice_used=4, is_caster=False,
        )
        assert result.success is True
        assert result.hp_after == 40
        assert result.hp_healed == 33

    def test_recovers_hit_dice_half_total(self):
        # level 10 -> recover 5; had used 7 -> regain 5, used_after = 2
        result = long_rest(
            char_class="fighter", level=10, current_hp=1, max_hp=100,
            hit_dice_used=7, is_caster=False,
        )
        assert result.hit_dice_recovered == 5
        assert result.hit_dice_used_after == 2
        assert result.hit_dice_available_after == 8  # 10 - 2

    def test_recovery_capped_by_spent(self):
        # level 10 -> would recover 5, but only 2 were used -> regain 2
        result = long_rest(
            char_class="fighter", level=10, current_hp=1, max_hp=100,
            hit_dice_used=2, is_caster=False,
        )
        assert result.hit_dice_recovered == 2
        assert result.hit_dice_used_after == 0
        assert result.hit_dice_available_after == 10

    def test_minimum_one_die_recovered(self):
        # level 1 -> half = 0 -> min 1, but 0 used -> regain 0 (can't exceed total)
        result = long_rest(
            char_class="fighter", level=1, current_hp=1, max_hp=10,
            hit_dice_used=0, is_caster=False,
        )
        assert result.hit_dice_recovered == 0  # nothing was spent
        assert result.hit_dice_used_after == 0

    def test_level_one_with_spent_die_recovers_it(self):
        # level 1, used 1 die -> min-recovery 1 regains it
        result = long_rest(
            char_class="fighter", level=1, current_hp=1, max_hp=10,
            hit_dice_used=1, is_caster=False,
        )
        assert result.hit_dice_recovered == 1
        assert result.hit_dice_used_after == 0

    def test_caster_recovers_slots(self):
        result = long_rest(
            char_class="wizard", level=5, current_hp=1, max_hp=30,
            hit_dice_used=2, is_caster=True,
        )
        assert result.slots_recovered is True

    def test_non_caster_no_slots(self):
        result = long_rest(
            char_class="fighter", level=5, current_hp=1, max_hp=30,
            hit_dice_used=2, is_caster=False,
        )
        assert result.slots_recovered is False

    def test_clears_restable_conditions(self):
        result = long_rest(
            char_class="fighter", level=5, current_hp=1, max_hp=30,
            hit_dice_used=2, is_caster=False,
            conditions=["poisoned", "frightened", "paralyzed"],
        )
        assert "poisoned" in result.conditions_cleared
        assert "frightened" in result.conditions_cleared
        # paralyzed is NOT cleared by rest
        assert "paralyzed" not in result.conditions_cleared

    def test_no_conditions_input(self):
        result = long_rest(
            char_class="fighter", level=5, current_hp=1, max_hp=30,
            hit_dice_used=2, is_caster=False, conditions=None,
        )
        assert result.conditions_cleared == []

    def test_full_hp_no_waste(self):
        # Already at full — still recovers dice and slots, heals 0
        result = long_rest(
            char_class="wizard", level=5, current_hp=30, max_hp=30,
            hit_dice_used=3, is_caster=True,
        )
        assert result.hp_healed == 0
        assert result.hp_after == 30
        assert result.slots_recovered is True
        assert result.hit_dice_recovered == 2  # min(2, 3)

    def test_to_dict_serialization(self):
        result = long_rest(
            char_class="wizard", level=5, current_hp=5, max_hp=30,
            hit_dice_used=3, is_caster=True, conditions=["poisoned"],
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["hp_after"] == 30
        assert d["slots_recovered"] is True
        assert d["conditions_cleared"] == ["poisoned"]
        assert "message" in d

    def test_message_describes_recovery(self):
        result = long_rest(
            char_class="wizard", level=5, current_hp=5, max_hp=30,
            hit_dice_used=3, is_caster=True, conditions=["poisoned"],
        )
        assert "recovered" in result.message.lower()
        assert "spell slots" in result.message.lower()
        assert "poisoned" in result.message.lower()
