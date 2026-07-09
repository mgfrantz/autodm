"""
Trap & hazard engine (DMG ch.5: "Traps").

Pure data classes and resolution logic for DnD 5e mechanical and magical traps.
No database or HTTP concerns — those live in ``app.api.traps``.

Key concepts
------------
* **Trap** — an immutable template (detection DC, disarm DC, effects, severity).
* **TrapInstance** — a trap placed in the world with mutable state
  (discovered / disarmed / triggered).
* **TrapInteraction** — the result of an attempt to *detect*, *disarm*, or
  *trigger* a trap (including damage and conditions applied).

Severity bands follow the DMG:
  * setback  — DC 10-11, light damage
  * dangerous — DC 12-19, moderate damage
  * deadly    — DC 18-20+, heavy / save-or-die
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TrapType(str, Enum):
    MECHANICAL = "mechanical"
    MAGICAL = "magical"


class TrapSeverity(str, Enum):
    SETBACK = "setback"
    DANGEROUS = "dangerous"
    DEADLY = "deadly"


class TrapEffectType(str, Enum):
    DAMAGE = "damage"
    CONDITION = "condition"
    TELEPORT = "teleport"
    SUMMON = "summon"
    TELEKINESIS = "telekinesis"


# ---------------------------------------------------------------------------
# Dice helper (kept self-contained so the engine is pure / importable in tests)
# ---------------------------------------------------------------------------

_DICE_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$")


def roll_dice(expression: str, roller: Optional[Any] = None) -> int:
    """Roll a dice expression like ``3d6`` or ``2d8+4``.

    ``roller`` may be a callable ``(num_dice, num_sides) -> list[int]`` for
    deterministic tests; otherwise ``random`` is used.
    """
    import random as _random

    m = _DICE_RE.match(expression.strip())
    if not m:
        raise ValueError(f"Invalid dice expression: {expression!r}")
    num = int(m.group(1))
    sides = int(m.group(2))
    mod = int(m.group(3) or 0)

    if roller is not None:
        rolls = roller(num, sides)
    else:
        rolls = [_random.randint(1, sides) for _ in range(num)]

    return sum(rolls) + mod


# ---------------------------------------------------------------------------
# Effect
# ---------------------------------------------------------------------------

@dataclass
class TrapEffect:
    """A single outcome applied when a trap is triggered."""
    type: TrapEffectType = TrapEffectType.DAMAGE
    # damage
    damage_dice: str = ""            # e.g. "3d6"
    damage_type: str = ""            # e.g. "piercing"
    save_ability: str = ""           # e.g. "dexterity" (empty = no save)
    save_dc: int = 0
    save_result: str = "half"        # "half" | "none" | "full" (on successful save)
    # condition
    condition: str = ""              # e.g. "restrained"
    condition_duration: int = 0      # rounds (0 = permanent until removed)
    # misc
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "damage_dice": self.damage_dice,
            "damage_type": self.damage_type,
            "save_ability": self.save_ability,
            "save_dc": self.save_dc,
            "save_result": self.save_result,
            "condition": self.condition,
            "condition_duration": self.condition_duration,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TrapEffect":
        return cls(
            type=TrapEffectType(d.get("type", "damage")),
            damage_dice=d.get("damage_dice", ""),
            damage_type=d.get("damage_type", ""),
            save_ability=d.get("save_ability", ""),
            save_dc=d.get("save_dc", 0),
            save_result=d.get("save_result", "half"),
            condition=d.get("condition", ""),
            condition_duration=d.get("condition_duration", 0),
            description=d.get("description", ""),
        )


# ---------------------------------------------------------------------------
# Trap (immutable template)
# ---------------------------------------------------------------------------

@dataclass
class Trap:
    """An immutable trap template."""
    id: str
    name: str
    description: str
    trap_type: TrapType = TrapType.MECHANICAL
    severity: TrapSeverity = TrapSeverity.DANGEROUS
    detection_dc: int = 12          # Passive/active Perception to notice
    disarm_dc: int = 12             # Thieves' tools or ability check DC
    trigger: str = ""               # human-readable trigger description
    effects: List[TrapEffect] = field(default_factory=list)
    countermeasure: str = ""        # how to bypass without disarming
    # size category of the trap area
    area: str = ""                  # e.g. "5-ft square", "10-ft corridor"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "trap_type": self.trap_type.value,
            "severity": self.severity.value,
            "detection_dc": self.detection_dc,
            "disarm_dc": self.disarm_dc,
            "trigger": self.trigger,
            "effects": [e.to_dict() for e in self.effects],
            "countermeasure": self.countermeasure,
            "area": self.area,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Trap":
        effects_data = d.get("effects", [])
        # Accept dicts or TrapEffect objects
        effects = []
        for e in effects_data:
            if isinstance(e, TrapEffect):
                effects.append(e)
            else:
                effects.append(TrapEffect.from_dict(e))
        return cls(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            trap_type=TrapType(d.get("trap_type", "mechanical")),
            severity=TrapSeverity(d.get("severity", "dangerous")),
            detection_dc=d.get("detection_dc", 12),
            disarm_dc=d.get("disarm_dc", 12),
            trigger=d.get("trigger", ""),
            effects=effects,
            countermeasure=d.get("countermeasure", ""),
            area=d.get("area", ""),
        )


# ---------------------------------------------------------------------------
# TrapInstance (mutable, placed in world)
# ---------------------------------------------------------------------------

@dataclass
class TrapInstance:
    """A trap placed in the game world with mutable state."""
    trap_id: str
    trap: Trap
    location: str = ""
    discovered: bool = False
    disarmed: bool = False
    triggered: bool = False
    trigger_count: int = 0           # how many times it has triggered

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trap_id": self.trap_id,
            "trap": self.trap.to_dict(),
            "location": self.location,
            "discovered": self.discovered,
            "disarmed": self.disarmed,
            "triggered": self.triggered,
            "trigger_count": self.trigger_count,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TrapInstance":
        trap_data = d.get("trap", {})
        trap = Trap.from_dict(trap_data) if isinstance(trap_data, dict) else trap_data
        return cls(
            trap_id=d.get("trap_id", trap.id if isinstance(trap, Trap) else ""),
            trap=trap,
            location=d.get("location", ""),
            discovered=d.get("discovered", False),
            disarmed=d.get("disarmed", False),
            triggered=d.get("triggered", False),
            trigger_count=d.get("trigger_count", 0),
        )

    @classmethod
    def from_trap(cls, trap: Trap, location: str = "") -> "TrapInstance":
        """Create a fresh instance from a trap template."""
        return cls(trap_id=trap.id, trap=trap, location=location)


# ---------------------------------------------------------------------------
# Interaction results
# ---------------------------------------------------------------------------

@dataclass
class DetectionResult:
    """Result of attempting to detect a trap."""
    success: bool
    roll: int
    perception_total: int       # roll + modifier
    dc: int
    discovered: bool            # whether the trap is now discovered
    narrative: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "roll": self.roll,
            "perception_total": self.perception_total,
            "dc": self.dc,
            "discovered": self.discovered,
            "narrative": self.narrative,
        }


@dataclass
class DisarmResult:
    """Result of attempting to disarm a trap."""
    success: bool
    roll: int
    check_total: int            # roll + modifier
    dc: int
    disarmed: bool
    method: str = "thieves_tools"   # "thieves_tools", "strength", "arcana", etc.
    narrative: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "roll": self.roll,
            "check_total": self.check_total,
            "dc": self.dc,
            "disarmed": self.disarmed,
            "method": self.method,
            "narrative": self.narrative,
        }


@dataclass
class TriggerResult:
    """Result of a trap being triggered."""
    triggered: bool
    damage: int = 0
    damage_type: str = ""
    save_ability: str = ""
    save_dc: int = 0
    save_success: bool = False       # whether the save (if any) succeeded
    conditions: List[str] = field(default_factory=list)
    effect_descriptions: List[str] = field(default_factory=list)
    narrative: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "triggered": self.triggered,
            "damage": self.damage,
            "damage_type": self.damage_type,
            "save_ability": self.save_ability,
            "save_dc": self.save_dc,
            "save_success": self.save_success,
            "conditions": list(self.conditions),
            "effect_descriptions": list(self.effect_descriptions),
            "narrative": self.narrative,
        }


# ---------------------------------------------------------------------------
# Resolution functions
# ---------------------------------------------------------------------------

def attempt_detection(
    instance: TrapInstance,
    perception_total: int,
    roll: int = 0,
) -> DetectionResult:
    """Attempt to detect a trap.

    ``perception_total`` is the full check result (roll + WIS modifier +
    proficiency).  ``roll`` is the raw d20 (for narration).
    """
    if instance.disarmed:
        return DetectionResult(
            success=False, roll=roll, perception_total=perception_total,
            dc=instance.trap.detection_dc, discovered=False,
            narrative="The trap has already been disarmed.",
        )

    success = perception_total >= instance.trap.detection_dc
    if success:
        instance.discovered = True

    if success:
        narrative = (f"You spot a {instance.trap.name}! "
                      f"({perception_total} vs DC {instance.trap.detection_dc}) "
                      f"{instance.trap.description}")
    else:
        narrative = (f"You don't notice anything unusual. "
                      f"({perception_total} vs DC {instance.trap.detection_dc})")

    return DetectionResult(
        success=success,
        roll=roll,
        perception_total=perception_total,
        dc=instance.trap.detection_dc,
        discovered=instance.discovered,
        narrative=narrative,
    )


def check_passive_perception(
    instance: TrapInstance,
    passive_perception: int,
) -> bool:
    """Check whether passive Perception notices the trap."""
    if instance.discovered or instance.disarmed:
        return True
    if passive_perception >= instance.trap.detection_dc:
        instance.discovered = True
        return True
    return False


def attempt_disarm(
    instance: TrapInstance,
    check_total: int,
    roll: int = 0,
    method: str = "thieves_tools",
) -> DisarmResult:
    """Attempt to disarm a trap.

    ``check_total`` is the full check result.  ``method`` describes how
    (thieves' tools, Strength, Arcana, etc.) for narration.
    """
    if instance.disarmed:
        return DisarmResult(
            success=True, roll=roll, check_total=check_total,
            dc=instance.trap.disarm_dc, disarmed=True, method=method,
            narrative="The trap is already disarmed.",
        )

    if not instance.discovered:
        return DisarmResult(
            success=False, roll=roll, check_total=check_total,
            dc=instance.trap.disarm_dc, disarmed=False, method=method,
            narrative="You can't disarm a trap you haven't found.",
        )

    success = check_total >= instance.trap.disarm_dc
    if success:
        instance.disarmed = True

    if success:
        narrative = (f"You successfully disarm the {instance.trap.name}! "
                      f"({check_total} vs DC {instance.trap.disarm_dc})")
    else:
        # A failed disarm has a 50% chance to trigger the trap (DMG guidance)
        narrative = (f"Your attempt to disarm the {instance.trap.name} fails. "
                      f"({check_total} vs DC {instance.trap.disarm_dc})")

    return DisarmResult(
        success=success,
        roll=roll,
        check_total=check_total,
        dc=instance.trap.disarm_dc,
        disarmed=instance.disarmed,
        method=method,
        narrative=narrative,
    )


def trigger_trap(
    instance: TrapInstance,
    save_roll: Optional[int] = None,
    save_modifier: int = 0,
    roller: Optional[Any] = None,
) -> TriggerResult:
    """Trigger a trap and resolve its effects.

    ``save_roll`` (raw d20) and ``save_modifier`` apply to the trap's save
    (if any).  If the trap has no save, these are ignored.  ``roller`` is
    an optional deterministic dice roller ``(num_dice, num_sides) -> list[int]``.
    """
    if instance.disarmed:
        return TriggerResult(
            triggered=False,
            narrative="The trap was already disarmed — nothing happens.",
        )

    instance.triggered = True
    instance.trigger_count += 1

    total_damage = 0
    damage_type = ""
    conditions: List[str] = []
    effect_descs: List[str] = []
    save_ability = ""
    save_dc = 0
    save_success = False

    for effect in instance.trap.effects:
        if effect.type == TrapEffectType.DAMAGE:
            # Resolve save first (if any)
            if effect.save_ability and effect.save_dc:
                save_ability = effect.save_ability
                save_dc = effect.save_dc
                if save_roll is not None:
                    save_total = save_roll + save_modifier
                    save_success = save_total >= effect.save_dc
                else:
                    # No roll provided — treat as failed save
                    save_success = False

            # Roll damage
            if effect.damage_dice:
                dmg = roll_dice(effect.damage_dice, roller=roller)
                if save_success:
                    if effect.save_result == "half":
                        dmg = dmg // 2
                    elif effect.save_result == "none":
                        dmg = 0
                    # "full" = take full damage even on save
                total_damage += dmg
                damage_type = effect.damage_type or damage_type

            desc = f"{effect.damage_dice} {effect.damage_type} damage"
            if save_success and effect.save_result == "half":
                desc += f" (halved by {effect.save_ability} save)"
            elif save_success and effect.save_result == "none":
                desc += f" (negated by {effect.save_ability} save)"
            effect_descs.append(desc)

        elif effect.type == TrapEffectType.CONDITION:
            if effect.save_ability and effect.save_dc:
                save_ability = effect.save_ability
                save_dc = effect.save_dc
                if save_roll is not None:
                    save_success = save_roll + save_modifier >= effect.save_dc
                else:
                    save_success = False

            if not save_success:
                conditions.append(effect.condition)
                dur = f" for {effect.condition_duration} rounds" if effect.condition_duration else ""
                effect_descs.append(f"applies {effect.condition}{dur}")
            else:
                effect_descs.append(f"{effect.condition} resisted ({effect.save_ability} save)")

        elif effect.type in (TrapEffectType.TELEPORT, TrapEffectType.SUMMON,
                             TrapEffectType.TELEKINESIS):
            effect_descs.append(effect.description or effect.type.value)

    # Build narrative
    parts = [f"The {instance.trap.name} triggers!"]
    if instance.trap.trigger:
        parts.append(instance.trap.trigger)
    if total_damage > 0:
        parts.append(f"{total_damage} {damage_type} damage")
    for c in conditions:
        parts.append(f"afflicted with {c}")
    parts.extend(effect_descs)

    return TriggerResult(
        triggered=True,
        damage=total_damage,
        damage_type=damage_type,
        save_ability=save_ability,
        save_dc=save_dc,
        save_success=save_success,
        conditions=conditions,
        effect_descriptions=effect_descs,
        narrative=" ".join(parts),
    )


def failed_disarm_triggers(instance: TrapInstance) -> bool:
    """DMG guidance: a failed disarm check has a chance to trigger the trap.

    For game purposes we treat this as True — a critical failure (nat 1) or
    a miss by 5+ triggers the trap.  The API can roll for this.
    """
    return True


# ---------------------------------------------------------------------------
# Registry — DMG sample traps + common hazards
# ---------------------------------------------------------------------------

def _dmg_damage(dice: str, dtype: str, save: str = "", dc: int = 0,
                save_result: str = "half") -> TrapEffect:
    return TrapEffect(
        type=TrapEffectType.DAMAGE,
        damage_dice=dice,
        damage_type=dtype,
        save_ability=save,
        save_dc=dc,
        save_result=save_result,
    )


def _dmg_condition(cond: str, save: str, dc: int, dur: int = 0,
                   desc: str = "") -> TrapEffect:
    return TrapEffect(
        type=TrapEffectType.CONDITION,
        condition=cond,
        save_ability=save,
        save_dc=dc,
        condition_duration=dur,
        description=desc,
    )


TRAP_REGISTRY: Dict[str, Trap] = {
    # ---- Mechanical traps (DMG ch.5) ----
    "collapsing_roof": Trap(
        id="collapsing_roof",
        name="Collapsing Roof",
        description="A weakened ceiling section gives way, burying those below in rubble.",
        trap_type=TrapType.MECHANICAL,
        severity=TrapSeverity.DANGEROUS,
        detection_dc=15,
        disarm_dc=15,
        trigger="Stepping on a loose floor tile drops the ceiling supports.",
        effects=[
            _dmg_damage("3d6", "bludgeoning", save="dexterity", dc=15,
                        save_result="half"),
            _dmg_condition("restrained", save="strength", dc=15, dur=0,
                           desc="Pinned under rubble"),
        ],
        countermeasure="A Wedge or piton driven into the trigger tile prevents collapse.",
        area="10-ft square",
    ),
    "falling_net": Trap(
        id="falling_net",
        name="Falling Net",
        description="A heavy net of rope and iron weights drops from above.",
        trap_type=TrapType.MECHANICAL,
        severity=TrapSeverity.SETBACK,
        detection_dc=10,
        disarm_dc=10,
        trigger="A tripwire releases the net.",
        effects=[
            _dmg_condition("restrained", save="dexterity", dc=10, dur=0,
                           desc="Tangled in the net"),
        ],
        countermeasure="Cut or avoid the tripwire; DC 10 Dexterity to escape the net.",
        area="10-ft square",
    ),
    "fire_breathing_statue": Trap(
        id="fire_breathing_statue",
        name="Fire-Breathing Statue",
        description="A stone statue's mouth opens and unleashes a gout of flame.",
        trap_type=TrapType.MAGICAL,
        severity=TrapSeverity.DANGEROUS,
        detection_dc=15,
        disarm_dc=15,
        trigger="Entering the statue's line of sight.",
        effects=[
            _dmg_damage("6d6", "fire", save="dexterity", dc=15,
                        save_result="half"),
        ],
        countermeasure="Cover the statue's mouth, dispel magic, or avoid its gaze line.",
        area="15-ft cone",
    ),
    "hidden_pit": Trap(
        id="hidden_pit",
        name="Hidden Pit",
        description="A concealed pit opens beneath the unwary.",
        trap_type=TrapType.MECHANICAL,
        severity=TrapSeverity.SETBACK,
        detection_dc=12,
        disarm_dc=12,
        trigger="Stepping on the hinged cover.",
        effects=[
            _dmg_damage("1d6", "bludgeoning", save="", dc=0, save_result="full"),
        ],
        countermeasure="Pound a piton to wedge the cover or avoid the flagged area.",
        area="10-ft square, 20-ft deep",
    ),
    "poison_darts": Trap(
        id="poison_darts",
        name="Poison Darts",
        description="A wall panel slides open and darts shoot out.",
        trap_type=TrapType.MECHANICAL,
        severity=TrapSeverity.DANGEROUS,
        detection_dc=15,
        disarm_dc=15,
        trigger="A pressure plate launches the darts.",
        effects=[
            _dmg_damage("2d10", "piercing", save="dexterity", dc=15,
                        save_result="half"),
            _dmg_condition("poisoned", save="constitution", dc=15, dur=60,
                           desc="Dart delivers a debilitating toxin"),
        ],
        countermeasure="Block the dart holes or wedge the pressure plate.",
        area="5-ft-wide corridor",
    ),
    "poisoned_needle": Trap(
        id="poisoned_needle",
        name="Poisoned Needle",
        description="A tiny needle springs from a lock or small object.",
        trap_type=TrapType.MECHANICAL,
        severity=TrapSeverity.SETBACK,
        detection_dc=13,
        disarm_dc=12,
        trigger="Opening the trapped container or picking the lock carelessly.",
        effects=[
            _dmg_damage("1d10", "piercing", save="dexterity", dc=13,
                        save_result="none"),
        ],
        countermeasure="Detect with Investigation before opening; disarm at the lock.",
        area="Single target",
    ),
    "rolling_sphere": Trap(
        id="rolling_sphere",
        name="Rolling Sphere",
        description="A massive stone sphere rolls down a corridor, crushing all in its path.",
        trap_type=TrapType.MECHANICAL,
        severity=TrapSeverity.DEADLY,
        detection_dc=18,
        disarm_dc=20,
        trigger="Stepping on a pressure plate releases the sphere from its alcove.",
        effects=[
            _dmg_damage("4d10", "bludgeoning", save="dexterity", dc=20,
                        save_result="half"),
            _dmg_condition("prone", save="strength", dc=18, dur=0,
                           desc="Knocked flat by the sphere"),
        ],
        countermeasure="A side niche offers refuge; jamming the alcove door stops it.",
        area="10-ft-wide corridor, 60 ft long",
    ),
    "swinging_blade": Trap(
        id="swinging_blade",
        name="Swinging Blade",
        description="A massive crescent blade swings down from the ceiling.",
        trap_type=TrapType.MECHANICAL,
        severity=TrapSeverity.DANGEROUS,
        detection_dc=13,
        disarm_dc=13,
        trigger="A tripwire releases the pendulum blade.",
        effects=[
            _dmg_damage("3d6", "slashing", save="dexterity", dc=13,
                        save_result="half"),
        ],
        countermeasure="Cut the tripwire or dodge past in the blade's upswing.",
        area="5-ft-wide corridor",
    ),
    "flood_room": Trap(
        id="flood_room",
        name="Flooding Room",
        description="Water pours in from hidden sluices, flooding the chamber.",
        trap_type=TrapType.MECHANICAL,
        severity=TrapSeverity.DANGEROUS,
        detection_dc=15,
        disarm_dc=15,
        trigger="A pressure plate opens the floodgates.",
        effects=[
            _dmg_condition("restrained", save="strength", dc=13, dur=0,
                           desc="Struggling against rising water"),
        ],
        countermeasure="Block the sluices or find the drainage switch.",
        area="30-ft-square room",
    ),
    # ---- Magical traps (DMG ch.5) ----
    "teleportation_trap": Trap(
        id="teleportation_trap",
        name="Teleportation Trap",
        description="A magical circle flares, whisking the victim away.",
        trap_type=TrapType.MAGICAL,
        severity=TrapSeverity.DANGEROUS,
        detection_dc=15,
        disarm_dc=15,
        trigger="Stepping into the rune circle.",
        effects=[
            TrapEffect(
                type=TrapEffectType.TELEPORT,
                description="Teleported to a random location within 100 feet (or into a pit).",
                save_ability="charisma",
                save_dc=15,
                save_result="none",
            ),
        ],
        countermeasure="Dispel magic (DC 15) or cover the runes.",
        area="5-ft circle",
    ),
    "sphere_of_annihilation": Trap(
        id="sphere_of_annihilation",
        name="Sphere of Annihilation",
        description="A tiny black sphere hungers to consume all matter.",
        trap_type=TrapType.MAGICAL,
        severity=TrapSeverity.DEADLY,
        detection_dc=20,
        disarm_dc=25,
        trigger="Approaching within 5 feet of the sphere.",
        effects=[
            TrapEffect(
                type=TrapEffectType.DAMAGE,
                damage_dice="10d10",
                damage_type="force",
                save_ability="dexterity",
                save_dc=20,
                save_result="half",
                description="The sphere's pull threatens to annihilate.",
            ),
        ],
        countermeasure="A talisman of the sphere grants control; otherwise avoid entirely.",
        area="2-ft-diameter sphere",
    ),
    "glyph_of_warding": Trap(
        id="glyph_of_warding",
        name="Glyph of Warding",
        description="A potent magical glyph inscribed on a surface, ready to unleash stored magic.",
        trap_type=TrapType.MAGICAL,
        severity=TrapSeverity.DANGEROUS,
        detection_dc=15,
        disarm_dc=15,
        trigger="Entering, opening, or reading the warded area.",
        effects=[
            _dmg_damage("5d8", "acid", save="dexterity", dc=15,
                        save_result="half"),
        ],
        countermeasure="Dispel magic (DC 15) or avoid the warded surface.",
        area="5-ft radius",
    ),
    "gas_trap": Trap(
        id="gas_trap",
        name="Poison Gas Trap",
        description="Vents in the wall release a cloud of noxious gas.",
        trap_type=TrapType.MECHANICAL,
        severity=TrapSeverity.DANGEROUS,
        detection_dc=13,
        disarm_dc=13,
        trigger="A pressure plate opens gas vents.",
        effects=[
            _dmg_condition("poisoned", save="constitution", dc=13, dur=60,
                           desc="Choking green gas fills the corridor"),
        ],
        countermeasure="Cover the vents or hold your breath (limited rounds).",
        area="20-ft-square cloud",
    ),
    "bear_trap": Trap(
        id="bear_trap",
        name="Bear Trap",
        description="A steel-jawed trap hidden under leaves or debris.",
        trap_type=TrapType.MECHANICAL,
        severity=TrapSeverity.SETBACK,
        detection_dc=13,
        disarm_dc=12,
        trigger="Stepping on the pressure plate.",
        effects=[
            _dmg_damage("2d4", "piercing", save="", dc=0, save_result="full"),
            _dmg_condition("restrained", save="strength", dc=13, dur=0,
                           desc="Jaws clamped around the leg"),
        ],
        countermeasure="Spot it and step around, or pry the jaws open.",
        area="Single target",
    ),
}


def get_trap(trap_id: str) -> Optional[Trap]:
    """Look up a trap template by ID."""
    return TRAP_REGISTRY.get(trap_id)


def list_traps(trap_type: Optional[TrapType] = None,
               severity: Optional[TrapSeverity] = None) -> List[Trap]:
    """List all traps, optionally filtered by type and/or severity."""
    result = []
    for trap in TRAP_REGISTRY.values():
        if trap_type and trap.trap_type != trap_type:
            continue
        if severity and trap.severity != severity:
            continue
        result.append(trap)
    return result


def list_trap_ids() -> List[str]:
    """List all trap IDs."""
    return sorted(TRAP_REGISTRY.keys())


def traps_by_severity(severity: TrapSeverity) -> List[Trap]:
    """Get all traps of a given severity."""
    return list_traps(severity=severity)


# ---------------------------------------------------------------------------
# DM context helper
# ---------------------------------------------------------------------------

def trap_summary_for_dm(instances: List[TrapInstance]) -> str:
    """Build a one-line DM context summary for active traps in an area."""
    if not instances:
        return ""

    undiscovered = [i for i in instances if not i.discovered]
    discovered = [i for i in instances if i.discovered and not i.disarmed]

    parts = []
    if discovered:
        names = ", ".join(i.trap.name for i in discovered)
        parts.append(f"Known traps: {names}")
    if undiscovered:
        parts.append(f"{len(undiscovered)} hidden trap(s)")

    return "; ".join(parts) if parts else ""


def severity_guidelines() -> Dict[str, Dict[str, Any]]:
    """Return DMG trap severity guidelines (DCs and damage by severity)."""
    return {
        "setback": {
            "detection_dc": "10-11",
            "disarm_dc": "10-11",
            "damage": "1d10 or 2d10",
            "description": "A minor inconvenience; rarely life-threatening.",
        },
        "dangerous": {
            "detection_dc": "12-19",
            "disarm_dc": "12-19",
            "damage": "4d10 (save for half)",
            "description": "Can seriously injure or kill a careless adventurer.",
        },
        "deadly": {
            "detection_dc": "18-20+",
            "disarm_dc": "20+",
            "damage": "10d10+ or save-or-die",
            "description": "Lethal; often requires high-level abilities to survive.",
        },
    }
