"""
Tests for the environment engine — weather, lighting, terrain, temperature.

Covers registry access, obscurement derivation, the full derived-effects matrix,
effective speed, combat situational modifiers, exhaustion saves, deterministic
procedural weather/temperature rolls, and serialization round-trips.
"""
import random

import pytest

from app.engine import environment as env
from app.engine.environment import (
    Environment,
    EnvironmentEffects,
    Environment as E,
    LIGHT_LEVELS,
    OBSCUREMENT_LEVELS,
    WEATHER_TYPES,
    TERRAIN_TYPES,
    TEMPERATURE_LEVELS,
    TIME_OF_DAY,
    CLIMATES,
    SEASONS,
    derive_obscurement,
    compute_effects,
    effective_speed,
    combat_modifiers,
    exhaustion_save,
    is_effectively_blinded,
    sight_perception_disadvantage,
    ranged_attack_disadvantage,
    random_weather,
    random_temperature,
    roll_environment,
    light_for_time_of_day,
    default_environment,
)


# --------------------------------------------------------------------------- #
# Registries / vocabularies.
# --------------------------------------------------------------------------- #

class TestRegistries:
    def test_vocabularies_are_complete(self):
        assert LIGHT_LEVELS == ("bright", "dim", "darkness")
        assert "fog" in WEATHER_TYPES
        assert "storm" in WEATHER_TYPES
        assert "blizzard" in WEATHER_TYPES
        assert "strong_wind" in WEATHER_TYPES
        assert "difficult" in TERRAIN_TYPES
        assert "ice" in TERRAIN_TYPES
        assert "water" in TERRAIN_TYPES
        assert "extreme_cold" in TEMPERATURE_LEVELS
        assert "extreme_heat" in TEMPERATURE_LEVELS
        assert "night" in TIME_OF_DAY
        assert "arctic" in CLIMATES
        assert "winter" in SEASONS

    def test_every_weather_has_rules(self):
        for w in WEATHER_TYPES:
            assert env.get_weather_info(w) is not None, f"missing weather rule: {w}"

    def test_every_terrain_has_rules(self):
        for t in TERRAIN_TYPES:
            assert env.get_terrain_info(t) is not None, f"missing terrain rule: {t}"

    def test_every_light_has_rules(self):
        for l in LIGHT_LEVELS:
            assert env.get_light_info(l) is not None

    def test_every_temperature_has_rules(self):
        for t in TEMPERATURE_LEVELS:
            assert env.get_temperature_info(t) is not None

    def test_list_helpers_return_dicts(self):
        for fn in (env.list_light_levels, env.list_weather, env.list_terrain,
                   env.list_temperatures):
            items = fn()
            assert isinstance(items, list) and items
            assert all(isinstance(i, dict) for i in items)
        times = env.list_times_of_day()
        assert any(t["name"] == "night" and t["light"] == "darkness" for t in times)

    def test_unknown_lookups_return_none(self):
        assert env.get_weather_info("tornado") is None
        assert env.get_terrain_info("lava") is None
        assert env.get_light_info("twilight") is None
        assert env.get_temperature_info("boiling") is None


# --------------------------------------------------------------------------- #
# Time-of-day ambient light.
# --------------------------------------------------------------------------- #

class TestTimeOfDay:
    @pytest.mark.parametrize("tod,expected", [
        ("dawn", "dim"),
        ("day", "bright"),
        ("dusk", "dim"),
        ("night", "darkness"),
    ])
    def test_known_times(self, tod, expected):
        assert light_for_time_of_day(tod) == expected

    def test_unknown_time_defaults_bright(self):
        assert light_for_time_of_day("eclipse") == "bright"


# --------------------------------------------------------------------------- #
# Obscurement derivation.
# --------------------------------------------------------------------------- #

