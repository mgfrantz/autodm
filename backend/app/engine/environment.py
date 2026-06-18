"""
Environment engine — DnD 5e environmental conditions (weather, lighting,
terrain, temperature, time of day) and the mechanical effects they impose.

DnD 5e treats the environment as a first-class rules layer (PHB ch.5 "The
Environment"; DMG ch.5 "Environment"). This module models the parts that have
*mechanical* consequences rather than just flavour:

LIGHTING & OBSCUREMENT
- ``bright`` light: an area is visible and unobscured.
- ``dim`` light (twilight, dawn/dusk): the area is *lightly obscured*.
  Creatures have disadvantage on Wisdom (Perception) checks that rely on sight.
- ``darkness``: the area is *heavily obscured*. A creature without darkvision
  (or another special sense) is effectively **blinded** — it automatically
  fails any check that requires sight, and attacks suffer the usual effects of
  being unable to see the target (advantage/disadvantage per the blinded
  condition).

WEATHER
- light precipitation (rain/snow): lightly obscured.
- heavy precipitation / fog / heavy snow / storm / blizzard: heavily obscured.
- strong wind: imposes **disadvantage on ranged weapon attack rolls**, makes
  Wisdom (Perception) checks relying on hearing harder, and extinguishes open
  flames. (Storms and blizzards combine wind + heavy obscurement.)

TERRAIN
- difficult terrain (rubble, undergrowth, ice, deep snow, bogs, climbing,
  swimming): every foot of movement costs one *extra* foot — i.e. effective
  speed is halved.
- ice is difficult *and* slippery (Dexterity checks to keep footing).

TEMPERATURE
- extreme cold / extreme heat require a Constitution saving throw (DC 10)
  roughly each hour of exposure or the creature suffers a level of exhaustion.

The module is **pure**: it operates on dataclasses and an optional
``random.Random`` instance for procedural weather. No database, no LLM. The API
layer persists an ``Environment`` snapshot inside ``game_state`` and asks the
engine for the derived ``EnvironmentEffects`` used by the rest of the game.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence


# --------------------------------------------------------------------------- #
# Controlled vocabularies.
# --------------------------------------------------------------------------- #

LIGHT_LEVELS: tuple[str, ...] = ("bright", "dim", "darkness")
OBSCUREMENT_LEVELS: tuple[str, ...] = ("clear", "lightly_obscured", "heavily_obscured")
WEATHER_TYPES: tuple[str, ...] = (
    "clear",
    "light_rain",
    "heavy_rain",
    "light_snow",
    "heavy_snow",
    "blizzard",
    "fog",
    "strong_wind",
    "storm",
)
TERRAIN_TYPES: tuple[str, ...] = (
    "normal",
    "difficult",
    "heavy_difficult",
    "ice",
    "rubble",
    "undergrowth",
    "water",
    "cliff",
)
TEMPERATURE_LEVELS: tuple[str, ...] = (
    "normal",
    "cold",
    "extreme_cold",
    "heat",
    "extreme_heat",
)
TIME_OF_DAY: tuple[str, ...] = ("dawn", "day", "dusk", "night")
CLIMATES: tuple[str, ...] = ("temperate", "cold", "desert", "arctic")
SEASONS: tuple[str, ...] = ("spring", "summer", "autumn", "winter")

#: Ordering used to pick the "worse" obscurement when several sources combine.
_OBSCUREMENT_RANK: dict[str, int] = {
    "clear": 0,
    "lightly_obscured": 1,
    "heavily_obscured": 2,
}


# A random source may be a seeded ``random.Random`` or the ``random`` module.
Rng = Any


# --------------------------------------------------------------------------- #
# Rule registries.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LightRules:
    """Mechanical effects of a light level."""

    name: str
    description: str
    obscurement: str  # base obscurement contributed by the light level

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "obscurement": self.obscurement,
        }


LIGHT_RULES: dict[str, LightRules] = {
    "bright": LightRules(
        name="bright",
        description=(
            "Bright light lets most creatures see normally. The area is "
            "unobscured."
        ),
        obscurement="clear",
    ),
    "dim": LightRules(
        name="dim",
        description=(
            "Dim light, also called shadows, creates a lightly obscured area. "
            "Creatures have disadvantage on Wisdom (Perception) checks that "
            "rely on sight."
        ),
        obscurement="lightly_obscured",
    ),
    "darkness": LightRules(
        name="darkness",
        description=(
            "Darkness creates a heavily obscured area. Creatures without "
            "darkvision (or a similar special sense) are effectively blinded."
        ),
        obscurement="heavily_obscured",
    ),
}


@dataclass(frozen=True)
class WeatherRules:
    """Mechanical effects of a weather condition.

    ``obscurement`` is ``None`` when the weather does not change visibility
    on its own (e.g. wind), so it does not override the lighting contribution.
    """

    name: str
    description: str
    obscurement: Optional[str] = None
    ranged_attack_disadvantage: bool = False
    flames_extinguished: bool = False
    listen_disadvantage: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "obscurement": self.obscurement,
            "ranged_attack_disadvantage": self.ranged_attack_disadvantage,
            "flames_extinguished": self.flames_extinguished,
            "listen_disadvantage": self.listen_disadvantage,
        }


WEATHER_RULES: dict[str, WeatherRules] = {
    "clear": WeatherRules(
        name="clear",
        description="Clear skies. No weather effects.",
    ),
    "light_rain": WeatherRules(
        name="light_rain",
        description=(
            "Light rain or drizzle. The area is lightly obscured beyond 1d6 × "
            "10 feet."
        ),
        obscurement="lightly_obscured",
    ),
    "heavy_rain": WeatherRules(
        name="heavy_rain",
        description=(
            "Heavy downpour. The area is heavily obscured beyond 1d6 × 10 feet "
            "and open flames are extinguished."
        ),
        obscurement="heavily_obscured",
        flames_extinguished=True,
    ),
    "light_snow": WeatherRules(
        name="light_snow",
        description=(
            "Falling snow. The area is lightly obscured beyond 1d6 × 10 feet."
        ),
        obscurement="lightly_obscured",
    ),
    "heavy_snow": WeatherRules(
        name="heavy_snow",
        description=(
            "Heavy snowfall. The area is heavily obscured beyond 1d6 × 10 "
            "feet and open flames may be extinguished."
        ),
        obscurement="heavily_obscured",
        flames_extinguished=True,
    ),
    "blizzard": WeatherRules(
        name="blizzard",
        description=(
            "Driving snow and howling wind. Heavily obscured, ranged weapon "
            "attacks have disadvantage, hearing is muffled, and open flames "
            "are extinguished."
        ),
        obscurement="heavily_obscured",
        ranged_attack_disadvantage=True,
        flames_extinguished=True,
        listen_disadvantage=True,
    ),
    "fog": WeatherRules(
        name="fog",
        description=(
            "Thick fog. The area is heavily obscured beyond 1d6 × 10 feet; "
            "only the closest few feet are visible."
        ),
        obscurement="heavily_obscured",
    ),
    "strong_wind": WeatherRules(
        name="strong_wind",
        description=(
            "Strong wind imposes disadvantage on ranged weapon attack rolls, "
            "disperse fog and similar clouds, muffle hearing, and extinguish "
            "open flames."
        ),
        ranged_attack_disadvantage=True,
        flames_extinguished=True,
        listen_disadvantage=True,
    ),
    "storm": WeatherRules(
        name="storm",
        description=(
            "A thunderstorm: heavy rain, strong wind, and lightning. "
            "Heavily obscured, ranged attacks have disadvantage, hearing is "
            "difficult, and open flames are extinguished."
        ),
        obscurement="heavily_obscured",
        ranged_attack_disadvantage=True,
        flames_extinguished=True,
        listen_disadvantage=True,
    ),
}


@dataclass(frozen=True)
class TerrainRules:
    """Movement effects of a terrain type."""

    name: str
    description: str
    #: Feet of movement each foot of travel costs (1.0 normal, 2.0 difficult).
    movement_cost: float = 1.0
    slippery: bool = False
    swim_required: bool = False
    climb_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "movement_cost": self.movement_cost,
            "slippery": self.slippery,
            "swim_required": self.swim_required,
            "climb_required": self.climb_required,
        }


TERRAIN_RULES: dict[str, TerrainRules] = {
    "normal": TerrainRules(
        name="normal",
        description="Open, firm ground. Normal movement.",
        movement_cost=1.0,
    ),
    "difficult": TerrainRules(
        name="difficult",
        description=(
            "Difficult terrain: rubble, thick mud, deep snow, and the like. "
            "Each foot of movement costs one extra foot."
        ),
        movement_cost=2.0,
    ),
    "heavy_difficult": TerrainRules(
        name="heavy_difficult",
        description=(
            "Severely difficult terrain (dense thorns, waist-deep snow). "
            "Each foot of movement costs one extra foot, and even careful "
            "movement is exhausting."
        ),
        movement_cost=2.0,
    ),
    "ice": TerrainRules(
        name="ice",
        description=(
            "Slippery ice. Treated as difficult terrain, and Dexterity checks "
            "to keep footing are made with disadvantage."
        ),
        movement_cost=2.0,
        slippery=True,
    ),
    "rubble": TerrainRules(
        name="rubble",
        description=(
            "Loose rubble and debris. Difficult terrain."
        ),
        movement_cost=2.0,
    ),
    "undergrowth": TerrainRules(
        name="undergrowth",
        description=(
            "Dense undergrowth and foliage. Difficult terrain."
        ),
        movement_cost=2.0,
    ),
    "water": TerrainRules(
        name="water",
        description=(
            "Swimming water. Each foot of movement costs one extra foot, and "
            "the creature must swim."
        ),
        movement_cost=2.0,
        swim_required=True,
    ),
    "cliff": TerrainRules(
        name="cliff",
        description=(
            "A sheer surface requiring a climb. Each foot of movement costs "
            "one extra foot."
        ),
        movement_cost=2.0,
        climb_required=True,
    ),
}


@dataclass(frozen=True)
class TemperatureRules:
    """Temperature exposure effects."""

    name: str
    description: str
    #: None when no exhaustion save is required.
    exhaustion_save: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "exhaustion_save": self.exhaustion_save,
        }


TEMPERATURE_RULES: dict[str, TemperatureRules] = {
    "normal": TemperatureRules(
        name="normal",
        description="Comfortable temperatures. No exposure effects.",
    ),
    "cold": TemperatureRules(
        name="cold",
        description=(
            "Chilly but survivable without special gear. No mechanical effect."
        ),
    ),
    "extreme_cold": TemperatureRules(
        name="extreme_cold",
        description=(
            "Below 0 °F. A creature must make a Constitution saving throw "
            "each hour of exposure or gain one level of exhaustion. "
            "Appropriate clothing or fire grants automatic success."
        ),
        exhaustion_save={
            "ability": "constitution",
            "dc": 10,
            "frequency": "hour",
            "reason": "extreme_cold",
        },
    ),
    "heat": TemperatureRules(
        name="heat",
        description=(
            "Hot but survivable. Travelers in heavy clothing or armor may "
            "find it uncomfortable."
        ),
    ),
    "extreme_heat": TemperatureRules(
        name="extreme_heat",
        description=(
            "Above 100 °F. A creature must make a Constitution saving throw "
            "each hour of travel (or vigorous activity) or gain one level of "
            "exhaustion. Creatures in heavy armor have disadvantage on the "
            "save, and everyone consumes extra water."
        ),
        exhaustion_save={
            "ability": "constitution",
            "dc": 10,
            "frequency": "hour",
            "reason": "extreme_heat",
        },
    ),
}


# --------------------------------------------------------------------------- #
# Ambient-light derivation from time of day.
# --------------------------------------------------------------------------- #

#: Time of day -> ambient light level (absent magical/structural lighting).
TIME_OF_DAY_LIGHT: dict[str, str] = {
    "dawn": "dim",
    "day": "bright",
    "dusk": "dim",
    "night": "darkness",
}


def light_for_time_of_day(time_of_day: str) -> str:
    """Return the ambient light level for a time of day.

    Unknown values default to ``bright``.
    """
    return TIME_OF_DAY_LIGHT.get(time_of_day, "bright")


# --------------------------------------------------------------------------- #
# Environment snapshot.
# --------------------------------------------------------------------------- #


@dataclass
class Environment:
    """A complete snapshot of a scene's environmental conditions."""

    light: str = "bright"
    weather: str = "clear"
    terrain: str = "normal"
    temperature: str = "normal"
    time_of_day: str = "day"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "light": self.light,
            "weather": self.weather,
            "terrain": self.terrain,
            "temperature": self.temperature,
            "time_of_day": self.time_of_day,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "Environment":
        data = data or {}
        return cls(
            light=data.get("light", "bright"),
            weather=data.get("weather", "clear"),
            terrain=data.get("terrain", "normal"),
            temperature=data.get("temperature", "normal"),
            time_of_day=data.get("time_of_day", "day"),
            notes=data.get("notes", "") or "",
        )


