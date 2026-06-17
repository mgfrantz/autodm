"""
Shop / economy engine — merchants, buying, selling, and gold.

Implements DnD 5e-flavoured trading mechanics:

* **Merchant types** — blacksmith (weapons/armor/shields), alchemist (potions),
  general store (misc goods & supplies), arcane shop (scrolls & magic items),
  fletcher (bows & ammunition). Each type stocks a different inventory and will
  only *buy back* items in its area of expertise.
* **Settlement tiers** — hamlet → metropolis. A bigger settlement's merchants
  have more gold on hand to buy the player's loot and carry a deeper stock.
  (Based on the DMG's "settlement" gold guidelines, simplified.)
* **Pricing** — merchants sell at full value (adjusted by an optional markup)
  and buy from the player at a percentage of base value (default 50 %, the PHB
  "selling treasure" rule). Magic items use a separate, lower sell rate.
* **Finite economy** — a merchant only has so much gold. Once it runs out it
  stops buying. Buying from a merchant depletes its stock (and restocking
  refills it). This makes the economy feel real.

The engine is pure: it operates on ``Merchant`` / ``Inventory`` dataclasses and
returns ``TransactionResult`` objects. Persistence is left to the API layer,
which stores merchant state in the game's ``game_state`` JSON.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.engine.inventory import (
    Item,
    Inventory,
    ItemType,
    Rarity,
    ArmorType,
    create_weapon,
    create_armor,
    create_shield,
    create_potion,
)


# --------------------------------------------------------------------------- #
# Merchant archetypes
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class MerchantArchetype:
    """Static definition of a merchant type — what it stocks & buys back."""

    key: str
    label: str  # human-readable, e.g. "Blacksmith"
    description: str
    # Item types this merchant will buy from the player.
    buys: tuple[str, ...]
    # Rarity cap for generated stock (merchants rarely stock legendaries).
    max_rarity: Rarity = Rarity.RARE
    # Sell-side markup applied to base value (1.0 = base value).
    buy_markup: float = 1.0
    # Default fraction of base value paid when buying from the player.
    sell_rate: float = 0.5

    def buys_type(self, item_type: ItemType) -> bool:
        return item_type.value in self.buys


MERCHANT_TYPES: dict[str, MerchantArchetype] = {
    "blacksmith": MerchantArchetype(
        key="blacksmith",
        label="Blacksmith",
        description="Sells weapons, armor, and shields. Buys martial gear.",
        buys=("weapon", "armor"),
    ),
    "alchemist": MerchantArchetype(
        key="alchemist",
        label="Alchemist",
        description="Brews and sells potions of all kinds. Buys potions.",
        buys=("potion",),
    ),
    "general": MerchantArchetype(
        key="general",
        label="General Store",
        description="Peddles everyday supplies and sundries. Buys most goods.",
        buys=("misc", "potion", "weapon", "armor", "scroll"),
        buy_markup=1.1,  # general stores charge a little extra
    ),
    "arcane": MerchantArchetype(
        key="arcane",
        label="Arcane Shop",
        description="Deals in scrolls and enchanted items. Buys magic goods.",
        buys=("scroll", "weapon", "armor"),
        max_rarity=Rarity.VERY_RARE,
        buy_markup=1.2,  # magic comes at a premium
        sell_rate=0.4,  # and they drive a hard bargain on buy-back
    ),
    "fletcher": MerchantArchetype(
        key="fletcher",
        label="Fletcher",
        description="Crafts bows and ammunition. Buys ranged weapons.",
        buys=("weapon",),
        buy_markup=0.95,  # cheaper on bows than the smith
    ),
}


# --------------------------------------------------------------------------- #
# Settlement tiers — govern merchant gold reserves and stock depth
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SettlementTier:
    key: str
    label: str
    gold_reserve: int        # how much gold a merchant here has to buy loot
    stock_multiplier: float  # scales base stock quantities
    rarity_floor: Rarity     # minimum rarity floor for stocked items


SETTLEMENT_TIERS: dict[str, SettlementTier] = {
    "hamlet": SettlementTier("hamlet", "Hamlet", 25, 0.5, Rarity.COMMON),
    "village": SettlementTier("village", "Village", 100, 0.75, Rarity.COMMON),
    "town": SettlementTier("town", "Town", 500, 1.0, Rarity.COMMON),
    "city": SettlementTier("city", "City", 2000, 1.25, Rarity.UNCOMMON),
    "metropolis": SettlementTier("metropolis", "Metropolis", 10000, 1.5, Rarity.UNCOMMON),
}

DEFAULT_TIER = "town"


def resolve_tier(tier: Optional[str]) -> SettlementTier:
    """Return the SettlementTier for a key, falling back to the default."""
    if tier and tier.lower() in SETTLEMENT_TIERS:
        return SETTLEMENT_TIERS[tier.lower()]
    return SETTLEMENT_TIERS[DEFAULT_TIER]


def resolve_archetype(merchant_type: str) -> MerchantArchetype:
    """Return the MerchantArchetype for a key, falling back to general store."""
    if merchant_type.lower() in MERCHANT_TYPES:
        return MERCHANT_TYPES[merchant_type.lower()]
    return MERCHANT_TYPES["general"]


# --------------------------------------------------------------------------- #
# Merchant runtime state
# --------------------------------------------------------------------------- #

@dataclass
class StockEntry:
    """A single item line in a merchant's catalogue."""

    item: Item
    quantity: int

    def to_dict(self) -> dict:
        return {"item": self.item.to_dict(), "quantity": self.quantity}

    @classmethod
    def from_dict(cls, data: dict) -> "StockEntry":
        return cls(item=Item.from_dict(data["item"]), quantity=int(data.get("quantity", 1)))


