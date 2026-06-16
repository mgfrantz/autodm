"""
Tests for the conditions / status-effects engine and its combat integration.

Covers:
- The 14 DnD 5e conditions registry and rule lookups.
- Condition query helpers (advantage / disadvantage / incapacitated / etc.).
- Condition management: apply / remove / timed durations.
- resolve_attack integration: condition-driven advantage/disadvantage,
  melee auto-crits (paralyzed), and damage resistance (petrified).
- next_turn integration: incapacitated combatants are skipped, and timed
  conditions tick down at the start of each new round.
- Serialization round-trips (conditions, durations, ranged attacks).
- REST API endpoints for listing / applying / removing conditions.
"""
import pytest

from app.engine import combat as combat_mod
from app.engine import conditions as cond
from app.engine.combat import Attack, Combatant, Encounter
from app.engine.dice import RollResult
from app.models.models import Character, World, GameSave


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #

def make_player(**kw) -> Combatant:
    base = dict(
        id="hero", name="Hero", side="player", max_hp=30, armor_class=16,
        initiative_bonus=3, speed=30,
        attacks=[Attack(name="Longsword", attack_bonus=5, damage_dice_count=1,
                        damage_dice_sides=8, damage_bonus=3)],
    )
    base.update(kw)
    return Combatant(**base)


def make_enemy(**kw) -> Combatant:
    base = dict(
        id="goblin", name="Goblin", side="enemy", max_hp=20, armor_class=14,
        initiative_bonus=2, speed=30,
        attacks=[Attack(name="Scimitar", attack_bonus=4, damage_dice_count=1,
                        damage_dice_sides=6, damage_bonus=2)],
    )
    base.update(kw)
    return Combatant(**base)


def roll_d20_spy(die: int = 15, capture: list | None = None):
    """Replace roll_d20: record call kwargs and return a fixed RollResult."""
    def _spy(modifier=0, advantage=False, disadvantage=False):
        if capture is not None:
            capture.append({"advantage": advantage, "disadvantage": disadvantage})
        return RollResult(
            rolls=[die], modifier=modifier, total=die + modifier, description="spy"
        )
    return _spy


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

class TestConditionRegistry:
    def test_all_fourteen_conditions_present(self):
        names = cond.list_conditions()
        assert len(names) == 14
        expected = {
            "blinded", "charmed", "deafened", "frightened", "grappled",
            "incapacitated", "invisible", "paralyzed", "petrified", "poisoned",
            "prone", "restrained", "stunned", "unconscious",
        }
        assert expected.issubset(set(names))

    def test_is_valid_condition(self):
        assert cond.is_valid_condition("poisoned")
        assert not cond.is_valid_condition("on_fire")

    def test_get_condition_info_unknown(self):
        assert cond.get_condition_info("nope") is None

    def test_get_condition_info_known(self):
        info = cond.get_condition_info("paralyzed")
        assert info["incapacitated"] is True
        assert info["melee_auto_crit"] is True
        assert info["defense_advantage"] is True
        assert info["speed_zero"] is True


# --------------------------------------------------------------------------- #
# Query helpers
# --------------------------------------------------------------------------- #

