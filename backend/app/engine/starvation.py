"""
Starvation & dehydration engine — DnD 5e food/water survival rules.

This closes the loop opened by the environment engine: extreme heat/cold
already force Constitution saves that add *exhaustion*, but nothing modelled
the more common, persistent survival pressure — going without enough food and
water. Per the Player's Handbook (ch. 8 "Food and Water") and the Dungeon
Master's Guide (ch. 5), inadequate sustenance is itself a driver of the
Exhaustion special state:

WATER (thirst)
- A character needs 1 gallon of water per day, or 2 gallons in hot weather.
- A character who drinks only **half** the required water must succeed on a
  DC 15 Constitution saving throw each day or suffer 1 level of exhaustion.
- A character who drinks **less than half** automatically suffers 1 level of
  exhaustion.

FOOD (starvation)
- A character needs 1 pound of food per day.
- A character can go without food for a number of days equal to
  ``3 + Constitution modifier`` (minimum 1) without ill effect.
- Each day beyond that grace period, the character **automatically** suffers
  1 level of exhaustion.
- A normal day of eating (at least the full daily need) resets the count of
  days without food to zero.

Exhaustion itself is tracked by the existing ``exhaustion`` system
(``game_state["exhaustion"]``). This engine only tracks the *drivers* (the
consecutive-day counters) and computes the exhaustion delta a given day of
deprivation should inflict; the API layer applies that delta.

The module is **pure** — no database, no LLM. The daily save is injectable
(``save_roll``) so the engine is fully deterministic under test.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.engine.dice import roll_d20


# --------------------------------------------------------------------------- #
# Constants (PHB ch. 8 "Food and Water").
# --------------------------------------------------------------------------- #

#: Pounds of food a Medium character needs each day.
DAILY_FOOD_LBS: float = 1.0
#: Gallons of water a character needs each day in temperate weather.
DAILY_WATER_GAL: float = 1.0
#: Gallons of water a character needs each day in hot weather.
HOT_WATER_GAL: float = 2.0
#: DC of the Constitution saving throw against dehydration (DMG).
THIRST_SAVE_DC: int = 15


# --------------------------------------------------------------------------- #
# Survival state — the consecutive-day deprivation counters.
# --------------------------------------------------------------------------- #

@dataclass
class SurvivalState:
    """The persistent drivers of starvation/dehydration exhaustion.

    Exhaustion levels are *not* stored here (the exhaustion system owns them);
    these counters only track how many consecutive days the character has gone
    without sufficient food/water so the engine can decide when to add a level.
    """

    #: Consecutive days on less than the full daily food need.
    days_without_food: int = 0
    #: Consecutive days on less than the full daily water need.
    days_without_water: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "days_without_food": self.days_without_food,
            "days_without_water": self.days_without_water,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "SurvivalState":
        data = data or {}
        try:
            return cls(
                days_without_food=max(0, int(data.get("days_without_food", 0) or 0)),
                days_without_water=max(0, int(data.get("days_without_water", 0) or 0)),
            )
        except (TypeError, ValueError):
            return cls()


# --------------------------------------------------------------------------- #
# Derived lookups.
# --------------------------------------------------------------------------- #

def food_grace_days(con_modifier: int) -> int:
    """How many days a character can go without food before suffering.

    ``3 + Constitution modifier`` (minimum 1), per the PHB.
    """
    return max(1, 3 + int(con_modifier))


def daily_needs(hot: bool = False) -> dict[str, float]:
    """The food/water a character must consume each day to stay healthy."""
    return {
        "food": DAILY_FOOD_LBS,
        "water": HOT_WATER_GAL if hot else DAILY_WATER_GAL,
    }


def is_hot(temperature: str) -> bool:
    """Whether a temperature level counts as 'hot' (doubling water needs).

    The environment engine's ``heat`` and ``extreme_heat`` bands both force
    extra water consumption.
    """
    return (temperature or "").lower() in {"heat", "extreme_heat"}


# --------------------------------------------------------------------------- #
# Result of advancing a single day.
# --------------------------------------------------------------------------- #

@dataclass
class SurvivalResult:
    """Outcome of resolving one day of food/water intake."""

    #: The updated survival state (post-day).
    state: SurvivalState
    #: Whether the day's food met the full daily need.
    food_intake_ok: bool
    #: Whether the day's water met the full daily need.
    water_intake_ok: bool
    #: Whether at least half the daily water was consumed.
    water_half_or_more: bool
    #: Water needed that day (2 gal in hot weather, else 1).
    water_needed: float
    #: Exhaustion levels inflicted by starvation this day (0 or 1).
    exhaustion_from_food: int = 0
    #: Exhaustion levels inflicted by dehydration this day (0 or 1).
    exhaustion_from_water: int = 0
    #: Total exhaustion added this day (food + water, typically 0–2).
    exhaustion_added: int = 0
    #: The projected exhaustion total after applying ``exhaustion_added``
    #: to ``current_exhaustion`` (clamped to 0–6).
    new_exhaustion: int = 0
    #: The DC of the dehydration save, if one was called for this day.
    thirst_save_dc: Optional[int] = None
    #: The raw d20 roll of the dehydration save, if rolled.
    thirst_save_roll: Optional[int] = None
    #: The bonus added to the dehydration save (CON mod, + proficiency if any).
    thirst_save_bonus: int = 0
    #: Whether the dehydration save succeeded (only set when a save happened).
    thirst_save_success: Optional[bool] = None
    #: Whether exhaustion reached the fatal level (6) this day.
    died: bool = False
    #: Human-readable narration lines for the story log.
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.to_dict(),
            "food_intake_ok": self.food_intake_ok,
            "water_intake_ok": self.water_intake_ok,
            "water_half_or_more": self.water_half_or_more,
            "water_needed": self.water_needed,
            "exhaustion_from_food": self.exhaustion_from_food,
            "exhaustion_from_water": self.exhaustion_from_water,
            "exhaustion_added": self.exhaustion_added,
            "new_exhaustion": self.new_exhaustion,
            "thirst_save_dc": self.thirst_save_dc,
            "thirst_save_roll": self.thirst_save_roll,
            "thirst_save_bonus": self.thirst_save_bonus,
            "thirst_save_success": self.thirst_save_success,
            "died": self.died,
            "messages": list(self.messages),
        }


# --------------------------------------------------------------------------- #
# Core: resolve one day of food/water intake.
# --------------------------------------------------------------------------- #

def advance_day(
    state: SurvivalState,
    *,
    food_lbs: float = DAILY_FOOD_LBS,
    water_gal: float = DAILY_WATER_GAL,
    hot: bool = False,
    con_modifier: int = 0,
    save_bonus: Optional[int] = None,
    save_roll: Optional[int] = None,
    current_exhaustion: int = 0,
    roller: Callable[[int], int] = lambda m: roll_d20(modifier=m).total,
) -> SurvivalResult:
    """Resolve a day's food/water intake against the survival rules.

    Args:
        state: The character's survival state (counters) at the start of the day.
        food_lbs: Pounds of food consumed that day.
        water_gal: Gallons of water consumed that day.
        hot: Whether the weather is hot (doubles the water need).
        con_modifier: The character's Constitution modifier.
        save_bonus: Bonus on the dehydration save. Defaults to ``con_modifier``;
            callers that know the character's Constitution *save* proficiency
            can pass ``con_modifier + proficiency_bonus`` for a faithful save.
        save_roll: An explicit d20 result for the dehydration save (testing /
            DM-adjudicated). When ``None`` and a save is required, the engine
            rolls via ``roller``.
        current_exhaustion: The character's exhaustion level at the start of
            the day (so the result can report the projected total and death).
        roller: Injected d20 roller taking the save bonus and returning a total.

    Returns:
        A :class:`SurvivalResult` describing the day's outcome, including the
        updated :class:`SurvivalState` and any exhaustion inflicted.
    """
    # Work on a copy so the caller's state is not mutated in place.
    new_state = SurvivalState(
        days_without_food=state.days_without_food,
        days_without_water=state.days_without_water,
    )

    water_needed = HOT_WATER_GAL if hot else DAILY_WATER_GAL
    food_ok = food_lbs >= DAILY_FOOD_LBS
    water_ok = water_gal >= water_needed
    water_half = water_gal >= (water_needed / 2.0)

    # ---- Update the consecutive-day counters. --------------------------------
    if food_ok:
        new_state.days_without_food = 0
    else:
        new_state.days_without_food = new_state.days_without_food + 1

    if water_ok:
        new_state.days_without_water = 0
    else:
        new_state.days_without_water = new_state.days_without_water + 1

    messages: list[str] = []

    # ---- Starvation (food): grace period, then automatic exhaustion. -------- #
    exhaustion_from_food = 0
    grace = food_grace_days(con_modifier)
    if new_state.days_without_food > grace:
        exhaustion_from_food = 1
        messages.append(
            f"{new_state.days_without_food} days without food (grace {grace}) — "
            f"starvation inflicts a level of exhaustion."
        )
    elif not food_ok and new_state.days_without_food == grace:
        messages.append(
            f"{new_state.days_without_food} days without food — at the limit of "
            f"what {grace} grace day(s) allow; one more day without food will "
            f"begin to Exhaust."
        )

    # ---- Dehydration (water): half → DC 15 save; less than half → auto. ----- #
    exhaustion_from_water = 0
    thirst_save_dc: Optional[int] = None
    thirst_save_roll: Optional[int] = None
    thirst_save_success: Optional[bool] = None
    bonus = con_modifier if save_bonus is None else int(save_bonus)

    if not water_ok:
        if water_half:
            # Half or more (but less than full): DC 15 CON save or a level.
            thirst_save_dc = THIRST_SAVE_DC
            if save_roll is None:
                total = roller(bonus)
                # The roller returns the total (d20 + bonus); recover the die.
                thirst_save_roll = total - bonus
            else:
                thirst_save_roll = int(save_roll)
            thirst_save_success = (thirst_save_roll + bonus) >= THIRST_SAVE_DC
            if not thirst_save_success:
                exhaustion_from_water = 1
                messages.append(
                    f"Dehydrated on half rations — CON save {thirst_save_roll}+"
                    f"{bonus} vs DC {THIRST_SAVE_DC} failed: a level of exhaustion."
                )
            else:
                messages.append(
                    f"Dehydrated on half rations — CON save {thirst_save_roll}+"
                    f"{bonus} vs DC {THIRST_SAVE_DC} succeeded: no exhaustion."
                )
        else:
            # Less than half: automatic exhaustion.
            exhaustion_from_water = 1
            messages.append(
                "Less than half the needed water — dehydration inflicts a level "
                "of exhaustion automatically."
            )

    exhaustion_added = exhaustion_from_food + exhaustion_from_water
    if exhaustion_added == 0 and food_ok and water_ok:
        messages.append("Ate and drank well — no survival pressure.")

    # ---- Project the exhaustion total (the API applies it). ----------------- #
    from app.engine import exhaustion as _exh  # local import avoids a cycle

    new_exhaustion = max(
        0, min(_exh.MAX_EXHAUSTION, int(current_exhaustion) + exhaustion_added)
    )
    died = new_exhaustion >= _exh.MAX_EXHAUSTION
    if died:
        messages.append("Exhaustion reaches level 6 — death from deprivation.")

    return SurvivalResult(
        state=new_state,
        food_intake_ok=food_ok,
        water_intake_ok=water_ok,
        water_half_or_more=water_half,
        water_needed=water_needed,
        exhaustion_from_food=exhaustion_from_food,
        exhaustion_from_water=exhaustion_from_water,
        exhaustion_added=exhaustion_added,
        new_exhaustion=new_exhaustion,
        thirst_save_dc=thirst_save_dc,
        thirst_save_roll=thirst_save_roll,
        thirst_save_bonus=bonus,
        thirst_save_success=thirst_save_success,
        died=died,
        messages=messages,
    )


# --------------------------------------------------------------------------- #
# UI / DM summary helpers.
# --------------------------------------------------------------------------- #

def deficit_summary(
    state: SurvivalState,
    con_modifier: int,
    hot: bool = False,
) -> dict[str, Any]:
    """A readable snapshot of how close a character is to suffering.

    Useful for the survival panel and the DM context block.
    """
    grace = food_grace_days(con_modifier)
    food_days_left = max(0, grace - state.days_without_food)
    water_need = HOT_WATER_GAL if hot else DAILY_WATER_GAL
    return {
        "days_without_food": state.days_without_food,
        "days_without_water": state.days_without_water,
        "food_grace_days": grace,
        "food_days_until_exhaustion": food_days_left,
        "starving": state.days_without_food > grace,
        "dehydrated": state.days_without_water > 0,
        "daily_food_lbs": DAILY_FOOD_LBS,
        "daily_water_gal": water_need,
        "hot": hot,
    }