@dataclass
class Merchant:
    """A specific, stateful merchant the player can trade with."""

    name: str
    archetype: MerchantArchetype
    tier: SettlementTier
    gold: int                       # gold the merchant has to buy loot
    stock: list[StockEntry] = field(default_factory=list)

    @property
    def merchant_type(self) -> str:
        return self.archetype.key

    @property
    def settlement_tier(self) -> str:
        return self.tier.key

    def find_stock(self, item_id: str) -> Optional[tuple[int, StockEntry]]:
        for idx, entry in enumerate(self.stock):
            if entry.item.id == item_id:
                return idx, entry
        return None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "merchant_type": self.merchant_type,
            "label": self.archetype.label,
            "description": self.archetype.description,
            "settlement_tier": self.settlement_tier,
            "gold": self.gold,
            "stock": [e.to_dict() for e in self.stock],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Merchant":
        archetype = resolve_archetype(data.get("merchant_type", "general"))
        tier = resolve_tier(data.get("settlement_tier"))
        return cls(
            name=data.get("name", archetype.label),
            archetype=archetype,
            tier=tier,
            gold=int(data.get("gold", tier.gold_reserve)),
            stock=[StockEntry.from_dict(e) for e in data.get("stock", [])],
        )


# --------------------------------------------------------------------------- #
# Transaction result
# --------------------------------------------------------------------------- #

@dataclass
class TransactionResult:
    """Outcome of a buy or sell attempt."""

    success: bool
    message: str
    transaction_type: str  # "buy" or "sell"
    item_name: str = ""
    item_id: str = ""
    quantity: int = 0
    unit_price: int = 0
    total: int = 0           # gold spent (buy) or gained (sell)
    gold_after: int = 0      # player's gold after the transaction
    merchant_gold_after: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "transaction_type": self.transaction_type,
            "item_name": self.item_name,
            "item_id": self.item_id,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "total": self.total,
            "gold_after": self.gold_after,
            "merchant_gold_after": self.merchant_gold_after,
        }


# --------------------------------------------------------------------------- #
# Price calculation
# --------------------------------------------------------------------------- #

# Items with rarity at or above this are treated as "magic items" for the
# purpose of the discounted magic-item sell rate.
MAGIC_RARITY_FLOOR = Rarity.UNCOMMON


def _is_magic(item: Item) -> bool:
    """An item is 'magic' if its rarity is uncommon or higher."""
    order = [Rarity.COMMON, Rarity.UNCOMMON, Rarity.RARE, Rarity.VERY_RARE, Rarity.LEGENDARY]
    return order.index(item.rarity) >= order.index(MAGIC_RARITY_FLOOR)


def buy_price(item: Item, archetype: MerchantArchetype) -> int:
    """Gold a player must pay to buy an item from a merchant.

    Base value scaled by the merchant's markup, never below 1 gp for non-free
    items.
    """
    base = max(0, item.value)
    price = round(base * archetype.buy_markup)
    if base > 0 and price < 1:
        price = 1
    return price