class TestConditionQueries:
    @pytest.mark.parametrize("name", [
        "paralyzed", "petrified", "stunned", "unconscious", "incapacitated",
    ])
    def test_incapacitating(self, name):
        assert cond.is_incapacitated(make_player(conditions=[name]))

    @pytest.mark.parametrize("name", [
        "blinded", "charmed", "deafened", "frightened", "grappled",
        "invisible", "poisoned", "prone", "restrained",
    ])
    def test_non_incapacitating(self, name):
        assert not cond.is_incapacitated(make_player(conditions=[name]))

    def test_invisible_grants_attack_advantage(self):
        assert cond.attack_roll_advantage(make_player(conditions=["invisible"]))

    def test_attack_advantage_false_for_others(self):
        assert not cond.attack_roll_advantage(make_player(conditions=["poisoned"]))

    @pytest.mark.parametrize("name", [
        "poisoned", "blinded", "frightened", "prone", "restrained",
    ])
    def test_attack_disadvantage(self, name):
        assert cond.attack_roll_disadvantage(make_player(conditions=[name]))

    def test_attack_disadvantage_false_for_invisible(self):
        assert not cond.attack_roll_disadvantage(make_player(conditions=["invisible"]))

    @pytest.mark.parametrize("name", [
        "blinded", "paralyzed", "petrified", "restrained", "stunned", "unconscious",
    ])
    def test_attacks_against_advantage(self, name):
        assert cond.attacks_against_have_advantage(make_player(conditions=[name]))

    def test_invisible_attacks_against_disadvantage(self):
        assert cond.attacks_against_have_disadvantage(make_player(conditions=["invisible"]))

    def test_prone_melee_advantage_ranged_disadvantage(self):
        prone = make_player(conditions=["prone"])
        assert cond.attacks_against_have_advantage(prone, ranged=False)
        assert not cond.attacks_against_have_advantage(prone, ranged=True)
        assert cond.attacks_against_have_disadvantage(prone, ranged=True)
        assert not cond.attacks_against_have_disadvantage(prone, ranged=False)

    @pytest.mark.parametrize("name", ["paralyzed", "petrified", "unconscious"])
    def test_melee_auto_crit(self, name):
        assert cond.melee_auto_crit(make_player(conditions=[name]))

    def test_melee_auto_crit_false_for_stunned(self):
        # Stunned makes you easier to hit but does NOT grant auto-crits.
        assert not cond.melee_auto_crit(make_player(conditions=["stunned"]))

    def test_petrified_damage_resistance(self):
        assert cond.has_damage_resistance(make_player(conditions=["petrified"]))

    def test_damage_resistance_false_for_others(self):
        assert not cond.has_damage_resistance(make_player(conditions=["paralyzed"]))

    @pytest.mark.parametrize("name", [
        "grappled", "restrained", "paralyzed", "petrified", "unconscious",
    ])
    def test_speed_zero(self, name):
        assert cond.effective_speed(make_player(conditions=[name], speed=30)) == 0

    def test_effective_speed_normal(self):
        assert cond.effective_speed(make_player(speed=30)) == 30

    def test_unknown_condition_label_ignored_in_queries(self):
        c = make_player(conditions=["custom_dot"])
        assert not cond.is_incapacitated(c)
        assert cond.effective_speed(c) == 30
        assert not cond.has_damage_resistance(c)


# --------------------------------------------------------------------------- #
# Management: apply / remove / durations
# --------------------------------------------------------------------------- #

class TestConditionManagement:
    def test_apply_adds_condition(self):
        c = make_player()
        assert cond.apply_condition(c, "poisoned") is True
        assert "poisoned" in c.conditions

    def test_apply_twice_returns_false_no_duplicate(self):
        c = make_player()
        cond.apply_condition(c, "poisoned")
        assert cond.apply_condition(c, "poisoned") is False
        assert c.conditions.count("poisoned") == 1

    def test_apply_invalid_raises(self):
        with pytest.raises(ValueError):
            cond.apply_condition(make_player(), "burning")

    def test_apply_invalid_duration_raises(self):
        with pytest.raises(ValueError):
            cond.apply_condition(make_player(), "poisoned", duration=0)

    def test_apply_with_duration_tracks(self):
        c = make_player()
        cond.apply_condition(c, "stunned", duration=3)
        assert cond.remaining_duration(c, "stunned") == 3

    def test_remaining_duration_none_for_permanent(self):
        c = make_player()
        cond.apply_condition(c, "poisoned")
        assert cond.remaining_duration(c, "poisoned") is None

    def test_remove_condition(self):
        c = make_player()
        cond.apply_condition(c, "poisoned")
        assert cond.remove_condition(c, "poisoned") is True
        assert "poisoned" not in c.conditions
        assert cond.remove_condition(c, "poisoned") is False

    def test_remove_clears_duration(self):
        c = make_player()
        cond.apply_condition(c, "poisoned", duration=2)
        cond.remove_condition(c, "poisoned")
        assert cond.remaining_duration(c, "poisoned") is None

    def test_tick_decrements_then_expires(self):
        c = make_player()
        cond.apply_condition(c, "poisoned", duration=2)
        assert cond.tick_conditions(c) == []
        assert cond.remaining_duration(c, "poisoned") == 1
        expired = cond.tick_conditions(c)
        assert expired == ["poisoned"]
        assert "poisoned" not in c.conditions

    def test_tick_leaves_permanent_conditions(self):
        c = make_player()
        cond.apply_condition(c, "poisoned")  # no duration -> permanent
        assert cond.tick_conditions(c) == []
        assert "poisoned" in c.conditions

    def test_describe_includes_info_and_duration(self):
        c = make_player()
        cond.apply_condition(c, "poisoned", duration=4)
        desc = cond.describe(c)
        assert len(desc) == 1
        assert desc[0]["name"] == "poisoned"
        assert desc[0]["attack_disadvantage"] is True
        assert desc[0]["duration"] == 4

    def test_combatant_add_remove_methods(self):
        c = make_player()
        c.add_condition("poisoned", duration=2)
        assert c.has_condition("poisoned")
        assert c.condition_durations["poisoned"] == 2
        assert c.remove_condition("poisoned") is True
        assert not c.has_condition("poisoned")

    def test_combatant_is_incapacitated_property(self):
        c = make_player()
        assert not c.is_incapacitated
        c.add_condition("stunned")
        assert c.is_incapacitated

    def test_combatant_effective_speed_property(self):
        c = make_player(speed=30)
        assert c.effective_speed == 30
        c.add_condition("restrained")
        assert c.effective_speed == 0


