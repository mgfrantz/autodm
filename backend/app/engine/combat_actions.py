"""
Combat actions engine — DnD 5e actions beyond the basic Attack action.

Each function is pure (no DB, no LLM): it operates on the
:class:`~app.engine.combat.Encounter` / :class:`~app.engine.combat.Combatant`
objects defined in :mod:`app.engine.combat` and returns a structured
:class:`ActionResult`.

Implemented actions (PHB "Actions in Combat"):

- **Dash** — gain movement equal to your speed (effectively double for the turn).
- **Disengage** — your movement provokes no opportunity attacks this turn.
- **Dodge** — attacks against you have disadvantage (and Dex saves have
  advantage) until the start of your next turn.
- **Help** — the next attack roll against the chosen target by an ally has
  advantage. (Tracked on the encounter and consumed in ``resolve_attack``.)
- **Grapple** — a Strength (Athletics) contest vs the target's best of Strength
  (Athletics) / Dexterity (Acrobatics). Success applies the *grappled*
  condition and records the grappler.
- **Shove** — the same contest; success either knocks the target *prone* or
  pushes it 5 ft away (attacker's choice).
- **Unarmed strike** — a melee attack dealing 1 + Str bludgeoning damage
  (monks may use a larger martial-arts die).
- **Two-weapon fighting** — a bonus-action off-hand attack with a light weapon
  that does NOT add the ability modifier to damage (unless the Two-Weapon
  Fighting fighting style applies).
- **Opportunity attack** — a reaction melee attack made when a creature leaves
  your reach; prevented if the mover took the Disengage action.

Reference: DnD 5e Player's Handbook, "Actions in Combat" (Ch. 9).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.engine.combat import Attack, AttackResult, Combatant, Encounter
from app.engine.dice import ability_modifier, roll_d20


# --------------------------------------------------------------------------- #
# Creature size categories (for the grapple/shove size restriction).
# --------------------------------------------------------------------------- #
SIZE_ORDER: dict[str, int] = {
    "tiny": 0,
    "small": 1,
    "medium": 2,
    "large": 3,
    "huge": 4,
    "gargantuan": 5,
}


def size_category(size: str) -> int:
    """Return the numeric size category (0-5), defaulting to medium (2)."""
    return SIZE_ORDER.get(str(size).lower(), 2)


def size_difference(a: Any, b: Any) -> int:
    """How many size categories larger ``a`` is than ``b`` (may be negative)."""
    return size_category(getattr(a, "size", "medium")) - size_category(
        getattr(b, "size", "medium")
    )


# --------------------------------------------------------------------------- #
# Skill-bonus derivation for contests.
# --------------------------------------------------------------------------- #
def athletics_bonus(combatant: Any) -> int:
    """The Strength (Athletics) check bonus for a combatant.

    Uses an explicit ``athletics_bonus`` if present, otherwise falls back to the
    Strength ability modifier.
    """
    explicit = getattr(combatant, "athletics_bonus", None)
    if explicit is not None:
        return explicit
    return ability_modifier(getattr(combatant, "strength", 10))


def acrobatics_bonus(combatant: Any) -> int:
    """The Dexterity (Acrobatics) check bonus for a combatant."""
    explicit = getattr(combatant, "acrobatics_bonus", None)
    if explicit is not None:
        return explicit
    return ability_modifier(getattr(combatant, "dexterity", 10))


def escape_bonus(combatant: Any) -> tuple[int, str]:
    """Best available check a grappled creature may use to escape a grapple.

    Per 5e the creature chooses Strength (Athletics) or Dexterity (Acrobatics).
    Returns ``(bonus, skill_name)`` for whichever is higher.
    """
    ath = athletics_bonus(combatant)
    acr = acrobatics_bonus(combatant)
    if acr > ath:
        return acr, "acrobatics"
    return ath, "athletics"


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #
@dataclass
class ContestResult:
    """The outcome of an opposed skill check (e.g. grapple/shove)."""

    attacker_skill: str
    attacker_total: int
    attacker_rolls: list[int]
    defender_skill: str
    defender_total: int
    defender_rolls: list[int]
    attacker_wins: bool  # a tie leaves the situation unchanged

    def to_dict(self) -> dict:
        return {
            "attacker_skill": self.attacker_skill,
            "attacker_total": self.attacker_total,
            "attacker_rolls": list(self.attacker_rolls),
            "defender_skill": self.defender_skill,
            "defender_total": self.defender_total,
            "defender_rolls": list(self.defender_rolls),
            "attacker_wins": self.attacker_wins,
        }


@dataclass
class ActionResult:
    """Generic result returned by every combat action."""

    action: str
    success: bool
    description: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "success": self.success,
            "description": self.description,
            "details": dict(self.details),
        }


# --------------------------------------------------------------------------- #
# Opposed-check core
# --------------------------------------------------------------------------- #
def run_contest(
    attacker_bonus: int,
    defender_bonus: int,
    attacker_skill: str = "athletics",
    defender_skill: str = "athletics",
) -> ContestResult:
    """Roll an opposed check; higher total wins (ties favour the defender).

    This models the PHB "Contests" rule. The attacker must strictly beat the
    defender's check to succeed.
    """
    atk = roll_d20(attacker_bonus)
    dfn = roll_d20(defender_bonus)
    return ContestResult(
        attacker_skill=attacker_skill,
        attacker_total=atk.total,
        attacker_rolls=list(atk.rolls),
        defender_skill=defender_skill,
        defender_total=dfn.total,
        defender_rolls=list(dfn.rolls),
        attacker_wins=atk.total > dfn.total,
    )


# --------------------------------------------------------------------------- #
# Movement & positioning actions
# --------------------------------------------------------------------------- #
def dash(encounter: Encounter, combatant: Combatant) -> ActionResult:
    """Dash: gain extra movement equal to your speed for the turn.

    A creature with speed 0 (grappled, restrained, etc.) gains no movement.
    """
    speed = combatant.effective_speed
    if speed <= 0:
        return ActionResult(
            action="dash",
            success=False,
            description=(
                f"{combatant.name} tries to Dash but has no movement to gain "
                f"(speed 0)."
            ),
            details={"available_movement": combatant.available_movement},
        )
    combatant.bonus_movement += speed
    encounter.log.append(
        f"{combatant.name} takes the Dash action (movement now "
        f"{combatant.available_movement} ft this turn)."
    )
    return ActionResult(
        action="dash",
        success=True,
        description=(
            f"{combatant.name} Dashes, gaining {speed} ft of movement "
            f"({combatant.available_movement} ft available this turn)."
        ),
        details={"available_movement": combatant.available_movement},
    )


def disengage(encounter: Encounter, combatant: Combatant) -> ActionResult:
    """Disengage: moving doesn't provoke opportunity attacks this turn."""
    combatant.disengaging = True
    encounter.log.append(
        f"{combatant.name} takes the Disengage action and won't provoke "
        f"opportunity attacks this turn."
    )
    return ActionResult(
        action="disengage",
        success=True,
        description=(
            f"{combatant.name} Disengages. Their movement provokes no "
            f"opportunity attacks until the end of the turn."
        ),
    )


