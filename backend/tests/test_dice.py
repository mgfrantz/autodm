"""
Tests for the dice rolling engine.

Covers d20 system mechanics: rolls, advantage/disadvantage, ability modifiers, proficiency.
"""
import pytest

from app.engine.dice import (
    roll_die,
    roll_dice,
    roll_d20,
    RollResult,
    ability_modifier,
    proficiency_bonus,
)


class TestRollDie:
    """Test basic single die rolls."""

    def test_roll_die_d20_range(self):
        """Test that d20 rolls are in valid range."""
        for _ in range(100):
            result = roll_die(20)
            assert 1 <= result <= 20

    def test_roll_die_d6_range(self):
        """Test that d6 rolls are in valid range."""
        for _ in range(100):
            result = roll_die(6)
            assert 1 <= result <= 6

    def test_roll_die_custom_sides(self):
        """Test custom die sides."""
        for sides in [4, 8, 10, 12, 100]:
            result = roll_die(sides)
            assert 1 <= result <= sides


class TestRollDice:
    """Test multi-die rolls with modifiers."""

    def test_roll_dice_2d6_range(self):
        """Test 2d6 roll produces valid range."""
        result = roll_dice(2, 6)
        assert 2 <= result.total <= 12
        assert len(result.rolls) == 2
        assert result.modifier == 0
        assert result.description == "2d6+0"

    def test_roll_dice_with_modifier(self):
        """Test dice rolls with modifiers."""
        result = roll_dice(2, 6, 5)
        assert 7 <= result.total <= 17  # 2-12 + 5
        assert result.modifier == 5
        assert result.description == "2d6+5"

    def test_roll_dice_negative_modifier(self):
        """Test dice rolls with negative modifiers."""
        result = roll_dice(3, 4, -2)
        assert 1 <= result.total <= 10  # 3-12 - 2
        assert result.modifier == -2
        assert result.description == "3d4-2"

    def test_roll_dice_str_representation(self):
        """Test RollResult string representation."""
        result = roll_dice(2, 6, 3)
        str_repr = str(result)
        # Format: "X + Y + ... = TOTAL"
        assert "=" in str_repr
        assert str(result.total) in str_repr

    def test_roll_dice_total_calculation(self):
        """Verify total calculation is correct."""
        # Mock with known values by testing calculation directly
        from unittest.mock import patch

        with patch('app.engine.dice.roll_die', return_value=5):
            result = roll_dice(3, 6, 2)
            assert result.rolls == [5, 5, 5]
            assert result.total == 17  # 5+5+5+2


class TestRollD20:
    """Test d20 rolls with advantage/disadvantage."""

    def test_roll_d20_basic_range(self):
        """Test basic d20 roll range."""
        result = roll_d20()
        assert 1 <= result.total <= 20
        assert len(result.rolls) == 1
        assert result.description.startswith("d20")

    def test_roll_d20_with_modifier(self):
        """Test d20 roll with modifier."""
        result = roll_d20(modifier=5)
        assert 6 <= result.total <= 25  # 1-20 + 5
        assert result.modifier == 5

    def test_roll_d20_advantage_takes_max(self):
        """Test advantage takes the higher of two rolls."""
        from unittest.mock import patch

        # Advantage should take max of two rolls
        with patch('app.engine.dice.roll_die') as mock_roll:
            mock_roll.side_effect = [5, 15]  # First roll 5, second 15
            result = roll_d20(advantage=True)
            assert result.rolls == [5, 15]
            assert result.total == 15  # Max of 5, 15
            assert "advantage" in result.description

    def test_roll_d20_advantage_with_modifier(self):
        """Test advantage with modifier."""
        from unittest.mock import patch

        with patch('app.engine.dice.roll_die') as mock_roll:
            mock_roll.side_effect = [3, 18]
            result = roll_d20(advantage=True, modifier=4)
            assert result.rolls == [3, 18]
            assert result.total == 22  # Max(3,18) + 4

    def test_roll_d20_disadvantage_takes_min(self):
        """Test disadvantage takes the lower of two rolls."""
        from unittest.mock import patch

        with patch('app.engine.dice.roll_die') as mock_roll:
            mock_roll.side_effect = [5, 15]  # First roll 5, second 15
            result = roll_d20(disadvantage=True)
            assert result.rolls == [5, 15]
            assert result.total == 5  # Min of 5, 15
            assert "disadvantage" in result.description

    def test_roll_d20_disadvantage_with_modifier(self):
        """Test disadvantage with modifier."""
        from unittest.mock import patch

        with patch('app.engine.dice.roll_die') as mock_roll:
            mock_roll.side_effect = [7, 19]
            result = roll_d20(disadvantage=True, modifier=3)
            assert result.rolls == [7, 19]
            assert result.total == 10  # Min(7,19) + 3

    def test_roll_d20_both_advantage_and_disadvantage(self):
        """Test that advantage + disadvantage cancel out."""
        from unittest.mock import patch

        with patch('app.engine.dice.roll_die') as mock_roll:
            mock_roll.side_effect = [10]  # Should only roll once
            result = roll_d20(advantage=True, disadvantage=True)
            assert result.rolls == [10]  # Single roll, not two
            assert "advantage" not in result.description
            assert "disadvantage" not in result.description

    def test_roll_d20_description_format(self):
        """Test d20 roll description formatting."""
        result_pos = roll_d20(modifier=5)
        assert "+5" in result_pos.description

        result_neg = roll_d20(modifier=-2)
        assert "-2" in result_neg.description

        result_zero = roll_d20(modifier=0)
        assert "+0" in result_zero.description


