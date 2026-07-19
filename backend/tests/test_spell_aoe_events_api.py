"""
Tests for AoE spell-casting event integration in the /action and /action/stream
endpoints (DM function calling Phase 3.5b — AoE multi-target resolution).

Verifies:
- DM-emitted ``cast_spell_aoe`` game_actions produce ONE ``spell_cast`` summary
  event (``is_aoe=True``) + N per-target ``damage`` events.
- Exactly ONE spell slot is consumed and persisted (not one per target).
- Each target rolls its own save (half/full damage split), and its combatant HP
  is reduced in the encounter.
- AoE concentration spells (Cloudkill) start concentration once.
- Graceful degradation: no encounter / empty target_ids → failed summary event.
- Streaming emits + parses the events over SSE.

All DSPy-mediated LLM functions are patched so no live LLM call is made.
"""
import json
from contextlib import contextmanager
from unittest.mock import patch, AsyncMock

from app.engine.combat import Attack, Combatant, Encounter
from app.engine.spells import Spellbook
from app.models.models import Character, World, GameSave


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wizard_spellbook_json() -> str:
    """A level-5 wizard spellbook with fire_bolt + fireball + cloudkill."""
    book = Spellbook(
        char_class="wizard",
        level=5,
        known_spells=["fire_bolt"],
        prepared_spells=["fireball", "cloudkill"],
        slots_used=[0] * 9,
    )
    return json.dumps(book.to_dict())


def _make_game_save_with_three_goblins(db_session, char_class="wizard"):
    """Create a game save whose caster has a live encounter with 3 goblins."""
    char = Character(
        name="Lyra", race="Elf", char_class=char_class, level=5,
        strength=8, dexterity=14, constitution=12, intelligence=18,
        wisdom=15, charisma=10, max_hp=28, current_hp=28, armor_class=13,
    )
    if char_class == "wizard":
        char.spells = _wizard_spellbook_json()

    world = World(
        name="The Shattered Vale",
        description="A land broken by ancient magic.",
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
        name="AoE Combat Test",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps({
            "location": "Dungeon",
            "visited_locations": ["Dungeon"],
            "conditions": [],
            "in_combat": True,
            "combat": encounter.to_dict(),
        }),
        story_log=json.dumps([]),
    )
    db_session.add(save)
    db_session.commit()
    db_session.refresh(save)
    return char, world, save


def _parse_sse(text):
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        for line in block.split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    return events


async def _fake_stream(*_args, **_kwargs):
    for piece in ["The ", "fireball ", "explodes!"]:
        yield piece


@contextmanager
def mock_action_llm(narration="The wizard casts a spell.", game_actions=None):
    with patch("app.api.game._dm_actionable_narrate", new=AsyncMock(
        return_value=(narration, game_actions or [])
    )), \
    patch("app.api.game._resolve_skill_check", return_value={}), \
    patch("app.api.game._detect_and_update_quests", side_effect=lambda n, gs: (gs, [])), \
    patch("app.api.game._detect_and_update_npc_mood", side_effect=lambda n, gs: gs), \
    patch("app.api.game._detect_and_update_game_flags", side_effect=lambda n, gs: gs), \
    patch("app.api.game._generate_action_suggestions", return_value=["Cast"]):
        yield


@contextmanager
def mock_stream_llm(narration="The wizard casts a spell.", game_actions=None):
    with patch("app.api.game.stream_narration_dspy", new=_fake_stream), \
    patch("app.api.game._dm_actionable_narrate", new=AsyncMock(
        return_value=(narration, game_actions or [])
    )), \
    patch("app.api.game._resolve_skill_check", return_value={}), \
    patch("app.api.game._detect_and_update_quests", side_effect=lambda n, gs: (gs, [])), \
    patch("app.api.game._detect_and_update_npc_mood", side_effect=lambda n, gs: gs), \
    patch("app.api.game._detect_and_update_game_flags", side_effect=lambda n, gs: gs), \
    patch("app.api.game._generate_action_suggestions", return_value=[]):
        yield


# Sample AoE game_action dicts.
_AOE_FIREBALL = [
    {"function": "cast_spell_aoe", "label": "Fireball engulfs the goblins",
     "args": {"spell_id": "fireball",
              "target_ids": ["goblin_1", "goblin_2", "goblin_3"]}},
]
_AOE_FIREBALL_TWO = [
    {"function": "cast_spell_aoe", "label": "Fireball",
     "args": {"spell_id": "fireball", "target_ids": ["goblin_1", "goblin_2"]}},
]
_AOE_NO_TARGETS = [
    {"function": "cast_spell_aoe", "label": "Fireball",
     "args": {"spell_id": "fireball", "target_ids": []}},
]
_AOE_CLOUDKILL = [
    {"function": "cast_spell_aoe", "label": "Cloudkill",
     "args": {"spell_id": "cloudkill",
              "target_ids": ["goblin_1", "goblin_2"]}},
]


