"""
Spell engine — spells, spell slots, and per-class casting.

Implements a simplified-but-faithful DnD 5e magic system:
- Spells (level 0 cantrips through level 9) grouped into eight schools.
- Spell slots: full / half / third caster progression by character level.
- Casting styles: "known" (sorcerer/bard/warlock/ranger cast what they know)
  vs "prepared" (wizard/cleric/druid/paladin prepare a daily subset).
- Casting ability per class (INT / WIS / CHA) feeding spell attack bonus and DC.
- Cantrip scaling (extra dice at levels 5/11/17) and upcasting (extra dice per
  slot level above the spell's base level).
- Effect resolution: attack-roll spells (d20 + spell attack vs AC), saving-throw
  spells (half damage on a successful save), healing spells, and utility spells.

The engine is pure (no DB, no LLM) so it is trivially unit-testable. Game state
code can serialize a Spellbook via ``Spellbook.to_dict`` and rebuild it with
``Spellbook.from_dict`` for persistence.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.engine.dice import roll_d20, roll_dice, proficiency_bonus, ability_modifier


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class SpellLevel(int, Enum):
    """Spell levels. Cantrip is treated as level 0."""
    CANTRIP = 0
    ONE = 1
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9


class SpellSchool(str, Enum):
    ABJURATION = "abjuration"
    CONJURATION = "conjuration"
    DIVINATION = "divination"
    ENCHANTMENT = "enchantment"
    EVOCATION = "evocation"
    ILLUSION = "illusion"
    NECROMANCY = "necromancy"
    TRANSMUTATION = "transmutation"


class CasterType(str, Enum):
    """How quickly a class earns spell slots."""
    FULL = "full"      # wizard, sorcerer, cleric, druid, bard, warlock
    HALF = "half"      # paladin, ranger
    THIRD = "third"    # eldritch knight, arcane trickster
    NONE = "none"      # non-casters


class CastingStyle(str, Enum):
    """Whether a caster chooses from known or prepared spells."""
    KNOWN = "known"
    PREPARED = "prepared"
    NONE = "none"


# ---------------------------------------------------------------------------
# Caster profiles: which classes cast, how, and with which ability.
# ---------------------------------------------------------------------------

CASTER_PROFILES = {
    # class (lowercase): (caster_type, casting_style, casting_ability)
    "wizard":   (CasterType.FULL,  CastingStyle.PREPARED, "int"),
    "sorcerer": (CasterType.FULL,  CastingStyle.KNOWN,    "cha"),
    "cleric":   (CasterType.FULL,  CastingStyle.PREPARED, "wis"),
    "druid":    (CasterType.FULL,  CastingStyle.PREPARED, "wis"),
    "bard":     (CasterType.FULL,  CastingStyle.KNOWN,    "cha"),
    "warlock":  (CasterType.FULL,  CastingStyle.KNOWN,    "cha"),
    "paladin":  (CasterType.HALF,  CastingStyle.PREPARED, "cha"),
    "ranger":   (CasterType.HALF,  CastingStyle.KNOWN,    "wis"),
    # Fighter (Eldritch Knight) and Rogue (Arcane Trickster) are third casters.
    # Base fighter/rogue are treated as non-casters; subclasses can opt in.
    "fighter":  (CasterType.NONE,  CastingStyle.NONE,     "int"),
    "rogue":    (CasterType.NONE,  CastingStyle.NONE,     "int"),
    "monk":     (CasterType.NONE,  CastingStyle.NONE,     "wis"),
    "barbarian":(CasterType.NONE,  CastingStyle.NONE,     "con"),
}


# ---------------------------------------------------------------------------
# Spell-slot progression (full caster table, slots per spell level 1-9).
# Half casters use ceil(level/2); third casters use ceil(level/3).
# ---------------------------------------------------------------------------

# Slots for levels 1-9 indexed by character level (1..20).
_FULL_CASTER_SLOTS = {
    1:  [2, 0, 0, 0, 0, 0, 0, 0, 0],
    2:  [3, 0, 0, 0, 0, 0, 0, 0, 0],
    3:  [4, 2, 0, 0, 0, 0, 0, 0, 0],
    4:  [4, 3, 0, 0, 0, 0, 0, 0, 0],
    5:  [4, 3, 2, 0, 0, 0, 0, 0, 0],
    6:  [4, 3, 3, 0, 0, 0, 0, 0, 0],
    7:  [4, 3, 3, 1, 0, 0, 0, 0, 0],
    8:  [4, 3, 3, 2, 0, 0, 0, 0, 0],
    9:  [4, 3, 3, 3, 1, 0, 0, 0, 0],
    10: [4, 3, 3, 3, 2, 0, 0, 0, 0],
    11: [4, 3, 3, 3, 2, 1, 0, 0, 0],
    12: [4, 3, 3, 3, 2, 1, 0, 0, 0],
    13: [4, 3, 3, 3, 2, 1, 1, 0, 0],
    14: [4, 3, 3, 3, 2, 1, 1, 0, 0],
    15: [4, 3, 3, 3, 2, 1, 1, 1, 0],
    16: [4, 3, 3, 3, 2, 1, 1, 1, 0],
    17: [4, 3, 3, 3, 2, 1, 1, 1, 1],
    18: [4, 3, 3, 3, 3, 1, 1, 1, 1],
    19: [4, 3, 3, 3, 3, 2, 2, 1, 1],
    20: [4, 3, 3, 3, 3, 2, 2, 2, 1],
}


def effective_caster_level(char_level: int, caster_type: CasterType) -> int:
    """Convert character level into full-caster-equivalent level.

    Half casters progress at half rate (rounded up), third casters at one third.
    Non-casters never earn slots. Levels below the table clamp to 1; above clamp
    to 20.
    """
    char_level = max(1, min(20, char_level))
    if caster_type == CasterType.FULL:
        eff = char_level
    elif caster_type == CasterType.HALF:
        # Half casters don't get slots until level 2, but the table already
        # returns [2,0,...] at effective level 1, which is fine.
        eff = math.ceil(char_level / 2)
    elif caster_type == CasterType.THIRD:
        eff = math.ceil(char_level / 3)
    else:
        eff = 0
    return max(1, eff) if eff else 0


def slots_for_level(char_level: int, caster_type: CasterType) -> list[int]:
    """Return the max spell slots (levels 1-9) for a given caster."""
    eff = effective_caster_level(char_level, caster_type)
    if caster_type == CasterType.NONE or eff == 0:
        return [0] * 9
    eff = max(1, min(20, eff))
    return list(_FULL_CASTER_SLOTS[eff])


# ---------------------------------------------------------------------------
# Cantrip scaling: cantrip damage dice multiply at caster levels 5/11/17.
# ---------------------------------------------------------------------------

def cantrip_dice_multiplier(caster_level: int) -> int:
    """How many times to roll a cantrip's base damage dice (1-4)."""
    if caster_level >= 17:
        return 4
    if caster_level >= 11:
        return 3
    if caster_level >= 5:
        return 2
    return 1


