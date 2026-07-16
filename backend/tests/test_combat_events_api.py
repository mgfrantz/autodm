"""
Tests for combat event integration in the /action and /action/stream endpoints.

These verify:
- DM-emitted combat game_actions (attack, damage, roll_initiative) produce
  the correct ATTACK/DAMAGE/INITIATIVE game_events in API responses.
- The encounter state is persisted to game_state["combat"] after resolution.
- Graceful degradation: combat actions are skipped (not crashed) when no
  encounter is loaded.
- The _combatant_roster_for_dm helper builds the correct roster string.

All DSPy-mediated LLM functions are patched so no live LLM call is made.
"""
import json
from contextlib import contextmanager
from unittest.mock import patch, AsyncMock

import pytest

from app.engine.combat import Attack, Combatant, Encounter
from app.engine.game_events import GameEventType
from app.models.models import GameSave


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game_save_with_combat(db_session):
    """Create a game save whose game_state contains a live encounter."""
    char = __import__("app.models.models", fromlist=["Character"]).Character(
        name="Lyra", race="Elf", char_class="Wizard", level=3,
        strength=8, dexterity=14, constitution=12, intelligence=18,
        wisdom=15, charisma=10, max_hp=24, current_hp=24, armor_class=13,
    )
    World = __import__("app.models.models", fromlist=["World"]).World
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

    # Build a live encounter and serialize it into game_state
    hero = Combatant(
        id="hero", name="Lyra", side="player", max_hp=24, armor_class=13,
        attacks=[Attack(name="Quarterstaff", attack_bonus=5,
                        damage_dice_count=1, damage_dice_sides=6,
                        damage_bonus=3, damage_type="bludgeoning")],
    )
    hero.current_hp = 24

    goblin = Combatant(
        id="goblin", name="Goblin Warrior", side="enemy",
        max_hp=12, armor_class=13,
        attacks=[Attack(name="Scimitar", attack_bonus=4,
                        damage_dice_count=1, damage_dice_sides=6,
                        damage_bonus=2, damage_type="slashing")],
    )
    goblin.current_hp = 12

    encounter = Encounter(combatants=[hero, goblin])
    combat_data = encounter.to_dict()

    save = GameSave(
        name="Combat Test",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps({
            "location": "Dungeon",
            "visited_locations": ["Dungeon"],
            "conditions": [],
            "in_combat": True,
            "combat": combat_data,
        }),
        story_log=json.dumps([]),
    )
    db_session.add(save)
    db_session.commit()
    db_session.refresh(save)
    return char, world, save


def _parse_sse(text):
    """Parse a raw SSE response body into a list of event payloads."""
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
    for piece in ["The ", "goblin ", "attacks!"]:
        yield piece


@contextmanager
def mock_action_llm(narration="The goblin attacks.", game_actions=None):
    with patch("app.api.game._dm_actionable_narrate", new=AsyncMock(
        return_value=(narration, game_actions or [])
    )), \
    patch("app.api.game._resolve_skill_check", return_value={}), \
    patch("app.api.game._detect_and_update_quests", side_effect=lambda n, gs: (gs, [])), \
    patch("app.api.game._detect_and_update_npc_mood", side_effect=lambda n, gs: gs), \
    patch("app.api.game._detect_and_update_game_flags", side_effect=lambda n, gs: gs), \
    patch("app.api.game._generate_action_suggestions", return_value=["Attack"]):
        yield


@contextmanager
def mock_stream_llm(narration="The goblin attacks.", game_actions=None):
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


# Sample combat game_action dicts.
_COMBAT_ATTACK_ACTION = [
    {"function": "attack", "label": "Goblin attacks Hero",
     "args": {"attacker_id": "goblin", "target_id": "hero"}},
]
_COMBAT_DAMAGE_ACTION = [
    {"function": "damage", "label": "Hero takes fire damage",
     "args": {"target_id": "goblin", "amount": 5, "damage_type": "fire"}},
]
_COMBAT_INITIATIVE_ACTION = [
    {"function": "roll_initiative", "label": "Roll initiative", "args": {}},
]
_MIXED_ACTIONS = [
    {"function": "roll_dice", "label": "Perception",
     "args": {"sides": 20, "modifier": 3}},
    {"function": "damage", "label": "Fire damage",
     "args": {"target_id": "goblin", "amount": 4}},
]


# ===========================================================================
# Non-streaming /action with combat
# ===========================================================================