def dodge(encounter: Encounter, combatant: Combatant) -> ActionResult:
    """Dodge: attacks against you have disadvantage until your next turn.

    The benefit is lost while incapacitated or at speed 0.
    """
    combatant.dodging = True
    encounter.log.append(
        f"{combatant.name} takes the Dodge action. Attacks against them have "
        f"disadvantage until their next turn."
    )
    return ActionResult(
        action="dodge",
        success=True,
        description=(
            f"{combatant.name} Dodges. Attack rolls against them have "
            f"disadvantage, and their Dexterity saving throws have advantage, "
            f"until the start of their next turn."
        ),
    )


# --------------------------------------------------------------------------- #
# Help action
# --------------------------------------------------------------------------- #
def help_ally(
    encounter: Encounter,
    helper: Combatant,
    target: Optional[Combatant] = None,
) -> ActionResult:
    """Help: the next attack roll against *target* (an enemy within reach) has
    advantage. If no target is given, the helper aids an ally for a future
    ability check (recorded narratively only).
    """
    if target is None:
        encounter.log.append(
            f"{helper.name} uses the Help action to aid an ally's next "
            f"ability check."
        )
        return ActionResult(
            action="help",
            success=True,
            description=(
                f"{helper.name} uses the Help action. An allied creature gains "
                f"advantage on its next ability check to perform the aided task."
            ),
            details={"aid_type": "ability_check"},
        )

    if target.id in encounter.help_advantage_targets:
        return ActionResult(
            action="help",
            success=True,
            description=(
                f"{helper.name} distracts {target.name}, who is already "
                f"vulnerable to the next attack."
            ),
            details={"aid_type": "attack", "target_id": target.id},
        )

    encounter.help_advantage_targets.append(target.id)
    encounter.log.append(
        f"{helper.name} uses the Help action against {target.name}: the next "
        f"attack against {target.name} has advantage."
    )
    return ActionResult(
        action="help",
        success=True,
        description=(
            f"{helper.name} feints/distracts {target.name}. The next attack "
            f"roll against {target.name} has advantage."
        ),
        details={"aid_type": "attack", "target_id": target.id},
    )