def default_environment() -> Environment:
    """A sane default environment: clear midday, normal ground."""
    return Environment()


# --------------------------------------------------------------------------- #
# Derived mechanical effects.
# --------------------------------------------------------------------------- #


def _worse_obscurement(a: str, b: str) -> str:
    """Return whichever obscurement is more severe."""
    return a if _OBSCUREMENT_RANK.get(a, 0) >= _OBSCUREMENT_RANK.get(b, 0) else b


def derive_obscurement(env: Environment) -> str:
    """Combine lighting and weather into a single obscurement level.

    Weather never *improves* visibility, so we always take the worse of the
    lighting contribution and the weather contribution.
    """
    light_rule = LIGHT_RULES.get(env.light, LIGHT_RULES["bright"])
    obscurement = light_rule.obscurement

    weather_rule = WEATHER_RULES.get(env.weather)
    if weather_rule is not None and weather_rule.obscurement is not None:
        obscurement = _worse_obscurement(obscurement, weather_rule.obscurement)

    return obscurement


@dataclass
class EnvironmentEffects:
    """All mechanical effects derived from an ``Environment``."""

    obscurement: str = "clear"
    lightly_obscured: bool = False
    heavily_obscured: bool = False
    perception_disadvantage: bool = False
    effective_blinded: bool = False
    ranged_attack_disadvantage: bool = False
    flames_extinguished: bool = False
    listen_disadvantage: bool = False
    movement_cost_multiplier: float = 1.0
    difficult_terrain: bool = False
    slippery: bool = False
    swim_required: bool = False
    climb_required: bool = False
    exhaustion_save: Optional[dict[str, Any]] = None
    active_effects: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "obscurement": self.obscurement,
            "lightly_obscured": self.lightly_obscured,
            "heavily_obscured": self.heavily_obscured,
            "perception_disadvantage": self.perception_disadvantage,
            "effective_blinded": self.effective_blinded,
            "ranged_attack_disadvantage": self.ranged_attack_disadvantage,
            "flames_extinguished": self.flames_extinguished,
            "listen_disadvantage": self.listen_disadvantage,
            "movement_cost_multiplier": self.movement_cost_multiplier,
            "difficult_terrain": self.difficult_terrain,
            "slippery": self.slippery,
            "swim_required": self.swim_required,
            "climb_required": self.climb_required,
            "exhaustion_save": self.exhaustion_save,
            "active_effects": list(self.active_effects),
            "summary": self.summary,
        }


