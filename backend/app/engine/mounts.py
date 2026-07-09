"""
Mounts & vehicles engine — DnD 5e mounted travel and mounted combat.

Covers the three things the game's navigation + combat loops need from a mount:

1. **Overland travel speed.** A mount (or a vehicle pulled by draft animals)
   multiplies how far the party travels in a day. A walking adventurer covers
   the baseline 24 miles/day (``WALKING_SPEED_FT = 30``); a mount of speed *S*
   scales distance by ``S / 30``. Travel *pace* (slow / normal / fast) layers a
   second multiplier on top and carries its own PHB side-effects (fast pace =
   −5 passive Perception; slow pace = can Stealth). Mounts can also *gallop*
   for a short daily burst, covering extra distance for ~1 hour/day (PHB).

2. **Mounted combat modifiers.** Per PHB ch.9 "Mounted Combat": a rider has
   advantage on melee attack rolls against unmounted creatures smaller than the
   mount, costs half their movement to mount/dismount, and uses the mount's
   space; the ``Mounted Combatant`` feat additionally lets the rider redirect
   attacks aimed at the mount onto themselves and grants the mount evasion-style
   Dexterity-save advantage.

3. **Weapon rules while mounted.** Some weapons behave differently astride a
   mount — the lance is the canonical example (one-handed on a mount, two-handed
   on foot, reach but disadvantage within 5 ft). ``weapon_mounted_rules()``
   returns the adjudication notes a DM / combat layer needs.

The module is **pure** (no DB, no LLM) so it is trivially unit-testable. Mount
*state* (which mount is currently acquired, its HP, whether the rider is
mounted) is persisted by the API layer inside ``game_state["mount"]``.

References: Player's Handbook ch.5 (mounts/equipment), ch.8 (travel pace), ch.9
(mounted combat); Monster Manual (mount stat blocks); Dungeon Master's Guide.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Constants — sizes, paces, baseline walking speed.
# --------------------------------------------------------------------------- #

#: Reference walking speed (a Medium adventurer with 30 ft speed) used to derive
#: the overland-travel multiplier of a faster mount.
WALKING_SPEED_FT: int = 30

#: Travel-pace multipliers and their PHB side-effects (PHB ch.8 "Travel Pace").
#:   slow   → 18 miles/day, can travel Stealthily
#:   normal → 24 miles/day
#:   fast   → 30 miles/day, −5 to passive Perception (greater chance of surprise)
PACE_MULTIPLIERS: dict[str, float] = {
    "slow": 18.0 / 24.0,   # ≈ 0.75
    "normal": 1.0,
    "fast": 30.0 / 24.0,   # ≈ 1.25
}

#: How far a mount's speed-based multiplier may push daily distance (4× afoot).
MAX_MOUNT_SPEED_MULT: float = 4.0
#: Floor for the speed-based multiplier (a slow beast of burden).
MIN_MOUNT_SPEED_MULT: float = 0.5

#: A mount can sustain a gallop for roughly this long per day (PHB: "a mounted
#: character can ride a galloping mount for about an hour, twice the distance").
GALLOP_BURST_HOURS: float = 1.0
#: Galloping covers roughly double distance for the burst.
GALLOP_BURST_MULT: float = 2.0

#: Creature-size carrying-capacity multipliers (DnD 5e: STR × 15, doubled per
#: size category above Medium, halved per category below).
SIZE_CARRY_MULT: dict[str, float] = {
    "tiny": 0.5,
    "small": 1.0,
    "medium": 1.0,
    "large": 2.0,
    "huge": 4.0,
    "gargantuan": 8.0,
}

#: Ordered size categories (smallest → largest) for "is *a* smaller than *b*?".
SIZE_ORDER: list[str] = ["tiny", "small", "medium", "large", "huge", "gargantuan"]


def size_rank(size: str) -> int:
    """Numeric size rank (tiny=0 … gargantuan=5); unknown sizes → medium rank."""
    size = (size or "medium").lower()
    return SIZE_ORDER.index(size) if size in SIZE_ORDER else SIZE_ORDER.index("medium")


def is_smaller(a: str, b: str) -> bool:
    """True when creature of size *a* is strictly smaller than size *b*."""
    return size_rank(a) < size_rank(b)


def pace_multiplier(pace: str) -> float:
    """Travel-pace multiplier (slow/normal/fast). Unknown → normal."""
    return PACE_MULTIPLIERS.get((pace or "normal").lower(), 1.0)


def pace_notes(pace: str) -> str:
    """PHB side-effects of a travel pace, for the DM/UI."""
    p = (pace or "normal").lower()
    if p == "fast":
        return "Fast pace: −5 passive Perception (greater surprise risk), no Stealth."
    if p == "slow":
        return "Slow pace: the party can travel Stealthily."
    return "Normal pace: no special modifiers."


# --------------------------------------------------------------------------- #
# Mount definitions + registry.
# --------------------------------------------------------------------------- #

@dataclass
class Mount:
    """A rideable creature or vehicle (DnD 5e mount / vehicle stat block).

    Fields mirror the Monster Manual's mount stat blocks plus the few
    travel/combat properties the engine needs. ``attacks`` are the mount's own
    attacks (used when it acts independently or defends itself); for a
    *controlled* mount the rider uses only its movement.
    """

    id: str
    name: str
    type: str                       # "land" | "flying" | "aquatic" | "vehicle"
    speed: int                      # tactical speed in feet
    fly_speed: int = 0              # 0 = cannot fly
    swim_speed: int = 0             # 0 = cannot swim
    size: str = "large"
    strength: int = 16
    hp: int = 13
    armor_class: int = 10
    cr: float = 0.0
    control_type: str = "controlled"   # "controlled" | "independent"
    # Extra capacity multiplier on top of the size-derived one (e.g. the mule's
    # "Beast of Burden" trait doubles its carrying capacity).
    capacity_mult: float = 1.0
    cost_gp: float = 0.0
    attacks: list[dict] = field(default_factory=list)
    notes: str = ""
    description: str = ""

    # -- derived -------------------------------------------------------------

    @property
    def effective_speed(self) -> int:
        """Highest movement speed available (fly > swim > land) in feet."""
        return max(self.speed, self.fly_speed, self.swim_speed)

    @property
    def can_fly(self) -> bool:
        return self.fly_speed > 0

    @property
    def can_swim(self) -> bool:
        return self.swim_speed > 0

    @property
    def is_vehicle(self) -> bool:
        return self.type == "vehicle"

    @property
    def carrying_capacity_lbs(self) -> int:
        """DnD 5e carrying capacity: STR × 15 × size mult × trait mult."""
        base = self.strength * 15
        size_mult = SIZE_CARRY_MULT.get(self.size.lower(), 1.0)
        return int(base * size_mult * self.capacity_mult)

    @property
    def speed_multiplier(self) -> float:
        """Overland-travel multiplier vs. a 30 ft walker, clamped to a sane band."""
        if self.is_vehicle:
            # Vehicles travel at a fixed, modest pace set by their draft animals;
            # their listed ``speed`` already encodes that. Don't let a slow wagon
            # divide distance to nothing — clamp at the floor.
            mult = self.speed / float(WALKING_SPEED_FT)
        else:
            mult = self.effective_speed / float(WALKING_SPEED_FT)
        return max(MIN_MOUNT_SPEED_MULT, min(MAX_MOUNT_SPEED_MULT, mult))

    # -- serialization -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "speed": self.speed,
            "fly_speed": self.fly_speed,
            "swim_speed": self.swim_speed,
            "size": self.size,
            "strength": self.strength,
            "hp": self.hp,
            "armor_class": self.armor_class,
            "cr": self.cr,
            "control_type": self.control_type,
            "capacity_mult": self.capacity_mult,
            "cost_gp": self.cost_gp,
            "attacks": list(self.attacks),
            "notes": self.notes,
            "description": self.description,
            # Derived convenience fields for the UI.
            "effective_speed": self.effective_speed,
            "carrying_capacity_lbs": self.carrying_capacity_lbs,
            "speed_multiplier": round(self.speed_multiplier, 4),
            "can_fly": self.can_fly,
            "can_swim": self.can_swim,
            "is_vehicle": self.is_vehicle,
        }


# Canonical mount stat blocks (PHB ch.5 mounts & Monster Manual). Attacks use
# the same {name, attack_bonus, damage_dice, damage_bonus, damage_type, ...}
# shape as the combat engine so a mount can be turned into a Combatant.
_HOOVES = [{
    "name": "Hooves", "attack_bonus": 6, "damage_dice_count": 2,
    "damage_dice_sides": 6, "damage_bonus": 4, "damage_type": "bludgeoning",
    "ranged": False,
}]

MOUNT_REGISTRY: dict[str, Mount] = {
    # --- Land mounts (beasts of burden / war mounts) -------------------------
    "riding_horse": Mount(
        id="riding_horse", name="Riding Horse", type="land", speed=60,
        size="large", strength=16, hp=13, armor_class=10, cr=0.25,
        cost_gp=75.0, capacity_mult=1.0,
        description="A trained but non-combatant mount, bred for travel.",
    ),
    "warhorse": Mount(
        id="warhorse", name="Warhorse", type="land", speed=60,
        size="large", strength=18, hp=19, armor_class=11, cr=0.5,
        cost_gp=400.0, attacks=_HOOVES, notes="Trample: DC 14 STR save or knocked prone.",
        description="A battle-trained steed that will fight alongside its rider.",
    ),
    "draft_horse": Mount(
        id="draft_horse", name="Draft Horse", type="land", speed=40,
        size="large", strength=18, hp=19, armor_class=10, cr=0.25,
        cost_gp=50.0,
        description="A heavy, placid beast bred to pull loads.",
    ),
    "pony": Mount(
        id="pony", name="Pony", type="land", speed=40, size="medium",
        strength=15, hp=13, armor_class=10, cr=0.0, cost_gp=30.0,
        description="A small mount suited to smaller riders.",
    ),
    "mule": Mount(
        id="mule", name="Mule", type="land", speed=40, size="medium",
        strength=14, hp=11, armor_class=10, cr=0.125, cost_gp=8.0,
        capacity_mult=2.0,
        notes="Beast of Burden: counts as Large for carrying capacity.",
        description="A surefooted hybrid; stubborn but a superb pack animal.",
    ),
    "donkey": Mount(
        id="donkey", name="Donkey", type="land", speed=40, size="medium",
        strength=12, hp=8, armor_class=10, cr=0.0, cost_gp=8.0,
        capacity_mult=2.0,
        description="A cheap, hardy pack beast (Beast of Burden).",
    ),
    "camel": Mount(
        id="camel", name="Camel", type="land", speed=50, size="large",
        strength=16, hp=15, armor_class=10, cr=0.125, cost_gp=50.0,
        description="A desert mount that endures heat and scarce water.",
    ),
    "elk": Mount(
        id="elk", name="Elk", type="land", speed=50, size="large",
        strength=16, hp=15, armor_class=10, cr=0.25, cost_gp=0.0,
        attacks=_HOOVES,
        description="A swift northern herd-beast, sometimes trained to bear riders.",
    ),
    "mastiff": Mount(
        id="mastiff", name="Mastiff", type="land", speed=40, size="medium",
        strength=14, hp=5, armor_class=12, cr=0.125, cost_gp=25.0,
        attacks=[{"name": "Bite", "attack_bonus": 3, "damage_dice_count": 1,
                  "damage_dice_sides": 4, "damage_bonus": 1,
                  "damage_type": "piercing", "ranged": False}],
        description="A small dog trained to carry halflings and gnomes.",
    ),

    # --- Flying mounts -------------------------------------------------------
    "pegasus": Mount(
        id="pegasus", name="Pegasus", type="flying", speed=90, fly_speed=90,
        size="large", strength=18, hp=59, armor_class=13, cr=2.0,
        cost_gp=0.0, control_type="independent",
        description="A winged celestial horse; intelligent and hard to master.",
    ),
    "griffon": Mount(
        id="griffon", name="Griffon", type="flying", speed=80, fly_speed=80,
        size="large", strength=18, hp=59, armor_class=12, cr=2.0,
        cost_gp=0.0, control_type="independent",
        description="Half-eagle, half-lion; a fierce aerial hunter.",
    ),
    "hippogriff": Mount(
        id="hippogriff", name="Hippogriff", type="flying", speed=60, fly_speed=60,
        size="large", strength=17, hp=19, armor_class=11, cr=1.0,
        cost_gp=0.0, control_type="independent",
        description="A trainable hybrid raptor-horse that nests in high cliffs.",
    ),
    "giant_eagle": Mount(
        id="giant_eagle", name="Giant Eagle", type="flying", speed=80, fly_speed=80,
        size="large", strength=16, hp=26, armor_class=13, cr=1.0,
        cost_gp=0.0, control_type="independent",
        description="A noble, intelligent bird of prey that tolerates allied riders.",
    ),
    "giant_owl": Mount(
        id="giant_owl", name="Giant Owl", type="flying", speed=60, fly_speed=60,
        size="large", strength=14, hp=19, armor_class=12, cr=0.25,
        cost_gp=0.0, control_type="independent",
        description="A silent flier of moonlit forests; a keen-eyed night mount.",
    ),

    # --- Vehicles ------------------------------------------------------------
    "cart": Mount(
        id="cart", name="Cart", type="vehicle", speed=30, size="large",
        strength=20, hp=15, armor_class=11, cr=0.0, cost_gp=15.0,
        capacity_mult=4.0, control_type="controlled",
        description="An open two-wheeled cart drawn by a single draft animal.",
    ),
    "wagon": Mount(
        id="wagon", name="Wagon", type="vehicle", speed=30, size="huge",
        strength=22, hp=25, armor_class=11, cr=0.0, cost_gp=35.0,
        capacity_mult=4.0, control_type="controlled",
        description="A large four-wheeled wagon drawn by a team of beasts.",
    ),
    "rowboat": Mount(
        id="rowboat", name="Rowboat", type="aquatic", speed=15, swim_speed=15,
        size="medium", strength=10, hp=10, armor_class=11, cr=0.0, cost_gp=50.0,
        control_type="controlled",
        description="A small boat for calm waters; carries a few travellers.",
    ),
    "sailing_ship": Mount(
        id="sailing_ship", name="Sailing Ship", type="aquatic", speed=30,
        swim_speed=30, size="gargantuan", strength=24, hp=150, armor_class=15,
        cr=0.0, cost_gp=10000.0, capacity_mult=1.0, control_type="controlled",
        description="A deep-water vessel; the fastest long-distance travel.",
    ),
}


def get_mount(mount_id: str) -> Optional[Mount]:
    """Look up a mount definition by id (None if unknown)."""
    return MOUNT_REGISTRY.get((mount_id or "").lower())


def list_mounts(mount_type: Optional[str] = None) -> list[Mount]:
    """All registered mounts, optionally filtered by type."""
    mounts = list(MOUNT_REGISTRY.values())
    if mount_type:
        mt = mount_type.lower()
        mounts = [m for m in mounts if m.type == mt]
    return sorted(mounts, key=lambda m: (m.type, m.cost_gp, m.name))


# --------------------------------------------------------------------------- #
# Persistent mount state (what the player currently has + whether mounted).
# --------------------------------------------------------------------------- #

@dataclass
class MountState:
    """The player's current mount situation, persisted in ``game_state["mount"]``.

    A character owns at most one *active* mount at a time (the one they're
    riding or leading). Mount HP is tracked here so damage sustained in combat
    or while travelling persists; conditions likewise.
    """

    mount_id: str = ""                 # registry id of the active mount, "" = none
    current_hp: int = 0                # live HP of the active mount
    max_hp: int = 0                    # cached max HP (set on acquisition)
    mounted: bool = False              # is the rider currently astride it?
    conditions: list[str] = field(default_factory=list)  # prone, frightened, ...
    # Toggle for the current overland trip (slow/normal/fast + gallop burst).
    pace: str = "normal"
    galloping: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "mount_id": self.mount_id,
            "current_hp": self.current_hp,
            "max_hp": self.max_hp,
            "mounted": self.mounted,
            "conditions": list(self.conditions),
            "pace": self.pace,
            "galloping": self.galloping,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "MountState":
        data = data or {}

        def _str(v: Any, default: str = "") -> str:
            try:
                return str(v) if v not in (None, "") else default
            except Exception:  # noqa: BLE001
                return default

        def _int(v: Any, default: int = 0) -> int:
            try:
                return int(v)
            except (TypeError, ValueError):
                return default

        try:
            conditions = [str(c) for c in (data.get("conditions", []) or [])]
        except (TypeError, ValueError):
            conditions = []
        return cls(
            mount_id=_str(data.get("mount_id", "")),
            current_hp=max(0, _int(data.get("current_hp", 0))),
            max_hp=max(0, _int(data.get("max_hp", 0))),
            mounted=bool(data.get("mounted", False)),
            conditions=conditions,
            pace=_str(data.get("pace", "normal"), "normal") or "normal",
            galloping=bool(data.get("galloping", False)),
        )

    @property
    def has_mount(self) -> bool:
        return bool(self.mount_id) and self.mount_id in MOUNT_REGISTRY

    def mount_obj(self) -> Optional[Mount]:
        return MOUNT_REGISTRY.get(self.mount_id) if self.mount_id else None

    def is_conscious(self) -> bool:
        """A mount at 0 HP is incapacitated/downed (the rider is force-dismounted)."""
        return self.current_hp > 0


def fresh_state(mount: Mount) -> MountState:
    """Create a fresh, fully-healthy, mounted MountState for a mount."""
    return MountState(
        mount_id=mount.id,
        current_hp=mount.hp,
        max_hp=mount.hp,
        mounted=True,
    )


# --------------------------------------------------------------------------- #
# Overland travel — speed / pace / gallop.
# --------------------------------------------------------------------------- #

@dataclass
class TravelSpeed:
    """Overland-travel speed breakdown for the active mount + pace."""
    base_hours: float
    adjusted_hours: float
    pace: str
    pace_multiplier: float
    mount_multiplier: float
    galloping: bool
    multiplier: float              # total (pace × mount, before gallop)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_hours": self.base_hours,
            "adjusted_hours": self.adjusted_hours,
            "pace": self.pace,
            "pace_multiplier": round(self.pace_multiplier, 4),
            "mount_multiplier": round(self.mount_multiplier, 4),
            "galloping": self.galloping,
            "total_multiplier": round(self.multiplier, 4),
            "notes": list(self.notes),
        }


def travel_multiplier(state: MountState) -> float:
    """Combined pace × mount multiplier for the current trip.

    When there's no mount, returns the bare pace multiplier (a walking
    adventurer still picks a pace). When galloping, the burst is folded in via
    :func:`adjust_travel_hours` (which knows it only applies to the first hour).
    """
    mult = pace_multiplier(state.pace)
    mount = state.mount_obj()
    if mount is not None:
        mult *= mount.speed_multiplier
    return mult


def adjust_travel_hours(
    base_hours: float,
    state: Optional[MountState] = None,
    *,
    pace: Optional[str] = None,
    galloping: Optional[bool] = None,
) -> TravelSpeed:
    """Scale ``base_hours`` of walking travel by pace and mount speed.

    Galloping lets a mount cover roughly double distance for its one daily
    burst hour, so the first hour of the trip is halved and the remainder is
    unaffected. The result is always at least 1 hour (you can't arrive
    instantly) and rounded to a whole hour for UI display.

    Args:
        base_hours: Travel time on foot at a normal pace.
        state: Optional mount state (provides mount, pace, galloping). May be
            ``None`` for a plain walking trip.
        pace: Override the pace (slow/normal/fast).
        galloping: Override whether the mount gallops this trip.
    """
    state = state or MountState()
    pace = (pace or state.pace or "normal").lower()
    galloping = state.galloping if galloping is None else bool(galloping)

    pmult = pace_multiplier(pace)
    mount = state.mount_obj()
    mmult = mount.speed_multiplier if mount is not None else 1.0
    total = pmult * mmult
    if total <= 0:
        total = 1.0

    hours = float(base_hours) / total

    notes: list[str] = [pace_notes(pace)]
    if mount is not None:
        notes.append(
            f"{mount.name} (speed {mount.effective_speed} ft): travel ×"
            f"{mmult:.2f} vs. walking."
        )
    else:
        notes.append("On foot — no mount.")

    # Gallop burst: a mount can sustain a gallop for ~1 hour/day, covering
    # double its normal distance in that hour (PHB). We model the burst as
    # covering GALLOP_BURST_HOURS × GALLOP_BURST_MULT "mount-hours" of distance
    # in GALLOP_BURST_HOURS real hours. Only meaningful for a non-vehicle mount.
    if galloping and mount is not None and not mount.is_vehicle:
        burst_distance = GALLOP_BURST_HOURS * GALLOP_BURST_MULT  # 2 mount-hours
        if hours <= burst_distance:
            # Whole trip fits inside the gallop burst → double speed throughout.
            hours = hours / GALLOP_BURST_MULT
        else:
            # Burst covers `burst_distance` of mount-distance in GALLOP_BURST_HOURS;
            # the remainder proceeds at the normal mount-scaled speed.
            hours = GALLOP_BURST_HOURS + (hours - burst_distance)
        notes.append(
            f"Gallop: covers ~{GALLOP_BURST_MULT:.0f}× distance for the first "
            f"{GALLOP_BURST_HOURS:.0f} hour/day."
        )

    # Clamp + round: never below 1 hour.
    hours = max(1.0, hours)
    adjusted = max(1, int(math.floor(hours + 0.5)))
    return TravelSpeed(
        base_hours=float(base_hours),
        adjusted_hours=adjusted,
        pace=pace,
        pace_multiplier=pmult,
        mount_multiplier=mmult,
        galloping=galloping,
        multiplier=total,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# Mounted combat modifiers (PHB ch.9 "Mounted Combat").
# --------------------------------------------------------------------------- #

#: The Mounted Combatant feat (PHB) grants three benefits.
MOUNTED_COMBATANT_FEAT: str = "Mounted Combatant"


@dataclass
class MountedCombatModifiers:
    """Mechanical consequences of being mounted in combat.

    ``melee_advantage`` is the headline PHB benefit; the ``*_feat`` flags come
    from the Mounted Combatant feat. ``mount_downed``/``mount_prone`` flag the
    situations that force a rider off their mount.
    """

    mounted: bool
    mount_name: str
    mount_size: str
    control_type: str
    melee_advantage: bool = False          # vs. smaller unmounted creatures
    mount_dex_save_advantage: bool = False  # Mounted Combatant feat
    mount_evasion: bool = False             # Mounted Combatant feat
    can_redirect_attack_to_rider: bool = False  # Mounted Combatant feat
    has_mounted_combatant_feat: bool = False
    mount_downed: bool = False              # mount at 0 HP → forced dismount
    mount_prone: bool = False               # prone mount → rider must react
    mount_speed: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mounted": self.mounted,
            "mount_name": self.mount_name,
            "mount_size": self.mount_size,
            "control_type": self.control_type,
            "melee_advantage": self.melee_advantage,
            "mount_dex_save_advantage": self.mount_dex_save_advantage,
            "mount_evasion": self.mount_evasion,
            "can_redirect_attack_to_rider": self.can_redirect_attack_to_rider,
            "has_mounted_combatant_feat": self.has_mounted_combatant_feat,
            "mount_downed": self.mount_downed,
            "mount_prone": self.mount_prone,
            "mount_speed": self.mount_speed,
            "notes": list(self.notes),
        }


def rider_combat_modifiers(
    state: MountState,
    has_mounted_combatant_feat: bool = False,
) -> MountedCombatModifiers:
    """Compute the combat modifiers for a rider, given their mount state.

    A rider who is not actually astride a conscious mount (or who has no mount
    at all) gets a near-empty result. Otherwise the PHB mounted-combat benefit
    set is applied.
    """
    mount = state.mount_obj()
    if mount is None or not state.mounted or not state.is_conscious():
        return MountedCombatModifiers(
            mounted=False,
            mount_name=mount.name if mount and state.mounted else "",
            mount_size="",
            control_type="",
            notes=[] if mount is None else [
                f"{mount.name} is downed — you are no longer mounted."
            ] if not state.is_conscious() else ["You are not currently mounted."],
        )

    prone = "prone" in {c.lower() for c in state.conditions}
    notes: list[str] = []
    notes.append(
        f"Mounted on {mount.name} ({mount.size}, speed {mount.effective_speed} ft): "
        f"advantage on melee attacks against unmounted creatures smaller than the mount."
    )
    if mount.control_type == "controlled":
        notes.append("Controlled mount: shares your turn; may only Dash/Disengage/Dodge.")
    else:
        notes.append("Independent mount: rolls its own initiative and acts on its own turn.")
    if prone:
        notes.append("Mount is prone: you must use your reaction to dismount or fall prone.")

    mods = MountedCombatModifiers(
        mounted=True,
        mount_name=mount.name,
        mount_size=mount.size,
        control_type=mount.control_type,
        melee_advantage=True,
        mount_speed=mount.effective_speed,
        mount_prone=prone,
        has_mounted_combatant_feat=bool(has_mounted_combatant_feat),
    )
    if has_mounted_combatant_feat:
        mods.mount_dex_save_advantage = True
        mods.mount_evasion = True
        mods.can_redirect_attack_to_rider = True
        notes.append(
            "Mounted Combatant: you can redirect attacks targeting your mount to "
            "yourself; your mount has advantage on Dex saves (no damage on success, "
            "half on failure)."
        )
    mods.notes = notes
    return mods


def melee_advantage_applies(
    state: MountState,
    target_size: str = "medium",
    target_mounted: bool = False,
) -> bool:
    """PHB: a rider has advantage vs. an *unmounted* creature *smaller* than the mount.

    Returns False when the rider isn't mounted, the target is also mounted, or
    the target is the mount's size or larger.
    """
    if not state.mounted or not state.is_conscious():
        return False
    mount = state.mount_obj()
    if mount is None:
        return False
    if target_mounted:
        return False
    return is_smaller((target_size or "medium").lower(), mount.size)


# --------------------------------------------------------------------------- #
# Weapon rules while mounted.
# --------------------------------------------------------------------------- #

#: Weapons with mount-specific adjudication (PHB/DMG). Each entry lists the
#: properties that change when the wielder is astride a mount.
_WEAPON_MOUNT_RULES: dict[str, dict[str, Any]] = {
    "lance": {
        "one_handed_while_mounted": True,
        "two_handed_on_foot": True,
        "reach": True,
        "disadvantage_within_5ft": True,
        "notes": (
            "A lance is one-handed when you are mounted and two-handed on foot. "
            "It has reach, but you have disadvantage against a target within 5 ft."
        ),
    },
    "longbow": {
        "disadvantage_while_mounted": False,
        "notes": "Ranged weapons work normally from a mount (you use the mount's space).",
    },
    "shortbow": {
        "notes": "Ranged weapons work normally from a mount.",
    },
    "crossbow": {
        "notes": "Crossbows work normally from a mount (reload rules unchanged).",
    },
}


def weapon_mounted_rules(weapon_name: str) -> dict[str, Any]:
    """Return the mount-specific rules for a weapon (empty dict if none special).

    Unknown weapons get a generic "no special mounted rules" note.
    """
    key = (weapon_name or "").lower().strip()
    if key in _WEAPON_MOUNT_RULES:
        return dict(_WEAPON_MOUNT_RULES[key])
    # Substring fallback: "heavy crossbow" → crossbow, "hand crossbow" → crossbow.
    for token, rules in _WEAPON_MOUNT_RULES.items():
        if token in key:
            return dict(rules)
    return {
        "notes": f"{weapon_name or 'weapon'} has no special mounted-combat rules.",
    }


def is_lance(weapon_name: str) -> bool:
    return "lance" in (weapon_name or "").lower()


# --------------------------------------------------------------------------- #
# Dismount outcomes (mount prone / mount downed / rider knocked prone).
# --------------------------------------------------------------------------- #

@dataclass
class DismountOutcome:
    """What happens to a rider when their mount is compromised."""
    forced_dismount: bool
    rider_prone: bool
    dc: Optional[int] = None           # save DC the rider faces, if any
    save_ability: Optional[str] = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "forced_dismount": self.forced_dismount,
            "rider_prone": self.rider_prone,
            "dc": self.dc,
            "save_ability": self.save_ability,
            "message": self.message,
        }


def mount_prone_outcome(save_total: Optional[int] = None) -> DismountOutcome:
    """A prone mount: rider uses their reaction to dismount or fall prone.

    PHB: if the mount falls prone, the rider must use their reaction to
    dismount as the mount falls, or they are dismounted and fall prone in a
    space within 5 feet. Mechanically we model a DC 10 Dexterity save to land
    on their feet.
    """
    dc = 10
    if save_total is None:
        return DismountOutcome(
            forced_dismount=True,
            rider_prone=False,
            dc=dc,
            save_ability="dexterity",
            message=(
                "Your mount goes prone. Use your reaction to leap clear, or "
                f"make a DC {dc} Dexterity save to avoid falling prone within 5 feet."
            ),
        )
    success = save_total >= dc
    return DismountOutcome(
        forced_dismount=True,
        rider_prone=not success,
        dc=dc,
        save_ability="dexterity",
        message=(
            "You leap clear of your prone mount and land on your feet."
            if success else
            f"You tumble from your prone mount and fall prone (failed DC {dc} Dex save)."
        ),
    )


def mount_downed_outcome() -> DismountOutcome:
    """A mount reduced to 0 HP throws its rider automatically."""
    return DismountOutcome(
        forced_dismount=True,
        rider_prone=True,
        message="Your mount collapses beneath you — you're thrown and land prone.",
    )


def damage_mount(
    state: MountState,
    amount: int,
    *,
    save_total: Optional[int] = None,
) -> tuple[MountState, DismountOutcome, int]:
    """Apply ``amount`` damage to the active mount and resolve the outcome.

    Returns the updated state (a copy), the dismount outcome (if any), and the
    overflow damage past 0 HP (usually wasted). If the mount drops to 0 HP the
    rider is force-dismounted and knocked prone.
    """
    new_state = MountState(
        mount_id=state.mount_id,
        current_hp=state.current_hp,
        max_hp=state.max_hp,
        mounted=state.mounted,
        conditions=list(state.conditions),
        pace=state.pace,
        galloping=state.galloping,
    )
    if amount <= 0 or not new_state.has_mount:
        return new_state, DismountOutcome(forced_dismount=False, rider_prone=False,
                                          message="No damage applied."), 0

    new_state.current_hp = max(0, new_state.current_hp - int(amount))
    overflow = max(0, int(amount) - (state.current_hp)) if state.current_hp >= 0 else 0

    if new_state.current_hp == 0:
        outcome = mount_downed_outcome()
        new_state.mounted = False
        return new_state, outcome, overflow

    mount = new_state.mount_obj()
    mount_name = mount.name if mount is not None else "Mount"
    return new_state, DismountOutcome(
        forced_dismount=False, rider_prone=False,
        message=f"{mount_name} takes {amount} damage "
                f"({new_state.current_hp}/{new_state.max_hp} HP).",
    ), 0


def heal_mount(state: MountState, amount: int) -> tuple[MountState, int]:
    """Heal the active mount (clamped to max HP). Returns (new state, healed)."""
    new_state = MountState(
        mount_id=state.mount_id,
        current_hp=state.current_hp,
        max_hp=state.max_hp,
        mounted=state.mounted,
        conditions=list(state.conditions),
        pace=state.pace,
        galloping=state.galloping,
    )
    if amount <= 0 or not new_state.has_mount:
        return new_state, 0
    before = new_state.current_hp
    new_state.current_hp = min(new_state.max_hp, before + int(amount))
    return new_state, new_state.current_hp - before


# --------------------------------------------------------------------------- #
# DM / UI summary helpers.
# --------------------------------------------------------------------------- #

def mount_summary(state: MountState) -> dict[str, Any]:
    """A readable snapshot of the current mount situation (for the panel + DM)."""
    mount = state.mount_obj()
    if mount is None:
        return {
            "has_mount": False,
            "mounted": False,
            "mount": None,
            "pace": state.pace,
            "pace_note": pace_notes(state.pace),
            "speed_multiplier": 1.0,
            "carrying_capacity_lbs": 0,
        }
    return {
        "has_mount": True,
        "mounted": state.mounted,
        "mount": mount.to_dict(),
        "mount_hp": f"{state.current_hp}/{state.max_hp}",
        "mount_conditions": list(state.conditions),
        "pace": state.pace,
        "pace_note": pace_notes(state.pace),
        "speed_multiplier": round(mount.speed_multiplier, 4),
        "travel_multiplier": round(travel_multiplier(state), 4),
        "carrying_capacity_lbs": mount.carrying_capacity_lbs,
        "control_type": mount.control_type,
    }


def mount_for_dm(state: MountState) -> str:
    """One-line DM context describing the rider's mount situation."""
    mount = state.mount_obj()
    if mount is None:
        return "on foot"
    status = "mounted" if state.mounted else "leading"
    hp = f" ({state.current_hp}/{state.max_hp} HP)"
    extra = ""
    if mount.can_fly:
        extra = " [flying]"
    elif mount.can_swim or mount.type == "aquatic":
        extra = " [waterborne]"
    elif mount.is_vehicle:
        extra = " [vehicle]"
    prone = " (prone)" if "prone" in {c.lower() for c in state.conditions} else ""
    return f"{status} a {mount.name}{hp}{extra}{prone} — travel ×{mount.speed_multiplier:.2f}"