# --------------------------------------------------------------------------- #
# Grapple & Shove (special melee attacks)
# --------------------------------------------------------------------------- #
def _contest_defender(target: Combatant) -> tuple[int, str]:
    """The defender's best available check (athletics or acrobatics)."""
    ath = athletics_bonus(target)
    acr = acrobatics_bonus(target)
    if acr > ath:
        return acr, "acrobatics"
    return ath, "athletics"


def attempt_grapple(
    encounter: Encounter,
    attacker: Combatant,
    target: Combatant,
    free_hand: bool = True,
) -> ActionResult:
    """Grapple a creature (Strength Athletics contest).

    Requirements (PHB): a free hand; the target must be no more than one size
    larger than you; the target must not already be grappled *by you*.
    """
    if not free_hand:
        return ActionResult(
            action="grapple",
            success=False,
            description=f"{attacker.name} needs a free hand to grapple.",
        )
    if not target.is_alive:
        return ActionResult(
            action="grapple",
            success=False,
            description=f"{attacker.name} cannot grapple a dying {target.name}.",
        )
    if size_difference(target, attacker) > 1:
        return ActionResult(
            action="grapple",
            success=False,
            description=(
                f"{target.name} is too large for {attacker.name} to grapple "
                f"(more than one size category larger)."
            ),
            details={
                "attacker_size": attacker.size,
                "target_size": target.size,
            },
        )
    # Already grappled by this attacker -> nothing to do.
    if target.has_condition("grappled") and target.grappled_by == attacker.id:
        return ActionResult(
            action="grapple",
            success=True,
            description=f"{attacker.name} is already grappling {target.name}.",
        )

    def_bonus, def_skill = _contest_defender(target)
    contest = run_contest(
        athletics_bonus(attacker),
        def_bonus,
        attacker_skill="athletics",
        defender_skill=def_skill,
    )

    if not contest.attacker_wins:
        msg = (
            f"{attacker.name} fails to grapple {target.name} "
            f"(Athletics {contest.attacker_total} vs "
            f"{def_skill.capitalize()} {contest.defender_total})."
        )
        encounter.log.append(msg)
        return ActionResult(
            action="grapple",
            success=False,
            description=msg,
            details={"contest": contest.to_dict()},
        )

    target.add_condition("grappled")
    target.grappled_by = attacker.id
    msg = (
        f"{attacker.name} grapples {target.name} (Athletics "
        f"{contest.attacker_total} vs {def_skill.capitalize()} "
        f"{contest.defender_total}). {target.name}'s speed is now 0."
    )
    encounter.log.append(msg)
    return ActionResult(
        action="grapple",
        success=True,
        description=msg,
        details={
            "contest": contest.to_dict(),
            "target_id": target.id,
            "condition": "grappled",
        },
    )


