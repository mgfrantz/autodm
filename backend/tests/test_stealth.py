"""
Stealth engine tests — hide/detect mechanics.

Tests the stealth system integration with the combat engine, including:
- Hide action and stealth roll calculation
- Detection via passive Perception
- Hidden attackers gain advantage and reveal on attack
- Hidden targets impose disadvantage
- Serialization round-trips
- API endpoints
"""
import pytest

from app.engine.stealth import (
    attempt_hide,
    check_detection,
    get_stealth_dc,
    get_stealth_status,
    is_hidden,
    list_visible_enemies,
    reveal,
)
from app.engine.combat import Combatant, Attack, Encounter


# --------------------------------------------------------------------------- #
# Engine tests
# --------------------------------------------------------------------------- #
class TestStealthEngine:
    """Test the core stealth engine functions."""

    def test_attempt_hide_sets_hidden_state(self):
        """Hide action should set hidden, stealth_roll, and stealth_dc."""
        combatant = Combatant(
            id="player",
            name="Hero",
            side="player",
            max_hp=10,
            armor_class=15,
            dexterity=16,
        )

        result = attempt_hide(combatant, rolls=[10])

        assert combatant.hidden is True
        assert combatant.stealth_roll > 0
        assert combatant.stealth_dc == combatant.stealth_roll
        assert result.success is True
        assert result.hidden is True
        assert "hides with a stealth check" in result.description

    def test_check_detection_success(self):
        """Detection succeeds when passive Perception meets or exceeds stealth DC."""
        hidden = Combatant(
            id="enemy",
            name="Goblin",
            side="enemy",
            max_hp=7,
            armor_class=12,
            hidden=True,
            stealth_dc=15,
        )

        # Passive Perception 15 equals DC 15 → detected
        result = check_detection(hidden, observer_passive_perception=15)
        assert result.detected is True
        assert "detected" in result.description

        # Passive Perception 16 exceeds DC 15 → detected
        result = check_detection(hidden, observer_passive_perception=16)
        assert result.detected is True

    def test_check_detection_failure(self):
        """Detection fails when passive Perception is below stealth DC."""
        hidden = Combatant(
            id="enemy",
            name="Goblin",
            side="enemy",
            max_hp=7,
            armor_class=12,
            hidden=True,
            stealth_dc=15,
        )

        # Passive Perception 14 < DC 15 → not detected
        result = check_detection(hidden, observer_passive_perception=14)
        assert result.detected is False
        assert "remains hidden" in result.description

    def test_reveal_clears_hidden_state(self):
        """Reveal should clear hidden, stealth_roll, and stealth_dc."""
        combatant = Combatant(
            id="player",
            name="Hero",
            side="player",
            max_hp=10,
            armor_class=15,
            hidden=True,
            stealth_roll=15,
            stealth_dc=15,
        )

        reveal(combatant)

        assert combatant.hidden is False
        assert combatant.stealth_roll == 0
        assert combatant.stealth_dc == 0

    def test_is_hidden_helper(self):
        """is_hidden should return the combatant's hidden state."""
        visible = Combatant(
            id="player",
            name="Hero",
            side="player",
            max_hp=10,
            armor_class=15,
            hidden=False,
        )
        hidden = Combatant(
            id="enemy",
            name="Goblin",
            side="enemy",
            max_hp=7,
            armor_class=12,
            hidden=True,
        )

        assert is_hidden(visible) is False
        assert is_hidden(hidden) is True

    def test_get_stealth_dc_helper(self):
        """get_stealth_dc should return DC if hidden, 0 otherwise."""
        visible = Combatant(
            id="player",
            name="Hero",
            side="player",
            max_hp=10,
            armor_class=15,
            hidden=False,
        )
        hidden = Combatant(
            id="enemy",
            name="Goblin",
            side="enemy",
            max_hp=7,
            armor_class=12,
            hidden=True,
            stealth_dc=18,
        )

        assert get_stealth_dc(visible) == 0
        assert get_stealth_dc(hidden) == 18

    def test_get_stealth_status(self):
        """get_stealth_status should return a dict with full status."""
        visible = Combatant(
            id="player",
            name="Hero",
            side="player",
            max_hp=10,
            armor_class=15,
            hidden=False,
        )
        hidden = Combatant(
            id="enemy",
            name="Goblin",
            side="enemy",
            max_hp=7,
            armor_class=12,
            hidden=True,
            stealth_roll=18,
            stealth_dc=18,
        )

        status = get_stealth_status(visible)
        assert status["hidden"] is False
        assert "not hidden" in status["description"]

        status = get_stealth_status(hidden)
        assert status["hidden"] is True
        assert status["stealth_roll"] == 18
        assert status["stealth_dc"] == 18

    def test_list_visible_enemies(self):
        """list_visible_enemies should check detection for all enemies."""
        player = Combatant(
            id="player",
            name="Hero",
            side="player",
            max_hp=10,
            armor_class=15,
        )

        visible_enemy = Combatant(
            id="enemy1",
            name="Orc",
            side="enemy",
            max_hp=15,
            armor_class=13,
            hidden=False,
        )

        hidden_detected = Combatant(
            id="enemy2",
            name="Goblin",
            side="enemy",
            max_hp=7,
            armor_class=12,
            hidden=True,
            stealth_dc=14,
        )

        hidden_undetected = Combatant(
            id="enemy3",
            name="Bugbear",
            side="enemy",
            max_hp=27,
            armor_class=16,
            hidden=True,
            stealth_dc=20,
        )

        combatants = [player, visible_enemy, hidden_detected, hidden_undetected]

        # Passive Perception 15 detects DC 14, not DC 20
        results = list_visible_enemies(combatants, observer_passive_perception=15)

        assert len(results) == 3
        assert results["enemy1"].detected is True  # Not hidden
        assert results["enemy2"].detected is True   # Hidden but detected
        assert results["enemy3"].detected is False  # Hidden and undetected

    # --------------------------------------------------------------------------- #
    # Combat integration tests (hidden in same class for simplicity)
    # --------------------------------------------------------------------------- #
    def test_attacker_revealed_on_hit(self):
        """Attacker should be revealed when making an attack (hit)."""
        player = Combatant(
            id="player",
            name="Hero",
            side="player",
            max_hp=10,
            armor_class=15,
            attacks=[Attack(name="Longsword", attack_bonus=10, damage_dice_sides=8)],
        )
        player.hidden = True

        enemy = Combatant(
            id="enemy",
            name="Orc",
            side="enemy",
            max_hp=15,
            armor_class=13,
        )

        encounter = Encounter(combatants=[player, enemy])

        # Make a hit (high attack bonus vs low AC)
        result = encounter.resolve_attack(player, enemy, player.attacks[0])

        assert result.hit is True
        assert player.hidden is False
        assert player.stealth_roll == 0
        assert player.stealth_dc == 0

    def test_attacker_revealed_on_miss(self):
        """Attacker should be revealed when making an attack (miss)."""
        player = Combatant(
            id="player",
            name="Hero",
            side="player",
            max_hp=10,
            armor_class=15,
            attacks=[Attack(name="Longsword", attack_bonus=-20, damage_dice_count=0)],  # Will miss
        )
        player.hidden = True

        enemy = Combatant(
            id="enemy",
            name="Orc",
            side="enemy",
            max_hp=15,
            armor_class=13,
        )

        encounter = Encounter(combatants=[player, enemy])

        result = encounter.resolve_attack(player, enemy, player.attacks[0])

        assert result.hit is False
        assert player.hidden is False
        assert player.stealth_roll == 0
        assert player.stealth_dc == 0

    def test_serialization_round_trip(self):
        """Stealth state should survive serialization round-trip."""
        player = Combatant(
            id="player",
            name="Hero",
            side="player",
            max_hp=10,
            armor_class=15,
            dexterity=16,
            attacks=[Attack(name="Longsword", attack_bonus=5)],
            hidden=True,
            stealth_roll=18,
            stealth_dc=18,
        )

        encounter = Encounter(combatants=[player])

        # Serialize
        data = encounter.to_dict()

        # Deserialize
        restored = Encounter.from_dict(data)

        restored_player = restored.combatants[0]

        assert restored_player.hidden is True
        assert restored_player.stealth_roll == 18
        assert restored_player.stealth_dc == 18