def sell_price(item: Item, archetype: MerchantArchetype) -> int:
    """Gold a player receives when selling an item to a merchant.

    Mundane goods use the archetype's sell_rate (default 50 %). Magic items
    (uncommon+) use a flat 50 % too unless the archetype negotiated lower — but
    a merchant that does not deal in an item's type offers nothing for it.
    """
    base = max(0, item.value)
    rate = archetype.sell_rate
    price = round(base * rate)
    if base > 0 and price < 1:
        price = 1
    return price


# --------------------------------------------------------------------------- #
# Merchant creation / stock generation
# --------------------------------------------------------------------------- #

# Name pools per archetype (picked deterministically by name hash so a given
# merchant in a given town is always the same).
_NAME_POOL: dict[str, tuple[str, ...]] = {
    "blacksmith": ("Grimm Ironforge", "Hilda Stonehammer", "Borin Coalbeard", "Mara Steelfist"),
    "alchemist": ("Elara Nightshade", "Voris Goldenbrew", "Wren Mossheart", "Old Fenwick"),
    "general": ("Tomas Goodfellow", "Bessie Thatcher", "Odo Pennywise", "Mabel Cooper"),
    "arcane": ("Archmage Thessaly", "Zerith the Binder", "Lady Quill", "Magister Orin"),
    "fletcher": ("Dalia Quickhand", "Corin Ashbow", "Nettle Longshot", "Pip Underleaf"),
}


def _merchant_name(archetype: MerchantArchetype, seed: str) -> str:
    pool = _NAME_POOL.get(archetype.key, ("a wandering merchant",))
    if not seed:
        return pool[0]
    return pool[hash(seed) % len(pool)]


def _base_stock_for(archetype: MerchantArchetype) -> list[tuple[Item, int]]:
    """The canonical catalogue a fresh merchant of this type carries.

    Returns ``(item, base_quantity)`` pairs; the base quantity is scaled by the
    settlement tier when the merchant is stocked. Non-stackable gear (weapons,
    armor) gets a modest count; stackables (potions, misc) get more.
    """
    def w(name, dice, dtype="slashing", bonus=0, rarity=Rarity.COMMON, value=10, weight=3, qty=3):
        return (create_weapon(name, dice, dtype, bonus, rarity, value, weight), qty)

    def a(name, atype, bonus=0, dex_limit=None, rarity=Rarity.COMMON, value=10, weight=10, qty=2):
        return (create_armor(name, atype, bonus, dex_limit, rarity, value, weight), qty)

    def p(name, effect, rarity=Rarity.COMMON, value=50, qty=4):
        return (create_potion(name, effect, 1, rarity, value), qty)

    def s(value, weight, qty, name):
        return (_make_misc(name, value, weight), qty)

    if archetype.key == "blacksmith":
        return [
            w("Longsword", "1d8", "slashing", 0, Rarity.COMMON, 15, 3, 3),
            w("Shortsword", "1d6", "piercing", 0, Rarity.COMMON, 10, 2, 3),
            w("Battleaxe", "1d8", "slashing", 0, Rarity.COMMON, 10, 4, 2),
            w("Warhammer", "1d8", "bludgeoning", 0, Rarity.COMMON, 15, 2, 2),
            w("Dagger", "1d4", "piercing", 0, Rarity.COMMON, 2, 1, 4),
            a("Leather Armor", ArmorType.LIGHT, 0, None, Rarity.COMMON, 10, 10, 2),
            a("Chain Mail", ArmorType.HEAVY, 0, None, Rarity.COMMON, 75, 55, 1),
            a("Scale Mail", ArmorType.MEDIUM, 0, 2, Rarity.COMMON, 50, 45, 2),
            (create_shield("Shield", 2, Rarity.COMMON, 10, 6), 2),
        ]
    if archetype.key == "alchemist":
        return [
            p("Potion of Healing", "Restores 2d4+2 HP", Rarity.COMMON, 50, 4),
            p("Greater Healing", "Restores 4d4+4 HP", Rarity.UNCOMMON, 150, 2),
            p("Potion of Shield of Faith", "Grants +2 AC", Rarity.UNCOMMON, 100, 2),
            p("Antitoxin", "Advantage vs poison", Rarity.COMMON, 50, 3),
            p("Potion of Climbing", "Climbing speed", Rarity.COMMON, 75, 2),
        ]
    if archetype.key == "general":
        return [
            p("Potion of Healing", "Restores 2d4+2 HP", Rarity.COMMON, 50, 3),
            s(2, 5, 4, "Backpack"),
            s(1, 1, 6, "Torch"),
            s(1, 10, 4, "Rope (50 ft.)"),
            s(5, 5, 3, "Rations (7 days)"),
            s(1, 5, 3, "Bedroll"),
        ]
    if archetype.key == "arcane":
        return [
            (_make_scroll("Scroll of Magic Missile", Rarity.UNCOMMON, 100), 2),
            (_make_scroll("Scroll of Identify", Rarity.UNCOMMON, 100), 2),
            (_make_scroll("Scroll of Cure Wounds", Rarity.UNCOMMON, 100), 2),
            (create_weapon("+1 Dagger", "1d4", "piercing", 1, Rarity.UNCOMMON, 300, 1), 1),
            (create_armor("+1 Leather Armor", ArmorType.LIGHT, 1, None, Rarity.UNCOMMON, 400, 10), 1),
        ]
    if archetype.key == "fletcher":
        return [
            w("Shortbow", "1d6", "piercing", 0, Rarity.COMMON, 25, 2, 2),
            w("Longbow", "1d8", "piercing", 0, Rarity.COMMON, 50, 2, 2),
            w("Crossbow, Light", "1d8", "piercing", 0, Rarity.COMMON, 25, 5, 2),
            s(1, 1, 5, "Arrows (20)"),
            s(1, 1, 3, "Quiver"),
        ]
    return [(_make_misc("Lantern", 5, 10), 2)]


