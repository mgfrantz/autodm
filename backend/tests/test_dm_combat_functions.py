"""
Tests for DM-callable combat functions — Phase 2 wrappers around the Encounter
engine that produce ATTACK / DAMAGE / INITIATIVE GameEvent objects.

Dice rolls are mocked so hit/miss/crit outcomes are deterministic.
"""
from unittest.mock import patch

import pytest

from app.engine.combat import Attack, Combatant, Encounter
from app.engine.dice import RollResult
from app.engine.game_events import GameEvent, GameEventType
from app.engine.dm_functions import (
    dm_attack,
    dm_apply_damage,
    dm_roll_initiative,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_encounter() -> Encounter:
    """Build a simple 2-combatant encounter (hero vs goblin)."""
    hero = Combatant(
        id="hero",
        name="Hero",
        side="player",
        max_hp=30,
        armor_class=16,
        initiative_bonus=2,
        attacks=[
            Attack(
                name="Longsword",
                attack_bonus=5,
                damage_dice_count=1,
                damage_dice_sides=8,
                damage_bonus=3,
                damage_type="slashing",
            ),
        ],
    )
    hero.current_hp = 30

    goblin = Combatant(
        id="goblin",
        name="Goblin",
        side="enemy",
        max_hp=12,
        armor_class=13,
        initiative_bonus=1,
        attacks=[
            Attack(
                name="Scimitar",
                attack_bonus=4,
                damage_dice_count=1,
                damage_dice_sides=6,
                damage_bonus=2,
                damage_type="slashing",
            ),
        ],
    )
    goblin.current_hp = 12

    return Encounter(combatants=[hero, goblin])


# ===========================================================================
# dm_attack
# ===========================================================================

class TestDmAttack:
    """dm_attack wraps Encounter.resolve_attack and returns an attack GameEvent."""

    def test_attack_hit(self):
        """A high attack roll beats AC and produces a hit event."""
        encounter = _make_encounter()
        with patch("app.engine.combat.roll_d20") as mock_d20, \
             patch("app.engine.combat.roll_dice") as mock_dmg:
            mock_d20.return_value = RollResult(
                rolls=[15], modifier=5, total=20,
                description="d20+5",
            )
            # 1d8+3 → say 6+3 = 9
            mock_dmg.return_value = RollResult(
                rolls=[6], modifier=3, total=9,
                description="1d8+3",
            )
            event = dm_attack(encounter, "hero", "goblin")
        assert event.type == GameEventType.ATTACK
        assert event.data["hit"] is True
        assert event.data["critical"] is False
        assert event.data["critical_miss"] is False
        assert event.data["attack_total"] == 20
        assert event.data["ac"] == 13
        assert event.data["damage"] == 9
        assert event.data["damage_type"] == "slashing"
        assert event.data["target_remaining_hp"] == 12 - 9
        assert event.data["target_max_hp"] == 12

    def test_attack_miss(self):
        """A low attack roll produces a miss event with zero damage."""
        encounter = _make_encounter()
        with patch("app.engine.combat.roll_d20") as mock_d20:
            mock_d20.return_value = RollResult(
                rolls=[3], modifier=5, total=8,
                description="d20+5",
            )
            event = dm_attack(encounter, "hero", "goblin")
        assert event.data["hit"] is False
        assert event.data["damage"] == 0
        assert event.data["target_remaining_hp"] == 12  # unchanged

    def test_attack_critical_hit(self):
        """A natural 20 is a critical hit with doubled damage dice."""
        encounter = _make_encounter()
        with patch("app.engine.combat.roll_d20") as mock_d20, \
             patch("app.engine.combat.roll_dice") as mock_dmg:
            mock_d20.return_value = RollResult(
                rolls=[20], modifier=5, total=25,
                description="d20+5",
            )
            # crit doubles dice count: 2d8+3 → say 6+5+3 = 14
            mock_dmg.return_value = RollResult(
                rolls=[6, 5], modifier=3, total=14,
                description="2d8+3",
            )
            event = dm_attack(encounter, "hero", "goblin")
        assert event.data["hit"] is True
        assert event.data["critical"] is True

    def test_attack_critical_miss(self):
        """A natural 1 is an automatic miss (critical miss)."""
        encounter = _make_encounter()
        with patch("app.engine.combat.roll_d20") as mock_d20:
            mock_d20.return_value = RollResult(
                rolls=[1], modifier=5, total=6,
                description="d20+5",
            )
            event = dm_attack(encounter, "hero", "goblin")
        assert event.data["hit"] is False
        assert event.data["critical_miss"] is True

    def test_attack_with_advantage(self):
        """Advantage flag is passed through to resolve_attack."""
        encounter = _make_encounter()
        with patch.object(encounter, "resolve_attack") as mock_resolve:
            from app.engine.combat import AttackResult
            mock_resolve.return_value = AttackResult(
                attack_total=20, hit=True, critical=False, critical_miss=False,
                damage=8, target_remaining_hp=4, description="hit",
            )
            dm_attack(encounter, "hero", "goblin", advantage=True)
        _, kwargs = mock_resolve.call_args
        assert kwargs.get("advantage") is True

    def test_attack_label_includes_attacker_and_target(self):
        encounter = _make_encounter()
        with patch("app.engine.combat.roll_d20") as mock_d20, \
             patch("app.engine.combat.roll_dice") as mock_dmg:
            mock_d20.return_value = RollResult(
                rolls=[15], modifier=5, total=20, description="d20+5",
            )
            mock_dmg.return_value = RollResult(
                rolls=[6], modifier=3, total=9, description="1d8+3",
            )
            event = dm_attack(encounter, "hero", "goblin")
        assert "Hero" in event.label
        assert "Goblin" in event.label

    def test_attack_invalid_attacker_id_raises(self):
        encounter = _make_encounter()
        with pytest.raises(ValueError, match="Attacker not found"):
            dm_attack(encounter, "nobody", "goblin")

    def test_attack_invalid_target_id_raises(self):
        encounter = _make_encounter()
        with pytest.raises(ValueError, match="Target not found"):
            dm_attack(encounter, "hero", "nobody")

    def test_attack_invalid_attack_index_raises(self):
        encounter = _make_encounter()
        with pytest.raises(ValueError, match="out of range"):
            dm_attack(encounter, "hero", "goblin", attack_index=99)

    def test_attack_updates_target_hp_in_encounter(self):
        """The encounter's combatant HP is mutated by the attack."""
        encounter = _make_encounter()
        with patch("app.engine.combat.roll_d20") as mock_d20, \
             patch("app.engine.combat.roll_dice") as mock_dmg:
            mock_d20.return_value = RollResult(
                rolls=[15], modifier=5, total=20, description="d20+5",
            )
            mock_dmg.return_value = RollResult(
                rolls=[6], modifier=3, total=9, description="1d8+3",
            )
            dm_attack(encounter, "hero", "goblin")
        goblin = encounter.combatants[1]
        assert goblin.current_hp == 3  # 12 - 9

    def test_attack_second_attack_index(self):
        """Selecting attack_index=1 uses the second attack in the list."""
        encounter = _make_encounter()
        hero = encounter.combatants[0]
        hero.attacks.append(
            Attack(name="Dagger", attack_bonus=3, damage_dice_count=1,
                   damage_dice_sides=4, damage_bonus=1, damage_type="piercing"),
        )
        with patch("app.engine.combat.roll_d20") as mock_d20, \
             patch("app.engine.combat.roll_dice") as mock_dmg:
            mock_d20.return_value = RollResult(
                rolls=[15], modifier=3, total=18, description="d20+3",
            )
            mock_dmg.return_value = RollResult(
                rolls=[3], modifier=1, total=4, description="1d4+1",
            )
            event = dm_attack(encounter, "hero", "goblin", attack_index=1)
        assert event.data["damage_type"] == "piercing"


# ===========================================================================
# dm_apply_damage
# ===========================================================================

class TestDmApplyDamage:
    """dm_apply_damage wraps Combatant.take_damage and returns a damage event."""

    def test_apply_damage_reduces_hp(self):
        encounter = _make_encounter()
        event = dm_apply_damage(encounter, "goblin", amount=5)
        assert event.type == GameEventType.DAMAGE
        assert event.data["amount"] == 5
        assert event.data["target_remaining_hp"] == 7  # 12 - 5
        assert event.data["target_max_hp"] == 12

    def test_apply_damage_kills_target(self):
        encounter = _make_encounter()
        event = dm_apply_damage(encounter, "goblin", amount=20)
        assert event.data["target_remaining_hp"] == 0  # floor at 0
        assert event.data["target_remaining_hp"] == 0

    def test_apply_damage_exact_hp(self):
        """Damage exactly equal to current HP drops to 0."""
        encounter = _make_encounter()
        event = dm_apply_damage(encounter, "goblin", amount=12)
        assert event.data["target_remaining_hp"] == 0

    def test_apply_damage_default_type(self):
        encounter = _make_encounter()
        event = dm_apply_damage(encounter, "goblin", amount=3)
        assert event.data["damage_type"] == "slashing"

    def test_apply_damage_custom_type(self):
        encounter = _make_encounter()
        event = dm_apply_damage(encounter, "goblin", amount=3, damage_type="fire")
        assert event.data["damage_type"] == "fire"

    def test_apply_damage_invalid_target_raises(self):
        encounter = _make_encounter()
        with pytest.raises(ValueError, match="Target not found"):
            dm_apply_damage(encounter, "ghost", amount=5)

    def test_apply_damage_label_includes_target_and_amount(self):
        encounter = _make_encounter()
        event = dm_apply_damage(encounter, "goblin", amount=5, damage_type="fire")
        assert "Goblin" in event.label
        assert "5" in event.label
        assert "fire" in event.label.lower()

    def test_apply_damage_mutates_encounter(self):
        """The encounter's combatant HP is mutated by the damage."""
        encounter = _make_encounter()
        dm_apply_damage(encounter, "goblin", amount=5)
        assert encounter.combatants[1].current_hp == 7


# ===========================================================================
# dm_roll_initiative
# ===========================================================================

class TestDmRollInitiative:
    """dm_roll_initiative rolls initiative for all combatants and sorts."""

    def test_roll_initiative_returns_event(self):
        encounter = _make_encounter()
        with patch("app.engine.combat.roll_d20") as mock_d20:
            mock_d20.side_effect = [
                RollResult(rolls=[14], modifier=2, total=16, description="d20+2"),
                RollResult(rolls=[8], modifier=1, total=9, description="d20+1"),
            ]
            event = dm_roll_initiative(encounter)
        assert event.type == GameEventType.INITIATIVE

    def test_roll_initiative_sorted_descending(self):
        """Combatants are sorted by initiative (highest first)."""
        encounter = _make_encounter()
        with patch("app.engine.combat.roll_d20") as mock_d20:
            mock_d20.side_effect = [
                RollResult(rolls=[14], modifier=2, total=16, description="d20+2"),
                RollResult(rolls=[18], modifier=1, total=19, description="d20+1"),
            ]
            event = dm_roll_initiative(encounter)
        combatants = event.data["combatants"]
        assert len(combatants) == 2
        # Goblin rolled 19, hero rolled 16 → goblin first
        assert combatants[0]["name"] == "Goblin"
        assert combatants[0]["initiative"] == 19
        assert combatants[1]["name"] == "Hero"
        assert combatants[1]["initiative"] == 16

    def test_roll_initiative_sets_encounter_started(self):
        encounter = _make_encounter()
        assert encounter.started is False
        with patch("app.engine.combat.roll_d20") as mock_d20:
            mock_d20.side_effect = [
                RollResult(rolls=[14], modifier=2, total=16, description="d20+2"),
                RollResult(rolls=[8], modifier=1, total=9, description="d20+1"),
            ]
            dm_roll_initiative(encounter)
        assert encounter.started is True

    def test_roll_initiative_updates_turn_order(self):
        """The encounter's turn_order is updated to match the sorted order."""
        encounter = _make_encounter()
        with patch("app.engine.combat.roll_d20") as mock_d20:
            mock_d20.side_effect = [
                RollResult(rolls=[14], modifier=2, total=16, description="d20+2"),
                RollResult(rolls=[18], modifier=1, total=19, description="d20+1"),
            ]
            dm_roll_initiative(encounter)
        assert len(encounter.turn_order) == 2
        assert encounter.turn_order[0].name == "Goblin"

    def test_roll_initiative_combatant_dict_fields(self):
        encounter = _make_encounter()
        with patch("app.engine.combat.roll_d20") as mock_d20:
            mock_d20.side_effect = [
                RollResult(rolls=[10], modifier=2, total=12, description="d20+2"),
                RollResult(rolls=[10], modifier=1, total=11, description="d20+1"),
            ]
            event = dm_roll_initiative(encounter)
        c = event.data["combatants"][0]
        assert "id" in c
        assert "name" in c
        assert "initiative" in c
        assert "side" in c

    def test_roll_initiative_tiebreak_by_dex(self):
        """Ties in initiative are broken by initiative_bonus (Dex)."""
        encounter = _make_encounter()
        with patch("app.engine.combat.roll_d20") as mock_d20:
            mock_d20.side_effect = [
                RollResult(rolls=[10], modifier=2, total=12, description="d20+2"),
                RollResult(rolls=[11], modifier=1, total=12, description="d20+1"),
            ]
            event = dm_roll_initiative(encounter)
        # Both rolled 12; hero has higher initiative_bonus (2 > 1) → hero first
        assert event.data["combatants"][0]["name"] == "Hero"