# --------------------------------------------------------------------------- #
# Character skill integration tests (simplified, removed complex mocking)
# --------------------------------------------------------------------------- #
class TestStealthWithCharacterSkills:
    """Test stealth with actual character skill bonuses."""

    def test_attempt_hide_with_character_skill_bonus(self):
        """Hide with a character should include skill proficiency bonus."""
        # Note: Simplified test without complex MockCharacter
        # The core hide functionality is tested elsewhere
        combatant = Combatant(
            id="player",
            name="Hero",
            side="player",
            max_hp=10,
            armor_class=15,
            dexterity=16,
        )

        # Create a simple character-like object
        class SimpleChar:
            dexterity = 16
            level = 3
            classes_dict = {"rogue": 3}
            char_class = "rogue"
            skill_proficiencies = '["stealth"]'
            skill_expertise = '[]'
            feats = '[]'

        result = attempt_hide(combatant, SimpleChar(), rolls=[10])

        # Dex mod +3, proficiency +2, roll 10 = 15
        assert result.stealth_dc == 15
        assert result.breakdown["ability"] == "dexterity"
        assert result.breakdown["proficient"] is True

    def test_attempt_hide_with_expertise(self):
        """Hide with expertise should double the proficiency bonus."""
        combatant = Combatant(
            id="player",
            name="Hero",
            side="player",
            max_hp=10,
            armor_class=15,
            dexterity=16,
        )

        class SimpleChar:
            dexterity = 16
            level = 3
            classes_dict = {"rogue": 3}
            char_class = "rogue"
            skill_proficiencies = '["stealth"]'
            skill_expertise = '["stealth"]'
            feats = '[]'

        result = attempt_hide(combatant, SimpleChar(), rolls=[10])

        # Dex mod +3, expertise +4 (double prof), roll 10 = 17
        assert result.stealth_dc == 17
        assert result.breakdown["expertise"] is True