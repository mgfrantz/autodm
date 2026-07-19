"""
Tests for condition/exhaustion-aware saving throws in the DM-resolved spell-save
paths (single-target + AoE).

Closes the cross-phase polish item flagged in PROGRESS.md's NEXT SESSION
DIRECTIVE: "advantage/disadvantage on AoE saves". The DM-resolved spell-save
helpers (``_combatant_save_total`` / ``_character_save_total``) previously
rolled a plain d20 and ignored the PHB save modifiers that the coded
``saving_throws`` engine already implements:

- **Auto-fail** — paralyzed / petrified / unconscious creatures auto-fail
  Strength and Dexterity saves (PHB p.290-292).
- **Disadvantage** — Restrained imposes Dex-save disadvantage; Exhaustion
  level 3+ imposes disadvantage on *all* saves (PHB p.291, p.291 Exhaustion).

The fix routes both helpers through a new ``_roll_save_total`` that mirrors
``engine.saving_throws.check_save_auto_fail`` / ``check_save_disadvantage``.
Combatants carry their own ``.conditions`` / ``.exhaustion``; the player's
conditions (``game_state["conditions"]``) and exhaustion
(``game_state["exhaustion"]``) are threaded into the AoE call site.

These tests verify:
- ``_roll_save_total`` rule logic (auto-fail, disadvantage, backward-compat).
- ``_combatant_save_total`` reads the combatant's own conditions/exhaustion.
- ``_character_save_total`` threads the conditions/exhaustion params.
- End-to-end: a paralyzed AoE target auto-fails its save (full damage) even
  when the dice are mocked high — proving the wiring through the real API.

All DSPy-mediated LLM functions are patched so no live LLM call is made.
"""
import json
from unittest.mock import patch, AsyncMock

from app.engine.combat import Attack, Combatant, Encounter
from app.engine.dice import RollResult
from app.engine.spells import Spellbook
from app.models.models import Character, World, GameSave


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #

def _wizard_spellbook_json() -> str:
    book = Spellbook(
        char_class="wizard", level=5, known_spells=["fire_bolt"],
        prepared_spells=["fireball"], slots_used=[0] * 9,
    )
    return json.dumps(book.to_dict())


def _make_game_save_with_goblins(db_session, char_class="wizard"):
    """A level-5 wizard with a live encounter of 3 goblins."""
    char = Character(
        name="Lyra", race="Elf", char_class=char_class, level=5,
        strength=8, dexterity=14, constitution=12, intelligence=18,
        wisdom=15, charisma=10, max_hp=28, current_hp=28, armor_class=13,
    )
    if char_class == "wizard":
        char.spells = _wizard_spellbook_json()

    world = World(
        name="The Shattered Vale", description="A land broken by ancient magic.",
        world_data=json.dumps({
            "description": "A land broken by ancient magic.",
            "starting_settlement": {"name": "Oakhaven"},
            "hook": "A strange light pulses.",
        }),
        tone="heroic fantasy",
    )
    db_session.add(char)
    db_session.add(world)
    db_session.commit()
    db_session.refresh(char)
    db_session.refresh(world)

    hero = Combatant(
        id="hero", name="Lyra", side="player", max_hp=28, armor_class=13,
        attacks=[Attack(name="Quarterstaff", attack_bonus=5,
                        damage_dice_count=1, damage_dice_sides=6,
                        damage_bonus=3, damage_type="bludgeoning")],
    )
    hero.current_hp = 28

    goblins = []
    for i in range(1, 4):
        g = Combatant(
            id=f"goblin_{i}", name=f"Goblin {i}", side="enemy",
            max_hp=22, armor_class=12, dexterity=14,
            attacks=[Attack(name="Scimitar", attack_bonus=4,
                            damage_dice_count=1, damage_dice_sides=6,
                            damage_bonus=2, damage_type="slashing")],
        )
        g.current_hp = 22
        goblins.append(g)

    encounter = Encounter(combatants=[hero, *goblins])
    save = GameSave(
        name="Save Conditions Test", character_id=char.id, world_id=world.id,
        game_state=json.dumps({
            "location": "Dungeon", "visited_locations": ["Dungeon"],
            "conditions": [], "exhaustion": 0,
            "in_combat": True, "combat": encounter.to_dict(),
        }),
        story_log=json.dumps([]),
    )
    db_session.add(save)
    db_session.commit()
    db_session.refresh(save)
    return char, world, save


