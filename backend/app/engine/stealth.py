"""
Stealth and hiding engine — DnD 5e stealth mechanics.

Implements faithful DnD 5e stealth rules:

- **Hide action**: Dexterity (Stealth) check to become unseen
- **Detection**: Passive Perception vs stealth DC
- **Unseen attackers**: Hidden attackers have advantage on attacks;
  attacks against hidden attackers have disadvantage
- **Reveal on attack**: Making an attack reveals your position
- **Invisibility integration**: Hidden state applies the *invisible* condition
  for advantage/disadvantage mechanics

The engine is pure (no DB, no LLM) and operates on Combatant objects.
Reference: DnD 5e Player's Handbook, "Hiding" (Ch. 7).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.engine.dice import roll_d20
from app.engine.skills import calculate_skill_modifier


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #
@dataclass
class HideResult:
    """Result of a Hide action."""

    stealth_roll: int
    stealth_dc: int
    success: bool
    hidden: bool
    description: str
    breakdown: dict  # {ability, ability_modifier, proficiency, expertise, roll, total}

    def to_dict(self) -> dict:
        return {
            "stealth_roll": self.stealth_roll,
            "stealth_dc": self.stealth_dc,
            "success": self.success,
            "hidden": self.hidden,
            "description": self.description,
            "breakdown": dict(self.breakdown),
        }


@dataclass
class StealthCheckResult:
    """Result of checking if a hidden creature is detected."""

    creature_id: str
    stealth_dc: int
    observer_passive_perception: int
    detected: bool
    description: str

    def to_dict(self) -> dict:
        return {
            "creature_id": self.creature_id,
            "stealth_dc": self.stealth_dc,
            "observer_passive_perception": self.observer_passive_perception,
            "detected": self.detected,
            "description": self.description,
        }


# --------------------------------------------------------------------------- #
# Core stealth mechanics
# --------------------------------------------------------------------------- #
def attempt_hide(
    combatant,
    character=None,
    rolls: list[int] | None = None,
) -> HideResult:
    """Attempt the Hide action.

    Makes a Dexterity (Stealth) check. On success, the combatant becomes hidden.
    The stealth DC is set to the roll total (for detection via passive Perception).

    Args:
        combatant: The Combatant attempting to hide.
        character: Optional character-like object for skill modifier calculation.
                   If None, falls back to Dexterity modifier only.
        rolls: Optional list of dice rolls (for deterministic testing).

    Returns:
        HideResult with the outcome and breakdown.
    """
    # Calculate stealth modifier
    if character is not None:
        modifier = calculate_skill_modifier("stealth", character)
        # Build breakdown for UI
        from app.engine.skills import (
            SKILL_ABILITIES,
            get_all_skill_expertise,
            get_all_skill_proficiencies,
        )
        ability = SKILL_ABILITIES["stealth"]
        profs = get_all_skill_proficiencies(character)
        exp = get_all_skill_expertise(character)
        from app.engine.saving_throws import get_ability_score, get_character_level
        from app.engine.dice import ability_modifier, proficiency_bonus

        score = get_ability_score(character, ability)
        ab_mod = ability_modifier(score)
        level = get_character_level(character)
        pb = proficiency_bonus(level)
        prof_mult = 0
        if "stealth" in profs:
            prof_mult = 2 if "stealth" in exp else 1
        breakdown = {
            "ability": ability,
            "ability_score": score,
            "ability_modifier": ab_mod,
            "proficient": "stealth" in profs,
            "expertise": "stealth" in exp,
            "proficiency_bonus": pb * prof_mult,
            "modifier": modifier,
        }
    else:
        # Fallback: Dexterity modifier only
        from app.engine.dice import ability_modifier

        modifier = ability_modifier(getattr(combatant, "dexterity", 10))
        breakdown = {
            "ability": "dexterity",
            "ability_score": getattr(combatant, "dexterity", 10),
            "ability_modifier": modifier,
            "proficient": False,
            "expertise": False,
            "proficiency_bonus": 0,
            "modifier": modifier,
        }

    # Roll the check
    if rolls is not None and len(rolls) > 0:
        # Deterministic testing: use provided roll
        roll_total = rolls[0] + modifier
        used_roll = rolls[0]
    else:
        roll_result = roll_d20(modifier)
        roll_total = roll_result.total
        used_roll = roll_result.rolls[0]

    stealth_dc = roll_total

    # Set hidden state on combatant
    combatant.hidden = True
    combatant.stealth_roll = roll_total
    combatant.stealth_dc = stealth_dc

    description = (
        f"{combatant.name} hides with a stealth check of {roll_total} "
        f"(rolled {used_roll} + {modifier})."
    )

    return HideResult(
        stealth_roll=roll_total,
        stealth_dc=stealth_dc,
        success=True,
        hidden=True,
        description=description,
        breakdown=breakdown,
    )


def check_detection(
    hidden_creature,
    observer_passive_perception: int,
) -> StealthCheckResult:
    """Check if a hidden creature is detected by passive Perception.

    A hidden creature is detected if the observer's passive Perception
    meets or exceeds the creature's stealth DC.

    Args:
        hidden_creature: The hidden Combatant.
        observer_passive_perception: Observer's passive Perception score.

    Returns:
        StealthCheckResult with detection status.
    """
    stealth_dc = getattr(hidden_creature, "stealth_dc", 0)
    detected = observer_passive_perception >= stealth_dc

    if detected:
        description = (
            f"{hidden_creature.name} is detected "
            f"(passive Perception {observer_passive_perception} >= stealth DC {stealth_dc})."
        )
    else:
        description = (
            f"{hidden_creature.name} remains hidden "
            f"(passive Perception {observer_passive_perception} < stealth DC {stealth_dc})."
        )

    return StealthCheckResult(
        creature_id=hidden_creature.id,
        stealth_dc=stealth_dc,
        observer_passive_perception=observer_passive_perception,
        detected=detected,
        description=description,
    )


def reveal(combatant) -> None:
    """Reveal a hidden creature (clear hidden state).

    Called when a hidden creature makes an attack or otherwise reveals itself.
    """
    if hasattr(combatant, "hidden"):
        combatant.hidden = False
    if hasattr(combatant, "stealth_roll"):
        combatant.stealth_roll = 0
    if hasattr(combatant, "stealth_dc"):
        combatant.stealth_dc = 0


def is_hidden(combatant) -> bool:
    """Check if a combatant is currently hidden."""
    return getattr(combatant, "hidden", False)


def get_stealth_dc(combatant) -> int:
    """Get the stealth DC for a hidden creature (0 if not hidden)."""
    return getattr(combatant, "stealth_dc", 0) if is_hidden(combatant) else 0


def list_visible_enemies(
    combatants: list,
    observer_passive_perception: int,
    enemy_side: str = "enemy",
) -> dict[str, StealthCheckResult]:
    """For a given observer, determine which enemies are visible.

    Returns a dict mapping enemy id to StealthCheckResult.
    Visible (not hidden or detected) enemies have detected=True.
    Hidden and undetected enemies have detected=False.

    Args:
        combatants: All combatants in the encounter.
        observer_passive_perception: Observer's passive Perception.
        enemy_side: The side to check (typically "enemy" or "player").

    Returns:
        Dict of combatant_id -> StealthCheckResult.
    """
    results = {}
    enemies = [c for c in combatants if c.side == enemy_side and c.is_alive]

    for enemy in enemies:
        if not is_hidden(enemy):
            # Not hidden -> automatically visible
            results[enemy.id] = StealthCheckResult(
                creature_id=enemy.id,
                stealth_dc=0,
                observer_passive_perception=observer_passive_perception,
                detected=True,
                description=f"{enemy.name} is visible (not hidden).",
            )
        else:
            # Hidden -> check detection
            results[enemy.id] = check_detection(enemy, observer_passive_perception)

    return results


def get_stealth_status(combatant) -> dict:
    """Get the full stealth status of a combatant."""
    hidden = is_hidden(combatant)
    stealth_roll = getattr(combatant, "stealth_roll", 0)
    stealth_dc = getattr(combatant, "stealth_dc", 0)

    if not hidden:
        return {
            "hidden": False,
            "stealth_roll": 0,
            "stealth_dc": 0,
            "description": f"{combatant.name} is not hidden.",
        }

    return {
        "hidden": True,
        "stealth_roll": stealth_roll,
        "stealth_dc": stealth_dc,
        "description": (
            f"{combatant.name} is hidden (stealth DC {stealth_dc}). "
            f"Enemies must beat this DC with passive Perception to detect them."
        ),
    }