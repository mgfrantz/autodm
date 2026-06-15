"""
Tests for the combat engine: initiative, turn order, attack resolution,
HP tracking, win conditions, and serialization.
"""
import pytest

from app.engine.combat import Attack, Combatant, Encounter
from app.engine import dice


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def make_player() -> Combatant:
    return Combatant(
        id="hero",
        name="Hero",
        side="player",
        max_hp=30,
        armor_class=16,
        initiative_bonus=3,
        attacks=[Attack(name="Longsword", attack_bonus=5, damage_dice_count=1, damage_dice_sides=8, damage_bonus=3)],
    )


def make_goblin() -> Combatant:
    return Combatant(
        id="goblin1",
        name="Goblin",
        side="enemy",
        max_hp=7,
        armor_class=15,
        initiative_bonus=2,
        attacks=[Attack(name="Scimitar", attack_bonus=4, damage_dice_count=1, damage_dice_sides=6, damage_bonus=2)],
    )


def fixed_die(value: int):
    """Return a function replacing random.randint that always yields `value`."""
    def _roll(_lo, _hi):
        return value
    return _roll


# ---------------------------------------------------------------------------
# Combatant
# ---------------------------------------------------------------------------

class TestCombatant:
    def test_default_hp_is_max(self):
        c = Combatant(id="a", name="A", side="player", max_hp=12, armor_class=10)
        assert c.current_hp == 12
        assert c.is_alive

    def test_take_damage_reduces_hp(self):
        c = make_player()
        assert c.take_damage(10) == 20
        assert c.current_hp == 20

    def test_take_damage_floors_at_zero(self):
        c = make_goblin()
        c.take_damage(999)
        assert c.current_hp == 0
        assert not c.is_alive

    def test_heal_caps_at_max(self):
        c = make_player()
        c.take_damage(10)
        assert c.heal(999) == 30
        assert c.current_hp == 30

    def test_conditions_dedup(self):
        c = make_player()
        c.add_condition("poisoned")
        c.add_condition("poisoned")
        c.add_condition("frightened")
        assert c.conditions == ["poisoned", "frightened"]
        c.remove_condition("poisoned")
        assert c.conditions == ["frightened"]

    def test_roll_initiative(self, monkeypatch):
        c = make_player()  # initiative_bonus 3
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        assert c.roll_initiative() == 13  # 10 + 3
        assert c.initiative == 13


# ---------------------------------------------------------------------------
# Attack
# ---------------------------------------------------------------------------

class TestAttack:
    def test_roll_damage_includes_bonus(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(4))
        a = Attack(name="x", attack_bonus=0, damage_dice_count=2, damage_dice_sides=8, damage_bonus=2)
        # 2 dice of 4 each + bonus 2 = 10
        assert a.roll_damage() == 10

    def test_roll_damage_crit_doubles_dice_not_bonus(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(4))
        a = Attack(name="x", attack_bonus=0, damage_dice_count=2, damage_dice_sides=8, damage_bonus=2)
        # Crit: 4 dice of 4 each = 16 + bonus 2 = 18
        assert a.roll_damage(critical=True) == 18


# ---------------------------------------------------------------------------
# Encounter setup & initiative
# ---------------------------------------------------------------------------

