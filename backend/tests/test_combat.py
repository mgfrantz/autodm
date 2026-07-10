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


# ---------------------------------------------------------------------------
# Damage-type modifiers (resistance/immunity/vulnerability)
# ---------------------------------------------------------------------------

    def test_combatant_immune_to_poison_takes_no_damage(self, monkeypatch):
        from app.engine.damage_types import immune
        # Dagger: 1d4. Set die to 8 for hit (8+5=13 vs AC 13) and damage 8.
        monkeypatch.setattr(dice.random, "randint", fixed_die(8))
        skeleton = Combatant(
            id="skel1",
            name="Skeleton",
            side="enemy",
            max_hp=13,
            armor_class=13,
            damage_modifiers=[immune("poison").to_dict()],
        )
        hero = Combatant(
            id="hero",
            name="Hero",
            side="player",
            max_hp=30,
            armor_class=16,
            attacks=[Attack(name="Poisoned Dagger", attack_bonus=5, damage_dice_count=1, damage_dice_sides=4, damage_type="poison")],
        )
        enc = Encounter([hero, skeleton])
        result = enc.resolve_attack(hero, skeleton, hero.attacks[0])
        assert result.hit
        assert result.damage == 0  # immunity

    def test_resistance_halves_damage(self, monkeypatch):
        from app.engine.damage_types import resist
        # Firebolt: 2d6+2. With fixed 4 per die = 8+2=10 raw. 4+5=9 vs AC 13, miss. Need higher.
        monkeypatch.setattr(dice.random, "randint", fixed_die(8))  # 8+5=13 hits; damage: 8+8+2=18; half=9.
        skeleton = Combatant(
            id="skel1",
            name="Skeleton",
            side="enemy",
            max_hp=20,
            armor_class=13,
            damage_modifiers=[resist("fire").to_dict()],
        )
        hero = Combatant(
            id="hero",
            name="Hero",
            side="player",
            max_hp=30,
            armor_class=16,
            attacks=[Attack(name="Firebolt", attack_bonus=5, damage_dice_count=2, damage_dice_sides=6, damage_type="fire", damage_bonus=2)],
        )
        enc = Encounter([hero, skeleton])
        result = enc.resolve_attack(hero, skeleton, hero.attacks[0])
        assert result.hit
        assert result.damage == 9  # (8*2+2) // 2 = 9

    def test_vulnerability_doubles_damage(self, monkeypatch):
        from app.engine.damage_types import vuln
        # Firebolt: 2d6+2. Troll AC 15. Need die 10 to hit (10+5=15). Damage: 10*2+2=22; vuln: 44.
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))  # 10+5=15 hits; damage: 20+2=22; vuln: 44.
        troll = Combatant(
            id="troll1",
            name="Troll",
            side="enemy",
            max_hp=40,
            armor_class=15,
            damage_modifiers=[vuln("fire").to_dict()],
        )
        hero = Combatant(
            id="hero",
            name="Hero",
            side="player",
            max_hp=30,
            armor_class=16,
            attacks=[Attack(name="Firebolt", attack_bonus=5, damage_dice_count=2, damage_dice_sides=6, damage_type="fire", damage_bonus=2)],
        )
        enc = Encounter([hero, troll])
        result = enc.resolve_attack(hero, troll, hero.attacks[0])
        assert result.hit
        assert result.damage == 44  # (20+2) * 2

    def test_nonmagical_resistance_bypassed_by_magic_weapon(self, monkeypatch):
        from app.engine.damage_types import resist_nonmagical_bps
        # Longsword: 1d8+3. Fixed die 10 for hit/damage: 10+5=15 hits; damage: 10+3=13.
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        imp = Combatant(
            id="imp1",
            name="Imp",
            side="enemy",
            max_hp=10,
            armor_class=13,
            damage_modifiers=[resist_nonmagical_bps().to_dict()],
        )
        # Nonmagical sword — resistance applies.
        hero = Combatant(
            id="hero",
            name="Hero",
            side="player",
            max_hp=30,
            armor_class=16,
            attacks=[Attack(name="Longsword", attack_bonus=5, damage_dice_count=1, damage_dice_sides=8, damage_bonus=3, magical=False)],
        )
        enc = Encounter([hero, imp])
        result = enc.resolve_attack(hero, imp, hero.attacks[0])
        assert result.hit
        assert result.damage == 6  # 13 // 2

        # Magic sword — bypasses.
        magic_hero = Combatant(
            id="hero",
            name="Hero",
            side="player",
            max_hp=30,
            armor_class=16,
            attacks=[Attack(name="Magic Longsword +1", attack_bonus=6, damage_dice_count=1, damage_dice_sides=8, damage_bonus=4, magical=True)],
        )
        enc2 = Encounter([magic_hero, imp])
        result2 = enc2.resolve_attack(magic_hero, imp, magic_hero.attacks[0])
        assert result2.hit
        assert result2.damage == 14  # full (10+4)

    def test_lycanthrope_immunity_bypassed_by_silver_or_magic(self, monkeypatch):
        from app.engine.damage_types import immune_nonmagical_bps
        # Longsword: 1d8+3. Fixed die 8 for hit/damage: 8+5=13 hits; damage: 8+3=11.
        monkeypatch.setattr(dice.random, "randint", fixed_die(8))
        werewolf = Combatant(
            id="wolf1",
            name="Werewolf",
            side="enemy",
            max_hp=58,
            armor_class=13,
            damage_modifiers=[immune_nonmagical_bps(silver_bypasses=True).to_dict()],
        )
        # Plain weapon → immunity applies (0 damage).
        hero = Combatant(
            id="hero",
            name="Hero",
            side="player",
            max_hp=30,
            armor_class=16,
            attacks=[Attack(name="Longsword", attack_bonus=5, damage_dice_count=1, damage_dice_sides=8, damage_bonus=3)],
        )
        enc = Encounter([hero, werewolf])
        result = enc.resolve_attack(hero, werewolf, hero.attacks[0])
        assert result.hit
        assert result.damage == 0  # immunity

        # Silvered weapon → bypasses.
        silver_hero = Combatant(
            id="hero",
            name="Hero",
            side="player",
            max_hp=30,
            armor_class=16,
            attacks=[Attack(name="Silver Longsword", attack_bonus=5, damage_dice_count=1, damage_dice_sides=8, damage_bonus=3, silvered=True)],
        )
        enc2 = Encounter([silver_hero, werewolf])
        result2 = enc2.resolve_attack(silver_hero, werewolf, silver_hero.attacks[0])
        assert result2.hit
        assert result2.damage == 11  # full

        # Magic weapon → also bypasses.
        magic_hero = Combatant(
            id="hero",
            name="Hero",
            side="player",
            max_hp=30,
            armor_class=16,
            attacks=[Attack(name="Magic Longsword", attack_bonus=5, damage_dice_count=1, damage_dice_sides=8, damage_bonus=3, magical=True)],
        )
        enc3 = Encounter([magic_hero, werewolf])
        result3 = enc3.resolve_attack(magic_hero, werewolf, magic_hero.attacks[0])
        assert result3.hit
        assert result3.damage == 11  # full

    def test_damage_modifiers_serialization_round_trip(self):
        from app.engine.damage_types import resist, immune
        c = Combatant(
            id="test",
            name="Test",
            side="player",
            max_hp=20,
            armor_class=12,
            damage_modifiers=[
                resist("fire").to_dict(),
                immune("poison").to_dict(),
            ],
        )
        d = c.to_dict()
        assert "damage_modifiers" in d
        assert len(d["damage_modifiers"]) == 2
        restored = Combatant.from_dict(d)
        assert restored.damage_modifiers == c.damage_modifiers
        # Behavior preserved.
        assert restored.apply_damage_modifiers(10, "fire") == 5
        assert restored.apply_damage_modifiers(10, "poison") == 0
        # Attacks serialize magical/silvered.
        magic_atk = Attack(name="Magic Blade", attack_bonus=3, damage_dice_count=1, damage_dice_sides=6, damage_type="slashing", magical=True, silvered=False)
        c2 = Combatant(id="test2", name="Test2", side="player", max_hp=20, armor_class=12, attacks=[magic_atk])
        d2 = c2.to_dict()
        assert d2["attacks"][0]["magical"] is True
        assert d2["attacks"][0]["silvered"] is False
        c2_restored = Combatant.from_dict(d2)
        assert c2_restored.attacks[0].magical is True
        assert c2_restored.attacks[0].silvered is False