def _aoe_with_player(extra_targets=None):
    ids = ["player"]
    if extra_targets:
        ids.extend(extra_targets)
    return [{"function": "cast_spell_aoe", "label": "Boom",
             "args": {"spell_id": "fireball", "target_ids": ids}}]


def _set_combatant_field(game_state_json, combatant_id, field, value):
    """Set a field on a serialized combatant inside game_state['combat']."""
    gs = json.loads(game_state_json)
    for c in gs["combat"]["combatants"]:
        if c["id"] == combatant_id:
            c[field] = value
    return json.dumps(gs)


def _save_action_llm(game_actions):
    """Patch the /action narration + side-effect helpers."""
    from contextlib import contextmanager

    @contextmanager
    def _ctx(narration="The spell erupts!", actions=None):
        with patch("app.api.game._dm_actionable_narrate", new=AsyncMock(
            return_value=(narration, actions or game_actions)
        )), \
        patch("app.api.game._resolve_skill_check", return_value={}), \
        patch("app.api.game._detect_and_update_quests", side_effect=lambda n, gs: (gs, [])), \
        patch("app.api.game._detect_and_update_npc_mood", side_effect=lambda n, gs: gs), \
        patch("app.api.game._detect_and_update_game_flags", side_effect=lambda n, gs: gs), \
        patch("app.api.game._generate_action_suggestions", return_value=["Cast"]):
            yield
    return _ctx


# =========================================================================== #
# _roll_save_total — pure rule logic
# =========================================================================== #

