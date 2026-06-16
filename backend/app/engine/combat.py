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

from app.engine import conditions as conditions_mod
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
    ranged: bool = False  # distinguishes melee vs ranged for prone/cover rules

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
    condition_durations: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Default current HP to max when not explicitly set.
        if self.current_hp == 0:
            self.current_hp = self.max_hp

    @property
    def is_alive(self) -> bool:
        return self.current_hp > 0

    @property
    def is_incapacitated(self) -> bool:
        """True if the combatant cannot act due to a condition (e.g. stunned)."""
        return conditions_mod.is_incapacitated(self)

    @property
    def effective_speed(self) -> int:
        """Speed, reduced to 0 by conditions such as grappled or restrained."""
        return conditions_mod.effective_speed(self)

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

    def add_condition(self, condition: str, duration: Optional[int] = None) -> None:
        """Add a condition (e.g. 'poisoned') if not already present.

        An optional *duration* (in rounds) makes the condition expire at the end
        of future rounds.
        """
        conditions_mod.apply_condition(self, condition, duration=duration)

    def remove_condition(self, condition: str) -> bool:
        """Remove a condition if present. Returns whether it was removed."""
        return conditions_mod.remove_condition(self, condition)

    def has_condition(self, condition: str) -> bool:
        """True if the combatant currently suffers from *condition*."""
        return conditions_mod.has_condition(self, condition)

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
            "condition_durations": dict(self.condition_durations),
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
            condition_durations=dict(data.get("condition_durations", {})),
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
        """Advance to the next combatant's turn.

        Dead combatants and incapacitated combatants (e.g. stunned, paralyzed)
        are skipped — they cannot take actions. When the turn order wraps around
        to a new round, timed conditions on every combatant tick down and any
        that expire are removed.

        Returns the combatant whose turn is now active, or None if no living,
        non-incapacitated combatant remains.
        """
        if not self.started:
            raise RuntimeError("Combat has not started")

        # Skip dead or incapacitated combatants while advancing.
        for _ in range(len(self.turn_order)):
            self.current_turn_index += 1
            if self.current_turn_index >= len(self.turn_order):
                # Wrapped around — new round: tick timed conditions first.
                self.current_turn_index = 0
                self.round_number += 1
                self._tick_round()
                self.log.append(f"--- Round {self.round_number} ---")
            candidate = self.current_combatant
            if candidate and candidate.is_alive and not candidate.is_incapacitated:
                return candidate
            if candidate and candidate.is_alive and candidate.is_incapacitated:
                self.log.append(
                    f"{candidate.name} is incapacitated and loses their turn."
                )

        # Everyone is dead or incapacitated — combat cannot continue normally.
        return None

    def _tick_round(self) -> None:
        """Advance timed conditions by one round for every combatant."""
        for combatant in self.combatants:
            if not combatant.is_alive:
                continue
            expired = conditions_mod.tick_conditions(combatant)
            for name in expired:
                self.log.append(
                    f"{combatant.name} is no longer {name}."
                )

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

        Implements the full DnD 5e to-hit and damage loop, including
        condition-driven modifiers:

        - The attacker's own conditions may grant advantage/disadvantage
          (e.g. poisoned → disadvantage, invisible → advantage).
        - The target's conditions may make it easier or harder to hit
          (e.g. stunned → attacks against have advantage; prone melee vs ranged).
        - Natural 20 = critical hit (double damage dice).
        - Natural 1 = critical miss (automatic miss).
        - A paralyzed/petrified/unconscious target hit by a melee attack within
          5 ft takes a critical hit.
        - A petrified target has resistance to all damage (halved).

        Advantage and disadvantage cancel out per 5e rules: if a creature would
        have both, it rolls a single d20.
        """
        ranged = bool(getattr(attack, "ranged", False))

        # --- Assemble net advantage / disadvantage from conditions + request ---
        att_adv = advantage or conditions_mod.attack_roll_advantage(attacker)
        att_dis = disadvantage or conditions_mod.attack_roll_disadvantage(attacker)
        tgt_adv = conditions_mod.attacks_against_have_advantage(target, ranged=ranged)
        tgt_dis = conditions_mod.attacks_against_have_disadvantage(target, ranged=ranged)

        net_adv = att_adv or tgt_adv
        net_dis = att_dis or tgt_dis
        # roll_d20 already cancels simultaneous advantage+disadvantage.
        roll = roll_d20(attack.attack_bonus, advantage=net_adv, disadvantage=net_dis)

        # Determine the "used" die for natural-20/natural-1 detection. With
        # advantage we keep the higher die; with disadvantage the lower; a
        # straight (or cancelled) roll uses the single die.
        if net_adv and not net_dis:
            used_die = max(roll.rolls)
        elif net_dis and not net_adv:
            used_die = min(roll.rolls)
        else:
            used_die = roll.rolls[0]

        attack_total = roll.total

        critical = used_die == 20
        critical_miss = used_die == 1
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

        # A melee hit within 5 ft against a paralyzed/petrified/unconscious
        # target is always a critical hit.
        if not critical and conditions_mod.melee_auto_crit(target) and not ranged:
            critical = True

        damage = attack.roll_damage(critical=critical)
        # Resistance to all damage (e.g. petrified) halves the total, rounding down.
        if conditions_mod.has_damage_resistance(target):
            damage = damage // 2
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
