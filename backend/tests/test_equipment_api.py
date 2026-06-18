"""
API integration tests for equipment-driven combat.

Verifies that:
- The inventory ``/combat-stats`` endpoint returns gear-derived AC + attacks.
- Equipping a shield via the inventory API raises the character's AC.
- Starting combat with an equipped custom weapon builds the player's attack from
  the *weapon's* damage dice (not the legacy class-based list).
"""
import pytest
from fastapi.testclient import TestClient

from app.models.models import Character, World, GameSave


def _make_character(db_session, **overrides) -> Character:
    """Create and commit a character with sensible defaults."""
    defaults = dict(
        name="Test Hero",
        race="Human",
        char_class="Fighter",
        level=1,
        strength=16,
        dexterity=14,
        constitution=14,
        intelligence=10,
        wisdom=10,
        charisma=10,
        max_hp=12,
        current_hp=12,
        armor_class=10,
        speed=30,
    )
    defaults.update(overrides)
    char = Character(**defaults)
    db_session.add(char)
    db_session.flush()
    return char


def _make_game(db_session, character: Character) -> GameSave:
    w = World(
        name="Test World",
        description="A world for testing.",
        world_data='{"starting_settlement": {"name": "Test Town"}}',
        tone="heroic fantasy",
    )
    db_session.add(w)
    db_session.flush()
    save = GameSave(
        name="Test Game",
        character_id=character.id,
        world_id=w.id,
        game_state='{"location": "Test Town"}',
        story_log="[]",
        current_act=1,
        xp=0,
    )
    db_session.add(save)
    db_session.commit()
    return save


# --------------------------------------------------------------------------- #
# combat-stats endpoint
# --------------------------------------------------------------------------- #