# --------------------------------------------------------------------------- #
# resolve_attack condition integration
# --------------------------------------------------------------------------- #

class TestCombatConditionIntegration:
    def _attack(self, monkeypatch, attacker, target, attack=None,
                capture=None, die=15):
        enc = Encounter([attacker, target])
        enc.started = True  # resolve_attack does not require initiative order
        monkeypatch.setattr(combat_mod, "roll_d20", roll_d20_spy(die=die, capture=capture))
        return enc.resolve_attack(attacker, target, attack or attacker.attacks[0])

    def test_poisoned_attacker_suffers_disadvantage(self, monkeypatch):
        cap = []
        self._attack(monkeypatch, make_player(conditions=["poisoned"]), make_enemy(),
                     capture=cap)
        assert cap[0]["disadvantage"] is True
        assert cap[0]["advantage"] is False

    def test_invisible_attacker_gains_advantage(self, monkeypatch):
        cap = []
        self._attack(monkeypatch, make_player(conditions=["invisible"]), make_enemy(),
                     capture=cap)
        assert cap[0]["advantage"] is True
        assert cap[0]["disadvantage"] is False

    def test_stunned_target_attacks_against_advantage(self, monkeypatch):
        cap = []
        self._attack(monkeypatch, make_player(), make_enemy(conditions=["stunned"]),
                     capture=cap)
        assert cap[0]["advantage"] is True
        assert cap[0]["disadvantage"] is False

    def test_invisible_target_attacks_against_disadvantage(self, monkeypatch):
        cap = []
        self._attack(monkeypatch, make_player(), make_enemy(conditions=["invisible"]),
                     capture=cap)
        assert cap[0]["disadvantage"] is True
        assert cap[0]["advantage"] is False

    def test_prone_target_melee_gives_advantage(self, monkeypatch):
        cap = []
        self._attack(monkeypatch, make_player(), make_enemy(conditions=["prone"]),
                     capture=cap)
        assert cap[0]["advantage"] is True

    def test_prone_target_ranged_gives_disadvantage(self, monkeypatch):
        cap = []
        ranged = Attack(name="Bow", attack_bonus=5, ranged=True,
                        damage_dice_count=1, damage_dice_sides=8)
        player = make_player(attacks=[ranged])
        self._attack(monkeypatch, player, make_enemy(conditions=["prone"]),
                     attack=ranged, capture=cap)
        assert cap[0]["disadvantage"] is True

    def test_advantage_and_disadvantage_both_passed_through(self, monkeypatch):
        # Attacker both poisoned (disadv) and invisible (adv) -> net cancels in roll_d20.
        cap = []
        self._attack(monkeypatch, make_player(conditions=["poisoned", "invisible"]),
                     make_enemy(), capture=cap)
        assert cap[0]["advantage"] is True
        assert cap[0]["disadvantage"] is True

    def test_paralyzed_target_melee_auto_crit(self, monkeypatch):
        result = self._attack(monkeypatch, make_player(),
                              make_enemy(conditions=["paralyzed"]), die=15)
        assert result.hit
        assert result.critical is True  # not a nat 20 — forced by the condition

    def test_paralyzed_target_ranged_no_auto_crit(self, monkeypatch):
        ranged = Attack(name="Bow", attack_bonus=5, ranged=True)
        player = make_player(attacks=[ranged])
        result = self._attack(monkeypatch, player, make_enemy(conditions=["paralyzed"]),
                              attack=ranged, die=15)
        assert result.hit
        assert result.critical is False

    def test_petrified_target_halves_damage(self, monkeypatch):
        ranged = Attack(name="Bow", attack_bonus=5, ranged=True,
                        damage_dice_count=1, damage_dice_sides=8, damage_bonus=0)
        player = make_player(attacks=[ranged])
        monkeypatch.setattr(ranged, "roll_damage", lambda critical=False: 10)
        result = self._attack(monkeypatch, player, make_enemy(conditions=["petrified"]),
                              attack=ranged, die=15)
        assert result.hit
        assert result.critical is False  # ranged, so no auto-crit
        assert result.damage == 5  # 10 halved by resistance

    def test_no_resistance_when_not_petrified(self, monkeypatch):
        ranged = Attack(name="Bow", attack_bonus=5, ranged=True)
        player = make_player(attacks=[ranged])
        monkeypatch.setattr(ranged, "roll_damage", lambda critical=False: 10)
        result = self._attack(monkeypatch, player, make_enemy(), attack=ranged, die=15)
        assert result.damage == 10