class TestRollSaveTotalRuleLogic:
    """Unit-test the shared save-total helper in isolation."""

    def _call(self, **kwargs):
        from app.api.game import _roll_save_total
        return _roll_save_total(**kwargs)

    def test_no_conditions_straight_roll(self):
        """No conditions / exhaustion → plain d20 + bonus (backward-compat)."""
        with patch("app.api.game.roll_d20") as mock:
            mock.return_value = RollResult(
                rolls=[11], modifier=3, total=14, description="x")
            total = self._call(bonus=3, save_ability="dexterity",
                               conditions=[], exhaustion=0)
        assert total == 14
        # No advantage/disadvantage modifiers passed.
        assert mock.call_args.kwargs.get("disadvantage") is False
        assert mock.call_args.kwargs.get("advantage") is False

    def test_paralyzed_dex_save_auto_fails(self):
        """Paralyzed → Dex save auto-fails (returns 0, no roll)."""
        with patch("app.api.game.roll_d20") as mock:
            total = self._call(bonus=5, save_ability="dexterity",
                               conditions=["paralyzed"], exhaustion=0)
        assert total == 0
        mock.assert_not_called()  # auto-fail short-circuits before rolling

    def test_petrified_str_save_auto_fails(self):
        with patch("app.api.game.roll_d20") as mock:
            total = self._call(bonus=2, save_ability="strength",
                               conditions=["petrified"], exhaustion=0)
        assert total == 0
        mock.assert_not_called()

    def test_unconscious_dex_save_auto_fails(self):
        with patch("app.api.game.roll_d20") as mock:
            total = self._call(bonus=1, save_ability="dexterity",
                               conditions=["unconscious"], exhaustion=0)
        assert total == 0
        mock.assert_not_called()

    def test_paralyzed_con_save_does_NOT_auto_fail(self):
        """Auto-fail only applies to Str/Dex — Con save rolls normally."""
        with patch("app.api.game.roll_d20") as mock:
            mock.return_value = RollResult(
                rolls=[12], modifier=3, total=15, description="x")
            total = self._call(bonus=3, save_ability="constitution",
                               conditions=["paralyzed"], exhaustion=0)
        assert total == 15
        mock.assert_called_once()

    def test_restrained_dex_save_disadvantage(self):
        """Restrained → Dexterity save disadvantage."""
        with patch("app.api.game.roll_d20") as mock:
            mock.return_value = RollResult(
                rolls=[8], modifier=2, total=10, description="x")
            self._call(bonus=2, save_ability="dexterity",
                       conditions=["restrained"], exhaustion=0)
        assert mock.call_args.kwargs.get("disadvantage") is True

    def test_restrained_str_save_no_disadvantage(self):
        """Restrained only imposes Dex-save disadvantage, not Str."""
        with patch("app.api.game.roll_d20") as mock:
            mock.return_value = RollResult(
                rolls=[10], modifier=2, total=12, description="x")
            self._call(bonus=2, save_ability="strength",
                       conditions=["restrained"], exhaustion=0)
        assert mock.call_args.kwargs.get("disadvantage") is False

    def test_exhaustion_3_imposes_disadvantage_on_all_saves(self):
        """Exhaustion level 3+ → disadvantage on every save."""
        for ability in ("strength", "dexterity", "constitution",
                        "intelligence", "wisdom", "charisma"):
            with patch("app.api.game.roll_d20") as mock:
                mock.return_value = RollResult(
                    rolls=[10], modifier=0, total=10, description="x")
                self._call(bonus=0, save_ability=ability,
                           conditions=[], exhaustion=3)
            assert mock.call_args.kwargs.get("disadvantage") is True, ability

    def test_exhaustion_2_no_disadvantage(self):
        """Exhaustion threshold is 3 — level 2 has no save disadvantage."""
        with patch("app.api.game.roll_d20") as mock:
            mock.return_value = RollResult(
                rolls=[10], modifier=0, total=10, description="x")
            self._call(bonus=0, save_ability="dexterity",
                       conditions=[], exhaustion=2)
        assert mock.call_args.kwargs.get("disadvantage") is False

    def test_condition_case_insensitive(self):
        """Conditions are lowercased defensively — 'Paralyzed' auto-fails too."""
        with patch("app.api.game.roll_d20") as mock:
            total = self._call(bonus=5, save_ability="dexterity",
                               conditions=["PARALYZED"], exhaustion=0)
        assert total == 0

    def test_no_save_ability_straight_roll(self):
        """No save ability (e.g. auto-damage spell) → plain roll, no checks."""
        with patch("app.api.game.roll_d20") as mock:
            mock.return_value = RollResult(
                rolls=[10], modifier=0, total=10, description="x")
            total = self._call(bonus=0, save_ability=None,
                               conditions=["paralyzed"], exhaustion=5)
        assert total == 10
        assert mock.call_args.kwargs.get("disadvantage") is False


# =========================================================================== #
# _combatant_save_total — reads the combatant's own conditions/exhaustion
# =========================================================================== #

