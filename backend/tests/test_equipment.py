"""
Tests for the equipment-driven combat engine.

Covers: weapon profile lookup (standard + enchantment + heuristic fallback),
magic-weapon enhancement, weapon→Attack conversion (ability/proficiency/magic
math, ranged/finesse/versatile handling), unarmed strikes, attack-list building
with extra attack, Armor Class derivation (armor + shield + unarmored defense),
and the full equipment combat-stats summary.
"""
import pytest

from app.engine.combat import Attack
from app.engine.inventory import (
    ArmorType,
    Inventory,
    ItemType,
    Rarity,
    create_armor,
    create_shield,
    create_weapon,
    get_starting_inventory,
)
from app.engine.equipment import (
    EquipmentCombatStats,
    WeaponProperties,
    WEAPON_PROFILES,
    attack_ability_modifier,
    build_attack_from_weapon,
    build_attacks_from_inventory,
    calculate_armor_class,
    calculate_armor_class_from_items,
    compute_equipment_combat_stats,
    get_weapon_profile,
    unarmed_strike_attack,
    weapon_magic_bonus,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def make_inventory(*items) -> Inventory:
    inv = Inventory()
    for item in items:
        inv.add_item(item)
    return inv


# --------------------------------------------------------------------------- #
# Weapon profile lookup
# --------------------------------------------------------------------------- #

class TestWeaponProfiles:
    def test_standard_melee_weapon(self):
        p = get_weapon_profile("Longsword")
        assert p.versatile is True
        assert p.versatile_die_sides == 10
        assert p.ranged is False
        assert p.finesse is False

    def test_ranged_weapon(self):
        p = get_weapon_profile("Longbow")
        assert p.ranged is True
        assert p.ammunition is True
        assert p.heavy is True
        assert p.two_handed is True

    def test_finesse_weapon(self):
        p = get_weapon_profile("Rapier")
        assert p.finesse is True

    def test_thrown_weapon(self):
        p = get_weapon_profile("Dagger")
        assert p.finesse is True
        assert p.light is True
        assert p.thrown is True

    def test_reach_weapon(self):
        p = get_weapon_profile("Glaive")
        assert p.reach is True
        assert p.heavy is True

    def test_case_insensitive(self):
        assert get_weapon_profile("longsword") == get_weapon_profile("LONGSWORD")

    def test_enchantment_prefix_stripped(self):
        assert get_weapon_profile("+1 Longsword") == WEAPON_PROFILES["longsword"]
        assert get_weapon_profile("+2 longsword") == WEAPON_PROFILES["longsword"]

    def test_enchantment_suffix_stripped(self):
        assert get_weapon_profile("Longsword +3") == WEAPON_PROFILES["longsword"]

    def test_of_suffix_stripped(self):
        assert get_weapon_profile("Longsword of Wounding") == WEAPON_PROFILES["longsword"]

    def test_unknown_weapon_heuristic_ranged(self):
        # Homebrew ranged weapon not in registry.
        p = get_weapon_profile("Elven Hand Crossbow")
        assert p.ranged is True

    def test_unknown_weapon_heuristic_finesse(self):
        p = get_weapon_profile("Twin Daggers of Doom")
        assert p.finesse is True

    def test_unknown_weapon_default_melee(self):
        p = get_weapon_profile("Spectral Cleaver")
        assert p.ranged is False
        assert p.finesse is False

    def test_empty_name(self):
        p = get_weapon_profile("")
        assert isinstance(p, WeaponProperties)
        assert p.ranged is False


# --------------------------------------------------------------------------- #
# Magic weapon bonus
# --------------------------------------------------------------------------- #

class TestMagicBonus:
    def test_mundane_common_weapon_no_bonus(self):
        sword = create_weapon("Longsword", "1d8", rarity=Rarity.COMMON, attack_bonus=2)
        # Legacy starting gear stores attack_bonus=2 but it's mundane → 0 magic.
        assert weapon_magic_bonus(sword) == 0

    def test_uncommon_weapon_bonus(self):
        sword = create_weapon("Longsword", "1d8", rarity=Rarity.UNCOMMON, attack_bonus=1)
        assert weapon_magic_bonus(sword) == 1

    def test_rare_weapon_bonus(self):
        sword = create_weapon("Longsword", "1d8", rarity=Rarity.RARE, attack_bonus=2)
        assert weapon_magic_bonus(sword) == 2

    def test_legendary_weapon_bonus(self):
        sword = create_weapon("Longsword", "1d8", rarity=Rarity.LEGENDARY, attack_bonus=3)
        assert weapon_magic_bonus(sword) == 3

    def test_magic_weapon_zero_attack_bonus(self):
        # A magic weapon that for some reason has attack_bonus=0 → 0.
        sword = create_weapon("Longsword", "1d8", rarity=Rarity.RARE, attack_bonus=0)
        assert weapon_magic_bonus(sword) == 0


# --------------------------------------------------------------------------- #
# Weapon → Attack
# --------------------------------------------------------------------------- #

class TestBuildAttackFromWeapon:
    def test_mundane_melee_longsword(self):
        sword = create_weapon("Longsword", "1d8", "slashing", rarity=Rarity.COMMON)
        # Str 16 (+3), proficiency 2.
        attack = build_attack_from_weapon(sword, str_mod=3, dex_mod=1, proficiency=2)
        assert attack.name == "Longsword"
        assert attack.attack_bonus == 3 + 2  # str + prof, no magic
        assert attack.damage_dice_count == 1
        assert attack.damage_dice_sides == 8
        assert attack.damage_bonus == 3  # str mod only
        assert attack.damage_type == "slashing"
        assert attack.ranged is False

    def test_magic_weapon_bonus_applies(self):
        sword = create_weapon("Longsword", "1d8", "slashing", attack_bonus=2, rarity=Rarity.RARE)
        # Str 16 (+3), prof 3.
        attack = build_attack_from_weapon(sword, str_mod=3, dex_mod=1, proficiency=3)
        assert attack.attack_bonus == 3 + 3 + 2  # str + prof + magic
        assert attack.damage_bonus == 3 + 2  # str + magic

    def test_ranged_weapon_uses_dex(self):
        bow = create_weapon("Longbow", "1d8", "piercing", rarity=Rarity.COMMON)
        # Dex 16 (+3), Str 8 (-1).
        attack = build_attack_from_weapon(bow, str_mod=-1, dex_mod=3, proficiency=2)
        assert attack.ranged is True
        assert attack.attack_bonus == 3 + 2  # dex + prof
        assert attack.damage_bonus == 3

    def test_finesse_uses_better_of_str_dex(self):
        rapier = create_weapon("Rapier", "1d8", "piercing", rarity=Rarity.COMMON)
        # Dex 16 (+3) > Str 14 (+2) → uses Dex.
        attack = build_attack_from_weapon(rapier, str_mod=2, dex_mod=3, proficiency=2)
        assert attack.attack_bonus == 3 + 2
        assert attack.damage_bonus == 3

    def test_finesse_uses_str_when_higher(self):
        rapier = create_weapon("Rapier", "1d8", "piercing", rarity=Rarity.COMMON)
        # Str 18 (+4) > Dex 12 (+1) → uses Str.
        attack = build_attack_from_weapon(rapier, str_mod=4, dex_mod=1, proficiency=2)
        assert attack.attack_bonus == 4 + 2
        assert attack.damage_bonus == 4

    def test_weapon_flat_damage_bonus_included(self):
        # A weapon with a baked-in flat damage bonus (e.g. Flametongue-style).
        sword = create_weapon("Longsword", "1d8", "slashing", rarity=Rarity.UNCOMMON, attack_bonus=1)
        sword.damage_bonus = 2  # extra flat damage
        attack = build_attack_from_weapon(sword, str_mod=3, dex_mod=1, proficiency=2)
        assert attack.damage_bonus == 3 + 2 + 1  # str + flat + magic

    def test_weapon_without_dice_degrades_to_unarmed(self):
        # A weapon whose dice were never set → 1d1 fallback.
        sword = create_weapon("Longsword", "1d8", rarity=Rarity.COMMON)
        sword.damage_dice_count = 0
        sword.damage_dice_sides = 0
        attack = build_attack_from_weapon(sword, str_mod=3, dex_mod=0, proficiency=2)
        assert attack.damage_dice_count == 1
        assert attack.damage_dice_sides == 1

    def test_custom_name_override(self):
        sword = create_weapon("Longsword", "1d8", rarity=Rarity.COMMON)
        attack = build_attack_from_weapon(sword, str_mod=3, dex_mod=0, proficiency=2, name="Slash")
        assert attack.name == "Slash"

    def test_returns_attack_type(self):
        sword = create_weapon("Longsword", "1d8", rarity=Rarity.COMMON)
        attack = build_attack_from_weapon(sword, str_mod=3, dex_mod=0, proficiency=2)
        assert isinstance(attack, Attack)


class TestAttackAbilityModifier:
    def test_melee_uses_str(self):
        assert attack_ability_modifier(4, 1, profile=get_weapon_profile("Longsword")) == 4

    def test_ranged_uses_dex(self):
        assert attack_ability_modifier(4, 3, profile=get_weapon_profile("Longbow")) == 3

    def test_finesse_uses_max(self):
        assert attack_ability_modifier(2, 5, profile=get_weapon_profile("Rapier")) == 5
        assert attack_ability_modifier(5, 2, profile=get_weapon_profile("Rapier")) == 5

    def test_defaults_when_no_weapon(self):
        # No weapon/profile → melee → Str.
        assert attack_ability_modifier(4, 1) == 4


# --------------------------------------------------------------------------- #
# Unarmed strike
# --------------------------------------------------------------------------- #

class TestUnarmedStrike:
    def test_standard_unarmed(self):
        attack = unarmed_strike_attack(str_mod=3, proficiency=2)
        assert attack.name == "Unarmed Strike"
        assert attack.attack_bonus == 3 + 2
        # 0d1 (always 0) + bonus of 1 + Str.
        assert attack.damage_dice_count == 0
        assert attack.damage_bonus == 1 + 3

    def test_unarmed_zero_str(self):
        attack = unarmed_strike_attack(str_mod=0, proficiency=2)
        assert attack.damage_bonus == 1

    def test_monk_die(self):
        attack = unarmed_strike_attack(str_mod=3, proficiency=2, monk_die_sides=6)
        assert attack.damage_dice_sides == 6
        assert attack.damage_dice_count == 1
        assert attack.damage_bonus == 3  # str mod (the die replaces the flat 1)


# --------------------------------------------------------------------------- #
# Attack list building
# --------------------------------------------------------------------------- #

class TestBuildAttacksFromInventory:
    def test_weapon_plus_unarmed(self):
        sword = create_weapon("Longsword", "1d8", "slashing", rarity=Rarity.COMMON)
        inv = make_inventory(sword)
        inv.equip_item(sword.id)
        attacks = build_attacks_from_inventory(inv, str_mod=3, dex_mod=1, proficiency=2)
        assert len(attacks) == 2
        assert attacks[0].name == "Longsword"
        assert attacks[1].name == "Unarmed Strike"

    def test_no_weapon_only_unarmed(self):
        inv = make_inventory()
        attacks = build_attacks_from_inventory(inv, str_mod=3, dex_mod=1, proficiency=2)
        assert len(attacks) == 1
        assert attacks[0].name == "Unarmed Strike"

    def test_extra_attack_duplicates_weapon(self):
        sword = create_weapon("Longsword", "1d8", "slashing", rarity=Rarity.COMMON)
        inv = make_inventory(sword)
        inv.equip_item(sword.id)
        attacks = build_attacks_from_inventory(
            inv, str_mod=3, dex_mod=1, proficiency=3, extra_attack=True
        )
        # Weapon, weapon (extra attack), unarmed.
        assert len(attacks) == 3
        assert attacks[0].name == "Longsword"
        assert "Extra Attack" in attacks[1].name
        assert attacks[1].attack_bonus == attacks[0].attack_bonus

    def test_monk_unarmed_die_scales(self):
        staff = create_weapon("Quarterstaff", "1d6", "bludgeoning", rarity=Rarity.COMMON)
        inv = make_inventory(staff)
        inv.equip_item(staff.id)
        # Level 11 monk → d8 martial arts die.
        attacks = build_attacks_from_inventory(
            inv, str_mod=3, dex_mod=3, proficiency=4, char_class="monk", level=11
        )
        unarmed = [a for a in attacks if a.name == "Unarmed Strike"][0]
        assert unarmed.damage_dice_sides == 8


# --------------------------------------------------------------------------- #
# Armor Class
# --------------------------------------------------------------------------- #

class TestCalculateArmorClass:
    def test_unarmored_commoner(self):
        inv = make_inventory()
        assert calculate_armor_class(inv, dex_mod=2) == 12  # 10 + dex

    def test_unarmored_barbarian_unarmored_defense(self):
        inv = make_inventory()
        # 10 + Dex(2) + Con(3) = 15
        assert calculate_armor_class(inv, dex_mod=2, char_class="barbarian", constitution=16) == 15

    def test_unarmored_monk_unarmored_defense(self):
        inv = make_inventory()
        # 10 + Dex(2) + Wis(3) = 15
        assert calculate_armor_class(inv, dex_mod=2, char_class="monk", wisdom=16) == 15

    def test_light_armor(self):
        leather = create_armor("Leather Armor", ArmorType.LIGHT, rarity=Rarity.COMMON)
        inv = make_inventory(leather)
        inv.equip_item(leather.id)
        # Base 11 + Dex(2) = 13
        assert calculate_armor_class(inv, dex_mod=2, char_class="fighter") == 13

    def test_medium_armor_dex_cap(self):
        scale = create_armor("Scale Mail", ArmorType.MEDIUM, dex_limit=2, rarity=Rarity.COMMON)
        inv = make_inventory(scale)
        inv.equip_item(scale.id)
        # Base 14 + min(Dex(3), 2) = 16
        assert calculate_armor_class(inv, dex_mod=3, char_class="fighter") == 16

    def test_heavy_armor_no_dex(self):
        chain = create_armor("Chain Mail", ArmorType.HEAVY, rarity=Rarity.COMMON)
        inv = make_inventory(chain)
        inv.equip_item(chain.id)
        # Base 16, no dex.
        assert calculate_armor_class(inv, dex_mod=3, char_class="fighter") == 16

    def test_shield_alone(self):
        shield = create_shield("Shield", armor_bonus=2)
        inv = make_inventory(shield)
        inv.equip_item(shield.id)
        # 10 + Dex(2) + shield(2) = 14
        assert calculate_armor_class(inv, dex_mod=2, char_class="fighter") == 14

    def test_armor_plus_shield(self):
        chain = create_armor("Chain Mail", ArmorType.HEAVY, rarity=Rarity.COMMON)
        shield = create_shield("Shield", armor_bonus=2)
        inv = make_inventory(chain, shield)
        inv.equip_item(chain.id)
        inv.equip_item(shield.id)
        # 16 (chain) + 2 (shield) = 18
        assert calculate_armor_class(inv, dex_mod=0, char_class="fighter") == 18

    def test_magic_shield_bonus(self):
        chain = create_armor("Chain Mail", ArmorType.HEAVY, rarity=Rarity.COMMON)
        # +1 shield → armor_bonus 3.
        shield = create_shield("Shield +1", armor_bonus=3)
        inv = make_inventory(chain, shield)
        inv.equip_item(chain.id)
        inv.equip_item(shield.id)
        # 16 + 3 = 19
        assert calculate_armor_class(inv, dex_mod=0, char_class="fighter") == 19

    def test_unarmored_defense_suppressed_when_armored(self):
        # A barbarian wearing armor does NOT add Con (Unarmored Defense is
        # unarmored-only).
        leather = create_armor("Leather Armor", ArmorType.LIGHT, rarity=Rarity.COMMON)
        inv = make_inventory(leather)
        inv.equip_item(leather.id)
        # 11 + Dex(2) = 13 (no Con bonus).
        assert calculate_armor_class(inv, dex_mod=2, char_class="barbarian", constitution=18) == 13


class TestCalculateArmorClassFromItems:
    def test_from_equipped_list(self):
        chain = create_armor("Chain Mail", ArmorType.HEAVY, rarity=Rarity.COMMON)
        shield = create_shield("Shield", armor_bonus=2)
        # Equipped items passed as a bare iterable.
        ac = calculate_armor_class_from_items([chain, shield], dex_mod=0, char_class="fighter")
        assert ac == 18

    def test_unarmored_list(self):
        ac = calculate_armor_class_from_items([], dex_mod=2, char_class="fighter")
        assert ac == 12


# --------------------------------------------------------------------------- #
# Shield equip slot separation (Inventory integration)
# --------------------------------------------------------------------------- #

class TestShieldEquipSlot:
    def test_armor_and_shield_coexist(self):
        chain = create_armor("Chain Mail", ArmorType.HEAVY, rarity=Rarity.COMMON)
        shield = create_shield("Shield", armor_bonus=2)
        inv = make_inventory(chain, shield)
        inv.equip_item(chain.id)
        inv.equip_item(shield.id)
        assert inv.equipped_body_armor is not None
        assert inv.equipped_body_armor.name == "Chain Mail"
        assert inv.equipped_shield is not None
        assert inv.equipped_shield.name == "Shield"
        assert len(inv.equipped_items) == 2

    def test_equipping_second_shield_swaps_first(self):
        s1 = create_shield("Wooden Shield", armor_bonus=2)
        s2 = create_shield("Iron Shield", armor_bonus=2)
        inv = make_inventory(s1, s2)
        inv.equip_item(s1.id)
        inv.equip_item(s2.id)
        assert inv.equipped_shield.name == "Iron Shield"
        # Body armor unaffected (none equipped).

    def test_equipping_body_armor_does_not_unequip_shield(self):
        chain = create_armor("Chain Mail", ArmorType.HEAVY, rarity=Rarity.COMMON)
        plate = create_armor("Plate Armor", ArmorType.HEAVY, rarity=Rarity.COMMON)
        shield = create_shield("Shield", armor_bonus=2)
        inv = make_inventory(chain, plate, shield)
        inv.equip_item(chain.id)
        inv.equip_item(shield.id)
        # Now swap body armor.
        inv.equip_item(plate.id)
        assert inv.equipped_body_armor.name == "Plate Armor"
        assert inv.equipped_shield is not None  # Shield still equipped

    def test_equipped_armor_excludes_shield(self):
        shield = create_shield("Shield", armor_bonus=2)
        inv = make_inventory(shield)
        inv.equip_item(shield.id)
        # equipped_armor (legacy) returns body armor only → None when only a
        # shield is equipped.
        assert inv.equipped_armor is None
        assert inv.equipped_shield is not None


# --------------------------------------------------------------------------- #
# Full equipment combat-stats summary
# --------------------------------------------------------------------------- #

class TestComputeEquipmentCombatStats:
    def test_fully_equipped_fighter(self):
        sword = create_weapon("Longsword", "1d8", "slashing", rarity=Rarity.COMMON)
        chain = create_armor("Chain Mail", ArmorType.HEAVY, rarity=Rarity.COMMON)
        shield = create_shield("Shield", armor_bonus=2)
        inv = make_inventory(sword, chain, shield)
        inv.equip_item(sword.id)
        inv.equip_item(chain.id)
        inv.equip_item(shield.id)

        stats = compute_equipment_combat_stats(
            inv,
            strength=16,  # +3
            dexterity=12,  # +1
            constitution=14,
            wisdom=10,
            proficiency=2,
            char_class="fighter",
            level=1,
        )
        assert isinstance(stats, EquipmentCombatStats)
        # AC: chain (16) + shield (2) = 18.
        assert stats.armor_class == 18
        # Weapon attack: str(3) + prof(2) = 5, damage bonus 3.
        assert stats.attacks[0].name == "Longsword"
        assert stats.attacks[0].attack_bonus == 5
        assert stats.attacks[0].damage_bonus == 3
        assert stats.weapon.name == "Longsword"
        assert stats.body_armor.name == "Chain Mail"
        assert stats.shield.name == "Shield"
        assert stats.weapon_magic_bonus == 0
        assert stats.weapon_properties.versatile is True

    def test_extra_attack_at_level_5(self):
        sword = create_weapon("Longsword", "1d8", "slashing", rarity=Rarity.COMMON)
        inv = make_inventory(sword)
        inv.equip_item(sword.id)
        stats = compute_equipment_combat_stats(
            inv, strength=16, dexterity=12, proficiency=3, char_class="fighter", level=5
        )
        # Longsword, Longsword (Extra Attack), Unarmed Strike.
        assert len(stats.attacks) == 3

    def test_no_extra_attack_low_level(self):
        sword = create_weapon("Longsword", "1d8", "slashing", rarity=Rarity.COMMON)
        inv = make_inventory(sword)
        inv.equip_item(sword.id)
        stats = compute_equipment_combat_stats(
            inv, strength=16, dexterity=12, proficiency=2, char_class="fighter", level=4
        )
        # Longsword + Unarmed Strike only.
        assert len(stats.attacks) == 2

    def test_magic_weapon_reflected(self):
        sword = create_weapon("Longsword", "1d8", "slashing", attack_bonus=2, rarity=Rarity.RARE)
        inv = make_inventory(sword)
        inv.equip_item(sword.id)
        stats = compute_equipment_combat_stats(
            inv, strength=16, dexterity=12, proficiency=3, char_class="fighter", level=5
        )
        assert stats.weapon_magic_bonus == 2
        assert stats.attacks[0].attack_bonus == 3 + 3 + 2  # str + prof + magic

    def test_unarmored_barbarian_ac(self):
        sword = create_weapon("Greataxe", "1d12", "slashing", rarity=Rarity.COMMON)
        inv = make_inventory(sword)
        inv.equip_item(sword.id)
        stats = compute_equipment_combat_stats(
            inv, strength=16, dexterity=14, constitution=16, wisdom=10,
            proficiency=2, char_class="barbarian", level=1,
        )
        # 10 + Dex(2) + Con(3) = 15.
        assert stats.armor_class == 15

    def test_to_dict_serializable(self):
        sword = create_weapon("Longsword", "1d8", "slashing", rarity=Rarity.COMMON)
        inv = make_inventory(sword)
        inv.equip_item(sword.id)
        stats = compute_equipment_combat_stats(
            inv, strength=16, dexterity=12, proficiency=2, char_class="fighter", level=1
        )
        d = stats.to_dict()
        assert "armor_class" in d
        assert "attacks" in d
        assert isinstance(d["attacks"], list)
        assert d["weapon"] == "Longsword"
        assert d["body_armor"] is None
        assert d["shield"] is None
        assert d["weapon_properties"]["versatile"] is True

    def test_starting_fighter_inventory_has_shield(self):
        """Fighter starting gear now includes an equipped shield → AC 18."""
        inv = get_starting_inventory("fighter")
        assert inv.equipped_shield is not None
        assert inv.equipped_body_armor is not None
        stats = compute_equipment_combat_stats(
            inv, strength=16, dexterity=12, constitution=14, wisdom=10,
            proficiency=2, char_class="fighter", level=1,
        )
        # Chain mail (16) + shield (2) = 18.
        assert stats.armor_class == 18
