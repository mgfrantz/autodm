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

# Additional iconic PHB cantrips — PHB CANTRIP-TIER COMPLETION. Closes the
# catalogue's last remaining tier gap: every Player's Handbook cantrip is now
# registered (level 0: 14 -> 29). With all ten leveled tiers (1-9) already
# PHB-complete, this completes the PHB spell catalogue at EVERY tier (0-9).
# The 15 additions cover all three cantrip resolution paths:
# - Attack-roll cantrips (Produce Flame, Thorn Whip): damage scales
#   automatically via cantrip_dice_multiplier at caster levels 5/11/17.
# - Utility / buff cantrips (13 spells): no dice modelled; effects documented
#   per PHB. Concentration set only where PHB specifies (Dancing Lights,
#   Guidance, Resistance, True Strike).
#
# Attack-roll cantrips (damage, with automatic cantrip scaling at 5/11/17):
register_spell(Spell("Produce Flame", 0, SpellSchool.CONJURATION,
    description="A flickering flame appears in your hand; it sheds bright light in "
                "a 10-foot radius and dim light for 10 feet more. You may hurl it as "
                "a ranged spell attack (thrown 30 feet) for 1d8 fire damage. The "
                "flame harms nothing else and goes out if you cast it again or dismiss "
                "it as an action.",
    casting_time="1 action", range="self (thrown 30 feet)", components="V, S",
    requires_attack_roll=True, damage_dice_count=1, damage_dice_sides=8,
    damage_type="fire"))
register_spell(Spell("Thorn Whip", 0, SpellSchool.TRANSMUTATION,
    description="A vine-like whip of thorns lashes out at a creature. Melee spell "
                "attack for 1d6 piercing damage; if the target is Large or smaller, "
                "you pull it up to 10 feet closer to you.",
    casting_time="1 action", range="30 feet", components="V, S, M",
    material_description="the stem of a plant with thorns",
    requires_attack_roll=True, damage_dice_count=1, damage_dice_sides=6,
    damage_type="piercing"))

# Utility / buff cantrips (no damage; effects documented per PHB):
register_spell(Spell("Blade Ward", 0, SpellSchool.ABJURATION,
    description="You extend your hand and trace a warding sigil. Until the end of "
                "your next turn, you have resistance against bludgeoning, piercing, "
                "and slashing damage from weapon attacks.",
    casting_time="1 action", range="self", components="V, S",
    duration="1 round"))
register_spell(Spell("Dancing Lights", 0, SpellSchool.EVOCATION,
    description="You create up to four torch-sized lights within range that hover in "
                "the air, appear as glowing humanoid shapes, or mark Medium or smaller "
                "creatures. You can move them up to 60 feet as a bonus action. A light "
                "goes out if it leaves range. Concentration, up to 1 minute.",
    casting_time="1 action", range="120 feet", components="V, S, M",
    material_description="a bit of phosphorus or wychwood, or a glowworm",
    concentration=True, duration="up to 1 minute"))
register_spell(Spell("Druidcraft", 0, SpellSchool.TRANSMUTATION,
    description="Whispering to the spirits of nature, you create one of several minor "
                "effects: instantly light or snuff a candle, torch, or small campfire; "
                "predict the next day's weather; cause a blossom to sprout on a plant; "
                "or create a harmless sensory effect of leaves rustling.",
    casting_time="1 action", range="30 feet", components="V, S"))
register_spell(Spell("Friends", 0, SpellSchool.ENCHANTMENT,
    description="For the duration, your Charisma checks against one creature of your "
                "choice have advantage. When the spell ends, the creature realizes you "
                "used magic to influence its mood and becomes hostile toward you.",
    casting_time="1 action", range="self", components="S, M",
    material_description="a small amount of makeup applied to the face as this spell is cast",
    duration="1 minute"))
register_spell(Spell("Guidance", 0, SpellSchool.DIVINATION,
    description="You touch one willing creature. Once before the spell ends, the "
                "target can roll 1d4 and add the number rolled to one ability check "
                "of its choice. Concentration, up to 1 minute.",
    casting_time="1 action", range="touch", components="V, S",
    concentration=True, duration="up to 1 minute"))
register_spell(Spell("Mending", 0, SpellSchool.TRANSMUTATION,
    description="You repair a single break or tear in an object (such as a broken key, "
                "a torn cloak, or a leaking wineskin) no larger than 1 inch in any "
                "dimension, leaving no trace of the former damage.",
    casting_time="1 action", range="touch", components="V, S, M",
    material_description="two lodestones"))
register_spell(Spell("Message", 0, SpellSchool.TRANSMUTATION,
    description="You point toward a creature within range and whisper a message that "
                "only it can hear; the target may whisper a reply that only you hear. "
                "The spell travels around (but not through) solid objects.",
    casting_time="1 action", range="120 feet", components="V, S, M",
    material_description="a short piece of copper wire"))
register_spell(Spell("Prestidigitation", 0, SpellSchool.TRANSMUTATION,
    description="You create a minor magical effect: an instantaneous harmless sensory "
                "effect; light or snuff a candle/torch/small campfire; clean or soil "
                "an object no larger than 1 cubic foot; chill, warm, or flavor 1 cubic "
                "foot of nonliving material for 1 hour; or color, mark, or soil a "
                "small object for 1 hour.",
    casting_time="1 action", range="10 feet", components="V, S",
    duration="up to 1 hour"))
register_spell(Spell("Resistance", 0, SpellSchool.ABJURATION,
    description="You touch one willing creature. Once before the spell ends, the "
                "target can roll 1d4 and add the number rolled to one saving throw "
                "of its choice. Concentration, up to 1 minute.",
    casting_time="1 action", range="touch", components="V, S, M",
    material_description="a miniature cloak",
    concentration=True, duration="up to 1 minute"))
register_spell(Spell("Shillelagh", 0, SpellSchool.TRANSMUTATION,
    description="The wood of a club or quarterstaff you are holding is imbued with "
                "nature's power. For 1 minute the weapon becomes magical; you use your "
                "spellcasting ability for its attack and damage rolls; and its damage "
                "die becomes a d8 (d10 if wielded two-handed). The spell ends if you "
                "cast it again or let go of the weapon.",
    casting_time="1 bonus action", range="touch", components="V, S, M",
    material_description="mistletoe, a shamrock leaf, and a club or quarterstaff",
    duration="1 minute"))
register_spell(Spell("Spare the Dying", 0, SpellSchool.NECROMANCY,
    description="You touch a living creature that has 0 hit points. The creature "
                "becomes stable. This spell has no effect on undead or constructs.",
    casting_time="1 action", range="touch", components="V, S"))
register_spell(Spell("Thaumaturgy", 0, SpellSchool.TRANSMUTATION,
    description="You manifest a minor sign of supernatural power: your voice is thrice "
                "as loud for 1 minute; you cause flames to flicker, brighten, dim, or "
                "change color; you cause harmless tremors; you create an instantaneous "
                "sound; or you instantaneously open or close an unlocked door/window.",
    casting_time="1 action", range="30 feet", components="V",
    duration="up to 1 minute"))
register_spell(Spell("True Strike", 0, SpellSchool.DIVINATION,
    description="You extend your hand and point a finger at a target within range. "
                "Your next attack roll against that target before the end of your next "
                "turn has advantage. Concentration, up to 1 round.",
    casting_time="1 action", range="30 feet", components="S",
    concentration=True, duration="1 round"))

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

# Additional iconic PHB level-2 spells (expanding the tier toward PHB coverage).
# Mirrors the level-1 / level-6 PHB-completeness expansions: damage spells use
# the standard dice+save path, attack-roll spells use requires_attack_roll, and
# save-debuff / utility / buff / ritual spells resolve cleanly via the
# "takes effect" or save-only paths.
# Damage / save-for-half: Moonbeam (Con, 2d10 radiant, +1d10/slot).
# Attack-roll: Flame Blade (3d6 fire melee spell attack, +1d6/slot),
#   Spiritual Weapon (1d8 force + spellcasting mod, +1d8/slot).
# Direct damage (no attack roll, no save): Heat Metal (2d8 fire, +1d8/slot),
#   Spike Growth (2d4 piercing zone).
# Save-spell with damage: Phantasmal Force (Int save, 1d6 psychic).
register_spell(Spell("Moonbeam", 2, SpellSchool.EVOCATION,
    description="A silvery beam of pale light shines down in a 5-foot-radius, 40-foot-high "
                "cylinder centered on a point within range. Until the spell ends, dim light "
                "fills the cylinder. When a creature enters the spell's area for the first time "
                "on a turn or starts its turn there, it is engulfed in phantom flames that cause "
                "it to take 2d10 radiant damage on a failed Constitution save, or half as much on "
                "a successful one. A shapechanger makes its save with disadvantage. Upcasting adds "
                "1d10 per slot level above 2nd. Concentration.",
    casting_time="1 action", range="120 feet", components="V, S, M",
    save_ability="con", damage_dice_count=2, damage_dice_sides=10,
    damage_type="radiant", concentration=True, duration="up to 1 minute",
    at_higher_levels_dice=1))