def attempt_shove(
    encounter: Encounter,
    attacker: Combatant,
    target: Combatant,
    option: str = "prone",
    free_hand: bool = True,
) -> ActionResult:
    """Shove a creature — knock it prone or push it 5 ft away.

    Same contest as Grapple. ``option`` is ``"prone"`` or ``"push"``.
    """
    option = (option or "prone").lower()
    if option not in ("prone", "push"):
        return ActionResult(
            action="shove",
            success=False,
            description=f"Unknown shove option: {option!r} (use 'prone' or 'push').",
        )
    if not free_hand:
        return ActionResult(
            action="shove",
            success=False,
            description=f"{attacker.name} needs a free hand to shove.",
        )
    if not target.is_alive:
        return ActionResult(
            action="shove",
            success=False,
            description=f"{attacker.name} cannot shove a dying {target.name}.",
        )
    if size_difference(target, attacker) > 1:
        return ActionResult(
            action="shove",
            success=False,
            description=(
                f"{target.name} is too large for {attacker.name} to shove."
            ),
            details={
                "attacker_size": attacker.size,
                "target_size": target.size,
            },
        )

    def_bonus, def_skill = _contest_defender(target)
    contest = run_contest(
        athletics_bonus(attacker),
        def_bonus,
        attacker_skill="athletics",
        defender_skill=def_skill,
    )

    if not contest.attacker_wins:
        verb = "knock down" if option == "prone" else "push"
        msg = (
            f"{attacker.name} fails to shove {target.name} ({verb} attempt: "
            f"Athletics {contest.attacker_total} vs "
            f"{def_skill.capitalize()} {contest.defender_total})."
        )
        encounter.log.append(msg)
        return ActionResult(
            action="shove",
            success=False,
            description=msg,
            details={"contest": contest.to_dict(), "option": option},
        )

    if option == "prone":
        target.add_condition("prone")
        outcome = f"{target.name} is knocked prone"
    else:
        # No grid is tracked; record the push narratively + consume movement.
        attacker.movement_used += min(5, attacker.available_movement)
        outcome = f"{target.name} is shoved 5 ft away"
    msg = (
        f"{attacker.name} shoves {target.name} — {outcome} "
        f"(Athletics {contest.attacker_total} vs {def_skill.capitalize()} "
        f"{contest.defender_total})."
    )
    encounter.log.append(msg)
    return ActionResult(
        action="shove",
        success=True,
        description=msg,
        details={
            "contest": contest.to_dict(),
            "option": option,
            "target_id": target.id,
        },
    )


def escape_grapple(
    encounter: Encounter,
    combatant: Combatant,
) -> ActionResult:
    """Attempt to break free of a grapple (an action the grappled creature
    may take). Opposes the grappler's Athletics with the escaper's best check.
    """
    if not combatant.has_condition("grappled") or combatant.grappled_by is None:
        return ActionResult(
            action="escape",
            success=False,
            description=f"{combatant.name} is not grappled.",
        )
    grappler = next(
        (c for c in encounter.combatants if c.id == combatant.grappled_by), None
    )
    grappler_bonus = athletics_bonus(grappler) if grappler else 0
    esc_bonus, esc_skill = escape_bonus(combatant)
    contest = run_contest(
        esc_bonus,
        grappler_bonus,
        attacker_skill=esc_skill,
        defender_skill="athletics",
    )
    if not contest.attacker_wins:
        msg = (
            f"{combatant.name} fails to escape the grapple ({esc_skill} "
            f"{contest.attacker_total} vs Athletics {contest.defender_total})."
        )
        encounter.log.append(msg)
        return ActionResult(
            action="escape",
            success=False,
            description=msg,
            details={"contest": contest.to_dict()},
        )
    combatant.remove_condition("grappled")
    combatant.grappled_by = None
    msg = (
        f"{combatant.name} breaks free of the grapple ({esc_skill} "
        f"{contest.attacker_total} vs Athletics {contest.defender_total})."
    )
    encounter.log.append(msg)
    return ActionResult(
        action="escape",
        success=True,
        description=msg,
        details={"contest": contest.to_dict()},
    )


# --------------------------------------------------------------------------- #
# Unarmed strikes & two-weapon fighting
# --------------------------------------------------------------------------- #
def unarmed_strike(
    attack_bonus: int,
    str_mod: int = 0,
    monk_die_sides: int = 1,
    use_dex: bool = False,
    dex_mod: int = 0,
) -> Attack:
    """Build an unarmed-strike Attack.

    Damage is ``1 + Str mod`` (modelled as ``1d1 + Str``). Monks may instead use
    Dexterity and a larger martial-arts die (e.g. 1d4, scaling with level).
    """
    if use_dex:
        # Monks use Dex for the attack & damage of unarmed strikes.
        ability = dex_mod
        bonus = attack_bonus
    else:
        ability = str_mod
        bonus = attack_bonus
    damage_bonus = max(ability, 0) if monk_die_sides <= 1 else ability
    return Attack(
        name="Unarmed Strike",
        attack_bonus=bonus,
        damage_dice_count=1,
        damage_dice_sides=max(1, monk_die_sides),
        damage_bonus=damage_bonus,
        damage_type="bludgeoning",
    )


