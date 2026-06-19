"""
Tests for the exhaustion engine — DnD 5e Exhaustion special state.

Covers:
- The 6-level registry and cumulative effect resolution.
- Object state helpers (get/set/add/reduce, clamping, death at 6).
- Effective speed (halved at 2, zero at 5) and effective max HP (halved at 4),
  including cumulative stacking (level 4 still halves speed).
- Cumulative disadvantage queries (ability checks 1+, attacks/saves 3+).
- Serialisation helpers (level_effects / describe).
"""
import pytest

from app.engine import exhaustion as exh
from app.engine.combat import Combatant, Attack


# --------------------------------------------------------------------------- #
# Stub object (so we don't depend on the Combatant machinery for pure tests)
# --------------------------------------------------------------------------- #

class Stub:
    def __init__(self, exhaustion=0):
        self.exhaustion = exhaustion


# --------------------------------------------------------------------------- #
# Registry / level rules
# --------------------------------------------------------------------------- #

class TestRegistry:
    def test_six_levels_plus_zero(self):
        assert exh.MAX_EXHAUSTION == 6
        for level in range(0, 7):
            rules = exh.level_rules(level)
            assert rules.level == level

    def test_level_descriptions(self):
        assert "ability checks" in exh.level_rules(1).description.lower()
        assert "speed" in exh.level_rules(2).description.lower()
        desc3 = exh.level_rules(3).description.lower()
        assert "attack" in desc3 and "saving" in desc3
        assert "hit point" in exh.level_rules(4).description.lower()
        assert "0" in exh.level_rules(5).description
        assert "death" in exh.level_rules(6).description.lower()

    def test_level_rules_clamps(self):
        assert exh.level_rules(-3).level == 0
        assert exh.level_rules(99).level == 6


# --------------------------------------------------------------------------- #
# State helpers
# --------------------------------------------------------------------------- #

class TestStateHelpers:
    def test_get_default_zero(self):
        obj = object()  # no exhaustion attr
        assert exh.get_exhaustion(obj) == 0

    def test_set_and_get(self):
        s = Stub()
        assert exh.set_exhaustion(s, 3) == 3
        assert exh.get_exhaustion(s) == 3

    def test_set_clamps(self):
        s = Stub()
        assert exh.set_exhaustion(s, -5) == 0
        assert exh.set_exhaustion(s, 100) == 6

    def test_add(self):
        s = Stub(2)
        assert exh.add_exhaustion(s, 1) == 3
        assert exh.add_exhaustion(s, 10) == 6  # caps at 6

    def test_add_negative_is_noop(self):
        s = Stub(2)
        assert exh.add_exhaustion(s, -3) == 2

    def test_reduce(self):
        s = Stub(4)
        assert exh.reduce_exhaustion(s, 1) == 3
        assert exh.reduce_exhaustion(s, 10) == 0  # floors at 0

    def test_reduce_negative_is_noop(self):
        s = Stub(4)
        assert exh.reduce_exhaustion(s, -2) == 4


# --------------------------------------------------------------------------- #
# Death
# --------------------------------------------------------------------------- #

class TestDeath:
    @pytest.mark.parametrize("level,dead", [(0, False), (1, False), (5, False), (6, True), (7, True)])
    def test_is_dead(self, level, dead):
        assert exh.is_dead(Stub(level)) is dead


# --------------------------------------------------------------------------- #
# Cumulative disadvantage queries
# --------------------------------------------------------------------------- #

class TestDisadvantageQueries:
    def test_ability_checks_from_level_1(self):
        for lvl in range(1, 6):
            assert exh.disadvantage_ability_checks(Stub(lvl)) is True
        assert exh.disadvantage_ability_checks(Stub(0)) is False

    def test_attack_rolls_from_level_3(self):
        assert exh.disadvantage_attack_rolls(Stub(0)) is False
        assert exh.disadvantage_attack_rolls(Stub(1)) is False
        assert exh.disadvantage_attack_rolls(Stub(2)) is False
        assert exh.disadvantage_attack_rolls(Stub(3)) is True
        assert exh.disadvantage_attack_rolls(Stub(5)) is True

    def test_saving_throws_from_level_3(self):
        assert exh.disadvantage_saving_throws(Stub(2)) is False
        assert exh.disadvantage_saving_throws(Stub(3)) is True


# --------------------------------------------------------------------------- #
# Effective speed / max HP (cumulative)
# --------------------------------------------------------------------------- #

