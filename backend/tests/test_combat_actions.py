"""
Tests for the combat-actions engine: Grapple, Shove, Dash, Disengage, Dodge,
Help, Escape, Unarmed Strike, Two-Weapon Fighting, Opportunity Attack, the
dispatcher, turn-lifecycle integration, and serialization.
"""
import pytest

from app.engine import combat_actions as ca
from app.engine import dice
from app.engine.combat import Attack, Combatant, Encounter


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
def make_strong_hero() -> Combatant:
    return Combatant(
        id="hero",
        name="Hero",
        side="player",
        max_hp=30,
        armor_class=16,
        initiative_bonus=2,
        speed=30,
        strength=18,
        dexterity=12,
        athletics_bonus=6,   # +4 Str, +2 prof
        acrobatics_bonus=1,
        attacks=[Attack(name="Longsword", attack_bonus=7, damage_dice_count=1,
                        damage_dice_sides=8, damage_bonus=4)],
    )


def make_nimble_rogue() -> Combatant:
    # Acrobatics bonus high so escaping/contesting favours Dex.
    return Combatant(
        id="rogue",
        name="Rogue",
        side="enemy",
        max_hp=20,
        armor_class=15,
        initiative_bonus=4,
        speed=30,
        strength=10,
        dexterity=18,
        athletics_bonus=0,
        acrobatics_bonus=6,  # +4 Dex, +2 prof (equal to hero athletics)
        attacks=[Attack(name="Dagger", attack_bonus=7, damage_dice_count=1,
                        damage_dice_sides=4, damage_bonus=4)],
    )


def make_goblin() -> Combatant:
    return Combatant(
        id="goblin1",
        name="Goblin",
        side="enemy",
        max_hp=7,
        armor_class=13,
        initiative_bonus=2,
        speed=30,
        strength=8,
        dexterity=14,
        athletics_bonus=-1,
        acrobatics_bonus=2,
        attacks=[Attack(name="Scimitar", attack_bonus=4, damage_dice_count=1,
                        damage_dice_sides=6, damage_bonus=2)],
    )


def make_huge_ogre() -> Combatant:
    return Combatant(
        id="ogre",
        name="Ogre",
        side="enemy",
        max_hp=60,
        armor_class=12,
        initiative_bonus=-1,
        speed=40,
        size="large",
        strength=20,
        dexterity=8,
        athletics_bonus=8,
        acrobatics_bonus=-1,
        attacks=[Attack(name="Greatclub", attack_bonus=6, damage_dice_count=2,
                        damage_dice_sides=8, damage_bonus=4)],
    )


def fixed_die(value):
    """Return a randint replacement that always yields ``value``."""
    def _roll(_lo, _hi):
        return value
    return _roll


def started_encounter(*combatants) -> Encounter:
    """Build and start an encounter with the given combatants."""
    enc = Encounter(list(combatants))
    enc.start()
    return enc


def spy_roll_d20(monkeypatch):
    """Replace combat.roll_d20 with a recorder that delegates to the real fn.

    Returns a list whose dicts capture the advantage/disadvantage flags per call.
    """
    from app.engine import combat as combat_mod
    real = combat_mod.roll_d20
    calls = []

    def _spy(modifier=0, advantage=False, disadvantage=False):
        calls.append({
            "modifier": modifier,
            "advantage": advantage,
            "disadvantage": disadvantage,
        })
        return real(modifier=modifier, advantage=advantage, disadvantage=disadvantage)

    monkeypatch.setattr(combat_mod, "roll_d20", _spy)
    return calls


# --------------------------------------------------------------------------- #
# Catalogue / dispatcher sanity
# --------------------------------------------------------------------------- #
class TestCatalogue:
    def test_list_actions_has_all_keys(self):
        actions = {a["key"] for a in ca.list_actions()}
        assert actions == {
            "grapple", "shove", "dash", "disengage", "dodge", "help",
            "unarmed-strike", "off-hand-attack", "escape", "opportunity-attack",
        }

    def test_list_actions_has_descriptions(self):
        for a in ca.list_actions():
            assert a["name"]
            assert a["description"]
            assert a["cost"] in {"one action", "one attack", "bonus action", "reaction"}
            assert isinstance(a["requires_target"], bool)

    def test_perform_unknown_action_raises(self):
        enc = started_encounter(make_strong_hero(), make_goblin())
        with pytest.raises(ValueError):
            ca.perform_action(enc, enc.combatants[0], "fly")