def off_hand_attack(
    encounter: Encounter,
    attacker: Combatant,
    target: Combatant,
    weapon: Attack,
    ability_mod: int = 0,
    two_weapon_style: bool = False,
) -> AttackResult:
    """Resolve a bonus-action off-hand attack (two-weapon fighting).

    Per PHB: when you wield two light melee weapons and take the Attack action,
    you may use a bonus action to attack with the off-hand weapon. You do **not**
    add your ability modifier to that attack's damage — unless it is negative,
    or you have the Two-Weapon Fighting fighting style.
    """
    off = Attack(
        name=weapon.name + " (off-hand)",
        attack_bonus=weapon.attack_bonus,
        damage_dice_count=weapon.damage_dice_count,
        damage_dice_sides=weapon.damage_dice_sides,
        damage_bonus=(ability_mod if two_weapon_style else min(ability_mod, 0)),
        damage_type=weapon.damage_type,
        ranged=weapon.ranged,
    )
    encounter.log.append(
        f"{attacker.name} makes a bonus-action off-hand attack with "
        f"{weapon.name}."
    )
    return encounter.resolve_attack(attacker, target, off)


# --------------------------------------------------------------------------- #
# Opportunity attacks (reaction)
# --------------------------------------------------------------------------- #
def opportunity_attack(
    encounter: Encounter,
    attacker: Combatant,
    target: Combatant,
) -> Optional[AttackResult]:
    """Make a reaction opportunity attack against *target* as it leaves reach.

    Returns ``None`` (no attack) if the target took Disengage this turn, or if
    the attacker has no melee attack available.
    """
    if getattr(target, "disengaging", False):
        encounter.log.append(
            f"{attacker.name} cannot make an opportunity attack: {target.name} "
            f"Disengaged."
        )
        return None
    melee = next((a for a in attacker.attacks if not a.ranged), None)
    if melee is None:
        # A creature with only ranged weapons still threatens with an unarmed
        # strike (range 5 ft), per 5e (unarmed strikes are melee weapon attacks).
        str_mod = ability_modifier(attacker.strength)
        melee = unarmed_strike(
            attack_bonus=0,
            str_mod=str_mod,
        )
    encounter.log.append(
        f"{attacker.name} makes a reaction opportunity attack against "
        f"{target.name}."
    )
    return encounter.resolve_attack(attacker, target, melee)


# --------------------------------------------------------------------------- #
# Action catalogue (for API/UI discovery)
# --------------------------------------------------------------------------- #
ACTIONS: dict[str, dict] = {
    "grapple": {
        "name": "Grapple",
        "description": (
            "Grab a creature (Str Athletics vs their Str Athletics/Dex "
            "Acrobatics). On a win it is grappled (speed 0)."
        ),
        "cost": "one attack",
        "requires_target": True,
    },
    "shove": {
        "name": "Shove",
        "description": (
            "Knock a creature prone or push it 5 ft (same contest as Grapple)."
        ),
        "cost": "one attack",
        "requires_target": True,
    },
    "dash": {
        "name": "Dash",
        "description": "Gain extra movement equal to your speed this turn.",
        "cost": "one action",
        "requires_target": False,
    },
    "disengage": {
        "name": "Disengage",
        "description": "Your movement provokes no opportunity attacks this turn.",
        "cost": "one action",
        "requires_target": False,
    },
    "dodge": {
        "name": "Dodge",
        "description": (
            "Attacks against you have disadvantage until your next turn."
        ),
        "cost": "one action",
        "requires_target": False,
    },
    "help": {
        "name": "Help",
        "description": (
            "Grant advantage on the next attack against a target (or an ally's "
            "next ability check)."
        ),
        "cost": "one action",
        "requires_target": True,
    },
    "unarmed-strike": {
        "name": "Unarmed Strike",
        "description": "A melee strike dealing 1 + Str bludgeoning damage.",
        "cost": "one attack",
        "requires_target": True,
    },
    "off-hand-attack": {
        "name": "Off-Hand Attack (Two-Weapon Fighting)",
        "description": (
            "Bonus-action attack with a light weapon; no ability mod to damage."
        ),
        "cost": "bonus action",
        "requires_target": True,
    },
    "escape": {
        "name": "Escape Grapple",
        "description": "Break free of a grapple (action while grappled).",
        "cost": "one action",
        "requires_target": False,
    },
    "opportunity-attack": {
        "name": "Opportunity Attack",
        "description": (
            "Reaction melee attack when a creature leaves your reach."
        ),
        "cost": "reaction",
        "requires_target": True,
    },
}