# ===========================================================================
# Non-streaming /action with AoE spells
# ===========================================================================

class TestNonStreamingAoeSpellEvents:
    def test_aoe_emits_one_summary_and_per_target_damage_events(
        self, client, db_session
    ):
        """Fireball at 3 goblins → 1 spell_cast summary + 3 damage events."""
        _, _, save = _make_game_save_with_three_goblins(db_session)
        # Patch damage (rolled once) + saves (rolled per target).
        with patch("app.engine.spells.Spell.roll_damage", return_value=30), \
             patch("app.api.game.roll_d20") as mock_save:
            from app.engine.dice import RollResult
            # Goblin 1 saves (total 20 ≥ DC), goblin 2 fails (5), goblin 3 saves (20).
            mock_save.side_effect = [
                RollResult(rolls=[18], modifier=2, total=20, description="save"),
                RollResult(rolls=[3], modifier=2, total=5, description="save"),
                RollResult(rolls=[18], modifier=2, total=20, description="save"),
            ]
            with mock_action_llm("Fireball!", _AOE_FIREBALL):
                response = client.post(
                    f"/api/game/{save.id}/action",
                    json={"action": "I cast Fireball at the goblins."},
                )
        assert response.status_code == 200
        events = response.json()["game_events"]
        types = [e["type"] for e in events]

        # ONE spell_cast summary + THREE damage events.
        assert types.count("spell_cast") == 1
        assert types.count("damage") == 3
        summary = [e for e in events if e["type"] == "spell_cast"][0]
        assert summary["data"]["is_aoe"] is True
        assert summary["data"]["target_count"] == 3
        assert summary["data"]["slot_level"] == 3
        assert summary["data"]["success"] is True
        # total = 15 (half) + 30 (full) + 15 (half) = 60
        assert summary["data"]["total_damage"] == 60
        # Fireball is not a concentration spell.
        assert not summary["data"].get("concentration_started")

        # Per-target damage events carry save outcome.
        dmg_by_target = {e["data"]["target"]: e["data"] for e in events
                         if e["type"] == "damage"}
        assert "Goblin 1" in dmg_by_target
        assert "Goblin 2" in dmg_by_target
        assert "Goblin 3" in dmg_by_target
        # Goblin 1 saved → half (15) + made_save True.
        assert dmg_by_target["Goblin 1"]["amount"] == 15
        assert dmg_by_target["Goblin 1"]["made_save"] is True
        assert dmg_by_target["Goblin 1"]["half_damage"] is True
        # Goblin 2 failed → full (30) + made_save False.
        assert dmg_by_target["Goblin 2"]["amount"] == 30
        assert dmg_by_target["Goblin 2"]["made_save"] is False

    def test_aoe_consumes_one_slot_and_persists(self, client, db_session):
        """Exactly ONE L3 slot is consumed (not one per target), persisted."""
        char, _, save = _make_game_save_with_three_goblins(db_session)
        with patch("app.engine.spells.Spell.roll_damage", return_value=20), \
             patch("app.api.game.roll_d20") as mock_save:
            from app.engine.dice import RollResult
            mock_save.return_value = RollResult(
                rolls=[2], modifier=2, total=4, description="save")
            with mock_action_llm("Fireball!", _AOE_FIREBALL_TWO):
                response = client.post(
                    f"/api/game/{save.id}/action",
                    json={"action": "I cast Fireball."},
                )
        assert response.status_code == 200
        db_session.expire_all()
        refreshed = db_session.query(Character).filter(
            Character.id == char.id).first()
        book_data = json.loads(refreshed.spells)
        # ONE L3 slot consumed (index 2), not two.
        assert book_data["slots_used"][2] == 1, book_data["slots_used"]

    def test_aoe_reduces_each_combatant_hp(self, client, db_session):
        """Each goblin's HP is reduced by its per-target damage."""
        _, _, save = _make_game_save_with_three_goblins(db_session)
        with patch("app.engine.spells.Spell.roll_damage", return_value=30), \
             patch("app.api.game.roll_d20") as mock_save:
            from app.engine.dice import RollResult
            mock_save.return_value = RollResult(
                rolls=[2], modifier=2, total=4, description="save")  # all fail
            with mock_action_llm("Fireball!", _AOE_FIREBALL):
                response = client.post(
                    f"/api/game/{save.id}/action",
                    json={"action": "I cast Fireball."},
                )
        events = response.json()["game_events"]
        dmg_events = [e["data"] for e in events if e["type"] == "damage"]
        # All three took 30 full damage → 22 - 30 = clamped to ≤ 0 (defeated).
        for d in dmg_events:
            assert d["amount"] == 30
            assert d["target_remaining_hp"] <= 0

    def test_aoe_no_encounter_emits_failed_summary(self, client, db_session):
        """cast_spell_aoe without an active encounter → failed summary event."""
        _, _, save = _make_game_save_with_three_goblins(db_session)
        # Remove the encounter.
        gs = json.loads(save.game_state)
        gs.pop("combat", None)
        gs["in_combat"] = False
        save.game_state = json.dumps(gs)
        db_session.commit()

        with mock_action_llm("Fireball!", _AOE_FIREBALL):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I cast Fireball."},
            )
        assert response.status_code == 200
        events = response.json()["game_events"]
        summary = [e for e in events if e["type"] == "spell_cast"]
        assert len(summary) == 1
        assert summary[0]["data"]["success"] is False
        assert "target_ids" in summary[0]["data"]["message"].lower() or \
               "encounter" in summary[0]["data"]["message"].lower()
        # No damage events.
        assert all(e["type"] != "damage" for e in events)

    def test_aoe_empty_target_ids_emits_failed_summary(
        self, client, db_session
    ):
        """Empty target_ids → failed summary, no slot consumed."""
        char, _, save = _make_game_save_with_three_goblins(db_session)
        with mock_action_llm("Fireball!", _AOE_NO_TARGETS):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I cast Fireball."},
            )
        assert response.status_code == 200
        events = response.json()["game_events"]
        summary = [e for e in events if e["type"] == "spell_cast"]
        assert len(summary) == 1
        assert summary[0]["data"]["success"] is False
        # No slot consumed on failure.
        db_session.expire_all()
        refreshed = db_session.query(Character).filter(
            Character.id == char.id).first()
        book_data = json.loads(refreshed.spells)
        assert book_data["slots_used"][2] == 0

    def test_aoe_unknown_target_id_skipped(self, client, db_session):
        """An unknown target_id is skipped; valid ones still resolve."""
        _, _, save = _make_game_save_with_three_goblins(db_session)
        action = [{
            "function": "cast_spell_aoe", "label": "Fireball",
            "args": {"spell_id": "fireball",
                     "target_ids": ["goblin_1", "ghost_not_real", "goblin_2"]},
        }]
        with patch("app.engine.spells.Spell.roll_damage", return_value=20), \
             patch("app.api.game.roll_d20") as mock_save:
            from app.engine.dice import RollResult
            mock_save.return_value = RollResult(
                rolls=[2], modifier=2, total=4, description="save")
            with mock_action_llm("Fireball!", action):
                response = client.post(
                    f"/api/game/{save.id}/action",
                    json={"action": "I cast Fireball."},
                )
        assert response.status_code == 200
        events = response.json()["game_events"]
        summary = [e for e in events if e["type"] == "spell_cast"][0]
        assert summary["data"]["success"] is True
        # Only the 2 valid targets counted.
        assert summary["data"]["target_count"] == 2
        dmg = [e for e in events if e["type"] == "damage"]
        assert len(dmg) == 2

    def test_aoe_concentration_spell_starts_concentration(
        self, client, db_session
    ):
        """Cloudkill (AoE concentration spell) starts concentration once."""
        char, _, save = _make_game_save_with_three_goblins(db_session)
        # Cloudkill is L5; bump the wizard to L9 for L5 slots + prepare it.
        char.level = 9
        book = Spellbook(
            char_class="wizard", level=9, known_spells=["fire_bolt"],
            prepared_spells=["fireball", "cloudkill"], slots_used=[0] * 9)
        char.spells = json.dumps(book.to_dict())
        db_session.commit()

        with patch("app.engine.spells.Spell.roll_damage", return_value=20), \
             patch("app.api.game.roll_d20") as mock_save:
            from app.engine.dice import RollResult
            mock_save.return_value = RollResult(
                rolls=[2], modifier=2, total=4, description="save")
            with mock_action_llm("Cloudkill!", _AOE_CLOUDKILL):
                response = client.post(
                    f"/api/game/{save.id}/action",
                    json={"action": "I cast Cloudkill."},
                )
        assert response.status_code == 200
        events = response.json()["game_events"]
        summary = [e for e in events if e["type"] == "spell_cast"][0]
        assert summary["data"]["success"] is True
        assert summary["data"].get("concentration_started") is True
        # A concentration event was emitted.
        conc = [e for e in events if e["type"] == "concentration"]
        assert len(conc) >= 1
        # game_state persisted concentration.
        gs = json.loads(
            db_session.query(GameSave).filter(GameSave.id == save.id).first().game_state
        )
        assert gs.get("concentration", {}).get("spell_id") == "cloudkill"


