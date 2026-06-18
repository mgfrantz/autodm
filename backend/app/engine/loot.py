"""
Loot engine — randomized treasure drops and hoards (DnD 5e DMG tables).

Two treasure systems, mirroring the *Dungeon Master's Guide* (p.136-139):

1. **Individual treasure** — rolled per defeated creature. Coin-heavy and
   quick: a single d100 pick from a CR-tiered table.

2. **Hoard treasure** — rolled for chests, bosses, and cleared encounters.
   Richer: a flat coin payout, plus a chance for gems / art objects and magic
   items drawn from the DMG's magic-item tables A-F.

The engine is **pure**: it operates on dataclasses and returns ``LootResult``
objects. An optional ``random.Random`` instance (or a seed) makes rolls
deterministic for testing. Persistence (gold + inventory) is left to the API
layer.

Coin conversion follows the DMG standard:
    1 pp = 10 gp, 1 ep = 0.5 gp, 1 gp = 1 gp, 1 sp = 0.1 gp, 1 cp = 0.01 gp
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# A random source is either an explicit seeded ``random.Random`` instance or,
# when omitted, the global ``random`` module (whose top-level ``randint`` is
# used). Annotated loosely to accept both without pyright friction.
Rng = Any

from app.engine.inventory import (
    Item,
    ItemType,
    Rarity,
    ArmorType,
    create_weapon,
    create_armor,
    create_shield,
    create_potion,
)


# --------------------------------------------------------------------------- #
# Coin handling
# --------------------------------------------------------------------------- #

# Conversion factors to gold pieces (DMG standard)
COIN_TO_GP = {
    "cp": 0.01,
    "sp": 0.1,
    "ep": 0.5,
    "gp": 1.0,
    "pp": 10.0,
}


@dataclass
class CoinPurse:
    """A bag of mixed coins."""
    cp: int = 0
    sp: int = 0
    ep: int = 0
    gp: int = 0
    pp: int = 0

    def total_gp(self) -> float:
        """Whole-purse value in gold pieces (rounded to 2 decimals)."""
        return round(
            self.cp * COIN_TO_GP["cp"]
            + self.sp * COIN_TO_GP["sp"]
            + self.ep * COIN_TO_GP["ep"]
            + self.gp * COIN_TO_GP["gp"]
            + self.pp * COIN_TO_GP["pp"],
            2,
        )

    def add(self, other: "CoinPurse") -> None:
        self.cp += other.cp
        self.sp += other.sp
        self.ep += other.ep
        self.gp += other.gp
        self.pp += other.pp

    def is_empty(self) -> bool:
        return not (self.cp or self.sp or self.ep or self.gp or self.pp)

    def to_dict(self) -> dict:
        return {
            "cp": self.cp,
            "sp": self.sp,
            "ep": self.ep,
            "gp": self.gp,
            "pp": self.pp,
            "total_gp": self.total_gp(),
        }


def _roll_dice(count: int, sides: int, multiplier: int = 1,
               rng: Rng = None) -> int:
    """Roll ``count`` d``sides`` and multiply (DMG shorthand like ``4d6 x100``)."""
    r = rng or random
    total = sum(r.randint(1, sides) for _ in range(max(count, 0)))
    return total * multiplier


# --------------------------------------------------------------------------- #
# CR classification
# --------------------------------------------------------------------------- #

def cr_tier(cr: float) -> str:
    """Map a Challenge Rating to one of the DMG loot tiers."""
    if cr <= 4:
        return "0-4"
    if cr <= 10:
        return "5-10"
    if cr <= 16:
        return "11-16"
    return "17+"


# --------------------------------------------------------------------------- #
# Individual treasure tables (DMG p.137)
# --------------------------------------------------------------------------- #
# Each entry: (min_roll, max_roll, denomination, dice_count, dice_sides, multiplier)
INDIVIDUAL_TREASURE: dict[str, list[tuple[int, int, str, int, int, int]]] = {
    "0-4": [
        (1, 30, "cp", 5, 6, 1),
        (31, 60, "sp", 4, 6, 1),
        (61, 70, "ep", 3, 6, 1),
        (71, 95, "gp", 2, 6, 1),
        (96, 100, "pp", 1, 6, 1),
    ],
    "5-10": [
        (1, 30, "cp", 4, 6, 100),
        (31, 60, "sp", 6, 6, 10),
        (61, 70, "ep", 3, 6, 100),
        (71, 95, "gp", 4, 6, 10),
        (96, 100, "pp", 2, 6, 10),
    ],
    "11-16": [
        (1, 20, "cp", 4, 6, 1000),
        (21, 35, "sp", 4, 6, 1000),
        (36, 75, "gp", 6, 6, 100),
        (76, 95, "pp", 5, 6, 100),
        (96, 100, "pp", 1, 6, 1000),
    ],
    "17+": [
        (1, 15, "gp", 12, 6, 1000),
        (16, 55, "pp", 8, 6, 1000),
    ],
}


def roll_individual_treasure(cr: float,
                             rng: Rng = None
                             ) -> CoinPurse:
    """Roll coins for a single defeated creature of the given CR."""
    r = rng or random
    tier = cr_tier(cr)
    entries = INDIVIDUAL_TREASURE[tier]
    roll = r.randint(1, 100)
    for lo, hi, denom, count, sides, mult in entries:
        if lo <= roll <= hi:
            amount = _roll_dice(count, sides, mult, r)
            purse = CoinPurse()
            setattr(purse, denom, amount)
            return purse
    # Defensive fallback (shouldn't happen with valid tables)
    return CoinPurse()


# --------------------------------------------------------------------------- #
# Hoard coin tables (DMG p.137)
# --------------------------------------------------------------------------- #
# (sp_dice, sp_sides, sp_mult, gp_dice, gp_sides, gp_mult) — plus pp at high CR
HOARD_COINS: dict[str, list[tuple[str, int, int, int]]] = {
    # denomination, dice_count, dice_sides, multiplier
    "0-4": [
        ("sp", 6, 6, 100),
        ("gp", 2, 6, 100),
    ],
    "5-10": [
        ("cp", 2, 6, 1000),
        ("sp", 2, 6, 1000),
        ("gp", 6, 6, 100),
        ("pp", 3, 6, 10),
    ],
    "11-16": [
        ("gp", 4, 6, 1000),
        ("pp", 5, 6, 100),
    ],
    "17+": [
        ("gp", 12, 6, 1000),
        ("pp", 8, 6, 1000),
    ],
}


def _roll_hoard_coins(tier: str,
                      rng: Rng = None) -> CoinPurse:
    """Roll the flat coin portion of a hoard for a CR tier."""
    r = rng or random
    purse = CoinPurse()
    for denom, count, sides, mult in HOARD_COINS.get(tier, []):
        setattr(purse, denom, getattr(purse, denom) + _roll_dice(count, sides, mult, r))
    return purse


# --------------------------------------------------------------------------- #
# Gemstones & art objects (DMG p.134-135)
# --------------------------------------------------------------------------- #
# Representative samples of each value tier.
GEMS: dict[int, list[str]] = {
    10: [
        "Azurite", "Banded Quartz", "Blue Quartz", "Eye Agate", "Hematite",
        "Lapis Lazuli", "Malachite", "Moss Agate", "Obsidian",
        "Rhodochrosite", "Tiger Eye", "Turquoise",
    ],
    50: [
        "Bloodstone", "Carnelian", "Chalcedony", "Chrysoprase", "Citrine",
        "Jasper", "Moonstone", "Onyx", "Quartz", "Sardonyx",
        "Star Rose Quartz", "Zircon",
    ],
    100: [
        "Amber", "Amethyst", "Chrysoberyl", "Coral", "Garnet", "Jade",
        "Jet", "Pearl", "Spinel", "Tourmaline",
    ],
    500: [
        "Alexandrite", "Aquamarine", "Black Pearl", "Blue Spinel", "Peridot",
    ],
    1000: [
        "Black Opal", "Blue Sapphire", "Emerald", "Fire Opal", "Opal",
        "Star Sapphire", "Yellow Sapphire",
    ],
}

ART_OBJECTS: dict[int, list[str]] = {
    25: [
        "Silver Ewer", "Carved Bone Statuette", "Small Gold Bracelet",
        "Cloth-of-Gold Vestments", "Black Velvet Mask Stitched with Silver Thread",
        "Copper Chalice with Silver Filigree", "Decorative Bone Comb",
        "Gold Ring with Engraved Sigil", "Ivory Idol", "Large Silver Buckle",
    ],
    250: [
        "Fine Gold Chain Set with Garnets", "Old Master Portrait in a Gold Frame",
        "Silver Music Box", "Silver Chalice with Jade Inlay",
        "Carved Ivory Statuette", "Large Silver Candelabra",
        "Silver-plated Longsword", "Silk Tapestry", "Brass Drinking Horn", "Silver Mask",
    ],
    750: [
        "Fine Gold Crown", "Electrum Ring with Star Sapphire",
        "Jeweled Gold Pendant", "Silver-and-Gold Tiara", "Carved Gold Idol",
        "Gold and Ruby Ring", "Painting in a Jeweled Frame", "Crystal Orb on Gold Stand",
        "Silver Goblet Encrusted with Moonstones", "Gold Scepter",
    ],
    2500: [
        "Jeweled Gold Crown", "Gold and Platinum Scepter", "Emerald-studded Statuette",
        "Gold Idol with Ruby Eyes", "Diamond Necklace", "Gold Mask of a King",
        "Platinum Candelabra", "Jeweled Gold Chalice", "Mithral Crown", "Golden Dragon Statuette",
    ],
    7500: [
        "Masterwork Jeweled Crown", "Ancient Gold Death Mask",
        "Platinum Idol of a Forgotten God", "Ruby the Size of a Fist",
        "Golden Sarcophagus Miniature", "Sapphire-studded Throne Model",
    ],
}


def _make_gemstone(value: int, rng: Rng = None) -> Item:
    """A loose gemstone of the given gold value."""
    r = rng or random
    pool = GEMS.get(value, GEMS[10])
    name = r.choice(pool)
    return Item(
        id="",
        name=f"{name} ({value} gp)",
        item_type=ItemType.MISC,
        description=f"A polished {name.lower()} gemstone worth {value} gold pieces.",
        rarity=_rarity_for_value(value),
        value=value,
        weight=0.0,
        quantity=1,
    )


def _make_art_object(value: int, rng: Rng = None) -> Item:
    """A decorative art object of the given gold value."""
    r = rng or random
    pool = ART_OBJECTS.get(value, ART_OBJECTS[25])
    name = r.choice(pool)
    return Item(
        id="",
        name=f"{name} ({value} gp)",
        item_type=ItemType.MISC,
        description=f"A work of art worth {value} gold pieces.",
        rarity=_rarity_for_value(value),
        value=value,
        weight=2.0,
        quantity=1,
    )


def _rarity_for_value(value: int) -> Rarity:
    """Estimate item rarity from its gold value."""
    if value >= 5000:
        return Rarity.LEGENDARY
    if value >= 1000:
        return Rarity.VERY_RARE
    if value >= 200:
        return Rarity.RARE
    if value >= 50:
        return Rarity.UNCOMMON
    return Rarity.COMMON


# Hoard valuable-object tables: (min_roll, max_roll, kind, value, count_dice, count_sides)
# kind is "gem", "art", or None (no valuables on that roll).
HOARD_VALUABLES: dict[str, list[tuple[int, int, Optional[str], int, int, int]]] = {
    "0-4": [
        (1, 6, None, 0, 0, 0),  # no valuables
        (7, 56, "gem", 10, 2, 6),
        (57, 75, "gem", 50, 2, 4),
        (76, 95, "art", 25, 2, 4),
        (96, 100, "art", 250, 2, 4),
    ],
    "5-10": [
        (1, 4, None, 0, 0, 0),
        (5, 28, "gem", 50, 2, 6),
        (29, 52, "gem", 100, 2, 6),
        (53, 76, "art", 250, 2, 4),
        (77, 96, "art", 750, 2, 4),
        (97, 100, "art", 750, 1, 4),  # rare single expensive piece (×1d4)
    ],
    "11-16": [
        (1, 3, None, 0, 0, 0),
        (4, 18, "gem", 500, 2, 4),
        (19, 38, None, 0, 0, 0),
        (39, 50, "gem", 1000, 1, 2),
        (51, 66, "art", 2500, 2, 4),
        (67, 80, None, 0, 0, 0),
        (81, 96, "art", 7500, 2, 4),
        (97, 100, "art", 7500, 1, 2),
    ],
    "17+": [
        (1, 2, None, 0, 0, 0),
        (3, 15, "art", 7500, 2, 4),
        (16, 40, "gem", 5000, 1, 2),
        (41, 65, "gem", 1000, 1, 8),
        (66, 68, None, 0, 0, 0),
        (69, 100, "art", 25000, 1, 3),
    ],
}


def _roll_hoard_valuables(tier: str,
                          rng: Rng = None) -> list[Item]:
    """Roll gems/art objects for a hoard of the given CR tier."""
    r = rng or random
    table = HOARD_VALUABLES.get(tier, HOARD_VALUABLES["0-4"])
    roll = r.randint(1, 100)
    for lo, hi, kind, value, count, sides in table:
        if lo <= roll <= hi:
            if kind is None:
                return []
            n = _roll_dice(count, sides, 1, r)
            items: list[Item] = []
            for _ in range(n):
                if kind == "gem":
                    items.append(_make_gemstone(value, r))
                else:
                    items.append(_make_art_object(value, r))
            return items
    return []


# --------------------------------------------------------------------------- #
# Magic item tables (DMG p.144-146, simplified)
# --------------------------------------------------------------------------- #
# Each table is a weighted list of (weight, builder). The builder is a function
# that returns an Item. Values are tuned to DMG rarity guidelines.

def _potion(name: str, effect: str, rarity: Rarity, value: int):
    return create_potion(name, effect, uses=1, rarity=rarity, value=value)


def _scroll(name: str, rarity: Rarity, value: int):
    return Item(
        id="",
        name=name,
        item_type=ItemType.SCROLL,
        description=f"A spell scroll holding the magic of {name}.",
        rarity=rarity,
        value=value,
        weight=0.0,
        uses=1,
        max_uses=1,
    )


def _magic_weapon(name: str, rarity: Rarity, value: int, bonus: int,
                  dice: str, dmg_type: str):
    weapon = create_weapon(name, dice, dmg_type, bonus, rarity, value, weight=4)
    weapon.attack_bonus = bonus
    return weapon


def _magic_armor(name: str, rarity: Rarity, value: int, bonus: int,
                 armor_type: ArmorType):
    armor = create_shield if armor_type == ArmorType.SHIELD else create_armor
    if armor_type == ArmorType.SHIELD:
        item = create_shield(name, bonus, rarity, value, weight=6)
    else:
        item = create_armor(name, armor_type, bonus, None, rarity, value, weight=45)
    item.armor_bonus = bonus + (2 if armor_type == ArmorType.SHIELD else 0)
    return item


# Table A — common consumables & trinkets (DMG). Weights sum to 100.
MAGIC_ITEM_TABLE_A: list[tuple[int, str, Callable[[], Item]]] = [
    (50, "Potion of Healing", lambda: _potion("Potion of Healing", "Restores 2d4+2 HP", Rarity.COMMON, 50)),
    (20, "Cantrip Scroll", lambda: _scroll("Spell Scroll (Cantrip)", Rarity.COMMON, 20)),
    (12, "Potion of Climbing", lambda: _potion("Potion of Climbing", "Advantage on climbing for 1 hour", Rarity.COMMON, 90)),
    (10, "Spell Scroll (1st)", lambda: _scroll("Spell Scroll (1st Level)", Rarity.COMMON, 50)),
    (5, "Spell Scroll (2nd)", lambda: _scroll("Spell Scroll (2nd Level)", Rarity.UNCOMMON, 100)),
    (3, "Trinket", lambda: Item(id="", name="Mysterious Trinket", item_type=ItemType.MISC, description="A small curious object of unknown purpose.", rarity=Rarity.COMMON, value=5, weight=0.0)),
]

# Table B — uncommon potions, minor gear, +1 ammunition.
MAGIC_ITEM_TABLE_B: list[tuple[int, str, Callable[[], Item]]] = [
    (25, "Potion of Greater Healing", lambda: _potion("Potion of Greater Healing", "Restores 4d4+4 HP", Rarity.UNCOMMON, 150)),
    (20, "Spell Scroll (2nd)", lambda: _scroll("Spell Scroll (2nd Level)", Rarity.UNCOMMON, 100)),
    (15, "Spell Scroll (3rd)", lambda: _scroll("Spell Scroll (3rd Level)", Rarity.UNCOMMON, 200)),
    (15, "Potion of Climbing", lambda: _potion("Potion of Climbing", "Advantage on climbing for 1 hour", Rarity.COMMON, 90)),
    (10, "Potion of Healing", lambda: _potion("Potion of Healing", "Restores 2d4+2 HP", Rarity.COMMON, 50)),
    (8, "Driftglobe", lambda: Item(id="", name="Driftglobe", item_type=ItemType.MISC, description="A small orb that sheds light at command.", rarity=Rarity.UNCOMMON, value=200, weight=1.0)),
    (4, "Potion of Animal Friendship", lambda: _potion("Potion of Animal Friendship", "Charm beasts for 1 hour", Rarity.UNCOMMON, 200)),
    (3, "Potion of Water Breathing", lambda: _potion("Potion of Water Breathing", "Breathe underwater for 1 hour", Rarity.UNCOMMON, 200)),
]

# Table C — uncommon-to-rare potions, +1 weapons/armor.
MAGIC_ITEM_TABLE_C: list[tuple[int, str, Callable[[], Item]]] = [
    (15, "Potion of Superior Healing", lambda: _potion("Potion of Superior Healing", "Restores 8d4+8 HP", Rarity.RARE, 450)),
    (15, "Spell Scroll (4th)", lambda: _scroll("Spell Scroll (4th Level)", Rarity.RARE, 400)),
    (15, "Ammunition +1", lambda: _magic_weapon("Arrows +1 (x3)", Rarity.UNCOMMON, 80, 1, "1d6", "piercing")),
    (10, "Potion of Clairvoyance", lambda: _potion("Potion of Clairvoyance", "See through an invisible sensor", Rarity.RARE, 450)),
    (10, "Potion of Diminution", lambda: _potion("Potion of Diminution", "Shrink to tiny size for 1d4 hours", Rarity.RARE, 450)),
    (10, "Potion of Growth", lambda: _potion("Potion of Growth", "Grow to large size for 1d4 hours", Rarity.RARE, 450)),
    (10, "Potion of Water Breathing", lambda: _potion("Potion of Water Breathing", "Breathe underwater for 1 hour", Rarity.UNCOMMON, 200)),
    (5, "Spell Scroll (5th)", lambda: _scroll("Spell Scroll (5th Level)", Rarity.RARE, 500)),
    (5, "Elixir of Health", lambda: _potion("Elixir of Health", "Cures blindness, deafness, disease, and poison", Rarity.RARE, 450)),
    (5, "Oil of Etherealness", lambda: _potion("Oil of Etherealness", "Enter the Ethereal Plane", Rarity.RARE, 500)),
]

# Table D — rare consumables, +2/+1 weapons and armor.
MAGIC_ITEM_TABLE_D: list[tuple[int, str, Callable[[], Item]]] = [
    (20, "Potion of Supreme Healing", lambda: _potion("Potion of Supreme Healing", "Restores 10d4+20 HP", Rarity.VERY_RARE, 1350)),
    (15, "Potion of Invisibility", lambda: _potion("Potion of Invisibility", "Become invisible for 1 hour", Rarity.VERY_RARE, 5000)),
    (15, "Potion of Speed", lambda: _potion("Potion of Speed", "Haste for 1 minute", Rarity.VERY_RARE, 1800)),
    (10, "Spell Scroll (6th)", lambda: _scroll("Spell Scroll (6th Level)", Rarity.VERY_RARE, 900)),
    (10, "Spell Scroll (7th)", lambda: _scroll("Spell Scroll (7th Level)", Rarity.VERY_RARE, 1200)),
    (8, "+1 Weapon", lambda: _magic_weapon("+1 Longsword", Rarity.UNCOMMON, 2000, 1, "1d8", "slashing")),
    (8, "+1 Armor", lambda: _magic_armor("+1 Chain Mail", Rarity.UNCOMMON, 2000, 1, ArmorType.HEAVY)),
    (6, "Potion of Flying", lambda: _potion("Potion of Flying", "Fly for 1 hour", Rarity.VERY_RARE, 1800)),
    (5, "Potion of Healing Superior", lambda: _potion("Potion of Superior Healing", "Restores 8d4+8 HP", Rarity.RARE, 450)),
    (3, "Spell Scroll (8th)", lambda: _scroll("Spell Scroll (8th Level)", Rarity.VERY_RARE, 3000)),
]

# Table E — very rare/legendary magic items.
MAGIC_ITEM_TABLE_E: list[tuple[int, str, Callable[[], Item]]] = [
    (30, "Spell Scroll (8th)", lambda: _scroll("Spell Scroll (8th Level)", Rarity.VERY_RARE, 3000)),
    (20, "Potion of Storm Giant Strength", lambda: _potion("Potion of Storm Giant Strength", "Strength becomes 29 for 1 hour", Rarity.LEGENDARY, 8000)),
    (15, "Spell Scroll (9th)", lambda: _scroll("Spell Scroll (9th Level)", Rarity.LEGENDARY, 5000)),
    (15, "+2 Weapon", lambda: _magic_weapon("+2 Longsword", Rarity.RARE, 4000, 2, "1d8", "slashing")),
    (10, "+2 Armor", lambda: _magic_armor("+2 Plate Armor", Rarity.RARE, 5000, 2, ArmorType.HEAVY)),
    (5, "Potion of Supreme Healing", lambda: _potion("Potion of Supreme Healing", "Restores 10d4+20 HP", Rarity.VERY_RARE, 1350)),
    (5, "Bag of Holding", lambda: Item(id="", name="Bag of Holding", item_type=ItemType.MISC, description="An extradimensional bag that holds far more than it should.", rarity=Rarity.RARE, value=2000, weight=15.0)),
]

# Table F — high-tier, often legendary.
MAGIC_ITEM_TABLE_F: list[tuple[int, str, Callable[[], Item]]] = [
    (15, "Spell Scroll (8th)", lambda: _scroll("Spell Scroll (8th Level)", Rarity.VERY_RARE, 3000)),
    (15, "+3 Weapon", lambda: _magic_weapon("+3 Longsword", Rarity.VERY_RARE, 8000, 3, "1d8", "slashing")),
    (15, "+3 Armor", lambda: _magic_armor("+3 Plate Armor", Rarity.VERY_RARE, 9000, 3, ArmorType.HEAVY)),
    (15, "+2 Shield", lambda: _magic_armor("+2 Shield", Rarity.RARE, 3000, 2, ArmorType.SHIELD)),
    (10, "Spell Scroll (9th)", lambda: _scroll("Spell Scroll (9th Level)", Rarity.LEGENDARY, 5000)),
    (10, "Potion of Storm Giant Strength", lambda: _potion("Potion of Storm Giant Strength", "Strength becomes 29 for 1 hour", Rarity.LEGENDARY, 8000)),
    (5, "Holy Avenger", lambda: _magic_weapon("Holy Avenger", Rarity.LEGENDARY, 50000, 3, "2d6", "slashing")),
    (5, "Cloak of Invisibility", lambda: Item(id="", name="Cloak of Invisibility", item_type=ItemType.ARMOR, description="A cloak that turns its wearer invisible at will.", rarity=Rarity.LEGENDARY, value=25000, weight=1.0, armor_type=ArmorType.LIGHT)),
    (5, "Ring of Three Wishes", lambda: Item(id="", name="Ring of Three Wishes", item_type=ItemType.MISC, description="A ring holding three wishes.", rarity=Rarity.LEGENDARY, value=50000, weight=0.0)),
    (5, "Vorpal Sword", lambda: _magic_weapon("Vorpal Sword", Rarity.LEGENDARY, 100000, 3, "1d8", "slashing")),
]

MAGIC_ITEM_TABLES: dict[str, list[tuple[int, str, Callable[[], Item]]]] = {
    "A": MAGIC_ITEM_TABLE_A,
    "B": MAGIC_ITEM_TABLE_B,
    "C": MAGIC_ITEM_TABLE_C,
    "D": MAGIC_ITEM_TABLE_D,
    "E": MAGIC_ITEM_TABLE_E,
    "F": MAGIC_ITEM_TABLE_F,
}


def _weighted_choice(table: list[tuple[int, str, Callable[[], Item]]],
                     rng: Rng = None) -> Callable[[], Item]:
    """Pick a builder from a weighted magic-item table."""
    r = rng or random
    total = sum(weight for weight, _, _ in table)
    pick = r.randint(1, total)
    upto = 0
    for weight, _, builder in table:
        upto += weight
        if pick <= upto:
            return builder
    return table[-1][2]  # fallback


def _roll_magic_table(table_key: str,
                      rng: Rng = None) -> Item:
    """Roll a single magic item from the named table (A-F)."""
    table = MAGIC_ITEM_TABLES.get(table_key, MAGIC_ITEM_TABLES["A"])
    builder = _weighted_choice(table, rng)
    return builder()


# Hoard magic-item tables: (min_roll, max_roll, [(count_dice, count_sides, table_key)])
# An entry's list may have multiple draws (e.g. "1d3 from table C").
HOARD_MAGIC: dict[str, list[tuple[int, int, list[tuple[int, int, str]]]]] = {
    "0-4": [
        (1, 70, []),  # no magic
        (71, 95, [(1, 1, "A")]),
        (96, 100, [(1, 3, "A")]),
    ],
    "5-10": [
        (1, 60, []),
        (61, 80, [(1, 4, "A")]),
        (81, 90, [(1, 1, "B")]),
        (91, 96, [(1, 4, "B")]),
        (97, 100, [(1, 1, "C")]),
    ],
    "11-16": [
        (1, 33, []),
        (34, 66, [(1, 4, "A")]),
        (67, 78, [(1, 1, "C")]),
        (79, 86, [(1, 1, "B")]),
        (87, 94, [(1, 4, "B")]),
        (95, 98, [(1, 1, "F")]),
        (99, 100, [(1, 4, "F")]),
    ],
    "17+": [
        (1, 26, []),
        (27, 40, [(1, 4, "C")]),
        (41, 50, [(1, 1, "D")]),
        (51, 62, [(1, 4, "D")]),
        (63, 70, [(1, 1, "E")]),
        (71, 78, [(1, 1, "F")]),
        (79, 90, [(1, 4, "F")]),
        (91, 96, [(1, 1, "E")]),
        (97, 100, [(1, 4, "E")]),
    ],
}


def _roll_hoard_magic(tier: str,
                      rng: Rng = None) -> list[Item]:
    """Roll magic items for a hoard of the given CR tier."""
    r = rng or random
    table = HOARD_MAGIC.get(tier, HOARD_MAGIC["0-4"])
    roll = r.randint(1, 100)
    for lo, hi, draws in table:
        if lo <= roll <= hi:
            items: list[Item] = []
            for count, sides, key in draws:
                n = _roll_dice(count, sides, 1, r)
                for _ in range(n):
                    items.append(_roll_magic_table(key, r))
            return items
    return []


# --------------------------------------------------------------------------- #
# Loot result
# --------------------------------------------------------------------------- #

@dataclass
class LootResult:
    """The outcome of rolling a loot table — coins plus items."""
    coins: CoinPurse = field(default_factory=CoinPurse)
    items: list[Item] = field(default_factory=list)
    source: str = "individual"  # "individual" | "hoard" | "chest"
    cr: float = 0.0

    @property
    def gold_total(self) -> float:
        """Coin value in gold pieces (items are separate)."""
        return self.coins.total_gp()

    @property
    def item_value_total(self) -> int:
        """Sum of all item base values in gold pieces."""
        return sum(item.value for item in self.items)

    @property
    def is_empty(self) -> bool:
        return self.coins.is_empty() and not self.items

    def add(self, other: "LootResult") -> None:
        self.coins.add(other.coins)
        self.items.extend(other.items)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "cr": self.cr,
            "coins": self.coins.to_dict(),
            "gold_total": self.gold_total,
            "items": [item.to_dict() for item in self.items],
            "item_value_total": self.item_value_total,
            "is_empty": self.is_empty,
        }


# --------------------------------------------------------------------------- #
# Public roll API
# --------------------------------------------------------------------------- #

def roll_individual_loot(cr: float,
                         rng: Rng = None) -> LootResult:
    """Roll individual treasure for one defeated creature."""
    r = rng or random
    return LootResult(
        coins=roll_individual_treasure(cr, r),
        items=[],
        source="individual",
        cr=cr,
    )


def roll_hoard_loot(cr: float,
                    rng: Rng = None) -> LootResult:
    """Roll a full hoard (coins + valuables + magic items) for the CR tier."""
    r = rng or random
    tier = cr_tier(cr)
    return LootResult(
        coins=_roll_hoard_coins(tier, r),
        items=_roll_hoard_valuables(tier, r) + _roll_hoard_magic(tier, r),
        source="hoard",
        cr=cr,
    )


# Chest difficulty tiers (independent of any monster CR).
CHEST_TIERS = {
    "common": {"cr": 1, "label": "Common Chest"},
    "uncommon": {"cr": 5, "label": "Uncommon Chest"},
    "rare": {"cr": 11, "label": "Rare Chest"},
    "legendary": {"cr": 17, "label": "Legendary Chest"},
}


def roll_chest_loot(tier: str = "common",
                    rng: Rng = None) -> LootResult:
    """Roll treasure for a standalone chest of the given difficulty tier."""
    r = rng or random
    spec = CHEST_TIERS.get(tier.lower(), CHEST_TIERS["common"])
    result = roll_hoard_loot(spec["cr"], r)
    result.source = "chest"
    return result


def loot_table_overview() -> dict:
    """Return a read-only description of all loot tables (for the API/DM)."""
    return {
        "cr_tiers": list(INDIVIDUAL_TREASURE.keys()),
        "individual_treasure": {
            tier: [
                {"range": f"{lo}-{hi}", "denomination": denom,
                 "dice": f"{count}d{sides}{' x' + str(mult) if mult > 1 else ''}"}
                for lo, hi, denom, count, sides, mult in entries
            ]
            for tier, entries in INDIVIDUAL_TREASURE.items()
        },
        "chest_tiers": {k: v["label"] for k, v in CHEST_TIERS.items()},
        "gem_values": sorted(GEMS.keys()),
        "art_values": sorted(ART_OBJECTS.keys()),
        "magic_item_tables": {k: sum(w for w, _, _ in v) for k, v in MAGIC_ITEM_TABLES.items()},
    }