class TestNonStreamingCombatEvents:
    """POST /action returns combat game_events from DM-emitted combat actions."""

    def test_attack_event_in_action_response(self, client, db_session):
        _, _, save = _make_game_save_with_combat(db_session)
        with patch("app.engine.combat.roll_d20") as mock_d20, \
             patch("app.engine.combat.roll_dice") as mock_dmg:
            mock_d20.return_value = __import__(
                "app.engine.dice", fromlist=["RollResult"]
            ).RollResult(rolls=[15], modifier=4, total=19, description="d20+4")
            mock_dmg.return_value = __import__(
                "app.engine.dice", fromlist=["RollResult"]
            ).RollResult(rolls=[5], modifier=2, total=7, description="1d6+2")
            with mock_action_llm("The goblin strikes!", _COMBAT_ATTACK_ACTION):
                response = client.post(
                    f"/api/game/{save.id}/action",
                    json={"action": "The goblin attacks me."},
                )
        assert response.status_code == 200
        events = response.json()["game_events"]
        assert len(events) == 1
        assert events[0]["type"] == "attack"
        assert events[0]["data"]["hit"] is True
        assert events[0]["data"]["damage"] == 7

    def test_damage_event_in_action_response(self, client, db_session):
        _, _, save = _make_game_save_with_combat(db_session)
        with mock_action_llm("Burn!", _COMBAT_DAMAGE_ACTION):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I cast fire."},
            )
        assert response.status_code == 200
        events = response.json()["game_events"]
        assert len(events) == 1
        assert events[0]["type"] == "damage"
        assert events[0]["data"]["amount"] == 5
        assert events[0]["data"]["damage_type"] == "fire"

    def test_initiative_event_in_action_response(self, client, db_session):
        _, _, save = _make_game_save_with_combat(db_session)
        with patch("app.engine.combat.roll_d20") as mock_d20:
            mock_d20.side_effect = [
                __import__("app.engine.dice", fromlist=["RollResult"]).RollResult(
                    rolls=[14], modifier=0, total=14, description="d20"),
                __import__("app.engine.dice", fromlist=["RollResult"]).RollResult(
                    rolls=[8], modifier=0, total=8, description="d20"),
            ]
            with mock_action_llm("Roll initiative!", _COMBAT_INITIATIVE_ACTION):
                response = client.post(
                    f"/api/game/{save.id}/action",
                    json={"action": "Roll for initiative."},
                )
        assert response.status_code == 200
        events = response.json()["game_events"]
        assert len(events) == 1
        assert events[0]["type"] == "initiative"
        assert len(events[0]["data"]["combatants"]) == 2

    def test_encounter_persisted_after_combat(self, client, db_session):
        """After a damage action, the encounter HP change is persisted to game_state."""
        _, _, save = _make_game_save_with_combat(db_session)
        with mock_action_llm("Burn!", _COMBAT_DAMAGE_ACTION):
            client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I cast fire."},
            )
        # Re-read the save from DB
        db_session.expire_all()
        refreshed = db_session.query(GameSave).filter(GameSave.id == save.id).first()
        gs = json.loads(refreshed.game_state)
        combat = gs["combat"]
        # Find goblin's HP — should be 12 - 5 = 7
        goblin = [c for c in combat["combatants"] if c["id"] == "goblin"][0]
        assert goblin["current_hp"] == 7

    def test_mixed_combat_and_noncombat_events(self, client, db_session):
        """Dice roll + damage action produce events of different types."""
        _, _, save = _make_game_save_with_combat(db_session)
        with mock_action_llm("You sense danger!", _MIXED_ACTIONS):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I look around and cast fire."},
            )
        assert response.status_code == 200
        events = response.json()["game_events"]
        assert len(events) == 2
        assert events[0]["type"] == "dice_roll"
        assert events[1]["type"] == "damage"

    def test_graceful_skip_combat_without_encounter(self, client, db_session):
        """Combat actions are silently skipped when no encounter exists."""
        # Create a save WITHOUT combat in game_state
        from app.models.models import Character, World
        char = Character(
            name="Lyra", race="Elf", char_class="Wizard", level=3,
            strength=8, dexterity=14, constitution=12, intelligence=18,
            wisdom=15, charisma=10, max_hp=24, current_hp=24, armor_class=13,
        )
        world = World(name="Vale", description="desc", world_data="{}",
                      tone="heroic")
        db_session.add(char)
        db_session.add(world)
        db_session.commit()
        db_session.refresh(char)
        db_session.refresh(world)
        save = GameSave(
            name="No Combat",
            character_id=char.id, world_id=world.id,
            game_state=json.dumps({"location": "Tavern", "in_combat": False}),
            story_log=json.dumps([]),
        )
        db_session.add(save)
        db_session.commit()
        db_session.refresh(save)

        with mock_action_llm("You're safe.", _COMBAT_ATTACK_ACTION):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I attack the air."},
            )
        assert response.status_code == 200
        # Combat action is skipped — no events
        events = response.json()["game_events"]
        assert events == []


# ===========================================================================
# Streaming /action/stream with combat
# ===========================================================================

