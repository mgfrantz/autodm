"""
Tests for the Legendary Actions & Lair Actions engine (engine/legendary.py).

Covers the Monster Manual (p. 11) boss mechanics: the per-round legendary-action
budget (spend / reset / affordability), off-turn legendary-action resolution,
lair-action scheduling on initiative 20, the DM summary, and the registry of
iconic legendary creatures. The engine is pure, so these are fast unit tests.
"""
from __future__ import annotations

from app.engine import legendary
from app.engine.combat import Combatant, Attack, Encounter
from app.engine.legendary import (
    LegendaryAction,
    LairAction,
    LegendaryState,
    LAIR_INITIATIVE_COUNT,
    ADULT_RED_DRAGON,
    LICH,
    BEHOLDER,
    VAMPIRE,
    TARRASQUE,
    ADULT_BLUE_DRAGON,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def make_boss(
    budget: int = 3,
    actions: list[LegendaryAction] | None = None,
) -> Combatant:
    if actions is None:
        actions = [
            LegendaryAction(id="detect", name="Detect", cost=1, kind="detect", description="Perception."),
            LegendaryAction(id="tail", name="Tail Attack", cost=1, kind="attack",
                            attack={"name": "Tail", "attack_bonus": 5,
                                    "damage_dice_count": 2, "damage_dice_sides": 8,
                                    "damage_bonus": 3, "damage_type": "bludgeoning"}),
            LegendaryAction(id="wing", name="Wing Attack", cost=2, kind="utility",
                            description="AoE knockdown."),
        ]
    return Combatant(
        id="dragon",
        name="Red Dragon",
        side="enemy",
        max_hp=200,
        armor_class=19,
        is_legendary=True,
        legendary_actions=[a.to_dict() for a in actions],
        legendary_budget_max=budget,
        legendary_budget_used=0,
    )


def make_hero() -> Combatant:
    return Combatant(
        id="player",
        name="Hero",
        side="player",
        max_hp=40,
        armor_class=16,
        attacks=[Attack(name="Sword", attack_bonus=6, damage_dice_count=1,
                        damage_dice_sides=8, damage_bonus=3)],
    )


def make_goblin() -> Combatant:
    return Combatant(
        id="goblin1",
        name="Goblin",
        side="enemy",
        max_hp=7,
        armor_class=13,
    )


# --------------------------------------------------------------------------- #
# LegendaryState
# --------------------------------------------------------------------------- #
class TestLegendaryState:
    def test_default_budget_is_three(self):
        s = LegendaryState()
        assert s.budget_max == 3
        assert s.budget_used == 0
        assert s.remaining == 3

    def test_can_spend_within_budget(self):
        s = LegendaryState(budget_max=3)
        assert s.can_spend(1) is True
        assert s.can_spend(2) is True
        assert s.can_spend(3) is True

    def test_cannot_spend_beyond_budget(self):
        s = LegendaryState(budget_max=3)
        assert s.can_spend(4) is False

    def test_zero_cost_is_invalid(self):
        s = LegendaryState(budget_max=3)
        assert s.can_spend(0) is False
        assert s.can_spend(-1) is False

    def test_spend_reduces_remaining(self):
        s = LegendaryState(budget_max=3)
        s.spend(2)
        assert s.remaining == 1
        s.spend(1)
        assert s.remaining == 0

    def test_spend_unaffordable_raises(self):
        s = LegendaryState(budget_max=3, budget_used=2)
        try:
            s.spend(2)
            assert False, "Expected ValueError"
        except ValueError:
            pass

    def test_reset_regains_all(self):
        s = LegendaryState(budget_max=3, budget_used=3)
        assert s.remaining == 0
        s.reset()
        assert s.remaining == 3

    def test_round_trip_serialization(self):
        s = LegendaryState(budget_max=5, budget_used=2)
        d = s.to_dict()
        assert d == {"budget_max": 5, "budget_used": 2}
        s2 = LegendaryState.from_dict(d)
        assert s2.budget_max == 5
        assert s2.budget_used == 2
        assert s2.remaining == 3

    def test_from_dict_empty(self):
        s = LegendaryState.from_dict({})
        assert s.budget_max == 3
        assert s.budget_used == 0


# --------------------------------------------------------------------------- #
# LegendaryAction / LairAction serialization
# --------------------------------------------------------------------------- #
class TestActionSerialization:
    def test_legendary_action_round_trip(self):
        a = LegendaryAction(id="tail", name="Tail Attack", cost=1, kind="attack",
                            attack={"name": "Tail", "attack_bonus": 5},
                            condition="prone", condition_duration=1, notes="x")
        d = a.to_dict()
        a2 = LegendaryAction.from_dict(d)
        assert a2.id == "tail"
        assert a2.cost == 1
        assert a2.kind == "attack"
        assert a2.attack == {"name": "Tail", "attack_bonus": 5}
        assert a2.condition == "prone"

    def test_lair_action_round_trip(self):
        a = LairAction(id="magma", name="Magma", kind="save", damage=21,
                       damage_type="fire", save_dc=15, save_ability="dex",
                       description="Magma erupts.")
        d = a.to_dict()
        a2 = LairAction.from_dict(d)
        assert a2.id == "magma"
        assert a2.initiative_count == LAIR_INITIATIVE_COUNT
        assert a2.save_dc == 15
        assert a2.save_ability == "dex"
        assert a2.damage == 21

    def test_lair_action_default_initiative_count(self):
        a = LairAction(id="x", name="X")
        assert a.initiative_count == 20
        assert LAIR_INITIATIVE_COUNT == 20


# --------------------------------------------------------------------------- #
# Combatant detection + state
# --------------------------------------------------------------------------- #
class TestLegendaryDetection:
    def test_non_legendary_is_not_legendary(self):
        c = make_goblin()
        assert legendary.is_legendary(c) is False

    def test_legendary_flag(self):
        c = Combatant(id="x", name="X", side="enemy", max_hp=10, armor_class=10,
                      is_legendary=True)
        assert legendary.is_legendary(c) is True

    def test_legendary_via_actions(self):
        c = Combatant(id="x", name="X", side="enemy", max_hp=10, armor_class=10,
                      legendary_actions=[{"id": "a", "name": "A"}],
                      legendary_budget_max=3)
        assert legendary.is_legendary(c) is True

    def test_get_legendary_actions_parses_dicts(self):
        c = make_boss()
        actions = legendary.get_legendary_actions(c)
        assert len(actions) == 3
        assert all(isinstance(a, LegendaryAction) for a in actions)

    def test_available_actions_respects_budget(self):
        c = make_boss()
        state = LegendaryState(budget_max=3, budget_used=2)
        avail = legendary.available_legendary_actions(c, state)
        # Only cost-1 actions fit with 1 remaining.
        ids = {a.id for a in avail}
        assert ids == {"detect", "tail"}

    def test_creature_state_reads_combatant(self):
        c = make_boss()
        c.legendary_budget_used = 1
        state = legendary.creature_state(c)
        assert state.budget_max == 3
        assert state.remaining == 2


# --------------------------------------------------------------------------- #
# Spending legendary actions
# --------------------------------------------------------------------------- #
class TestSpendLegendary:
    def test_can_take_valid_action(self):
        c = make_boss()
        state = legendary.creature_state(c)
        action = legendary.get_legendary_actions(c)[0]  # detect, cost 1
        ok, _ = legendary.can_take_legendary_action(c, state, action)
        assert ok is True

    def test_cannot_take_unknown_action(self):
        c = make_boss()
        state = legendary.creature_state(c)
        fake = LegendaryAction(id="nope", name="Nope", cost=1)
        ok, reason = legendary.can_take_legendary_action(c, state, fake)
        assert ok is False
        assert "not one of" in reason

    def test_non_legendary_cannot_act(self):
        goblin = make_goblin()
        state = LegendaryState()
        ok, reason = legendary.can_take_legendary_action(
            goblin, state, LegendaryAction(id="detect", name="Detect", cost=1)
        )
        assert ok is False
        assert "not legendary" in reason

    def test_cannot_afford_costly_action(self):
        c = make_boss()
        state = LegendaryState(budget_max=3, budget_used=2)
        wing = next(a for a in legendary.get_legendary_actions(c) if a.cost == 2)
        ok, reason = legendary.can_take_legendary_action(c, state, wing)
        assert ok is False
        assert "Not enough" in reason

    def test_spend_reduces_budget_and_persists(self):
        c = make_boss()
        state = legendary.creature_state(c)
        tail = next(a for a in legendary.get_legendary_actions(c) if a.id == "tail")
        result = legendary.spend_legendary_action(c, state, tail)
        assert result.used is True
        assert result.remaining_budget == 2
        # Persisted onto the combatant.
        assert c.legendary_budget_used == 1

    def test_spend_blocked_when_broke(self):
        c = make_boss()
        c.legendary_budget_used = 3
        state = legendary.creature_state(c)
        tail = next(a for a in legendary.get_legendary_actions(c) if a.id == "tail")
        result = legendary.spend_legendary_action(c, state, tail)
        assert result.used is False
        assert "Not enough" in result.reason

    def test_reset_legendary_actions(self):
        c = make_boss()
        c.legendary_budget_used = 3
        legendary.reset_legendary_actions(c)
        assert c.legendary_budget_used == 0


# --------------------------------------------------------------------------- #
# Lair actions
# --------------------------------------------------------------------------- #
class TestLairActions:
    def test_has_lair_true_with_actions(self):
        class Holder:
            lair_actions = [{"id": "a", "name": "A"}]
        assert legendary.has_lair(Holder()) is True

    def test_has_lair_false_empty(self):
        class Holder:
            lair_actions = []
        assert legendary.has_lair(Holder()) is False

    def test_get_lair_actions_parses(self):
        class Holder:
            lair_actions = [{"id": "a", "name": "A", "kind": "save", "save_dc": 14}]
        lair = legendary.get_lair_actions(Holder())
        assert len(lair) == 1
        assert isinstance(lair[0], LairAction)
        assert lair[0].save_dc == 14

    def test_should_fire_with_actions(self):
        actions = [LairAction(id="a", name="A")]
        assert legendary.should_fire_lair_action(1, actions) is True

    def test_should_not_fire_when_no_actions(self):
        assert legendary.should_fire_lair_action(1, []) is False

    def test_should_not_fire_twice_same_round(self):
        actions = [LairAction(id="a", name="A")]
        assert legendary.should_fire_lair_action(
            1, actions, last_fired_round=1
        ) is False

    def test_choose_lair_action_round_robin(self):
        actions = [LairAction(id="a", name="A"), LairAction(id="b", name="B")]
        assert legendary.choose_lair_action(actions, 1).id == "a"
        assert legendary.choose_lair_action(actions, 2).id == "b"
        assert legendary.choose_lair_action(actions, 3).id == "a"

    def test_choose_lair_action_empty(self):
        assert legendary.choose_lair_action([], 1) is None

    def test_fire_lair_action_returns_description(self):
        a = LairAction(id="magma", name="Magma", description="Magma erupts.",
                       kind="save", save_dc=15)
        result = legendary.fire_lair_action(a, 2)
        assert result.triggered is True
        assert "Magma" in result.description
        assert "round 2" in result.description

    def test_fire_lair_action_none(self):
        result = legendary.fire_lair_action(None, 1)
        assert result.triggered is False


# --------------------------------------------------------------------------- #
# DM summary
# --------------------------------------------------------------------------- #
class TestDMSummary:
    def test_summary_for_legendary_with_lair(self):
        # Lair actions are encounter-level, but legendary_summary_for_dm also
        # surfaces them when attached to the summarised object.
        class Holder:
            name = "Red Dragon"
            is_legendary = True
            legendary_actions = [a.to_dict() for a in [
                LegendaryAction(id="detect", name="Detect", cost=1),
                LegendaryAction(id="wing", name="Wing Attack", cost=2),
            ]]
            legendary_budget_max = 3
            lair_actions = [LairAction(id="m", name="Magma").to_dict()]
        summary = legendary.legendary_summary_for_dm(Holder())
        assert "legendary" in summary
        assert "Detect (1)" in summary
        assert "Wing Attack (2)" in summary
        assert "Magma" in summary
        assert "initiative 20" in summary

    def test_summary_for_plain_combatant(self):
        c = make_boss()
        summary = legendary.legendary_summary_for_dm(c)
        assert "legendary" in summary
        assert "Detect (1)" in summary
        # A plain Combatant has no encounter-level lair actions attached.
        assert "initiative 20" not in summary

    def test_summary_empty_for_non_legendary(self):
        c = make_goblin()
        assert legendary.legendary_summary_for_dm(c) == ""

    def test_creature_has_lair_false_on_plain_combatant(self):
        c = make_boss()
        assert legendary.creature_has_lair(c) is False


# --------------------------------------------------------------------------- #
# Combatant / Encounter integration
# --------------------------------------------------------------------------- #
class TestCombatIntegration:
    def test_combatant_round_trip_preserves_legendary(self):
        boss = make_boss()
        d = boss.to_dict()
        assert d["is_legendary"] is True
        assert d["legendary_budget_max"] == 3
        assert len(d["legendary_actions"]) == 3
        boss2 = Combatant.from_dict(d)
        assert boss2.is_legendary is True
        assert boss2.legendary_budget_max == 3
        assert len(boss2.legendary_actions) == 3

    def test_non_legendary_round_trip_defaults(self):
        g = make_goblin()
        d = g.to_dict()
        assert d["is_legendary"] is False
        assert d["legendary_actions"] == []
        assert d["legendary_budget_max"] == 0
        g2 = Combatant.from_dict(d)
        assert legendary.is_legendary(g2) is False

    def test_start_turn_resets_legendary_budget(self):
        boss = make_boss()
        boss.legendary_budget_used = 3
        assert boss.legendary_budget_used == 3
        boss.start_turn()
        assert boss.legendary_budget_used == 0

    def test_non_legendary_start_turn_unaffected(self):
        g = make_goblin()
        g.start_turn()  # should not raise
        assert g.legendary_budget_used == 0

    def test_encounter_lair_action_fires(self):
        boss = make_boss()
        lair = [LairAction(id="m", name="Magma", description="Magma erupts.",
                           kind="save", save_dc=15).to_dict()]
        enc = Encounter([make_hero(), boss])
        enc.lair_actions = lair
        enc.start()
        result = enc.trigger_lair_action()
        assert result is not None
        assert result.triggered is True
        assert "Magma" in result.description
        assert enc.lair_last_fired_round == enc.round_number

    def test_encounter_lair_action_no_repeat_same_round(self):
        boss = make_boss()
        lair = [LairAction(id="m", name="Magma", description="Magma.").to_dict()]
        enc = Encounter([make_hero(), boss])
        enc.lair_actions = lair
        enc.start()
        first = enc.trigger_lair_action()
        assert first is not None and first.triggered is True
        second = enc.trigger_lair_action()
        assert second is None  # already fired this round

    def test_encounter_no_lair_returns_none(self):
        enc = Encounter([make_hero(), make_goblin()])
        enc.start()
        assert enc.trigger_lair_action() is None

    def test_encounter_lair_round_trip(self):
        boss = make_boss()
        lair = [LairAction(id="m", name="Magma", description="Magma.").to_dict()]
        enc = Encounter([make_hero(), boss])
        enc.lair_actions = lair
        enc.start()
        enc.trigger_lair_action()
        d = enc.to_dict()
        assert d["lair_actions"] == lair
        assert d["lair_last_fired_round"] == 1
        enc2 = Encounter.from_dict(d)
        assert len(enc2.lair_actions) == 1
        assert enc2.lair_last_fired_round == 1


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
class TestRegistry:
    def test_registry_has_six_creatures(self):
        creatures = legendary.list_legendary_creatures()
        assert len(creatures) == 6

    def test_registry_ids(self):
        ids = {p.id for p in legendary.list_legendary_creatures()}
        assert ids == {
            "adult_red_dragon", "lich", "beholder", "vampire", "tarrasque",
            "adult_blue_dragon",
        }

    def test_get_legendary_creature(self):
        p = legendary.get_legendary_creature("lich")
        assert p is not None
        assert p.name == "Lich"
        assert p.cr == 21

    def test_get_unknown_returns_none(self):
        assert legendary.get_legendary_creature("nobody") is None

    def test_red_dragon_has_legendary_and_lair(self):
        p = legendary.get_legendary_creature("adult_red_dragon")
        assert len(p.legendary_actions) == 3
        assert any(a.cost == 2 for a in p.legendary_actions)  # Wing Attack
        assert len(p.lair_actions) == 2
        assert p.legendary_budget_max == 3
        assert p.cr == 17

    def test_lich_has_legendary_no_lair(self):
        p = legendary.get_legendary_creature("lich")
        assert len(p.legendary_actions) >= 3
        assert len(p.lair_actions) == 0

    def test_tarrasque_high_cr(self):
        p = legendary.get_legendary_creature("tarrasque")
        assert p.cr == 30
        assert p.max_hp == 676

    def test_blue_dragon_has_lair(self):
        p = legendary.get_legendary_creature("adult_blue_dragon")
        assert len(p.lair_actions) == 2
        assert p.cr == 16

    def test_preset_to_dict_round_trip(self):
        p = legendary.get_legendary_creature("beholder")
        d = p.to_dict()
        assert d["id"] == "beholder"
        assert d["cr"] == 13
        assert len(d["legendary_actions"]) == 2
        # The combat /combat/start contract fields are present.
        assert "max_hp" in d
        assert "armor_class" in d
        assert "attacks" in d

    def test_all_presets_have_attacks_and_actions(self):
        for p in legendary.list_legendary_creatures():
            assert p.attacks, f"{p.id} has no attacks"
            assert p.legendary_actions, f"{p.id} has no legendary actions"
            assert p.legendary_budget_max > 0, f"{p.id} has no budget"
