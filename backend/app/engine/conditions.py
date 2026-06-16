"""
Conditions engine — DnD 5e condition mechanics.

Defines the 14 core conditions and the combat effects each imposes:

- advantage / disadvantage on the afflicted creature's own attack rolls
- advantage / disadvantage on attacks *against* the afflicted creature
- incapacitation (the creature cannot take actions)
- automatic critical hits on melee hits within 5 ft
- resistance to all damage
- speed reduction to 0
- timed durations (in rounds), ticked down at the end of each round

The module is pure: every helper operates on a combatant-like object that
exposes a ``conditions`` list (of condition-name strings) and an optional
``condition_durations`` mapping (condition name -> rounds remaining). This
makes the engine fully unit-testable without a database or LLM.

Reference: DnD 5e Player's Handbook, "Conditions" (Appendix A).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ConditionRules:
    """The mechanical effects of a single DnD 5e condition."""

    name: str
    description: str
    # This creature's own attack rolls gain advantage (e.g. invisible).
    attack_advantage: bool = False
    # This creature's own attack rolls suffer disadvantage (e.g. poisoned).
    attack_disadvantage: bool = False
    # Attacks against this creature gain advantage (e.g. stunned).
    defense_advantage: bool = False
    # Attacks against this creature suffer disadvantage (e.g. invisible).
    defense_disadvantage: bool = False
    # The creature is incapacitated: it cannot take actions or reactions.
    incapacitated: bool = False
    # Any melee hit against this creature within 5 ft is a critical hit.
    melee_auto_crit: bool = False
    # The creature has resistance to all damage (e.g. petrified).
    damage_resistance: bool = False
    # The creature's speed becomes 0 (e.g. grappled, restrained).
    speed_zero: bool = False


# --------------------------------------------------------------------------- #
# Registry — all 14 core DnD 5e conditions.
# --------------------------------------------------------------------------- #
CONDITIONS: dict[str, ConditionRules] = {
    "blinded": ConditionRules(
        name="blinded",
        description=(
            "A blinded creature can't see and automatically fails any ability "
            "check that requires sight. Attack rolls against the creature have "
            "advantage, and the creature's attack rolls have disadvantage."
        ),
        attack_disadvantage=True,
        defense_advantage=True,
    ),
    "charmed": ConditionRules(
        name="charmed",
        description=(
            "A charmed creature can't attack the charmer or target the charmer "
            "with harmful abilities or magical effects. The charmer has "
            "advantage on ability checks to interact socially with the creature."
        ),
    ),
    "deafened": ConditionRules(
        name="deafened",
        description=(
            "A deafened creature can't hear and automatically fails any ability "
            "check that requires hearing."
        ),
    ),
    "frightened": ConditionRules(
        name="frightened",
        description=(
            "A frightened creature has disadvantage on ability checks and attack "
            "rolls while the source of its fear is within line of sight. The "
            "creature can't willingly move closer to the source of its fear."
        ),
        attack_disadvantage=True,
    ),
    "grappled": ConditionRules(
        name="grappled",
        description=(
            "A grappled creature's speed becomes 0, and it can't benefit from any "
            "bonus to its speed. The condition ends if the grappler is "
            "incapacitated or moved out of reach."
        ),
        speed_zero=True,
    ),
    "incapacitated": ConditionRules(
        name="incapacitated",
        description=(
            "An incapacitated creature can't take actions or reactions."
        ),
        incapacitated=True,
    ),
    "invisible": ConditionRules(
        name="invisible",
        description=(
            "An invisible creature is impossible to see without the aid of magic "
            "or a special sense. Attack rolls against the creature have "
            "disadvantage, and the creature's attack rolls have advantage."
        ),
        attack_advantage=True,
        defense_disadvantage=True,
    ),
    "paralyzed": ConditionRules(
        name="paralyzed",
        description=(
            "A paralyzed creature is incapacitated and can't move or speak. It "
            "automatically fails Strength and Dexterity saving throws. Attack "
            "rolls against the creature have advantage, and any attack that hits "
            "the creature is a critical hit if the attacker is within 5 feet."
        ),
        incapacitated=True,
        speed_zero=True,
        defense_advantage=True,
        melee_auto_crit=True,
    ),
    "petrified": ConditionRules(
        name="petrified",
        description=(
            "A petrified creature is transformed, along with its nonmagical "
            "objects, into a solid inanimate substance (usually stone). Its "
            "weight increases by a factor of ten, and it ceases aging. It is "
            "incapacitated, can't move or speak, and is unaware of its "
            "surroundings. Attack rolls against it have advantage, any hit "
            "within 5 ft is a critical hit, and it has resistance to all damage."
        ),
        incapacitated=True,
        speed_zero=True,
        defense_advantage=True,
        melee_auto_crit=True,
        damage_resistance=True,
    ),
    "poisoned": ConditionRules(
        name="poisoned",
        description=(
            "A poisoned creature has disadvantage on attack rolls and ability "
            "checks."
        ),
        attack_disadvantage=True,
    ),
    "prone": ConditionRules(
        name="prone",
        description=(
            "A prone creature's only movement option is to crawl. The creature "
            "has disadvantage on attack rolls. An attack against the creature has "
            "advantage if the attacker is within 5 feet (melee), or disadvantage "
            "otherwise (ranged)."
        ),
        # NOTE: prone's defense depends on whether the attack is melee or ranged,
        # so it is resolved in the query helpers below, not in the registry flags.
        attack_disadvantage=True,
    ),
    "restrained": ConditionRules(
        name="restrained",
        description=(
            "A restrained creature's speed becomes 0, and it can't benefit from "
            "any bonus to its speed. Attack rolls against the creature have "
            "advantage, and the creature's attack rolls and Dexterity saving "
            "throws have disadvantage."
        ),
        attack_disadvantage=True,
        defense_advantage=True,
        speed_zero=True,
    ),
    "stunned": ConditionRules(
        name="stunned",
        description=(
            "A stunned creature is incapacitated, can't move, and can speak only "
            "falteringly. Attack rolls against the creature have advantage."
        ),
        incapacitated=True,
        defense_advantage=True,
    ),
    "unconscious": ConditionRules(
        name="unconscious",
        description=(
            "An unconscious creature is incapacitated, can't move or speak, and "
            "is unaware of its surroundings. The creature drops whatever it's "
            "holding and falls prone. It automatically fails Strength and "
            "Dexterity saving throws. Attack rolls against the creature have "
            "advantage, and any attack that hits within 5 ft is a critical hit."
        ),
        incapacitated=True,
        speed_zero=True,
        defense_advantage=True,
        melee_auto_crit=True,
    ),
}

#: Conditions that confer incapacitation (directly or transitively).
INCAPACITATING_CONDITIONS: frozenset[str] = frozenset(
    name for name, rules in CONDITIONS.items() if rules.incapacitated
)


def list_conditions() -> list[str]:
    """Return the names of all known conditions, sorted."""
    return sorted(CONDITIONS.keys())


def is_valid_condition(name: str) -> bool:
    """True if *name* is a recognised DnD 5e condition."""
    return name in CONDITIONS


def get_condition_info(name: str) -> Optional[dict[str, Any]]:
    """Return a serialisable description of a condition, or None if unknown."""
    rules = CONDITIONS.get(name)
    if rules is None:
        return None
    return {
        "name": rules.name,
        "description": rules.description,
        "attack_advantage": rules.attack_advantage,
        "attack_disadvantage": rules.attack_disadvantage,
        "defense_advantage": rules.defense_advantage,
        "defense_disadvantage": rules.defense_disadvantage,
        "incapacitated": rules.incapacitated,
        "melee_auto_crit": rules.melee_auto_crit,
        "damage_resistance": rules.damage_resistance,
        "speed_zero": rules.speed_zero,
    }


# --------------------------------------------------------------------------- #
# Combatant state helpers — each operates on a combatant-like object.
# --------------------------------------------------------------------------- #

def _active_rules(combatant: Any) -> list[ConditionRules]:
    """Return the ConditionRules for every recognised condition on *combatant*."""
    conds = getattr(combatant, "conditions", []) or []
    return [CONDITIONS[c] for c in conds if c in CONDITIONS]


def has_condition(combatant: Any, name: str) -> bool:
    """True if *combatant* currently has the named condition."""
    return name in (getattr(combatant, "conditions", []) or [])


def is_incapacitated(combatant: Any) -> bool:
    """True if the combatant has any incapacitating condition."""
    return any(rules.incapacitated for rules in _active_rules(combatant))


def attack_roll_advantage(combatant: Any) -> bool:
    """Does the combatant's own attack roll gain advantage from conditions?"""
    return any(rules.attack_advantage for rules in _active_rules(combatant))