# ---------------------------------------------------------------------------
# Spell definition
# ---------------------------------------------------------------------------

@dataclass
class Spell:
    """A single DnD spell and its mechanical effects."""

    name: str
    level: int  # 0 = cantrip, 1-9 = spell level
    school: SpellSchool
    description: str = ""
    casting_time: str = "1 action"
    range: str = "self"
    components: str = "V, S"
    duration: str = "instantaneous"
    concentration: bool = False
    ritual: bool = False

    # Mechanics ------------------------------------------------------------
    requires_attack_roll: bool = False       # ranged/melee spell attack vs AC
    save_ability: Optional[str] = None       # e.g. "dex" -> target rolls save
    damage_dice_count: int = 0
    damage_dice_sides: int = 0
    damage_bonus: int = 0
    damage_type: str = ""
    healing_dice_count: int = 0
    healing_dice_sides: int = 0
    healing_bonus: int = 0
    # Extra dice added per slot level above the spell's base level (upcasting).
    at_higher_levels_dice: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.school, str):
            object.__setattr__(self, "school", SpellSchool(self.school))

    @property
    def id(self) -> str:
        """Stable identifier derived from the spell name."""
        return self.name.lower().replace(" ", "_")

    @property
    def is_cantrip(self) -> bool:
        return self.level == 0

    @property
    def deals_damage(self) -> bool:
        return self.damage_dice_count > 0 and self.damage_dice_sides > 0

    @property
    def heals(self) -> bool:
        return self.healing_dice_count > 0 and self.healing_dice_sides > 0

    def roll_damage(self, caster_level: int, slot_level: Optional[int] = None) -> int:
        """Roll the spell's damage, applying cantrip scaling and upcasting.

        For cantrips, ``slot_level`` is ignored and dice scale with caster level.
        For leveled spells, upcasting adds ``at_higher_levels_dice`` dice per
        slot level above the spell's base level.
        """
        if not self.deals_damage:
            return 0

        if self.is_cantrip:
            mult = cantrip_dice_multiplier(caster_level)
            count = self.damage_dice_count * mult
            result = roll_dice(count, self.damage_dice_sides, self.damage_bonus)
            return result.total

        slot_level = slot_level if slot_level is not None else self.level
        extra_levels = max(0, slot_level - self.level)
        count = self.damage_dice_count + self.at_higher_levels_dice * extra_levels
        result = roll_dice(count, self.damage_dice_sides, self.damage_bonus)
        return result.total

    def roll_healing(self, caster_level: int, slot_level: Optional[int] = None) -> int:
        """Roll the spell's healing, applying upcasting for leveled spells."""
        if not self.heals:
            return 0

        slot_level = slot_level if slot_level is not None else self.level
        extra_levels = max(0, slot_level - self.level)
        count = self.healing_dice_count + self.at_higher_levels_dice * extra_levels
        result = roll_dice(count, self.healing_dice_sides, self.healing_bonus)
        return result.total

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level,
            "school": self.school.value,
            "description": self.description,
            "casting_time": self.casting_time,
            "range": self.range,
            "components": self.components,
            "duration": self.duration,
            "concentration": self.concentration,
            "ritual": self.ritual,
            "requires_attack_roll": self.requires_attack_roll,
            "save_ability": self.save_ability,
            "damage_dice_count": self.damage_dice_count,
            "damage_dice_sides": self.damage_dice_sides,
            "damage_bonus": self.damage_bonus,
            "damage_type": self.damage_type,
            "healing_dice_count": self.healing_dice_count,
            "healing_dice_sides": self.healing_dice_sides,
            "healing_bonus": self.healing_bonus,
            "at_higher_levels_dice": self.at_higher_levels_dice,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Spell":
        return cls(
            name=data["name"],
            level=data["level"],
            school=SpellSchool(data.get("school", "evocation")),
            description=data.get("description", ""),
            casting_time=data.get("casting_time", "1 action"),
            range=data.get("range", "self"),
            components=data.get("components", "V, S"),
            duration=data.get("duration", "instantaneous"),
            concentration=data.get("concentration", False),
            ritual=data.get("ritual", False),
            requires_attack_roll=data.get("requires_attack_roll", False),
            save_ability=data.get("save_ability"),
            damage_dice_count=data.get("damage_dice_count", 0),
            damage_dice_sides=data.get("damage_dice_sides", 0),
            damage_bonus=data.get("damage_bonus", 0),
            damage_type=data.get("damage_type", ""),
            healing_dice_count=data.get("healing_dice_count", 0),
            healing_dice_sides=data.get("healing_dice_sides", 0),
            healing_bonus=data.get("healing_bonus", 0),
            at_higher_levels_dice=data.get("at_higher_levels_dice", 0),
        )


# ---------------------------------------------------------------------------
# Spell registry — canonical DnD spells keyed by id.
# ---------------------------------------------------------------------------

SPELL_REGISTRY: dict[str, Spell] = {}


def register_spell(spell: Spell) -> Spell:
    """Add a spell to the global registry, keyed by its id."""
    SPELL_REGISTRY[spell.id] = spell
    return spell


def get_spell(spell_id: str) -> Optional[Spell]:
    """Look up a spell by id (e.g. 'fire_bolt') or name (e.g. 'Fire Bolt')."""
    key = spell_id.lower().replace(" ", "_")
    return SPELL_REGISTRY.get(key)


# --- Cantrips --------------------------------------------------------------
register_spell(Spell("Fire Bolt", 0, SpellSchool.EVOCATION,
    description="A hurl a mote of fire at a creature or object.",
    casting_time="1 action", range="120 feet", components="V, S",
    requires_attack_roll=True, damage_dice_count=1, damage_dice_sides=10,
    damage_type="fire"))
register_spell(Spell("Ray of Frost", 0, SpellSchool.EVOCATION,
    description="A frigid beam of blue-white light. Target's speed drops 10 ft.",
    casting_time="1 action", range="60 feet", components="V, S",
    requires_attack_roll=True, damage_dice_count=1, damage_dice_sides=8,
    damage_type="cold"))
register_spell(Spell("Sacred Flame", 0, SpellSchool.EVOCATION,
    description="Flame-like radiance descends on a target. No attack roll; Dex save.",
    casting_time="1 action", range="60 feet", components="V, S",
    save_ability="dex", damage_dice_count=1, damage_dice_sides=8,
    damage_type="radiant"))