class TestCombatantSaveTotalThreading:
    """The combatant helper reads ``.conditions`` / ``.exhaustion`` off the
    combatant object (not from external game_state)."""

    def _goblin(self, **kw):
        g = Combatant(
            id="g1", name="Goblin", side="enemy", max_hp=22,
            armor_class=12, dexterity=14,
        )
        for k, v in kw.items():
            setattr(g, k, v)
        return g

    def test_clean_combatant_backward_compat(self):
        """Combatant with no conditions/exhaustion → plain ability-mod roll."""
        from app.api.game import _combatant_save_total
        with patch("app.api.game.roll_d20") as mock:
            mock.return_value = RollResult(
                rolls=[10], modifier=2, total=12, description="x")
            total = _combatant_save_total(self._goblin(), "dexterity")
        # Dex 14 → +2 modifier.
        assert mock.call_args.kwargs.get("modifier") == 2
        assert mock.call_args.kwargs.get("disadvantage") is False
        assert total == 12

    def test_paralyzed_combatant_dex_save_auto_fails(self):
        from app.api.game import _combatant_save_total
        with patch("app.api.game.roll_d20") as mock:
            total = _combatant_save_total(
                self._goblin(conditions=["paralyzed"]), "dexterity")
        assert total == 0
        mock.assert_not_called()

    def test_restrained_combatant_dex_disadvantage(self):
        from app.api.game import _combatant_save_total
        with patch("app.api.game.roll_d20") as mock:
            mock.return_value = RollResult(
                rolls=[10], modifier=2, total=12, description="x")
            _combatant_save_total(
                self._goblin(conditions=["restrained"]), "dexterity")
        assert mock.call_args.kwargs.get("disadvantage") is True

    def test_exhausted_combatant_disadvantage(self):
        from app.api.game import _combatant_save_total
        with patch("app.api.game.roll_d20") as mock:
            mock.return_value = RollResult(
                rolls=[10], modifier=2, total=12, description="x")
            _combatant_save_total(self._goblin(exhaustion=4), "constitution")
        assert mock.call_args.kwargs.get("disadvantage") is True


# =========================================================================== #
# _character_save_total — threads conditions/exhaustion params
# =========================================================================== #

class TestCharacterSaveTotalThreading:
    """The player helper honours the conditions/exhaustion kwargs."""

    def _char(self):
        return Character(
            name="Lyra", race="Elf", char_class="wizard", level=5,
            strength=8, dexterity=14, constitution=12, intelligence=18,
            wisdom=15, charisma=10, max_hp=28, current_hp=28, armor_class=13,
        )

    def test_default_no_conditions_backward_compat(self):
        from app.api.game import _character_save_total
        with patch("app.engine.saving_throws.calculate_save_bonus",
                   return_value=4), \
             patch("app.api.game.roll_d20") as mock:
            mock.return_value = RollResult(
                rolls=[10], modifier=4, total=14, description="x")
            total = _character_save_total(self._char(), "dexterity")
        assert total == 14
        assert mock.call_args.kwargs.get("disadvantage") is False

    def test_restrained_player_dex_disadvantage(self):
        from app.api.game import _character_save_total
        with patch("app.engine.saving_throws.calculate_save_bonus",
                   return_value=4), \
             patch("app.api.game.roll_d20") as mock:
            mock.return_value = RollResult(
                rolls=[10], modifier=4, total=14, description="x")
            _character_save_total(
                self._char(), "dexterity",
                conditions=["restrained"], exhaustion=0)
        assert mock.call_args.kwargs.get("disadvantage") is True

    def test_paralyzed_player_dex_auto_fails(self):
        from app.api.game import _character_save_total
        with patch("app.engine.saving_throws.calculate_save_bonus",
                   return_value=6), \
             patch("app.api.game.roll_d20") as mock:
            total = _character_save_total(
                self._char(), "dexterity",
                conditions=["paralyzed"], exhaustion=0)
        assert total == 0
        mock.assert_not_called()

    def test_exhausted_player_disadvantage(self):
        from app.api.game import _character_save_total
        with patch("app.engine.saving_throws.calculate_save_bonus",
                   return_value=3), \
             patch("app.api.game.roll_d20") as mock:
            mock.return_value = RollResult(
                rolls=[10], modifier=3, total=13, description="x")
            _character_save_total(
                self._char(), "constitution",
                conditions=[], exhaustion=3)
        assert mock.call_args.kwargs.get("disadvantage") is True


# =========================================================================== #
# End-to-end via the /action AoE API path
# =========================================================================== #