def attack_roll_disadvantage(combatant: Any) -> bool:
    """Does the combatant's own attack roll suffer disadvantage from conditions?"""
    return any(rules.attack_disadvantage for rules in _active_rules(combatant))


def attacks_against_have_advantage(combatant: Any, ranged: bool = False) -> bool:
    """Do attacks *against* this combatant gain advantage from its conditions?

    ``ranged`` distinguishes the prone edge case: a prone target is easier to
    hit in melee (advantage) but harder to hit at range.
    """
    adv = any(rules.defense_advantage for rules in _active_rules(combatant))
    if not ranged and has_condition(combatant, "prone"):
        adv = True
    return adv


def attacks_against_have_disadvantage(combatant: Any, ranged: bool = False) -> bool:
    """Do attacks *against* this combatant suffer disadvantage from its conditions?"""
    dis = any(rules.defense_disadvantage for rules in _active_rules(combatant))
    if ranged and has_condition(combatant, "prone"):
        dis = True
    return dis


def melee_auto_crit(combatant: Any) -> bool:
    """Should a melee hit against this combatant within 5 ft be a critical hit?"""
    return any(rules.melee_auto_crit for rules in _active_rules(combatant))


def has_damage_resistance(combatant: Any) -> bool:
    """Does the combatant have resistance to all damage from conditions?"""
    return any(rules.damage_resistance for rules in _active_rules(combatant))