register_spell(Spell("Eldritch Blast", 0, SpellSchool.EVOCATION,
    description="A beam of crackling energy streaks toward a creature.",
    casting_time="1 action", range="120 feet", components="V, S",
    requires_attack_roll=True, damage_dice_count=1, damage_dice_sides=10,
    damage_type="force"))
register_spell(Spell("Vicious Mockery", 0, SpellSchool.ENCHANTMENT,
    description="You unleash a string of insults. Wis save or damage + disadvantage.",
    casting_time="1 action", range="60 feet", components="V",
    save_ability="wis", damage_dice_count=1, damage_dice_sides=4,
    damage_type="psychic"))
register_spell(Spell("Acid Splash", 0, SpellSchool.CONJURATION,
    description="A splash of acid. Dex save.",
    casting_time="1 action", range="60 feet", components="V, S",
    save_ability="dex", damage_dice_count=1, damage_dice_sides=6,
    damage_type="acid"))
register_spell(Spell("Light", 0, SpellSchool.EVOCATION,
    description="An object glows with bright light.",
    casting_time="1 action", range="touch", components="V, M"))
register_spell(Spell("Mage Hand", 0, SpellSchool.CONJURATION,
    description="A spectral floating hand appears.",
    casting_time="1 action", range="30 feet", components="V, S"))
register_spell(Spell("Minor Illusion", 0, SpellSchool.ILLUSION,
    description="You create a sound or an image of an object.",
    casting_time="1 action", range="30 feet", components="S, M"))

# --- Level 1 ---------------------------------------------------------------
register_spell(Spell("Magic Missile", 1, SpellSchool.EVOCATION,
    description="Three darts of force hit their targets. Always hits; no save.",
    casting_time="1 action", range="120 feet", components="V, S",
    damage_dice_count=3, damage_dice_sides=4, damage_bonus=1,
    damage_type="force", at_higher_levels_dice=1))
register_spell(Spell("Burning Hands", 1, SpellSchool.EVOCATION,
    description="A cone of fire erupts. Dex save for half.",
    casting_time="1 action", range="self (15-foot cone)", components="V, S",
    save_ability="dex", damage_dice_count=3, damage_dice_sides=6,
    damage_type="fire", at_higher_levels_dice=1))
register_spell(Spell("Thunderwave", 1, SpellSchool.EVOCATION,
    description="A wave of thunderous force. Con save or pushed + damage.",
    casting_time="1 action", range="self (15-foot cube)", components="V, S",
    save_ability="con", damage_dice_count=2, damage_dice_sides=8,
    damage_type="thunder", at_higher_levels_dice=1))
register_spell(Spell("Chromatic Orb", 1, SpellSchool.EVOCATION,
    description="An orb of energy strikes a target. Ranged spell attack.",
    casting_time="1 action", range="90 feet", components="V, S, M",
    requires_attack_roll=True, damage_dice_count=3, damage_dice_sides=8,
    damage_type="acid", at_higher_levels_dice=1))
register_spell(Spell("Cure Wounds", 1, SpellSchool.EVOCATION,
    description="A creature you touch regains hit points.",
    casting_time="1 action", range="touch", components="V, S",
    healing_dice_count=1, healing_dice_sides=8, healing_bonus=0,
    at_higher_levels_dice=1))
register_spell(Spell("Healing Word", 1, SpellSchool.EVOCATION,
    description="A creature regains hit points as a bonus action.",
    casting_time="1 bonus action", range="60 feet", components="V",
    healing_dice_count=1, healing_dice_sides=4, healing_bonus=0,
    at_higher_levels_dice=1))
register_spell(Spell("Guiding Bolt", 1, SpellSchool.EVOCATION,
    description="A flash of light strikes a foe. Ranged spell attack.",
    casting_time="1 action", range="120 feet", components="V, S",
    requires_attack_roll=True, damage_dice_count=4, damage_dice_sides=6,
    damage_type="radiant", at_higher_levels_dice=1))
register_spell(Spell("Entangle", 1, SpellSchool.CONJURATION,
    description="Grasping weeds sprout. Str save or restrained.",
    casting_time="1 action", range="90 feet", components="V, S",
    save_ability="str", concentration=True))
register_spell(Spell("Shield of Faith", 1, SpellSchool.ABJURATION,
    description="A shimmering field grants +2 AC. Concentration.",
    casting_time="1 bonus action", range="60 feet", components="V, S, M",
    concentration=True))
register_spell(Spell("Detect Magic", 1, SpellSchool.DIVINATION,
    description="Sense the presence of magic. Ritual.",
    casting_time="1 action", range="self", components="V, S",
    concentration=True, ritual=True))
register_spell(Spell("Sleep", 1, SpellSchool.ENCHANTMENT,
    description="Creatures in an area fall asleep.",
    casting_time="1 action", range="90 feet", components="V, S, M"))
register_spell(Spell("Hex", 1, SpellSchool.ENCHANTMENT,
    description="Curse a target; extra damage on hits. Concentration.",
    casting_time="1 bonus action", range="90 feet", components="V, S, M",
    concentration=True))

# --- Level 2 ---------------------------------------------------------------
register_spell(Spell("Scorching Ray", 2, SpellSchool.EVOCATION,
    description="Rays of fire blast targets. Multiple ranged attacks.",
    casting_time="1 action", range="120 feet", components="V, S",
    requires_attack_roll=True, damage_dice_count=2, damage_dice_sides=6,
    damage_type="fire", at_higher_levels_dice=1))
register_spell(Spell("Shatter", 2, SpellSchool.EVOCATION,
    description="A loud ringing noise damages creatures. Con save.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    save_ability="con", damage_dice_count=3, damage_dice_sides=8,
    damage_type="thunder", at_higher_levels_dice=1))
