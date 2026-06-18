"""
Loot engine unit tests — DMG-style treasure tables.

Tests individual treasure, hoard loot, chest generation, and all helpers.
All tests use seeded RNG for determinism.
"""
import pytest
import random
from app.engine.loot import (
    CoinPurse,
    LootResult,
    cr_tier,
    roll_individual_loot,
    roll_hoard_loot,
    roll_chest_loot,
    loot_table_overview,
    CHEST_TIERS,
)


class TestCoinPurse:
    """Test coin handling and gold conversion."""

    def test_empty_purse(self):
        purse = CoinPurse()
        assert purse.is_empty()
        assert purse.total_gp() == 0

    def test_total_gold_conversion(self):
        # 1 pp = 10 gp
        assert CoinPurse(pp=1).total_gp() == 10.0
        # 1 ep = 0.5 gp
        assert CoinPurse(ep=1).total_gp() == 0.5
        # 1 sp = 0.1 gp
        assert CoinPurse(sp=1).total_gp() == 0.1
        # 1 cp = 0.01 gp
        assert CoinPurse(cp=1).total_gp() == 0.01

    def test_mixed_coins(self):
        purse = CoinPurse(cp=50, sp=20, ep=4, gp=10, pp=2)
        # 50 cp = 0.5 gp, 20 sp = 2 gp, 4 ep = 2 gp, 10 gp = 10 gp, 2 pp = 20 gp
        # Total: 34.5 gp
        assert purse.total_gp() == 34.5

    def test_purse_add(self):
        p1 = CoinPurse(gp=5, sp=10)
        p2 = CoinPurse(gp=3, pp=1)
        p1.add(p2)
        assert p1.gp == 8
        assert p1.sp == 10
        assert p1.pp == 1

    def test_to_dict(self):
        purse = CoinPurse(cp=5, sp=10, ep=2, gp=100, pp=5)
        d = purse.to_dict()
        assert d == {
            "cp": 5,
            "sp": 10,
            "ep": 2,
            "gp": 100,
            "pp": 5,
            "total_gp": 152.05,
        }


class TestCRTier:
    """Test CR classification into loot tiers."""

    @pytest.mark.parametrize("cr,expected", [
        (0, "0-4"),
        (1, "0-4"),
        (4, "0-4"),
        (5, "5-10"),
        (10, "5-10"),
        (11, "11-16"),
        (16, "11-16"),
        (17, "17+"),
        (20, "17+"),
        (0.125, "0-4"),
        (0.5, "0-4"),
        (2.5, "0-4"),
        (7.5, "5-10"),
        (12.5, "11-16"),
    ])
    def test_cr_tier_classification(self, cr, expected):
        assert cr_tier(cr) == expected


class TestIndividualTreasure:
    """Test individual treasure tables (coins only)."""

    def test_cr0_4_individual(self):
        # Seed 42: rolls into gp range (71-95) on the 0-4 table
        rng = random.Random(42)
        result = roll_individual_loot(1, rng)
        assert not result.is_empty
        assert result.coins.gp > 0  # gp range
        assert result.coins.total_gp() > 0
        assert result.items == []

    def test_cr5_10_individual(self):
        # Seed 7: high-level drop
        rng = random.Random(7)
        result = roll_individual_loot(8, rng)
        assert not result.is_empty
        assert result.coins.total_gp() > 0
        assert result.items == []

    def test_cr11_16_individual(self):
        rng = random.Random(99)
        result = roll_individual_loot(14, rng)
        assert not result.is_empty
        assert result.coins.total_gp() > 0
        # High CR can drop pp
        assert result.coins.pp >= 0

    def test_cr17_individual(self):
        rng = random.Random(123)
        result = roll_individual_loot(18, rng)
        assert not result.is_empty
        # CR 17+ individual only has gp or pp rolls
        assert result.coins.total_gp() > 0

    def test_individual_no_items(self):
        # Individual treasure never has items, only coins
        for cr in [0.5, 2, 8, 14, 20]:
            rng = random.Random(cr * 1000)
            result = roll_individual_loot(cr, rng)
            assert result.items == []

    def test_deterministic_with_seed(self):
        rng1 = random.Random(999)
        rng2 = random.Random(999)
        result1 = roll_individual_loot(3, rng1)
        result2 = roll_individual_loot(3, rng2)
        assert result1.coins.to_dict() == result2.coins.to_dict()


class TestHoardTreasure:
    """Test hoard loot (coins + valuables + magic items)."""

    def test_cr0_4_hoard(self):
        rng = random.Random(42)
        result = roll_hoard_loot(3, rng)
        # Hoards have coins + possibly items
        assert result.coins.total_gp() >= 0
        # May or may not have items
        assert isinstance(result.items, list)

    def test_cr5_10_hoard(self):
        rng = random.Random(99)
        result = roll_hoard_loot(7, rng)
        assert result.coins.total_gp() >= 0
        assert isinstance(result.items, list)

    def test_cr11_16_hoard(self):
        rng = random.Random(7)
        result = roll_hoard_loot(14, rng)
        assert result.coins.total_gp() >= 0
        # High CR hoards can have gems/art/magic
        assert isinstance(result.items, list)

    def test_cr17_hoard(self):
        rng = random.Random(123)
        result = roll_hoard_loot(19, rng)
        assert result.coins.total_gp() >= 0
        # Very high CR hoards can have significant treasure
        assert isinstance(result.items, list)

    def test_hoard_items_are_valid(self):
        rng = random.Random(555)
        result = roll_hoard_loot(12, rng)
        for item in result.items:
            assert item.name
            assert item.value >= 0
            assert item.rarity

    def test_hoard_deterministic_with_seed(self):
        rng1 = random.Random(888)
        rng2 = random.Random(888)
        result1 = roll_hoard_loot(5, rng1)
        result2 = roll_hoard_loot(5, rng2)
        assert result1.coins.to_dict() == result2.coins.to_dict()
        assert [i.name for i in result1.items] == [i.name for i in result2.items]