def _make_misc(name: str, value: int, weight: float) -> Item:
    return Item(
        id="",
        name=name,
        item_type=ItemType.MISC,
        description=f"A {name.lower()}.",
        rarity=Rarity.COMMON,
        value=value,
        weight=weight,
        quantity=1,
    )


def _make_scroll(name: str, rarity: Rarity, value: int) -> Item:
    return Item(
        id="",
        name=name,
        item_type=ItemType.SCROLL,
        description=f"A scroll inscribed with {name.replace('Scroll of ', '').lower()}.",
        rarity=rarity,
        value=value,
        weight=0.1,
        uses=1,
        max_uses=1,
        quantity=1,
    )


def _scale_quantity(base: int, tier: SettlementTier) -> int:
    qty = round(base * tier.stock_multiplier)
    return max(1, qty)


def create_merchant(
    merchant_type: str,
    settlement_tier: Optional[str] = None,
    name: Optional[str] = None,
) -> Merchant:
    """Build a fully-stocked merchant of the given type for a settlement tier."""
    archetype = resolve_archetype(merchant_type)
    tier = resolve_tier(settlement_tier)
    merchant = Merchant(
        name=name or _merchant_name(archetype, f"{archetype.key}:{tier.key}"),
        archetype=archetype,
        tier=tier,
        gold=tier.gold_reserve,
        stock=[],
    )
    restock(merchant)
    return merchant


def restock(merchant: Merchant, restore_gold: bool = True) -> dict:
    """Refill a merchant's stock (and, optionally, its gold reserve).

    Existing stock quantities are *reset* to their tier-scaled baseline; items
    that were fully bought out are replenished. Returns a summary dict.
    """
    base_items = _base_stock_for(merchant.archetype)
    # Group identical items so stackable potions don't produce duplicate lines.
    merchant.stock = []
    for item, base_qty in base_items:
        qty = _scale_quantity(base_qty, merchant.tier)
        merchant.stock.append(StockEntry(item=item, quantity=qty))

    if restore_gold:
        merchant.gold = merchant.tier.gold_reserve

    return {
        "merchant_type": merchant.merchant_type,
        "restocked_lines": len(merchant.stock),
        "gold_restored": restore_gold,
        "gold": merchant.gold,
    }


# --------------------------------------------------------------------------- #
# Transactions
# --------------------------------------------------------------------------- #