def effective_speed(combatant: Any) -> int:
    """Return the combatant's effective speed (0 if any speed-zero condition)."""
    if any(rules.speed_zero for rules in _active_rules(combatant)):
        return 0
    return getattr(combatant, "speed", 30)


# --------------------------------------------------------------------------- #
# Duration management — conditions may be timed (in rounds) or permanent.
# --------------------------------------------------------------------------- #

def get_durations(combatant: Any) -> dict[str, int]:
    """Return the (mutable) condition-durations dict, creating it if absent."""
    durations = getattr(combatant, "condition_durations", None)
    if durations is None:
        durations = {}
        try:
            combatant.condition_durations = durations
        except Exception:
            # Fallback for frozen/typed objects: operate on a local copy.
            pass
    return durations


def apply_condition(combatant: Any, name: str, duration: Optional[int] = None) -> bool:
    """Apply a condition to a combatant.

    ``duration`` (in rounds) is optional. A condition with no duration is
    permanent until explicitly removed. Returns True if the condition was newly
    applied (False if already present — duration is still refreshed).
    """
    if not is_valid_condition(name):
        raise ValueError(f"Unknown condition: {name!r}")
    if duration is not None and duration < 1:
        raise ValueError("duration must be a positive number of rounds")

    conditions = getattr(combatant, "conditions", None)
    if conditions is None:
        conditions = []
        combatant.conditions = conditions
    already = name in conditions
    if not already:
        conditions.append(name)

    durations = get_durations(combatant)
    if duration is not None:
        durations[name] = duration
    elif name in durations:
        # Make a freshly-applied permanent condition permanent.
        durations.pop(name, None)
    return not already


def remove_condition(combatant: Any, name: str) -> bool:
    """Remove a condition from a combatant. Returns True if it was present."""
    conditions = getattr(combatant, "conditions", []) or []
    removed = False
    if name in conditions:
        conditions.remove(name)
        removed = True
    get_durations(combatant).pop(name, None)
    return removed


def tick_conditions(combatant: Any) -> list[str]:
    """Advance timed conditions by one round.

    Decrements the remaining duration of every tracked condition and removes
    those whose duration reaches 0. Conditions with no duration entry are
    permanent and are left untouched. Returns the list of conditions that
    expired this tick.
    """
    durations = get_durations(combatant)
    conditions = getattr(combatant, "conditions", []) or []
    expired: list[str] = []
    for name in list(durations.keys()):
        durations[name] -= 1
        if durations[name] <= 0:
            durations.pop(name, None)
            if name in conditions:
                conditions.remove(name)
            expired.append(name)
    return expired


def remaining_duration(combatant: Any, name: str) -> Optional[int]:
    """Remaining rounds for a timed condition, or None if permanent/absent."""
    if not has_condition(combatant, name):
        return None
    return get_durations(combatant).get(name)


def describe(combatant: Any) -> list[dict[str, Any]]:
    """Return a list of {name, description, duration} dicts for each condition."""
    conditions = getattr(combatant, "conditions", []) or []
    durations = get_durations(combatant)
    out: list[dict[str, Any]] = []
    for name in conditions:
        info = get_condition_info(name)
        if info is None:
            # Unknown/free-form condition label — keep it for compatibility.
            out.append({"name": name, "description": "", "duration": durations.get(name)})
        else:
            out.append({**info, "duration": durations.get(name)})
    return out
