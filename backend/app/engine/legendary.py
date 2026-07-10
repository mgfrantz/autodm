"""
Legendary Actions & Lair Actions engine — DnD 5e boss-monster mechanics.

Implements the Monster Manual (p. 11) rules that let a single powerful creature
hold its own against an entire party, compensating for the action-economy
imbalance of "one monster vs. many heroes":

**Legendary Actions**
A legendary creature can take a limited number of special actions *outside its
turn* — specifically at the end of another creature's turn. Each legendary
action has a *cost* (1, 2, or 3) drawn from a per-round budget (typically 3).
The creature regains all spent legendary actions at the start of its own turn.
It may only take one legendary action at a time, and it cannot use one on its
own turn. Common legendary actions include "Detect" (cost 1), an extra attack
(cost 1), or a powerful "Wing Attack"/"Tail Swipe" (cost 2).

**Lair Actions**
When fighting inside its lair, certain legendary creatures can take lair
actions. On initiative count 20 (losing all ties), the creature — if not
incapacitated — can use one of its lair action options. Lair actions use the
same initiative slot each round.

The module is **pure** (no DB, no LLM): every helper operates on plain
dataclasses or combatant-like objects that expose the legendary fields. This
makes the engine fully unit-testable and lets the combat API serialize/restore
the state through ``to_dict`` / ``from_dict``.

Reference: DnD 5e Monster Manual, "Legendary Creatures" (p. 11); Dungeon
Master's Guide, "Lairs" (ch. 3); Mordenkainen Presents: Monsters of the
Multiverse.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# Initiative count on which lair actions trigger each round (MM p. 11).
LAIR_INITIATIVE_COUNT: int = 20


# --------------------------------------------------------------------------- #
# Legendary action
# --------------------------------------------------------------------------- #
@dataclass
class LegendaryAction:
    """A single special action a legendary creature may take off-turn.

    ``cost`` is the number of legendary-action points it consumes from the
    creature's per-round budget (1, 2, or 3). ``kind`` describes the effect:

    - ``attack`` — performs an attack (``attack`` payload is an ``Attack``
      ``to_dict()`` shape resolved through the encounter's attack logic).
    - ``detect`` — a passive perception/Wisdom check; narrative only.
    - ``move`` — the creature moves up to half its speed.
    - ``utility`` — a non-combat option (e.g. *Wing Attack* shoves creatures
      back and lets the dragon fly); resolved narratively.
    """

    id: str
    name: str
    description: str = ""
    cost: int = 1
    kind: str = "utility"
    # ``Attack.to_dict()`` shape for ``kind == "attack"``.
    attack: Optional[dict] = None
    # Optional condition inflicted on the target on a hit (attack kind).
    condition: Optional[str] = None
    condition_duration: Optional[int] = None
    # Optional damage-type modifiers flag for the DM/UI.
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "cost": self.cost,
            "kind": self.kind,
            "attack": dict(self.attack) if self.attack else None,
            "condition": self.condition,
            "condition_duration": self.condition_duration,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LegendaryAction":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            cost=data.get("cost", 1),
            kind=data.get("kind", "utility"),
            attack=dict(data["attack"]) if data.get("attack") else None,
            condition=data.get("condition"),
            condition_duration=data.get("condition_duration"),
            notes=data.get("notes", ""),
        )


# --------------------------------------------------------------------------- #
# Lair action
# --------------------------------------------------------------------------- #
@dataclass
class LairAction:
    """An environmental action a creature can use while in its lair.

    Lair actions fire on ``LAIR_INITIATIVE_COUNT`` (initiative 20, losing
    ties) each round. ``kind`` describes the resolution:

    - ``attack`` — makes an attack against one or more creatures (``attack``).
    - ``save`` — every creature in range makes a saving throw (``save_dc``,
      ``save_ability``) or suffers ``damage`` / gains ``condition``.
    - ``utility`` — a narrative environmental effect (lava flows, fog rolls
      in, etc.) with no mechanical roll.
    """

    id: str
    name: str
    description: str = ""
    initiative_count: int = LAIR_INITIATIVE_COUNT
    kind: str = "utility"
    attack: Optional[dict] = None
    damage: int = 0
    damage_type: str = ""
    save_dc: int = 0
    save_ability: str = ""  # "dex", "con", "wis", ...
    condition: Optional[str] = None
    condition_duration: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "initiative_count": self.initiative_count,
            "kind": self.kind,
            "attack": dict(self.attack) if self.attack else None,
            "damage": self.damage,
            "damage_type": self.damage_type,
            "save_dc": self.save_dc,
            "save_ability": self.save_ability,
            "condition": self.condition,
            "condition_duration": self.condition_duration,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LairAction":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            initiative_count=data.get("initiative_count", LAIR_INITIATIVE_COUNT),
            kind=data.get("kind", "utility"),
            attack=dict(data["attack"]) if data.get("attack") else None,
            damage=data.get("damage", 0),
            damage_type=data.get("damage_type", ""),
            save_dc=data.get("save_dc", 0),
            save_ability=data.get("save_ability", ""),
            condition=data.get("condition"),
            condition_duration=data.get("condition_duration"),
        )


# --------------------------------------------------------------------------- #
# Per-round legendary-action budget
# --------------------------------------------------------------------------- #
@dataclass
class LegendaryState:
    """Tracks a legendary creature's spent/remaining legendary actions.

    The budget resets to ``budget_max`` at the start of the creature's turn.
    """

    budget_max: int = 3
    budget_used: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.budget_max - self.budget_used)

    def can_spend(self, cost: int) -> bool:
        """True if the creature can afford a legendary action of ``cost``."""
        return cost > 0 and self.remaining >= cost

    def reset(self) -> None:
        """Regain all legendary actions (called at the start of its turn)."""
        self.budget_used = 0

    def spend(self, cost: int) -> None:
        """Consume ``cost`` points. Raises ``ValueError`` if unaffordable."""
        if not self.can_spend(cost):
            raise ValueError(
                f"Cannot spend {cost} legendary action points "
                f"(only {self.remaining} remaining)."
            )
        self.budget_used += cost

    def to_dict(self) -> dict:
        return {
            "budget_max": self.budget_max,
            "budget_used": self.budget_used,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LegendaryState":
        if not data:
            return cls()
        return cls(
            budget_max=data.get("budget_max", 3),
            budget_used=data.get("budget_used", 0),
        )


# --------------------------------------------------------------------------- #
# Resolution results
# --------------------------------------------------------------------------- #
@dataclass
class LegendaryActionResult:
    """Outcome of attempting a legendary action."""

    action: Optional[LegendaryAction]
    used: bool
    remaining_budget: int
    reason: str = ""
    # For attack-kind actions, the attack description (filled by the resolver
    # which actually resolves the attack through the encounter).
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "used": self.used,
            "remaining_budget": self.remaining_budget,
            "reason": self.reason,
            "description": self.description,
            "action": self.action.to_dict() if self.action else None,
        }


@dataclass
class LairActionResult:
    """Outcome of a lair action firing on initiative 20."""

    action: Optional[LairAction]
    triggered: bool
    description: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "triggered": self.triggered,
            "description": self.description,
            "reason": self.reason,
            "action": self.action.to_dict() if self.action else None,
        }


# --------------------------------------------------------------------------- #
# Combatant-attached helpers
# --------------------------------------------------------------------------- #
def is_legendary(combatant: Any) -> bool:
    """True if the combatant is a legendary creature.

    A combatant is legendary when it carries a non-empty ``legendary_actions``
    list (and/or a positive ``legendary_budget_max``). The legacy
    ``is_legendary`` boolean flag is honoured too.
    """
    if bool(getattr(combatant, "is_legendary", False)):
        return True
    actions = getattr(combatant, "legendary_actions", None) or []
    if actions:
        return True
    return (getattr(combatant, "legendary_budget_max", 0) or 0) > 0


def get_legendary_actions(combatant: Any) -> list[LegendaryAction]:
    """Return the combatant's parsed legendary actions (empty if none)."""
    raw = getattr(combatant, "legendary_actions", None) or []
    return [LegendaryAction.from_dict(a) if isinstance(a, dict) else a for a in raw]


def available_legendary_actions(
    combatant: Any, state: LegendaryState
) -> list[LegendaryAction]:
    """Legendary actions the creature can still afford this round."""
    return [a for a in get_legendary_actions(combatant) if state.can_spend(a.cost)]


def creature_state(combatant: Any) -> LegendaryState:
    """Rebuild the per-round LegendaryState from a combatant's live fields."""
    return LegendaryState(
        budget_max=getattr(combatant, "legendary_budget_max", 3) or 3,
        budget_used=getattr(combatant, "legendary_budget_used", 0) or 0,
    )


def can_take_legendary_action(
    combatant: Any, state: LegendaryState, action: LegendaryAction
) -> tuple[bool, str]:
    """Validate that the creature may take ``action`` right now.

    Returns ``(ok, reason)``. ``reason`` explains why the action is blocked
    (used for the API 400 detail and the story log).
    """
    if not is_legendary(combatant):
        return False, f"{getattr(combatant, 'name', 'Creature')} is not legendary."
    actions = get_legendary_actions(combatant)
    if action.id not in {a.id for a in actions}:
        return False, f"{action.name} is not one of this creature's legendary actions."
    if not state.can_spend(action.cost):
        return (
            False,
            f"Not enough legendary actions left "
            f"(need {action.cost}, have {state.remaining}).",
        )
    return True, ""


def spend_legendary_action(
    combatant: Any, state: LegendaryState, action: LegendaryAction
) -> LegendaryActionResult:
    """Consume ``action``'s cost from the budget and persist ``budget_used``.

    Does **not** resolve the action's effect (the combat API resolves attacks
    through the encounter). Returns a :class:`LegendaryActionResult`.
    """
    ok, reason = can_take_legendary_action(combatant, state, action)
    if not ok:
        return LegendaryActionResult(
            action=action, used=False, remaining_budget=state.remaining, reason=reason
        )
    state.spend(action.cost)
    # Persist the new used count back onto the combatant so it survives
    # serialization through the encounter's ``to_dict``.
    try:
        combatant.legendary_budget_used = state.budget_used
    except Exception:
        pass
    return LegendaryActionResult(
        action=action,
        used=True,
        remaining_budget=state.remaining,
        description=(
            f"{getattr(combatant, 'name', 'Creature')} uses the legendary "
            f"action {action.name} (cost {action.cost}; "
            f"{state.remaining} left)."
        ),
    )


def reset_legendary_actions(combatant: Any) -> None:
    """Regain all legendary actions (call at the start of the creature's turn)."""
    try:
        combatant.legendary_budget_used = 0
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Lair helpers
# --------------------------------------------------------------------------- #
def has_lair(combatant_or_encounter: Any) -> bool:
    """True if the encounter/creature has lair actions configured."""
    lair = getattr(combatant_or_encounter, "lair_actions", None) or []
    return bool(lair)


def get_lair_actions(holder: Any) -> list[LairAction]:
    """Return the parsed lair actions on an encounter or creature."""
    raw = getattr(holder, "lair_actions", None) or []
    return [LairAction.from_dict(a) if isinstance(a, dict) else a for a in raw]


def should_fire_lair_action(
    round_number: int,
    lair_actions: list[LairAction],
    *,
    last_fired_round: Optional[int] = None,
) -> bool:
    """Whether a lair action should fire *now*.

    Lair actions fire once per round on initiative count 20. ``last_fired_round``
    prevents double-firing within the same round. Returns False if there are no
    lair actions or it already fired this round.
    """
    if not lair_actions:
        return False
    if last_fired_round is not None and last_fired_round == round_number:
        return False
    return True


def choose_lair_action(
    lair_actions: list[LairAction], round_number: int
) -> Optional[LairAction]:
    """Deterministically pick which lair action fires for a given round.

    Round-robins through the options (indexed by round number) so a creature
    with several lair actions cycles through them, matching how a DM typically
    rotates them. Returns ``None`` if there are no lair actions.
    """
    if not lair_actions:
        return None
    index = (round_number - 1) % len(lair_actions)
    return lair_actions[index]


def fire_lair_action(
    action: LairAction, round_number: int
) -> LairActionResult:
    """Produce the resolution narrative for a lair action firing.

    Returns a :class:`LairActionResult` describing the effect; the combat API
    resolves any ``attack`` / ``save`` mechanically and appends a richer
    description. ``triggered`` is False only when the action is invalid.
    """
    if action is None:
        return LairActionResult(action=None, triggered=False, reason="No lair action.")
    desc = (
        f"Lair action on initiative {action.initiative_count} (round "
        f"{round_number}): {action.name}. {action.description}"
    )
    return LairActionResult(action=action, triggered=True, description=desc)


# --------------------------------------------------------------------------- #
# DM / UI helpers
# --------------------------------------------------------------------------- #
def legendary_summary_for_dm(combatant: Any) -> str:
    """One-line DM context summary of a creature's legendary/lair capabilities."""
    name = getattr(combatant, "name", "Creature")
    parts: list[str] = []
    if is_legendary(combatant):
        actions = get_legendary_actions(combatant)
        budget = getattr(combatant, "legendary_budget_max", 3) or 3
        names = ", ".join(f"{a.name} ({a.cost})" for a in actions) or "none"
        parts.append(
            f"{name} is legendary: {budget} legendary actions/round "
            f"[{names}]"
        )
    lair = get_lair_actions(combatant)
    if lair:
        names = ", ".join(a.name for a in lair)
        parts.append(f"lair actions on initiative {LAIR_INITIATIVE_COUNT}: {names}")
    return "; ".join(parts) if parts else ""


def creature_has_lair(combatant: Any) -> bool:
    """Convenience alias checking lair actions on a creature."""
    return has_lair(combatant)


# --------------------------------------------------------------------------- #
# Registry — iconic legendary creatures
# --------------------------------------------------------------------------- #
@dataclass
class LegendaryCreaturePreset:
    """A ready-to-use legendary creature blueprint.

    Brings together a base stat-block (CR, HP, AC, attacks, damage modifiers)
    and the creature's legendary + lair actions, so the DM can drop a boss
    into combat in one call. The combat API's ``/combat/start`` endpoint
    accepts an ``enemy`` dict that may carry ``legendary_actions`` /
    ``legendary_budget_max`` / ``lair_actions``; this registry feeds those.
    """

    id: str
    name: str
    cr: float
    max_hp: int
    armor_class: int
    speed: int = 30
    size: str = "huge"
    strength: int = 10
    dexterity: int = 10
    initiative_bonus: int = 0
    attacks: list[dict] = field(default_factory=list)
    damage_modifiers: list[dict] = field(default_factory=list)
    legendary_budget_max: int = 3
    legendary_actions: list[LegendaryAction] = field(default_factory=list)
    lair_actions: list[LairAction] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "cr": self.cr,
            "max_hp": self.max_hp,
            "armor_class": self.armor_class,
            "speed": self.speed,
            "size": self.size,
            "strength": self.strength,
            "dexterity": self.dexterity,
            "initiative_bonus": self.initiative_bonus,
            "attacks": [dict(a) for a in self.attacks],
            "damage_modifiers": [dict(d) for d in self.damage_modifiers],
            "legendary_budget_max": self.legendary_budget_max,
            "legendary_actions": [a.to_dict() for a in self.legendary_actions],
            "lair_actions": [a.to_dict() for a in self.lair_actions],
            "notes": self.notes,
        }