class TestObscurement:
    def test_bright_clear_is_clear(self):
        assert derive_obscurement(E(light="bright", weather="clear")) == "clear"

    def test_dim_is_lightly_obscured(self):
        assert derive_obscurement(E(light="dim", weather="clear")) == "lightly_obscured"

    def test_darkness_is_heavily_obscured(self):
        assert derive_obscurement(E(light="darkness", weather="clear")) == "heavily_obscured"

    def test_fog_overrides_bright(self):
        # Fog is heavily obscured regardless of bright light.
        assert derive_obscurement(E(light="bright", weather="fog")) == "heavily_obscured"

    def test_light_rain_with_bright_is_lightly_obscured(self):
        assert derive_obscurement(E(light="bright", weather="light_rain")) == "lightly_obscured"

    def test_weather_never_improves_lighting(self):
        # Darkness + clear stays heavily obscured (weather can't improve it).
        assert derive_obscurement(E(light="darkness", weather="clear")) == "heavily_obscured"
        # Dim + heavy rain -> heavily obscured (weather worsens it).
        assert derive_obscurement(E(light="dim", weather="heavy_rain")) == "heavily_obscured"

    def test_strong_wind_alone_does_not_obscure(self):
        # Wind has no obscurement contribution, so bright+wind stays clear.
        assert derive_obscurement(E(light="bright", weather="strong_wind")) == "clear"

    def test_blizzard_is_heavily_obscured(self):
        assert derive_obscurement(E(light="bright", weather="blizzard")) == "heavily_obscured"


# --------------------------------------------------------------------------- #
# Derived effects matrix.
# --------------------------------------------------------------------------- #

class TestComputeEffects:
    def test_clear_day_normal_terrain_has_no_penalties(self):
        eff = compute_effects(E(light="bright", weather="clear", terrain="normal"))
        assert eff.obscurement == "clear"
        assert not eff.perception_disadvantage
        assert not eff.effective_blinded
        assert not eff.ranged_attack_disadvantage
        assert not eff.difficult_terrain
        assert eff.movement_cost_multiplier == 1.0
        assert eff.exhaustion_save is None
        assert eff.summary == "No environmental penalties."
        assert eff.active_effects == []

    def test_dim_light_gives_perception_disadvantage(self):
        eff = compute_effects(E(light="dim"))
        assert eff.lightly_obscured
        assert eff.perception_disadvantage
        assert not eff.effective_blinded
        assert "disadvantage on sight-based Perception checks" in eff.active_effects

    def test_darkness_blinds(self):
        eff = compute_effects(E(light="darkness"))
        assert eff.heavily_obscured
        assert eff.effective_blinded
        assert not eff.perception_disadvantage  # blinded, not lightly obscured
        assert "effectively blinded" in eff.summary

    def test_strong_wind_ranged_and_listen_disadvantage(self):
        eff = compute_effects(E(weather="strong_wind"))
        assert eff.ranged_attack_disadvantage
        assert eff.listen_disadvantage
        assert eff.flames_extinguished
        # Wind alone doesn't obscure.
        assert not eff.effective_blinded

    def test_blizzard_does_everything(self):
        eff = compute_effects(E(weather="blizzard"))
        assert eff.heavily_obscured
        assert eff.ranged_attack_disadvantage
        assert eff.listen_disadvantage
        assert eff.flames_extinguished
        assert eff.effective_blinded

    def test_difficult_terrain_doubles_movement_cost(self):
        for terrain in ("difficult", "heavy_difficult", "ice", "rubble",
                        "undergrowth", "water", "cliff"):
            eff = compute_effects(E(terrain=terrain))
            assert eff.difficult_terrain, f"{terrain} should be difficult"
            assert eff.movement_cost_multiplier == 2.0

    def test_ice_is_slippery(self):
        eff = compute_effects(E(terrain="ice"))
        assert eff.slippery
        assert "slippery footing" in eff.active_effects

    def test_water_requires_swim(self):
        eff = compute_effects(E(terrain="water"))
        assert eff.swim_required
        assert "swimming required" in eff.active_effects

    def test_cliff_requires_climb(self):
        eff = compute_effects(E(terrain="cliff"))
        assert eff.climb_required
        assert "climbing required" in eff.active_effects

    def test_extreme_cold_requires_save(self):
        eff = compute_effects(E(temperature="extreme_cold"))
        assert eff.exhaustion_save == {
            "ability": "constitution", "dc": 10,
            "frequency": "hour", "reason": "extreme_cold",
        }
        assert "extreme_cold" in eff.summary

    def test_extreme_heat_requires_save(self):
        eff = compute_effects(E(temperature="extreme_heat"))
        assert eff.exhaustion_save["reason"] == "extreme_heat"
        assert eff.exhaustion_save["ability"] == "constitution"

    def test_mild_cold_and_heat_have_no_save(self):
        for temp in ("normal", "cold", "heat"):
            eff = compute_effects(E(temperature=temp))
            assert eff.exhaustion_save is None

    def test_effects_serialize_to_dict(self):
        eff = compute_effects(E(weather="storm", terrain="ice", temperature="extreme_cold"))
        d = eff.to_dict()
        assert d["obscurement"] == "heavily_obscured"
        assert d["ranged_attack_disadvantage"] is True
        assert d["movement_cost_multiplier"] == 2.0
        assert d["exhaustion_save"]["reason"] == "extreme_cold"
        assert isinstance(d["active_effects"], list) and d["active_effects"]


