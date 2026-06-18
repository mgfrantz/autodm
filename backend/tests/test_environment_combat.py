"""
Tests wiring the environment engine into the combat engine.

The environment engine (``app.engine.environment``) describes how weather,
lighting, and terrain reshape attack rolls. These tests verify that
``Encounter.resolve_attack`` actually applies those modifiers, that the 5e
"unseen attackers and targets" mutual-blindness rule cancels to a straight
roll in scene-wide darkness, and that the encounter persists its scene
environment across serialization.
"""
import pytest

from app.engine.combat import Attack, Combatant, Encounter
from app.engine import dice
from app.engine.environment import (
    Environment,
    combat_modifiers,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def make_attacker(name: str = "Hero", ranged: bool = False) -> Combatant:
    return Combatant(
        id="hero",
        name=name,
        side="player",
        max_hp=30,
        armor_class=16,
        initiative_bonus=3,
        attacks=[
            Attack(
                name="Strike",
                attack_bonus=5,
                damage_dice_count=1,
                damage_dice_sides=8,
                damage_bonus=3,
                ranged=ranged,
            )
        ],
    )


def make_target() -> Combatant:
    return Combatant(
        id="goblin",
        name="Goblin",
        side="enemy",
        max_hp=20,
        armor_class=15,
        initiative_bonus=2,
        attacks=[Attack(name="Scimitar", attack_bonus=4, damage_dice_count=1, damage_dice_sides=6, damage_bonus=2)],
    )


def fixed_die(value: int):
    """Return a randint replacement that always yields ``value``."""
    def _roll(_lo, _hi):
        return value
    return _roll


class RollSpy:
    """Wraps ``roll_d20`` to capture the advantage/disadvantage flags used.

    Delegates to the real implementation so the attack resolves normally.
    """

    def __init__(self, real_fn):
        self._real = real_fn
        self.calls: list[dict] = []

    def __call__(self, *args, **kwargs):
        self.calls.append({
            "modifier": kwargs.get("modifier", args[0] if args else 0),
            "advantage": kwargs.get("advantage", False),
            "disadvantage": kwargs.get("disadvantage", False),
        })
        return self._real(*args, **kwargs)


def _start_encounter(monkeypatch, attacker: Combatant, target: Combatant) -> Encounter:
    """Build + start an encounter with a deterministic initiative roll."""
    monkeypatch.setattr(dice.random, "randint", fixed_die(10))
    enc = Encounter([attacker, target])
    enc.start()
    return enc


def _resolve_with_spy(monkeypatch, enc: Encounter, attacker, target) -> tuple:
    """Resolve an attack while spying on roll_d20; return (result, spy)."""
    monkeypatch.setattr(dice.random, "randint", fixed_die(12))  # hit die, damage
    import app.engine.combat as combat_mod
    real_roll = combat_mod.roll_d20
    spy = RollSpy(real_roll)
    monkeypatch.setattr(combat_mod, "roll_d20", spy)
    result = enc.resolve_attack(attacker, target, attacker.attacks[0])
    return result, spy


# --------------------------------------------------------------------------- #
# combat_modifiers — the new unseen-attacker advantage field
# --------------------------------------------------------------------------- #

class TestCombatModifiersUnseenAdvantage:
    def test_darkness_grants_unseen_advantage(self):
        mods = combat_modifiers(Environment(light="darkness"), attack_is_ranged=False)
        assert mods.attacker_unseen_advantage
        assert mods.attacker_cannot_see_target  # symmetric mutual blindness

    def test_fog_grants_unseen_advantage(self):
        mods = combat_modifiers(Environment(weather="fog"), attack_is_ranged=True)
        assert mods.attacker_unseen_advantage
        assert mods.attacker_cannot_see_target

    def test_clear_no_unseen_advantage(self):
        mods = combat_modifiers(Environment(), attack_is_ranged=False)
        assert not mods.attacker_unseen_advantage

    def test_wind_no_unseen_advantage(self):
        # Strong wind obscures nothing — only ranged attacks suffer.
        mods = combat_modifiers(Environment(weather="strong_wind"), attack_is_ranged=True)
        assert not mods.attacker_unseen_advantage
        assert mods.attacker_ranged_disadvantage

    def test_unseen_advantage_serializes(self):
        d = combat_modifiers(Environment(light="darkness")).to_dict()
        assert d["attacker_unseen_advantage"] is True


# --------------------------------------------------------------------------- #
# Encounter.resolve_attack — environment integration
# --------------------------------------------------------------------------- #

class TestEnvironmentInResolveAttack:
    def test_wind_disadvantages_ranged_attack(self, monkeypatch):
        attacker = make_attacker(ranged=True)
        target = make_target()
        enc = _start_encounter(monkeypatch, attacker, target)
        enc.set_environment(Environment(weather="strong_wind"))

        _, spy = _resolve_with_spy(monkeypatch, enc, attacker, target)

        assert len(spy.calls) == 1
        call = spy.calls[0]
        assert call["disadvantage"] is True
        assert call["advantage"] is False

    def test_wind_does_not_affect_melee(self, monkeypatch):
        attacker = make_attacker(ranged=False)
        target = make_target()
        enc = _start_encounter(monkeypatch, attacker, target)
        enc.set_environment(Environment(weather="strong_wind"))

        _, spy = _resolve_with_spy(monkeypatch, enc, attacker, target)

        assert len(spy.calls) == 1
        call = spy.calls[0]
        assert call["advantage"] is False
        assert call["disadvantage"] is False

    def test_darkness_melee_is_straight_roll(self, monkeypatch):
        # Scene-wide darkness: attacker can't see target (disadv) AND is unseen
        # by the target (adv) → cancels to a straight roll (5e mutual blindness).
        attacker = make_attacker(ranged=False)
        target = make_target()
        enc = _start_encounter(monkeypatch, attacker, target)
        enc.set_environment(Environment(light="darkness"))

        _, spy = _resolve_with_spy(monkeypatch, enc, attacker, target)

        call = spy.calls[0]
        # Net straight roll: advantage and disadvantage cancel inside roll_d20,
        # which happens when the two flags are equal (both True or both False).
        assert call["advantage"] == call["disadvantage"]

    def test_darkness_ranged_is_straight_roll(self, monkeypatch):
        attacker = make_attacker(ranged=True)
        target = make_target()
        enc = _start_encounter(monkeypatch, attacker, target)
        enc.set_environment(Environment(light="darkness"))

        _, spy = _resolve_with_spy(monkeypatch, enc, attacker, target)

        call = spy.calls[0]
        assert call["advantage"] == call["disadvantage"]

    def test_fog_ranged_is_straight_roll(self, monkeypatch):
        attacker = make_attacker(ranged=True)
        target = make_target()
        enc = _start_encounter(monkeypatch, attacker, target)
        enc.set_environment(Environment(weather="fog"))

        _, spy = _resolve_with_spy(monkeypatch, enc, attacker, target)

        call = spy.calls[0]
        assert call["advantage"] == call["disadvantage"]

    def test_storm_ranged_is_straight_roll(self, monkeypatch):
        # A storm is heavily obscured (→ mutual blindness) and also imposes
        # ranged disadvantage. 5e: any advantage cancels ALL disadvantage, so
        # the net result is a straight roll (advantage == disadvantage).
        attacker = make_attacker(ranged=True)
        target = make_target()
        enc = _start_encounter(monkeypatch, attacker, target)
        enc.set_environment(Environment(weather="storm"))

        _, spy = _resolve_with_spy(monkeypatch, enc, attacker, target)

        call = spy.calls[0]
        assert call["advantage"] == call["disadvantage"]

    def test_environment_param_overrides_encounter_scene(self, monkeypatch):
        # Encounter scene is clear, but we resolve a single attack in wind.
        attacker = make_attacker(ranged=True)
        target = make_target()
        enc = _start_encounter(monkeypatch, attacker, target)
        # No environment on the encounter itself.
        assert enc.environment is None

        monkeypatch.setattr(dice.random, "randint", fixed_die(12))
        import app.engine.combat as combat_mod
        spy = RollSpy(combat_mod.roll_d20)
        monkeypatch.setattr(combat_mod, "roll_d20", spy)
        enc.resolve_attack(
            attacker, target, attacker.attacks[0],
            environment=Environment(weather="strong_wind"),
        )

        call = spy.calls[0]
        assert call["disadvantage"] is True
        assert call["advantage"] is False

    def test_no_environment_is_straight_roll(self, monkeypatch):
        # Backward compatibility: no environment means no situational modifiers.
        attacker = make_attacker(ranged=True)
        target = make_target()
        enc = _start_encounter(monkeypatch, attacker, target)

        _, spy = _resolve_with_spy(monkeypatch, enc, attacker, target)

        call = spy.calls[0]
        assert call["advantage"] is False
        assert call["disadvantage"] is False

    def test_wind_ranged_description_notes_disruption(self, monkeypatch):
        attacker = make_attacker(ranged=True)
        target = make_target()
        enc = _start_encounter(monkeypatch, attacker, target)
        enc.set_environment(Environment(weather="strong_wind"))

        result, _ = _resolve_with_spy(monkeypatch, enc, attacker, target)

        assert "wind disrupts the shot" in result.description

    def test_explicit_advantage_not_clobbered_by_clear_env(self, monkeypatch):
        # Caller-requested advantage survives a clear environment.
        attacker = make_attacker(ranged=False)
        target = make_target()
        enc = _start_encounter(monkeypatch, attacker, target)
        enc.set_environment(Environment())  # clear midday

        monkeypatch.setattr(dice.random, "randint", fixed_die(12))
        import app.engine.combat as combat_mod
        spy = RollSpy(combat_mod.roll_d20)
        monkeypatch.setattr(combat_mod, "roll_d20", spy)
        enc.resolve_attack(attacker, target, attacker.attacks[0], advantage=True)

        call = spy.calls[0]
        assert call["advantage"] is True
        assert call["disadvantage"] is False


# --------------------------------------------------------------------------- #
# Serialization round-trip
# --------------------------------------------------------------------------- #

class TestEnvironmentSerialization:
    def test_environment_round_trips_through_to_dict(self):
        attacker = make_attacker()
        target = make_target()
        enc = Encounter([attacker, target])
        enc.set_environment(Environment(light="darkness", weather="heavy_rain"))

        data = enc.to_dict()
        assert data["environment"] is not None
        assert data["environment"]["light"] == "darkness"
        assert data["environment"]["weather"] == "heavy_rain"

        restored = Encounter.from_dict(data)
        assert restored.environment is not None
        assert restored.environment.light == "darkness"
        assert restored.environment.weather == "heavy_rain"

    def test_legacy_encounter_without_environment_loads(self):
        # An encounter serialized before this feature had no environment key.
        legacy = {
            "combatants": [],
            "turn_order_ids": [],
            "current_turn_index": 0,
            "round_number": 1,
            "started": True,
            "log": [],
            "help_advantage_targets": [],
        }
        enc = Encounter.from_dict(legacy)
        assert enc.environment is None

    def test_set_environment_none_clears_scene(self):
        enc = Encounter([make_attacker(), make_target()])
        enc.set_environment(Environment(light="darkness"))
        assert enc.environment is not None
        enc.set_environment(None)
        assert enc.environment is None

    def test_restored_environment_still_drives_modifiers(self, monkeypatch):
        # Environment restored from a save must still affect attacks.
        attacker = make_attacker(ranged=True)
        target = make_target()
        enc = Encounter([attacker, target])
        enc.set_environment(Environment(weather="strong_wind"))
        data = enc.to_dict()
        restored = Encounter.from_dict(data)

        _, spy = _resolve_with_spy(monkeypatch, restored, attacker, target)
        call = spy.calls[0]
        assert call["disadvantage"] is True