# ===========================================================================
# Streaming /action/stream with AoE spells
# ===========================================================================

class TestStreamingAoeSpellEvents:
    def test_streaming_emits_aoe_events(self, client, db_session):
        """POST /action/stream emits the spell_cast summary + damage SSE events."""
        _, _, save = _make_game_save_with_three_goblins(db_session)
        with patch("app.engine.spells.Spell.roll_damage", return_value=24), \
             patch("app.api.game.roll_d20") as mock_save:
            from app.engine.dice import RollResult
            mock_save.side_effect = [
                RollResult(rolls=[18], modifier=2, total=20, description="s"),
                RollResult(rolls=[3], modifier=2, total=5, description="s"),
            ]
            with mock_stream_llm("Fireball!", _AOE_FIREBALL_TWO):
                response = client.post(
                    f"/api/game/{save.id}/action/stream",
                    json={"action": "I cast Fireball."},
                )
        assert response.status_code == 200
        events = _parse_sse(response.text)
        types = [e.get("type") for e in events]
        # game_event payloads carry the typed events.
        game_events = [e for e in events if e.get("type") == "game_event"]
        payload_types = []
        for ge in game_events:
            ev = ge.get("event", ge)
            payload_types.append(ev.get("type"))
        assert "spell_cast" in payload_types
        assert payload_types.count("damage") == 2