# --------------------------------------------------------------------------- #
# Targeted effect queries.
# --------------------------------------------------------------------------- #

class TestEffectQueries:
    def test_sight_perception_disadvantage(self):
        assert sight_perception_disadvantage(E(light="dim"))
        assert not sight_perception_disadvantage(E(light="bright"))
        assert not sight_perception_disadvantage(E(light="darkness"))  # blinded, not disadv

    def test_is_effectively_blinded(self):
        assert is_effectively_blinded(E(light="darkness"))
        assert is_effectively_blinded(E(weather="fog"))
        assert not is_effectively_blinded(E(light="bright", weather="clear"))

    def test_ranged_attack_disadvantage(self):
        assert ranged_attack_disadvantage(E(weather="strong_wind"))
        assert ranged_attack_disadvantage(E(weather="storm"))
        assert not ranged_attack_disadvantage(E(weather="clear"))

    @pytest.mark.parametrize("base,terrain,expected", [
        (30, "normal", 30),
        (30, "difficult", 15),
        (25, "difficult", 12),
        (30, "ice", 15),
        (0, "difficult", 0),
        (30, "normal", 30),
    ])
    def test_effective_speed(self, base, terrain, expected):
        assert effective_speed(E(terrain=terrain), base) == expected

    def test_exhaustion_save_lookup(self):
        assert exhaustion_save(E(temperature="extreme_cold"))["dc"] == 10
        assert exhaustion_save(E(temperature="normal")) is None


# --------------------------------------------------------------------------- #
# Combat modifiers.
# --------------------------------------------------------------------------- #

class TestCombatModifiers:
    def test_ranged_attack_in_wind_has_disadvantage(self):
        mods = combat_modifiers(E(weather="strong_wind"), attack_is_ranged=True)
        assert mods.attacker_ranged_disadvantage
        assert not mods.attacker_melee_disadvantage

    def test_ranged_attack_in_clear_no_disadvantage(self):
        mods = combat_modifiers(E(weather="clear"), attack_is_ranged=True)
        assert not mods.attacker_ranged_disadvantage

    def test_melee_not_affected_by_wind(self):
        mods = combat_modifiers(E(weather="strong_wind"), attack_is_ranged=False)
        assert not mods.attacker_ranged_disadvantage
        assert not mods.attacker_melee_disadvantage

    def test_blinded_environment_disadvantages_melee(self):
        mods = combat_modifiers(E(light="darkness"), attack_is_ranged=False)
        assert mods.attacker_melee_disadvantage
        assert mods.attacker_cannot_see_target
        assert mods.target_unseen_by_attacker

    def test_modifiers_serialize(self):
        mods = combat_modifiers(E(weather="storm"), attack_is_ranged=True)
        d = mods.to_dict()
        assert d["attacker_ranged_disadvantage"] is True


# --------------------------------------------------------------------------- #
# Procedural weather / temperature.
# --------------------------------------------------------------------------- #