def execute_buy(
    merchant: Merchant,
    inventory: Inventory,
    player_gold: int,
    item_id: str,
    quantity: int = 1,
) -> tuple[TransactionResult, int]:
    """Player buys ``quantity`` of a stocked item from the merchant.

    Returns ``(result, player_gold_after)``. On success the item is added to the
    player's ``inventory`` and removed from the merchant's stock; the merchant's
    gold is unchanged (it gains the gold, but that's reflected in the result).
    """
    quantity = max(1, int(quantity))
    found = merchant.find_stock(item_id)
    if not found:
        res = TransactionResult(
            success=False,
            message="That item is not for sale here.",
            transaction_type="buy",
            gold_after=player_gold,
            merchant_gold_after=merchant.gold,
        )
        return res, player_gold

    _, entry = found
    item = entry.item

    if entry.quantity < quantity:
        res = TransactionResult(
            success=False,
            message=f"Only {entry.quantity} of {item.name} in stock.",
            transaction_type="buy",
            item_name=item.name,
            item_id=item.id,
            quantity=quantity,
            gold_after=player_gold,
            merchant_gold_after=merchant.gold,
        )
        return res, player_gold

    unit = buy_price(item, merchant.archetype)
    total = unit * quantity

    if player_gold < total:
        res = TransactionResult(
            success=False,
            message=f"You need {total} gp but only have {player_gold} gp.",
            transaction_type="buy",
            item_name=item.name,
            item_id=item.id,
            quantity=quantity,
            unit_price=unit,
            total=total,
            gold_after=player_gold,
            merchant_gold_after=merchant.gold,
        )
        return res, player_gold

    # --- complete the purchase --------------------------------------------- #
    for _ in range(quantity):
        # Fresh copy (new id) so non-stackable gear doesn't alias the stock item.
        bought = Item.from_dict(item.to_dict())
        object.__setattr__(bought, "id", "")  # force a new UUID
        inventory.add_item(bought)

    entry.quantity -= quantity
    if entry.quantity <= 0:
        merchant.stock = [e for e in merchant.stock if e.item.id != item.id]

    player_gold -= total
    merchant.gold += total

    result = TransactionResult(
        success=True,
        message=f"Bought {quantity}x {item.name} for {total} gp.",
        transaction_type="buy",
        item_name=item.name,
        item_id=item.id,
        quantity=quantity,
        unit_price=unit,
        total=total,
        gold_after=player_gold,
        merchant_gold_after=merchant.gold,
    )
    return result, player_gold


def execute_sell(
    merchant: Merchant,
    inventory: Inventory,
    player_gold: int,
    item_id: str,
    quantity: int = 1,
) -> tuple[TransactionResult, int]:
    """Player sells ``quantity`` of an owned item to the merchant.

    Returns ``(result, player_gold_after)``. The merchant will only buy items it
    deals in, and only while it still has gold. On success the item is removed
    from the player's ``inventory`` and the merchant's gold is reduced.
    """
    quantity = max(1, int(quantity))
    item = inventory.get_item(item_id)
    if not item:
        res = TransactionResult(
            success=False,
            message="You don't have that item.",
            transaction_type="sell",
            gold_after=player_gold,
            merchant_gold_after=merchant.gold,
        )
        return res, player_gold

    available = item.quantity or 1
    if quantity > available:
        res = TransactionResult(
            success=False,
            message=f"You only have {available} of {item.name}.",
            transaction_type="sell",
            item_name=item.name,
            item_id=item.id,
            quantity=quantity,
            gold_after=player_gold,
            merchant_gold_after=merchant.gold,
        )
        return res, player_gold

    if not merchant.archetype.buys_type(item.item_type):
        res = TransactionResult(
            success=False,
            message=f"{merchant.name} doesn't deal in {item.item_type.value}s.",
            transaction_type="sell",
            item_name=item.name,
            item_id=item.id,
            quantity=quantity,
            gold_after=player_gold,
            merchant_gold_after=merchant.gold,
        )
        return res, player_gold

    unit = sell_price(item, merchant.archetype)
    total = unit * quantity

    if merchant.gold < total:
        res = TransactionResult(
            success=False,
            message=f"{merchant.name} can't afford that (only {merchant.gold} gp on hand).",
            transaction_type="sell",
            item_name=item.name,
            item_id=item.id,
            quantity=quantity,
            unit_price=unit,
            total=total,
            gold_after=player_gold,
            merchant_gold_after=merchant.gold,
        )
        return res, player_gold

    # --- complete the sale ------------------------------------------------- #
    inventory.remove_item(item_id, quantity)
    player_gold += total
    merchant.gold -= total

    result = TransactionResult(
        success=True,
        message=f"Sold {quantity}x {item.name} for {total} gp.",
        transaction_type="sell",
        item_name=item.name,
        item_id=item.id,
        quantity=quantity,
        unit_price=unit,
        total=total,
        gold_after=player_gold,
        merchant_gold_after=merchant.gold,
    )
    return result, player_gold