def compute_effects(env: Environment) -> EnvironmentEffects:
    """Derive every mechanical effect an environment imposes."""
    obscurement = derive_obscurement(env)
    weather_rule = WEATHER_RULES.get(env.weather)
    terrain_rule = TERRAIN_RULES.get(env.terrain, TERRAIN_RULES["normal"])
    temp_rule = TEMPERATURE_RULES.get(env.temperature, TEMPERATURE_RULES["normal"])

    heavily = obscurement == "heavily_obscured"
    lightly = obscurement == "lightly_obscured"

    effects = EnvironmentEffects(
        obscurement=obscurement,
        lightly_obscured=lightly,
        heavily_obscured=heavily,
        # Lightly obscured: disadvantage on sight-based Perception.
        # Heavily obscured: the creature is effectively blinded, which in 5e
        # means it auto-fails sight checks (handled via the blinded flag).
        perception_disadvantage=lightly,
        effective_blinded=heavily,
        ranged_attack_disadvantage=bool(weather_rule and weather_rule.ranged_attack_disadvantage),
        flames_extinguished=bool(weather_rule and weather_rule.flames_extinguished),
        listen_disadvantage=bool(weather_rule and weather_rule.listen_disadvantage),
        movement_cost_multiplier=terrain_rule.movement_cost,
        difficult_terrain=terrain_rule.movement_cost > 1.0,
        slippery=terrain_rule.slippery,
        swim_required=terrain_rule.swim_required,
        climb_required=terrain_rule.climb_required,
        exhaustion_save=temp_rule.exhaustion_save,
        active_effects=[],
        summary="",
    )

    # Build a human-readable list of the active mechanical effects.
    parts: list[str] = []
    if effects.perception_disadvantage:
        parts.append("disadvantage on sight-based Perception checks")
    if effects.effective_blinded:
        parts.append("creatures without special senses are effectively blinded")
    if effects.ranged_attack_disadvantage:
        parts.append("disadvantage on ranged weapon attacks")
    if effects.listen_disadvantage:
        parts.append("disadvantage on hearing-based Perception checks")
    if effects.flames_extinguished:
        parts.append("open flames are extinguished")
    if effects.difficult_terrain:
        parts.append(f"difficult terrain (movement costs x{effects.movement_cost_multiplier:.0g})")
    if effects.slippery:
        parts.append("slippery footing")
    if effects.swim_required:
        parts.append("swimming required")
    if effects.climb_required:
        parts.append("climbing required")
    if effects.exhaustion_save is not None:
        sv = effects.exhaustion_save
        parts.append(
            f"{sv['reason']}: Constitution save DC {sv['dc']} per {sv['frequency']} or exhaustion"
        )
    effects.active_effects = parts
    if parts:
        effects.summary = "; ".join(parts)
    else:
        effects.summary = "No environmental penalties."
    return effects


