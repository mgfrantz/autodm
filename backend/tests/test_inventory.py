"""
Tests for the inventory engine: items, equipment slots, stacking,
serialization, and starting equipment.
"""
import pytest

from app.engine.inventory import (
    Item,
    Inventory,
    InventorySlot,
    ItemType,
    Rarity,
    ArmorType,
    create_weapon,
    create_armor,
    create_potion,
    get_starting_inventory,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_sword() -> Item:
    return create_weapon(
        name="Longsword",
        damage_dice="1d8",
        damage_type="slashing",
        attack_bonus=2,
        rarity=Rarity.COMMON,
        value=15,
        weight=3.0,
    )


def make_leather_armor() -> Item:
    return create_armor(
        name="Leather Armor",
        armor_type=ArmorType.LIGHT,
        armor_bonus=0,
        dex_limit=None,
        rarity=Rarity.COMMON,
        value=10,
        weight=10.0,
    )


def make_healing_potion() -> Item:
    return create_potion(
        name="Potion of Healing",
        effect="Restores 2d4+2 HP",
        uses=1,
        rarity=Rarity.COMMON,
        value=50,
    )


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------

class TestItem:
    def test_weapon_creation(self):
        weapon = make_sword()
        assert weapon.name == "Longsword"
        assert weapon.item_type == ItemType.WEAPON
        assert weapon.damage_dice_count == 1
        assert weapon.damage_dice_sides == 8
        assert weapon.attack_bonus == 2
        assert weapon.is_equippable
        assert not weapon.is_consumable
        assert not weapon.is_stackable
    
    def test_armor_creation(self):
        armor = make_leather_armor()
        assert armor.name == "Leather Armor"
        assert armor.item_type == ItemType.ARMOR
        assert armor.armor_type == ArmorType.LIGHT
        assert armor.is_equippable
        assert not armor.is_consumable
    
    def test_potion_creation(self):
        potion = make_healing_potion()
        assert potion.name == "Potion of Healing"
        assert potion.item_type == ItemType.POTION
        assert potion.uses == 1
        assert potion.max_uses == 1
        assert not potion.is_equippable
        assert potion.is_consumable
        assert potion.is_stackable
    
    def test_potion_use(self):
        potion = make_healing_potion()
        assert potion.uses == 1
        assert potion.is_depleted == False
        
        still_has = potion.use()
        assert potion.uses == 0
        assert still_has == False
        assert potion.is_depleted == True
    
    def test_auto_generate_id(self):
        item = Item(
            id="",
            name="Test",
            item_type=ItemType.MISC,
        )
        assert item.id != ""
        assert len(item.id) > 0
    
    def test_item_serialization(self):
        weapon = make_sword()
        data = weapon.to_dict()
        
        assert data["name"] == "Longsword"
        assert data["item_type"] == "weapon"
        assert data["damage_dice_count"] == 1
        assert data["damage_dice_sides"] == 8
        
        # Round-trip
        restored = Item.from_dict(data)
        assert restored.name == weapon.name
        assert restored.damage_dice_count == weapon.damage_dice_count
        assert restored.damage_dice_sides == weapon.damage_dice_sides
    
    def test_armor_ac_calculation_light(self):
        armor = make_leather_armor()  # Light armor
        # Light armor: base 11 + Dex mod
        ac = armor.get_ac_bonus(3)  # Dex +3
        assert ac == 14  # 11 + 3
        
        ac = armor.get_ac_bonus(0)  # Dex +0
        assert ac == 11
    
    def test_armor_ac_calculation_medium(self):
        armor = create_armor(
            name="Scale Mail",
            armor_type=ArmorType.MEDIUM,
            armor_bonus=0,
            dex_limit=2,
        )
        # Medium armor: base 14 + min(Dex, 2)
        ac = armor.get_ac_bonus(3)  # Dex +3, but capped at 2
        assert ac == 16  # 14 + 2
        
        ac = armor.get_ac_bonus(1)  # Dex +1
        assert ac == 15  # 14 + 1
    
    def test_armor_ac_calculation_heavy(self):
        armor = create_armor(
            name="Plate Mail",
            armor_type=ArmorType.HEAVY,
            armor_bonus=0,
            dex_limit=None,
        )
        # Heavy armor: base 16, no Dex
        ac = armor.get_ac_bonus(5)  # Dex +5, but ignored
        assert ac == 16
    
    def test_shield_ac_calculation(self):
        shield = create_armor(
            name="Shield",
            armor_type=ArmorType.SHIELD,
            armor_bonus=2,
        )
        ac = shield.get_ac_bonus(0)
        assert ac == 2


# ---------------------------------------------------------------------------
# InventorySlot
# ---------------------------------------------------------------------------

class TestInventorySlot:
    def test_creation(self):
        item = make_sword()
        slot = InventorySlot(item=item, equipped=False)
        
        assert slot.item == item
        assert slot.equipped == False
    
    def test_serialization(self):
        item = make_sword()
        slot = InventorySlot(item=item, equipped=True)
        data = slot.to_dict()
        
        assert data["equipped"] == True
        assert data["item"]["name"] == "Longsword"
        
        restored = InventorySlot.from_dict(data)
        assert restored.equipped == True
        assert restored.item.name == "Longsword"


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

class TestInventory:
    def test_empty_inventory(self):
        inv = Inventory()
        assert len(inv.slots) == 0
        assert inv.total_weight == 0.0
        assert inv.total_value == 0
        assert inv.equipped_weapon is None
        assert inv.equipped_armor is None
    
    def test_add_item(self):
        inv = Inventory()
        sword = make_sword()
        
        slot = inv.add_item(sword)
        assert len(inv.slots) == 1
        assert slot.item == sword
        assert inv.total_weight == 3.0
        assert inv.total_value == 15
    
    def test_add_multiple_items(self):
        inv = Inventory()
        inv.add_item(make_sword())
        inv.add_item(make_leather_armor())
        inv.add_item(make_healing_potion())
        
        assert len(inv.slots) == 3
        assert inv.total_weight == 13.5  # 3 + 10 + 0.5
        assert inv.total_value == 75  # 15 + 10 + 50
    
    def test_stack_consumables(self):
        inv = Inventory()
        potion1 = create_potion("Potion of Healing", "Heals", 1, Rarity.COMMON, 50)
        potion2 = create_potion("Potion of Healing", "Heals", 1, Rarity.COMMON, 50)
        
        inv.add_item(potion1)
        inv.add_item(potion2)
        
        # Should stack into one slot with quantity 2
        assert len(inv.slots) == 1
        assert inv.slots[0].item.quantity == 2
        assert inv.total_value == 100  # 50 * 2
    
    def test_get_item(self):
        inv = Inventory()
        sword = make_sword()
        inv.add_item(sword)
        
        found = inv.get_item(sword.id)
        assert found is not None
        assert found.name == "Longsword"
        
        not_found = inv.get_item("nonexistent")
        assert not_found is None
    
    def test_remove_item_full_quantity(self):
        inv = Inventory()
        sword = make_sword()
        inv.add_item(sword)
        
        success = inv.remove_item(sword.id, quantity=1)
        assert success == True
        assert len(inv.slots) == 0
    
    def test_remove_item_partial_quantity(self):
        inv = Inventory()
        potion = create_potion("Potion", "Heals", 1, Rarity.COMMON, 50, quantity=5)
        inv.add_item(potion)
        
        success = inv.remove_item(potion.id, quantity=2)
        assert success == True
        assert len(inv.slots) == 1
        assert inv.slots[0].item.quantity == 3
    
    def test_remove_item_insufficient_quantity(self):
        inv = Inventory()
        potion = create_potion("Potion", "Heals", 1, Rarity.COMMON, 50, quantity=2)
        inv.add_item(potion)
        
        success = inv.remove_item(potion.id, quantity=5)
        assert success == False
    
    def test_equip_weapon(self):
        inv = Inventory()
        sword = make_sword()
        inv.add_item(sword)
        
        equipped = inv.equip_item(sword.id)
        assert equipped is not None
        assert equipped.name == "Longsword"
        assert inv.equipped_weapon == sword
        assert inv.slots[0].equipped == True
    
    def test_equip_armor(self):
        inv = Inventory()
        armor = make_leather_armor()
        inv.add_item(armor)
        
        equipped = inv.equip_item(armor.id)
        assert equipped is not None
        assert equipped.name == "Leather Armor"
        assert inv.equipped_armor == armor
    
    def test_equip_switches_weapon(self):
        inv = Inventory()
        sword1 = create_weapon("Sword", "1d8", "slashing", 2, Rarity.COMMON, 15, 3)
        sword2 = create_weapon("Axe", "1d12", "slashing", 1, Rarity.COMMON, 30, 7)
        
        inv.add_item(sword1)
        inv.add_item(sword2)
        
        inv.equip_item(sword1.id)
        assert inv.equipped_weapon == sword1
        
        # Equip second weapon - should unequip first
        inv.equip_item(sword2.id)
        assert inv.equipped_weapon == sword2
        assert inv.slots[0].equipped == False  # First sword
        assert inv.slots[1].equipped == True  # Second sword (axe)
    
    def test_equip_non_equippable_item(self):
        inv = Inventory()
        potion = make_healing_potion()
        inv.add_item(potion)
        
        equipped = inv.equip_item(potion.id)
        assert equipped is None
    
    def test_unequip_item(self):
        inv = Inventory()
        sword = make_sword()
        inv.add_item(sword)
        inv.equip_item(sword.id)
        
        success = inv.unequip_item(sword.id)
        assert success == True
        assert inv.equipped_weapon is None
        assert inv.slots[0].equipped == False
    
    def test_use_consumable(self):
        inv = Inventory()
        potion = make_healing_potion()
        inv.add_item(potion)
        
        success, message = inv.use_item(potion.id)
        assert success == True
        assert "Used Potion of Healing" in message
        # Item is removed when depleted
        assert len(inv.slots) == 0
    
    def test_use_depleted_item(self):
        inv = Inventory()
        potion = make_healing_potion()
        inv.add_item(potion)
        
        # Use once (depletes and removes it)
        inv.use_item(potion.id)
        
        # Try to use again - item no longer exists
        success, message = inv.use_item(potion.id)
        assert success == False
        assert "not found" in message.lower()
    
    def test_use_non_consumable(self):
        inv = Inventory()
        sword = make_sword()
        inv.add_item(sword)
        
        success, message = inv.use_item(sword.id)
        assert success == False
        assert "not consumable" in message.lower()
    
    def test_equipped_items_list(self):
        inv = Inventory()
        sword = make_sword()
        armor = make_leather_armor()
        inv.add_item(sword)
        inv.add_item(armor)
        
        inv.equip_item(sword.id)
        inv.equip_item(armor.id)
        
        equipped = inv.equipped_items
        assert len(equipped) == 2
        assert sword in equipped
        assert armor in equipped
    
    def test_serialization(self):
        inv = Inventory()
        inv.add_item(make_sword())
        inv.add_item(make_leather_armor())
        inv.equip_item(inv.slots[0].item.id)
        
        data = inv.to_dict()
        assert "slots" in data
        assert len(data["slots"]) == 2
        assert data["slots"][0]["equipped"] == True
        
        restored = Inventory.from_dict(data)
        assert len(restored.slots) == 2
        assert restored.total_weight == inv.total_weight
        assert restored.total_value == inv.total_value


# ---------------------------------------------------------------------------
# Starting Equipment
# ---------------------------------------------------------------------------

class TestStartingEquipment:
    def test_fighter_starting_inventory(self):
        inv = get_starting_inventory("fighter")
        
        assert len(inv.slots) >= 2  # At least weapon and armor
        assert inv.total_value > 0
        assert inv.equipped_weapon is not None
        assert inv.equipped_armor is not None
        
        # Fighter should have good armor
        assert inv.equipped_armor.armor_type in (ArmorType.HEAVY, ArmorType.MEDIUM)
    
    def test_wizard_starting_inventory(self):
        inv = get_starting_inventory("wizard")
        
        assert len(inv.slots) >= 1  # At least a weapon
        assert inv.equipped_weapon is not None
        # Wizard starts with light armor or no armor
        
        # Wizard should have a quarterstaff
        has_staff = any("staff" in s.item.name.lower() for s in inv.slots)
        assert has_staff
    
    def test_rogue_starting_inventory(self):
        inv = get_starting_inventory("rogue")
        
        assert len(inv.slots) >= 2
        assert inv.equipped_weapon is not None
        assert inv.equipped_armor is not None
        
        # Rogue should have light armor
        assert inv.equipped_armor.armor_type == ArmorType.LIGHT
    
    def test_unknown_class_fallback(self):
        inv = get_starting_inventory("unknown_class")
        
        assert len(inv.slots) >= 1
        # Should have at least a club
        has_club = any("club" in s.item.name.lower() for s in inv.slots)
        assert has_club
    
    def test_case_insensitive_class(self):
        inv1 = get_starting_inventory("FIGHTER")
        inv2 = get_starting_inventory("fighter")
        
        assert len(inv1.slots) == len(inv2.slots)


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestInventoryIntegration:
    def test_full_inventory_lifecycle(self):
        # Create inventory
        inv = Inventory()
        
        # Add items
        sword = make_sword()
        armor = make_leather_armor()
        potion = make_healing_potion()
        
        inv.add_item(sword)
        inv.add_item(armor)
        inv.add_item(potion)
        
        # Equip items
        inv.equip_item(sword.id)
        inv.equip_item(armor.id)
        
        assert len(inv.equipped_items) == 2
        
        # Use potion
        success, _ = inv.use_item(potion.id)
        assert success
        assert len(inv.slots) == 2  # Potion removed after depletion
        
        # Unequip weapon
        inv.unequip_item(sword.id)
        assert inv.equipped_weapon is None
        assert len(inv.equipped_items) == 1
        
        # Serialize and restore
        data = inv.to_dict()
        restored = Inventory.from_dict(data)
        
        assert len(restored.slots) == len(inv.slots)
        assert restored.total_value == inv.total_value
        assert restored.equipped_armor.name == armor.name