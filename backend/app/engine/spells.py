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
import re
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
# Spell Components — parsed and structured
# ---------------------------------------------------------------------------

@dataclass
class SpellComponents:
    """Parsed spell components with material details."""
    verbal: bool = False
    somatic: bool = False
    material: bool = False
    material_description: str = ""
    material_cost_gp: float = 0.0
    material_consumed: bool = True

    def has_verbal(self) -> bool:
        return self.verbal

    def has_somatic(self) -> bool:
        return self.somatic

    def has_material(self) -> bool:
        return self.material

    def to_dict(self) -> dict:
        return {
            "verbal": self.verbal,
            "somatic": self.somatic,
            "material": self.material,
            "material_description": self.material_description,
            "material_cost_gp": self.material_cost_gp,
            "material_consumed": self.material_consumed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SpellComponents":
        return cls(
            verbal=data.get("verbal", False),
            somatic=data.get("somatic", False),
            material=data.get("material", False),
            material_description=data.get("material_description", ""),
            material_cost_gp=data.get("material_cost_gp", 0.0),
            material_consumed=data.get("material_consumed", True),
        )


def parse_components(components_str: str, material_desc: str = "") -> SpellComponents:
    """Parse a components string into structured data.

    Args:
        components_str: e.g., "V", "V, S", "V, S, M", "V, M"
        material_desc: Optional material component description and cost, e.g.,
            "a tiny piece of phosphor" or "a diamond worth at least 300 gp"

    Returns:
        SpellComponents with parsed flags and material details.
    """
    comp = SpellComponents()
    parts = [p.strip().upper() for p in components_str.split(",")]
    comp.verbal = "V" in parts
    comp.somatic = "S" in parts
    comp.material = "M" in parts

    if comp.material and material_desc:
        comp.material_description = material_desc.strip()

        # Parse gold cost if present (e.g., "a diamond worth at least 300 gp")
        cost_match = re.search(r"(\d+(?:\.\d+)?)\s*gp", material_desc.lower())
        if cost_match:
            comp.material_cost_gp = float(cost_match.group(1))

    return comp


# Conditions that prevent verbal components (speech not possible)
SILENCED_CONDITIONS = frozenset([
    "paralyzed",      # can't speak (per PHB)
    "petrified",      # can't speak (per PHB)
    "unconscious",    # can't speak (per PHB)
    "stunned",        # can speak only falteringly - effectively no verbal spells
])

# Conditions that prevent somatic components (no hand gestures possible)
NO_SOMATIC_CONDITIONS = frozenset([
    "paralyzed",      # can't move
    "petrified",      # can't move
    "unconscious",    # can't move
])


def can_cast_with_conditions(
    components: SpellComponents,
    active_conditions: list[str],
) -> tuple[bool, str]:
    """Check if spell can be cast given current conditions.

    Returns:
        (can_cast, reason) where reason is empty if can_cast is True.
    """
    if components.has_verbal():
        blocked = any(c in active_conditions for c in SILENCED_CONDITIONS)
        if blocked:
            return False, "Cannot cast spells with verbal components while silenced or unable to speak"

    if components.has_somatic():
        blocked = any(c in active_conditions for c in NO_SOMATIC_CONDITIONS)
        if blocked:
            return False, "Cannot cast spells with somatic components while unable to move"

    return True, ""


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

    # Material component description (for M components), e.g., "a tiny piece of phosphor"
    material_description: str = ""

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

    # Parsed components (auto-populated from components + material_description)
    _parsed_components: SpellComponents = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.school, str):
            object.__setattr__(self, "school", SpellSchool(self.school))
        # Parse components
        object.__setattr__(self, "_parsed_components", parse_components(self.components, self.material_description))

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

    @property
    def parsed_components(self) -> SpellComponents:
        """The parsed components data."""
        return self._parsed_components

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
            "material_description": self.material_description,
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
            "parsed_components": self._parsed_components.to_dict(),
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
            material_description=data.get("material_description", ""),
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
register_spell(Spell("Chill Touch", 0, SpellSchool.NECROMANCY,
    description="A spectral hand sears a target. Ranged spell attack; target can't regain HP for a turn.",
    casting_time="1 action", range="120 feet", components="V, S",
    requires_attack_roll=True, damage_dice_count=1, damage_dice_sides=8,
    damage_type="necrotic"))
register_spell(Spell("Poison Spray", 0, SpellSchool.CONJURATION,
    description="A noxious gas poisons a nearby creature. Con save.",
    casting_time="1 action", range="10 feet", components="V, S",
    save_ability="con", damage_dice_count=1, damage_dice_sides=12,
    damage_type="poison"))
register_spell(Spell("Shocking Grasp", 0, SpellSchool.EVOCATION,
    description="Lightning springs from your hand to a creature. Melee spell attack; advantage vs. metal armor.",
    casting_time="1 action", range="touch", components="V, S",
    requires_attack_roll=True, damage_dice_count=1, damage_dice_sides=8,
    damage_type="lightning"))
register_spell(Spell("Toll the Dead", 0, SpellSchool.NECROMANCY,
    description="A dolorous bell tolls for a target. Wis save; 1d12 necrotic if the target is missing HP, else 1d8.",
    casting_time="1 action", range="60 feet", components="V, S",
    save_ability="wis", damage_dice_count=1, damage_dice_sides=8,
    damage_type="necrotic"))
register_spell(Spell("Mind Sliver", 0, SpellSchool.ENCHANTMENT,
    description="A beam of psychic energy pierces a mind. Int save; target subtracts 1d4 from its next save.",
    casting_time="1 action", range="60 feet", components="V",
    save_ability="int", damage_dice_count=1, damage_dice_sides=6,
    damage_type="psychic"))

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
register_spell(Spell("Shield", 1, SpellSchool.ABJURATION,
    description="An invisible barrier grants +5 AC until your next turn. Cast as a reaction.",
    casting_time="1 reaction", range="self", components="V, S",
    duration="1 round"))
register_spell(Spell("Mage Armor", 1, SpellSchool.ABJURATION,
    description="A protective magical force surrounds a creature; its AC becomes 13 + Dex. 8 hours.",
    casting_time="1 action", range="touch", components="V, S, M",
    duration="8 hours"))
register_spell(Spell("Bless", 1, SpellSchool.ENCHANTMENT,
    description="Up to three creatures add 1d4 to attack rolls and saving throws. Concentration.",
    casting_time="1 action", range="30 feet", components="V, S, M",
    concentration=True, duration="up to 1 minute"))
register_spell(Spell("Bane", 1, SpellSchool.ENCHANTMENT,
    description="Up to three enemies subtract 1d4 from attack rolls and saving throws. Cha save. Concentration.",
    casting_time="1 action", range="30 feet", components="V, S, M",
    save_ability="cha", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Command", 1, SpellSchool.ENCHANTMENT,
    description="A target obeys a one-word command on its next turn. Wis save.",
    casting_time="1 action", range="60 feet", components="V",
    save_ability="wis", duration="1 round"))
register_spell(Spell("Charm Person", 1, SpellSchool.ENCHANTMENT,
    description="A humanoid regards you as a friendly acquaintance for 1 hour. Wis save.",
    casting_time="1 action", range="30 feet", components="V, S",
    save_ability="wis", duration="1 hour"))