def _bite(bonus: int, dice: int, sides: int, dmg: int, dmg_type: str = "piercing") -> dict:
    return {
        "name": "Bite",
        "attack_bonus": bonus,
        "damage_dice_count": dice,
        "damage_dice_sides": sides,
        "damage_bonus": dmg,
        "damage_type": dmg_type,
        "magical": False,
    }


def _attack(name: str, bonus: int, dice: int, sides: int, dmg: int, dmg_type: str, magical: bool = False) -> dict:
    return {
        "name": name,
        "attack_bonus": bonus,
        "damage_dice_count": dice,
        "damage_dice_sides": sides,
        "damage_bonus": dmg,
        "damage_type": dmg_type,
        "magical": magical,
    }


def _leg_attack(name: str, source_attack: dict, cost: int = 1, desc: str = "", **extra) -> LegendaryAction:
    return LegendaryAction(
        id=name.lower().replace(" ", "_"),
        name=name,
        description=desc,
        cost=cost,
        kind=extra.get("kind", "attack"),
        attack=dict(source_attack),
        condition=extra.get("condition"),
        condition_duration=extra.get("condition_duration"),
        notes=extra.get("notes", ""),
    )


# --- Adult Red Dragon (CR 17) — the archetypal legendary + lair creature ---
ADULT_RED_DRAGON = LegendaryCreaturePreset(
    id="adult_red_dragon",
    name="Adult Red Dragon",
    cr=17,
    max_hp=256,
    armor_class=19,
    speed=40,
    size="huge",
    strength=27,
    dexterity=10,
    initiative_bonus=0,
    attacks=[
        _bite(14, 2, 10, 8, "piercing"),
        _attack("Claw", 14, 2, 6, 8, "slashing"),
        _attack("Fire Breath", 0, 12, 8, 0, "fire"),
    ],
    damage_modifiers=[{"types": ["fire"], "kind": "immunity"}],
    legendary_budget_max=3,
    legendary_actions=[
        LegendaryAction(
            id="detect", name="Detect", cost=1, kind="detect",
            description="The dragon makes a Wisdom (Perception) check.",
            notes="Passive detection between turns.",
        ),
        LegendaryAction(
            id="tail_attack", name="Tail Attack", cost=1, kind="attack",
            attack=_attack("Tail", 14, 2, 8, 4, "bludgeoning"),
            description="The dragon makes one tail attack.",
        ),
        LegendaryAction(
            id="wing_attack", name="Wing Attack (Costs 2 Actions)", cost=2, kind="utility",
            description=(
                "The dragon beats its wings. Each creature within 10 ft must "
                "succeed on a DC 22 Dexterity saving throw or take 15 "
                "bludgeoning damage and be knocked prone. The dragon can then "
                "fly up to half its flying speed."
            ),
            notes="AoE knockdown + repositioning; costs 2 actions.",
        ),
    ],
    lair_actions=[
        LairAction(
            id="magma_fissure", name="Magma Fissure",
            description=(
                "Magma erupts from a point on the ground the dragon can see "
                "within 120 ft, creating a 20-ft-radius area. Each creature "
                "in that area must make a DC 15 Dexterity save, taking 6d6 "
                "fire damage on a failed save."
            ),
            kind="save", damage=21, damage_type="fire",
            save_dc=15, save_ability="dex",
        ),
        LairAction(
            id="tremor", name="Tremor",
            description=(
                "The ground within 120 ft of the dragon shakes. Each creature "
                "on the ground in that area must succeed on a DC 15 Dexterity "
                "save or be knocked prone."
            ),
            kind="save", save_dc=15, save_ability="dex", condition="prone",
        ),
    ],
    notes="Iconic CR 17 legendary dragon with fire immunity and a magma lair.",
)