class TestAbilityModifier:
    """Test DnD 5e ability modifier calculation."""

    def test_ability_modifier_ten(self):
        """Test score 10 has +0 modifier."""
        assert ability_modifier(10) == 0

    def test_ability_modifier_eleven(self):
        """Test score 11 has +0 modifier."""
        assert ability_modifier(11) == 0

    def test_ability_modifier_one(self):
        """Test minimum score 1 has -5 modifier."""
        assert ability_modifier(1) == -5

    def test_ability_modifier_twenty(self):
        """Test score 20 has +5 modifier."""
        assert ability_modifier(20) == 5

    def test_ability_modifier_thirty(self):
        """Test score 30 has +10 modifier."""
        assert ability_modifier(30) == 10

    def test_ability_modifier_values(self):
        """Test various ability score modifiers."""
        # Odd and even scores should give same modifier
        assert ability_modifier(12) == 1
        assert ability_modifier(13) == 1

        assert ability_modifier(14) == 2
        assert ability_modifier(15) == 2

        assert ability_modifier(16) == 3
        assert ability_modifier(17) == 3

        assert ability_modifier(18) == 4
        assert ability_modifier(19) == 4

        # Low scores
        assert ability_modifier(8) == -1
        assert ability_modifier(6) == -2
        assert ability_modifier(4) == -3


class TestProficiencyBonus:
    """Test proficiency bonus by level."""

    def test_proficiency_bonus_level_1(self):
        """Test level 1 has +2 proficiency."""
        assert proficiency_bonus(1) == 2

    def test_proficiency_bonus_level_4(self):
        """Test level 4 still has +2 proficiency."""
        assert proficiency_bonus(4) == 2

    def test_proficiency_bonus_level_5(self):
        """Test level 5 has +3 proficiency."""
        assert proficiency_bonus(5) == 3

    def test_proficiency_bonus_level_8(self):
        """Test level 8 still has +3 proficiency."""
        assert proficiency_bonus(8) == 3

    def test_proficiency_bonus_level_9(self):
        """Test level 9 has +4 proficiency."""
        assert proficiency_bonus(9) == 4

    def test_proficiency_bonus_level_13(self):
        """Test level 13 has +5 proficiency."""
        assert proficiency_bonus(13) == 5

    def test_proficiency_bonus_level_17(self):
        """Test level 17 has +6 proficiency."""
        assert proficiency_bonus(17) == 6

    def test_proficiency_bonus_level_20(self):
        """Test level 20 has +6 proficiency (max)."""
        assert proficiency_bonus(20) == 6

    def test_proficiency_bonus_progression(self):
        """Test that proficiency bonus increases every 4 levels."""
        # 1-4: +2
        for lvl in [1, 2, 3, 4]:
            assert proficiency_bonus(lvl) == 2
        # 5-8: +3
        for lvl in [5, 6, 7, 8]:
            assert proficiency_bonus(lvl) == 3
        # 9-12: +4
        for lvl in [9, 10, 11, 12]:
            assert proficiency_bonus(lvl) == 4
        # 13-16: +5
        for lvl in [13, 14, 15, 16]:
            assert proficiency_bonus(lvl) == 5
        # 17-20: +6
        for lvl in [17, 18, 19, 20]:
            assert proficiency_bonus(lvl) == 6


class TestRollResult:
    """Test RollResult dataclass."""

    def test_roll_result_creation(self):
        """Test RollResult can be created and accessed."""
        result = RollResult(
            rolls=[3, 5],
            modifier=2,
            total=10,
            description="2d6+2"
        )
        assert result.rolls == [3, 5]
        assert result.modifier == 2
        assert result.total == 10
        assert result.description == "2d6+2"

    def test_roll_result_str_with_modifier(self):
        """Test RollResult string with positive modifier."""
        result = RollResult(rolls=[3, 4], modifier=2, total=9, description="2d6+2")
        str_repr = str(result)
        assert "3 + 4" in str_repr or "4 + 3" in str_repr
        assert "+2" in str_repr  # Modifier is concatenated without space
        assert "= 9" in str_repr

    def test_roll_result_str_no_modifier(self):
        """Test RollResult string without modifier."""
        result = RollResult(rolls=[5, 6], modifier=0, total=11, description="2d6")
        str_repr = str(result)
        assert "5 + 6" in str_repr or "6 + 5" in str_repr
        assert "= 11" in str_repr
        # No modifier sign should appear when modifier is 0
        assert "+ 0" not in str_repr

    def test_roll_result_str_negative_modifier(self):
        """Test RollResult string with negative modifier."""
        result = RollResult(rolls=[2, 3], modifier=-1, total=4, description="2d6-1")
        str_repr = str(result)
        assert "2 + 3" in str_repr or "3 + 2" in str_repr
        assert "-1" in str_repr  # Negative modifier shows with sign
        assert "= 4" in str_repr