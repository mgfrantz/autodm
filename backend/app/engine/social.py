"""
Social Interaction engine — DnD 5e NPC interaction resolution rules.

The third pillar of DnD 5e (Combat, Exploration, **Social Interaction**) had no
resolution engine. ``world_state`` tracks an NPC's *attitude/trust*, but
provides none of the Dungeon Master's Guide adjudication that turns a roleplay
exchange into a deterministic mechanical outcome. This module closes that gap.

Sources: Dungeon Master's Guide ch. 4 "Creating NPCs" (NPC interaction,
attitude, influence) and ch. 8 "Running the Game" (reaction rolls); Player's
Handbook ch. 8 "Social Interaction".

Three resolution layers, in increasing specificity:

1. **Reaction roll** — ``reaction_roll()``. A 2d6 + Charisma modifier table
   that establishes an NPC's *initial* disposition when the DM hasn't pre-set
   one (the classic "the guard's mood when you walk up" roll). Maps to one of
   the five DMG attitude levels.

2. **Influence check** — ``influence_check()``. A Charisma (Persuasion /
   Intimidation / Deception / Performance) check against a DC derived from the
   NPC's *current* attitude; success shifts the attitude one step friendlier,
   failure by 5+ (or a natural 1) worsens it. This is the DMG ch.4 "Changing
   Attitude" table made mechanical.

3. **Insight-vs-Deception contest** — ``insight_check()``. Detect whether an
   NPC is lying: the player's Insight check vs the NPC's Deception (rolled or
   passive).

The module also:
- Maps the DMG five-level attitude scale (hostile/unfriendly/indifferent/
  friendly/helpful) onto the ``world_state.NPCRelationship`` trust score and
  seven-level attitude string so the two systems stay in sync
  (``attitude_for_trust``, ``trust_for_attitude``).
- Applies condition effects on social checks (charmed → advantage; frightened /
  poisoned → disadvantage) per PHB.
- Exposes ``npc_interaction_summary`` for the DM context block.

The engine is **pure** — no database, no LLM. All dice are injectable
(``reaction_dice``, ``save_roll``, ``deception_total``) for full determinism.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.engine.dice import roll_die, roll_dice, roll_d20


# --------------------------------------------------------------------------- #
# DMG ch.4 attitude scale — the five interaction levels, ordered hostile→helpful
# --------------------------------------------------------------------------- #

#: The five DMG attitude levels, ordered from most-hostile to most-friendly.
#: Index math relies on this ordering; do not reorder.
ATTITUDE_LEVELS: tuple[str, ...] = (
    "hostile",
    "unfriendly",
    "indifferent",
    "friendly",
    "helpful",
)

#: Alias mapping for the older seven-level ``world_state`` attitude strings.
#: The DMG five map cleanly onto the world_state scale; "neutral" there is
#: treated as equivalent to DMG "indifferent".
_ATTITUDE_ALIASES: dict[str, str] = {
    "neutral": "indifferent",
    "devoted": "helpful",
    "hated": "hostile",
}

#: Skills usable as a social-interaction *approach* (all Charisma-based).
SOCIAL_SKILLS: tuple[str, ...] = (
    "persuasion",
    "intimidation",
    "deception",
    "performance",
)


def normalize_attitude(attitude: Optional[str]) -> str:
    """Normalize an attitude string to one of the five DMG levels.

    Accepts the DMG five (hostile..helpful) and the world_state aliases
    (neutral, devoted, hated). Unknown values collapse to ``"indifferent"``.
    """
    a = (attitude or "indifferent").strip().lower()
    a = _ATTITUDE_ALIASES.get(a, a)
    if a not in ATTITUDE_LEVELS:
        return "indifferent"
    return a


def attitude_rank(attitude: Optional[str]) -> int:
    """Numeric rank of an attitude (0 = hostile … 4 = helpful)."""
    return ATTITUDE_LEVELS.index(normalize_attitude(attitude))


def attitude_at_rank(rank: int) -> str:
    """The attitude at a given rank, clamped to the valid range."""
    clamped = max(0, min(len(ATTITUDE_LEVELS) - 1, int(rank)))
    return ATTITUDE_LEVELS[clamped]


def shift_attitude(attitude: Optional[str], steps: int) -> str:
    """Return the attitude shifted by ``steps`` (negative = more hostile)."""
    return attitude_at_rank(attitude_rank(attitude) + int(steps))


# --------------------------------------------------------------------------- #
# Trust-score bridge — keep DMG attitude and world_state.NPCRelationship in sync
# --------------------------------------------------------------------------- #
# world_state uses a -100..100 trust score with seven bands; the DMG uses five.
# These maps let a social-interaction outcome update both representations.

#: DMG attitude → midpoint of the matching world_state trust band.
TRUST_FOR_ATTITUDE: dict[str, int] = {
    "hostile": -85,      # world_state "hostile" band (≤ -75)
    "unfriendly": -40,   # world_state "unfriendly" band (-74..-25)
    "indifferent": 0,    # world_state "neutral" band (-24..24)
    "friendly": 50,      # world_state "friendly" band (25..74)
    "helpful": 90,       # world_state "devoted" band (75..100)
}


def trust_for_attitude(attitude: Optional[str]) -> int:
    """The world_state trust score midpoint for a DMG attitude level."""
    return TRUST_FOR_ATTITUDE[normalize_attitude(attitude)]


def attitude_for_trust(trust: int) -> str:
    """The DMG attitude level for a world_state trust score."""
    t = int(trust)
    if t <= -75:
        return "hostile"
    if t <= -25:
        return "unfriendly"
    if t < 25:
        return "indifferent"
    if t < 75:
        return "friendly"
    return "helpful"


# --------------------------------------------------------------------------- #
# Condition effects on social checks (PHB)
# --------------------------------------------------------------------------- #

#: Conditions that grant advantage on social checks made *by* the bearer.
_ADVANTAGE_CONDITIONS: set[str] = {"charmed"}

#: Conditions that impose disadvantage on ability checks (incl. social).
_DISADVANTAGE_CONDITIONS: set[str] = {
    "frightened",
    "poisoned",
    "restrained",
    "blinded",
    "deafened",
}


def social_check_advantage(conditions: Optional[list[str]]) -> tuple[bool, bool]:
    """Resolve (advantage, disadvantage) for a social check given conditions.

    Per the PHB: ``charmed`` grants advantage on social checks toward the
    charmer; ``frightened``/``poisoned``/``restrained``/``blinded``/
    ``deafened`` impose disadvantage on the relevant checks. Advantage and
    disadvantage cancel (neither applies) when both are present, matching the
    d20 rule.
    """
    conds = {(c or "").lower() for c in (conditions or [])}
    adv = bool(conds & _ADVANTAGE_CONDITIONS)
    disadv = bool(conds & _DISADVANTAGE_CONDITIONS)
    if adv and disadv:
        return False, False
    return adv, disadv


# --------------------------------------------------------------------------- #
# Layer 1 — Reaction roll (initial NPC disposition, 2d6 + CHA mod)
# --------------------------------------------------------------------------- #
# Classic reaction table (2d6 + Charisma modifier). Used when no attitude is
# pre-established for a newly-met NPC. Higher is friendlier.
#
#   2–5  Hostile
#   6–8  Unfriendly
#   9–12 Indifferent
#   13–15 Friendly
#   16+  Helpful
_REACTION_BANDS: tuple[tuple[int, str], ...] = (
    (16, "helpful"),
    (13, "friendly"),
    (9, "indifferent"),
    (6, "unfriendly"),
    (2, "hostile"),
)


def _reaction_attitude(total: int) -> str:
    for threshold, attitude in _REACTION_BANDS:
        if total >= threshold:
            return attitude
    return "hostile"  # below 2 is impossible on 2d6 but be safe


@dataclass
class ReactionResult:
    """Outcome of an initial-reaction roll."""

    rolls: list[int]
    modifier: int
    total: int
    attitude: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rolls": list(self.rolls),
            "modifier": self.modifier,
            "total": self.total,
            "attitude": self.attitude,
            "description": self.description,
        }


def reaction_roll(
    charisma_modifier: int = 0,
    reaction_dice: Optional[tuple[int, int]] = None,
) -> ReactionResult:
    """Roll 2d6 + CHA mod for a newly-met NPC's initial disposition.

    Args:
        charisma_modifier: The character's Charisma modifier (applies per DMG).
        reaction_dice: An explicit ``(d1, d2)`` pair for determinism/testing.
            When ``None`` the dice are rolled.
    """
    if reaction_dice is not None:
        d1, d2 = int(reaction_dice[0]), int(reaction_dice[1])
    else:
        rolled = roll_dice(2, 6)
        d1, d2 = rolled.rolls[0], rolled.rolls[1]
    total = d1 + d2 + charisma_modifier
    attitude = _reaction_attitude(total)
    desc = (
        f"Reaction roll 2d6({d1}+{d2}) {charisma_modifier:+d} = {total} "
        f"→ {attitude}"
    )
    return ReactionResult(
        rolls=[d1, d2],
        modifier=charisma_modifier,
        total=total,
        attitude=attitude,
        description=desc,
    )


# --------------------------------------------------------------------------- #
# Layer 2 — Influence check (shift an NPC's attitude one step)
# --------------------------------------------------------------------------- #
# DMG ch.4 "Changing Attitude": the Charisma check DC to improve an NPC's
# attitude by one step depends on the current attitude. We also honour the
# common DM option that a failure by 5+ (or a natural 1) worsens attitude.

#: DC to *improve* an attitude by one step, keyed by the *current* attitude.
INFLUENCE_DC: dict[str, int] = {
    "hostile": 20,      # Hostile → Unfriendly
    "unfriendly": 15,   # Unfriendly → Indifferent
    "indifferent": 15,  # Indifferent → Friendly
    "friendly": 10,     # Friendly → Helpful
    "helpful": 0,       # Already cooperative; no check needed
}

#: How much the trust score moves on a one-step attitude change.
#: (Used only when no live NPCRelationship is available; the API syncs the
#: real NPC object directly.)
ATTITUDE_STEP_TRUST_DELTA: int = 30


@dataclass
class InfluenceResult:
    """Outcome of a single influence (Charisma) check against an NPC."""

    skill: str
    current_attitude: str
    target_attitude: str
    dc: int
    roll: int            # the raw d20
    modifier: int        # skill modifier applied
    total: int           # roll + modifier
    advantage: bool
    disadvantage: bool
    success: bool        # attitude improved one step
    worsened: bool       # attitude dropped one step (fail by 5+ or nat 1)
    new_attitude: str
    trust_delta: int     # suggested trust-score change to apply
    auto_success: bool   # True if already helpful (no check needed)
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill": self.skill,
            "current_attitude": self.current_attitude,
            "target_attitude": self.target_attitude,
            "dc": self.dc,
            "roll": self.roll,
            "modifier": self.modifier,
            "total": self.total,
            "advantage": self.advantage,
            "disadvantage": self.disadvantage,
            "success": self.success,
            "worsened": self.worsened,
            "new_attitude": self.new_attitude,
            "trust_delta": self.trust_delta,
            "auto_success": self.auto_success,
            "description": self.description,
        }


def influence_check(
    *,
    skill: str,
    skill_modifier: int,
    current_attitude: str,
    conditions: Optional[list[str]] = None,
    forced_advantage: bool = False,
    forced_disadvantage: bool = False,
    roll: Optional[int] = None,
    fail_margin_for_worsen: int = 5,
) -> InfluenceResult:
    """Resolve a Charisma check to improve an NPC's attitude by one step.

    Implements the DMG ch.4 "Changing Attitude" table: the DC is keyed to the
    NPC's *current* attitude. Success shifts the attitude one step friendlier;
    a failure by ``fail_margin_for_worsen`` (default 5) or more, or a natural 1,
    worsens the attitude by one step (a DM option that makes influence checks
    carry risk, matching how most tables run it).

    Args:
        skill: One of :data:`SOCIAL_SKILLS` (persuasion/intimidation/deception/
            performance). Other skills are accepted (treated as a generic
            Charisma check) but canonical approaches should use the list.
        skill_modifier: The character's full skill modifier (ability + prof +
            expertise). The caller computes this via ``skills``.
        current_attitude: The NPC's current DMG attitude level.
        conditions: Active combat conditions on the character (charmed grants
            advantage; frightened/poisoned/etc. impose disadvantage).
        forced_advantage / forced_disadvantage: Situation-based overrides
            (e.g., a known vulnerability to Intimidation).
        roll: An explicit d20 result for determinism/testing.
        fail_margin_for_worsen: How far below the DC a failure must be to
            worsen the attitude. Set to a large number (e.g., 99) to disable
            the worsen-on-failure rule for a gentler table.
    """
    skill_l = (skill or "persuasion").lower()
    cur = normalize_attitude(current_attitude)
    target = shift_attitude(cur, +1)
    dc = INFLUENCE_DC[cur]
    auto_success = cur == "helpful"  # already cooperative

    adv, disadv = social_check_advantage(conditions or [])
    if forced_advantage:
        adv = True
    if forced_disadvantage:
        disadv = True
    if adv and disadv:
        adv, disadv = False, False

    # Roll the d20 (with adv/disadv when not auto-success).
    if roll is not None:
        raw = int(roll)
        roll_display = raw
    else:
        r = roll_d20(modifier=0, advantage=adv, disadvantage=disadv)
        # For advantage/disadvantage the engine returns two dice; use the
        # selected one (max for advantage, min for disadvantage).
        raw = max(r.rolls) if adv else (min(r.rolls) if disadv else r.rolls[0])
        roll_display = raw

    modifier = int(skill_modifier)
    total = raw + modifier

    if auto_success:
        success = True
        worsened = False
        new_attitude = cur
        trust_delta = 0
        desc = (
            f"Already {cur} — no influence check needed; {skill_l} is automatic."
        )
    else:
        success = total >= dc
        nat1 = raw == 1
        failed_by = dc - total
        worsened = (not success) and (nat1 or failed_by >= fail_margin_for_worsen)

        if success:
            new_attitude = target
            trust_delta = ATTITUDE_STEP_TRUST_DELTA
        elif worsened:
            new_attitude = shift_attitude(cur, -1)
            trust_delta = -ATTITUDE_STEP_TRUST_DELTA
        else:
            new_attitude = cur
            trust_delta = 0

        adv_tag = ""
        if adv:
            adv_tag = " (advantage)"
        elif disadv:
            adv_tag = " (disadvantage)"
        outcome = "improves" if success else ("worsens" if worsened else "holds")
        desc = (
            f"Influence {skill_l}{adv_tag}: d20({roll_display}) {modifier:+d} "
            f"= {total} vs DC {dc} ({cur}) — attitude {outcome} "
            f"({cur} → {new_attitude})."
        )

    return InfluenceResult(
        skill=skill_l,
        current_attitude=cur,
        target_attitude=target,
        dc=dc,
        roll=roll_display,
        modifier=modifier,
        total=total,
        advantage=adv,
        disadvantage=disadv,
        success=success,
        worsened=worsened,
        new_attitude=new_attitude,
        trust_delta=trust_delta,
        auto_success=auto_success,
        description=desc,
    )


# --------------------------------------------------------------------------- #
# Layer 3 — Insight-vs-Deception contest (detect lies)
# --------------------------------------------------------------------------- #

@dataclass
class InsightResult:
    """Outcome of an Insight check to detect an NPC's deception."""

    insight_total: int
    insight_roll: Optional[int]
    insight_modifier: int
    deception_total: int
    detected: bool          # True = the lie is seen through
    contested: bool         # False when using the NPC's passive Deception
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "insight_total": self.insight_total,
            "insight_roll": self.insight_roll,
            "insight_modifier": self.insight_modifier,
            "deception_total": self.deception_total,
            "detected": self.detected,
            "contested": self.contested,
            "description": self.description,
        }


