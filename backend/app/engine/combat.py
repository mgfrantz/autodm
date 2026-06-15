"""
Combat engine — initiative tracking, turn order, and attack resolution.

Implements the core DnD 5e combat loop:
1. Roll initiative for every combatant and build a turn order.
2. Cycle through turns (skipping dead combatants).
3. Resolve attacks: d20 + attack bonus vs target AC, with crits/fumbles.
4. Track HP, conditions, and whether combat is still active.

The engine is pure (no DB, no LLM) so it is trivially unit-testable. Game
state code can serialize an Encounter to JSON via ``Encounter.to_dict`` and
reconstruct it with ``Encounter.from_dict`` for persistence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.engine.dice import roll_d20, roll_dice


@dataclass
class Attack:
    """A weapon or attack a combatant can make."""

    name: str
    attack_bonus: int = 0
    damage_dice_count: int = 1
    damage_dice_sides: int = 6
    damage_bonus: int = 0
    damage_type: str = "slashing"

    def roll_damage(self, critical: bool = False) -> int:
        """Roll damage. On a critical hit the damage dice are doubled (5e rule)."""
        multiplier = 2 if critical else 1
        result = roll_dice(
            self.damage_dice_count * multiplier,
            self.damage_dice_sides,
            self.damage_bonus,  # bonus is NOT doubled per 5e rules
        )
        return result.total


@dataclass
class AttackResult:
    """The outcome of a single attack roll against a target."""

    attack_total: int
    hit: bool
    critical: bool
    critical_miss: bool
    damage: int
    target_remaining_hp: int
    description: str


@dataclass
class Combatant:
    """A participant in combat — player character or enemy/NPC."""

    id: str
    name: str
    side: str  # "player" or "enemy"
    max_hp: int
    armor_class: int
    initiative_bonus: int = 0  # typically the Dexterity modifier
    speed: int = 30
    attacks: list[Attack] = field(default_factory=list)
    current_hp: int = 0
    initiative: int = 0
    conditions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Default current HP to max when not explicitly set.
        if self.current_hp == 0:
            self.current_hp = self.max_hp

    @property
    def is_alive(self) -> bool:
        return self.current_hp > 0

    def take_damage(self, amount: int) -> int:
        """Apply damage (min 0). Returns the new current HP."""
        self.current_hp = max(0, self.current_hp - amount)
        return self.current_hp

    def heal(self, amount: int) -> int:
        """Restore HP (capped at max). Returns the new current HP."""
        self.current_hp = min(self.max_hp, self.current_hp + amount)
        return self.current_hp

    def roll_initiative(self) -> int:
        """Roll this combatant's initiative (d20 + initiative bonus)."""
        result = roll_d20(self.initiative_bonus)
        self.initiative = result.total
        return self.initiative

    def add_condition(self, condition: str) -> None:
        """Add a condition (e.g. 'poisoned') if not already present."""
        if condition not in self.conditions:
            self.conditions.append(condition)

    def remove_condition(self, condition: str) -> None:
        """Remove a condition if present."""
        if condition in self.conditions:
            self.conditions.remove(condition)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "side": self.side,
            "max_hp": self.max_hp,
            "current_hp": self.current_hp,
            "armor_class": self.armor_class,
            "initiative_bonus": self.initiative_bonus,
            "initiative": self.initiative,
            "speed": self.speed,
            "conditions": list(self.conditions),
            "attacks": [
                {
                    "name": a.name,
                    "attack_bonus": a.attack_bonus,
                    "damage_dice_count": a.damage_dice_count,
                    "damage_dice_sides": a.damage_dice_sides,
                    "damage_bonus": a.damage_bonus,
                    "damage_type": a.damage_type,
                }
                for a in self.attacks
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Combatant":
        attacks = [Attack(**a) for a in data.get("attacks", [])]
        return cls(
            id=data["id"],
            name=data["name"],
            side=data["side"],
            max_hp=data["max_hp"],
            armor_class=data["armor_class"],
            initiative_bonus=data.get("initiative_bonus", 0),
            initiative=data.get("initiative", 0),
            speed=data.get("speed", 30),
            conditions=list(data.get("conditions", [])),
            attacks=attacks,
            current_hp=data.get("current_hp", data["max_hp"]),
        )


class Encounter:
    """A single combat encounter with initiative order and turn tracking."""

    def __init__(self, combatants: Optional[list[Combatant]] = None) -> None:
        self.combatants: list[Combatant] = list(combatants) if combatants else []
        self.turn_order: list[Combatant] = []
        self.current_turn_index: int = 0
        self.round_number: int = 0
        self.started: bool = False
        self.log: list[str] = []

    def add_combatant(self, combatant: Combatant) -> None:
        """Add a combatant before initiative is rolled."""
        if self.started:
            raise RuntimeError("Cannot add combatants after initiative is rolled")
        self.combatants.append(combatant)

    def roll_initiative(self) -> list[tuple[str, int]]:
        """Roll initiative for all combatants and build the turn order.

        Returns the ordered (name, initiative) list. Ties are broken by
        initiative bonus, then a random die roll for fairness.
        """
        for c in self.combatants:
            c.roll_initiative()

        # Highest initiative first. Ties are broken by initiative bonus, then
        # by original insertion order (Python's sort is stable), which keeps
        # the ordering deterministic and testable.
        self.turn_order = sorted(
            self.combatants,
            key=lambda c: (c.initiative, c.initiative_bonus),
            reverse=True,
        )
        return [(c.name, c.initiative) for c in self.turn_order]

    def start(self) -> list[tuple[str, int]]:
        """Roll initiative and begin combat. Returns the turn order."""
        order = self.roll_initiative()
        self.started = True
        self.current_turn_index = 0
        self.round_number = 1
        self.log.append(f"Combat begins! Round {self.round_number}.")
        return order

    @property
    def current_combatant(self) -> Optional[Combatant]:
        """The combatant whose turn it currently is, or None."""
        if not self.turn_order:
            return None
        return self.turn_order[self.current_turn_index % len(self.turn_order)]

    def next_turn(self) -> Optional[Combatant]:
        """Advance to the next living combatant's turn.

        Returns the combatant whose turn is now active, or None if combat ended.
        """
        if not self.started:
            raise RuntimeError("Combat has not started")

        # Skip dead combatants while advancing.
        for _ in range(len(self.turn_order)):
            self.current_turn_index += 1
            if self.current_turn_index >= len(self.turn_order):
                # Wrapped around — new round.
                self.current_turn_index = 0
                self.round_number += 1
                self.log.append(f"--- Round {self.round_number} ---")
            if self.current_combatant and self.current_combatant.is_alive:
                return self.current_combatant

        # Everyone is dead — shouldn't normally happen for the player's side,
        # but guard against it anyway.
        return None

    def alive_combatants(self, side: Optional[str] = None) -> list[Combatant]:
        """Return living combatants, optionally filtered by side."""
        return [
            c for c in self.combatants
            if c.is_alive and (side is None or c.side == side)
        ]

    @property
    def is_active(self) -> bool:
        """True if both sides still have living combatants."""
        return (
            self.started
            and bool(self.alive_combatants("player"))
            and bool(self.alive_combatants("enemy"))
        )

    @property
    def winner(self) -> Optional[str]:
        """The winning side ('player'/'enemy'), or None if combat is ongoing."""
        if not self.started:
            return None
        players_alive = bool(self.alive_combatants("player"))
        enemies_alive = bool(self.alive_combatants("enemy"))
        if players_alive and not enemies_alive:
            return "player"
        if enemies_alive and not players_alive:
            return "enemy"
        return None

    def resolve_attack(
        self,
        attacker: Combatant,
        target: Combatant,
        attack: Attack,
        advantage: bool = False,
        disadvantage: bool = False,
    ) -> AttackResult:
        """Resolve an attack: roll to hit against AC, then roll damage.

        - Natural 20 = critical hit (double damage dice).
        - Natural 1 = critical miss (automatic miss).
        - Otherwise total >= target AC = hit.
        """
        roll = roll_d20(attack.attack_bonus, advantage=advantage, disadvantage=disadvantage)
        d20_value = roll.rolls[0]
        attack_total = roll.total

        critical = d20_value == 20
        critical_miss = d20_value == 1
        hit = (not critical_miss) and (critical or attack_total >= target.armor_class)

        if not hit:
            description = (
                f"{attacker.name} attacks {target.name} with {attack.name} "
                f"but misses (rolled {attack_total} vs AC {target.armor_class})."
            )
            return AttackResult(
                attack_total=attack_total,
                hit=False,
                critical=False,
                critical_miss=critical_miss,
                damage=0,
                target_remaining_hp=target.current_hp,
                description=description,
            )

        damage = attack.roll_damage(critical=critical)
        remaining = target.take_damage(damage)

        crit_label = "CRITICAL HIT! " if critical else ""
        description = (
            f"{crit_label}{attacker.name} hits {target.name} with {attack.name} "
            f"for {damage} {attack.damage_type} damage "
            f"(rolled {attack_total} vs AC {target.armor_class}). "
            f"{target.name} has {remaining} HP remaining."
        )

        if not target.is_alive:
            description += f" {target.name} is defeated!"
            self.log.append(description)

        return AttackResult(
            attack_total=attack_total,
            hit=True,
            critical=critical,
            critical_miss=False,
            damage=damage,
            target_remaining_hp=remaining,
            description=description,
        )

    def to_dict(self) -> dict:
        return {
            "combatants": [c.to_dict() for c in self.combatants],
            "turn_order_ids": [c.id for c in self.turn_order],
            "current_turn_index": self.current_turn_index,
            "round_number": self.round_number,
            "started": self.started,
            "log": list(self.log),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Encounter":
        combatants = [Combatant.from_dict(c) for c in data.get("combatants", [])]
        encounter = cls(combatants=combatants)
        # Rebuild turn order using stored ids to preserve initiative order.
        order_ids = data.get("turn_order_ids", [])
        by_id = {c.id: c for c in combatants}
        encounter.turn_order = [by_id[i] for i in order_ids if i in by_id]
        encounter.current_turn_index = data.get("current_turn_index", 0)
        encounter.round_number = data.get("round_number", 0)
        encounter.started = data.get("started", False)
        encounter.log = list(data.get("log", []))
        return encounter
