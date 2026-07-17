"""
Tests for spell-casting event integration in the /action and /action/stream
endpoints (DM function calling Phase 3).

These verify:
- DM-emitted ``cast_spell`` game_actions produce ``spell_cast`` game_events.
- A damage spell targeting an encounter combatant reduces that combatant's HP
  (dual-state coupling) and emits a follow-up ``damage`` event.
- The consumed spell slot is persisted to ``character.spells``.
- Non-casters / missing target degrade gracefully.
- The ``_available_spells_for_dm`` roster helper formats castable spells.

All DSPy-mediated LLM functions are patched so no live LLM call is made.
"""
import json
from contextlib import contextmanager
from unittest.mock import patch, AsyncMock

import pytest

from app.engine.combat import Attack, Combatant, Encounter
from app.engine.game_events import GameEventType
from app.engine.spells import Spellbook
from app.models.models import Character, World, GameSave


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wizard_spellbook_json() -> str:
    """A level-3 wizard spellbook with fire_bolt + magic_missile + cure_wounds."""
    book = Spellbook(
        char_class="wizard",
        level=3,
        known_spells=["fire_bolt"],
        prepared_spells=["magic_missile", "cure_wounds"],
        slots_used=[0] * 9,
    )
    return json.dumps(book.to_dict())