class TestEffectiveStats:
    def test_speed_untouched_below_2(self):
        assert exh.effective_speed(30, 0) == 30
        assert exh.effective_speed(30, 1) == 30

    def test_speed_halved_at_2(self):
        assert exh.effective_speed(30, 2) == 15
        assert exh.effective_speed(25, 2) == 12  # rounds down

    def test_speed_zero_at_5_and_6(self):
        assert exh.effective_speed(30, 5) == 0
        assert exh.effective_speed(30, 6) == 0

    def test_speed_stacks_at_level_4(self):
        # Level 4 grants max-HP halving AND inherits level 2's speed halving.
        assert exh.effective_speed(30, 3) == 15
        assert exh.effective_speed(30, 4) == 15

    def test_max_hp_untouched_below_4(self):
        for lvl in range(0, 4):
            assert exh.effective_max_hp(40, lvl) == 40

    def test_max_hp_halved_at_4_plus(self):
        assert exh.effective_max_hp(40, 4) == 20
        assert exh.effective_max_hp(45, 4) == 22  # rounds down
        assert exh.effective_max_hp(40, 6) == 20

    def test_max_hp_never_below_one(self):
        assert exh.effective_max_hp(1, 4) == 1
        assert exh.effective_max_hp(0, 4) == 1


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #

class TestSerialisation:
    def test_level_effects_zero(self):
        eff = exh.level_effects(0)
        assert eff["level"] == 0
        assert eff["dead"] is False
        assert eff["active_effects"] == []

    def test_level_effects_cumulative(self):
        eff = exh.level_effects(3)
        assert eff["level"] == 3
        assert eff["disadvantage_attack_rolls"] is True
        assert eff["disadvantage_saving_throws"] is True
        assert eff["disadvantage_ability_checks"] is True  # inherited from 1
        assert eff["speed_divisor"] == 2  # inherited from 2
        assert eff["max_hp_halved"] is False
        assert len(eff["active_effects"]) == 3  # levels 1, 2, 3

    def test_level_effects_six_is_death(self):
        eff = exh.level_effects(6)
        assert eff["dead"] is True
        assert eff["max_hp_halved"] is True
        assert eff["speed_divisor"] == 0

    def test_level_effects_clamps(self):
        assert exh.level_effects(-2)["level"] == 0
        assert exh.level_effects(9)["level"] == 6

    def test_describe(self):
        d = exh.describe(Stub(2))
        assert d["exhaustion"] == 2
        assert d["speed_divisor"] == 2


# --------------------------------------------------------------------------- #
# Combatant integration (Combatant carries exhaustion)
# --------------------------------------------------------------------------- #

class TestCombatantIntegration:
    def _combatant(self, **kw):
        base = dict(
            id="hero", name="Hero", side="player", max_hp=40, armor_class=16,
            speed=30, exhaustion=0,
            attacks=[Attack(name="Sword", attack_bonus=5, damage_dice_sides=8)],
        )
        base.update(kw)
        return Combatant(**base)

    def test_default_exhaustion_zero(self):
        c = self._combatant()
        assert c.exhaustion == 0
        assert c.is_alive

    def test_exhaustion_six_kills(self):
        c = self._combatant(exhaustion=6)
        assert c.is_alive is False
        assert exh.is_dead(c)

    def test_effective_speed_halved(self):
        assert self._combatant(exhaustion=2).effective_speed == 15
        assert self._combatant(exhaustion=5).effective_speed == 0

    def test_effective_max_hp_halved(self):
        assert self._combatant(exhaustion=3).effective_max_hp == 40
        assert self._combatant(exhaustion=4).effective_max_hp == 20

    def test_heal_capped_by_effective_max(self):
        c = self._combatant(max_hp=40, exhaustion=4)
        c.current_hp = 5
        c.heal(100)
        # Halved max (20), not full max (40).
        assert c.current_hp == 20

    def test_serialization_roundtrip(self):
        c = self._combatant(exhaustion=3)
        data = c.to_dict()
        assert data["exhaustion"] == 3
        c2 = Combatant.from_dict(data)
        assert c2.exhaustion == 3
        assert c2.effective_speed == 15


# --------------------------------------------------------------------------- #
# resolve_attack integration — exhaustion 3+ imposes attack disadvantage
# --------------------------------------------------------------------------- #