class TestStreamingCombatEvents:
    """POST /action/stream emits combat game_event SSE payloads."""

    def test_streaming_emits_attack_event(self, client, db_session):
        _, _, save = _make_game_save_with_combat(db_session)
        with patch("app.engine.combat.roll_d20") as mock_d20, \
             patch("app.engine.combat.roll_dice") as mock_dmg:
            RollResult = __import__(
                "app.engine.dice", fromlist=["RollResult"]).RollResult
            mock_d20.return_value = RollResult(
                rolls=[15], modifier=4, total=19, description="d20+4")
            mock_dmg.return_value = RollResult(
                rolls=[5], modifier=2, total=7, description="1d6+2")
            with mock_stream_llm("The goblin strikes!", _COMBAT_ATTACK_ACTION):
                response = client.post(
                    f"/api/game/{save.id}/action/stream",
                    json={"action": "The goblin attacks."},
                )
        assert response.status_code == 200
        events = _parse_sse(response.text)
        types = [e["type"] for e in events]
        assert "game_event" in types
        game_event_idx = types.index("game_event")
        assert events[game_event_idx]["event"]["type"] == "attack"

    def test_streaming_done_includes_combat_events(self, client, db_session):
        _, _, save = _make_game_save_with_combat(db_session)
        with mock_stream_llm("Burn!", _COMBAT_DAMAGE_ACTION):
            response = client.post(
                f"/api/game/{save.id}/action/stream",
                json={"action": "I cast fire."},
            )
        events = _parse_sse(response.text)
        done = events[-1]
        assert done["type"] == "done"
        assert len(done["game_events"]) == 1
        assert done["game_events"][0]["type"] == "damage"

    def test_streaming_persists_combat_state(self, client, db_session):
        """After streaming a damage action, encounter HP is persisted."""
        _, _, save = _make_game_save_with_combat(db_session)
        with mock_stream_llm("Burn!", _COMBAT_DAMAGE_ACTION):
            client.post(
                f"/api/game/{save.id}/action/stream",
                json={"action": "I cast fire."},
            )
        db_session.expire_all()
        refreshed = db_session.query(GameSave).filter(GameSave.id == save.id).first()
        gs = json.loads(refreshed.game_state)
        goblin = [c for c in gs["combat"]["combatants"] if c["id"] == "goblin"][0]
        assert goblin["current_hp"] == 7  # 12 - 5

    def test_streaming_combat_skipped_without_encounter(self, client, db_session):
        """Combat actions in streaming are skipped when no encounter exists."""
        from app.models.models import Character, World
        char = Character(
            name="Lyra", race="Elf", char_class="Wizard", level=3,
            strength=8, dexterity=14, constitution=12, intelligence=18,
            wisdom=15, charisma=10, max_hp=24, current_hp=24, armor_class=13,
        )
        world = World(name="Vale", description="desc", world_data="{}",
                      tone="heroic")
        db_session.add(char)
        db_session.add(world)
        db_session.commit()
        db_session.refresh(char)
        db_session.refresh(world)
        save = GameSave(
            name="No Combat Stream",
            character_id=char.id, world_id=world.id,
            game_state=json.dumps({"location": "Tavern", "in_combat": False}),
            story_log=json.dumps([]),
        )
        db_session.add(save)
        db_session.commit()
        db_session.refresh(save)

        with mock_stream_llm("You're safe.", _COMBAT_ATTACK_ACTION):
            response = client.post(
                f"/api/game/{save.id}/action/stream",
                json={"action": "I attack."},
            )
        assert response.status_code == 200
        events = _parse_sse(response.text)
        done = events[-1]
        assert done["game_events"] == []


# ===========================================================================
# _combatant_roster_for_dm helper
# ===========================================================================

class TestCombatantRosterHelper:
    """The roster builder formats combatants for DM context."""

    def test_roster_with_encounter(self):
        from app.api.game import _combatant_roster_for_dm
        encounter = Encounter(combatants=[
            Combatant(id="hero", name="Lyra", side="player", max_hp=24,
                      armor_class=13),
            Combatant(id="gob1", name="Goblin", side="enemy", max_hp=12,
                      armor_class=13),
        ])
        encounter.combatants[0].current_hp = 20
        encounter.combatants[1].current_hp = 12
        gs = {"combat": encounter.to_dict()}
        roster = _combatant_roster_for_dm(gs)
        assert "COMBATANT_ROSTER:" in roster
        assert "hero" in roster
        assert "Lyra" in roster
        assert "gob1" in roster
        assert "Use these IDs" in roster

    def test_roster_empty_when_no_combat(self):
        from app.api.game import _combatant_roster_for_dm
        assert _combatant_roster_for_dm({}) == ""
        assert _combatant_roster_for_dm({"combat": None}) == ""

    def test_roster_empty_when_no_combatants(self):
        from app.api.game import _combatant_roster_for_dm
        encounter = Encounter(combatants=[])
        gs = {"combat": encounter.to_dict()}
        assert _combatant_roster_for_dm(gs) == ""

    def test_roster_includes_hp_and_ac(self):
        from app.api.game import _combatant_roster_for_dm
        encounter = Encounter(combatants=[
            Combatant(id="orc", name="Orc", side="enemy", max_hp=15,
                      armor_class=12),
        ])
        encounter.combatants[0].current_hp = 8
        gs = {"combat": encounter.to_dict()}
        roster = _combatant_roster_for_dm(gs)
        assert "8/15" in roster
        assert "AC: 12" in roster