# --------------------------------------------------------------------------- #
# Size helpers
# --------------------------------------------------------------------------- #
class TestSizes:
    def test_size_category_defaults_to_medium(self):
        assert ca.size_category("nonsense") == 2
        assert ca.size_category("huge") == 4

    def test_size_difference(self):
        assert ca.size_difference(make_huge_ogre(), make_goblin()) == 1
        assert ca.size_difference(make_goblin(), make_huge_ogre()) == -1


# --------------------------------------------------------------------------- #
# Grapple
# --------------------------------------------------------------------------- #
class TestGrapple:
    def test_grapple_success_applies_condition(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        hero, goblin = enc.combatants[0], enc.combatants[1]
        result = ca.attempt_grapple(enc, hero, goblin)
        assert result.success
        assert goblin.has_condition("grappled")
        assert goblin.grappled_by == "hero"
        # Grappled creature has speed 0.
        assert goblin.effective_speed == 0

    def test_grapple_fail_does_not_apply(self, monkeypatch):
        # Same die for both; goblin acrobatics(2) < hero athletics(6) -> hero
        # still wins on a tie, so weaken the hero instead.
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_goblin(), make_strong_hero())
        goblin, hero = enc.combatants[0], enc.combatants[1]
        # Goblin athletics(-1) vs hero acrobatics(1) -> hero defends better.
        result = ca.attempt_grapple(enc, goblin, hero)
        assert not result.success
        assert not hero.has_condition("grappled")
        assert hero.grappled_by is None

    def test_grapple_tie_goes_to_defender(self, monkeypatch):
        # Equal bonuses + equal die => tie => attacker does not win.
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        a = Combatant(id="a", name="A", side="player", max_hp=10, armor_class=10,
                      athletics_bonus=3)
        b = Combatant(id="b", name="B", side="enemy", max_hp=10, armor_class=10,
                      acrobatics_bonus=3)
        enc = started_encounter(a, b)
        result = ca.attempt_grapple(enc, a, b)
        assert not result.success
        assert not b.has_condition("grappled")

    def test_grapple_too_large(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_goblin(), make_huge_ogre())
        goblin, ogre = enc.combatants[0], enc.combatants[1]
        # Goblin (small) vs ogre (large): one category larger is OK; make ogre huge.
        ogre.size = "huge"
        result = ca.attempt_grapple(enc, goblin, ogre)
        assert not result.success
        assert "too large" in result.description.lower()

    def test_grapple_no_free_hand(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        result = ca.attempt_grapple(enc, enc.combatants[0], enc.combatants[1], free_hand=False)
        assert not result.success
        assert "free hand" in result.description.lower()

    def test_grapple_already_grappled_by_you(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        hero, goblin = enc.combatants[0], enc.combatants[1]
        assert ca.attempt_grapple(enc, hero, goblin).success
        second = ca.attempt_grapple(enc, hero, goblin)
        assert second.success
        assert "already" in second.description.lower()


# --------------------------------------------------------------------------- #
# Shove
# --------------------------------------------------------------------------- #
class TestShove:
    def test_shove_prone_success(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        hero, goblin = enc.combatants[0], enc.combatants[1]
        result = ca.attempt_shove(enc, hero, goblin, option="prone")
        assert result.success
        assert goblin.has_condition("prone")

    def test_shove_push_success(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        hero, goblin = enc.combatants[0], enc.combatants[1]
        result = ca.attempt_shove(enc, hero, goblin, option="push")
        assert result.success
        assert "shoved 5 ft" in result.description

    def test_shove_fail(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_goblin(), make_strong_hero())
        goblin, hero = enc.combatants[0], enc.combatants[1]
        result = ca.attempt_shove(enc, goblin, hero)
        assert not result.success
        assert not hero.has_condition("prone")

    def test_shove_invalid_option(self):
        enc = started_encounter(make_strong_hero(), make_goblin())
        result = ca.attempt_shove(enc, enc.combatants[0], enc.combatants[1], option="launch")
        assert not result.success


# --------------------------------------------------------------------------- #
# Escape grapple
# --------------------------------------------------------------------------- #
class TestEscape:
    def test_escape_not_grappled(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        result = ca.escape_grapple(enc, enc.combatants[0])
        assert not result.success

    def test_escape_success_breaks_free(self, monkeypatch):
        # Equal bonuses (rogue acr 6 == hero ath 6); dice decide each contest.
        # Sequence: 2x initiative, grapple(atk,def), escape(atk,def).
        rolls = iter([10, 10, 20, 1, 20, 1])
        monkeypatch.setattr(dice.random, "randint", lambda _a, _b: next(rolls))
        enc = started_encounter(make_strong_hero(), make_nimble_rogue())
        hero, rogue = enc.combatants[0], enc.combatants[1]
        assert ca.attempt_grapple(enc, hero, rogue).success  # 26 vs 7
        assert rogue.has_condition("grappled")
        result = ca.escape_grapple(enc, rogue)  # 26 vs 7
        assert result.success
        assert not rogue.has_condition("grappled")
        assert rogue.grappled_by is None

    def test_escape_fail_stays_grappled(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        hero, goblin = enc.combatants[0], enc.combatants[1]
        assert ca.attempt_grapple(enc, hero, goblin).success
        # Goblin escape best is acrobatics(2) vs hero athletics(6) -> goblin loses.
        result = ca.escape_grapple(enc, goblin)
        assert not result.success
        assert goblin.has_condition("grappled")


# --------------------------------------------------------------------------- #
# Movement actions: Dash, Disengage, Dodge
# --------------------------------------------------------------------------- #
class TestMovementActions:
    def test_dash_grants_extra_movement(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        hero = enc.combatants[0]
        before = hero.available_movement
        result = ca.dash(enc, hero)
        assert result.success
        assert hero.bonus_movement == 30
        assert hero.available_movement == before + 30

    def test_dash_no_movement_when_speed_zero(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        hero = enc.combatants[0]
        hero.add_condition("restrained")  # speed 0
        result = ca.dash(enc, hero)
        assert not result.success
        assert hero.bonus_movement == 0

    def test_disengage_sets_flag(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        hero = enc.combatants[0]
        result = ca.disengage(enc, hero)
        assert result.success
        assert hero.disengaging is True

    def test_dodge_sets_flag(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        hero = enc.combatants[0]
        result = ca.dodge(enc, hero)
        assert result.success
        assert hero.dodging is True


# --------------------------------------------------------------------------- #
# Dodge -> resolve_attack disadvantage integration
# --------------------------------------------------------------------------- #
class TestDodgeIntegration:
    def test_dodge_imposes_disadvantage_on_attack(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_goblin(), make_strong_hero())
        goblin, hero = enc.combatants[0], enc.combatants[1]
        calls = spy_roll_d20(monkeypatch)
        ca.dodge(enc, hero)
        enc.resolve_attack(goblin, hero, goblin.attacks[0])
        assert calls, "roll_d20 should have been called"
        assert calls[-1]["disadvantage"] is True

    def test_dodge_no_effect_when_incapacitated(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_goblin(), make_strong_hero())
        goblin, hero = enc.combatants[0], enc.combatants[1]
        calls = spy_roll_d20(monkeypatch)
        ca.dodge(enc, hero)
        hero.add_condition("stunned")  # incapacitated -> dodge useless
        enc.resolve_attack(goblin, hero, goblin.attacks[0])
        assert calls[-1]["disadvantage"] is False

    def test_dodge_clears_at_start_of_own_next_turn(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        # Hero first in order (init 12) then goblin (init 12, lower bonus).
        enc = started_encounter(make_strong_hero(), make_goblin())
        hero, goblin = enc.combatants[0], enc.combatants[1]
        ca.dodge(enc, hero)
        assert hero.dodging is True
        # Goblin's turn (hero.end_turn runs, dodge persists).
        enc.next_turn()
        assert hero.dodging is True
        # Back to hero's turn -> start_turn clears dodge.
        enc.next_turn()
        assert hero.dodging is False


# --------------------------------------------------------------------------- #
# Disengage -> turn lifecycle + opportunity attack
# --------------------------------------------------------------------------- #
class TestDisengageLifecycle:
    def test_disengage_clears_at_end_of_turn(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        hero = enc.combatants[0]
        ca.disengage(enc, hero)
        assert hero.disengaging is True
        enc.next_turn()  # hero's turn ends -> end_turn clears disengage
        assert hero.disengaging is False


# --------------------------------------------------------------------------- #
# Help action
# --------------------------------------------------------------------------- #
class TestHelp:
    def test_help_grants_advantage_then_consumed(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        hero, goblin = enc.combatants[0], enc.combatants[1]
        calls = spy_roll_d20(monkeypatch)
        result = ca.help_ally(enc, hero, goblin)
        assert result.success
        assert goblin.id in enc.help_advantage_targets
        # First attack against goblin gets advantage and consumes the help.
        enc.resolve_attack(hero, goblin, hero.attacks[0])
        assert calls[-1]["advantage"] is True
        assert goblin.id not in enc.help_advantage_targets

    def test_help_without_target_is_ability_check(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        result = ca.help_ally(enc, enc.combatants[0], None)
        assert result.success
        assert result.details["aid_type"] == "ability_check"


# --------------------------------------------------------------------------- #
# Unarmed strike & two-weapon fighting
# --------------------------------------------------------------------------- #
class TestStrikes:
    def test_unarmed_strike_damage_is_one_plus_str(self):
        # d1 always rolls 1 (real randint), so damage = 1 + damage_bonus.
        strike = ca.unarmed_strike(attack_bonus=5, str_mod=3)
        assert strike.roll_damage() == 4  # 1 + 3
        assert strike.damage_type == "bludgeoning"

    def test_unarmed_strike_no_negative_floor(self):
        strike = ca.unarmed_strike(attack_bonus=5, str_mod=-2)
        # max(ability, 0) -> 0; damage = 1 + 0 = 1
        assert strike.roll_damage() == 1

    def test_off_hand_attack_omits_ability_mod(self, monkeypatch):
        # Sequence: 2x initiative, attack d20=15 (hit), damage d4=2; no ability mod.
        rolls = iter([10, 10, 15, 2])
        monkeypatch.setattr(dice.random, "randint", lambda _a, _b: next(rolls))
        enc = started_encounter(make_strong_hero(), make_goblin())
        hero, goblin = enc.combatants[0], enc.combatants[1]
        weapon = Attack(name="Shortsword", attack_bonus=7, damage_dice_count=1,
                        damage_dice_sides=4, damage_bonus=0)
        result = ca.off_hand_attack(enc, hero, goblin, weapon, ability_mod=4)
        assert result.hit
        # d4(2) + min(4, 0) -> 2
        assert result.damage == 2

    def test_off_hand_attack_with_fighting_style_adds_mod(self, monkeypatch):
        # Same rolls; with Two-Weapon style the ability mod is added to damage.
        rolls = iter([10, 10, 15, 2])
        monkeypatch.setattr(dice.random, "randint", lambda _a, _b: next(rolls))
        enc = started_encounter(make_strong_hero(), make_goblin())
        hero, goblin = enc.combatants[0], enc.combatants[1]
        weapon = Attack(name="Shortsword", attack_bonus=7, damage_dice_count=1,
                        damage_dice_sides=4, damage_bonus=0)
        result = ca.off_hand_attack(enc, hero, goblin, weapon, ability_mod=4,
                                    two_weapon_style=True)
        assert result.hit
        # d4(2) + ability mod 4 = 6
        assert result.damage == 6


# --------------------------------------------------------------------------- #
# Opportunity attack
# --------------------------------------------------------------------------- #
class TestOpportunityAttack:
    def test_opportunity_attack_blocked_by_disengage(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        hero, goblin = enc.combatants[0], enc.combatants[1]
        goblin.disengaging = True
        result = ca.opportunity_attack(enc, hero, goblin)
        assert result is None

    def test_opportunity_attack_uses_melee_weapon(self, monkeypatch):
        # Fixed 20 -> auto-hit/crit. Hero longsword vs goblin.
        monkeypatch.setattr(dice.random, "randint", fixed_die(20))
        enc = started_encounter(make_strong_hero(), make_goblin())
        hero, goblin = enc.combatants[0], enc.combatants[1]
        result = ca.opportunity_attack(enc, hero, goblin)
        assert result is not None
        assert result.hit

    def test_opportunity_attack_unarmed_when_no_melee(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(20))
        archer = Combatant(
            id="archer", name="Archer", side="player", max_hp=20, armor_class=14,
            strength=12, dexterity=16,
            attacks=[Attack(name="Bow", attack_bonus=6, damage_dice_count=1,
                            damage_dice_sides=8, ranged=True)],
        )
        goblin = make_goblin()
        enc = started_encounter(archer, goblin)
        result = ca.opportunity_attack(enc, archer, goblin)
        assert result is not None
        assert result.hit


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #
class TestDispatcher:
    def test_dispatch_dash(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        out = ca.perform_action(enc, enc.combatants[0], "dash")
        assert out["action_result"]["success"]
        assert enc.combatants[0].bonus_movement == 30

    def test_dispatch_grapple(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        out = ca.perform_action(enc, enc.combatants[0], "grapple",
                                target=enc.combatants[1])
        assert out["action_result"]["success"]
        assert enc.combatants[1].has_condition("grappled")

    def test_dispatch_shove_option(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        out = ca.perform_action(enc, enc.combatants[0], "shove",
                                target=enc.combatants[1], option="push")
        assert out["action_result"]["success"]

    def test_dispatch_target_required_without_target(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_goblin())
        out = ca.perform_action(enc, enc.combatants[0], "grapple", target=None)
        assert out["action_result"]["success"] is False

    def test_dispatch_unarmed_strike_returns_attack_result(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(20))
        enc = started_encounter(make_strong_hero(), make_goblin())
        out = ca.perform_action(enc, enc.combatants[0], "unarmed-strike",
                                target=enc.combatants[1])
        assert "attack_result" in out
        assert out["attack_result"]["hit"]

    def test_dispatch_off_hand_attack(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(15))
        enc = started_encounter(make_strong_hero(), make_goblin())
        out = ca.perform_action(enc, enc.combatants[0], "off-hand-attack",
                                target=enc.combatants[1])
        assert out["action_result"]["success"]


# --------------------------------------------------------------------------- #
# Serialization round-trip with new fields
# --------------------------------------------------------------------------- #
class TestSerialization:
    def test_new_fields_round_trip(self, monkeypatch):
        monkeypatch.setattr(dice.random, "randint", fixed_die(10))
        enc = started_encounter(make_strong_hero(), make_huge_ogre())
        hero, ogre = enc.combatants[0], enc.combatants[1]
        ca.dodge(enc, hero)
        ca.help_ally(enc, hero, ogre)
        data = enc.to_dict()
        restored = Encounter.from_dict(data)

        r_hero = next(c for c in restored.combatants if c.id == "hero")
        r_ogre = next(c for c in restored.combatants if c.id == "ogre")
        assert r_hero.dodging is True
        assert r_hero.strength == 18
        assert r_ogre.size == "large"
        assert r_ogre.athletics_bonus == 8
        assert restored.help_advantage_targets == [r_ogre.id]

    def test_backward_compat_old_data_loads(self):
        # An encounter dict missing the new fields must still load with defaults.
        minimal = {
            "combatants": [{
                "id": "p", "name": "P", "side": "player",
                "max_hp": 10, "armor_class": 10,
            }],
            "turn_order_ids": ["p"],
            "started": True,
        }
        enc = Encounter.from_dict(minimal)
        c = enc.combatants[0]
        assert c.size == "medium"
        assert c.strength == 10
        assert c.dodging is False
        assert c.grappled_by is None
        assert enc.help_advantage_targets == []