# --- Lich (CR 21) — master necromancer ---
LICH = LegendaryCreaturePreset(
    id="lich",
    name="Lich",
    cr=21,
    max_hp=135,
    armor_class=17,
    speed=30,
    size="medium",
    strength=11,
    dexterity=16,
    initiative_bonus=3,
    attacks=[
        _attack("Paralyzing Touch", 12, 3, 6, 0, "cold", magical=True),
    ],
    damage_modifiers=[
        {"types": ["poison", "cold"], "kind": "immunity"},
        {"types": ["bludgeoning", "piercing", "slashing"], "kind": "immunity"},
    ],
    legendary_budget_max=3,
    legendary_actions=[
        LegendaryAction(
            id="cantrip", name="Cantrip", cost=1, kind="utility",
            description="The lich casts a cantrip.",
        ),
        LegendaryAction(
            id="paralyzing_touch", name="Paralyzing Touch", cost=1, kind="attack",
            attack=_attack("Paralyzing Touch", 12, 3, 6, 0, "cold", magical=True),
            condition="paralyzed", condition_duration=1,
            description=(
                "The lich uses its Paralyzing Touch. DC 18 Constitution save "
                "or be paralyzed for 1 minute."
            ),
        ),
        LegendaryAction(
            id="frightening_gaze", name="Frightening Gaze (Costs 2 Actions)", cost=2,
            kind="utility",
            description=(
                "The lich fixes its gaze on one creature it can see within 10 "
                "ft. The target must succeed on a DC 18 Wisdom save or become "
                "frightened for 1 minute."
            ),
            condition="frightened", condition_duration=10,
        ),
        LegendaryAction(
            id="disrupt_life", name="Disrupt Life (Costs 2 Actions)", cost=2,
            kind="utility",
            description=(
                "Each non-undead creature within 20 ft must make a DC 18 "
                "Constitution save, taking 21 necrotic damage on a failure."
            ),
        ),
    ],
    lair_actions=[],
    notes="CR 21 undead archmage; legendary disrupt-life aura and paralysis.",
)