register_spell(Spell("Web", 2, SpellSchool.CONJURATION,
    description="Webs restrain creatures in an area. Dex save.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    save_ability="dex", concentration=True))
register_spell(Spell("Invisibility", 2, SpellSchool.ILLUSION,
    description="A creature becomes invisible until it attacks or casts a spell.",
    casting_time="1 action", range="touch", components="V, S, M",
    concentration=True))
register_spell(Spell("Misty Step", 2, SpellSchool.CONJURATION,
    description="Briefly surround yourself with mist and teleport.",
    casting_time="1 bonus action", range="self", components="V"))
register_spell(Spell("Hold Person", 2, SpellSchool.ENCHANTMENT,
    description="Paralyze a humanoid. Wis save each turn.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    save_ability="wis", concentration=True))
register_spell(Spell("Blindness/Deafness", 2, SpellSchool.NECROMANCY,
    description="A target becomes blind or deaf. Con save.",
    casting_time="1 action", range="30 feet", components="V",
    save_ability="con", concentration=True))
register_spell(Spell("Flaming Sphere", 2, SpellSchool.EVOCATION,
    description="A 5-foot-diameter sphere of fire damages nearby creatures.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    damage_dice_count=2, damage_dice_sides=6, damage_type="fire",
    concentration=True))
register_spell(Spell("Mirror Image", 2, SpellSchool.ILLUSION,
    description="Three illusory duplicates distract attacks.",
    casting_time="1 action", range="self", components="V, S"))
register_spell(Spell("Ray of Enfeeblement", 2, SpellSchool.NECROMANCY,
    description="Target's weapon attacks deal half damage. Con save.",
    casting_time="1 action", range="60 feet", components="V, S",
    save_ability="con", concentration=True))
register_spell(Spell("Spider Climb", 2, SpellSchool.TRANSMUTATION,
    description="Target gains a climbing speed equal to walking speed.",
    casting_time="1 action", range="touch", components="V, S, M",
    concentration=True))
register_spell(Spell("Suggestion", 2, SpellSchool.ENCHANTMENT,
    description="Suggest a course of activity to a creature. Wis save.",
    casting_time="1 action", range="30 feet", components="V, M",
    save_ability="wis", concentration=True))

# --- Level 3 ---------------------------------------------------------------
register_spell(Spell("Fireball", 3, SpellSchool.EVOCATION,
    description="A bright streak flashes to a point and explodes. Dex save.",
    casting_time="1 action", range="150 feet", components="V, S, M",
    save_ability="dex", damage_dice_count=8, damage_dice_sides=6,
    damage_type="fire", at_higher_levels_dice=1))
register_spell(Spell("Lightning Bolt", 3, SpellSchool.EVOCATION,
    description="A stroke of lightning forms a line. Dex save.",
    casting_time="1 action", range="self (100-foot line)", components="V, S, M",
    save_ability="dex", damage_dice_count=8, damage_dice_sides=6,
    damage_type="lightning", at_higher_levels_dice=1))
register_spell(Spell("Healing Spirit", 3, SpellSchool.CONJURATION,
    description="A spirit heals creatures in its area.",
    casting_time="1 bonus action", range="60 feet", components="V, S",
    healing_dice_count=1, healing_dice_sides=6, healing_bonus=0,
    concentration=True, at_higher_levels_dice=1))
register_spell(Spell("Revivify", 3, SpellSchool.NECROMANCY,
    description="Bring a creature back from death instantly.",
    casting_time="1 action", range="touch", components="V, S, M",
    healing_dice_count=0, healing_dice_sides=0, healing_bonus=1))
register_spell(Spell("Counterspell", 3, SpellSchool.ABJURATION,
    description="Attempt to interrupt a creature in the process of casting a spell.",
    casting_time="1 reaction", range="60 feet", components="S"))
register_spell(Spell("Dispel Magic", 3, SpellSchool.ABJURATION,
    description="End a spell on a target or area.",
    casting_time="1 action", range="120 feet", components="V, S"))
register_spell(Spell("Fly", 3, SpellSchool.TRANSMUTATION,
    description="Target gains flying speed. Con check if restrained.",
    casting_time="1 action", range="touch", components="V, S, M",
    concentration=True))
register_spell(Spell("Haste", 3, SpellSchool.TRANSMUTATION,
    description="Choose a willing creature. Doubles speed, +2 AC, extra action.",
    casting_time="1 action", range="30 feet", components="V, S, M",
    concentration=True))
register_spell(Spell("Hypnotic Pattern", 3, SpellSchool.ILLUSION,
    description="Create a pattern of colors that charms creatures. Wis save.",
    casting_time="1 action", range="120 feet", components="V, S, M",
    save_ability="wis", concentration=True))
register_spell(Spell("Spirit Guardians", 3, SpellSchool.CONJURATION,
    description="Spirits protect you and damage nearby enemies. Wis save.",
    casting_time="1 action", range="self (15-foot radius)", components="V, S, M",
    save_ability="wis", damage_dice_count=3, damage_dice_sides=8,
    damage_type="radiant", concentration=True))
register_spell(Spell("Stinking Cloud", 3, SpellSchool.CONJURATION,
    description="Poisonous gas sickens creatures. Con save for retching.",
    casting_time="1 action", range="120 feet", components="V, S, M",
    save_ability="con", concentration=True))
register_spell(Spell("Thunderwave", 3, SpellSchool.EVOCATION,
    description="A wave of thunderous force. Con save or pushed + damage.",
    casting_time="1 action", range="self (15-foot cube)", components="V, S",
    save_ability="con", damage_dice_count=2, damage_dice_sides=8,
    damage_type="thunder", at_higher_levels_dice=1))

# --- Level 4 ---------------------------------------------------------------
register_spell(Spell("Polymorph", 4, SpellSchool.TRANSMUTATION,
    description="Transform a creature into a beast. Con save to resist.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    save_ability="con", concentration=True))
register_spell(Spell("Fire Shield", 4, SpellSchool.EVOCATION,
    description="Shield from cold/fire and damage attackers.",
    casting_time="1 action", range="self", components="V, S, M",
    concentration=True))
register_spell(Spell("Ice Storm", 4, SpellSchool.EVOCATION,
    description="Hailstones pound creatures and objects. Dex save for half.",
    casting_time="1 action", range="300 feet", components="V, S, M",
    save_ability="dex", damage_dice_count=5, damage_dice_sides=6,
    damage_type="cold"))
register_spell(Spell("Blight", 4, SpellSchool.NECROMANCY,
    description="Necrotic energy damages a plant creature. Con save.",
    casting_time="1 action", range="30 feet", components="V, S",
    save_ability="con", damage_dice_count=8, damage_dice_sides=8,
    damage_type="necrotic"))
register_spell(Spell("Greater Invisibility", 4, SpellSchool.ILLUSION,
    description="You or another creature becomes invisible for 1 minute.",
    casting_time="1 action", range="touch", components="V, S",
    concentration=True))
register_spell(Spell("Dimension Door", 4, SpellSchool.CONJURATION,
    description="Teleport yourself and another creature instantly.",
    casting_time="1 action", range="500 feet", components="V"))
register_spell(Spell("Stoneskin", 4, SpellSchool.ABJURATION,
    description="Grants resistance to nonmagical bludgeoning/piercing/slashing.",
    casting_time="1 action", range="touch", components="V, S, M",
    concentration=True))
register_spell(Spell("Phantasmal Killer", 4, SpellSchool.ILLUSION,
    description="Tap into nightmares. Wis save each round or take psychic damage.",
    casting_time="1 action", range="120 feet", components="V, S",
    save_ability="wis", damage_dice_count=4, damage_dice_sides=10,
    damage_type="psychic", concentration=True))

# --- Level 5 ---------------------------------------------------------------
register_spell(Spell("Cone of Cold", 5, SpellSchool.EVOCATION,
    description="Freezing cold sprays from your hands. Dex save for half.",
    casting_time="1 action", range="self (60-foot cone)", components="V, S, M",
    save_ability="dex", damage_dice_count=8, damage_dice_sides=8,
    damage_type="cold"))
register_spell(Spell("Scrying", 5, SpellSchool.DIVINATION,
    description="Spy on a creature from a distance. Wis save.",
    casting_time="10 minutes", range="self", components="V, S, M",
    save_ability="wis", concentration=True))
register_spell(Spell("Cloudkill", 5, SpellSchool.CONJURATION,
    description="Heavy cloud of poison kills creatures in area.",
    casting_time="1 action", range="120 feet", components="V, S",
    save_ability="con", damage_dice_count=5, damage_dice_sides=8,
    damage_type="poison", concentration=True))
register_spell(Spell("Animate Objects", 5, SpellSchool.TRANSMUTATION,
    description="Objects come to life and fight for you.",
    casting_time="1 action", range="60 feet", components="V, S",
    concentration=True))
register_spell(Spell("Flame Strike", 5, SpellSchool.EVOCATION,
    description="Searing flame in a column. Dex save for half.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    save_ability="dex", damage_dice_count=4, damage_dice_sides=6,
    damage_type="fire"))
register_spell(Spell("Hold Monster", 5, SpellSchool.ENCHANTMENT,
    description="Paralyze a creature. Wis save each turn.",
    casting_time="1 action", range="90 feet", components="V, S, M",
    save_ability="wis", concentration=True))
register_spell(Spell("Wall of Stone", 5, SpellSchool.EVOCATION,
    description="Create a stone wall that blocks passage.",
    casting_time="1 action", range="120 feet", components="V, S, M",
    concentration=True))
register_spell(Spell("Bigby's Hand", 5, SpellSchool.EVOCATION,
    description="A spectral hand grapples, pushes, or strikes foes.",
    casting_time="1 action", range="120 feet", components="V, S, M",
    concentration=True))

# --- Level 6 ---------------------------------------------------------------
register_spell(Spell("Disintegrate", 6, SpellSchool.TRANSMUTATION,
    description="Thin green ray reduces target to dust. Dex save.",
    casting_time="1 action", range="120 feet", components="V, S, M",
    save_ability="dex", damage_dice_count=10, damage_dice_sides=6,
    damage_type="force"))
register_spell(Spell("Chain Lightning", 6, SpellSchool.EVOCATION,
    description="Lightning arcs to multiple targets. Dex save for half.",
    casting_time="1 action", range="150 feet", components="V, S, M",
    save_ability="dex", damage_dice_count=10, damage_dice_sides=6,
    damage_type="lightning"))
register_spell(Spell("Sunbeam", 6, SpellSchool.EVOCATION,
    description="Brilliant sunlight blinds and damages. Con save for half.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    save_ability="con", damage_dice_count=8, damage_dice_sides=8,
    damage_type="radiant", concentration=True))
register_spell(Spell("Heal", 6, SpellSchool.EVOCATION,
    description="Massive healing and cures blindness/deafness/diseases.",
    casting_time="1 action", range="60 feet", components="V, S",
    healing_dice_count=0, healing_dice_sides=0, healing_bonus=70))
register_spell(Spell("Globe of Invulnerability", 6, SpellSchool.ABJURATION,
    description="Barrier stops spells of 5th level and lower.",
    casting_time="1 action", range="self (10-foot radius)", components="V, S, M",
    concentration=True))
register_spell(Spell("Flesh to Stone", 6, SpellSchool.TRANSMUTATION,
    description="Turn a creature to stone. Con save each round.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    save_ability="con", concentration=True))
register_spell(Spell("True Seeing", 6, SpellSchool.DIVINATION,
    description="See through illusions, shapechangers, invisibility.",
    casting_time="1 action", range="touch", components="V, S, M",
    concentration=True))

# --- Level 7 ---------------------------------------------------------------
register_spell(Spell("Finger of Death", 7, SpellSchool.NECROMANCY,
    description="Necrotic energy kills instantly if reduced to 0 HP.",
    casting_time="1 action", range="60 feet", components="V, S",
    save_ability="con", damage_dice_count=8, damage_dice_sides=8,
    damage_type="necrotic"))
register_spell(Spell("Fire Storm", 7, SpellSchool.EVOCATION,
    description="Storm of fire and smoke fills an area. Dex save for half.",
    casting_time="1 action", range="150 feet", components="V, S",
    save_ability="dex", damage_dice_count=10, damage_dice_sides=6,
    damage_type="fire"))
register_spell(Spell("Forcecage", 7, SpellSchool.EVOCATION,
    description="Imprison a creature in a cage of force. No save.",
    casting_time="1 action", range="100 feet", components="V, S, M"))
register_spell(Spell("Plane Shift", 7, SpellSchool.CONJURATION,
    description="Travel to another plane of existence.",
    casting_time="1 action", range="touch", components="V, S, M"))
register_spell(Spell("Simulacrum", 7, SpellSchool.ILLUSION,
    description="Create a duplicate of yourself from snow and ice.",
    casting_time="12 hours", range="touch", components="V, S, M"))
register_spell(Spell("Regenerate", 7, SpellSchool.EVOCATION,
    description="Target regrows severed limbs and regains HP.",
    casting_time="1 minute", range="touch", components="V, S, M",
    healing_dice_count=1, healing_dice_sides=4, healing_bonus=15,
    concentration=True))
register_spell(Spell("Teleport", 7, SpellSchool.CONJURATION,
    description="Instantly transport to a known location.",
    casting_time="1 action", range="10 feet", components="V"))

# --- Level 8 ---------------------------------------------------------------
register_spell(Spell("Power Word Stun", 8, SpellSchool.ENCHANTMENT,
    description="Creature with 150 HP or less is stunned. No save.",
    casting_time="1 action", range="60 feet", components="V"))
register_spell(Spell("Dominate Monster", 8, SpellSchool.ENCHANTMENT,
    description="Control a creature. Wis save each turn.",
    casting_time="1 action", range="60 feet", components="V, S",
    save_ability="wis", concentration=True))
register_spell(Spell("Maze", 8, SpellSchool.ENCHANTMENT,
    description="Trap a creature in an extradimensional maze. Int check.",
    casting_time="1 action", range="60 feet", components="V"))
register_spell(Spell("Sunburst", 8, SpellSchool.EVOCATION,
    description="Brilliant flash blinds and deals radiant damage. Con save.",
    casting_time="1 action", range="150 feet", components="V, S, M",
    save_ability="con", damage_dice_count=12, damage_dice_sides=6,
    damage_type="radiant"))
register_spell(Spell("Earthquake", 8, SpellSchool.EVOCATION,
    description="Powerful tremor shakes ground in a large area.",
    casting_time="1 action", range="500 feet", components="V, S, M"))
register_spell(Spell("Feeblemind", 8, SpellSchool.ENCHANTMENT,
    description="Target's INT and CHA become 1. Int save.",
    casting_time="1 action", range="150 feet", components="V, S, M",
    save_ability="int"))
register_spell(Spell("Abi-Dalzim's Horrid Wilting", 8, SpellSchool.NECROMANCY,
    description="Draw moisture from creatures. Con save for half.",
    casting_time="1 action", range="150 feet", components="V, S, M",
    save_ability="con", damage_dice_count=12, damage_dice_sides=8,
    damage_type="necrotic"))

# --- Level 9 ---------------------------------------------------------------
register_spell(Spell("Power Word Kill", 9, SpellSchool.ENCHANTMENT,
    description="Creature with 100 HP or less dies instantly. No save.",
    casting_time="1 action", range="60 feet", components="V"))
register_spell(Spell("Meteor Swarm", 9, SpellSchool.EVOCATION,
    description="Flaming meteors pummel a massive area. Dex save for half.",
    casting_time="1 action", range="1 mile", components="V, S",
    save_ability="dex", damage_dice_count=20, damage_dice_sides=6,
    damage_type="fire"))
register_spell(Spell("Wish", 9, SpellSchool.EVOCATION,
    description="Rewrite reality itself. Can duplicate any spell or create effects.",
    casting_time="1 action", range="self", components="V"))
register_spell(Spell("Time Stop", 9, SpellSchool.TRANSMUTATION,
    description="You freeze time for 1d4+1 rounds while you can act freely.",
    casting_time="1 action", range="self", components="V"))
register_spell(Spell("True Polymorph", 9, SpellSchool.TRANSMUTATION,
    description="Transform a creature into any other creature permanently.",
    casting_time="1 action", range="30 feet", components="V, S, M",
    concentration=True))
register_spell(Spell("Power Word Heal", 9, SpellSchool.EVOCATION,
    description="Target returns to full HP and is freed from charms/fear/etc.",
    casting_time="1 action", range="60 feet", components="V, S",
    healing_dice_count=0, healing_dice_sides=0, healing_bonus=9999))
register_spell(Spell("Foresight", 9, SpellSchool.DIVINATION,
    description="You glimpse the future and gain advantage on attacks/saves.",
    casting_time="1 minute", range="touch", components="V, S, M",
    concentration=True))


# ---------------------------------------------------------------------------
# Starting spells per class (level 1): cantrips + known/prepared level 1 spells.
# ---------------------------------------------------------------------------

STARTING_SPELLS = {
    "wizard": {
        "cantrips": ["fire_bolt", "light", "mage_hand"],
        "spells": ["magic_missile", "burning_hands", "detect_magic", "shield_of_faith"],
    },
    "sorcerer": {
        "cantrips": ["fire_bolt", "ray_of_frost", "acid_splash"],
        "spells": ["magic_missile", "burning_hands", "chromatic_orb"],
    },
    "cleric": {
        "cantrips": ["sacred_flame", "light", "mage_hand"],
        "spells": ["cure_wounds", "healing_word", "guiding_bolt", "bless" if False else "shield_of_faith"],
    },
    "druid": {
        "cantrips": ["acid_splash", "minor_illusion", "light"],
        "spells": ["cure_wounds", "entangle", "healing_word"],
    },
    "bard": {
        "cantrips": ["vicious_mockery", "minor_illusion", "light"],
        "spells": ["healing_word", "sleep"],
    },
    "warlock": {
        "cantrips": ["eldritch_blast", "mage_hand", "minor_illusion"],
        "spells": ["hex", "burning_hands"],
    },
    "paladin": {
        "cantrips": [],
        "spells": ["cure_wounds", "shield_of_faith"],
    },
    "ranger": {
        "cantrips": [],
        "spells": ["cure_wounds", "entangle"],
    },
}


# ---------------------------------------------------------------------------
# Casting resolution
# ---------------------------------------------------------------------------

@dataclass
class SpellEffectResult:
    """Outcome of resolving a spell's effect against a target context."""
    spell_name: str
    slot_level: int
    rolled_attack: Optional[int]  # d20 total for attack-roll spells
    hit: Optional[bool]           # attack-roll spells only
    made_save: Optional[bool]     # saving-throw spells only
    damage: int
    healing: int
    damage_type: str
    half_damage: bool             # saved for half
    description: str


def resolve_spell_effect(
    spell: Spell,
    caster_level: int,
    proficiency_bonus: int,
    casting_mod: int,
    slot_level: Optional[int] = None,
    target_ac: Optional[int] = None,
    target_save_total: Optional[int] = None,
    spell_save_dc: Optional[int] = None,
) -> SpellEffectResult:
    """Resolve a spell's mechanical effect.

    Parameters
    ----------
    target_ac : int, optional
        Required for attack-roll spells. The attack hits if total >= AC.
    target_save_total : int, optional
        The target's d20 + save ability mod + proficiency. Compared against
        ``spell_save_dc`` (or one derived from the caster).
    spell_save_dc : int, optional
        Save DC. If omitted, derived as 8 + proficiency + casting_mod.
    """
    slot_level = slot_level if slot_level is not None else spell.level
    if spell_save_dc is None:
        spell_save_dc = 8 + proficiency_bonus + casting_mod
    spell_attack = proficiency_bonus + casting_mod

    # ----- Attack-roll spell ----------------------------------------------
    if spell.requires_attack_roll:
        if target_ac is None:
            raise ValueError(f"{spell.name} requires a target_ac to resolve")
        attack = roll_d20(spell_attack)
        rolled = attack.total
        d20 = attack.rolls[0]
        hit = (d20 != 1) and (d20 == 20 or rolled >= target_ac)
        if not hit:
            return SpellEffectResult(
                spell_name=spell.name, slot_level=slot_level,
                rolled_attack=rolled, hit=False, made_save=None,
                damage=0, healing=0, damage_type=spell.damage_type,
                half_damage=False,
                description=f"{spell.name} attack rolled {rolled} vs AC {target_ac} — miss.",
            )
        damage = spell.roll_damage(caster_level, slot_level)
        crit = d20 == 20
        if crit:
            damage += spell.roll_damage(caster_level, slot_level)  # crude crit
        return SpellEffectResult(
            spell_name=spell.name, slot_level=slot_level,
            rolled_attack=rolled, hit=True, made_save=None,
            damage=damage, healing=0, damage_type=spell.damage_type,
            half_damage=False,
            description=f"{spell.name} hit (rolled {rolled} vs AC {target_ac}) "
                        f"for {damage} {spell.damage_type} damage"
                        + (" — CRITICAL!" if crit else "") + ".",
        )

    # ----- Saving-throw spell ---------------------------------------------
    if spell.save_ability is not None:
        made_save = None
        if target_save_total is not None:
            made_save = target_save_total >= spell_save_dc
        full = spell.roll_damage(caster_level, slot_level)
        if spell.deals_damage:
            if made_save is None:
                damage = full
                half = False
                note = "(no save provided — full damage applied)"
            elif made_save:
                damage = full // 2
                half = True
                note = f"target saved (DC {spell_save_dc}) — half damage"
            else:
                damage = full
                half = False
                note = f"target failed save (DC {spell_save_dc})"
            return SpellEffectResult(
                spell_name=spell.name, slot_level=slot_level,
                rolled_attack=None, hit=None, made_save=made_save,
                damage=damage, healing=0, damage_type=spell.damage_type,
                half_damage=half,
                description=f"{spell.name} deals {damage} {spell.damage_type} damage {note}.",
            )
        # Save spell with no damage (e.g. Entangle) — success/failure only.
        return SpellEffectResult(
            spell_name=spell.name, slot_level=slot_level,
            rolled_attack=None, hit=None, made_save=made_save,
            damage=0, healing=0, damage_type="",
            half_damage=False,
            description=f"{spell.name} resolved (save vs DC {spell_save_dc}).",
        )

    # ----- Direct damage spell (no attack roll, no save, e.g., Magic Missile) -----
    if spell.deals_damage:
        damage = spell.roll_damage(caster_level, slot_level)
        return SpellEffectResult(
            spell_name=spell.name, slot_level=slot_level,
            rolled_attack=None, hit=None, made_save=None,
            damage=damage, healing=0, damage_type=spell.damage_type,
            half_damage=False,
            description=f"{spell.name} deals {damage} {spell.damage_type} damage automatically.",
        )

    # ----- Healing spell ---------------------------------------------------
    if spell.heals:
        healing = spell.roll_healing(caster_level, slot_level)
        return SpellEffectResult(
            spell_name=spell.name, slot_level=slot_level,
            rolled_attack=None, hit=None, made_save=None,
            damage=0, healing=healing, damage_type="",
            half_damage=False,
            description=f"{spell.name} restores {healing} HP.",
        )

    # ----- Utility spell ---------------------------------------------------
    return SpellEffectResult(
        spell_name=spell.name, slot_level=slot_level,
        rolled_attack=None, hit=None, made_save=None,
        damage=0, healing=0, damage_type="", half_damage=False,
        description=f"{spell.name} takes effect.",
    )


# ---------------------------------------------------------------------------
# Spellbook — owned by a character
# ---------------------------------------------------------------------------

@dataclass
class CastOutcome:
    """Result of attempting to cast a spell from a Spellbook."""
    success: bool
    message: str
    effect: Optional[SpellEffectResult] = None
    slot_level: Optional[int] = None
    spell: Optional[Spell] = None


class Spellbook:
    """A character's collection of known/prepared spells plus spell slots."""

    def __init__(
        self,
        char_class: str,
        level: int = 1,
        known_spells: Optional[list[str]] = None,
        prepared_spells: Optional[list[str]] = None,
        slots_used: Optional[list[int]] = None,
        max_slots: Optional[list[int]] = None,
    ) -> None:
        profile = CASTER_PROFILES.get(char_class.lower())
        if profile is None:
            # Unknown class — default to a non-caster.
            self.caster_type = CasterType.NONE
            self.casting_style = CastingStyle.NONE
            self.casting_ability = "int"
        else:
            self.caster_type, self.casting_style, self.casting_ability = profile

        self.char_class = char_class.lower()
        self.level = max(1, level)
        self.known_spells: list[str] = list(known_spells) if known_spells else []
        self.prepared_spells: list[str] = list(prepared_spells) if prepared_spells else []
        self._slots_used: list[int] = list(slots_used) if slots_used else [0] * 9
        # Recompute max slots unless explicitly provided (e.g. on deserialization).
        self._max_slots: list[int] = (
            list(max_slots) if max_slots is not None
            else slots_for_level(self.level, self.caster_type)
        )

    # --- Casting ability helpers -----------------------------------------

    @property
    def is_caster(self) -> bool:
        return self.caster_type != CasterType.NONE

    @property
    def spell_attack_bonus(self) -> int:
        return proficiency_bonus(self.level) + _ability_modifier_from_book(self)

    @property
    def spell_save_dc(self) -> int:
        return 8 + proficiency_bonus(self.level) + _ability_modifier_from_book(self)

    # --- Spell-slot accounting -------------------------------------------

    def set_level(self, level: int) -> None:
        """Update character level and recompute max slots (keeping spent slots)."""
        self.level = max(1, level)
        self._max_slots = slots_for_level(self.level, self.caster_type)
        # Clamp used slots to new maxima.
        self._slots_used = [
            min(u, m) for u, m in zip(self._slots_used, self._max_slots)
        ] + [0] * (9 - len(self._slots_used))
        self._slots_used = self._slots_used[:9]

    def max_slots(self, slot_level: int) -> int:
        if slot_level < 1 or slot_level > 9:
            return 0
        return self._max_slots[slot_level - 1]

    def slots_used(self, slot_level: int) -> int:
        if slot_level < 1 or slot_level > 9:
            return 0
        return self._slots_used[slot_level - 1]

    def available_slots(self, slot_level: int) -> int:
        return max(0, self.max_slots(slot_level) - self.slots_used(slot_level))

    def slots_overview(self) -> list[dict]:
        return [
            {
                "level": lvl,
                "max": self.max_slots(lvl),
                "used": self.slots_used(lvl),
                "available": self.available_slots(lvl),
            }
            for lvl in range(1, 10)
        ]

    @property
    def has_slots_available(self) -> bool:
        return any(self.available_slots(lvl) > 0 for lvl in range(1, 10))

    # --- Spell ownership -------------------------------------------------

    def knows(self, spell_id: str) -> bool:
        return _norm(spell_id) in self.known_spells or _norm(spell_id) in self.prepared_spells

    def learn_spell(self, spell_id: str) -> bool:
        """Add a spell to the known list. Returns False if already known."""
        sid = _norm(spell_id)
        spell = get_spell(sid)
        if spell is None:
            return False
        if sid in self.known_spells or sid in self.prepared_spells:
            return False
        self.known_spells.append(sid)
        return True

    def forget_spell(self, spell_id: str) -> bool:
        sid = _norm(spell_id)
        removed = sid in self.known_spells
        if sid in self.known_spells:
            self.known_spells.remove(sid)
        if sid in self.prepared_spells:
            self.prepared_spells.remove(sid)
        return removed

    def prepare_spell(self, spell_id: str) -> bool:
        """Mark a known spell as prepared. Returns False if not known."""
        sid = _norm(spell_id)
        if sid not in self.known_spells:
            return False
        if sid not in self.prepared_spells:
            self.prepared_spells.append(sid)
        return True

    def unprepare_spell(self, spell_id: str) -> bool:
        sid = _norm(spell_id)
        if sid in self.prepared_spells:
            self.prepared_spells.remove(sid)
            return True
        return False

    def castable_spells(self) -> list[Spell]:
        """Spells the character can currently choose to cast.

        - Cantrips are always available if known/prepared.
        - Known casters: all known spells.
        - Prepared casters: only prepared spells (plus cantrips known).
        """
        ids = set()
        # Cantrips are always available.
        for sid in list(self.known_spells) + list(self.prepared_spells):
            spell = get_spell(sid)
            if spell and spell.is_cantrip:
                ids.add(sid)
        if self.casting_style == CastingStyle.KNOWN:
            ids.update(self.known_spells)
        elif self.casting_style == CastingStyle.PREPARED:
            ids.update(self.prepared_spells)
        return [s for s in (get_spell(i) for i in sorted(ids)) if s is not None]

    def can_cast(self, spell_id: str, slot_level: Optional[int] = None) -> bool:
        sid = _norm(spell_id)
        spell = get_spell(sid)
        if spell is None:
            return False
        if not self.is_caster:
            return False
        if spell not in self.castable_spells():
            return False
        if spell.is_cantrip:
            return True
        # Need an available slot at or above the spell's level.
        target = slot_level or spell.level
        for lvl in range(max(spell.level, target), 10):
            if self.available_slots(lvl) > 0:
                return True
        return False

    # --- Casting ---------------------------------------------------------

    def cast(
        self,
        spell_id: str,
        slot_level: Optional[int] = None,
        caster_mod: int = 0,
        target_ac: Optional[int] = None,
        target_save_total: Optional[int] = None,
    ) -> CastOutcome:
        """Attempt to cast a spell, consuming a slot if needed.

        Returns a CastOutcome whose ``effect`` (if not None) can be applied to a
        target by the caller (combat engine / API).
        """
        sid = _norm(spell_id)
        spell = get_spell(sid)
        if spell is None:
            return CastOutcome(False, f"Unknown spell: {spell_id}")
        if not self.is_caster:
            return CastOutcome(False, f"{self.char_class} cannot cast spells")
        if spell not in self.castable_spells():
            return CastOutcome(False, f"{spell.name} is not available to cast "
                                      "(not known/prepared)")

        if spell.is_cantrip:
            used_level = 0
        else:
            # Determine the slot to expend: caller's choice, else the lowest
            # available slot at or above the spell's level.
            target = slot_level or spell.level
            chosen = next(
                (lvl for lvl in range(max(spell.level, target), 10)
                 if self.available_slots(lvl) > 0),
                None,
            )
            if chosen is None:
                return CastOutcome(False, f"No spell slots available for {spell.name}")
            if slot_level is not None and self.available_slots(slot_level) <= 0:
                return CastOutcome(False, f"No level-{slot_level} slots available")
            used_level = slot_level or chosen
            self._slots_used[used_level - 1] += 1

        prof = proficiency_bonus(self.level)
        effect = resolve_spell_effect(
            spell=spell,
            caster_level=self.level,
            proficiency_bonus=prof,
            casting_mod=caster_mod,
            slot_level=used_level if used_level > 0 else None,
            target_ac=target_ac,
            target_save_total=target_save_total,
        )
        return CastOutcome(
            success=True,
            message=effect.description,
            effect=effect,
            slot_level=used_level,
            spell=spell,
        )

    # --- Rest ------------------------------------------------------------

    def long_rest(self) -> None:
        """Recover all expended spell slots."""
        self._slots_used = [0] * 9

    # --- Serialization ---------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "char_class": self.char_class,
            "level": self.level,
            "caster_type": self.caster_type.value,
            "casting_style": self.casting_style.value,
            "casting_ability": self.casting_ability,
            "known_spells": list(self.known_spells),
            "prepared_spells": list(self.prepared_spells),
            "slots_used": list(self._slots_used),
            "max_slots": list(self._max_slots),
            "slots": self.slots_overview(),
            "castable_spells": [s.to_dict() for s in self.castable_spells()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Spellbook":
        char_class = data.get("char_class", "fighter")
        level = data.get("level", 1)
        known = data.get("known_spells", [])
        prepared = data.get("prepared_spells", [])
        used = data.get("slots_used", [0] * 9)
        max_slots = data.get("max_slots")

        # Create the spellbook with the correct char_class first
        book = cls(
            char_class=char_class,
            level=level,
            known_spells=known,
            prepared_spells=prepared,
            slots_used=used,
            max_slots=max_slots,
        )

        # If max_slots was provided (not from fresh creation), use it
        if max_slots is not None:
            book._max_slots = list(max_slots)

        return book


# ---------------------------------------------------------------------------
# Starting spellbook factory
# ---------------------------------------------------------------------------

def get_starting_spellbook(char_class: str, level: int = 1) -> Spellbook:
    """Build the starting spellbook for a class at a given level.

    Cantrips are always known (and considered available). For known casters,
    starting spells are added to ``known_spells``. For prepared casters, they
    are added to both ``known_spells`` and ``prepared_spells`` so they can be
    cast immediately.
    """
    book = Spellbook(char_class=char_class, level=level)
    starting = STARTING_SPELLS.get(char_class.lower())
    if not starting or not book.is_caster:
        return book

    cantrips = starting.get("cantrips", [])
    spells = starting.get("spells", [])

    # Filter to spells that actually exist in the registry.
    cantrip_ids = [c for c in cantrips if get_spell(c) is not None]
    spell_ids = [s for s in spells if get_spell(s) is not None]

    all_ids = cantrip_ids + spell_ids
    for sid in all_ids:
        book.known_spells.append(sid)

    if book.casting_style == CastingStyle.PREPARED:
        for sid in spell_ids:
            book.prepared_spells.append(sid)

    return book


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _norm(spell_id: str) -> str:
    return spell_id.lower().replace(" ", "_")


def _ability_modifier_from_book(book: Spellbook) -> int:
    """Placeholder ability modifier derived from the casting ability.

    The Spellbook does not store ability scores; callers pass the real modifier
    into ``cast``. This returns 0 so save-DC/attack math degrades gracefully if
    no modifier is supplied.
    """
    return 0
