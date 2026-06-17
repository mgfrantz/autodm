"""
Tests for the shop / economy engine.

Covers merchant generation, pricing (buy/sell), transaction mechanics (success
and every failure mode), the finite-economy model (merchant gold + stock
depletion/restock), settlement tiers, and serialization round-trips.
"""
import pytest

from app.engine.inventory import (
    Inventory,
    Item,
    ItemType,
    Rarity,
    ArmorType,
    create_weapon,
    create_armor,
    create_potion,
)
from app.engine import shop as shop_engine
from app.engine.shop import (
    Merchant,
    MerchantArchetype,
    SettlementTier,
    StockEntry,
    TransactionResult,
    MERCHANT_TYPES,
    SETTLEMENT_TIERS,
    DEFAULT_TIER,
    buy_price,
    sell_price,
    create_merchant,
    restock,
    execute_buy,
    execute_sell,
    resolve_archetype,
    resolve_tier,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def blacksmith():
    return create_merchant("blacksmith", "town")


@pytest.fixture
def empty_inventory():
    return Inventory()


# --------------------------------------------------------------------------- #
# Archetypes / settlement tiers
# --------------------------------------------------------------------------- #

class TestArchetypes:
    def test_all_merchant_types_present(self):
        assert set(MERCHANT_TYPES) == {
            "blacksmith", "alchemist", "general", "arcane", "fletcher",
        }

    def test_each_archetype_has_buy_categories(self):
        for arch in MERCHANT_TYPES.values():
            assert len(arch.buys) >= 1
            assert isinstance(arch.label, str) and arch.label

    def test_resolve_archetype_known(self):
        assert resolve_archetype("blacksmith").key == "blacksmith"

    def test_resolve_archetype_unknown_falls_back_to_general(self):
        assert resolve_archetype("nonsense").key == "general"

    def test_resolve_archetype_is_case_insensitive(self):
        assert resolve_archetype("Blacksmith").key == "blacksmith"

    def test_buys_type(self):
        arch = MERCHANT_TYPES["blacksmith"]
        weapon = create_weapon("Sword", "1d8")
        potion = create_potion("Potion", "heal")
        assert arch.buys_type(weapon.item_type) is True
        assert arch.buys_type(potion.item_type) is False


class TestSettlementTiers:
    def test_all_tiers_present(self):
        assert set(SETTLEMENT_TIERS) == {
            "hamlet", "village", "town", "city", "metropolis",
        }

    def test_gold_reserve_scales_with_tier(self):
        reserves = [SETTLEMENT_TIERS[k].gold_reserve for k in
                    ("hamlet", "village", "town", "city", "metropolis")]
        assert reserves == sorted(reserves)
        assert reserves[0] < reserves[-1]

    def test_resolve_tier_known(self):
        assert resolve_tier("city").key == "city"

    def test_resolve_tier_unknown_falls_back(self):
        assert resolve_tier("nowhere").key == DEFAULT_TIER
        assert resolve_tier(None).key == DEFAULT_TIER


# --------------------------------------------------------------------------- #
# Pricing
# --------------------------------------------------------------------------- #

class TestPricing:
    def test_buy_price_uses_base_value(self):
        arch = MERCHANT_TYPES["blacksmith"]  # markup 1.0
        item = create_weapon("Sword", "1d8", value=15)
        assert buy_price(item, arch) == 15

    def test_buy_price_applies_markup(self):
        arch = MERCHANT_TYPES["arcane"]  # markup 1.2
        item = create_weapon("Rod", "1d4", value=100)
        assert buy_price(item, arch) == 120

    def test_buy_price_general_store_markup(self):
        arch = MERCHANT_TYPES["general"]  # markup 1.1
        item = create_potion("Potion", "heal", value=50)
        assert buy_price(item, arch) == 55

    def test_buy_price_fletcher_discount(self):
        arch = MERCHANT_TYPES["fletcher"]  # markup 0.95
        item = create_weapon("Longbow", "1d8", value=50)
        assert buy_price(item, arch) == 48  # round(50 * 0.95)

    def test_buy_price_zero_value_stays_zero(self):
        arch = MERCHANT_TYPES["blacksmith"]
        item = create_weapon("Free", "1d4", value=0)
        assert buy_price(item, arch) == 0

    def test_buy_price_nonzero_min_one(self):
        arch = MERCHANT_TYPES["fletcher"]
        item = create_weapon("Cheap", "1d4", value=1)
        # 1 * 0.95 = 0.95 -> rounds to 1, floored at 1 for non-zero value
        assert buy_price(item, arch) >= 1

    def test_sell_price_half_value_default(self):
        arch = MERCHANT_TYPES["blacksmith"]  # sell_rate 0.5
        item = create_weapon("Sword", "1d8", value=20)
        assert sell_price(item, arch) == 10

    def test_sell_price_arcane_lower_rate(self):
        arch = MERCHANT_TYPES["arcane"]  # sell_rate 0.4
        item = create_weapon("Rod", "1d4", value=100)
        assert sell_price(item, arch) == 40

    def test_sell_price_min_one_for_nonzero(self):
        arch = MERCHANT_TYPES["blacksmith"]
        item = create_weapon("Cheap", "1d4", value=1)
        assert sell_price(item, arch) == 1


# --------------------------------------------------------------------------- #
# Merchant creation / stock
# --------------------------------------------------------------------------- #

class TestMerchantCreation:
    def test_blacksmith_has_stock(self, blacksmith):
        assert len(blacksmith.stock) >= 5
        assert blacksmith.gold > 0

    def test_town_gold_reserve(self, blacksmith):
        assert blacksmith.gold == SETTLEMENT_TIERS["town"].gold_reserve

    def test_hamlet_has_less_gold_than_city(self):
        hamlet = create_merchant("blacksmith", "hamlet")
        city = create_merchant("blacksmith", "city")
        assert hamlet.gold < city.gold

    def test_stock_quantities_scale_with_tier(self):
        hamlet = create_merchant("alchemist", "hamlet")
        metro = create_merchant("alchemist", "metropolis")
        # A metropolis stocks at least as many of each as a hamlet
        assert sum(e.quantity for e in metro.stock) >= sum(e.quantity for e in hamlet.stock)

    def test_each_merchant_type_generates_stock(self):
        for mtype in MERCHANT_TYPES:
            m = create_merchant(mtype, "town")
            assert len(m.stock) >= 1, f"{mtype} has no stock"

    def test_merchant_name_is_deterministic(self):
        m1 = create_merchant("blacksmith", "town")
        m2 = create_merchant("blacksmith", "town")
        assert m1.name == m2.name

    def test_custom_name_used(self):
        m = create_merchant("blacksmith", "town", name="Custom Smith")
        assert m.name == "Custom Smith"


# --------------------------------------------------------------------------- #
# Restock
# --------------------------------------------------------------------------- #

class TestRestock:
    def test_restock_refills_depleted_stock(self, blacksmith, empty_inventory):
        target = blacksmith.stock[0]
        target_name = target.item.name
        original_qty = target.quantity
        # Buy out the whole line
        result, _ = execute_buy(blacksmith, empty_inventory, 10_000, target.item.id, original_qty)
        assert result.success
        assert blacksmith.find_stock(target.item.id) is None

        summary = restock(blacksmith, restore_gold=False)
        assert summary["restocked_lines"] >= 1
        # Restock regenerates the catalogue with fresh item instances, so look up
        # the replenished line by name rather than the (now-gone) old item id.
        replenished = next(
            (e for e in blacksmith.stock if e.item.name == target_name), None
        )
        assert replenished is not None
        assert replenished.quantity == original_qty

    def test_restock_restores_gold(self):
        m = create_merchant("blacksmith", "village")
        m.gold = 0
        restock(m, restore_gold=True)
        assert m.gold == SETTLEMENT_TIERS["village"].gold_reserve

    def test_restock_can_skip_gold(self):
        m = create_merchant("blacksmith", "village")
        m.gold = 0
        restock(m, restore_gold=False)
        assert m.gold == 0


# --------------------------------------------------------------------------- #
# Buying
# --------------------------------------------------------------------------- #

class TestExecuteBuy:
    def test_successful_buy(self, blacksmith, empty_inventory):
        target = blacksmith.stock[0]
        unit = buy_price(target.item, blacksmith.archetype)
        result, gold = execute_buy(blacksmith, empty_inventory, 10_000, target.item.id, 1)

        assert result.success is True
        assert result.transaction_type == "buy"
        assert result.unit_price == unit
        assert result.total == unit
        assert gold == 10_000 - unit
        assert len(empty_inventory.slots) == 1

    def test_buy_decreases_player_gold(self, blacksmith, empty_inventory):
        target = blacksmith.stock[0]
        unit = buy_price(target.item, blacksmith.archetype)
        _, gold = execute_buy(blacksmith, empty_inventory, unit + 5, target.item.id)
        assert gold == 5

    def test_buy_increases_merchant_gold(self, blacksmith, empty_inventory):
        target = blacksmith.stock[0]
        start_gold = blacksmith.gold
        execute_buy(blacksmith, empty_inventory, 10_000, target.item.id)
        assert blacksmith.gold == start_gold + buy_price(target.item, blacksmith.archetype)

    def test_buy_decreases_stock_quantity(self, blacksmith, empty_inventory):
        target = blacksmith.stock[0]
        start_qty = target.quantity
        execute_buy(blacksmith, empty_inventory, 10_000, target.item.id, 2)
        assert target.quantity == start_qty - 2

    def test_buying_out_removes_stock_line(self, blacksmith, empty_inventory):
        target = blacksmith.stock[0]
        qty = target.quantity
        execute_buy(blacksmith, empty_inventory, 10_000, target.item.id, qty)
        assert blacksmith.find_stock(target.item.id) is None

    def test_buy_insufficient_gold(self, blacksmith, empty_inventory):
        target = blacksmith.stock[0]
        result, gold = execute_buy(blacksmith, empty_inventory, 1, target.item.id, 1)
        assert result.success is False
        assert "need" in result.message.lower()
        assert gold == 1  # unchanged
        assert len(empty_inventory.slots) == 0

    def test_buy_unknown_item(self, blacksmith, empty_inventory):
        result, gold = execute_buy(blacksmith, empty_inventory, 10_000, "does-not-exist")
        assert result.success is False
        assert gold == 10_000

    def test_buy_more_than_stock(self, blacksmith, empty_inventory):
        target = blacksmith.stock[0]
        too_many = target.quantity + 10
        result, _ = execute_buy(blacksmith, empty_inventory, 10_000, target.item.id, too_many)
        assert result.success is False
        assert "only" in result.message.lower()

    def test_buy_quantity_clamped_to_one_min(self, blacksmith, empty_inventory):
        target = blacksmith.stock[0]
        result, _ = execute_buy(blacksmith, empty_inventory, 10_000, target.item.id, 0)
        assert result.success is True
        assert result.quantity == 1

    def test_buy_multiple(self, blacksmith, empty_inventory):
        target = blacksmith.stock[0]
        unit = buy_price(target.item, blacksmith.archetype)
        result, gold = execute_buy(blacksmith, empty_inventory, 10_000, target.item.id, 3)
        assert result.success is True
        assert result.total == unit * 3
        assert gold == 10_000 - unit * 3

    def test_buy_purchased_item_has_fresh_id(self, blacksmith, empty_inventory):
        target = blacksmith.stock[0]
        execute_buy(blacksmith, empty_inventory, 10_000, target.item.id, 1)
        bought = empty_inventory.slots[0].item
        assert bought.id != target.item.id
        assert bought.name == target.item.name

    def test_buy_two_nonstackable_creates_two_lines(self, blacksmith, empty_inventory):
        # Weapons aren't stackable — buying 2 of a weapon yields 2 inventory lines
        target = next(e for e in blacksmith.stock if e.item.item_type == ItemType.WEAPON)
        execute_buy(blacksmith, empty_inventory, 10_000, target.item.id, 2)
        weapons = [s for s in empty_inventory.slots if s.item.item_type == ItemType.WEAPON]
        assert len(weapons) == 2


# --------------------------------------------------------------------------- #
# Selling
# --------------------------------------------------------------------------- #

class TestExecuteSell:
    def test_successful_sell(self, blacksmith):
        inv = Inventory()
        sword = create_weapon("Longsword", "1d8", value=15)
        inv.add_item(sword)
        unit = sell_price(sword, blacksmith.archetype)

        result, gold = execute_sell(blacksmith, inv, 100, sword.id, 1)
        assert result.success is True
        assert result.transaction_type == "sell"
        assert result.unit_price == unit
        assert result.total == unit
        assert gold == 100 + unit
        assert len(inv.slots) == 0

    def test_sell_increases_player_gold(self, blacksmith):
        inv = Inventory()
        sword = create_weapon("Longsword", "1d8", value=20)
        inv.add_item(sword)
        _, gold = execute_sell(blacksmith, inv, 0, sword.id)
        assert gold == 10  # 50% of 20

    def test_sell_decreases_merchant_gold(self, blacksmith):
        inv = Inventory()
        sword = create_weapon("Longsword", "1d8", value=20)
        inv.add_item(sword)
        start_gold = blacksmith.gold
        execute_sell(blacksmith, inv, 0, sword.id)
        assert blacksmith.gold == start_gold - 10

    def test_sell_wrong_merchant_type_rejected(self):
        # Alchemist doesn't buy weapons
        alchemist = create_merchant("alchemist", "town")
        inv = Inventory()
        sword = create_weapon("Longsword", "1d8", value=15)
        inv.add_item(sword)
        result, gold = execute_sell(alchemist, inv, 100, sword.id)
        assert result.success is False
        assert "doesn't deal" in result.message
        assert gold == 100
        assert len(inv.slots) == 1

    def test_sell_unknown_item(self, blacksmith, empty_inventory):
        result, gold = execute_sell(blacksmith, empty_inventory, 100, "nope")
        assert result.success is False
        assert gold == 100

    def test_sell_more_than_owned(self, blacksmith):
        inv = Inventory()
        sword = create_weapon("Longsword", "1d8", value=15)
        inv.add_item(sword)  # quantity 1
        result, gold = execute_sell(blacksmith, inv, 100, sword.id, 5)
        assert result.success is False
        assert "only have" in result.message
        assert gold == 100

    def test_sell_when_merchant_cannot_afford(self):
        # Hamlet merchant has only 25 gp; selling a 500 gp item fails
        hamlet = create_merchant("blacksmith", "hamlet")
        inv = Inventory()
        plate = create_armor("Plate Armor", ArmorType.HEAVY, value=500)
        inv.add_item(plate)
        result, gold = execute_sell(hamlet, inv, 0, plate.id)
        assert result.success is False
        assert "can't afford" in result.message
        assert gold == 0
        assert len(inv.slots) == 1

    def test_sell_quantity_clamped(self, blacksmith):
        inv = Inventory()
        sword = create_weapon("Longsword", "1d8", value=15)
        inv.add_item(sword)
        result, _ = execute_sell(blacksmith, inv, 100, sword.id, 0)
        assert result.success is True
        assert result.quantity == 1

    def test_sell_partial_quantity_of_stack(self, blacksmith):
        # Blacksmith doesn't buy potions — use a stackable misc it does NOT buy?
        # Misc IS bought by general store. Build a stack of misc for the general store.
        general = create_merchant("general", "town")
        inv = Inventory()
        item = Item(id="", name="Backpack", item_type=ItemType.MISC, value=2, quantity=5)
        inv.add_item(item)
        result, gold = execute_sell(general, inv, 50, item.id, 2)
        assert result.success is True
        assert result.quantity == 2
        # Remaining quantity 3 still in inventory
        remaining = inv.get_item(item.id)
        assert remaining is not None
        assert remaining.quantity == 3

    def test_general_store_buys_potions(self):
        general = create_merchant("general", "town")
        inv = Inventory()
        potion = create_potion("Potion of Healing", "heal", value=50)
        inv.add_item(potion)
        result, _ = execute_sell(general, inv, 0, potion.id)
        assert result.success is True


# --------------------------------------------------------------------------- #
# Integration / economy model
# --------------------------------------------------------------------------- #

class TestEconomyModel:
    def test_buy_then_sell_loses_value(self, blacksmith):
        """Selling an item you just bought recovers at most the buy price."""
        inv = Inventory()
        target = blacksmith.stock[0]
        buy_total = buy_price(target.item, blacksmith.archetype)
        _, gold = execute_buy(blacksmith, inv, buy_total, target.item.id, 1)
        assert gold == 0
        bought_id = inv.slots[0].item.id
        _, gold_after = execute_sell(blacksmith, inv, 0, bought_id, 1)
        # Player should have less than they paid (merchant takes a cut)
        assert 0 < gold_after < buy_total

    def test_merchant_gold_is_finite(self):
        """A hamlet merchant eventually stops buying once its gold runs low."""
        hamlet = create_merchant("blacksmith", "hamlet")
        inv = Inventory()
        # Add many swords worth 20 gp each (10 gp sell each). 25 gp reserve.
        swords = [create_weapon("Sword", "1d8", value=20) for _ in range(20)]
        for s in swords:
            inv.add_item(s)
        sold = 0
        for s in swords:
            res, _ = execute_sell(hamlet, inv, 0, s.id)
            if res.success:
                sold += 1
        # Should have sold some, then stopped (can't afford a full 10 gp sale)
        assert 0 < sold < len(swords)
        # Remaining gold is less than a single sale price -> merchant broke
        assert hamlet.gold < sell_price(swords[0], hamlet.archetype)

    def test_round_trip_serialization(self, blacksmith):
        data = blacksmith.to_dict()
        restored = Merchant.from_dict(data)
        assert restored.name == blacksmith.name
        assert restored.merchant_type == blacksmith.merchant_type
        assert restored.gold == blacksmith.gold
        assert len(restored.stock) == len(blacksmith.stock)
        for a, b in zip(restored.stock, blacksmith.stock):
            assert a.item.name == b.item.name
            assert a.item.value == b.item.value
            assert a.quantity == b.quantity

    def test_transaction_result_serialization(self):
        r = TransactionResult(
            success=True, message="ok", transaction_type="buy",
            item_name="Sword", item_id="x", quantity=1,
            unit_price=10, total=10, gold_after=90, merchant_gold_after=510,
        )
        d = r.to_dict()
        assert d["success"] is True
        assert d["total"] == 10
        assert d["gold_after"] == 90
        assert d["merchant_gold_after"] == 510


# --------------------------------------------------------------------------- #
# StockEntry serialization
# --------------------------------------------------------------------------- #

class TestStockEntry:
    def test_round_trip(self):
        item = create_weapon("Sword", "1d8", value=15)
        entry = StockEntry(item=item, quantity=3)
        data = entry.to_dict()
        restored = StockEntry.from_dict(data)
        assert restored.item.name == "Sword"
        assert restored.item.value == 15
        assert restored.quantity == 3

    def test_quantity_default(self):
        item = create_weapon("Sword", "1d8")
        restored = StockEntry.from_dict({"item": item.to_dict()})
        assert restored.quantity == 1