# --- Beholder (CR 13) — many-eyed tyrant ---
BEHOLDER = LegendaryCreaturePreset(
    id="beholder",
    name="Beholder",
    cr=13,
    max_hp=180,
    armor_class=18,
    speed=0,
    size="large",
    strength=10,
    dexterity=14,
    initiative_bonus=2,
    attacks=[
        _attack("Bite", 5, 2, 6, 0, "piercing"),
    ],
    damage_modifiers=[],
    legendary_budget_max=3,
    legendary_actions=[
        LegendaryAction(
            id="eye_ray", name="Eye Ray", cost=1, kind="utility",
            description=(
                "The beholder fires one of its eye rays at a random target "
                "(see the creature's stat block for ray effects)."
            ),
            notes="DM selects a ray (Charm, Disintegration, Death, etc.).",
        ),
        LegendaryAction(
            id="detect", name="Detect", cost=1, kind="detect",
            description="The beholder makes a Wisdom (Perception) check.",
        ),
    ],
    lair_actions=[
        LairAction(
            id="lair_entrance", name="Lair Entrance",
            description=(
                "On initiative 20, the beholder can alter the lair: doors "
                "seal, shafts open, or walls shift to disorient intruders."
            ),
            kind="utility",
        ),
    ],
    notes="CR 13 aberration; random eye rays and a shifting lair.",
)