# ===========================================================================
# Cross-phase polish: player as an AoE target (concentration coupling)
# ===========================================================================
#
# "player" is a valid target_id in cast_spell_aoe — the player is not an
# encounter combatant (HP lives on the Character), so routing their AoE damage
# through character.current_hp and firing a concentration check mirrors the
# plain `damage` action's player path. These tests verify that coupling.

def _aoe_with_player(extra_targets=None):
    """cast_spell_aoe action that includes the player in the blast radius."""
    ids = ["player"]
    if extra_targets:
        ids.extend(extra_targets)
    return [{
        "function": "cast_spell_aoe", "label": "Fireball catches the hero",
        "args": {"spell_id": "fireball", "target_ids": ids},
    }]


class TestPlayerAsAoeTarget:
    """The player can be a valid AoE target; damage routes to character HP."""

    def test_player_aoe_target_takes_full_damage(self, client, db_session):
        """Player fails the save → full damage, HP reduced on the Character."""
        char, _, save = _make_game_save_with_three_goblins(db_session)
        with patch("app.engine.spells.Spell.roll_damage", return_value=20), \
             patch("app.api.game.roll_d20") as mock_save:
            from app.engine.dice import RollResult
            # Player Dex save total 4 (< DC 15) → fail → full damage.
            mock_save.return_value = RollResult(
                rolls=[2], modifier=2, total=4, description="save")
            with mock_action_llm("Caught in the blast!", _aoe_with_player()):
                response = client.post(
                    f"/api/game/{save.id}/action",
                    json={"action": "The trap explodes!"},
                )
        assert response.status_code == 200
        events = response.json()["game_events"]
        # One AoE spell_cast summary + one damage event on the player.
        assert sum(1 for e in events if e["type"] == "spell_cast") == 1
        dmg = [e for e in events if e["type"] == "damage"]
        assert len(dmg) == 1
        assert dmg[0]["data"]["target"] == "Lyra"
        assert dmg[0]["data"]["amount"] == 20
        assert dmg[0]["data"]["made_save"] is False
        # HP reduced on the Character (28 → 8), not a combatant.
        db_session.expire_all()
        refreshed = db_session.query(Character).filter(
            Character.id == char.id).first()
        assert int(refreshed.current_hp) == 8

    def test_player_aoe_target_makes_save_half_damage(self, client, db_session):
        """Player makes the save → half damage + made_save/half flags set."""
        _, _, save = _make_game_save_with_three_goblins(db_session)
        with patch("app.engine.spells.Spell.roll_damage", return_value=20), \
             patch("app.api.game.roll_d20") as mock_save:
            from app.engine.dice import RollResult
            # Player Dex save total 20 (≥ DC 15) → save → half damage.
            mock_save.return_value = RollResult(
                rolls=[18], modifier=2, total=20, description="save")
            with mock_action_llm("Dive!", _aoe_with_player()):
                response = client.post(
                    f"/api/game/{save.id}/action",
                    json={"action": "I dive away."},
                )
        events = response.json()["game_events"]
        dmg = [e for e in events if e["type"] == "damage"]
        assert len(dmg) == 1
        assert dmg[0]["data"]["amount"] == 10  # half of 20
        assert dmg[0]["data"]["made_save"] is True
        assert dmg[0]["data"]["half_damage"] is True

    def test_player_aoe_damage_fires_concentration_check(
        self, client, db_session
    ):
        """Player concentrating + AoE damage → a concentration check event."""
        from app.engine.concentration import ConcentrationState

        char, _, save = _make_game_save_with_three_goblins(db_session)
        # Put the player in a concentrating state.
        gs = json.loads(save.game_state)
        gs["concentration"] = ConcentrationState(
            spell_name="Bless", spell_id="bless", is_concentrating=True,
        ).to_dict()
        save.game_state = json.dumps(gs)
        db_session.commit()

        with patch("app.engine.spells.Spell.roll_damage", return_value=20), \
             patch("app.api.game.roll_d20") as mock_save:
            from app.engine.dice import RollResult
            mock_save.return_value = RollResult(
                rolls=[2], modifier=2, total=4, description="save")
            with mock_action_llm("The blast hits you!", _aoe_with_player()):
                response = client.post(
                    f"/api/game/{save.id}/action",
                    json={"action": "I'm caught!"},
                )
        assert response.status_code == 200
        events = response.json()["game_events"]
        # A concentration check event was emitted with the AoE damage amount.
        checks = [
            e for e in events
            if e["type"] == "concentration"
            and e["data"].get("operation") in ("check_passed", "check_failed")
        ]
        assert len(checks) == 1, [e.get("data") for e in events
                                  if e["type"] == "concentration"]
        assert checks[0]["data"]["damage_taken"] == 20

    def test_player_and_combatant_mixed_aoe_targets(self, client, db_session):
        """Player + goblin both targeted → both damaged via their own paths."""
        char, _, save = _make_game_save_with_three_goblins(db_session)
        action = _aoe_with_player(extra_targets=["goblin_1"])
        with patch("app.engine.spells.Spell.roll_damage", return_value=20), \
             patch("app.api.game.roll_d20") as mock_save:
            from app.engine.dice import RollResult
            # Both fail their saves (return_value applies to every roll).
            mock_save.return_value = RollResult(
                rolls=[2], modifier=2, total=4, description="save")
            with mock_action_llm("Fireball!", action):
                response = client.post(
                    f"/api/game/{save.id}/action",
                    json={"action": "I cast Fireball recklessly."},
                )
        assert response.status_code == 200
        events = response.json()["game_events"]
        summary = [e for e in events if e["type"] == "spell_cast"][0]
        assert summary["data"]["success"] is True
        assert summary["data"]["target_count"] == 2
        # Two damage events: one player, one goblin.
        dmg = [e["data"] for e in events if e["type"] == "damage"]
        targets = {d["target"] for d in dmg}
        assert targets == {"Lyra", "Goblin 1"}
        # Player HP reduced on the Character.
        db_session.expire_all()
        refreshed = db_session.query(Character).filter(
            Character.id == char.id).first()
        assert int(refreshed.current_hp) == 8  # 28 - 20
        # Goblin HP reduced in the persisted encounter.
        gs = json.loads(
            db_session.query(GameSave).filter(
                GameSave.id == save.id).first().game_state
        )
        gobs = [c for c in gs["combat"]["combatants"] if c["id"] == "goblin_1"]
        assert gobs and gobs[0]["current_hp"] == 2  # 22 - 20

    def test_streaming_player_aoe_target_emits_damage(self, client, db_session):
        """Streaming endpoint also routes player AoE damage correctly."""
        char, _, save = _make_game_save_with_three_goblins(db_session)
        with patch("app.engine.spells.Spell.roll_damage", return_value=16), \
             patch("app.api.game.roll_d20") as mock_save:
            from app.engine.dice import RollResult
            mock_save.return_value = RollResult(
                rolls=[2], modifier=2, total=4, description="save")
            with mock_stream_llm("Boom!", _aoe_with_player()):
                response = client.post(
                    f"/api/game/{save.id}/action/stream",
                    json={"action": "It explodes!"},
                )
        assert response.status_code == 200
        events = _parse_sse(response.text)
        game_events = [e for e in events if e.get("type") == "game_event"]
        payloads = [ge.get("event", ge) for ge in game_events]
        dmg = [p for p in payloads if p.get("type") == "damage"]
        assert len(dmg) == 1
        assert dmg[0]["data"]["target"] == "Lyra"
        assert dmg[0]["data"]["amount"] == 16
