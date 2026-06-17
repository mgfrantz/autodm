"""
Equipment-driven combat engine — derive Attacks and Armor Class from gear.

This module bridges the inventory :class:`~app.engine.inventory.Item` model and
the combat :class:`~app.engine.combat.Attack` / ``armor_class`` concepts so that
a character's *equipped* weapon, armor, and shield actually drive their combat
stats, instead of the legacy hardcoded per-class attack lists.

Three capabilities:

1. **Weapon → Attack.**  :func:`build_attack_from_weapon` converts an equipped
   weapon ``Item`` into a combat :class:`~app.engine.combat.Attack` whose
   attack bonus = ability mod + proficiency + magic enhancement, whose damage
   dice/type come from the weapon, and whose damage bonus = ability mod + magic.
   The ability used respects weapon properties (finesse → best of Str/Dex,
   ranged → Dex, otherwise Str).

2. **Magic weapon bonuses.**  A magic weapon (rarity uncommon or higher) grants
   its enhancement bonus to both attack and damage rolls (DnD 5e rule).  Mundane
   (common) weapons grant no such bonus — this also normalises legacy starting
   gear whose stored ``attack_bonus`` was a static approximation, so the ability
   and proficiency modifiers are never double-counted.

3. **Armor Class from equipped armor + shield.**  :func:`calculate_armor_class`
   computes AC from worn body armor (respecting light/medium/heavy Dex caps),
   plus an equipped shield, plus unarmored-defense features (barbarian Con,
   monk Wis) when no body armor is worn.

Weapon *properties* (finesse, ranged, two-handed, light, reach, thrown, heavy,
versatile, ammunition) come from the :data:`WEAPON_PROFILES` registry, which
covers every standard DnD 5e weapon.  Unknown / homebrew weapons fall back to a
sensible heuristic derived from the weapon name.

The engine is pure (no DB, no LLM) so it is trivially unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from app.engine.combat import Attack
from app.engine.dice import ability_modifier
from app.engine.inventory import ArmorType, Item, ItemType, Rarity


# --------------------------------------------------------------------------- #
# Weapon properties
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class WeaponProperties:
    """The mechanical properties of a weapon (a subset of DnD 5e PHB weapon
    properties that influence combat resolution).

    ``versatile_die_count``/``versatile_die_sides`` describe the larger damage
    die used when a versatile weapon is wielded two-handed.
    """

    ranged: bool = False
    finesse: bool = False
    light: bool = False
    two_handed: bool = False
    reach: bool = False
    thrown: bool = False
    heavy: bool = False
    versatile: bool = False
    versatile_die_count: int = 0
    versatile_die_sides: int = 0
    ammunition: bool = False


def _wp(**kwargs) -> WeaponProperties:
    return WeaponProperties(**kwargs)


# Registry of standard DnD 5e weapons → properties.  Keyed by lowercase name.
# Source: Player's Handbook, Weapons table.
WEAPON_PROFILES: dict[str, WeaponProperties] = {
    # --- Simple melee ---
    "club": _wp(light=True),
    "dagger": _wp(finesse=True, light=True, thrown=True),
    "greatclub": _wp(two_handed=True),
    "handaxe": _wp(light=True, thrown=True),
    "javelin": _wp(thrown=True),
    "light hammer": _wp(light=True, thrown=True),
    "mace": _wp(),
    "quarterstaff": _wp(versatile=True, versatile_die_count=1, versatile_die_sides=8),
    "sickle": _wp(light=True),
    "spear": _wp(thrown=True, versatile=True, versatile_die_count=1, versatile_die_sides=8),
    # --- Simple ranged ---
    "dart": _wp(finesse=True, thrown=True, ranged=True),
    "shortbow": _wp(ranged=True, ammunition=True, two_handed=True),
    "sling": _wp(ranged=True, ammunition=True),
    # --- Martial melee ---
    "battleaxe": _wp(versatile=True, versatile_die_count=1, versatile_die_sides=10),
    "flail": _wp(),
    "glaive": _wp(heavy=True, reach=True, two_handed=True),
    "greataxe": _wp(heavy=True, two_handed=True),
    "greatsword": _wp(heavy=True, two_handed=True),
    "halberd": _wp(heavy=True, reach=True, two_handed=True),
    "lance": _wp(reach=True),
    "longsword": _wp(versatile=True, versatile_die_count=1, versatile_die_sides=10),
    "maul": _wp(heavy=True, two_handed=True),
    "morningstar": _wp(),
    "pike": _wp(heavy=True, reach=True, two_handed=True),
    "rapier": _wp(finesse=True),
    "scimitar": _wp(finesse=True, light=True),
    "shortsword": _wp(finesse=True, light=True),
    "trident": _wp(thrown=True, versatile=True, versatile_die_count=1, versatile_die_sides=8),
    "war pick": _wp(),
    "warhammer": _wp(versatile=True, versatile_die_count=1, versatile_die_sides=10),
    "whip": _wp(finesse=True, reach=True),
    # --- Martial ranged ---
    "blowgun": _wp(ranged=True, ammunition=True),
    "hand crossbow": _wp(ranged=True, ammunition=True, light=True),
    "heavy crossbow": _wp(ranged=True, ammunition=True, heavy=True, two_handed=True),
    "light crossbow": _wp(ranged=True, ammunition=True, two_handed=True),
    "longbow": _wp(ranged=True, ammunition=True, heavy=True, two_handed=True),
    "crossbow": _wp(ranged=True, ammunition=True, two_handed=True),
    "bow": _wp(ranged=True, ammunition=True, heavy=True, two_handed=True),
}

# Name fragments that imply a ranged weapon.
_RANGED_HINTS = ("bow", "crossbow", "sling", "dart", "javelin", "blowgun", "net")
# Name fragments that imply a finesse weapon.
_FINESSE_HINTS = ("dagger", "shortsword", "rapier", "scimitar", "whip", "dart")
# Name fragments that imply a light weapon.
_LIGHT_HINTS = ("dagger", "shortsword", "scimitar", "handaxe", "light hammer", "club", "sickle", "dart")


def _normalize_weapon_name(name: str) -> str:
    """Strip enchantment prefixes/suffixes for registry lookup.

    Handles ``"+1 longsword"``, ``"longsword +2"``, ``"flaming longsword"``,
    ``"longsword of wounding"`` so the underlying weapon type resolves.
    """
    s = (name or "").lower().strip()
    # Drop leading "+N" / "-N" enchantment.
    if s and s[0] in "+-":
        parts = s.split(maxsplit=1)
        if len(parts) == 2 and parts[1]:
            s = parts[1]
    # Drop trailing "+N" / "-N" enchantment.
    for sep in (" +", " -"):
        if sep in s:
            head, _, tail = s.partition(sep)
            if tail.strip().lstrip("+-").isdigit():
                s = head.strip()
    # Drop "of <something>" suffixes.
    if " of " in s:
        s = s.split(" of ", 1)[0].strip()
    return s


def get_weapon_profile(name: str) -> WeaponProperties:
    """Look up weapon properties by name.

    Standard weapons resolve against :data:`WEAPON_PROFILES` (after normalising
    enchantment prefixes/suffixes).  Unknown / homebrew weapons fall back to a
    heuristic derived from the name, so they still get sensible ``ranged`` /
    ``finesse`` / ``light`` flags.
    """
    key = _normalize_weapon_name(name)
    if key in WEAPON_PROFILES:
        return WEAPON_PROFILES[key]

    # Heuristic fallback for custom/homebrew weapons.
    ranged = any(h in key for h in _RANGED_HINTS)
    finesse = any(h in key for h in _FINESSE_HINTS)
    light = any(h in key for h in _LIGHT_HINTS)
    two_handed = "great" in key or "two-handed" in key
    reach = "halberd" in key or "glaive" in key or "pike" in key or "lance" in key or "whip" in key
    return WeaponProperties(
        ranged=ranged,
        finesse=finesse,
        light=light,
        two_handed=two_handed,
        reach=reach,
    )


# --------------------------------------------------------------------------- #
# Magic weapon bonuses
# --------------------------------------------------------------------------- #

_RARITY_ORDER = ["common", "uncommon", "rare", "very_rare", "legendary"]


def _is_magical(weapon: Item) -> bool:
    """True if the weapon is magical (uncommon rarity or higher)."""
    rarity = getattr(weapon, "rarity", None)
    value = getattr(rarity, "value", rarity)
    if not isinstance(value, str):
        return False
    try:
        return _RARITY_ORDER.index(value) >= 1
    except ValueError:
        return False


def weapon_magic_bonus(weapon: Item) -> int:
    """Enhancement bonus (+1/+2/+3) granted by a magic weapon.

    Mundane (common) weapons grant **no** bonus even when their stored
    ``attack_bonus`` field is non-zero — the field historically held a static
    approximation that the equipment engine now replaces with the real
    ability + proficiency math.  Magic weapons (uncommon+) honour their stored
    ``attack_bonus`` as the enhancement value, which applies to both attack and
    damage rolls per DnD 5e rules.
    """
    if not _is_magical(weapon):
        return 0
    return max(0, int(getattr(weapon, "attack_bonus", 0) or 0))


# --------------------------------------------------------------------------- #
# Weapon → Attack
# --------------------------------------------------------------------------- #

def attack_ability_modifier(
    str_mod: int,
    dex_mod: int,
    weapon: Optional[Item] = None,
    profile: Optional[WeaponProperties] = None,
) -> int:
    """The ability modifier that applies to attack/damage rolls with *weapon*.

    Finesse weapons may use Strength *or* Dexterity (the better one); ranged
    weapons use Dexterity; all other weapons use Strength.
    """
    profile = profile if profile is not None else (
        get_weapon_profile(weapon.name) if weapon is not None else WeaponProperties()
    )
    if profile.ranged:
        return dex_mod
    if profile.finesse:
        return max(str_mod, dex_mod)
    return str_mod


def build_attack_from_weapon(
    weapon: Item,
    *,
    str_mod: int = 0,
    dex_mod: int = 0,
    proficiency: int = 0,
    name: Optional[str] = None,
) -> Attack:
    """Construct a combat :class:`~app.engine.combat.Attack` from an equipped
    weapon.

    Parameters mirror DnD 5e to-hit/damage math:

    - ``attack_bonus`` = ability mod (weapon-dependent) + proficiency + magic
    - ``damage_dice_count``/``damage_dice_sides``/``damage_type`` from the weapon
    - ``damage_bonus`` = ability mod + weapon's flat damage bonus + magic
    - ``ranged`` flag derived from the weapon's properties

    Weapons with no damage dice (e.g. a net, or a weapon whose dice were not
    set) fall back to an unarmed-style ``1`` bludgeoning strike so combat can
    still proceed.
    """
    profile = get_weapon_profile(weapon.name)
    ability = attack_ability_modifier(str_mod, dex_mod, weapon=weapon, profile=profile)
    magic = weapon_magic_bonus(weapon)

    dice_count = int(getattr(weapon, "damage_dice_count", 0) or 0)
    dice_sides = int(getattr(weapon, "damage_dice_sides", 0) or 0)
    if dice_count <= 0 or dice_sides <= 0:
        # No weapon dice configured — degrade to an unarmed strike.
        dice_count, dice_sides = 1, 1

    return Attack(
        name=name or weapon.name,
        attack_bonus=ability + proficiency + magic,
        damage_dice_count=dice_count,
        damage_dice_sides=dice_sides,
        damage_bonus=ability + int(getattr(weapon, "damage_bonus", 0) or 0) + magic,
        damage_type=getattr(weapon, "damage_type", "") or "bludgeoning",
        ranged=bool(profile.ranged),
    )


# Standard unarmed strike damage (1 + Str per PHB).
def unarmed_strike_attack(*, str_mod: int = 0, proficiency: int = 0, monk_die_sides: int = 0) -> Attack:
    """An unarmed-strike :class:`~app.engine.combat.Attack`.

    Monks may use a martial-arts die in place of the normal 1 bludgeoning
    damage; pass ``monk_die_sides`` (e.g. 4 at levels 1-4) to model this.
    Otherwise the damage is the flat PHB value of ``1 + Str``.
    """
    if monk_die_sides and monk_die_sides > 1:
        return Attack(
            name="Unarmed Strike",
            attack_bonus=str_mod + proficiency,
            damage_dice_count=1,
            damage_dice_sides=monk_die_sides,
            damage_bonus=str_mod,
            damage_type="bludgeoning",
        )
    return Attack(
        name="Unarmed Strike",
        attack_bonus=str_mod + proficiency,
        damage_dice_count=0,
        damage_dice_sides=1,
        # Flat 1 damage + Str, represented via a 0d1 (always 0) + bonus.
        damage_bonus=1 + str_mod,
        damage_type="bludgeoning",
    )


def build_attacks_from_inventory(
    inventory,
    *,
    str_mod: int = 0,
    dex_mod: int = 0,
    proficiency: int = 0,
    char_class: str = "",
    level: int = 1,
    extra_attack: bool = False,
) -> list[Attack]:
    """Build a character's full attack list from equipped gear.

    The primary attack comes from the equipped weapon (if any); an unarmed
    strike is always appended as a backup.  When ``extra_attack`` is True (e.g.
    a Fighter/Paladin/Ranger/Monk at level 5+), the weapon attack is duplicated
    so the character may strike twice with the Attack action.

    If no weapon is equipped, only the unarmed strike is returned.
    """
    attacks: list[Attack] = []
    weapon = getattr(inventory, "equipped_weapon", None)
    if weapon is not None:
        primary = build_attack_from_weapon(
            weapon, str_mod=str_mod, dex_mod=dex_mod, proficiency=proficiency
        )
        attacks.append(primary)
        if extra_attack:
            attacks.append(Attack(
                name=f"{primary.name} (Extra Attack)",
                attack_bonus=primary.attack_bonus,
                damage_dice_count=primary.damage_dice_count,
                damage_dice_sides=primary.damage_dice_sides,
                damage_bonus=primary.damage_bonus,
                damage_type=primary.damage_type,
                ranged=primary.ranged,
            ))

    # Monks deal martial-arts die damage with unarmed strikes.
    monk = (char_class or "").lower() == "monk"
    monk_die = 0
    if monk:
        monk_die = 4 if level < 5 else (6 if level < 11 else (8 if level < 17 else 10))
    attacks.append(unarmed_strike_attack(str_mod=str_mod, proficiency=proficiency, monk_die_sides=monk_die))
    return attacks


# --------------------------------------------------------------------------- #
# Armor Class from equipped armor + shield
# --------------------------------------------------------------------------- #

_UNARMORED_DEFENSE = {
    "barbarian": "constitution",
    "monk": "wisdom",
}


def _body_armor(inventory) -> Optional[Item]:
    """The equipped worn-body armor (armor that is not a shield)."""
    for slot in getattr(inventory, "slots", []):
        if slot.equipped and slot.item.item_type == ItemType.ARMOR:
            if slot.item.armor_type != ArmorType.SHIELD:
                return slot.item
    return None


def _shield(inventory) -> Optional[Item]:
    """The equipped shield, if any."""
    for slot in getattr(inventory, "slots", []):
        if slot.equipped and slot.item.item_type == ItemType.ARMOR:
            if slot.item.armor_type == ArmorType.SHIELD:
                return slot.item
    return None


def _ac_from_armor(armor: Item, dex_mod: int) -> int:
    """AC contributed by a single worn-armor item (body armor only)."""
    return armor.get_ac_bonus(dex_mod)


def calculate_armor_class(
    inventory,
    *,
    dex_mod: int,
    char_class: str = "commoner",
    constitution: int = 10,
    wisdom: int = 10,
) -> int:
    """Compute Armor Class from a character's equipped armor and shield.

    Rules:

    - **Body armor worn:** ``armor base + Dex (capped by armor type) + magic``
      via :meth:`Item.get_ac_bonus`, plus a shield bonus if one is equipped.
    - **No body armor:** base ``10 + Dex``; barbarian/monk *Unarmored Defense*
      adds the Con/Wis modifier respectively.
    - A shield always adds its bonus on top (a shield can be used unarmored too).

    ``constitution``/``wisdom`` are ability *scores* (the same convention used
    elsewhere in the codebase); they are converted to modifiers internally.
    """
    body = _body_armor(inventory)
    shield = _shield(inventory)

    if body is not None:
        ac = _ac_from_armor(body, dex_mod)
    else:
        ac = 10 + dex_mod
        # Unarmored Defense (barbarian / monk) — only meaningful when unarmored.
        cls = (char_class or "").lower()
        secondary = _UNARMORED_DEFENSE.get(cls)
        if secondary == "constitution":
            ac += ability_modifier(constitution)
        elif secondary == "wisdom":
            ac += ability_modifier(wisdom)

    if shield is not None:
        ac += shield.get_ac_bonus(dex_mod)  # shield AC is additive (+2 + magic)

    return ac


def calculate_armor_class_from_items(
    equipped_items: Iterable[Item],
    *,
    dex_mod: int,
    char_class: str = "commoner",
    constitution: int = 10,
    wisdom: int = 10,
) -> int:
    """Compute AC from an iterable of equipped :class:`Item` objects.

    Convenience variant of :func:`calculate_armor_class` for callers that have
    a bare list of equipped items rather than a full :class:`Inventory`.
    """
    body = None
    shield = None
    for item in equipped_items:
        if item.item_type != ItemType.ARMOR:
            continue
        if item.armor_type == ArmorType.SHIELD:
            shield = item
        else:
            body = item

    if body is not None:
        ac = body.get_ac_bonus(dex_mod)
    else:
        ac = 10 + dex_mod
        cls = (char_class or "").lower()
        secondary = _UNARMORED_DEFENSE.get(cls)
        if secondary == "constitution":
            ac += ability_modifier(constitution)
        elif secondary == "wisdom":
            ac += ability_modifier(wisdom)

    if shield is not None:
        ac += shield.get_ac_bonus(dex_mod)

    return ac


# --------------------------------------------------------------------------- #
# Combat-stats summary (used by the API + tests)
# --------------------------------------------------------------------------- #

@dataclass
class EquipmentCombatStats:
    """A snapshot of the combat stats derived from a character's gear."""

    armor_class: int
    attacks: list[Attack]
    weapon: Optional[Item]
    body_armor: Optional[Item]
    shield: Optional[Item]
    weapon_properties: Optional[WeaponProperties]
    weapon_magic_bonus: int

    def to_dict(self) -> dict:
        return {
            "armor_class": self.armor_class,
            "attacks": [
                {
                    "name": a.name,
                    "attack_bonus": a.attack_bonus,
                    "damage_dice_count": a.damage_dice_count,
                    "damage_dice_sides": a.damage_dice_sides,
                    "damage_bonus": a.damage_bonus,
                    "damage_type": a.damage_type,
                    "ranged": a.ranged,
                }
                for a in self.attacks
            ],
            "weapon": self.weapon.name if self.weapon else None,
            "body_armor": self.body_armor.name if self.body_armor else None,
            "shield": self.shield.name if self.shield else None,
            "weapon_properties": (
                {
                    "ranged": self.weapon_properties.ranged,
                    "finesse": self.weapon_properties.finesse,
                    "light": self.weapon_properties.light,
                    "two_handed": self.weapon_properties.two_handed,
                    "reach": self.weapon_properties.reach,
                    "thrown": self.weapon_properties.thrown,
                    "heavy": self.weapon_properties.heavy,
                    "versatile": self.weapon_properties.versatile,
                    "ammunition": self.weapon_properties.ammunition,
                }
                if self.weapon_properties
                else None
            ),
            "weapon_magic_bonus": self.weapon_magic_bonus,
        }


