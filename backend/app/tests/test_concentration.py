"""
Tests for the concentration engine.
"""
import pytest

from app.engine.concentration import (
    ConcentrationState,
    ConcentrationCheckResult,
    calculate_concentration_dc,
    check_concentration,
    start_concentration,
    end_concentration,
    can_concentrate,
    should_break_concentration,
)


def test_concentration_state_serialization():
    """Test that ConcentrationState can be serialized and deserialized."""
    state = ConcentrationState(
        spell_name="Bless",
        spell_id="bless",
        is_concentrating=True,
    )
    data = state.to_dict()
    restored = ConcentrationState.from_dict(data)
    assert restored.spell_name == "Bless"
    assert restored.spell_id == "bless"
    assert restored.is_concentrating is True


def test_concentration_state_defaults():
    """Test default ConcentrationState values."""
    state = ConcentrationState()
    assert state.spell_name == ""
    assert state.spell_id == ""
    assert state.is_concentrating is False


def test_calculate_concentration_dc():
    """Test DC calculation for concentration checks."""
    # DC = 10 or half damage (rounded down), whichever is higher
    assert calculate_concentration_dc(0) == 10
    assert calculate_concentration_dc(1) == 10
    assert calculate_concentration_dc(19) == 10
    assert calculate_concentration_dc(20) == 10
    assert calculate_concentration_dc(21) == 10  # 21//2 = 10, max(10, 10) = 10
    assert calculate_concentration_dc(40) == 20  # 40//2 = 20
    assert calculate_concentration_dc(41) == 20  # 41//2 = 20, max(10, 20) = 20
    assert calculate_concentration_dc(100) == 50


def test_check_concentration_not_concentrating():
    """Test concentration check when not concentrating."""
    state = ConcentrationState()
    result = check_concentration(state, damage_taken=10, con_score=10, proficiency_bonus=2)
    assert result.concentration_lost is False
    assert result.reason == "Not concentrating on any spell"


def test_check_concentration_no_damage():
    """Test concentration check with no damage."""
    state = ConcentrationState(
        spell_name="Bless",
        spell_id="bless",
        is_concentrating=True,
    )
    result = check_concentration(state, damage_taken=0, con_score=10, proficiency_bonus=2)
    assert result.concentration_lost is False
    assert result.reason == "No damage taken"


def test_check_concentration_with_damage():
    """Test concentration check with damage."""
    state = ConcentrationState(
        spell_name="Bless",
        spell_id="bless",
        is_concentrating=True,
    )
    # Take 10 damage -> DC = max(10, 5) = 10
    # Con mod from 10 = 0, proficiency = 2
    # Need to roll 8 or higher on d20
    result = check_concentration(state, damage_taken=10, con_score=10, proficiency_bonus=2)
    assert result.damage_taken == 10
    assert result.concentration_dc == 10
    assert result.con_mod == 0
    # Result depends on dice roll, so just check structure
    assert isinstance(result.roll_total, int)
    assert isinstance(result.success, bool)


def test_check_concentration_high_dc():
    """Test concentration check with high damage."""
    state = ConcentrationState(
        spell_name="Bless",
        spell_id="bless",
        is_concentrating=True,
    )
    # Take 50 damage -> DC = max(10, 25) = 25
    result = check_concentration(state, damage_taken=50, con_score=10, proficiency_bonus=2)
    assert result.concentration_dc == 25
    assert result.damage_taken == 50


def test_check_concentration_with_proficiency():
    """Test concentration check with Constitution save proficiency."""
    state = ConcentrationState(
        spell_name="Bless",
        spell_id="bless",
        is_concentrating=True,
    )
    result = check_concentration(
        state,
        damage_taken=10,
        con_score=10,
        proficiency_bonus=2,
        con_proficient=True,
    )
    assert result.concentration_dc == 10
    assert result.con_mod == 0
    # With proficiency, roll_total = d20 + 0 + 2
    # The actual roll depends on dice


def test_check_concentration_high_con():
    """Test concentration check with high Constitution."""
    state = ConcentrationState(
        spell_name="Bless",
        spell_id="bless",
        is_concentrating=True,
    )
    result = check_concentration(
        state,
        damage_taken=10,
        con_score=18,  # +4 mod
        proficiency_bonus=2,
    )
    assert result.concentration_dc == 10
    assert result.con_mod == 4


def test_start_concentration():
    """Test starting concentration."""
    state = start_concentration("Bless", "bless")
    assert state.is_concentrating is True
    assert state.spell_name == "Bless"
    assert state.spell_id == "bless"


def test_end_concentration():
    """Test ending concentration."""
    state = end_concentration("Ended manually")
    assert state.is_concentrating is False
    assert state.spell_name == ""
    assert state.spell_id == ""


def test_can_concentrate():
    """Test checking if a character can concentrate."""
    not_concentrating = ConcentrationState()
    assert can_concentrate(not_concentrating) is True

    already_concentrating = ConcentrationState(
        spell_name="Bless",
        spell_id="bless",
        is_concentrating=True,
    )
    assert can_concentrate(already_concentrating) is False


def test_should_break_concentration():
    """Test conditions that break concentration."""
    # These conditions break concentration
    assert should_break_concentration(["stunned"]) is True
    assert should_break_concentration(["paralyzed"]) is True
    assert should_break_concentration(["petrified"]) is True
    assert should_break_concentration(["unconscious"]) is True

    # These don't break concentration
    assert should_break_concentration(["poisoned"]) is False
    assert should_break_concentration(["blinded"]) is False
    assert should_break_concentration(["prone"]) is False
    assert should_break_concentration(["grappled"]) is False
    assert should_break_concentration([]) is False

    # Mixed conditions - if any breaks, it should break
    assert should_break_concentration(["poisoned", "stunned"]) is True
    assert should_break_concentration(["blinded", "paralyzed"]) is True


def test_concentration_check_result_serialization():
    """Test that ConcentrationCheckResult can be serialized."""
    result = ConcentrationCheckResult(
        damage_taken=10,
        concentration_dc=10,
        con_mod=0,
        roll_total=15,
        success=True,
        concentration_lost=False,
        reason="Rolled 15 + 0 (Con mod) + 2 (prof) = 17 vs DC 10",
    )
    data = result.to_dict()
    assert data["damage_taken"] == 10
    assert data["concentration_dc"] == 10
    assert data["success"] is True
    assert data["concentration_lost"] is False


def test_concentration_loss_updates_state():
    """Test that losing concentration updates the concentration state."""
    state = ConcentrationState(
        spell_name="Bless",
        spell_id="bless",
        is_concentrating=True,
    )

    # Simulate a concentration check result (we'll create one directly)
    result = ConcentrationCheckResult(
        damage_taken=10,
        concentration_dc=20,
        con_mod=0,
        roll_total=5,
        success=False,
        concentration_lost=True,
        reason="Rolled 5 + 0 (Con mod) + 2 (prof) = 7 vs DC 20 (failed)",
    )

    assert result.concentration_lost is True
    # The calling code would then update the state
    if result.concentration_lost:
        state = end_concentration()

    assert state.is_concentrating is False
    assert state.spell_name == ""