"""
Concentration engine — tracking concentration on spells and handling concentration checks.

Implements the DnD 5e concentration rules (PHB p.203-204):
- Only one concentration spell active at a time
- When taking damage while concentrating, make a Constitution saving throw
- DC = 10 or half the damage taken (rounded down), whichever is higher
- Critical hits force a concentration check (they don't auto-break)
- Psychic damage has special rules: if the damage was dealt by a spell or magical effect,
  it's handled the same as other damage
- Taking 0 damage doesn't trigger a check
- The caster loses concentration on a failed save
- Concentration ends when the caster casts another concentration spell
- Concentration ends when the caster is incapacitated or dies
- Concentration ends when the caster is subject to certain conditions (stunned, petrified,
  paralyzed, unconscious, or visibly distracted by the environment)

The engine is pure (no DB, no LLM) so it is trivially unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.engine.dice import roll_d20, ability_modifier


@dataclass
class ConcentrationState:
    """Tracks a character's current concentration state."""

    spell_name: str = ""  # The spell the character is concentrating on
    spell_id: str = ""    # The normalized spell ID
    is_concentrating: bool = False

    def to_dict(self) -> dict:
        return {
            "spell_name": self.spell_name,
            "spell_id": self.spell_id,
            "is_concentrating": self.is_concentrating,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConcentrationState":
        return cls(
            spell_name=data.get("spell_name", ""),
            spell_id=data.get("spell_id", ""),
            is_concentrating=data.get("is_concentrating", False),
        )


@dataclass
class ConcentrationCheckResult:
    """Result of a concentration check after taking damage."""

    damage_taken: int
    concentration_dc: int
    con_mod: int
    roll_total: int
    success: bool
    concentration_lost: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "damage_taken": self.damage_taken,
            "concentration_dc": self.concentration_dc,
            "con_mod": self.con_mod,
            "roll_total": self.roll_total,
            "success": self.success,
            "concentration_lost": self.concentration_lost,
            "reason": self.reason,
        }


def calculate_concentration_dc(damage_taken: int) -> int:
    """Calculate the DC for a concentration check after taking damage.

    DC = 10 or half the damage (rounded down), whichever is higher.
    """
    half_damage = damage_taken // 2
    return max(10, half_damage)


def check_concentration(
    concentration_state: ConcentrationState,
    damage_taken: int,
    con_score: int,
    proficiency_bonus: int,
    con_proficient: bool = False,
) -> ConcentrationCheckResult:
    """Make a concentration check after taking damage.

    Args:
        concentration_state: The current concentration state
        damage_taken: The damage actually taken (after resistances/immunities)
        con_score: The Constitution ability score
        proficiency_bonus: The character's proficiency bonus
        con_proficient: Whether the character is proficient in Constitution saves

    Returns:
        A ConcentrationCheckResult with the outcome
    """
    if not concentration_state.is_concentrating:
        return ConcentrationCheckResult(
            damage_taken=damage_taken,
            concentration_dc=0,
            con_mod=ability_modifier(con_score),
            roll_total=0,
            success=True,
            concentration_lost=False,
            reason="Not concentrating on any spell",
        )

    if damage_taken <= 0:
        return ConcentrationCheckResult(
            damage_taken=damage_taken,
            concentration_dc=0,
            con_mod=ability_modifier(con_score),
            roll_total=0,
            success=True,
            concentration_lost=False,
            reason="No damage taken",
        )

    dc = calculate_concentration_dc(damage_taken)
    con_mod = ability_modifier(con_score)

    # Constitution save proficiency bonus
    save_bonus = proficiency_bonus if con_proficient else 0

    # Roll the Constitution saving throw
    roll = roll_d20()
    roll_total = roll.total + con_mod + save_bonus
    success = roll_total >= dc

    return ConcentrationCheckResult(
        damage_taken=damage_taken,
        concentration_dc=dc,
        con_mod=con_mod,
        roll_total=roll_total,
        success=success,
        concentration_lost=not success,
        reason=f"Rolled {roll.total} + {con_mod} (Con mod) + {save_bonus} (prof) = {roll_total} vs DC {dc}"
        if success
        else f"Rolled {roll.total} + {con_mod} (Con mod) + {save_bonus} (prof) = {roll_total} vs DC {dc} (failed)",
    )


def start_concentration(spell_name: str, spell_id: str) -> ConcentrationState:
    """Start concentrating on a spell.

    Args:
        spell_name: The name of the spell
        spell_id: The normalized spell ID

    Returns:
        A new ConcentrationState with the spell information
    """
    return ConcentrationState(
        spell_name=spell_name,
        spell_id=spell_id,
        is_concentrating=True,
    )


def end_concentration(reason: str = "Concentration ended") -> ConcentrationState:
    """Stop concentrating on a spell.

    Args:
        reason: The reason for ending concentration (for logging)

    Returns:
        A ConcentrationState with is_concentrating=False
    """
    return ConcentrationState(
        spell_name="",
        spell_id="",
        is_concentrating=False,
    )


def can_concentrate(state: ConcentrationState) -> bool:
    """Check if a character can start concentrating."""
    return not state.is_concentrating


def should_break_concentration(conditions: list[str]) -> bool:
    """Check if current conditions should break concentration.

    Incapacitating conditions break concentration:
    - stunned
    - petrified
    - paralyzed
    - unconscious

    These conditions are tracked in the combat engine.
    """
    concentration_breaking = {
        "stunned",
        "petrified",
        "paralyzed",
        "unconscious",
    }
    return bool(set(conditions) & concentration_breaking)