def compute_equipment_combat_stats(
    inventory,
    *,
    strength: int = 10,
    dexterity: int = 10,
    constitution: int = 10,
    wisdom: int = 10,
    proficiency: int = 2,
    char_class: str = "commoner",
    level: int = 1,
) -> EquipmentCombatStats:
    """Compute the full combat-stat snapshot derived from a character's gear.

    Combines AC (:func:`calculate_armor_class`) and attacks
    (:func:`build_attacks_from_inventory`) into one summary used by the combat
    API when starting an encounter, and by the equipment-stats endpoint.
    """
    str_mod = ability_modifier(strength)
    dex_mod = ability_modifier(dexterity)

    weapon = getattr(inventory, "equipped_weapon", None)
    body = _body_armor(inventory)
    shield = _shield(inventory)

    extra_attack = False
    cls = (char_class or "").lower()
    if cls in {"fighter", "paladin", "ranger"} and level >= 5:
        extra_attack = True
    elif cls in {"barbarian", "bard", "druid", "monk"} and level >= 6:
        extra_attack = True
    elif cls in {"rogue", "cleric", "wizard", "sorcerer", "warlock"} and level >= 8:
        extra_attack = True

    attacks = build_attacks_from_inventory(
        inventory,
        str_mod=str_mod,
        dex_mod=dex_mod,
        proficiency=proficiency,
        char_class=char_class,
        level=level,
        extra_attack=extra_attack,
    )

    ac = calculate_armor_class(
        inventory,
        dex_mod=dex_mod,
        char_class=char_class,
        constitution=constitution,
        wisdom=wisdom,
    )

    return EquipmentCombatStats(
        armor_class=ac,
        attacks=attacks,
        weapon=weapon,
        body_armor=body,
        shield=shield,
        weapon_properties=get_weapon_profile(weapon.name) if weapon else None,
        weapon_magic_bonus=weapon_magic_bonus(weapon) if weapon else 0,
    )