def _make_game_save_with_combat(db_session, char_class="wizard"):
    """Create a game save whose character is a caster with a live encounter."""
    kwargs = dict(
        name="Lyra", race="Elf", char_class=char_class, level=3,
        strength=8, dexterity=14, constitution=12, intelligence=18,
        wisdom=15, charisma=10, max_hp=24, current_hp=24, armor_class=13,
    )
    char = Character(**kwargs)
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

    # Build a live encounter (hero + goblin) and serialize into game_state.
    hero = Combatant(
        id="hero", name="Lyra", side="player", max_hp=24, armor_class=13,
        attacks=[Attack(name="Quarterstaff", attack_bonus=5,
                        damage_dice_count=1, damage_dice_sides=6,
                        damage_bonus=3, damage_type="bludgeoning")],
    )
    hero.current_hp = 24

    goblin = Combatant(
        id="goblin", name="Goblin Warrior", side="enemy",
        max_hp=22, armor_class=12,
        attacks=[Attack(name="Scimitar", attack_bonus=4,
                        damage_dice_count=1, damage_dice_sides=6,
                        damage_bonus=2, damage_type="slashing")],
    )
    goblin.current_hp = 22

    encounter = Encounter(combatants=[hero, goblin])
    save = GameSave(
        name="Spell Combat Test",
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
    for piece in ["The ", "wizard ", "casts!"]:
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


# Sample spell game_action dicts.
_SPELL_FIREBOLT = [
    {"function": "cast_spell", "label": "Wizard casts Fire Bolt",
     "args": {"spell_id": "fire_bolt", "target_id": "goblin"}},
]
_SPELL_MAGIC_MISSILE = [
    {"function": "cast_spell", "label": "Magic Missile",
     "args": {"spell_id": "magic_missile", "target_id": "goblin"}},
]
_SPELL_CURE_SELF = [
    {"function": "cast_spell", "label": "Cure Wounds on self",
     "args": {"spell_id": "cure_wounds"}},
]
_SPELL_UNKNOWN = [
    {"function": "cast_spell", "label": "Cast nonsense",
     "args": {"spell_id": "definitely_not_real"}},
]


# ===========================================================================
# Non-streaming /action with spells
# ===========================================================================

class TestNonStreamingSpellEvents:
    """POST /action returns spell_cast game_events from DM cast_spell actions."""

    def test_spell_cast_event_in_action_response(self, client, db_session):
        _, _, save = _make_game_save_with_combat(db_session)
        with patch("app.engine.spells.roll_d20") as mock_d20, \
             patch("app.engine.spells.roll_dice") as mock_dmg:
            from app.engine.dice import RollResult
            mock_d20.return_value = RollResult(
                rolls=[18], modifier=6, total=24, description="d20+6")
            mock_dmg.return_value = RollResult(
                rolls=[10], modifier=0, total=10, description="1d10")
            with mock_action_llm("Fire Bolt!", _SPELL_FIREBOLT):
                response = client.post(
                    f"/api/game/{save.id}/action",
                    json={"action": "I cast Fire Bolt at the goblin."},
                )
        assert response.status_code == 200
        events = response.json()["game_events"]
        spell_events = [e for e in events if e["type"] == "spell_cast"]
        assert len(spell_events) == 1
        ev = spell_events[0]
        assert ev["data"]["spell_name"] == "Fire Bolt"
        assert ev["data"]["success"] is True
        assert ev["data"]["hit"] is True
        assert ev["data"]["damage"] == 10
        assert ev["data"]["target"] == "Goblin Warrior"

    def test_spell_damage_reduces_combatant_hp_and_emits_damage_event(
        self, client, db_session
    ):
        _, _, save = _make_game_save_with_combat(db_session)
        with patch("app.engine.spells.roll_dice") as mock_dmg:
            from app.engine.dice import RollResult
            mock_dmg.return_value = RollResult(
                rolls=[3, 1, 1], modifier=3, total=5, description="3d4+3?")  # magic missile ~ varies
            with mock_action_llm("Magic Missile!", _SPELL_MAGIC_MISSILE):
                response = client.post(
                    f"/api/game/{save.id}/action",
                    json={"action": "I cast Magic Missile."},
                )
        assert response.status_code == 200
        events = response.json()["game_events"]
        types = [e["type"] for e in events]
        assert "spell_cast" in types
        assert "damage" in types  # follow-up DAMAGE event from coupling
        # The damage event target HP reflects the reduction.
        dmg_event = [e for e in events if e["type"] == "damage"][0]
        assert dmg_event["data"]["target"] == "Goblin Warrior"
        assert dmg_event["data"]["target_remaining_hp"] < 22

    def test_spell_slot_persisted_to_character(self, client, db_session):
        """A leveled spell consumes a slot persisted to character.spells."""
        char, _, save = _make_game_save_with_combat(db_session)
        with mock_action_llm("Magic Missile!", _SPELL_MAGIC_MISSILE):
            client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I cast Magic Missile."},
            )
        db_session.expire_all()
        refreshed = db_session.query(Character).filter(Character.id == char.id).first()
        book_data = json.loads(refreshed.spells)
        # A level-1 slot was consumed.
        assert book_data["slots_used"][0] == 1, book_data["slots_used"]

    def test_failed_cast_event_has_success_false(self, client, db_session):
        _, _, save = _make_game_save_with_combat(db_session)
        with mock_action_llm("Hmm.", _SPELL_UNKNOWN):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I cast nonsense."},
            )
        assert response.status_code == 200
        events = response.json()["game_events"]
        assert len(events) == 1
        assert events[0]["type"] == "spell_cast"
        assert events[0]["data"]["success"] is False
        assert events[0]["data"]["message"]

    def test_self_healing_updates_character_hp(self, client, db_session):
        """A healing spell with no target heals the character outside combat."""
        char, _, save = _make_game_save_with_combat(db_session)
        char.current_hp = 10
        db_session.commit()
        # Remove the encounter so this is out-of-combat self-healing.
        gs = json.loads(save.game_state)
        gs.pop("combat", None)
        gs["in_combat"] = False
        save.game_state = json.dumps(gs)
        db_session.commit()

        with patch("app.engine.spells.roll_dice") as mock_heal:
            from app.engine.dice import RollResult
            mock_heal.return_value = RollResult(
                rolls=[8], modifier=0, total=8, description="1d8")
            with mock_action_llm("Heal!", _SPELL_CURE_SELF):
                response = client.post(
                    f"/api/game/{save.id}/action",
                    json={"action": "I heal myself."},
                )
        assert response.status_code == 200
        events = response.json()["game_events"]
        spell_ev = [e for e in events if e["type"] == "spell_cast"][0]
        assert spell_ev["data"]["success"] is True
        assert spell_ev["data"]["healing"] == 8
        db_session.expire_all()
        refreshed = db_session.query(Character).filter(Character.id == char.id).first()
        assert refreshed.current_hp == 18  # 10 + 8

    def test_non_caster_skips_spell_action_gracefully(self, client, db_session):
        """A non-caster character skips cast_spell actions (no crash, no event)."""
        _, _, save = _make_game_save_with_combat(db_session, char_class="fighter")
        with mock_action_llm("You have no magic.", _SPELL_FIREBOLT):
            response = client.post(
                f"/api/game/{save.id}/action",
                json={"action": "I cast Fire Bolt."},
            )
        assert response.status_code == 200
        events = response.json()["game_events"]
        # Spell action skipped — no spell_cast events.
        assert all(e["type"] != "spell_cast" for e in events)


# ===========================================================================
# Streaming /action/stream with spells
# ===========================================================================