class TestChestLoot:
    """Test standalone chest generation by tier."""

    def test_common_chest(self):
        rng = random.Random(42)
        result = roll_chest_loot("common", rng)
        assert result.source == "chest"
        assert result.coins.total_gp() >= 0
        assert isinstance(result.items, list)

    def test_uncommon_chest(self):
        rng = random.Random(99)
        result = roll_chest_loot("uncommon", rng)
        assert result.source == "chest"
        assert isinstance(result.items, list)

    def test_rare_chest(self):
        rng = random.Random(123)
        result = roll_chest_loot("rare", rng)
        assert result.source == "chest"
        assert isinstance(result.items, list)

    def test_legendary_chest(self):
        rng = random.Random(456)
        result = roll_chest_loot("legendary", rng)
        assert result.source == "chest"
        assert isinstance(result.items, list)

    def test_chest_deterministic_with_seed(self):
        rng1 = random.Random(777)
        rng2 = random.Random(777)
        result1 = roll_chest_loot("rare", rng1)
        result2 = roll_chest_loot("rare", rng2)
        assert result1.coins.to_dict() == result2.coins.to_dict()

    def test_invalid_chest_tier(self):
        # Invalid tier should fall back to common
        rng = random.Random(999)
        result = roll_chest_loot("mythic", rng)
        assert result.source == "chest"


class TestLootResult:
    """Test LootResult dataclass methods."""

    def test_result_addition(self):
        from app.engine.loot import LootResult
        r1 = LootResult(coins=CoinPurse(gp=10), items=[], source="individual", cr=1)
        r2 = LootResult(coins=CoinPurse(gp=5, sp=20), items=[], source="individual", cr=2)
        r1.add(r2)
        assert r1.coins.gp == 15
        assert r1.coins.sp == 20

    def test_result_is_empty(self):
        from app.engine.loot import LootResult
        assert LootResult(coins=CoinPurse(), items=[]).is_empty
        assert not LootResult(coins=CoinPurse(gp=1), items=[]).is_empty
        # Need an actual item for the second assertion

    def test_result_to_dict(self):
        from app.engine.loot import LootResult
        from app.engine.inventory import Item, ItemType, Rarity
        item = Item(id="1", name="Test Gem", item_type=ItemType.MISC, rarity=Rarity.COMMON, value=10)
        result = LootResult(
            coins=CoinPurse(gp=5, sp=10),
            items=[item],
            source="chest",
            cr=0,
        )
        d = result.to_dict()
        assert d["source"] == "chest"
        assert d["coins"]["gp"] == 5
        assert d["coins"]["total_gp"] == 6.0
        assert len(d["items"]) == 1
        assert d["items"][0]["name"] == "Test Gem"
        assert d["item_value_total"] == 10
        assert not d["is_empty"]


class TestLootTableOverview:
    """Test the read-only loot-table inspector."""

    def test_overview_structure(self):
        overview = loot_table_overview()
        assert "cr_tiers" in overview
        assert "individual_treasure" in overview
        assert "chest_tiers" in overview
        assert "gem_values" in overview
        assert "art_values" in overview
        assert "magic_item_tables" in overview

    def test_cr_tiers(self):
        overview = loot_table_overview()
        assert "0-4" in overview["cr_tiers"]
        assert "5-10" in overview["cr_tiers"]
        assert "11-16" in overview["cr_tiers"]
        assert "17+" in overview["cr_tiers"]

    def test_chest_tiers_match_constants(self):
        overview = loot_table_overview()
        for tier in CHEST_TIERS:
            assert tier in overview["chest_tiers"]

    def test_gem_values_sorted(self):
        overview = loot_table_overview()
        values = overview["gem_values"]
        assert values == sorted(values)

    def test_art_values_sorted(self):
        overview = loot_table_overview()
        values = overview["art_values"]
        assert values == sorted(values)

    def test_magic_item_tables(self):
        overview = loot_table_overview()
        tables = overview["magic_item_tables"]
        assert "A" in tables
        assert "B" in tables
        assert "C" in tables
        assert "D" in tables
        assert "E" in tables
        assert "F" in tables
        # Each table should have weights summing to something
        for key, total_weight in tables.items():
            assert total_weight > 0


class TestIntegration:
    """End-to-end loot generation scenarios."""

    def test_sequential_kills_accumulate(self):
        """Simulate killing multiple creatures and accumulating loot."""
        rng = random.Random(42)
        total = LootResult(coins=CoinPurse(), items=[], source="accumulated", cr=0)
        for cr in [1, 2, 3, 1]:
            kill = roll_individual_loot(cr, random.Random(cr * 111))
            total.add(kill)
        # Should have some gold from the four kills
        assert total.coins.total_gp() > 0
        assert not total.is_empty

    def test_boss_hoard_vs_common_hoard(self):
        """A boss hoard should be richer than a low-level hoard."""
        rng1 = random.Random(99)
        rng2 = random.Random(99)
        boss = roll_hoard_loot(15, rng1)  # CR 15 boss
        low = roll_hoard_loot(3, rng2)    # CR 3 mook
        # Boss hoard should have more gold
        assert boss.coins.total_gp() > low.coins.total_gp()