# --------------------------------------------------------------------------- #
# next_turn integration: incapacitated skip + round ticking
# --------------------------------------------------------------------------- #

class TestNextTurnConditions:
    def test_incapacitated_combatant_is_skipped(self):
        player = make_player()
        goblin = make_enemy(conditions=["stunned"])  # permanently stunned
        enc = Encounter([player, goblin])
        enc.turn_order = [player, goblin]
        enc.started = True
        enc.round_number = 1
        enc.current_turn_index = 0  # player's turn now
        nxt = enc.next_turn()
        assert nxt is player          # goblin skipped
        assert enc.round_number == 2  # wrapped around

    def test_timed_condition_expires_on_new_round(self):
        player = make_player()
        goblin = make_enemy()
        enc = Encounter([player, goblin])
        enc.turn_order = [player, goblin]
        enc.started = True
        enc.round_number = 1
        enc.current_turn_index = 1  # goblin's turn now
        player.add_condition("poisoned", duration=1)
        assert player.has_condition("poisoned")
        nxt = enc.next_turn()  # wraps -> new round ticks conditions
        assert nxt is player
        assert enc.round_number == 2
        assert not player.has_condition("poisoned")  # expired

    def test_all_incapacitated_returns_none(self):
        player = make_player(conditions=["stunned"])
        goblin = make_enemy(conditions=["paralyzed"])
        enc = Encounter([player, goblin])
        enc.turn_order = [player, goblin]
        enc.started = True
        enc.round_number = 1
        enc.current_turn_index = 0
        assert enc.next_turn() is None


# --------------------------------------------------------------------------- #
# Serialization round-trips
# --------------------------------------------------------------------------- #

class TestConditionSerialization:
    def test_combatant_roundtrip_conditions_and_durations(self):
        player = make_player()
        player.add_condition("poisoned", duration=2)
        player.attacks[0].ranged = True
        data = player.to_dict()
        assert data["conditions"] == ["poisoned"]
        assert data["condition_durations"] == {"poisoned": 2}
        assert data["attacks"][0]["ranged"] is True
        restored = Combatant.from_dict(data)
        assert restored.conditions == ["poisoned"]
        assert restored.condition_durations == {"poisoned": 2}
        assert restored.attacks[0].ranged is True
        assert restored.has_condition("poisoned")

    def test_encounter_roundtrip_preserves_conditions(self):
        player = make_player()
        goblin = make_enemy(conditions=["stunned"])
        goblin.add_condition("poisoned", duration=3)
        enc = Encounter([player, goblin])
        enc.start()
        enc2 = Encounter.from_dict(enc.to_dict())
        g2 = next(c for c in enc2.combatants if c.id == "goblin")
        assert g2.has_condition("stunned")
        assert g2.has_condition("poisoned")
        assert g2.condition_durations["poisoned"] == 3
        assert g2.is_incapacitated  # stunned incapacitates

    def test_backwards_compatible_dict_without_new_fields(self):
        # Old serialized combatants without condition_durations / ranged still load.
        legacy = {
            "id": "hero", "name": "Hero", "side": "player", "max_hp": 30,
            "armor_class": 16, "conditions": ["poisoned"],
            "attacks": [{"name": "Sword", "attack_bonus": 5,
                         "damage_dice_count": 1, "damage_dice_sides": 8,
                         "damage_bonus": 3, "damage_type": "slashing"}],
        }
        c = Combatant.from_dict(legacy)
        assert c.conditions == ["poisoned"]
        assert c.condition_durations == {}
        assert c.attacks[0].ranged is False


# --------------------------------------------------------------------------- #
# REST API
# --------------------------------------------------------------------------- #