class TestCombatStatsEndpoint:
    def test_combat_stats_unarmed_character(self, client: TestClient, db_session):
        """A character with no inventory gets unarmored AC + unarmed strike."""
        char = _make_character(db_session, dexterity=14)
        db_session.commit()

        resp = client.get(f"/api/characters/{char.id}/combat-stats")
        assert resp.status_code == 200
        data = resp.json()
        # Unarmored: 10 + Dex(2) = 12.
        assert data["armor_class"] == 12
        assert data["weapon"] is None
        # At least an unarmed strike.
        assert any(a["name"] == "Unarmed Strike" for a in data["attacks"])

    def test_combat_stats_with_equipment(self, client: TestClient, db_session):
        char = _make_character(db_session, strength=16, dexterity=14)
        db_session.commit()

        # Add a magic battleaxe and equip it.
        add = client.post(
            f"/api/characters/{char.id}/items",
            json={
                "name": "Battleaxe",
                "item_type": "weapon",
                "rarity": "uncommon",
                "value": 50,
                "weight": 4.0,
                "damage_dice": "1d8",
                "damage_type": "slashing",
                "attack_bonus": 1,  # +1 magic
            },
        )
        assert add.status_code == 200
        weapon_id = add.json()["slots"][-1]["item"]["id"]
        equip = client.post(f"/api/characters/{char.id}/equip/{weapon_id}")
        assert equip.status_code == 200

        resp = client.get(f"/api/characters/{char.id}/combat-stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["weapon"] == "Battleaxe"
        assert data["weapon_magic_bonus"] == 1
        # Str 16 (+3) + prof 2 + magic 1 = 6.
        primary = data["attacks"][0]
        assert primary["name"] == "Battleaxe"
        assert primary["attack_bonus"] == 6
        assert primary["damage_dice_count"] == 1
        assert primary["damage_dice_sides"] == 8
        assert primary["ranged"] is False

    def test_combat_stats_404_unknown_character(self, client: TestClient, db_session):
        resp = client.get("/api/characters/999999/combat-stats")
        assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Shield via inventory API raises AC
# --------------------------------------------------------------------------- #

class TestShieldEquipAC:
    def test_equipping_shield_increases_ac(self, client: TestClient, db_session):
        char = _make_character(db_session, dexterity=14)
        db_session.commit()

        # Add + equip leather armor first.
        armor = client.post(
            f"/api/characters/{char.id}/items",
            json={
                "name": "Leather Armor",
                "item_type": "armor",
                "armor_type": "light",
                "value": 10,
                "weight": 10.0,
            },
        )
        armor_id = armor.json()["slots"][-1]["item"]["id"]
        client.post(f"/api/characters/{char.id}/equip/{armor_id}")

        ac_before = client.get(f"/api/characters/{char.id}/combat-stats").json()["armor_class"]
        # Leather: 11 + Dex(2) = 13.
        assert ac_before == 13

        # Add + equip a shield.
        shield = client.post(
            f"/api/characters/{char.id}/items",
            json={
                "name": "Shield",
                "item_type": "armor",
                "armor_type": "shield",
                "armor_bonus": 2,
                "value": 10,
                "weight": 6.0,
            },
        )
        shield_id = shield.json()["slots"][-1]["item"]["id"]
        equip_resp = client.post(f"/api/characters/{char.id}/equip/{shield_id}")
        assert equip_resp.status_code == 200
        # The response surfaces the shield.
        assert equip_resp.json()["equipped_shield"] is not None
        # And body armor is still equipped.
        assert equip_resp.json()["equipped_armor"] is not None

        ac_after = client.get(f"/api/characters/{char.id}/combat-stats").json()["armor_class"]
        # 13 + shield(2) = 15.
        assert ac_after == 15

    def test_unequipping_shield_lowers_ac(self, client: TestClient, db_session):
        char = _make_character(db_session, dexterity=14)
        db_session.commit()
        shield = client.post(
            f"/api/characters/{char.id}/items",
            json={"name": "Shield", "item_type": "armor", "armor_type": "shield", "armor_bonus": 2},
        )
        shield_id = shield.json()["slots"][-1]["item"]["id"]
        client.post(f"/api/characters/{char.id}/equip/{shield_id}")
        assert client.get(f"/api/characters/{char.id}/combat-stats").json()["armor_class"] == 14

        client.post(f"/api/characters/{char.id}/unequip/{shield_id}")
        # Back to unarmored 10 + Dex(2) = 12.
        assert client.get(f"/api/characters/{char.id}/combat-stats").json()["armor_class"] == 12


# --------------------------------------------------------------------------- #
# Combat start uses the equipped weapon
# --------------------------------------------------------------------------- #

class TestCombatStartUsesEquipment:
    def test_player_attack_uses_equipped_weapon(self, client: TestClient, db_session):
        """The player's combat attack must come from the equipped weapon, not
        the legacy hardcoded class list."""
        char = _make_character(db_session, char_class="Fighter", strength=16, dexterity=12)
        db_session.commit()

        # Give the fighter a distinctly-named custom weapon.
        add = client.post(
            f"/api/characters/{char.id}/items",
            json={
                "name": "Warhammer",
                "item_type": "weapon",
                "rarity": "common",
                "value": 15,
                "damage_dice": "1d8",
                "damage_type": "bludgeoning",
                "attack_bonus": 0,
            },
        )
        weapon_id = add.json()["slots"][-1]["item"]["id"]
        client.post(f"/api/characters/{char.id}/equip/{weapon_id}")

        save = _make_game(db_session, char)

        resp = client.post(
            f"/api/game/{save.id}/combat/start",
            json={"enemies": [{"name": "Goblin", "max_hp": 7, "armor_class": 12, "attacks": []}]},
        )
        assert resp.status_code == 200
        encounter = resp.json()["encounter"]
        player = next(c for c in encounter["combatants"] if c["id"] == "player")

        attack_names = [a["name"] for a in player["attacks"]]
        assert "Warhammer" in attack_names
        # The legacy "Longsword" must NOT be present when a weapon is equipped.
        assert "Longsword" not in attack_names

        warhammer = next(a for a in player["attacks"] if a["name"] == "Warhammer")
        # Str 16 (+3) + prof 2 = 5 attack, 1d8 bludgeoning, damage bonus 3.
        assert warhammer["attack_bonus"] == 5
        assert warhammer["damage_dice_count"] == 1
        assert warhammer["damage_dice_sides"] == 8
        assert warhammer["damage_bonus"] == 3
        assert warhammer["damage_type"] == "bludgeoning"

    def test_player_ac_reflects_equipped_armor_and_shield(self, client: TestClient, db_session):
        char = _make_character(db_session, char_class="Fighter", strength=16, dexterity=10)
        db_session.commit()

        chain = client.post(
            f"/api/characters/{char.id}/items",
            json={"name": "Chain Mail", "item_type": "armor", "armor_type": "heavy", "value": 75},
        )
        chain_id = chain.json()["slots"][-1]["item"]["id"]
        client.post(f"/api/characters/{char.id}/equip/{chain_id}")

        shield = client.post(
            f"/api/characters/{char.id}/items",
            json={"name": "Shield", "item_type": "armor", "armor_type": "shield", "armor_bonus": 2},
        )
        shield_id = shield.json()["slots"][-1]["item"]["id"]
        client.post(f"/api/characters/{char.id}/equip/{shield_id}")

        save = _make_game(db_session, char)
        resp = client.post(
            f"/api/game/{save.id}/combat/start",
            json={"enemies": [{"name": "Goblin", "max_hp": 7, "armor_class": 12, "attacks": []}]},
        )
        assert resp.status_code == 200
        player = next(
            c for c in resp.json()["encounter"]["combatants"] if c["id"] == "player"
        )
        # Chain mail (16) + shield (2) = 18.
        assert player["armor_class"] == 18

    def test_combat_falls_back_for_unequipped_character(self, client: TestClient, db_session):
        """A character with no inventory keeps the legacy class-based attacks
        and stored AC (no regression)."""
        char = _make_character(db_session, char_class="Fighter", armor_class=16)
        db_session.commit()
        save = _make_game(db_session, char)

        resp = client.post(
            f"/api/game/{save.id}/combat/start",
            json={"enemies": [{"name": "Goblin", "max_hp": 7, "armor_class": 12, "attacks": []}]},
        )
        assert resp.status_code == 200
        player = next(
            c for c in resp.json()["encounter"]["combatants"] if c["id"] == "player"
        )
        attack_names = [a["name"] for a in player["attacks"]]
        assert "Longsword" in attack_names  # legacy fallback
        assert player["armor_class"] == 16  # stored AC

    def test_initialize_fighter_gives_shield_ac(self, client: TestClient, db_session):
        """Initializing a fighter's inventory now equips a shield → AC 18."""
        char = _make_character(db_session, char_class="Fighter", dexterity=10)
        db_session.commit()

        resp = client.post(f"/api/characters/{char.id}/initialize")
        assert resp.status_code == 200
        # Chain mail (16) + shield (2) = 18.
        assert resp.json()["inventory"]["equipped_shield"] is not None

        # The character's stored AC should reflect armor + shield.
        db_session.refresh(char)
        assert char.armor_class == 18


# --------------------------------------------------------------------------- #
# Explicit inventory endpoint
# --------------------------------------------------------------------------- #

class TestInventoryExplicitEndpoint:
    def test_explicit_inventory_path_matches_base(self, client: TestClient, db_session):
        """The new GET /{character_id}/inventory path returns the same data
        as the base endpoint (now shadowed by the characters router)."""
        char = _make_character(db_session, strength=16, dexterity=14)
        db_session.commit()

        # Add a few items to have something to show.
        client.post(
            f"/api/characters/{char.id}/items",
            json={"name": "Sword", "item_type": "weapon", "damage_dice": "1d8", "damage_type": "slashing"},
        )
        client.post(
            f"/api/characters/{char.id}/items",
            json={"name": "Potion", "item_type": "potion", "uses": 1},
        )

        # Get via the explicit path (unambiguous).
        resp = client.get(f"/api/characters/{char.id}/inventory")
        assert resp.status_code == 200
        data = resp.json()

        # Expected structure.
        assert "slots" in data
        assert "total_weight" in data
        assert "total_value" in data
        assert "equipped_weapon" in data
        assert "equipped_armor" in data
        assert "equipped_shield" in data

        # Should have 2 items.
        assert len(data["slots"]) == 2
        names = {s["item"]["name"] for s in data["slots"]}
        assert "Sword" in names
        assert "Potion" in names

    def test_explicit_inventory_path_404(self, client: TestClient, db_session):
        resp = client.get("/api/characters/999999/inventory")
        assert resp.status_code == 404