class TestResolveAttackIntegration:
    def _make(self, **kw):
        from app.engine.combat import Attack
        base = dict(
            id="hero", name="Hero", side="player", max_hp=40, armor_class=16,
            speed=30, exhaustion=0,
            attacks=[Attack(name="Sword", attack_bonus=5, damage_dice_sides=8)],
        )
        base.update(kw)
        return Combatant(**base)

    def test_exhausted_attacker_rolls_disadvantage(self, monkeypatch):
        from app.engine import combat as combat_mod
        from app.engine.dice import RollResult

        captured = {}
        def spy(modifier=0, advantage=False, disadvantage=False):
            captured["adv"] = advantage
            captured["dis"] = disadvantage
            return RollResult(rolls=[15], modifier=modifier,
                              total=15 + modifier, description="spy")
        monkeypatch.setattr(combat_mod, "roll_d20", spy)

        attacker = self._make(exhaustion=3)
        target = Combatant(id="goblin", name="Goblin", side="enemy",
                           max_hp=20, armor_class=10,
                           attacks=[Attack(name="Claw", attack_bonus=4, damage_dice_sides=4)])
        enc = combat_mod.Encounter([attacker, target])
        enc.resolve_attack(attacker, target, attacker.attacks[0])

        assert captured["dis"] is True
        assert captured["adv"] is False

    def test_mildly_exhausted_attacker_no_disadvantage(self, monkeypatch):
        from app.engine import combat as combat_mod
        from app.engine.dice import RollResult

        captured = {}
        def spy(modifier=0, advantage=False, disadvantage=False):
            captured["dis"] = disadvantage
            return RollResult(rolls=[15], modifier=modifier,
                              total=15 + modifier, description="spy")
        monkeypatch.setattr(combat_mod, "roll_d20", spy)

        attacker = self._make(exhaustion=2)  # only ability-check disadv, not attack
        target = Combatant(id="goblin", name="Goblin", side="enemy",
                           max_hp=20, armor_class=10,
                           attacks=[Attack(name="Claw", attack_bonus=4, damage_dice_sides=4)])
        enc = combat_mod.Encounter([attacker, target])
        enc.resolve_attack(attacker, target, attacker.attacks[0])
        assert captured["dis"] is False


# --------------------------------------------------------------------------- #
# Saving-throw integration — exhaustion 3+ imposes save disadvantage
# --------------------------------------------------------------------------- #

class TestSavingThrowIntegration:
    def _char(self):
        class _C:
            level = 5
            strength = 14
            dexterity = 12
            constitution = 14
            intelligence = 10
            wisdom = 10
            charisma = 10
            classes = '{"fighter": 5}'
            char_class = "fighter"
            feats = "[]"
            classes_dict = {"fighter": 5}
            primary_class = "fighter"
        return _C()

    def test_check_save_disadvantage_from_exhaustion(self):
        from app.engine import saving_throws as st
        assert st.check_save_disadvantage("constitution", [], exhaustion=3) is True
        assert st.check_save_disadvantage("constitution", [], exhaustion=2) is False

    def test_exhausted_save_rolls_disadvantage(self, monkeypatch):
        from app.engine import saving_throws as st
        from app.engine.dice import RollResult

        captured = {}
        def spy(modifier=0, advantage=False, disadvantage=False):
            captured["dis"] = disadvantage
            captured["adv"] = advantage
            return RollResult(rolls=[12], modifier=modifier,
                              total=12 + modifier, description="spy")
        monkeypatch.setattr(st, "roll_d20", spy)

        st.roll_saving_throw("constitution", self._char(), dc=13, exhaustion=3)
        assert captured["dis"] is True
        assert captured["adv"] is False

    def test_non_exhausted_save_no_disadvantage(self, monkeypatch):
        from app.engine import saving_throws as st
        from app.engine.dice import RollResult

        captured = {}
        def spy(modifier=0, advantage=False, disadvantage=False):
            captured["dis"] = disadvantage
            return RollResult(rolls=[12], modifier=modifier,
                              total=12 + modifier, description="spy")
        monkeypatch.setattr(st, "roll_d20", spy)

        st.roll_saving_throw("constitution", self._char(), dc=13, exhaustion=2)
        assert captured["dis"] is False


# --------------------------------------------------------------------------- #
# Rest integration — long rest reduces exhaustion by one level
# --------------------------------------------------------------------------- #

class TestRestIntegration:
    def test_long_rest_reduces_exhaustion(self):
        from app.engine.rest import long_rest
        result = long_rest("fighter", 5, 20, 40, 1, is_caster=False, exhaustion=3)
        assert result.exhaustion_before == 3
        assert result.exhaustion_after == 2
        assert result.exhaustion_reduced is True
        assert "exhaustion" in result.message.lower()

    def test_long_rest_no_exhaustion_no_recovery(self):
        from app.engine.rest import long_rest
        result = long_rest("fighter", 5, 20, 40, 1, is_caster=False, exhaustion=0)
        assert result.exhaustion_reduced is False
        assert result.exhaustion_after == 0

    def test_long_rest_fatal_level_cannot_recover(self):
        from app.engine.rest import long_rest
        result = long_rest("fighter", 5, 20, 40, 1, is_caster=False, exhaustion=6)
        assert result.exhaustion_reduced is False
        assert result.exhaustion_after == 6

    def test_long_rest_dict_serialisation(self):
        from app.engine.rest import long_rest
        d = long_rest("fighter", 5, 20, 40, 1, is_caster=False, exhaustion=2).to_dict()
        assert d["exhaustion_before"] == 2
        assert d["exhaustion_after"] == 1
        assert d["exhaustion_reduced"] is True