class TestProceduralWeather:
    def test_random_weather_deterministic_with_seed(self):
        r1 = random.Random(1234)
        r2 = random.Random(1234)
        results1 = [random_weather("temperate", "summer", r1) for _ in range(10)]
        results2 = [random_weather("temperate", "summer", r2) for _ in range(10)]
        assert results1 == results2

    def test_random_weather_returns_valid_type(self):
        for _ in range(50):
            w = random_weather("temperate", "spring")
            assert w in WEATHER_TYPES

    def test_random_weather_distribution(self):
        # Arctic winter should mostly produce snow/blizzard, not rain.
        r = random.Random(99)
        results = [random_weather("arctic", "winter", r) for _ in range(200)]
        snowy = sum(1 for w in results if "snow" in w or w == "blizzard")
        # Heavily snow-weighted table -> at least half should be snowy.
        assert snowy >= 100

    def test_random_weather_desert_rarely_storms(self):
        r = random.Random(7)
        results = [random_weather("desert", "summer", r) for _ in range(300)]
        clear = sum(1 for w in results if w == "clear")
        # Desert summer is ~85% clear.
        assert clear >= 200

    def test_random_weather_unknown_climate_defaults_temperate(self):
        r = random.Random(1)
        result = random_weather("tropical", "summer", r)
        assert result in WEATHER_TYPES

    def test_random_temperature_extreme_swing(self):
        # A seeded run that hits the 15% extreme-swing branch for cold -> extreme_cold.
        r = random.Random(1)
        found_extreme = False
        for _ in range(100):
            t = random_temperature("cold", "winter", r)
            assert t in TEMPERATURE_LEVELS
            if t == "extreme_cold":
                found_extreme = True
        # The 15% chance should trigger at least once in 100 rolls.
        assert found_extreme

    def test_random_temperature_tables(self):
        # Cold winter base is extreme_cold already; arctic winter is extreme_cold.
        r = random.Random(42)
        # Force a non-swing (set randint to return > 15) by overriding.
        class NoSwing:
            def randint(self, a, b):
                return 100  # always > 15 -> no swing
        assert random_temperature("temperate", "summer", NoSwing()) == "heat"
        assert random_temperature("cold", "summer", NoSwing()) == "normal"
        assert random_temperature("desert", "summer", NoSwing()) == "extreme_heat"
        assert random_temperature("arctic", "summer", NoSwing()) == "cold"

    def test_roll_environment_full_snapshot(self):
        r = random.Random(5)
        env = roll_environment("arctic", "winter", "night", r)
        assert env.time_of_day == "night"
        assert env.light == "darkness"
        assert env.weather in WEATHER_TYPES
        assert env.temperature in TEMPERATURE_LEVELS
        assert env.terrain == "normal"


# --------------------------------------------------------------------------- #
# Serialization.
# --------------------------------------------------------------------------- #

class TestSerialization:
    def test_environment_round_trip(self):
        env = Environment(
            light="darkness", weather="storm", terrain="ice",
            temperature="extreme_cold", time_of_day="night", notes="Frozen lake",
        )
        data = env.to_dict()
        restored = Environment.from_dict(data)
        assert restored.light == "darkness"
        assert restored.weather == "storm"
        assert restored.terrain == "ice"
        assert restored.temperature == "extreme_cold"
        assert restored.time_of_day == "night"
        assert restored.notes == "Frozen lake"

    def test_from_dict_none_returns_defaults(self):
        env = Environment.from_dict(None)
        assert env.light == "bright"
        assert env.weather == "clear"
        assert env.terrain == "normal"
        assert env.temperature == "normal"
        assert env.time_of_day == "day"
        assert env.notes == ""

    def test_from_dict_missing_fields(self):
        env = Environment.from_dict({"weather": "fog"})
        assert env.weather == "fog"
        assert env.light == "bright"  # default

    def test_from_dict_notes_null(self):
        env = Environment.from_dict({"notes": None})
        assert env.notes == ""

    def test_default_environment(self):
        env = default_environment()
        assert env.weather == "clear"
        assert env.light == "bright"

    def test_effects_computed_from_restored_env(self):
        env = Environment(light="dim", weather="fog")
        data = env.to_dict()
        restored = Environment.from_dict(data)
        eff = compute_effects(restored)
        assert eff.heavily_obscured  # fog dominates