register_spell(Spell("Flame Blade", 2, SpellSchool.EVOCATION,
    description="You evoke a fiery blade in your free hand. The blade is similar in size and "
                "shape to a scimitar, and it lasts for the duration. If you let go of the blade, "
                "it disappears, but you can evoke the blade again as a bonus action. You can use "
                "your action to make a melee spell attack with the fiery blade. On a hit, the "
                "target takes 3d6 fire damage. Upcasting adds 1d6 per slot level above 2nd. "
                "Concentration.",
    casting_time="1 bonus action", range="self", components="V, S, M",
    requires_attack_roll=True, damage_dice_count=3, damage_dice_sides=6,
    damage_type="fire", concentration=True, duration="up to 10 minutes",
    at_higher_levels_dice=1))
register_spell(Spell("Spiritual Weapon", 2, SpellSchool.EVOCATION,
    description="You create a floating, spectral weapon within range that lasts for the duration "
                "or until you cast this spell again. When you cast the spell, you can make a melee "
                "spell attack against a creature within 5 feet of the weapon. On a hit, the target "
                "takes force damage equal to 1d8 + your spellcasting ability modifier. As a bonus "
                "action on your turn, you can move the weapon up to 20 feet and repeat the attack "
                "against a creature within 5 feet of it. No concentration required. Upcasting adds "
                "1d8 per slot level above 2nd.",
    casting_time="1 bonus action", range="60 feet", components="V, S",
    requires_attack_roll=True, damage_dice_count=1, damage_dice_sides=8,
    damage_type="force", duration="1 minute", at_higher_levels_dice=1))
register_spell(Spell("Heat Metal", 2, SpellSchool.TRANSMUTATION,
    description="Choose a manufactured metal object within range that you can see, such as a metal "
                "weapon or a suit of metal armor. The object glows red-hot. Any creature in "
                "physical contact with the object takes 2d8 fire damage when you cast the spell. "
                "Until the spell ends, you can use a bonus action on each of your subsequent turns "
                "to deal this damage again, and the creature must use its reaction (if available) "
                "to drop the object if it can. If the creature is wearing the object and chooses "
                "not to drop it, it has disadvantage on attack rolls and ability checks until the "
                "spell ends. Upcasting adds 1d8 per slot level above 2nd. Concentration.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    damage_dice_count=2, damage_dice_sides=8, damage_type="fire",
    concentration=True, duration="up to 1 minute", at_higher_levels_dice=1))
register_spell(Spell("Spike Growth", 2, SpellSchool.TRANSMUTATION,
    description="The ground in a 20-foot radius centered on a point within range twists and sprouts "
                "hard spikes and thorns. The area becomes difficult terrain for the duration. When "
                "a creature moves into or within the area for the first time on a turn or starts its "
                "turn there, it takes 2d4 piercing damage. The transformation is camouflaged to "
                "look natural; a creature that can't see the area at the time the spell is cast must "
                "make a Wisdom (Perception) check against your spell save DC to recognize it as "
                "dangerous before entering. Concentration.",
    casting_time="1 action", range="150 feet", components="V, S, M",
    damage_dice_count=2, damage_dice_sides=4, damage_type="piercing",
    concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Phantasmal Force", 2, SpellSchool.ILLUSION,
    description="You craft an illusion that takes root in the mind of a creature you can see within "
                "range. The target must make an Intelligence saving throw. On a failed save, you "
                "create a phantasmal object, creature, or other visible phenomenon that is no "
                "larger than a 10-foot cube and perceivable only to the target for the duration. "
                "The phantasm includes sound, temperature, and other stimuli. While affected by the "
                "spell, the creature treats the phantasm as if it were real and rationalizes any "
                "illogical outcomes. The target can use its action to examine the phantasm with an "
                "Intelligence (Investigation) check against your spell save DC; if successful, the "
                "target realizes it is an illusion and the spell ends. While affected, the target "
                "takes 1d6 psychic damage per turn if subject to an attack or effect from the "
                "phantasm. Concentration.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    save_ability="int", damage_dice_count=1, damage_dice_sides=6,
    damage_type="psychic", concentration=True, duration="up to 1 minute"))