class TestStreamingSpellEvents:
    """POST /action/stream emits spell_cast game_event SSE payloads."""

    def test_streaming_emits_spell_cast_event(self, client, db_session):
        _, _, save = _make_game_save_with_combat(db_session)
        with patch("app.engine.spells.roll_d20") as mock_d20, \
             patch("app.engine.spells.roll_dice") as mock_dmg:
            from app.engine.dice import RollResult
            mock_d20.return_value = RollResult(
                rolls=[18], modifier=6, total=24, description="d20+6")
            mock_dmg.return_value = RollResult(
                rolls=[10], modifier=0, total=10, description="1d10")
            with mock_stream_llm("Fire Bolt!", _SPELL_FIREBOLT):
                response = client.post(
                    f"/api/game/{save.id}/action/stream",
                    json={"action": "I cast Fire Bolt at the goblin."},
                )
        assert response.status_code == 200
        events = _parse_sse(response.text)
        types = [e["type"] for e in events]
        assert "game_event" in types
        spell_payloads = [
            e for e in events if e["type"] == "game_event"
            and e["event"]["type"] == "spell_cast"
        ]
        assert len(spell_payloads) == 1
        assert spell_payloads[0]["event"]["data"]["spell_name"] == "Fire Bolt"

    def test_streaming_done_includes_spell_events(self, client, db_session):
        _, _, save = _make_game_save_with_combat(db_session)
        with mock_stream_llm("Magic Missile!", _SPELL_MAGIC_MISSILE):
            response = client.post(
                f"/api/game/{save.id}/action/stream",
                json={"action": "I cast Magic Missile."},
            )
        events = _parse_sse(response.text)
        done = events[-1]
        assert done["type"] == "done"
        spell_events = [e for e in done["game_events"] if e["type"] == "spell_cast"]
        assert len(spell_events) == 1

    def test_streaming_persists_spell_slot(self, client, db_session):
        """Streaming a leveled spell persists slot consumption to character.spells."""
        char, _, save = _make_game_save_with_combat(db_session)
        with mock_stream_llm("Magic Missile!", _SPELL_MAGIC_MISSILE):
            client.post(
                f"/api/game/{save.id}/action/stream",
                json={"action": "I cast Magic Missile."},
            )
        db_session.expire_all()
        refreshed = db_session.query(Character).filter(Character.id == char.id).first()
        book_data = json.loads(refreshed.spells)
        assert book_data["slots_used"][0] == 1

    def test_streaming_spell_damage_persisted_to_encounter(self, client, db_session):
        """Streaming a damage spell reduces the encounter combatant's HP."""
        _, _, save = _make_game_save_with_combat(db_session)
        with mock_stream_llm("Magic Missile!", _SPELL_MAGIC_MISSILE):
            client.post(
                f"/api/game/{save.id}/action/stream",
                json={"action": "I cast Magic Missile."},
            )
        db_session.expire_all()
        refreshed = db_session.query(GameSave).filter(GameSave.id == save.id).first()
        gs = json.loads(refreshed.game_state)
        goblin = [c for c in gs["combat"]["combatants"] if c["id"] == "goblin"][0]
        assert goblin["current_hp"] < 22  # took damage


# ===========================================================================
# _available_spells_for_dm helper
# ===========================================================================

class TestAvailableSpellsRosterHelper:
    """The roster builder formats castable spells for DM context."""

    def test_roster_for_caster(self):
        from app.api.game import _available_spells_for_dm
        char = Character(
            name="Lyra", race="Elf", char_class="wizard", level=3,
            strength=8, dexterity=14, constitution=12, intelligence=18,
            wisdom=15, charisma=10, max_hp=24, current_hp=24, armor_class=13,
        )
        char.spells = _wizard_spellbook_json()
        roster = _available_spells_for_dm(char)
        assert "AVAILABLE_SPELLS:" in roster
        assert "fire_bolt" in roster
        assert "Fire Bolt" in roster
        assert "REMAINING_SLOTS" in roster

    def test_roster_empty_for_non_caster(self):
        from app.api.game import _available_spells_for_dm
        char = Character(
            name="Bruenor", race="Dwarf", char_class="fighter", level=3,
            strength=16, dexterity=12, constitution=16, intelligence=10,
            wisdom=10, charisma=10, max_hp=30, current_hp=30, armor_class=16,
        )
        assert _available_spells_for_dm(char) == ""

    def test_roster_empty_when_no_spells(self):
        from app.api.game import _available_spells_for_dm
        char = Character(
            name="Lyra", race="Elf", char_class="wizard", level=1,
            strength=8, dexterity=14, constitution=12, intelligence=18,
            wisdom=15, charisma=10, max_hp=24, current_hp=24, armor_class=13,
        )
        # No spells column content.
        char.spells = "{}"
        assert _available_spells_for_dm(char) == ""