# --- Vampire (CR 13) — gothic lord of the night ---
VAMPIRE = LegendaryCreaturePreset(
    id="vampire",
    name="Vampire",
    cr=13,
    max_hp=144,
    armor_class=16,
    speed=30,
    size="medium",
    strength=18,
    dexterity=18,
    initiative_bonus=4,
    attacks=[
        _attack("Unarmed Strike", 9, 1, 8, 4, "bludgeoning", magical=True),
        _attack("Bite", 9, 1, 6, 4, "piercing", magical=True),
    ],
    damage_modifiers=[
        {"types": ["necrotic", "poison"], "kind": "immunity"},
    ],
    legendary_budget_max=3,
    legendary_actions=[
        LegendaryAction(
            id="unarmed_strike", name="Unarmed Strike", cost=1, kind="attack",
            attack=_attack("Unarmed Strike", 9, 1, 8, 4, "bludgeoning", magical=True),
            description="The vampire makes one unarmed strike.",
        ),
        LegendaryAction(
            id="move", name="Move", cost=1, kind="move",
            description="The vampire moves up to its speed without provoking opportunity attacks.",
        ),
    ],
    lair_actions=[],
    notes="CR 13 undead noble; legendary mobility and strikes, sunlight-averse.",
)


# --- Tarrasque (CR 30) — the colossal legendary titan ---
TARRASQUE = LegendaryCreaturePreset(
    id="tarrasque",
    name="Tarrasque",
    cr=30,
    max_hp=676,
    armor_class=25,
    speed=40,
    size="gargantuan",
    strength=30,
    dexterity=11,
    initiative_bonus=0,
    attacks=[
        _bite(13, 4, 12, 10, "piercing"),
        _attack("Claw", 13, 4, 8, 10, "slashing"),
        _attack("Horns", 13, 4, 10, 10, "piercing"),
        _attack("Tail", 13, 4, 12, 10, "bludgeoning"),
    ],
    damage_modifiers=[
        {"types": ["fire", "poison"], "kind": "immunity"},
        {
            "types": ["bludgeoning", "piercing", "slashing"],
            "kind": "resistance",
            "bypassed_by": ["magical"],
        },
    ],
    legendary_budget_max=3,
    legendary_actions=[
        LegendaryAction(
            id="attack", name="Attack", cost=1, kind="attack",
            attack=_attack("Onslaught", 13, 3, 12, 10, "slashing"),
            description="The tarrasque makes one attack.",
        ),
        LegendaryAction(
            id="move", name="Move", cost=1, kind="move",
            description="The tarrasque moves up to half its speed.",
        ),
    ],
    lair_actions=[],
    notes="CR 30 colossal titan; near-indestructible, legendary thrash.",
)