# Save-debuff (no damage) — effects documented in the description
register_spell(Spell("Crown of Madness", 2, SpellSchool.ENCHANTMENT,
    description="One humanoid of your choice that you can see within range must make a Wisdom saving "
                "throw. On a failed save, the target is charmed by you for the duration. While "
                "charmed, you have a psychic link with the target; you must use your action on each "
                "of your turns to keep the target under your control, issuing it a command to attack "
                "a creature other than itself that you choose. The target makes its first such "
                "attack before you issue the command on your next turn. Concentration.",
    casting_time="1 action", range="120 feet", components="V, S",
    save_ability="wis", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Calm Emotions", 2, SpellSchool.ENCHANTMENT,
    description="You attempt to suppress strong emotions in a group of people. Each humanoid in a "
                "20-foot-radius sphere centered on a point you choose must make a Charisma saving "
                "throw; on a failed save, choose one of the following effects for the duration: "
                "suppress any effect causing a target to be charmed or frightened (the effect is "
                "merely suppressed, not ended), or suppress any feeling of hostility toward other "
                "creatures. An affected target's attitude toward others shifts from hostile to "
                "indifferent. Concentration.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    save_ability="cha", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Enlarge/Reduce", 2, SpellSchool.TRANSMUTATION,
    description="You cause one creature or object you can see within range to grow larger or smaller "
                "for the duration. The target must make a Constitution saving throw. On a failed "
                "save, choose either: Enlarge — the target's size doubles, its weight multiplies by "
                "eight, it has advantage on Strength checks and saves, and its weapons deal an extra "
                "1d4 damage; or Reduce — the target's size halves, its weight multiplies by "
                "one-eighth, it has disadvantage on Strength checks and saves, and its weapons deal "
                "1d4 less damage. Concentration.",
    casting_time="1 action", range="30 feet", components="V, S, M",
    save_ability="con", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Levitate", 2, SpellSchool.TRANSMUTATION,
    description="One creature or object of your choice that you can see within range rises vertically, "
                "up to 20 feet, and remains suspended for the duration. The target can be another "
                "willing creature, or an object that isn't being worn or carried. An unwilling "
                "creature must make a Constitution saving throw. On a failed save, the spell levitates "
                "the target, and you can use your action to move it up or down 20 feet; the target "
                "can move only by pushing or pulling against a fixed object or surface within reach. "
                "Concentration.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    save_ability="con", concentration=True, duration="up to 1 minute"))
# Utility / buff / ritual — resolve via the "takes effect" path
register_spell(Spell("Darkness", 2, SpellSchool.EVOCATION,
    description="Magical darkness spreads from a point you choose within range to fill a 15-foot-radius "
                "sphere for the duration. The darkness spreads around corners. A creature with "
                "darkvision can't see through this darkness, and nonmagical light can't illuminate "
                "it. If the point you choose is on an object you are holding or one that isn't being "
                "worn or carried, the darkness emanates from the object and moves with it. Completely "
                "covering the source with an opaque object blocks the darkness. Concentration.",
    casting_time="1 action", range="60 feet", components="V, M",
    concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Silence", 2, SpellSchool.ILLUSION,
    description="For the duration, no sound can be created within or pass through a 20-foot-radius "
                "sphere centered on a point you choose within range. Any creature or object entirely "
                "inside the sphere is immune to thunder damage, and creatures are deafened when "
                "entirely inside it. Casting a spell that includes a verbal component is impossible "
                "there. Ritual.",
    casting_time="1 action", range="120 feet", components="V, S",
    ritual=True, duration="10 minutes"))
register_spell(Spell("Blur", 2, SpellSchool.ILLUSION,
    description="Your body becomes blurred, shifting and wavering to all who can see you. For the "
                "duration, any creature has disadvantage on attack rolls against you. An attacker is "
                "immune to this effect if it doesn't rely on sight or if it can see through "
                "illusions. Concentration.",
    casting_time="1 action", range="self", components="V",
    concentration=True, duration="up to 1 minute"))
register_spell(Spell("Barkskin", 2, SpellSchool.TRANSMUTATION,
    description="You touch a willing creature. Until the spell ends, the target's skin has a rough, "
                "bark-like appearance, and the target's AC can't be less than 16, regardless of "
                "what kind of armor it is wearing. Concentration.",
    casting_time="1 action", range="touch", components="V, S, M",
    concentration=True, duration="up to 1 hour"))
register_spell(Spell("Detect Thoughts", 2, SpellSchool.DIVINATION,
    description="For the duration, you can read the thoughts of certain creatures. When you cast the "
                "spell and as your action on each turn until the spell ends, you can focus your mind "
                "on any one creature you can see within 30 feet. You initially learn the surface "
                "thoughts of the creature. You can probe deeper as an action, forcing the target to "
                "make a Wisdom saving throw; on a failure you gain insight into its reasoning, "
                "emotional state, and something it cares greatly about. Concentration.",
    casting_time="1 action", range="self", components="V, S, M",
    concentration=True, duration="up to 1 minute"))
register_spell(Spell("See Invisibility", 2, SpellSchool.DIVINATION,
    description="For the duration, you see invisible creatures and objects as if they were visible, "
                "and you can see into the Ethereal Plane. Ethereal creatures and objects appear "
                "ghostly and translucent.",
    casting_time="1 action", range="self", components="V, S, M",
    duration="1 hour"))
register_spell(Spell("Darkvision", 2, SpellSchool.TRANSMUTATION,
    description="You touch a willing creature to grant it the ability to see in the dark. For the "
                "duration, that creature has darkvision out to a range of 60 feet. Ritual.",
    casting_time="1 action", range="touch", components="V, S, M",
    ritual=True, duration="8 hours"))
register_spell(Spell("Knock", 2, SpellSchool.TRANSMUTATION,
    description="Choose an object that you can see within range. The spell can open the target if it "
                "is locked, held, or barred by a mundane or magical means. When you cast the spell, "
                "you must choose one of two effects: one lock or bar is unlocked or unbarred, or one "
                "stuck or held object is released. The sound of a loud knock emanates from the "
                "target audible up to 300 feet away.",
    casting_time="1 action", range="60 feet", components="V",
    duration="instantaneous"))
register_spell(Spell("Augury", 2, SpellSchool.DIVINATION,
    description="By casting gem-inlaid sticks, rolling dragon bones, or drawing mystic marks on "
                "parchment, you receive an omen about the results of a specific course of action "
                "that you plan to take within the next 30 minutes. The DM chooses from weal (good "
                "result), woe (bad result), weal and woe (both), or nothing (neither). Ritual.",
    casting_time="1 minute", range="self", components="V, S, M",
    ritual=True, duration="instantaneous"))
register_spell(Spell("Pass Without Trace", 2, SpellSchool.ABJURATION,
    description="A veil of shadows and silence radiates from you, masking you and your companions "
                "from detection. For the duration, each creature you choose within 30 feet of you "
                "(including you) has a +10 bonus to Dexterity (Stealth) checks and can't be tracked "
                "except by magical means. A bonus that high can be attributed only to the aid of a "
                "supernatural force. Concentration.",
    casting_time="1 action", range="self", components="V, S, M",
    concentration=True, duration="up to 1 hour"))

# PHB level-2 completion (36 -> 55, full PHB coverage). Mirrors the level-1 /
# level-6 / level-7-8-9 PHB-completeness expansions: damage spells use the
# standard dice+save path, healing spells use healing_dice_count, save-debuff
# spells carry a save_ability but no damage dice (effects documented in the
# description), and utility / buff / ritual spells resolve cleanly via the
# "takes effect" path.
# Save-spell with damage: Cordon of Arrows (Dex, 1d6 piercing, +1d6/slot).
# Save-debuff (no damage): Gust of Wind (Str, push), Enthrall (Wis, NO
#   concentration — PHB signature), Zone of Truth (Cha, can't lie).
# Healing: Prayer of Healing (2d8+mod to up to 6 creatures, +1d8/slot,
#   10-minute cast, Cleric).
# Utility / buff / ritual (19 spells): Alter Self (concentration, three
#   modes), Animal Messenger (ritual, 24-hour), Arcane Lock (permanent),
#   Beast Sense (ritual + concentration), Continual Flame (permanent flame),
#   Find Steed (10-minute cast, summon mount, Paladin), Find Traps
#   (instantaneous divination), Gentle Repose (ritual, 10-day), Locate Object
#   (concentration), Magic Mouth (ritual, 1-minute cast, programmed illusion),
#   Magic Weapon (concentration, +1 weapon), Protection from Poison (1-hour,
#   no concentration), Rope Trick (concentration, extradimensional space),
#   Warding Bond (1-hour bond, NO concentration — PHB signature).
register_spell(Spell("Cordon of Arrows", 2, SpellSchool.TRANSMUTATION,
    description="You plant four pieces of nonmagical ammunition — arrows or crossbow bolts — in "
                "the ground within range and lay them in the shape of a 5-foot-radius circle "
                "centered on a point within range. Until the spell ends, the ammunition turns "
                "into arrows that fire at each creature that enters or starts its turn within the "
                "circle. A creature takes 1d6 piercing damage for each arrow that hits it. The "
                "ammunition is destroyed when the spell ends. Upcasting adds 1d6 damage per slot "
                "level above 2nd. Concentration.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    save_ability="dex", damage_dice_count=1, damage_dice_sides=6,
    damage_type="piercing", concentration=True, duration="up to 1 minute",
    at_higher_levels_dice=1))
register_spell(Spell("Gust of Wind", 2, SpellSchool.EVOCATION,
    description="A line of strong wind 60 feet long and 10 feet wide blasts from you in a "
                "direction you choose for the spell's duration. Each creature that starts its turn "
                "in the line must succeed on a Strength saving throw or be pushed 15 feet away "
                "from you in a direction following the line. Any creature in the line must spend "
                "2 feet of movement for every 1 foot it moves when moving closer to you. The gust "
                "dispels unsecured objects weighing up to 10 pounds that are in its path and "
                "extinguishes open flames. Concentration.",
    casting_time="1 action", range="self (60-foot line)", components="V, S, M",
    save_ability="str", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Enthrall", 2, SpellSchool.ENCHANTMENT,
    description="You weave a compelling string of words, distracting a creature you can see within "
                "range. Each creature within 10 feet of the target that can hear you and understand "
                "you must make a Wisdom saving throw. On a failed save, the creature is distracted "
                "and has disadvantage on Wisdom (Perception) checks; the creature is also unable "
                "to hear anything beyond 10 feet away. This spell has no concentration "
                "requirement — its 1-minute duration simply elapses. Creatures that can't be "
                "charmed are immune.",
    casting_time="1 action", range="60 feet", components="V, S",
    save_ability="wis", duration="1 minute"))
register_spell(Spell("Zone of Truth", 2, SpellSchool.ENCHANTMENT,
    description="You create a magical zone that guards against deception in a 15-foot-radius sphere "
                "centered on a point of your choice within range. Until the spell ends, a creature "
                "that enters the spell's area for the first time on a turn or starts its turn there "
                "must make a Charisma saving throw. On a failed save, a creature can't speak a "
                "deliberate lie while in the zone. You know whether each creature succeeds or "
                "fails. An affected creature is aware of the spell and can thus avoid answering "
                "questions to which it would normally respond with lies — but it may be evasive. "
                "Concentration.",
    casting_time="1 action", range="60 feet", components="V, S, M",
    save_ability="cha", concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Prayer of Healing", 2, SpellSchool.EVOCATION,
    description="Up to six creatures of your choice that you can see within range each regain hit "
                "points equal to 2d8 + your spellcasting ability modifier. This spell has no "
                "effect on undead or constructs. The casting time is unusually long (10 minutes) "
                "because it is spoken as a communal prayer — it cannot be cast in the heat of "
                "combat. Upcasting heals 1d8 more per slot level above 2nd.",
    casting_time="10 minutes", range="30 feet", components="V, S",
    healing_dice_count=2, healing_dice_sides=8, healing_bonus=0,
    duration="instantaneous", at_higher_levels_dice=1))
register_spell(Spell("Alter Self", 2, SpellSchool.TRANSMUTATION,
    description="You assume a different form. When you cast the spell, choose one of the following "
                "options, the effects of which last for the duration: Aquatic Adaptation (you "
                "grow gills and gain a swimming speed equal to your walking speed, and you can "
                "breathe underwater), Change Appearance (you transform your appearance, including "
                "clothing, armor, weapons, height, weight, and facial features; you can't appear "
                "as a creature of a different size, and your statistics stay the same), or "
                "Natural Weapons (your unarmed strikes deal 1d6 + your Strength modifier "
                "bludgeoning, piercing, or slashing damage — chosen when you cast — and are "
                "magical). Concentration.",
    casting_time="1 action", range="self", components="V, S",
    concentration=True, duration="up to 1 hour"))
register_spell(Spell("Animal Messenger", 2, SpellSchool.ENCHANTMENT,
    description="By means of this ritual, you choose a Tiny beast you can see within range. The "
                "target must be a Beast of Challenge Rating 0. For the duration, the beast "
                "becomes charmed by you and remains within 5 feet of you while you set it its "
                "task: deliver a message of twenty-five words or fewer to a specific, "
                "well-known creature, place, or object you describe. The beast travels toward "
                "the location for the duration, taking the most direct route. When the beast "
                "arrives, it delivers your message, then returns to rejoin you. Ritual.",
    casting_time="1 action", range="30 feet", components="V, S, M",
    ritual=True, duration="24 hours"))
register_spell(Spell("Arcane Lock", 2, SpellSchool.ABJURATION,
    description="You touch a closed door, window, gate, chest, or other entryway, and it becomes "
                "locked for the duration. You and the creatures you designate when you cast this "
                "spell can open the object normally. You can also set a password that, when spoken "
                "within 5 feet of the object, suppresses this spell for 1 minute. Otherwise, it is "
                "impassable until it is broken or the spell is dispelled or suppressed. Casting "
                "knock on the object suppresses arcane lock for 10 minutes. While affected by this "
                "spell, the object is more difficult to break or force open; the DC to break it or "
                "pick any locks on it increases by 10. The material (gold dust worth at least 25 "
                "gp) is consumed by the spell, and the effect is permanent until dispelled.",
    casting_time="1 action", range="touch", components="V, S, M",
    duration="instantaneous"))
register_spell(Spell("Beast Sense", 2, SpellSchool.DIVINATION,
    description="You touch a willing beast. For the duration of the spell, you can use your action "
                "to see through the beast's eyes and hear what it hears, and continue to do so "
                "until you use your action to return to your normal senses. While perceiving "
                "through the beast's senses, you gain the benefits of any special senses that the "
                "beast has. Concentration. Ritual.",
    casting_time="1 action", range="touch", components="V, S",
    ritual=True, concentration=True, duration="up to 1 hour"))
register_spell(Spell("Continual Flame", 2, SpellSchool.EVOCATION,
    description="A flame, equivalent in brightness to a torch, springs forth from an object that "
                "you touch. The effect looks like a regular flame, but it creates no heat and "
                "doesn't use oxygen. A continual flame can be covered or hidden but not smothered "
                "or quenched. The ruby dust (worth at least 50 gp) is consumed by the spell, and "
                "the flame is permanent until dispelled.",
    casting_time="1 action", range="touch", components="V, S, M",
    duration="instantaneous"))
register_spell(Spell("Find Steed", 2, SpellSchool.CONJURATION,
    description="You summon a spirit that assumes the form of an unusually intelligent, strong, "
                "and loyal steed, creating a long-lasting bond with it. Appearing in an "
                "unoccupied space within range, the steed takes on a form that you choose: a "
                "warhorse, a pony, a camel, an elk, or a mastiff. Your DM might allow other "
                "animals to be summoned as steeds. The steed has the statistics of the chosen "
                "form, though its type is celestial, fey, or fiend (your choice). While mounted on "
                "your steed, you make any saving throw triggered by an effect that targets only "
                "you or only your steed with advantage. The steed shares your alignment and "
                "understands your languages. When you cast a spell with a range of self, it can "
                "also affect the steed if the steed is within 5 feet of you. The casting time of "
                "10 minutes reflects the ritual summoning. Paladin signature spell. The steed "
                "remains until dismissed or reduced to 0 hit points.",
    casting_time="10 minutes", range="30 feet", components="V, S",
    duration="instantaneous"))
register_spell(Spell("Find Traps", 2, SpellSchool.DIVINATION,
    description="You sense the presence of any trap within range that is within line of sight. A "
                "trap, for the purpose of this spell, includes anything designed to harm you or "
                "others, such as a pit trap, an arrow trap, a falling-block mechanism, a tripwire "
                "that releases poisonous gas, or any other similar hazard. The spell does not "
                "reveal the trap's exact nature or location, only its presence. Natural hazards "
                "and the unpredictable results of spellcasting (such as the area targeted by a "
                "summoned creature) are not detected.",
    casting_time="1 action", range="120 feet", components="V, S",
    duration="instantaneous"))
register_spell(Spell("Gentle Repose", 2, SpellSchool.NECROMANCY,
    description="You touch a corpse or other remains. For the duration, the target is protected "
                "from decay. This spell also extends the time limit on raising the target from "
                "the dead, since days spent under the influence of this spell don't count against "
                "the time limit of spells such as raise dead. The spell also effectively extends "
                "the time limit on revivify. The spell has no effect on undead. Ritual.",
    casting_time="1 action", range="touch", components="V, S, M",
    ritual=True, duration="10 days"))
register_spell(Spell("Locate Object", 2, SpellSchool.DIVINATION,
    description="Describe or name an object that is familiar to you. You sense the direction to "
                "the object's location, as long as that object is within 1,000 feet of you. If the "
                "object is in motion, you know the direction of its movement. The spell can find "
                "an object you have seen (even in a painting or through a description), or the "
                "nearest object of a particular kind (such as a particular kind of apparel, "
                "jewelry, furniture, vehicle, or weapon). The spell is blocked by even a thin "
                "sheet of lead, and it cannot find objects underwater. Concentration.",
    casting_time="1 action", range="self", components="V, S, M",
    concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Magic Mouth", 2, SpellSchool.ILLUSION,
    description="You implant a message within an object in range, a message that is uttered when "
                "a trigger condition is met. Choose an object that you can see and that isn't "
                "being worn or carried by another creature. Then speak the message, which must be "
                "25 words or fewer, including the trigger condition. The trigger can be a general "
                "event (\"when a creature steps on this plate\") or specific (\"when a human in "
                "leather armor steps on this plate\"). When the trigger occurs, a magical mouth "
                "appears on the object and utters the message in your voice at the same volume "
                "you spoke. The casting time of 1 minute reflects the ritual enchantment. Ritual. "
                "The enchantment persists until dispelled.",
    casting_time="1 minute", range="30 feet", components="V, S, M",
    ritual=True, duration="until dispelled"))
register_spell(Spell("Magic Weapon", 2, SpellSchool.TRANSMUTATION,
    description="You touch a nonmagical weapon. Until the spell ends, that weapon becomes a magic "
                "weapon with a +1 bonus to attack rolls and damage rolls. When cast at higher "
                "levels, the bonus grows: +2 when cast with a 6th-level slot, +3 when cast with "
                "an 8th-level slot. Concentration.",
    casting_time="1 bonus action", range="touch", components="V, S",
    concentration=True, duration="up to 1 hour"))
register_spell(Spell("Protection from Poison", 2, SpellSchool.ABJURATION,
    description="You touch a creature. If it is poisoned, you neutralize the poison. If more than "
                "one poison afflicts the creature, you neutralize one poison that you know is "
                "present, or the one affecting it most severely. For the duration, the target has "
                "advantage on saving throws against being poisoned, and it has resistance to "
                "poison damage. The spell lasts 1 hour with no concentration required.",
    casting_time="1 action", range="touch", components="V, S",
    duration="1 hour"))
register_spell(Spell("Rope Trick", 2, SpellSchool.TRANSMUTATION,
    description="You touch a length of rope that is up to 60 feet long. One end of the rope then "
                "rises into the air until the whole rope hangs perpendicular to the ground. At "
                "the upper end of the rope, an invisible entrance opens to an extradimensional "
                "space that lasts until the spell ends. The extradimensional space can be reached "
                "by climbing to the top of the rope. The space can hold as many as eight Medium or "
                "smaller creatures. Attacks and spells can't cross through the entrance into or "
                "out of the extradimensional space, but those inside can see out through it as if "
                "through a 3-foot-by-5-foot window centered on the rope. The spell ends if the "
                "rope is destroyed or if any creature inside exits the space. Concentration.",
    casting_time="1 action", range="touch", components="V, S, M",
    concentration=True, duration="up to 1 hour"))
register_spell(Spell("Warding Bond", 2, SpellSchool.ABJURATION,
    description="This spell wards a willing creature you touch and creates a mystic connection "
                "between you and the target so that some of its wounds are transferred to you. "
                "Until the spell ends, the target gains a +1 bonus to AC and saving throws, and "
                "it has resistance to all damage. Each time it takes damage, you take the same "
                "amount of damage. The spell ends if you drop to 0 hit points or if you and the "
                "target become separated by more than 60 feet. The spell also ends if it is cast "
                "again on either of the connected creatures. Warding Bond lasts 1 hour with no "
                "concentration required — the bond persists until ended. The paired platinum rings "
                "(worth at least 50 gp each) are worn by caster and target, and are not consumed. "
                "Cleric signature spell.",
    casting_time="1 action", range="touch", components="V, S, M",
    duration="1 hour"))

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

# PHB level-3 completion (13 -> 39, full PHB coverage). Mirrors the level-1 /
# level-2 / level-6 PHB-completeness expansions: damage spells use the standard
# dice+save path, attack-roll spells use requires_attack_roll, save-debuff
# spells carry a save_ability but no damage dice (effects documented in the
# description), damage-zone spells use the auto-damage path (no save, no attack
# roll — like Spike Growth / Wall of Thorns), and utility / buff / ritual spells
# resolve cleanly via the "takes effect" path.
# Save-spell with damage: Glyph of Warding (Dex, 5d8, +1d8/slot, 1-hour cast).
# Save-debuff (no damage): Bestow Curse (Wis, touch), Slow (Wis, 40-ft cube),
#   Sleet Storm (Dex, 40-ft cylinder).
# Attack-roll: Vampiric Touch (melee spell attack, 3d6 necrotic, heal half,
#   +1d6/slot).
# Damage zone (auto-damage, no save): Wind Wall (3d8 bludgeoning wall).
# Utility / buff / ritual (20 spells): Animate Dead (1-min cast, 24-hour
#   undead), Beacon of Hope (concentration, advantage Wis/death saves + max
#   heal), Clairvoyance (ritual + concentration, 10-min cast, sensor), Conjure
#   Animals (concentration, summon beasts), Create Food and Water (instant),
#   Crusader's Mantle (concentration, +1d4 radiant weapon aura), Daylight
#   (1-hour, NO concentration), Elemental Weapon (concentration, +1 weapon /
#   +1d4 element; +2/+3 at slot 5/7), Feign Death (ritual, 1-hour trance),
#   Gaseous Form (concentration, 1-hour), Plant Growth (instant overgrowth),
#   Protection from Energy (concentration, 1-hour, resist element), Remove
#   Curse (instant), Sending (instant 25-word message), Speak with Dead
#   (10-min cast, 5 questions), Speak with Plants (concentration, 10-min),
#   Tiny Hut (ritual, 1-min cast, 8-hour dome, NO concentration), Tongues
#   (1-hour, understand all languages, NO concentration), Water Breathing
#   (ritual, 24-hour, NO concentration), Water Walk (ritual, 1-hour, NO
#   concentration).
register_spell(Spell("Glyph of Warding", 3, SpellSchool.ABJURATION,
    description="When you cast this spell, you inscribe a glyph that later unleashes a magical effect. "
                "You decide what triggers the glyph when you cast the spell. Once the glyph is triggered, "
                "the spell ends. You choose either an explosive glyph or a spell glyph. Explosive glyph: "
                "each creature in the area must make a Dexterity saving throw. A creature takes 5d8 acid, "
                "cold, fire, lightning, or thunder damage on a failed saving throw (your choice when you "
                "cast the glyph), or half as much on a successful one. Spell glyph: you can store a "
                "prepared spell of 3rd level or lower by casting it as part of creating the glyph. The "
                "casting time of 1 hour reflects the careful inscription — this is a trap, not a combat "
                "spell. Upcasting adds 1d8 explosive damage per slot level above 3rd.",
    casting_time="1 hour", range="touch", components="V, S, M",
    save_ability="dex", damage_dice_count=5, damage_dice_sides=8,
    damage_type="acid", duration="until dispelled or triggered",
    at_higher_levels_dice=1))
register_spell(Spell("Bestow Curse", 3, SpellSchool.NECROMANCY,
    description="You touch a creature, and that creature must succeed on a Wisdom saving throw or become "
                "cursed for the duration. When you cast this spell, choose the nature of the curse from "
                "the following options: the target has disadvantage on ability checks and saving throws "
                "tied to one ability score you choose; the target has disadvantage on attack rolls "
                "against you; the target must use its action each turn to do nothing; or you create a "
                "custom effect. A remove curse spell ends it. Concentration. At slot 4 the duration "
                "extends to 8 hours; at slot 5 it lasts 24 hours with no concentration required.",
    casting_time="1 action", range="touch", components="V, S",
    save_ability="wis", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Slow", 3, SpellSchool.TRANSMUTATION,
    description="You alter time around up to six creatures of your choice in a 40-foot cube within range. "
                "Each target must succeed on a Wisdom saving throw. For the duration, a target's speed "
                "is halved, it takes a -2 penalty to AC and Dexterity saving throws, and it can't use "
                "reactions. On its turn, it can use either an action or a bonus action, not both. "
                "Regardless of abilities or magic items, it can't make more than one melee or ranged "
                "attack during its turn. If the creature attempts to cast a spell with a casting time of "
                "1 action, roll a d20; on an 11 or higher the spell doesn't take effect until the "
                "creature's next turn. Concentration.",
    casting_time="1 action", range="120 feet", components="V, S, M",
    save_ability="wis", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Sleet Storm", 3, SpellSchool.CONJURATION,
    description="Until the spell ends, freezing rain and sleet fall in a 20-foot-tall cylinder with a "
                "40-foot radius centered on a point you choose within range. The area is difficult "
                "terrain, and each creature in the area when it is cast must succeed on a Dexterity "
                "saving throw or have its speed reduced to 0 until the start of its next turn. A creature "
                "that enters the area or ends its turn there must also succeed on a Dexterity saving "
                "throw or fall prone. The precipitation also extinguishes unprotected flames in the area. "
                "Concentration.",
    casting_time="1 action", range="150 feet", components="V, S, M",
    save_ability="dex", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Vampiric Touch", 3, SpellSchool.NECROMANCY,
    description="The touch of your shadow-wreathed hand can siphon life force from others. When you cast "
                "the spell, make a melee spell attack against a creature within your reach. On a hit, the "
                "target takes 3d6 necrotic damage, and you regain hit points equal to half the amount of "
                "necrotic damage dealt. Until the spell ends, you can make the attack again on each of "
                "your turns as an action. Upcasting adds 1d6 necrotic damage per slot level above 3rd. "
                "Concentration.",
    casting_time="1 action", range="self", components="V, S",
    requires_attack_roll=True, damage_dice_count=3, damage_dice_sides=6,
    damage_type="necrotic", concentration=True, duration="up to 1 minute",
    at_higher_levels_dice=1))
register_spell(Spell("Wind Wall", 3, SpellSchool.EVOCATION,
    description="A wall of strong wind rises from the ground at a point you choose within range. You can "
                "make the wall up to 50 feet long, 15 feet high, and 1 foot thick. You can shape the wall "
                "in any way you choose so long as it makes one continuous path along the ground. The wall "
                "remains for the spell's duration. Each creature that makes a ranged weapon attack "
                "through the wall has disadvantage on the attack roll. Each creature that moves into the "
                "wall for the first time on a turn or starts its turn there takes 3d8 bludgeoning damage. "
                "The wind extinguishes unprotected flames in the area. Concentration.",
    casting_time="1 action", range="120 feet", components="V, S, M",
    damage_dice_count=3, damage_dice_sides=8, damage_type="bludgeoning",
    concentration=True, duration="up to 1 minute"))
register_spell(Spell("Animate Dead", 3, SpellSchool.NECROMANCY,
    description="This spell creates an undead servant. Choose a pile of bones or a corpse of a Medium or "
                "Small humanoid within range. Your spell imbues the target with a foul mimicry of life, "
                "raising it as an undead creature. The target becomes a skeleton if you chose bones or a "
                "zombie if you chose a corpse. On each of your turns, you can use a bonus action to "
                "mentally command the creature if it is within 60 feet of you. The creature is under your "
                "control for 24 hours, after which it stops obeying any command. The casting time of 1 "
                "minute reflects the ritual animation. For each slot level above 3rd, you animate or "
                "reassert control over two additional undead.",
    casting_time="1 minute", range="10 feet", components="V, S, M",
    duration="instantaneous"))
register_spell(Spell("Beacon of Hope", 3, SpellSchool.ABJURATION,
    description="This spell bestows hope and vitality. Choose any number of creatures within range. For "
                "the duration, each target has advantage on Wisdom saving throws and death saving throws, "
                "and regains the maximum number of hit points possible from any healing. Concentration.",
    casting_time="1 action", range="30 feet", components="V, S",
    concentration=True, duration="up to 1 minute"))
register_spell(Spell("Clairvoyance", 3, SpellSchool.DIVINATION,
    description="You create an invisible sensor within range in a location familiar to you (a place you "
                "have visited or seen before) or in an obvious location that is unfamiliar to you. The "
                "sensor remains in place for the duration, and it can't be attacked or otherwise "
                "interacted with. When you cast the spell, you choose seeing or hearing. You can use your "
                "action to change the mode. The casting time of 10 minutes reflects the ritual scrying. "
                "Concentration. Ritual.",
    casting_time="10 minutes", range="1 mile", components="V, S, M",
    ritual=True, concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Conjure Animals", 3, SpellSchool.CONJURATION,
    description="You summon fey spirits that take the form of animals and appear in unoccupied spaces "
                "that you can see within range. Choose one of the following options: one beast of "
                "challenge rating 2 or lower, two beasts of challenge rating 1 or lower, four beasts of "
                "challenge rating 1/2 or lower, or eight beasts of challenge rating 1/4 or lower. The "
                "beasts are friendly to you and your companions. They obey any verbal commands that you "
                "issue to them. For each slot level above 3rd, the CR or number of beasts increases. "
                "Concentration.",
    casting_time="1 action", range="60 feet", components="V, S",
    concentration=True, duration="up to 1 hour"))
register_spell(Spell("Create Food and Water", 3, SpellSchool.CONJURATION,
    description="You create 45 pounds of food and 30 gallons of water on the ground or in containers "
                "within range, enough to sustain up to fifteen humanoids or five steeds for 24 hours. "
                "The food is bland but nourishing, and spoils if uneaten after 24 hours. The water is "
                "clean and doesn't go bad.",
    casting_time="1 action", range="30 feet", components="V, S",
    duration="instantaneous"))
register_spell(Spell("Crusader's Mantle", 3, SpellSchool.ABJURATION,
    description="Holy power radiates from you in an aura with a 30-foot radius, awakening boldness in "
                "friendly creatures. Until the spell ends, the aura moves with you, centered on you. "
                "While in the aura, each nonhostile creature in the aura (including you) deals an extra "
                "1d4 radiant damage when it hits with a weapon attack. Paladin signature spell. "
                "Concentration.",
    casting_time="1 action", range="self", components="V, S",
    concentration=True, duration="up to 1 minute"))
register_spell(Spell("Daylight", 3, SpellSchool.EVOCATION,
    description="A 60-foot-radius sphere of light spreads out from a point you choose within range. The "
                "sphere is bright light and sheds dim light for an additional 60 feet. If the point you "
                "choose is on an object you are holding or one that isn't being worn or carried, the "
                "light shines from the object and moves with it. Completely covering the affected object "
                "with an opaque object blocks the light. If any of this spell's area overlaps with an "
                "area of darkness created by a spell of 3rd level or lower, the spell that created the "
                "darkness is dispelled. Daylight lasts 1 hour with no concentration required.",
    casting_time="1 action", range="60 feet", components="V, S",
    duration="1 hour"))
register_spell(Spell("Elemental Weapon", 3, SpellSchool.TRANSMUTATION,
    description="A nonmagical weapon you touch becomes a magic weapon. Choose one of the following "
                "damage types: acid, cold, fire, lightning, or thunder. For the duration, the weapon "
                "has a +1 bonus to attack rolls and deals an extra 1d4 damage of the chosen type when "
                "it hits. At slot 5 the bonus becomes +2 and the extra damage 2d4; at slot 7 it becomes "
                "+3 and 3d4. Concentration.",
    casting_time="1 action", range="touch", components="V, S",
    concentration=True, duration="up to 1 hour"))
register_spell(Spell("Feign Death", 3, SpellSchool.NECROMANCY,
    description="You touch a willing creature and put it into a cataleptic state that is indistinguishable "
                "from death. For the spell's duration, or until you use an action to touch the target and "
                "dismiss the spell, the target appears dead to all outward inspection and to spells used "
                "to determine status. The target is blinded and incapacitated, and its speed drops to 0. "
                "The target has resistance to all damage except psychic. The target can hear everything "
                "around it. The casting time of 1 minute reflects the ritual trance. Ritual.",
    casting_time="1 minute", range="touch", components="V, S, M",
    ritual=True, duration="1 hour"))
register_spell(Spell("Gaseous Form", 3, SpellSchool.TRANSMUTATION,
    description="You transform a willing creature you touch, along with everything it's wearing and "
                "carrying, into a misty cloud for the duration. While in this form, the target's only "
                "method of movement is a flying speed of 10 feet. The target can enter and occupy the "
                "space of another creature. The target has resistance to nonmagical damage, and it has "
                "advantage on Strength, Dexterity, and Constitution saving throws. The target can pass "
                "through small holes, narrow openings, and mere cracks. The target can't fall and "
                "remains suspended in the air. Concentration.",
    casting_time="1 action", range="touch", components="V, S, M",
    concentration=True, duration="up to 1 hour"))
register_spell(Spell("Plant Growth", 3, SpellSchool.TRANSMUTATION,
    description="This spell channels vitality into plants within a specific area. There are two possible "
                "uses. In the combat-relevant mode (1 action), all normal plants in a 100-foot radius "
                "centered on a point within range become thick and overgrown; the area becomes difficult "
                "terrain that lasts for the duration. In the overland mode (8 hours), you enrich the "
                "land so all plants in a half-mile radius centered on a point within range become "
                "enriched for 1 year, yielding twice the normal amount of harvested food. The overgrowth "
                "of the combat mode persists for 1 year unless cleared.",
    casting_time="1 action", range="150 feet", components="V, S",
    duration="instantaneous"))
register_spell(Spell("Protection from Energy", 3, SpellSchool.ABJURATION,
    description="For the duration, the willing creature you touch has resistance to one damage type of "
                "your choice: acid, cold, fire, lightning, or thunder. When you cast the spell, choose "
                "the damage type. Concentration.",
    casting_time="1 action", range="touch", components="V, S",
    concentration=True, duration="up to 1 hour"))
register_spell(Spell("Remove Curse", 3, SpellSchool.ABJURATION,
    description="At your touch, all curses affecting one creature or object end. If the object is a "
                "cursed magic item, its curse remains, but the spell breaks its owner's attunement to "
                "the object so it can be removed or discarded.",
    casting_time="1 action", range="touch", components="V, S",
    duration="instantaneous"))
register_spell(Spell("Sending", 3, SpellSchool.EVOCATION,
    description="You send a short message of twenty-five words or less to a creature with which you are "
                "familiar. The creature hears the message in its mind, recognizes you as the sender if "
                "it knows you, and can answer in a like manner immediately. The spell enables a creature "
                "with an Intelligence score of at least 1 to understand the meaning of your words. The "
                "message is instantaneous and crosses any distance, even to another plane of existence, "
                "though there is a 5 percent chance the message doesn't arrive to a target on another "
                "plane.",
    casting_time="1 action", range="unlimited", components="V, S, M",
    duration="instantaneous"))
register_spell(Spell("Speak with Dead", 3, SpellSchool.NECROMANCY,
    description="You grant the semblance of life and intelligence to a corpse of your choice within range, "
                "allowing it to answer the questions you pose. The corpse must still have a mouth and "
                "can't be undead. The spell fails if the corpse was the target of this spell within the "
                "last 10 days. Until the spell ends, you can ask the corpse up to five questions. The "
                "corpse knows only what it knew in life, including the languages it knew. Answers are "
                "usually brief, cryptic, or repetitive, and the corpse is under no compulsion to offer a "
                "truthful answer. The casting time of 10 minutes reflects the ritual questioning.",
    casting_time="10 minutes", range="10 feet", components="V, S, M",
    duration="instantaneous"))
register_spell(Spell("Speak with Plants", 3, SpellSchool.TRANSMUTATION,
    description="You imbue plants within 30 feet of you with limited sentience and animation, giving them "
                "the ability to communicate with you and follow your simple commands. You can question "
                "plants about events in the spell's area within the past day, gaining information about "
                "creatures that have passed, weather, and other circumstances. You can also turn "
                "difficult terrain caused by plant growth into ordinary terrain, or vice versa. Plants "
                "might be able to perform minor tasks for you. Concentration.",
    casting_time="1 action", range="self (30-foot radius)", components="V, S",
    concentration=True, duration="10 minutes"))
register_spell(Spell("Tiny Hut", 3, SpellSchool.ABJURATION,
    description="A 10-foot-radius immobile dome of force springs into existence around and above you and "
                "remains stationary for the duration. The spell ends if you leave its area. Nine "
                "creatures of Medium size or smaller can fit inside the dome with you. The spell fails if "
                "its area includes a larger creature or more than nine creatures. Creatures and objects "
                "within the dome when you cast this spell can move through it freely. All other creatures "
                "and objects are barred from passing through it. Spells and other magical effects can't "
                "extend through the dome or be cast through it. The atmosphere inside the space is "
                "comfortable and dry, regardless of the weather outside. The casting time of 1 minute "
                "reflects the ritual casting. Tiny Hut lasts 8 hours with no concentration required. "
                "Ritual.",
    casting_time="1 minute", range="self", components="V, S, M",
    ritual=True, duration="8 hours"))
register_spell(Spell("Tongues", 3, SpellSchool.DIVINATION,
    description="This spell grants the creature you touch the ability to understand any spoken language "
                "it hears for the duration. Moreover, when the target speaks, any creature that knows at "
                "least one language and can hear the target understands what it says. Tongues lasts 1 "
                "hour with no concentration required.",
    casting_time="1 action", range="touch", components="V, M",
    duration="1 hour"))
register_spell(Spell("Water Breathing", 3, SpellSchool.TRANSMUTATION,
    description="This spell grants up to ten willing creatures of your choice within range the ability to "
                "breathe underwater until the spell ends. Affected creatures also retain their normal "
                "mode of respiration. Water Breathing lasts 24 hours with no concentration required. "
                "Ritual.",
    casting_time="1 action", range="30 feet", components="V, S, M",
    ritual=True, duration="24 hours"))
register_spell(Spell("Water Walk", 3, SpellSchool.TRANSMUTATION,
    description="This spell grants the ability to move across any liquid surface as though it were solid "
                "ground. Up to ten willing creatures you can see within range gain this ability for the "
                "duration. Affected creatures can also choose to descend beneath the surface of the "
                "liquid. The spell ends for a creature if that creature falls more than 10 feet into the "
                "liquid. Water Walk lasts 1 hour with no concentration required. Ritual.",
    casting_time="1 action", range="30 feet", components="V, S, M",
    ritual=True, duration="1 hour"))

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

# --- Level 4 PHB completion additions (14 -> 30, full Player's Handbook ----
#   coverage). Grouped by resolution path, mirroring the level 1/2/3/6
#   PHB-completeness expansion convention.

# Save-spell with damage (+1d8/slot upcast)
register_spell(Spell("Wall of Fire", 4, SpellSchool.EVOCATION,
    description="A wall of fire appears; creatures in it or ending their turn "
                "there take 5d8 fire (Dex save for half). One side deals damage.",
    casting_time="1 action", range="120 feet", components="V, S, M",
    save_ability="dex", damage_dice_count=5, damage_dice_sides=8,
    damage_type="fire", concentration=True, duration="up to 1 minute",
    at_higher_levels_dice=1))
register_spell(Spell("Sickening Radiance", 4, SpellSchool.EVOCATION,
    description="Dim, sickly light fills a 30-foot sphere; failed Con save takes "
                "4d10 radiant and one level of exhaustion, half damage on success.",
    casting_time="1 action", range="120 feet", components="V, S",
    save_ability="con", damage_dice_count=4, damage_dice_sides=10,
    damage_type="radiant", concentration=True, duration="up to 10 minutes",
    at_higher_levels_dice=1))

# Save-debuff (no damage)
register_spell(Spell("Compulsion", 4, SpellSchool.ENCHANTMENT,
    description="Up to 12 creatures you choose must use their movement on your "
                "turn toward a direction you choose (Wis negates). Concentration.",
    casting_time="1 action", range="30 feet", components="V, S",
    save_ability="wis", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Otiluke's Resilient Sphere", 4, SpellSchool.EVOCATION,
    description="A shimmering sphere encloses the target (Dex negates); it is "
                "restrained and protected from outside damage. Concentration.",
    casting_time="1 action", range="30 feet", components="V, S, M",
    save_ability="dex", concentration=True, duration="up to 1 minute"))

# Utility / buff / ritual (12 spells)
register_spell(Spell("Arcane Eye", 4, SpellSchool.DIVINATION,
    description="An invisible magical eye you can see through moves up to 30 ft "
                "per turn, transmitting what it sees. Concentration.",
    casting_time="1 minute", range="30 feet", components="V, S, M",
    concentration=True, duration="up to 1 hour"))
register_spell(Spell("Conjure Minor Elementals", 4, SpellSchool.CONJURATION,
    description="Summons elementals whose total CR matches the slot (CR 2 at "
                "4th level) that obey your commands. Concentration.",
    casting_time="1 action", range="90 feet", components="V, S",
    concentration=True, duration="up to 1 hour"))
register_spell(Spell("Control Water", 4, SpellSchool.TRANSMUTATION,
    description="Control standing water in a 100-foot cube: flood, part water, "
                "redirect flow, or form a whirlpool. Concentration.",
    casting_time="1 action", range="300 feet", components="V, S, M",
    concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Divination", 4, SpellSchool.DIVINATION,
    description="Your god answers a single question about an event up to seven "
                "days away with a short, truthful reply. Ritual.",
    casting_time="1 minute", range="self", components="V, S, M",
    ritual=True, duration="instantaneous"))
register_spell(Spell("Fabricate", 4, SpellSchool.TRANSMUTATION,
    description="Convert raw material you can see into finished goods of the "
                "same material (armor, weapons, structures) up to a large object.",
    casting_time="10 minutes", range="120 feet", components="V, S",
    duration="instantaneous"))
register_spell(Spell("Giant Insect", 4, SpellSchool.TRANSMUTATION,
    description="Transform centipedes, spiders, wasps, or scorpions within range "
                "into giant versions that obey you. Concentration.",
    casting_time="1 action", range="30 feet", components="V, S",
    concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Guardian of Faith", 4, SpellSchool.CONJURATION,
    description="A Large spectral guardian appears; hostile creatures within 10 "
                "feet take 20 radiant damage (no save). It vanishes after dealing "
                "60 damage. Lasts up to 8 hours.",
    casting_time="1 action", range="30 feet", components="V, S",
    duration="8 hours"))
register_spell(Spell("Hallucinatory Terrain", 4, SpellSchool.ILLUSION,
    description="Make natural terrain look, sound, and smell like another kind "
                "(bridge over a chasm, bog as meadow). Investigation to discern.",
    casting_time="10 minutes", range="300 feet", components="V, S, M",
    duration="24 hours"))
register_spell(Spell("Leomund's Secret Chest", 4, SpellSchool.CONJURATION,
    description="Hide a chest and its contents on the Ethereal Plane and recall "
                "it with this spell. A replica serves as the focus. Ritual.",
    casting_time="1 action", range="30 feet", components="V, S, M",
    ritual=True, duration="instantaneous"))
register_spell(Spell("Locate Creature", 4, SpellSchool.DIVINATION,
    description="Sense the direction to a specific creature or kind of creature "
                "within 1,000 feet (described or blood/possessed item). Concentration.",
    casting_time="1 action", range="self", components="V, S, M",
    concentration=True, duration="up to 1 hour"))
register_spell(Spell("Mordenkainen's Faithful Hound", 4, SpellSchool.CONJURATION,
    description="An invisible phantom watchdog guards a 30-foot area for 8 hours, "
                "biting any hostile creature that enters. No concentration.",
    casting_time="1 action", range="30 feet", components="V, S, M",
    duration="8 hours"))
register_spell(Spell("Stone Shape", 4, SpellSchool.TRANSMUTATION,
    description="Reshape a stone object (Medium or smaller) you touch into any "
                "form you can imagine.",
    casting_time="1 action", range="touch", components="V, S, M",
    duration="instantaneous"))

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

# --- Level 5 additions — PHB completeness (13 → 39; catalogue 286 → 312) -----
# All 26 missing PHB 5th-level spells, grouped by resolution path. With this
# block every one of the ten leveled tiers (1-9) reaches full Player's Handbook
# coverage. Mirrors the level-1/2/3/4/6/7/8/9 PHB-completeness batches.

# Save-spell with damage -----------------------------------------------------
# Destructive Wave (PHB p.154) — Con save, 5d8 thunder + knocked prone; the
# secondary 5d8 radiant rider is documented (single-dice-type engine model);
# +1d8 thunder per slot above 5th.
register_spell(Spell("Destructive Wave", 5, SpellSchool.EVOCATION,
    description="Divine energy ripples out from you. Each creature within 10 feet "
                "must make a Constitution save. On a failed save a creature takes "
                "5d8 thunder damage plus 5d8 radiant damage and is knocked prone; "
                "on a successful one it takes half as much. (+1d8 thunder per slot "
                "above 5th; the radiant rider is documented, not modeled.)",
    casting_time="1 action", range="self (10-foot radius)", components="V",
    save_ability="con", damage_dice_count=5, damage_dice_sides=8,
    damage_type="thunder", at_higher_levels_dice=1))
# Conjure Volley (PHB p.69) — Dex save, 8d8 piercing, 40-foot cone; +1d8/slot.
register_spell(Spell("Conjure Volley", 5, SpellSchool.CONJURATION,
    description="You fire a piece of nonmagical ammunition or hurl a thrown "
                "weapon into the air and it multiplies into a volley that rains "
                "down in a 40-foot cone. Each creature in the area makes a "
                "Dexterity save, taking 8d8 piercing damage on a failed save or "
                "half as much on a successful one. (+1d8 per slot above 5th.)",
    casting_time="1 action", range="self (40-foot cone)", components="V, S, M",
    material_description="one piece of ammunition or a thrown weapon",
    save_ability="dex", damage_dice_count=8, damage_dice_sides=8,
    damage_type="piercing", at_higher_levels_dice=1))

# Save-debuff (save, no damage) ----------------------------------------------
# Contagion (PHB p.129) — Con save on cast; the multi-save disease sequence is
# documented (the engine resolves the single on-cast save, like Bestow Curse).
register_spell(Spell("Contagion", 5, SpellSchool.NECROMANCY,
    description="You touch a creature, afflicting it with a magical disease. The "
                "target must succeed on a Constitution save or be poisoned; after "
                "three failed saves while poisoned it contracts one of several "
                "crippling diseases (blinding sickness, filth fever, flesh rot, "
                "mindfire, seizure, or slimy doom) for 7 days. (Engine models the "
                "on-cast Con save; the multi-save disease sequence is documented.)",
    casting_time="1 action", range="touch", components="V, S",
    save_ability="con", duration="7 days"))
register_spell(Spell("Modify Memory", 5, SpellSchool.ENCHANTMENT,
    description="You attempt to reshape a creature's memories. One creature you "
                "can see must make a Wisdom save; on a failure you may eliminate "
                "up to 24 hours of memory, implant a false memory, or make it "
                "forget an event, while it is charmed by you for the duration. "
                "The modified memory fades over time.",
    casting_time="1 action", range="60 feet", components="V, S",
    save_ability="wis", concentration=True, duration="up to 1 minute"))
register_spell(Spell("Telekinesis", 5, SpellSchool.TRANSMUTATION,
    description="You gain the ability to move or manipulate creatures and objects "
                "by thought. On your turn you can move a Huge or smaller creature "
                "or object (Str save to resist), push it, or attempt to grapple a "
                "creature using your spellcasting ability in place of Strength.",
    casting_time="1 action", range="60 feet", components="V, S",
    save_ability="str", concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Planar Binding", 5, SpellSchool.ABJURATION,
    description="With an hour-long ritual you bind a celestial, elemental, fey, "
                "or fiend within range to your service. The target makes a "
                "Charisma save; on a failure it serves you for the duration, "
                "obeying your commands to the best of its ability. (Upcasting "
                "extends the duration: 10 days at slot 6, 30 at 7, 180 at 8, a "
                "year and a day at 9.)",
    casting_time="1 hour", range="60 feet", components="V, S, M",
    material_description="a jewel worth at least 1000 gp, which the spell consumes",
    save_ability="cha", concentration=True, duration="24 hours"))
register_spell(Spell("Geas", 5, SpellSchool.ENCHANTMENT,
    description="You place a magical command on a creature that you can see within "
                "range, forcing it to carry out or refrain from some activity. The "
                "target makes a Wisdom save; on a failure it is charmed by you for "
                "the duration and takes 5d10 psychic damage each time it acts "
                "against your instructions. (30-day duration, no concentration; the "
                "psychic rider is documented.)",
    casting_time="1 minute", range="60 feet", components="V",
    save_ability="wis", duration="30 days"))
register_spell(Spell("Seeming", 5, SpellSchool.TRANSMUTATION,
    description="You change the appearance of any number of creatures that you can "
                "see within range (Charisma save to resist). You give each a new "
                "illusory appearance — clothing, armor, weapons, or features — that "
                "holds for the duration; nothing physical actually changes.",
    casting_time="1 action", range="30 feet", components="V, S",
    save_ability="cha", duration="8 hours"))

# Utility / buff / ritual ----------------------------------------------------
register_spell(Spell("Awaken", 5, SpellSchool.TRANSMUTATION,
    description="After eight hours of ritual, you awaken a Beast or plant you "
                "touch, granting it human-like sentience, an Intelligence of 10, "
                "the ability to speak one language you know, and free will. The "
                "effect is instantaneous and permanent.",
    casting_time="8 hours", range="touch", components="V, S, M",
    material_description="an agate worth at least 1000 gp, which the spell consumes"))
register_spell(Spell("Banishing Smite", 5, SpellSchool.ABJURATION,
    description="The next time you hit a creature with a weapon attack before this "
                "spell ends, your weapon deals an extra 5d10 force damage, and if "
                "the target has 50 hit points or fewer after taking this damage it "
                "is banished to its home plane. (Concentration smite; the damage "
                "and banish rider are documented, not modeled on cast.)",
    casting_time="1 bonus action", range="self", components="V",
    concentration=True, duration="up to 1 minute"))
register_spell(Spell("Circle of Power", 5, SpellSchool.ABJURATION,
    description="Divine energy radiates from you in a 30-foot radius. Each "
                "creature of your choice that you can see in the area has "
                "advantage on saving throws against spells and other magical "
                "effects for the duration.",
    casting_time="1 action", range="self (30-foot radius)", components="V",
    concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Commune", 5, SpellSchool.DIVINATION,
    description="You contact your deity or a divine proxy and ask up to three "
                "questions that can be answered with a yes or a no. You must ask "
                "before the spell ends and receive truthful answers. (Divination "
                "ritual.)",
    casting_time="1 minute", range="self", components="V, S, M",
    material_description="incense and a vial of holy water or a phylactery worth at least 500 gp",
    ritual=True, duration="1 minute"))
register_spell(Spell("Commune with Nature", 5, SpellSchool.DIVINATION,
    description="You become one with nature, gaining knowledge of the surrounding "
                "territory out to 3 miles (1 mile underground). You learn the "
                "terrain, bodies of water, prevalent plant life, powerful minerals, "
                "the presence of peoples, and mighty fey, elementals, aberrations, "
                "or undead. (Divination ritual.)",
    casting_time="1 minute", range="self (3-mile radius)", components="V, S",
    ritual=True))
register_spell(Spell("Conjure Elemental", 5, SpellSchool.CONJURATION,
    description="You call forth an elemental servant — air, earth, fire, or water "
                "(CR 5 or lower at base level) — which appears in an unoccupied "
                "space in range and obeys your commands. It vanishes when the spell "
                "ends or its hit points reach 0; if concentration ends early the "
                "elemental turns hostile. (Upcasting raises the maximum CR.)",
    casting_time="1 minute", range="90 feet", components="V, S, M",
    material_description="burning incense for air, soft clay for earth, sulfur and phosphorus for fire, or water and sand for water, which the spell consumes",
    concentration=True, duration="up to 1 hour"))
register_spell(Spell("Contact Other Plane", 5, SpellSchool.DIVINATION,
    description="You mentally contact a demigod, the spirit of a long-dead sage, "
                "or some other mysterious entity and may ask up to five questions "
                "that receive one-word answers. You must make a DC 15 Wisdom save; "
                "on a failure you take 6d6 psychic damage and are insane until your "
                "next long rest (you cannot cast spells or take reactions). "
                "(Divination ritual; the caster's self-risk is documented, not "
                "modeled.)",
    casting_time="1 minute", range="self", components="V",
    ritual=True))
register_spell(Spell("Creation", 5, SpellSchool.ILLUSION,
    description="You pull wisps of shadow material from the Shadowfell to create a "
                "nonliving object of vegetable matter within range — soft goods, "
                "rope, wood, or even a mineral object. The created object's "
                "duration depends on its material (vegetable matter lasts longest; "
                "minerals last mere minutes). Larger objects require higher slots.",
    casting_time="1 minute", range="30 feet", components="V, S, M",
    material_description="a tiny piece of matter of the same type as the item you plan to create"))
register_spell(Spell("Dispel Evil and Good", 5, SpellSchool.ABJURATION,
    description="Shimmering energy surrounds you, granting protection against "
                "celestials, elementals, fey, fiends, and undead: you have "
                "advantage on saves against their spells and abilities and they "
                "have disadvantage on attacks against you. As an action you may end "
                "the spell to break enchantment on yourself, dismiss one such "
                "creature to its home plane, or end one effect causing you to be "
                "charmed, frightened, or possessed.",
    casting_time="1 action", range="self", components="V, S, M",
    material_description="holy water or powdered silver and iron",
    concentration=True, duration="up to 10 minutes"))
register_spell(Spell("Dream", 5, SpellSchool.ILLUSION,
    description="You or a willing creature you touch enters a trance and projects "
                "a messenger into the dreams of a creature you know. The messenger "
                "delivers a message of any length and may converse with the "
                "sleeping target, who remembers it perfectly on waking. The "
                "nightmare option deals 3d6 psychic damage and prevents rest. "
                "(Range: special — the target can be on any plane.)",
    casting_time="1 minute", range="special", components="V, S, M",
    material_description="a handful of sand, a few drops of ink, and a pen, plus rose petals or a cricket",
    concentration=True, duration="10 minutes"))
register_spell(Spell("Hallow", 5, SpellSchool.EVOCATION,
    description="You bless an area around a fixed point you touch, creating a "
                "60-foot-radius sanctuary suffused with divine power for as long as "
                "it remains undisrupted. You may bind one secondary effect to the "
                "hallowed ground (Courage, Darkness, Daylight, Energy Protection, "
                "Energy Suppression, Extradimensional Interference, Fog, Sounds, "
                "or Tongues). Celestials, elementals, fey, fiends, and undead "
                "cannot enter without an invitation.",
    casting_time="24 hours", range="touch", components="V, S, M",
    material_description="herbs, oils, and incense worth at least 1000 gp, which the spell consumes"))
register_spell(Spell("Legend Lore", 5, SpellSchool.DIVINATION,
    description="You name or describe a person, place, or object and bring to mind "
                "a brief summary of the significant lore about it — its history, "
                "mythic properties, secrets, and the like. The more information you "
                "already possess, the more precise and detailed the lore.",
    casting_time="10 minutes", range="self", components="V, S, M",
    material_description="incense worth 250 gp that is consumed, plus four ivory strips worth 50 gp each"))
register_spell(Spell("Passwall", 5, SpellSchool.TRANSMUTATION,
    description="A passage appears at a point on a wooden, plaster, or stone "
                "surface you choose within range, large enough for Medium "
                "creatures to walk through single file. The passage does not "
                "compromise the structure's integrity and closes after the "
                "duration, sealing anything inside.",
    casting_time="1 action", range="120 feet", components="V, S, M",
    material_description="a pinch of sesame seeds",
    duration="1 hour"))
register_spell(Spell("Raise Dead", 5, SpellSchool.NECROMANCY,
    description="You return a dead creature you touch to life, provided it has "
                "been dead no longer than ten days and its body is mostly intact. "
                "It returns with 1 hit point and is incapacitated, regaining "
                "function over 1d4 days; for a week its attacks, ability checks, "
                "and saving throws are reduced. Cannot restore missing body parts "
                "or revive undead.",
    casting_time="1 hour", range="touch", components="V, S, M",
    material_description="a diamond worth at least 500 gp, which the spell consumes"))
register_spell(Spell("Reincarnate", 5, SpellSchool.TRANSMUTATION,
    description="You touch a dead humanoid or a piece of one that has been dead no "
                "longer than ten days. The spell forms a new adult body for it and "
                "calls the soul to return — if willing. The creature returns in a "
                "randomly-determined new race (rolled on the Reincarnation table), "
                "keeping its personality and class but gaining the new race's "
                "traits.",
    casting_time="1 hour", range="touch", components="V, S, M",
    material_description="rare oils and unguents worth at least 1000 gp, which the spell consumes"))
register_spell(Spell("Swift Quiver", 5, SpellSchool.TRANSMUTATION,
    description="You transmute your quiver so it produces an endless supply of "
                "nonmagical ammunition. While the spell lasts, on each of your "
                "turns you may use a bonus action to make two attacks with a weapon "
                "that uses ammunition from the quiver, in addition to your normal "
                "action.",
    casting_time="1 bonus action", range="touch", components="V, S, M",
    material_description="a quiver containing at least one piece of ammunition",
    concentration=True, duration="up to 1 minute"))
register_spell(Spell("Teleportation Circle", 5, SpellSchool.CONJURATION,
    description="You draw a 10-foot circle on the ground, linking it to a "
                "permanent teleportation circle whose sigil sequence you know. Any "
                "creature inside the circle when you finish casting is transported "
                "to the destination circle. Mishaps are possible if the sequence is "
                "unfamiliar; permanent circles exist in major temples, guildhalls, "
                "and towers.",
    casting_time="1 minute", range="10 feet", components="V, M",
    material_description="rare chalks and inks worth at least 50 gp each, which the spell consumes",
    duration="1 round"))
register_spell(Spell("Tree Stride", 5, SpellSchool.CONJURATION,
    description="You enter a living tree within range and instantly teleport to "
                "another tree of the same kind within 500 feet. You may continue "
                "moving from tree to tree on subsequent turns (spending 5 feet of "
                "movement each time) until the spell ends. The trees must be living "
                "and Large or larger.",
    casting_time="1 action", range="self", components="V, S",
    concentration=True, duration="up to 1 minute"))

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