def list_actions() -> list[dict]:
    """Return all combat actions with their metadata (for UI/API discovery)."""
    return [
        {"key": key, **meta}
        for key, meta in ACTIONS.items()
    ]


# --------------------------------------------------------------------------- #
# Dispatcher (used by the REST API)
# --------------------------------------------------------------------------- #
def perform_action(
    encounter: Encounter,
    combatant: Combatant,
    action: str,
    target: Optional[Combatant] = None,
    option: Optional[str] = None,
) -> dict:
    """Dispatch a combat action by key.

    Returns a dict with ``action`` (an :class:`ActionResult` serialised) and,
    for attacks, an ``attack_result`` when one was produced.
    """
    action = (action or "").lower()
    if action not in ACTIONS:
        raise ValueError(f"Unknown combat action: {action!r}")

    # Actions that need a target must receive a living one.
    if ACTIONS[action]["requires_target"]:
        if target is None or not target.is_alive:
            return {
                "action_result": ActionResult(
                    action=action,
                    success=False,
                    description=(
                        f"{action!r} requires a valid living target."
                    ),
                ).to_dict()
            }

    attack_result: Optional[AttackResult] = None

    if action == "grapple":
        result = attempt_grapple(encounter, combatant, target)
    elif action == "shove":
        result = attempt_shove(encounter, combatant, target, option=option or "prone")
    elif action == "dash":
        result = dash(encounter, combatant)
    elif action == "disengage":
        result = disengage(encounter, combatant)
    elif action == "dodge":
        result = dodge(encounter, combatant)
    elif action == "help":
        result = help_ally(encounter, combatant, target)
    elif action == "escape":
        result = escape_grapple(encounter, combatant)
    elif action == "unarmed-strike":
        str_mod = ability_modifier(combatant.strength)
        strike = unarmed_strike(
            attack_bonus=_melee_attack_bonus(combatant),
            str_mod=str_mod,
        )
        attack_result = encounter.resolve_attack(combatant, target, strike)
        result = ActionResult(
            action="unarmed-strike",
            success=attack_result.hit,
            description=attack_result.description,
        )
    elif action == "off-hand-attack":
        weapon = next((a for a in combatant.attacks if not a.ranged), None)
        if weapon is None:
            result = ActionResult(
                action="off-hand-attack",
                success=False,
                description=f"{combatant.name} has no melee weapon for an off-hand attack.",
            )
        else:
            attack_result = off_hand_attack(
                encounter,
                combatant,
                target,
                weapon,
                ability_mod=ability_modifier(combatant.strength),
            )
            result = ActionResult(
                action="off-hand-attack",
                success=attack_result.hit,
                description=attack_result.description,
            )
    elif action == "opportunity-attack":
        ao = opportunity_attack(encounter, combatant, target)
        if ao is None:
            result = ActionResult(
                action="opportunity-attack",
                success=False,
                description="No opportunity attack was made.",
            )
        else:
            attack_result = ao
            result = ActionResult(
                action="opportunity-attack",
                success=ao.hit,
                description=ao.description,
            )
    else:  # pragma: no cover - guarded by the membership check above
        raise ValueError(f"Unhandled combat action: {action!r}")

    out: dict = {"action_result": result.to_dict()}
    if attack_result is not None:
        out["attack_result"] = {
            "hit": attack_result.hit,
            "critical": attack_result.critical,
            "critical_miss": attack_result.critical_miss,
            "damage": attack_result.damage,
            "target_remaining_hp": attack_result.target_remaining_hp,
        }
    return out


def _melee_attack_bonus(combatant: Combatant) -> int:
    """A reasonable to-hit bonus for an unarmed strike when no attack list is
    available: proficiency (none here) + Str/Dex mod. Defaults to Str mod."""
    str_mod = ability_modifier(combatant.strength)
    dex_mod = ability_modifier(combatant.dexterity)
    # Use the better of Str/Dex (monk flavour) — no proficiency bonus assumed.
    return max(str_mod, dex_mod)