register_spell(Spell("Hunter's Mark", 1, SpellSchool.DIVINATION,
    description="Mark a creature; deal an extra 1d6 damage on weapon hits. Concentration.",
    casting_time="1 bonus action", range="90 feet", components="V",
    concentration=True, duration="up to 1 hour"))
register_spell(Spell("Faerie Fire", 1, SpellSchool.EVOCATION,
    description="Outline objects in a 20-foot cube; affected creatures grant attack advantage. Dex save. Concentration.",
    casting_time="1 action", range="60 feet", components="V",
    save_ability="dex", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Grease", 1, SpellSchool.CONJURATION,
    description="Cover a 10-foot square in grease; creatures must save or fall prone. Dex save.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    save_ability="dex", duration="1 minute"))

# Additional iconic PHB level-1 spells (utility, buff, control, attack, save).
register_spell(Spell("Alarm", 1, SpellSchool.ABJURATION,
    description="Ward a 20-foot cube for 8 hours; you are alerted when a Tiny or larger "
                "creature touches or enters it. Ritual.",
    casting_time="1 minute", range="30 feet", components="V, S, M",
    ritual=True, duration="8 hours"))
register_spell(Spell("Comprehend Languages", 1, SpellSchool.DIVINATION,
    description="For 1 hour you understand all spoken language you hear and can read text "
                "you touch. Ritual.",
    casting_time="1 action", range="self", components="V, S, M",
    ritual=True, duration="1 hour"))
register_spell(Spell("Disguise Self", 1, SpellSchool.ILLUSION,
    description="For 1 hour your appearance — including clothing, armor, and body — changes. "
                "A creature can investigate (Int check) to determine it is an illusion.",
    casting_time="1 action", range="self", components="V, S",
    duration="1 hour"))
register_spell(Spell("False Life", 1, SpellSchool.NECROMANCY,
    description="Bolster yourself with necromantic energy, gaining temporary hit points "
                "for 1 hour.",
    casting_time="1 action", range="self", components="V, S, M",
    healing_dice_count=1, healing_dice_sides=4, healing_bonus=4,
    duration="1 hour", at_higher_levels_dice=5))
register_spell(Spell("Find Familiar", 1, SpellSchool.CONJURATION,
    description="Summon a spirit that takes an animal form as your familiar. It can't attack "
                "but can deliver your touch spells. Ritual; lasts until dismissed.",
    casting_time="1 hour", range="10 feet", components="V, S, M",
    ritual=True, duration="until dismissed"))
register_spell(Spell("Fog Cloud", 1, SpellSchool.CONJURATION,
    description="A 20-foot sphere of fog centered on a point becomes heavily obscured. "
                "Concentration, up to 1 hour.",
    casting_time="1 action", range="120 feet", components="V, S",
    concentration=True, duration="up to 1 hour"))
register_spell(Spell("Hellish Rebuke", 1, SpellSchool.EVOCATION,
    description="In reaction to being damaged by a creature within 60 feet, you point and it "
                "is wreathed in hellish flames. Dex save for half.",
    casting_time="1 reaction", range="60 feet", components="V, S",
    save_ability="dex", damage_dice_count=2, damage_dice_sides=10,
    damage_type="fire", at_higher_levels_dice=1))
register_spell(Spell("Identify", 1, SpellSchool.DIVINATION,
    description="Touch an object for 1 minute to learn its magical properties and how to use "
                "them. Ritual.",
    casting_time="1 minute", range="touch", components="V, S, M",
    ritual=True))
register_spell(Spell("Inflict Wounds", 1, SpellSchool.NECROMANCY,
    description="Make a melee spell attack against a creature; on a hit it takes necrotic "
                "damage from a chilling touch.",
    casting_time="1 action", range="touch", components="V, S",
    requires_attack_roll=True, damage_dice_count=3, damage_dice_sides=10,
    damage_type="necrotic", at_higher_levels_dice=1))
register_spell(Spell("Longstrider", 1, SpellSchool.TRANSMUTATION,
    description="Touch a creature to increase its speed by 10 feet for 1 hour.",
    casting_time="1 action", range="touch", components="V, S, M",
    duration="1 hour"))
register_spell(Spell("Protection from Evil and Good", 1, SpellSchool.ABJURATION,
    description="Touch a creature to ward it for 10 minutes: aberrations, celestials, "
                "elementals, fey, fiends, and undead have disadvantage on attacks against it, "
                "and it can't be charmed, frightened, or possessed by them. Concentration.",
    casting_time="1 action", range="touch", components="V, S, M",
    concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Ray of Sickness", 1, SpellSchool.NECROMANCY,
    description="A sickening ray. Ranged spell attack; on a hit the target takes poison damage "
                "and must succeed on a Con save or be poisoned until your next turn.",
    casting_time="1 action", range="60 feet", components="V, S",
    requires_attack_roll=True, damage_dice_count=2, damage_dice_sides=8,
    damage_type="poison", at_higher_levels_dice=1))
register_spell(Spell("Sanctuary", 1, SpellSchool.ABJURATION,
    description="Ward a creature for 1 minute: any attacker targeting it must first succeed "
                "on a Wis save or be forced to choose a different target.",
    casting_time="1 bonus action", range="30 feet", components="V, S, M",
    save_ability="wis", duration="1 minute"))
register_spell(Spell("Speak with Animals", 1, SpellSchool.DIVINATION,
    description="For 10 minutes you comprehend and can be understood by beasts. Concentration. "
                "Ritual.",
    casting_time="1 action", range="self", components="V, S",
    concentration=True, ritual=True, duration="10 minutes"))
register_spell(Spell("Tasha's Hideous Laughter", 1, SpellSchool.ENCHANTMENT,
    description="A target perceives everything as funny and falls prone with laughter, "
                "incapacitated. Wis save negates; repeats each turn and after taking damage. "
                "Concentration, up to 1 minute.",
    casting_time="1 action", range="30 feet", components="V, S, M",
    save_ability="wis", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Witch Bolt", 1, SpellSchool.EVOCATION,
    description="A sustained arc of lightning. Ranged spell attack for lightning damage; while "
                "concentrating you can use your action each turn to deal the damage again "
                "automatically.",
    casting_time="1 action", range="30 feet", components="V, S, M",
    requires_attack_roll=True, damage_dice_count=1, damage_dice_sides=12,
    damage_type="lightning", concentration=True, duration="up to 1 minute",
    at_higher_levels_dice=1))

# Additional iconic PHB level-1 spells (completing the tier to PHB coverage).
# Save-debuff (no damage): Animal Friendship, Compelled Duel.
# Healing (consumable berries): Goodberry.
# Utility / buff / ritual: Color Spray, Create or Destroy Water, Detect Evil and
# Good, Detect Poison and Disease, Expeditious Retreat, Feather Fall, Heroism,
# Jump, Purify Food and Drink, Silent Image, Tenser's Floating Disk,
# Unseen Servant, Wrathful Smite.
register_spell(Spell("Animal Friendship", 1, SpellSchool.ENCHANTMENT,
    description="Convince a beast you mean it no harm. A target beast (Intelligence 3 or lower) "
                "must make a Wisdom save or be charmed by you for the duration. ",
    casting_time="1 action", range="30 feet", components="V, S, M",
    save_ability="wis", duration="24 hours"))
register_spell(Spell("Color Spray", 1, SpellSchool.ILLUSION,
    description="A dazzling cone of flashing colored light springs from your hand. Roll 6d10 — "
                "the total is how many hit points of creatures this spell can affect. Creatures "
                "in a 15-foot cone are affected in ascending hit-point order: each becomes "
                "unconscious and blinded until the end of your next turn. No saving throw (the "
                "6d10 sets the hit-point budget). Upcasting adds 2d10 to the budget per slot "
                "level above 1st.",
    casting_time="1 action", range="self (15-foot cone)", components="V, S, M",
    duration="1 round"))
register_spell(Spell("Compelled Duel", 1, SpellSchool.ABJURATION,
    description="Compel a creature into a duel. The target must make a Wisdom save or be drawn "
                "to you, gaining disadvantage on attack rolls against creatures other than you, "
                "and it must make a Wisdom save to move more than 30 feet away from you. "
                "Concentration, up to 1 minute.",
    casting_time="1 bonus action", range="30 feet", components="V",
    save_ability="wis", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Create or Destroy Water", 1, SpellSchool.TRANSMUTATION,
    description="You either create or destroy water. Create: up to 10 gallons of clean water "
                "appears in an open container, or it falls as rain in a 30-foot cube. Destroy: "
                "up to 10 gallons of water in a 30-foot cube vanishes. Upcasting adds 10 gallons "
                "per slot level above 1st.",
    casting_time="1 action", range="30 feet", components="V, S, M"))
register_spell(Spell("Detect Evil and Good", 1, SpellSchool.DIVINATION,
    description="For the duration you sense the presence of aberrations, celestials, elementals, "
                "feys, fiends, and undead within 30 feet, and can identify consecrated or "
                "desecrated ground. Concentration, up to 10 minutes.",
    casting_time="1 action", range="self", components="V, S",
    concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Detect Poison and Disease", 1, SpellSchool.DIVINATION,
    description="For the duration you sense the presence and location of poisons, venomous "
                "creatures, and diseases within 30 feet. Ritual; concentration, up to 10 minutes.",
    casting_time="1 action", range="self", components="V, S, M",
    ritual=True, concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Expeditious Retreat", 1, SpellSchool.TRANSMUTATION,
    description="This spell allows you to move at an incredible pace. You can take the Dash "
                "action as a bonus action for the duration. Concentration, up to 10 minutes.",
    casting_time="1 bonus action", range="self", components="V, S",
    concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Feather Fall", 1, SpellSchool.TRANSMUTATION,
    description="Choose up to five falling creatures within range. Their rate of descent slows "
                "to 60 feet per round, and they take no falling damage and land on their feet. "
                "Duration 1 minute.",
    casting_time="1 reaction", range="60 feet", components="V",
    duration="1 minute"))
register_spell(Spell("Goodberry", 1, SpellSchool.TRANSMUTATION,
    description="Up to ten berries appear in your hand, infused with magic for 24 hours. A "
                "creature can use its action to eat one berry to restore 1 hit point; the berry "
                "also provides enough nourishment to sustain a creature for one day. Eating all "
                "ten berries restores 10 hit points total.",
    casting_time="1 action", range="self", components="V, S, M",
    healing_dice_count=10, healing_dice_sides=1, healing_bonus=0,
    duration="24 hours"))
register_spell(Spell("Heroism", 1, SpellSchool.ENCHANTMENT,
    description="A willing creature you touch is imbued with bravery. Until the spell ends, the "
                "creature is immune to being frightened and gains temporary hit points equal to "
                "your spellcasting ability modifier at the start of each of its turns. "
                "Concentration, up to 1 minute.",
    casting_time="1 action", range="touch", components="V, S",
    concentration=True, duration="up to 1 minute"))
register_spell(Spell("Jump", 1, SpellSchool.TRANSMUTATION,
    description="Touch a creature. For the duration, the target's jump distance is tripled. "
                "Duration 1 minute.",
    casting_time="1 action", range="touch", components="V, S, M",
    duration="1 minute"))
register_spell(Spell("Purify Food and Drink", 1, SpellSchool.TRANSMUTATION,
    description="All nonmagical food and drink within a 5-foot-radius sphere centered on a point "
                "within range is purified and freed of poison and disease. Ritual.",
    casting_time="1 action", range="10 feet", components="V, S",
    ritual=True))
register_spell(Spell("Silent Image", 1, SpellSchool.ILLUSION,
    description="You create the image of an object, creature, or other visible phenomenon that "
                "is no larger than a 15-foot cube. It is purely visual. A creature that uses its "
                "action to examine the image can determine it is an illusion with a successful "
                "Intelligence (Investigation) check against your spell save DC. Concentration, "
                "up to 10 minutes.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Tenser's Floating Disk", 1, SpellSchool.CONJURATION,
    description="A circular plane of force, 3 feet in diameter, floats 3 feet above the ground "
                "and follows you, carrying up to 500 pounds at your speed. The disk vanishes "
                "when the spell ends, dropping anything it carried. Ritual, 1 hour.",
    casting_time="1 action", range="10 feet", components="V, S, M",
    ritual=True, duration="1 hour"))
register_spell(Spell("Unseen Servant", 1, SpellSchool.CONJURATION,
    description="An invisible, mindless, shapeless force appears that performs simple tasks at "
                "your command — fetching, cleaning, holding items. It can't attack. It drops "
                "anything it holds when it moves more than 60 feet from you. Ritual, 1 hour.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    ritual=True, duration="1 hour"))
register_spell(Spell("Wrathful Smite", 1, SpellSchool.EVOCATION,
    description="The next time you hit with a melee weapon attack during this spell's duration, "
                "your attack deals an extra 1d6 psychic damage, and the target must succeed on "
                "a Wisdom save or become frightened of you until the spell ends. As an action, "
                "a frightened creature can make a Wisdom check against your spell save DC to "
                "steady itself and end the effect. Concentration, up to 1 minute.",
    casting_time="1 bonus action", range="self", components="V",
    concentration=True, duration="up to 1 minute"))

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
register_spell(Spell("Aid", 2, SpellSchool.ABJURATION,
    description="Up to three creatures' hit point maximum and current HP increase by 5 for 8 hours.",
    casting_time="1 action", range="30 feet", components="V, S, M",
    duration="8 hours"))
register_spell(Spell("Lesser Restoration", 2, SpellSchool.ABJURATION,
    description="Touch a creature to end one condition: blinded, deafened, paralyzed, poisoned, or stunned.",
    casting_time="1 action", range="touch", components="V, S"))
register_spell(Spell("Melf's Acid Arrow", 2, SpellSchool.EVOCATION,
    description="A shimmering arrow of acid. Ranged spell attack; 4d4 acid on a hit (2d4 on a miss).",
    casting_time="1 action", range="90 feet", components="V, S, M",
    requires_attack_roll=True, damage_dice_count=4, damage_dice_sides=4,
    damage_type="acid", at_higher_levels_dice=1))
register_spell(Spell("Enhance Ability", 2, SpellSchool.TRANSMUTATION,
    description="Touch a creature to grant advantage on one chosen ability's checks. Concentration.",
    casting_time="1 action", range="touch", components="V, S",
    concentration=True, duration="up to 1 hour"))

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
# NOTE: Thunderwave is a 1st-level evocation spell (registered above in the
# Level 1 section). A duplicate Level-3 registration was removed here; it had
# been silently overwriting the canonical Level-1 entry via the shared id key.
register_spell(Spell("Mass Healing Word", 3, SpellSchool.EVOCATION,
    description="Up to six creatures regain hit points as a bonus action.",
    casting_time="1 bonus action", range="60 feet", components="V",
    healing_dice_count=1, healing_dice_sides=4, healing_bonus=0,
    at_higher_levels_dice=1))
register_spell(Spell("Fear", 3, SpellSchool.ILLUSION,
    description="A phantasmal image terrifies creatures in a cone; they become frightened and drop items. Wis save. Concentration.",
    casting_time="1 action", range="self (30-foot cone)", components="V, S, M",
    save_ability="wis", concentration=True, duration="up to 1 minute"))

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
register_spell(Spell("Banishment", 4, SpellSchool.ABJURATION,
    description="Banish one creature to a harmless demiplane on a failed Wis save; extraplanar targets are sent home. Concentration.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    save_ability="wis", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Confusion", 4, SpellSchool.ENCHANTMENT,
    description="Beasts and humanoids in a 10-foot cube behave randomly; Wis save each turn. Concentration.",
    casting_time="1 action", range="90 feet", components="V, S, M",
    save_ability="wis", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Death Ward", 4, SpellSchool.ABJURATION,
    description="The next time the target would drop to 0 HP, it instead drops to 1 HP.",
    casting_time="1 action", range="touch", components="V, S",
    duration="8 hours"))
register_spell(Spell("Dominate Beast", 4, SpellSchool.ENCHANTMENT,
    description="Telepathically control a beast's actions; Wis save to resist. Concentration.",
    casting_time="1 action", range="60 feet", components="V, S",
    save_ability="wis", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Evard's Black Tentacles", 4, SpellSchool.CONJURATION,
    description="Rubbery tentacles grip a 20-foot square; Dex save or 3d6 bludgeoning and restrained. Concentration.",
    casting_time="1 action", range="90 feet", components="V, S, M",
    save_ability="dex", damage_dice_count=3, damage_dice_sides=6,
    damage_type="bludgeoning", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Freedom of Movement", 4, SpellSchool.ABJURATION,
    description="Target's movement ignores difficult terrain, magical restraint, and grappling for 1 hour.",
    casting_time="1 action", range="touch", components="V, S, M",
    duration="1 hour"))

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
register_spell(Spell("Dominate Person", 5, SpellSchool.ENCHANTMENT,
    description="Telepathically control a humanoid's actions; Wis save to resist. Concentration.",
    casting_time="1 action", range="60 feet", components="V, S",
    save_ability="wis", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Greater Restoration", 5, SpellSchool.ABJURATION,
    description="Touch a creature to end charm, petrification, or a curse, reduce exhaustion by one, or restore one reduced ability score.",
    casting_time="1 action", range="touch", components="V, S, M"))
register_spell(Spell("Insect Plague", 5, SpellSchool.CONJURATION,
    description="Biting locusts fill a 20-foot radius; Con save or 4d10 piercing damage. Concentration.",
    casting_time="1 action", range="300 feet", components="V, S, M",
    save_ability="con", damage_dice_count=4, damage_dice_sides=10,
    damage_type="piercing", concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Mass Cure Wounds", 5, SpellSchool.EVOCATION,
    description="Up to six creatures regain 3d8 HP. Upcast adds 1d8 per slot level.",
    casting_time="1 action", range="60 feet", components="V, S",
    healing_dice_count=3, healing_dice_sides=8,
    at_higher_levels_dice=1))
register_spell(Spell("Wall of Force", 5, SpellSchool.EVOCATION,
    description="An indestructible wall of invisible force shapes the battlefield; nothing physical or magical passes through. Concentration.",
    casting_time="1 action", range="120 feet", components="V, S, M",
    concentration=True, duration="up to 10 minutes"))

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
register_spell(Spell("Circle of Death", 6, SpellSchool.NECROMANCY,
    description="Sphere of negative energy sweeps out; Con save or 8d6 necrotic. Upcast adds 2d6 per slot level.",
    casting_time="1 action", range="150 feet", components="V, S, M",
    save_ability="con", damage_dice_count=8, damage_dice_sides=6,
    damage_type="necrotic", at_higher_levels_dice=2))
register_spell(Spell("Harm", 6, SpellSchool.NECROMANCY,
    description="A torrent of necrotic energy; Con save or 14d6 necrotic and the target's HP maximum is reduced by the damage taken.",
    casting_time="1 action", range="60 feet", components="V, S",
    save_ability="con", damage_dice_count=14, damage_dice_sides=6,
    damage_type="necrotic"))
register_spell(Spell("Heroes' Feast", 6, SpellSchool.CONJURATION,
    description="A feast cures all diseases and poison, and grants +2d10 max HP, immunity to poison and fright, and advantage on Wisdom saves for 24 hours.",
    casting_time="10 minutes", range="30 feet", components="V, S, M",
    duration="24 hours"))
register_spell(Spell("Otto's Irresistible Dance", 6, SpellSchool.ENCHANTMENT,
    description="The target is compelled to dance; there is no save on cast. It has disadvantage on attacks and Dexterity saves while you concentrate, and it may use its action to re-save (Wis) each turn. Concentration.",
    casting_time="1 action", range="30 feet", components="V",
    save_ability="wis", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Wall of Ice", 6, SpellSchool.EVOCATION,
    description="A wall of ice forms to block the battlefield; a shattered section bursts for 10d6 cold damage (Dex save for half). Concentration.",
    casting_time="1 action", range="120 feet", components="V, S, M",
    save_ability="dex", damage_dice_count=10, damage_dice_sides=6,
    damage_type="cold", concentration=True, duration="up to 10 minutes"))

# Level 6 PHB completion — 19 iconic spells rounding the tier to 31/31
# (every Player's Handbook 6th-level spell now registered). Mirrors the level
# 1 / 7 / 8 / 9 PHB-completion runs: damage spells use the standard dice+save
# path, save-debuff spells use save-ability-with-effects-in-description, and
# utility/buff spells resolve cleanly via the "takes effect" path.
# Damage / save-for-half
register_spell(Spell("Blade Barrier", 6, SpellSchool.EVOCATION,
    description="A wall of blades forms in a 100-ft line; creatures in the wall when it appears or ending their turn there take 6d10 slashing (Dex save for half). Concentration.",
    casting_time="1 action", range="90 feet", components="V, S",
    save_ability="dex", damage_dice_count=6, damage_dice_sides=10,
    damage_type="slashing", concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Otiluke's Freezing Sphere", 6, SpellSchool.EVOCATION,
    description="A frigid globe bursts on impact; creatures in a 60-ft radius sphere take 10d6 cold damage (Dex save for half). Upcast adds 1d6 per slot level.",
    casting_time="1 action", range="300 feet", components="V, S, M",
    save_ability="dex", damage_dice_count=10, damage_dice_sides=6,
    damage_type="cold", at_higher_levels_dice=1))
register_spell(Spell("Wall of Thorns", 6, SpellSchool.CONJURATION,
    description="A wall of tough, tangled brush bristling with daggers-like thorns forms on the ground; a creature inside the wall or that enters it takes 7d8 slashing damage (Dex save for half). Upcast adds 1d8 per slot level. Concentration.",
    casting_time="1 action", range="120 feet", components="V, S, M",
    save_ability="dex", damage_dice_count=7, damage_dice_sides=8,
    damage_type="slashing", concentration=True, at_higher_levels_dice=1,
    duration="up to 10 minutes"))
# Save-debuff (no damage) — effects documented in the description
register_spell(Spell("Eyebite", 6, SpellSchool.NECROMANCY,
    description="Your eyes become an inky void; for the duration, as an action on each of your turns you can target one creature within 60 ft that you can see — it must make a Wisdom save or suffer one of three effects of your choice: Asleep (falls unconscious, wakes on damage or an action to shake them), Sickened (poisoned), or Panicked (frightened and must use its action to Dash away from you). Concentration.",
    casting_time="1 action", range="self", components="V, S",
    save_ability="wis", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Magic Jar", 6, SpellSchool.NECROMANCY,
    description="Your body falls unconscious and your soul moves into a tiny container within range. While in the jar you can sense surroundings and, as an action, project your soul to try to possess a humanoid within 100 ft — the target must make a Charisma save or be possessed (you control its body; your body remains unconscious). You can return to the jar (or your body if within 100 ft) as an action. If the container is destroyed when your soul is not in it, you die; if your body is destroyed, you can possess targets indefinitely but cannot return to your original body.",
    casting_time="1 minute", range="self (100 feet)", components="V, S, M",
    save_ability="cha", duration="until dispelled"))
register_spell(Spell("Mass Suggestion", 6, SpellSchool.ENCHANTMENT,
    description="You suggest a course of activity (limited to a sentence or two) to up to twelve creatures you can see within range; targets that fail a Wisdom save pursue the suggested course as best they can. The suggestion must sound reasonable; failing that, the spell ends for that target. Upcasting extends the duration (1 day at 7th, 10 days at 8th, 30 days at 9th, a year and a day at 10th+). Concentration.",
    casting_time="1 action", range="60 feet", components="V, M",
    save_ability="wis", concentration=True, duration="up to 24 hours"))
# Utility / buff / ritual / summon — resolve via the "takes effect" path
register_spell(Spell("Arcane Gate", 6, SpellSchool.CONJURATION,
    description="You create two linked portals, each a 10-ft circle, anywhere within range; a creature or object entering one portal exits the other. The portals persist for the duration. Concentration.",
    casting_time="1 action", range="500 feet", components="V, S",
    concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Conjure Fey", 6, SpellSchool.CONJURATION,
    description="You summon a fey creature of challenge rating 6 or lower (your choice), which appears in an unoccupied space within range and is friendly to you and your companions. It obeys your verbal commands and vanishes when it drops to 0 HP or when the spell ends. Upcasting summons a single fey of higher CR or multiple lower-CR fey. Concentration.",
    casting_time="1 action", range="90 feet", components="V, S, M",
    concentration=True, duration="up to 1 hour"))
register_spell(Spell("Contingency", 6, SpellSchool.EVOCATION,
    description="Choose a spell of 5th level or lower that you can cast, with a casting time of 1 action, that targets you. You cast that spell as part of casting contingency, specifying a triggering condition. The chosen spell takes effect when the trigger occurs; contingency then ends. You can have only one contingency active at a time.",
    casting_time="10 minutes", range="self", components="V, S, M",
    duration="10 days"))
register_spell(Spell("Create Undead", 6, SpellSchool.NECROMANCY,
    description="You can cast this spell only at night. You raise up to three ghouls (your choice of one or more) from corpses or remains within range; they are under your control for the duration and obey your commands. Upcasting animates additional or stronger undead (ghasts at 8th level, wights at 9th).",
    casting_time="1 minute", range="10 feet", components="V, S, M",
    duration="instantaneous"))
register_spell(Spell("Drawmij's Instant Summons", 6, SpellSchool.CONJURATION,
    description="You touch an object weighing 10 pounds or less that can be carried. The spell leaves an arcane mark on it (invisible to others) and for the next month you can use an action to speak a command word and summon it to your hand from anywhere on the same plane, unless it is being held or carried by another creature (you learn who holds it). Ritual.",
    casting_time="1 action", range="touch", components="V, S, M",
    ritual=True, duration="1 month"))
register_spell(Spell("Find the Path", 6, SpellSchool.DIVINATION,
    description="You describe or name a location that you have previously visited, or a well-known landmark, and the spell grants you knowledge of the most direct, shortest route to it by the most efficient means of travel. The spell ends when you arrive or the duration expires. Concentration.",
    casting_time="1 minute", range="self", components="V, S, M",
    concentration=True, duration="until discharged"))
register_spell(Spell("Guards and Wards", 6, SpellSchool.ABJURATION,
    description="You ward a multi-story structure (up to 2,500 sq ft per floor, up to 5 floors) with a web of protective magic: corridors fill with fog, doors become magical (arcane lock + the door appears as a plain wall), a stairwell reverses direction, a study fills with a fire-themed illusion, and a wraith-like image challenges intruders. Each effect lasts for the duration.",
    casting_time="10 minutes", range="touch", components="V, S, M",
    duration="24 hours"))
register_spell(Spell("Move Earth", 6, SpellSchool.TRANSMUTATION,
    description="Choose an area of terrain no larger than 40 feet on a side within range. You can reshape dirt (but not solid rock or ice) into any shape — excavate a trench, raise a rampart, form a 20-ft-deep pit, etc. The changes occur gradually over the casting time. A creature in the area when the spell is cast can move out of the way.",
    casting_time="2 hours", range="120 feet", components="V, S, M",
    duration="instantaneous"))
register_spell(Spell("Planar Ally", 6, SpellSchool.CONJURATION,
    description="You utter a divine plea to a power of your choice, requesting the aid of a celestial, elemental, or fiend (your choice). The entity appears within range and bargains with you for service in exchange for payment; if you reach terms, it serves for the agreed task and duration (up to days). The being returns to its home plane when the task is done or the bargain is broken.",
    casting_time="10 minutes", range="60 feet", components="V, S",
    duration="instantaneous"))
register_spell(Spell("Programmed Illusion", 6, SpellSchool.ILLUSION,
    description="You create the illusion of an object, creature, or other visible phenomenon up to a 30-ft cube, performing a script you design (no longer than 10 minutes). The illusion triggers when a creature you specify enters the area; that creature perceives it as real (an Investigation check against your spell save DC reveals it as an illusion). The illusion vanishes when no creature is in the area, then resets to trigger again.",
    casting_time="1 action", range="120 feet", components="V, S, M",
    duration="until dispelled"))
register_spell(Spell("Transport via Plants", 6, SpellSchool.CONJURATION,
    description="You create a magical link between a Large or larger inanimate plant within range and another plant (of any size) on the same plane of existence that you have seen or touched within the last 24 hours. Any creature can step into the first plant and exit through the second; the portal closes after the spell ends.",
    casting_time="1 action", range="10 feet", components="V, S",
    duration="1 round"))
register_spell(Spell("Wind Walk", 6, SpellSchool.TRANSMUTATION,
    description="You and up to ten willing creatures you can see within range transform into a cloud of mist and gain a flying speed of 300 feet for the duration. You can change back to your normal form as an action, ending the spell for those who do; while in cloud form you have resistance to nonmagical weapon damage and advantage on Strength, Dexterity, and Constitution saves. Reverting to normal form takes 6 seconds (1 round).",
    casting_time="1 minute", range="30 feet", components="V, S, M",
    duration="up to 8 hours"))
register_spell(Spell("Word of Recall", 6, SpellSchool.CONJURATION,
    description="You and up to five willing creatures within 5 feet of you instantly teleport to a designated sanctuary you have previously prepared for this spell (typically a temple or stronghold attuned to your deity). The teleportation is error-free; arriving creatures appear in the nearest unoccupied space to the sanctuary's mark.",
    casting_time="1 action", range="5 feet", components="V",
    duration="instantaneous"))

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
register_spell(Spell("Delayed Blast Fireball", 7, SpellSchool.EVOCATION,
    description="A glowing bead grows in power as it waits; on detonation, Dex save or 12d6 fire (it gains 1d6 each round it waits). Upcast adds 1d6 per slot level. Concentration.",
    casting_time="1 action", range="150 feet", components="V, S, M",
    save_ability="dex", damage_dice_count=12, damage_dice_sides=6,
    damage_type="fire", concentration=True, at_higher_levels_dice=1,
    duration="up to 1 minute"))
register_spell(Spell("Prismatic Spray", 7, SpellSchool.EVOCATION,
    description="Eight multicolored rays spray from your hands; each target rolls a d8 for an effect (typically 8d6 damage of a random type: acid/cold/fire/lightning/poison). Dex save for half.",
    casting_time="1 action", range="self (60-foot cone)", components="V, S",
    save_ability="dex", damage_dice_count=8, damage_dice_sides=6,
    damage_type="acid"))
register_spell(Spell("Resurrection", 7, SpellSchool.NECROMANCY,
    description="Return a dead creature to life with full hit points; the spell also cures any conditions afflicting the corpse.",
    casting_time="1 hour", range="touch", components="V, S, M"))
register_spell(Spell("Reverse Gravity", 7, SpellSchool.TRANSMUTATION,
    description="Objects and creatures in a 50-foot cylinder fall upward for the duration; creatures take falling damage when the spell ends. Dex save to cling to something fixed. Concentration.",
    casting_time="1 action", range="100 feet", components="V, S, M",
    save_ability="dex", concentration=True, duration="up to 1 minute"))

# Level 7 PHB completion — 7 iconic spells rounding the tier to 18/18.
# (Divine Word, Etherealness, Mordenkainen's Magnificent Mansion,
#  Mordenkainen's Sword, Project Image, Sequester, Symbol.)
register_spell(Spell("Divine Word", 7, SpellSchool.ABJURATION,
    description="You utter a divine word; each hostile creature of your choice you can hear within range suffers an effect by current HP — 20 or fewer dies, 21-30 stunned 1 minute, 31-40 blinded and deafened 1 minute, 41-50 deafened 1 minute (no save; no effect on creatures above 50 HP). Celestials, elementals, fey, and fiends within range are banished to their home plane if they fail a Charisma save. No save applies to the HP-tiered effects.",
    casting_time="1 action", range="60 feet", components="V",
    save_ability="cha", duration="instantaneous"))
register_spell(Spell("Etherealness", 7, SpellSchool.TRANSMUTATION,
    description="You step into the Border Ethereal for the duration, able to move through the material plane and unseen by those on it. You can end the spell early, and it ends if you cast a spell or make an attack.",
    casting_time="1 action", range="self", components="V, S",
    duration="up to 8 hours"))
register_spell(Spell("Mordenkainen's Magnificent Mansion", 7, SpellSchool.CONJURATION,
    description="A shimmering portal opens to a sprawling extradimensional mansion furnished and staffed to your taste; up to a chosen number of creatures may enter and take a short or long rest in safety. The mansion vanishes and its guests are expelled when the spell ends.",
    casting_time="1 action", range="300 feet", components="V, S, M",
    duration="24 hours"))
register_spell(Spell("Mordenkainen's Sword", 7, SpellSchool.EVOCATION,
    description="A luminous blade of force springs into being and hovers near you. On each of your turns for the duration you can use a bonus action to move it and make one melee spell attack against a creature within 5 feet of it, dealing 3d10 force damage on a hit. Concentration.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    requires_attack_roll=True, damage_dice_count=3, damage_dice_sides=10,
    damage_type="force", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Project Image", 7, SpellSchool.ILLUSION,
    description="You create an illusory copy of yourself that can appear anywhere within range. Through its senses you can see, hear, and speak as though you stood in its space, and you can cast spells as if you were there; the image is intangible and vanishes if a creature uses an action to determine it is an illusion. Concentration.",
    casting_time="1 action", range="500 miles", components="V, S, M",
    concentration=True, duration="up to 1 day"))
register_spell(Spell("Sequester", 7, SpellSchool.TRANSMUTATION,
    description="You hide a willing creature or an object in a pocket dimension, suspended in time and unreachable by any means, until you use an action to release it or the spell is dispelled. The target does not age and is unaware of passing time.",
    casting_time="1 action", range="touch", components="V, S, M",
    duration="until dispelled"))
register_spell(Spell("Symbol", 7, SpellSchool.ABJURATION,
    description="Over an hour you inscribe a potent rune onto a surface and set a trigger; when activated, creatures in the area make a saving throw. Default glyph is a Con save (Death: 10d10 necrotic on a failed save, half on success). Variants and their saves: Discord (Con), Fear (Wis), Hopelessness (Cha), Insanity (Int), Pain (Con), Sleep (Wis), Stunning (Wis). No concentration; lasts until triggered or dispelled.",
    casting_time="1 hour", range="touch", components="V, S, M",
    save_ability="con", duration="until dispelled or triggered"))

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
register_spell(Spell("Antimagic Field", 8, SpellSchool.ABJURATION,
    description="A 10-foot sphere suppresses all magic — spells, magical effects, and magical items — within it. Concentration.",
    casting_time="1 action", range="self (10-foot radius)", components="V, S, M",
    concentration=True, duration="up to 1 hour"))
register_spell(Spell("Incendiary Cloud", 8, SpellSchool.CONJURATION,
    description="A swirling cloud of fire roils across the battlefield; Dex save or 8d6 fire each round. Concentration.",
    casting_time="1 action", range="150 feet", components="V, S",
    save_ability="dex", damage_dice_count=8, damage_dice_sides=6,
    damage_type="fire", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Mind Blank", 8, SpellSchool.ABJURATION,
    description="The target is immune to psychic damage and its mind cannot be read by any means for 24 hours.",
    casting_time="1 action", range="touch", components="V, S",
    duration="24 hours"))

# Level 8 PHB completion — 8 iconic spells rounding the tier to 18/18.
# (Animal Shapes, Antipathy/Sympathy, Clone, Control Weather, Demiplane,
#  Glibness, Holy Aura, Telepathy.)
register_spell(Spell("Animal Shapes", 8, SpellSchool.TRANSMUTATION,
    description="Choose any number of willing creatures within range; each transforms into a beast of challenge rating 4 or lower of your choice, gaining its game statistics while retaining alignment and personality. You can use an action on later turns to transform them again. Concentration.",
    casting_time="1 action", range="30 feet", components="V, S",
    concentration=True, duration="up to 24 hours"))
register_spell(Spell("Antipathy/Sympathy", 8, SpellSchool.ENCHANTMENT,
    description="Over an hour you cause a target to attract or repel a chosen kind of intelligent creature. Creatures of the chosen kind that come within 60 feet of the target must make a Wisdom save: on a failure they are charmed (sympathy) or frightened (antipathy) by it while they remain in range and cannot approach. The effect lasts until the spell ends or is dispelled; no concentration.",
    casting_time="1 hour", range="60 feet", components="V, S, M",
    save_ability="wis", duration="10 days"))
register_spell(Spell("Clone", 8, SpellSchool.NECROMANCY,
    description="Over an hour you grow a duplicate of a living creature in a sealed vessel. When that creature dies, its soul transfers to the clone, which awakens as a full copy of the original at the time the flesh was taken. The original body crumbles to dust.",
    casting_time="1 hour", range="touch", components="V, S, M",
    duration="indefinite"))
register_spell(Spell("Control Weather", 8, SpellSchool.TRANSMUTATION,
    description="You alter the weather in a 5-mile radius centered on you for the duration, raising or lowering temperature, clearing or bringing precipitation, and changing wind one stage per round. Concentration.",
    casting_time="10 minutes", range="self (5 miles)", components="V, S, M",
    concentration=True, duration="up to 8 hours"))
register_spell(Spell("Demiplane", 8, SpellSchool.CONJURATION,
    description="A shadowy door appears on a flat surface, opening onto an empty 30-foot-cubic demiplane that lasts for the duration; objects and willing creatures can pass through. Each casting of demiplane links to a different demiplane unless you consciously recall one you have created before.",
    casting_time="1 action", range="60 feet", components="S",
    duration="1 hour"))
register_spell(Spell("Glibness", 8, SpellSchool.TRANSMUTATION,
    description="For the duration you can replace any Charisma check or attack roll result lower than 15 with a 15, and magic that would discern whether you are telling the truth reveals that you believe your lies. Self-buff; no save.",
    casting_time="1 action", range="self", components="V",
    duration="1 hour"))
register_spell(Spell("Holy Aura", 8, SpellSchool.ABJURATION,
    description="Divine light surrounds you in a 30-foot aura for the duration: you and allied creatures have advantage on all saving throws, and other creatures have disadvantage on attack rolls against you. Fiends and undead that hit an ally in the aura with a melee attack must make a Constitution save or be blinded. Concentration.",
    casting_time="1 action", range="self (30-foot radius)", components="V, S, M",
    save_ability="con", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Telepathy", 8, SpellSchool.EVOCATION,
    description="For 24 hours, you and a willing creature you touch can communicate telepathically through a private link, sharing words, images, and sounds across any distance on the same plane.",
    casting_time="1 action", range="unlimited", components="V, S, M",
    duration="24 hours"))

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
register_spell(Spell("Mass Heal", 9, SpellSchool.EVOCATION,
    description="Up to 700 hit points of healing spread among any creatures in range; the spell also cures blindness, deafness, and diseases.",
    casting_time="1 action", range="60 feet", components="V, S",
    healing_dice_count=0, healing_dice_sides=0, healing_bonus=700))
register_spell(Spell("Prismatic Wall", 9, SpellSchool.EVOCATION,
    description="A shimmering multicolored wall blinds creatures within 20 feet and deals 10d6 fire plus 10d6 radiant (modeled here as 20d6 fire) to anything passing through; Dex save for half.",
    casting_time="1 action", range="60 feet", components="V, S",
    save_ability="dex", damage_dice_count=20, damage_dice_sides=6,
    damage_type="fire", duration="10 minutes"))
register_spell(Spell("Astral Projection", 9, SpellSchool.NECROMANCY,
    description="You and up to eight willing creatures project your astral bodies onto the Astral Plane, leaving your physical bodies behind in suspended animation. Astral forms can travel to other planes; if an astral form drops to 0 HP it (and the caster's body) returns to the physical form. Costs material components for each creature.",
    casting_time="1 hour", range="10 feet", components="V, S, M",
    duration="until dispelled"))
register_spell(Spell("Gate", 9, SpellSchool.CONJURATION,
    description="A 5-to-20-foot circular portal opens to another plane of existence, allowing two-way travel for the duration. If you know a specific creature's true name, you can direct the gate to create a portal in front of it and pull it through (the target may resist with a Cha save).",
    casting_time="1 action", range="60 feet", components="V, S, M",
    concentration=True, duration="up to 1 minute"))
register_spell(Spell("Imprisonment", 9, SpellSchool.ABJURATION,
    description="You bind a creature with one of six prisons until dispelled: burial (Str save, entombed in earth), chaining (Dex save, bound in chains), hedged prison (Wis save, walled in a tiny sphere), minimus containment (Dex save, shrunk into a gem), slumber (Wis save, eternal sleep), or appearing (no save, banished to a demiplane). The save shown is the default burial version. A special component releases the target.",
    casting_time="1 action", range="30 feet", components="V, S, M",
    save_ability="str", duration="until dispelled"))
register_spell(Spell("Shapechange", 9, SpellSchool.TRANSMUTATION,
    description="You assume the form of a different creature (Challenge Rating no greater than your level) for the duration, gaining its game statistics while keeping your alignment, personality, and class features. You can use an action to adopt a new eligible form. If you drop to 0 HP, the spell ends. Concentration.",
    casting_time="1 action", range="self", components="V, S, M",
    concentration=True, duration="up to 1 hour"))
register_spell(Spell("Storm of Vengeance", 9, SpellSchool.CONJURATION,
    description="A churning storm cloud forms and escalates over the duration: round 1 deals thunder damage and deafens; round 2 rains acid; round 3 pelts cold hail; round 4 brings bludgeoning debris that restrains; rounds 5-10 unleash 10d6 lightning each round (modeled here as the signature 10d6 lightning strike, Con save for half). Concentration.",
    casting_time="1 action", range="self (360-foot radius)", components="V, S",
    save_ability="con", damage_dice_count=10, damage_dice_sides=6,
    damage_type="lightning", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Weird", 9, SpellSchool.ILLUSION,
    description="Tentacles of doomy illusion fill a 30-foot sphere; each creature makes a Wisdom save or takes 4d8 psychic damage and is frightened, and must use its action to Dash away from the illusion. A creature repeats the save at the end of each of its turns, taking 4d8 psychic on a failure. Concentration.",
    casting_time="1 action", range="120 feet", components="V, S, M",
    save_ability="wis", damage_dice_count=4, damage_dice_sides=8,
    damage_type="psychic", concentration=True, duration="up to 1 minute"))


# ---------------------------------------------------------------------------
# Starting spells per class (level 1): cantrips + known/prepared level 1 spells.
# ---------------------------------------------------------------------------

STARTING_SPELLS = {
    "wizard": {
        "cantrips": ["fire_bolt", "light", "mage_hand"],
        "spells": ["magic_missile", "burning_hands", "detect_magic", "shield_of_faith",
                   "shield", "mage_armor"],
    },
    "sorcerer": {
        "cantrips": ["fire_bolt", "ray_of_frost", "acid_splash"],
        "spells": ["magic_missile", "burning_hands", "chromatic_orb", "shield"],
    },
    "cleric": {
        "cantrips": ["sacred_flame", "light", "mage_hand"],
        "spells": ["cure_wounds", "healing_word", "guiding_bolt", "shield_of_faith", "bless"],
    },
    "druid": {
        "cantrips": ["acid_splash", "minor_illusion", "light"],
        "spells": ["cure_wounds", "entangle", "healing_word", "faerie_fire"],
    },
    "bard": {
        "cantrips": ["vicious_mockery", "minor_illusion", "light"],
        "spells": ["healing_word", "sleep", "charm_person"],
    },
    "warlock": {
        "cantrips": ["eldritch_blast", "mage_hand", "minor_illusion"],
        "spells": ["hex", "burning_hands"],
    },
    "paladin": {
        "cantrips": [],
        "spells": ["cure_wounds", "shield_of_faith", "command"],
    },
    "ranger": {
        "cantrips": [],
        "spells": ["cure_wounds", "entangle", "hunter's_mark"],
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


def resolve_spell_aoe_target(
    spell: Spell,
    slot_level: Optional[int],
    full_damage: int,
    target_save_total: Optional[int],
    spell_save_dc: Optional[int] = None,
) -> SpellEffectResult:
    """Resolve ONE AoE target's outcome against a shared damage roll.

    Per PHB p.204, an AoE spell's damage is rolled **once** and every target
    saves against that same damage. This helper takes the already-rolled
    ``full_damage`` (rolled once by the caller) and a single target's save
    total, and returns that target's outcome:

    - **Save spell** (``spell.save_ability`` set): if ``target_save_total`` is
      provided, ``made_save = total >= DC``; on a save the target takes half
      (``full_damage // 2``), otherwise full. If no save total is provided,
      full damage is applied (no save rolled).
    - **Auto-damage spell** (no save, e.g. an AoE that deals damage with no
      roll): full damage to every target.
    - **Non-damage AoE** (e.g. an area debuff): zero damage; ``made_save`` set
      when a save total is provided.

    Attack-roll AoE is not supported here (rare; callers should use
    :func:`resolve_spell_effect` per target instead). ``slot_level`` is the
    level the spell was actually cast at (used only for the result record).

    Args:
        spell: The spell being cast.
        slot_level: The slot level used for the cast (record-keeping only).
        full_damage: The damage rolled once for the whole AoE.
        target_save_total: This target's d20 + save mod (+ proficiency).
        spell_save_dc: The save DC. If omitted, the caller must supply a real
            DC (this helper does not know the caster's proficiency/mod).
    """
    slot_level = slot_level if slot_level is not None else spell.level
    damage_type = spell.damage_type

    # ----- Saving-throw AoE (the common case: Fireball, Shatter, etc.) -----
    if spell.save_ability is not None:
        made_save: Optional[bool] = None
        if target_save_total is not None and spell_save_dc is not None:
            made_save = target_save_total >= spell_save_dc
        if spell.deals_damage:
            if made_save is None:
                damage = full_damage
                half = False
                note = "(no save provided — full damage)"
            elif made_save:
                damage = full_damage // 2
                half = True
                note = f"saved (DC {spell_save_dc}) — half damage"
            else:
                damage = full_damage
                half = False
                note = f"failed save (DC {spell_save_dc})"
            return SpellEffectResult(
                spell_name=spell.name, slot_level=slot_level,
                rolled_attack=None, hit=None, made_save=made_save,
                damage=damage, healing=0, damage_type=damage_type,
                half_damage=half,
                description=f"{spell.name} deals {damage} {damage_type} damage {note}.",
            )
        # Save AoE with no damage (e.g. Stinking Cloud) — success/failure only.
        return SpellEffectResult(
            spell_name=spell.name, slot_level=slot_level,
            rolled_attack=None, hit=None, made_save=made_save,
            damage=0, healing=0, damage_type="", half_damage=False,
            description=f"{spell.name} resolved (save vs DC {spell_save_dc}).",
        )

    # ----- Auto-damage AoE (no save, no attack roll) -----------------------
    if spell.deals_damage:
        return SpellEffectResult(
            spell_name=spell.name, slot_level=slot_level,
            rolled_attack=None, hit=None, made_save=None,
            damage=full_damage, healing=0, damage_type=damage_type,
            half_damage=False,
            description=f"{spell.name} deals {full_damage} {damage_type} damage automatically.",
        )

    # ----- Non-damage AoE (utility / debuff area) --------------------------
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
        active_conditions: Optional[list[str]] = None,
    ) -> CastOutcome:
        """Attempt to cast a spell, consuming a slot if needed.

        Returns a CastOutcome whose ``effect`` (if not None) can be applied to a
        target by the caller (combat engine / API).

        Args:
            active_conditions: List of active condition names (e.g., ['stunned', 'grappled'])
                that may prevent spellcasting due to component restrictions.
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

        # Check component restrictions
        conditions = active_conditions or []
        can_cast, reason = can_cast_with_conditions(spell.parsed_components, conditions)
        if not can_cast:
            return CastOutcome(False, reason)

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

    def prepare_cast(
        self,
        spell_id: str,
        slot_level: Optional[int] = None,
        active_conditions: Optional[list[str]] = None,
    ) -> CastOutcome:
        """Validate + consume a spell slot WITHOUT resolving the effect.

        This is the AoE companion to :meth:`cast`: it performs the exact same
        validation and slot-consumption as the front half of ``cast``, but
        does NOT call :func:`resolve_spell_effect`. The returned
        :class:`CastOutcome` carries ``spell`` + ``slot_level`` (and
        ``effect=None``); the caller then resolves the effect once per target
        (e.g. via :func:`resolve_spell_aoe_target`), so that one slot feeds N
        independent per-target saving throws.

        Failure modes are identical to ``cast``: unknown spell, non-caster,
        not known/prepared, component-blocked by an active condition, or no
        spell slots available → ``CastOutcome(success=False, message=...)``
        and NO slot is consumed.

        Args:
            spell_id: Spell id or name (e.g. ``"fireball"``).
            slot_level: Desired slot level for upcasting (``None`` = auto).
            active_conditions: Caster's conditions (may block V/S components).

        Returns:
            A CastOutcome. On success ``effect`` is None and ``slot_level`` is
            the level actually expended (0 for cantrips).
        """
        sid = _norm(spell_id)
        spell = get_spell(sid)
        if spell is None:
            return CastOutcome(False, f"Unknown spell: {spell_id}")
        if not self.is_caster:
            return CastOutcome(False, f"{self.char_class} cannot cast spells")
        if spell not in self.castable_spells():
            return CastOutcome(
                False,
                f"{spell.name} is not available to cast (not known/prepared)",
            )

        # Check component restrictions (same as cast()).
        conditions = active_conditions or []
        can_cast, reason = can_cast_with_conditions(spell.parsed_components, conditions)
        if not can_cast:
            return CastOutcome(False, reason)

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

        return CastOutcome(
            success=True,
            message=f"{spell.name} prepared.",
            effect=None,
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