# --------------------------------------------------------------------------- #
# Targeted effect queries — convenience helpers for the rest of the engine.
# --------------------------------------------------------------------------- #

def sight_perception_disadvantage(env: Environment) -> bool:
    """True if sight-based Perception checks suffer disadvantage here."""
    return derive_obscurement(env) == "lightly_obscured"


def is_effectively_blinded(env: Environment) -> bool:
    """True if creatures without special senses are effectively blinded."""
    return derive_obscurement(env) == "heavily_obscured"


def ranged_attack_disadvantage(env: Environment) -> bool:
    """True if ranged weapon attacks suffer disadvantage here."""
    rule = WEATHER_RULES.get(env.weather)
    return bool(rule and rule.ranged_attack_disadvantage)


def effective_speed(env: Environment, base_speed: int) -> int:
    """A creature's effective speed after terrain is applied.

    Difficult terrain costs one extra foot per foot moved, so a base speed is
    divided by the movement-cost multiplier and floored. A speed of 0 stays 0.
    """
    if base_speed <= 0:
        return 0
    terrain_rule = TERRAIN_RULES.get(env.terrain, TERRAIN_RULES["normal"])
    if terrain_rule.movement_cost <= 1.0:
        return base_speed
    return max(1, int(base_speed // terrain_rule.movement_cost))


def exhaustion_save(env: Environment) -> Optional[dict[str, Any]]:
    """The exhaustion save (if any) imposed by the temperature."""
    rule = TEMPERATURE_RULES.get(env.temperature, TEMPERATURE_RULES["normal"])
    return rule.exhaustion_save


# --------------------------------------------------------------------------- #
# Combat modifier bundle — a thin view for the combat API to consume.
# --------------------------------------------------------------------------- #


@dataclass
class CombatModifiers:
    """How the environment reshapes a creature's combat rolls.

    These are *situational* modifiers: the combat engine applies them as
    advantage/disadvantage signals rather than flat bonuses. ``attack_roll``
    refers to the creature's own attack roll; ``defense`` refers to attacks
    made *against* the creature.
    """

    attacker_ranged_disadvantage: bool = False
    attacker_melee_disadvantage: bool = False
    attacker_cannot_see_target: bool = False  # attacker blinded by environment
    target_unseen_by_attacker: bool = False  # target hidden by environment

    def to_dict(self) -> dict[str, Any]:
        return {
            "attacker_ranged_disadvantage": self.attacker_ranged_disadvantage,
            "attacker_melee_disadvantage": self.attacker_melee_disadvantage,
            "attacker_cannot_see_target": self.attacker_cannot_see_target,
            "target_unseen_by_attacker": self.target_unseen_by_attacker,
        }


def combat_modifiers(env: Environment, *, attack_is_ranged: bool = False) -> CombatModifiers:
    """Compute the environment's effect on a single attack.

    Per the PHB's rules for *unseen attackers*: when a creature can't see its
    target (because the target is heavily obscured) the attacker has
    disadvantage, and when the attacker itself is effectively blinded it also
    has disadvantage on the attack roll.
    """
    heavily = is_effectively_blinded(env)
    mods = CombatModifiers(
        attacker_ranged_disadvantage=ranged_attack_disadvantage(env) and attack_is_ranged,
        attacker_melee_disadvantage=heavily,
        attacker_cannot_see_target=heavily,
        target_unseen_by_attacker=heavily,
    )
    return mods


# --------------------------------------------------------------------------- #
# Procedural weather / temperature by climate and season.
# --------------------------------------------------------------------------- #

#: Weighted weather tables: climate -> season -> [(weather, weight), ...].
WEATHER_TABLES: dict[str, dict[str, list[tuple[str, int]]]] = {
    "temperate": {
        "spring": [
            ("clear", 50), ("light_rain", 25), ("fog", 10),
            ("heavy_rain", 10), ("storm", 5),
        ],
        "summer": [
            ("clear", 60), ("light_rain", 15), ("heavy_rain", 10),
            ("storm", 10), ("fog", 5),
        ],
        "autumn": [
            ("clear", 40), ("light_rain", 25), ("fog", 15),
            ("heavy_rain", 10), ("storm", 10),
        ],
        "winter": [
            ("clear", 35), ("light_snow", 30), ("heavy_snow", 15),
            ("fog", 15), ("blizzard", 5),
        ],
    },
    "cold": {
        "spring": [
            ("clear", 30), ("light_snow", 25), ("light_rain", 20),
            ("heavy_snow", 15), ("fog", 10),
        ],
        "summer": [
            ("clear", 50), ("light_rain", 25), ("fog", 15), ("heavy_rain", 10),
        ],
        "autumn": [
            ("clear", 25), ("light_snow", 25), ("heavy_snow", 20),
            ("fog", 15), ("light_rain", 15),
        ],
        "winter": [
            ("clear", 20), ("light_snow", 30), ("heavy_snow", 30),
            ("blizzard", 20),
        ],
    },
    "desert": {
        "spring": [("clear", 75), ("fog", 10), ("light_rain", 10), ("storm", 5)],
        "summer": [("clear", 85), ("storm", 10), ("fog", 5)],
        "autumn": [("clear", 80), ("light_rain", 10), ("fog", 5), ("storm", 5)],
        "winter": [("clear", 80), ("light_rain", 10), ("fog", 5), ("storm", 5)],
    },
    "arctic": {
        "spring": [
            ("clear", 20), ("light_snow", 35), ("heavy_snow", 25),
            ("blizzard", 15), ("fog", 5),
        ],
        "summer": [
            ("clear", 40), ("light_snow", 30), ("heavy_snow", 15),
            ("fog", 10), ("blizzard", 5),
        ],
        "autumn": [
            ("clear", 20), ("light_snow", 30), ("heavy_snow", 30),
            ("blizzard", 20),
        ],
        "winter": [
            ("clear", 10), ("light_snow", 25), ("heavy_snow", 30),
            ("blizzard", 35),
        ],
    },
}

#: Default temperatures by climate and season.
TEMPERATURE_TABLES: dict[str, dict[str, str]] = {
    "temperate": {
        "spring": "normal", "summer": "heat", "autumn": "normal", "winter": "cold",
    },
    "cold": {
        "spring": "cold", "summer": "normal", "autumn": "cold", "winter": "extreme_cold",
    },
    "desert": {
        "spring": "heat", "summer": "extreme_heat", "autumn": "heat", "winter": "normal",
    },
    "arctic": {
        "spring": "extreme_cold", "summer": "cold",
        "autumn": "extreme_cold", "winter": "extreme_cold",
    },
}


def _weighted_choice(options: Sequence[tuple[str, int]], rng: Rng = None) -> str:
    """Pick a key from a weighted ``(value, weight)`` list."""
    r = rng or random
    total = sum(w for _, w in options)
    if total <= 0:
        return options[0][0] if options else "clear"
    roll = r.randint(1, total)
    upto = 0
    for value, weight in options:
        upto += weight
        if roll <= upto:
            return value
    return options[-1][0]


def random_weather(climate: str = "temperate", season: str = "summer", rng: Rng = None) -> str:
    """Roll a weather type for the given climate and season."""
    climate_table = WEATHER_TABLES.get(climate, WEATHER_TABLES["temperate"])
    season_table = climate_table.get(season, climate_table["summer"])
    return _weighted_choice(season_table, rng)


def random_temperature(climate: str = "temperate", season: str = "summer", rng: Rng = None) -> str:
    """Roll a temperature for the given climate and season.

    Most of the time the temperature matches the table; a small chance rolls
    one step more extreme (e.g. a desert summer heat wave, an arctic blizzard
    snap) to keep travel interesting.
    """
    climate_table = TEMPERATURE_TABLES.get(climate, TEMPERATURE_TABLES["temperate"])
    base = climate_table.get(season, "normal")
    r = rng or random
    # 15% chance of a one-step swing toward the extreme.
    if r.randint(1, 100) <= 15:
        extremes = {"cold": "extreme_cold", "heat": "extreme_heat"}
        return extremes.get(base, base)
    return base


def roll_environment(
    climate: str = "temperate",
    season: str = "summer",
    time_of_day: str = "day",
    rng: Rng = None,
) -> Environment:
    """Roll a full procedural environment (weather + temperature + light)."""
    weather = random_weather(climate, season, rng)
    temperature = random_temperature(climate, season, rng)
    light = light_for_time_of_day(time_of_day)
    return Environment(
        light=light,
        weather=weather,
        terrain="normal",
        temperature=temperature,
        time_of_day=time_of_day,
    )


# --------------------------------------------------------------------------- #
# Registry accessors (for the UI / discovery endpoints).
# --------------------------------------------------------------------------- #

def list_light_levels() -> list[dict[str, Any]]:
    return [rule.to_dict() for rule in LIGHT_RULES.values()]


def list_weather() -> list[dict[str, Any]]:
    return [rule.to_dict() for rule in WEATHER_RULES.values()]


def list_terrain() -> list[dict[str, Any]]:
    return [rule.to_dict() for rule in TERRAIN_RULES.values()]


def list_temperatures() -> list[dict[str, Any]]:
    return [rule.to_dict() for rule in TEMPERATURE_RULES.values()]


def list_times_of_day() -> list[dict[str, str]]:
    return [
        {"name": t, "light": TIME_OF_DAY_LIGHT.get(t, "bright")}
        for t in TIME_OF_DAY
    ]


def get_light_info(name: str) -> Optional[dict[str, Any]]:
    rule = LIGHT_RULES.get(name)
    return rule.to_dict() if rule else None


def get_weather_info(name: str) -> Optional[dict[str, Any]]:
    rule = WEATHER_RULES.get(name)
    return rule.to_dict() if rule else None


def get_terrain_info(name: str) -> Optional[dict[str, Any]]:
    rule = TERRAIN_RULES.get(name)
    return rule.to_dict() if rule else None


def get_temperature_info(name: str) -> Optional[dict[str, Any]]:
    rule = TEMPERATURE_RULES.get(name)
    return rule.to_dict() if rule else None