# --- Adult Blue Dragon (CR 16) — desert lightning wyrm with a lair ---
ADULT_BLUE_DRAGON = LegendaryCreaturePreset(
    id="adult_blue_dragon",
    name="Adult Blue Dragon",
    cr=16,
    max_hp=225,
    armor_class=19,
    speed=40,
    size="huge",
    strength=25,
    dexterity=10,
    initiative_bonus=0,
    attacks=[
        _bite(12, 2, 10, 6, "piercing"),
        _attack("Claw", 12, 2, 6, 6, "slashing"),
        _attack("Lightning Breath", 0, 10, 8, 0, "lightning"),
    ],
    damage_modifiers=[{"types": ["lightning"], "kind": "immunity"}],
    legendary_budget_max=3,
    legendary_actions=[
        LegendaryAction(
            id="detect", name="Detect", cost=1, kind="detect",
            description="The dragon makes a Wisdom (Perception) check.",
        ),
        LegendaryAction(
            id="tail_attack", name="Tail Attack", cost=1, kind="attack",
            attack=_attack("Tail", 12, 2, 8, 4, "bludgeoning"),
            description="The dragon makes one tail attack.",
        ),
        LegendaryAction(
            id="wing_attack", name="Wing Attack (Costs 2 Actions)", cost=2, kind="utility",
            description=(
                "The dragon beats its wings. Each creature within 10 ft must "
                "succeed on a DC 20 Dexterity save or take 14 bludgeoning "
                "damage and be knocked prone. The dragon can then fly up to "
                "half its flying speed."
            ),
        ),
    ],
    lair_actions=[
        LairAction(
            id="thunderclap", name="Thunderclap",
            description=(
                "A burst of sonic energy erupts from a point the dragon "
                "chooses within 120 ft. Each creature within 20 ft must make "
                "a DC 15 Constitution save, taking 10 thunder damage and "
                "being deafened on a failure."
            ),
            kind="save", damage=10, damage_type="thunder",
            save_dc=15, save_ability="con", condition="deafened",
        ),
        LairAction(
            id="sandstorm", name="Sandstorm",
            description=(
                "Blinding sand sweeps through the lair. Each creature other "
                "than the dragon must succeed on a DC 15 Strength save or be "
                "restrained until initiative 20 on the next round."
            ),
            kind="save", save_dc=15, save_ability="str", condition="restrained",
        ),
    ],
    notes="CR 16 desert dragon; lightning immunity and a thunder/sand lair.",
)


LEGENDARY_CREATURE_REGISTRY: dict[str, LegendaryCreaturePreset] = {
    p.id: p
    for p in (
        ADULT_RED_DRAGON,
        LICH,
        BEHOLDER,
        VAMPIRE,
        TARRASQUE,
        ADULT_BLUE_DRAGON,
    )
}


def list_legendary_creatures() -> list[LegendaryCreaturePreset]:
    """All registered legendary creature presets."""
    return list(LEGENDARY_CREATURE_REGISTRY.values())


def get_legendary_creature(creature_id: str) -> Optional[LegendaryCreaturePreset]:
    """Look up a legendary creature preset by id."""
    return LEGENDARY_CREATURE_REGISTRY.get(creature_id)
