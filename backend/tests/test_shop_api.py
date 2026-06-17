"""
Tests for the shop / economy API endpoints.

Covers the overview, lazy merchant generation, buying/selling with gold + stock
persistence, every failure mode (insufficient gold, wrong merchant, no stock,
in-combat guard, 404), restock, story logging, and starting gold on creation.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.models.models import Character, World, GameSave


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def game(client: TestClient, db_session):
    """A fighter game with some gold and a town settlement tier."""
    char = Character(
        name="Borin", race="Dwarf", char_class="Fighter", level=3,
        classes=json.dumps({"fighter": 3}),
        strength=16, dexterity=12, constitution=14, intelligence=10,
        wisdom=10, charisma=10,
        max_hp=30, current_hp=30, armor_class=16, speed=25,
        gold=500,
    )
    db_session.add(char)
    db_session.flush()

    w = World(
        name="Test World", description="A world.",
        world_data='{"starting_settlement": {"name": "Oakhaven"}}', tone="heroic",
    )
    db_session.add(w)
    db_session.flush()

    save = GameSave(
        name="Test Game", character_id=char.id, world_id=w.id,
        game_state=json.dumps({
            "location": "Oakhaven", "in_combat": False, "settlement_tier": "town",
        }),
        story_log="[]",
    )
    db_session.add(save)
    db_session.commit()
    return save


def _first_stock_item(client: TestClient, game_id: int, merchant_type: str) -> dict:
    """Helper: fetch a merchant and return its first stock entry."""
    r = client.get(f"/api/game/{game_id}/shop/{merchant_type}")
    assert r.status_code == 200, r.text
    return r.json()["stock"][0]


# --------------------------------------------------------------------------- #
# GET /shop overview
# --------------------------------------------------------------------------- #

class TestShopOverview:
    def test_overview_returns_gold_and_merchants(self, client: TestClient, game):
        r = client.get(f"/api/game/{game.id}/shop")
        assert r.status_code == 200
        data = r.json()
        assert data["character_name"] == "Borin"
        assert data["gold"] == 500
        assert data["settlement_tier"] == "town"
        merchant_keys = {m["merchant_type"] for m in data["merchants"]}
        assert {"blacksmith", "alchemist", "general", "arcane", "fletcher"} <= merchant_keys
        # None visited yet
        assert all(m["visited"] is False for m in data["merchants"])

    def test_overview_404(self, client: TestClient):
        assert client.get("/api/game/9999/shop").status_code == 404


# --------------------------------------------------------------------------- #
# GET /shop/{merchant_type}
# --------------------------------------------------------------------------- #

class TestGetMerchant:
    def test_get_merchant_generates_stock(self, client: TestClient, game):
        r = client.get(f"/api/game/{game.id}/shop/blacksmith")
        assert r.status_code == 200
        data = r.json()
        assert data["merchant_type"] == "blacksmith"
        assert data["label"] == "Blacksmith"
        assert data["settlement_tier"] == "town"
        assert data["gold"] > 0
        assert len(data["stock"]) >= 5
        # Each stock entry has a buy price >= 0
        for entry in data["stock"]:
            assert "buy_price" in entry
            assert entry["buy_price"] >= 0
            assert entry["quantity"] >= 1

    def test_get_merchant_marks_visited(self, client: TestClient, game):
        client.get(f"/api/game/{game.id}/shop/blacksmith")
        overview = client.get(f"/api/game/{game.id}/shop").json()
        smith = next(m for m in overview["merchants"] if m["merchant_type"] == "blacksmith")
        assert smith["visited"] is True

    def test_unknown_merchant_type_falls_back_to_general(self, client: TestClient, game):
        r = client.get(f"/api/game/{game.id}/shop/nonsense")
        assert r.status_code == 200
        assert r.json()["merchant_type"] == "general"

    def test_get_merchant_404(self, client: TestClient):
        assert client.get("/api/game/9999/shop/blacksmith").status_code == 404

    def test_merchant_gold_is_town_reserve(self, client: TestClient, game):
        from app.engine.shop import SETTLEMENT_TIERS
        r = client.get(f"/api/game/{game.id}/shop/blacksmith")
        assert r.json()["gold"] == SETTLEMENT_TIERS["town"].gold_reserve


# --------------------------------------------------------------------------- #
# POST /buy
# --------------------------------------------------------------------------- #

class TestBuy:
    def test_buy_success(self, client: TestClient, game):
        entry = _first_stock_item(client, game.id, "blacksmith")
        item_id = entry["item"]["id"]
        price = entry["buy_price"]

        r = client.post(f"/api/game/{game.id}/shop/blacksmith/buy",
                        json={"item_id": item_id, "quantity": 1})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["transaction_type"] == "buy"
        assert data["unit_price"] == price
        assert data["total"] == price
        assert data["gold"] == 500 - price
        # Item is now in the player's inventory
        names = [s["item"]["name"] for s in data["inventory"]["slots"]]
        assert entry["item"]["name"] in names

    def test_buy_persists_gold(self, client: TestClient, game):
        entry = _first_stock_item(client, game.id, "blacksmith")
        client.post(f"/api/game/{game.id}/shop/blacksmith/buy",
                    json={"item_id": entry["item"]["id"]})
        # Re-fetch the character to confirm gold persisted
        char = client.get(f"/api/characters/{game.character_id}").json()
        assert char["gold"] == 500 - entry["buy_price"]

    def test_buy_decreases_merchant_stock(self, client: TestClient, game):
        entry = _first_stock_item(client, game.id, "blacksmith")
        start_qty = entry["quantity"]
        client.post(f"/api/game/{game.id}/shop/blacksmith/buy",
                    json={"item_id": entry["item"]["id"]})
        after = client.get(f"/api/game/{game.id}/shop/blacksmith").json()
        same = next((e for e in after["stock"] if e["item"]["name"] == entry["item"]["name"]), None)
        # Either quantity dropped by 1, or the line was removed if it was the last
        if same is not None:
            assert same["quantity"] == start_qty - 1
        else:
            assert start_qty == 1

    def test_buy_insufficient_gold(self, client: TestClient, game, db_session):
        # Drain the character's gold
        game.character.gold = 1
        db_session.commit()
        entry = _first_stock_item(client, game.id, "blacksmith")
        r = client.post(f"/api/game/{game.id}/shop/blacksmith/buy",
                        json={"item_id": entry["item"]["id"]})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False
        assert "need" in data["message"].lower()
        assert data["gold"] == 1

    def test_buy_unknown_item(self, client: TestClient, game):
        r = client.post(f"/api/game/{game.id}/shop/blacksmith/buy",
                        json={"item_id": "nope"})
        assert r.status_code == 200
        assert r.json()["success"] is False

    def test_buy_blocked_in_combat(self, client: TestClient, game, db_session):
        state = json.loads(game.game_state)
        state["in_combat"] = True
        game.game_state = json.dumps(state)
        db_session.commit()
        entry = _first_stock_item(client, game.id, "blacksmith")
        r = client.post(f"/api/game/{game.id}/shop/blacksmith/buy",
                        json={"item_id": entry["item"]["id"]})
        assert r.status_code == 400

    def test_buy_logs_to_story(self, client: TestClient, game):
        entry = _first_stock_item(client, game.id, "blacksmith")
        client.post(f"/api/game/{game.id}/shop/blacksmith/buy",
                    json={"item_id": entry["item"]["id"]})
        state = client.get(f"/api/game/{game.id}/state").json()
        assert any(e["role"] == "system" and "Bought" in e["content"]
                   for e in state["story_log"])

    def test_buy_404(self, client: TestClient):
        r = client.post("/api/game/9999/shop/blacksmith/buy", json={"item_id": "x"})
        assert r.status_code == 404


# --------------------------------------------------------------------------- #
# POST /sell
# --------------------------------------------------------------------------- #

class TestSell:
    def test_sell_success(self, client: TestClient, game):
        # First give the character something to sell via the inventory add endpoint
        add = client.post(f"/api/characters/{game.character_id}/items",
                          json={"name": "Longsword", "item_type": "weapon",
                                "value": 20, "damage_dice": "1d8"})
        assert add.status_code == 200
        item_id = add.json()["slots"][-1]["item"]["id"]

        r = client.post(f"/api/game/{game.id}/shop/blacksmith/sell",
                        json={"item_id": item_id, "quantity": 1})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["transaction_type"] == "sell"
        # 50% of 20 = 10
        assert data["unit_price"] == 10
        assert data["gold"] == 500 + 10

    def test_sell_wrong_merchant(self, client: TestClient, game):
        add = client.post(f"/api/characters/{game.character_id}/items",
                          json={"name": "Longsword", "item_type": "weapon", "value": 20})
        item_id = add.json()["slots"][-1]["item"]["id"]
        # Alchemist doesn't buy weapons
        r = client.post(f"/api/game/{game.id}/shop/alchemist/sell",
                        json={"item_id": item_id})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False
        assert "doesn't deal" in data["message"]
        assert data["gold"] == 500

    def test_sell_unknown_item(self, client: TestClient, game):
        r = client.post(f"/api/game/{game.id}/shop/blacksmith/sell",
                        json={"item_id": "ghost"})
        assert r.json()["success"] is False

    def test_sell_blocked_in_combat(self, client: TestClient, game, db_session):
        state = json.loads(game.game_state)
        state["in_combat"] = True
        game.game_state = json.dumps(state)
        db_session.commit()
        r = client.post(f"/api/game/{game.id}/shop/blacksmith/sell",
                        json={"item_id": "x"})
        assert r.status_code == 400

    def test_sell_logs_to_story(self, client: TestClient, game):
        add = client.post(f"/api/characters/{game.character_id}/items",
                          json={"name": "Longsword", "item_type": "weapon", "value": 20})
        item_id = add.json()["slots"][-1]["item"]["id"]
        client.post(f"/api/game/{game.id}/shop/blacksmith/sell", json={"item_id": item_id})
        state = client.get(f"/api/game/{game.id}/state").json()
        assert any(e["role"] == "system" and "Sold" in e["content"]
                   for e in state["story_log"])

    def test_sell_merchant_runs_out_of_gold(self, client: TestClient, game, db_session):
        # A hamlet merchant has 25 gp; selling 20-gp items (10 gp each) drains it
        state = json.loads(game.game_state)
        state["settlement_tier"] = "hamlet"
        game.game_state = json.dumps(state)
        db_session.commit()

        # Add many swords
        item_ids = []
        for _ in range(10):
            add = client.post(f"/api/characters/{game.character_id}/items",
                              json={"name": "Longsword", "item_type": "weapon", "value": 20})
            item_ids.append(add.json()["slots"][-1]["item"]["id"])

        sold = 0
        for iid in item_ids:
            r = client.post(f"/api/game/{game.id}/shop/blacksmith/sell",
                            json={"item_id": iid})
            if r.json()["success"]:
                sold += 1
        assert sold < len(item_ids)  # merchant ran out of gold


# --------------------------------------------------------------------------- #
# POST /restock
# --------------------------------------------------------------------------- #

class TestRestock:
    def test_restock_refills(self, client: TestClient, game):
        # Buy out a line first
        entry = _first_stock_item(client, game.id, "blacksmith")
        client.post(f"/api/game/{game.id}/shop/blacksmith/buy",
                    json={"item_id": entry["item"]["id"], "quantity": entry["quantity"]})
        after = client.get(f"/api/game/{game.id}/shop/blacksmith").json()
        names_after = {e["item"]["name"] for e in after["stock"]}
        assert entry["item"]["name"] not in names_after  # bought out

        r = client.post(f"/api/game/{game.id}/shop/blacksmith/restock")
        assert r.status_code == 200
        data = r.json()
        assert data["restocked_lines"] >= 1
        # Line is back
        names = {e["item"]["name"] for e in data["merchant"]["stock"]}
        assert entry["item"]["name"] in names

    def test_restock_restores_merchant_gold(self, client: TestClient, game):
        from app.engine.shop import SETTLEMENT_TIERS
        # Drain some merchant gold by selling an expensive item
        add = client.post(f"/api/characters/{game.character_id}/items",
                          json={"name": "Plate Armor", "item_type": "armor", "value": 100})
        plate_id = add.json()["slots"][-1]["item"]["id"]
        client.post(f"/api/game/{game.id}/shop/blacksmith/sell", json={"item_id": plate_id})

        before = client.get(f"/api/game/{game.id}/shop/blacksmith").json()["gold"]
        client.post(f"/api/game/{game.id}/shop/blacksmith/restock")
        after = client.get(f"/api/game/{game.id}/shop/blacksmith").json()["gold"]
        assert after > before
        assert after == SETTLEMENT_TIERS["town"].gold_reserve


# --------------------------------------------------------------------------- #
# Starting gold on character creation
# --------------------------------------------------------------------------- #

class TestStartingGold:
    def test_fighter_gets_starting_gold(self, client: TestClient):
        r = client.post("/api/characters/", json={
            "name": "Tester", "race": "Human", "char_class": "Fighter",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["gold"] > 0  # fighter starting gold

    def test_monk_gets_less_than_fighter(self, client: TestClient):
        fighter = client.post("/api/characters/", json={
            "name": "F", "race": "Human", "char_class": "Fighter"}).json()["gold"]
        monk = client.post("/api/characters/", json={
            "name": "M", "race": "Human", "char_class": "Monk"}).json()["gold"]
        assert monk < fighter

    def test_character_response_includes_gold(self, client: TestClient):
        r = client.post("/api/characters/", json={
            "name": "X", "race": "Human", "char_class": "Wizard"})
        assert "gold" in r.json()


# --------------------------------------------------------------------------- #
# Persistence across requests
# --------------------------------------------------------------------------- #

class TestPersistence:
    def test_merchant_state_persists_in_game_state(self, client: TestClient, game):
        entry = _first_stock_item(client, game.id, "blacksmith")
        start_qty = entry["quantity"]
        client.post(f"/api/game/{game.id}/shop/blacksmith/buy",
                    json={"item_id": entry["item"]["id"]})
        # A second GET should show the reduced stock, not a fresh merchant
        after = client.get(f"/api/game/{game.id}/shop/blacksmith").json()
        same = next((e for e in after["stock"] if e["item"]["name"] == entry["item"]["name"]), None)
        assert same is not None
        assert same["quantity"] == start_qty - 1