class TestAoeSaveConditionsEndToEnd:
    """Integration: conditioned AoE targets auto-fail / suffer disadvantage."""

    def test_paralyzed_goblin_auto_fails_aoe_save(self, client, db_session):
        """A paralyzed goblin auto-fails the Fireball Dex save even when the
        dice are mocked high — proving the combatant-side wiring."""
        char, _, save = _make_game_save_with_goblins(db_session)
        # Paralyze goblin_1 in the serialized encounter.
        save.game_state = _set_combatant_field(
            save.game_state, "goblin_1", "conditions", ["paralyzed"])
        db_session.commit()

        action = [{"function": "cast_spell_aoe", "label": "Fireball",
                   "args": {"spell_id": "fireball",
                            "target_ids": ["goblin_1", "goblin_2"]}}]
        ctx = _save_action_llm(action)
        with patch("app.engine.spells.Spell.roll_damage", return_value=20), \
             patch("app.api.game.roll_d20") as mock_save, ctx("Boom!"):
            # Mocked high save total (30 ≥ DC ~15) would normally SAVE.
            mock_save.return_value = RollResult(
                rolls=[25], modifier=5, total=30, description="save")
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "The wizard hurls a fireball."},
            )
        assert response.status_code == 200
        events = response.json()["game_events"]
        dmg = [e["data"] for e in events if e["type"] == "damage"]
        by_target = {d["target"]: d for d in dmg}
        # Goblin 1 is paralyzed → auto-fail → FULL damage (20) despite the
        # mocked high roll.
        assert by_target["Goblin 1"]["made_save"] is False
        assert by_target["Goblin 1"]["amount"] == 20
        # Goblin 2 is clean → mocked 30 saves → HALF damage (10).
        assert by_target["Goblin 2"]["made_save"] is True
        assert by_target["Goblin 2"]["amount"] == 10

    def test_exhausted_player_save_rolled_with_disadvantage(
        self, client, db_session
    ):
        """An exhausted (level 3+) player can still cast (exhaustion only
        blocks casting at level 6 = death) but rolls all saves at
        disadvantage — verified by inspecting the roll_d20 call kwargs."""
        char, _, save = _make_game_save_with_goblins(db_session)
        gs = json.loads(save.game_state)
        gs["exhaustion"] = 3  # all saves at disadvantage
        save.game_state = json.dumps(gs)
        db_session.commit()

        ctx = _save_action_llm(_aoe_with_player())
        with patch("app.engine.spells.Spell.roll_damage", return_value=20), \
             patch("app.api.game.roll_d20") as mock_save, ctx("Stagger!"):
            mock_save.return_value = RollResult(
                rolls=[10], modifier=2, total=12, description="save")
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "Exhausted, I hurl the fireball."},
            )
        assert response.status_code == 200
        # The player's AoE save must be rolled at disadvantage (exhaustion 3+).
        disadvantage_calls = [
            c for c in mock_save.call_args_list
            if c.kwargs.get("disadvantage") is True
        ]
        assert disadvantage_calls, [
            c.kwargs for c in mock_save.call_args_list]
        # Player took damage (the cast succeeded — exhaustion doesn't block it).
        dmg = [e for e in response.json()["game_events"]
               if e["type"] == "damage"]
        assert len(dmg) == 1

    def test_restrained_player_save_rolled_with_disadvantage(
        self, client, db_session
    ):
        """A restrained player's AoE Dex save is rolled at disadvantage —
        verified by inspecting the roll_d20 call kwargs (the outcome is
        mocked, so we assert the modifier flag, not the result)."""
        _, _, save = _make_game_save_with_goblins(db_session)
        gs = json.loads(save.game_state)
        gs["conditions"] = ["restrained"]
        save.game_state = json.dumps(gs)
        db_session.commit()

        ctx = _save_action_llm(_aoe_with_player())
        with patch("app.engine.spells.Spell.roll_damage", return_value=20), \
             patch("app.api.game.roll_d20") as mock_save, ctx("Dive!"):
            mock_save.return_value = RollResult(
                rolls=[10], modifier=2, total=12, description="save")
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I try to dodge the blast."},
            )
        assert response.status_code == 200
        # At least one roll_d20 call was made with disadvantage=True (the
        # player's Dex save against the AoE).
        disadvantage_calls = [
            c for c in mock_save.call_args_list
            if c.kwargs.get("disadvantage") is True
        ]
        assert disadvantage_calls, [
            c.kwargs for c in mock_save.call_args_list]