class TestEncounterInitiative:
    def test_add_combatant(self):
        enc = Encounter()
        p = make_player()
        enc.add_combatant(p)
        assert enc.combatants == [p]

    def test_cannot_add_after_start(self):
        enc = Encounter([make_player(), make_goblin()])
        enc.start()
        with pytest.raises(RuntimeError):
            enc.add_combatant(make_player())

    def test_initiative_order_descending(self, monkeypatch):
        # Player rolls 15 (+3 = 18), Goblin rolls 10 (+2 = 12) -> player first
        rolls = iter([15, 10])
        monkeypatch.setattr(dice.random, "randint", lambda _a, _b: next(rolls))
        enc = Encounter([make_player(), make_goblin()])
        order = enc.roll_initiative()
        assert order[0] == ("Hero", 18)
        assert order[1] == ("Goblin", 12)
        assert enc.turn_order[0].name == "Hero"

    def test_start_sets_round_one(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = Encounter([make_player(), make_goblin()])
        enc.start()
        assert enc.started
        assert enc.round_number == 1
        assert enc.current_turn_index == 0


# ---------------------------------------------------------------------------
# Turn order & win conditions
# ---------------------------------------------------------------------------

class TestEncounterTurns:
    def _started_encounter(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        player = make_player()
        goblin = make_goblin()
        enc = Encounter([player, goblin])
        enc.start()
        return enc, player, goblin

    def test_current_combatant_is_first(self, monkeypatch):
        enc, player, _ = self._started_encounter(monkeypatch)
        # Player initiative 13 > goblin 12, so player goes first.
        assert enc.current_combatant.id == "hero"

    def test_next_turn_advances(self, monkeypatch):
        enc, _, goblin = self._started_encounter(monkeypatch)
        nxt = enc.next_turn()
        assert nxt is not None
        assert nxt.id == "goblin1"

    def test_next_turn_wraps_to_new_round(self, monkeypatch):
        enc, _, _ = self._started_encounter(monkeypatch)
        enc.next_turn()  # goblin
        back = enc.next_turn()  # wraps to player
        assert back is not None
        assert back.id == "hero"
        assert enc.round_number == 2

    def test_next_turn_skips_dead(self, monkeypatch):
        enc, player, goblin = self._started_encounter(monkeypatch)
        goblin.take_damage(999)  # goblin dead
        nxt = enc.next_turn()
        assert nxt is not None
        assert nxt.id == "hero"  # skips dead goblin, wraps to player

    def test_is_active_while_both_sides_alive(self, monkeypatch):
        enc, _, _ = self._started_encounter(monkeypatch)
        assert enc.is_active

    def test_winner_when_enemies_dead(self, monkeypatch):
        enc, _, goblin = self._started_encounter(monkeypatch)
        goblin.take_damage(999)
        assert enc.winner == "player"
        assert not enc.is_active

    def test_winner_when_players_dead(self, monkeypatch):
        enc, player, _ = self._started_encounter(monkeypatch)
        player.take_damage(999)
        assert enc.winner == "enemy"

    def test_no_winner_while_ongoing(self, monkeypatch):
        enc, _, _ = self._started_encounter(monkeypatch)
        assert enc.winner is None


# ---------------------------------------------------------------------------
# Attack resolution
# ---------------------------------------------------------------------------

class TestResolveAttack:
    def test_hit_when_total_meets_ac(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(13))
        player = make_player()  # attack_bonus 5 -> total 18
        goblin = make_goblin()  # AC 15
        enc = Encounter([player, goblin])
        enc.start()
        result = enc.resolve_attack(player, goblin, player.attacks[0])
        assert result.hit
        assert not result.critical
        assert result.attack_total == 18
        assert result.damage > 0

    def test_miss_when_total_below_ac(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(2))
        player = make_player()  # total 7 < AC 15
        goblin = make_goblin()
        enc = Encounter([player, goblin])
        enc.start()
        result = enc.resolve_attack(player, goblin, player.attacks[0])
        assert not result.hit
        assert result.damage == 0

    def test_natural_20_is_critical_hit(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(20))
        player = make_player()
        goblin = make_goblin()
        enc = Encounter([player, goblin])
        enc.start()
        result = enc.resolve_attack(player, goblin, player.attacks[0])
        assert result.hit
        assert result.critical
        # Crit doubles dice: 1d8 -> 2d8. With fixed 20 per die that's 40 + bonus 3 = 43.
        assert result.damage == 43

    def test_natural_1_is_critical_miss(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(1))
        player = make_player()
        goblin = make_goblin()
        enc = Encounter([player, goblin])
        enc.start()
        result = enc.resolve_attack(player, goblin, player.attacks[0])
        assert not result.hit
        assert result.critical_miss

    def test_damage_reduces_target_hp(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(13))
        player = make_player()
        goblin = make_goblin()  # max_hp 7
        enc = Encounter([player, goblin])
        enc.start()
        # damage = d8(13 capped -> die) ... actually fixed_die(13) for randint(1,8)
        # yields 13, which is invalid for a d8 but randint is mocked broadly.
        # damage_dice roll uses randint(1, sides) -> returns 13, sum=13 + bonus 3 = 16.
        result = enc.resolve_attack(player, goblin, player.attacks[0])
        assert result.damage == 16  # 13 + 3
        assert goblin.current_hp == 0
        assert not goblin.is_alive


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_combatant_round_trip(self):
        c = make_player()
        c.take_damage(5)
        c.add_condition("poisoned")
        data = c.to_dict()
        restored = Combatant.from_dict(data)
        assert restored.id == c.id
        assert restored.name == c.name
        assert restored.current_hp == 25
        assert restored.armor_class == 16
        assert restored.conditions == ["poisoned"]
        assert len(restored.attacks) == 1
        assert restored.attacks[0].name == "Longsword"

    def test_encounter_round_trip(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = Encounter([make_player(), make_goblin()])
        enc.start()
        enc.next_turn()  # advance once
        data = enc.to_dict()

        restored = Encounter.from_dict(data)
        assert restored.started
        assert restored.round_number == 1
        assert len(restored.turn_order) == 2
        # Turn order preserved by id.
        assert restored.turn_order[0].id == enc.turn_order[0].id
        assert restored.current_turn_index == enc.current_turn_index