def insight_check(
    *,
    insight_modifier: int,
    npc_deception_total: Optional[int] = None,
    npc_passive_deception: Optional[int] = None,
    insight_roll: Optional[int] = None,
) -> InsightResult:
    """Resolve an Insight check against an NPC's Deception to detect a lie.

    Either an explicit ``npc_deception_total`` (a rolled Deception) or a
    ``npc_passive_deception`` (10 + Deception modifier, the resting lie skill)
    must be supplied. The player's Insight check (rolled unless ``insight_roll``
    is given) must meet or beat the NPC's Deception total to detect the lie.

    Args:
        insight_modifier: The player's Insight skill modifier.
        npc_deception_total: A rolled NPC Deception total (active contest).
        npc_passive_deception: The NPC's passive Deception (10 + Deception mod).
        insight_roll: An explicit d20 for the Insight check (determinism).
    """
    if npc_deception_total is None and npc_passive_deception is None:
        raise ValueError(
            "insight_check requires npc_deception_total or npc_passive_deception"
        )

    contested = npc_deception_total is not None
    if contested:
        deception_total = int(npc_deception_total)
    else:
        deception_total = int(npc_passive_deception) if npc_passive_deception is not None else 10

    modifier = int(insight_modifier)
    if insight_roll is not None:
        raw = int(insight_roll)
        roll_val: Optional[int] = raw
    else:
        raw = roll_die(20)
        roll_val = raw
    total = raw + modifier
    detected = total >= deception_total

    kind = "active Deception" if contested else "passive Deception"
    desc = (
        f"Insight d20({raw}) {modifier:+d} = {total} vs NPC {kind} "
        f"{deception_total} — {'lie detected' if detected else 'deception holds'}."
    )
    return InsightResult(
        insight_total=total,
        insight_roll=roll_val,
        insight_modifier=modifier,
        deception_total=deception_total,
        detected=detected,
        contested=contested,
        description=desc,
    )


# --------------------------------------------------------------------------- #
# DM / UI summary helper
# --------------------------------------------------------------------------- #

def npc_interaction_summary(
    npc_name: str,
    attitude: Optional[str],
    trust: Optional[int] = None,
) -> str:
    """A one-line DM-context summary of an NPC's current interaction stance.

    Includes the DMG attitude level, the (optional) world_state trust score,
    and the DC the player would need to improve the relationship — the exact
    information a DM needs mid-conversation without consulting the table.
    """
    att = normalize_attitude(attitude)
    dc = INFLUENCE_DC[att]
    trust_str = f", trust {trust}" if trust is not None else ""
    if att == "helpful":
        return f"{npc_name}: {att}{trust_str} — already cooperative."
    return f"{npc_name}: {att}{trust_str} — improve DC {dc} ({att}→{shift_attitude(att, +1)})."