def _make_char_and_world(db_session):
    char = Character(
        name="Hero", race="Human", char_class="Fighter", level=1,
        strength=16, dexterity=12, constitution=14, intelligence=10,
        wisdom=10, charisma=10, max_hp=12, current_hp=12, armor_class=16, speed=30,
    )
    db_session.add(char)
    db_session.flush()
    w = World(name="W", description="d", world_data="{}", tone="heroic fantasy")
    db_session.add(w)
    db_session.flush()
    return char, w


def _start_combat(client, db_session):
    char, w = _make_char_and_world(db_session)
    save = GameSave(
        name="G", character_id=char.id, world_id=w.id,
        game_state='{"location": "town"}', story_log="[]", current_act=1, xp=0,
    )
    db_session.add(save)
    db_session.commit()
    client.post(
        f"/api/game/{save.id}/combat/start",
        json={"enemies": [{"name": "Goblin", "max_hp": 7, "armor_class": 15, "attacks": []}]},
    )
    return save


class TestConditionAPI:
    def test_list_conditions(self, client, db_session):
        save = _start_combat(client, db_session)
        r = client.get(f"/api/game/{save.id}/combat/conditions")
        assert r.status_code == 200
        names = {c["name"] for c in r.json()["conditions"]}
        assert len(names) == 14
        assert "poisoned" in names

    def test_apply_condition(self, client, db_session):
        save = _start_combat(client, db_session)
        r = client.post(
            f"/api/game/{save.id}/combat/conditions/player",
            json={"condition": "poisoned"},
        )
        assert r.status_code == 200
        assert "poisoned" in r.json()["combatant"]["conditions"]

    def test_apply_condition_with_duration(self, client, db_session):
        save = _start_combat(client, db_session)
        r = client.post(
            f"/api/game/{save.id}/combat/conditions/player",
            json={"condition": "stunned", "duration": 2},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["combatant"]["condition_durations"]["stunned"] == 2

    def test_apply_condition_persists_to_state(self, client, db_session):
        save = _start_combat(client, db_session)
        client.post(
            f"/api/game/{save.id}/combat/conditions/enemy_1",
            json={"condition": "stunned"},
        )
        state = client.get(f"/api/game/{save.id}/combat/state").json()
        enemy = next(c for c in state["encounter"]["combatants"] if c["id"] == "enemy_1")
        assert "stunned" in enemy["conditions"]

    def test_apply_condition_twice_refreshes(self, client, db_session):
        save = _start_combat(client, db_session)
        client.post(f"/api/game/{save.id}/combat/conditions/player",
                    json={"condition": "poisoned"})
        r = client.post(f"/api/game/{save.id}/combat/conditions/player",
                        json={"condition": "poisoned", "duration": 3})
        assert r.status_code == 200
        assert "refreshed" in r.json()["message"]
        assert r.json()["combatant"]["condition_durations"]["poisoned"] == 3

    def test_remove_condition(self, client, db_session):
        save = _start_combat(client, db_session)
        client.post(f"/api/game/{save.id}/combat/conditions/player",
                    json={"condition": "poisoned"})
        r = client.request(
            "DELETE",
            f"/api/game/{save.id}/combat/conditions/player",
            json={"condition": "poisoned"},
        )
        assert r.status_code == 200
        assert "poisoned" not in r.json()["combatant"]["conditions"]

    def test_apply_invalid_condition_returns_400(self, client, db_session):
        save = _start_combat(client, db_session)
        r = client.post(f"/api/game/{save.id}/combat/conditions/player",
                        json={"condition": "on_fire"})
        assert r.status_code == 400

    def test_apply_to_unknown_combatant_returns_404(self, client, db_session):
        save = _start_combat(client, db_session)
        r = client.post(f"/api/game/{save.id}/combat/conditions/ghost",
                        json={"condition": "poisoned"})
        assert r.status_code == 404

    def test_apply_condition_when_not_in_combat_returns_400(self, client, db_session):
        char, w = _make_char_and_world(db_session)
        save = GameSave(
            name="G", character_id=char.id, world_id=w.id,
            game_state='{"location": "town"}', story_log="[]", current_act=1, xp=0,
        )
        db_session.add(save)
        db_session.commit()
        r = client.post(f"/api/game/{save.id}/combat/conditions/player",
                        json={"condition": "poisoned"})
        assert r.status_code == 400

    def test_list_conditions_unknown_game_returns_404(self, client, db_session):
        r = client.get("/api/game/9999/combat/conditions")
        assert r.status_code == 404
