"""
Tests for the mounts & vehicles engine.

Covers:
- Mount registry: lookup, filtering, derived fields (speed multiplier,
  carrying capacity, fly/swim detection).
- MountState round-trip serialisation + fresh_state.
- Overland travel: pace multipliers + side-effect notes, mount speed scaling,
  gallop burst math (whole-trip vs remainder), clamping (min 1 hour), and the
  on-foot (no mount) baseline.
- Mounted combat modifiers: advantage vs smaller unmounted creatures; the
  Mounted Combatant feat benefits; controlled vs independent control; prone
  mount; downed mount (rider no longer mounted).
- melee_advantage_applies edge cases.
- Weapon-mounted rules (lance one-handed/reach/disadvantage-within-5ft;
  generic weapons; substring fallback).
- Dismount outcomes (prone save DC 10 success/failure; downed mount) and the
  damage/heal mount helpers (HP clamping, overflow, forced dismount at 0).
- DM/UI summary helpers.
"""
import pytest

from app.engine import mounts


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

class TestRegistry:
    def test_lookup_known(self):
        m = mounts.get_mount("warhorse")
        assert m is not None
        assert m.name == "Warhorse"
        assert m.speed == 60
        assert m.size == "large"
        assert m.cr == 0.5
        assert m.attacks  # warhorse has hooves

    def test_lookup_unknown(self):
        assert mounts.get_mount("nonsense") is None
        assert mounts.get_mount("") is None
        assert mounts.get_mount(None) is None

    def test_list_filter_by_type(self):
        flying = mounts.list_mounts("flying")
        assert all(m.type == "flying" for m in flying)
        assert {m.id for m in flying} >= {"pegasus", "griffon", "hippogriff"}
        land = mounts.list_mounts("land")
        assert all(m.type == "land" for m in land)
        assert mounts.get_mount("warhorse") in land
        vehicles = mounts.list_mounts("vehicle")
        assert {m.id for m in vehicles} >= {"cart", "wagon"}

    def test_list_all_unfiltered(self):
        all_mounts = mounts.list_mounts()
        assert len(all_mounts) >= 18
        # Sorted by (type, cost, name).
        types = [m.type for m in all_mounts]
        assert types == sorted(types)

    def test_speed_multiplier_uses_effective_speed(self):
        horse = mounts.get_mount("riding_horse")  # speed 60
        # 60/30 = 2.0
        assert horse.speed_multiplier == pytest.approx(2.0)
        pegasus = mounts.get_mount("pegasus")  # fly 90
        assert pegasus.speed_multiplier == pytest.approx(3.0)
        assert pegasus.can_fly

    def test_speed_multiplier_clamped(self):
        # A hypothetical very slow beast still bottoms out.
        slow = mounts.Mount(id="x", name="x", type="land", speed=1)
        assert slow.speed_multiplier == mounts.MIN_MOUNT_SPEED_MULT
        fast = mounts.Mount(id="x", name="x", type="land", speed=1000)
        assert fast.speed_multiplier == mounts.MAX_MOUNT_SPEED_MULT

    def test_carrying_capacity(self):
        horse = mounts.get_mount("riding_horse")  # STR 16, large (×2)
        # 16 × 15 × 2 = 480
        assert horse.carrying_capacity_lbs == 480
        mule = mounts.get_mount("mule")  # STR 14, medium (×1), Beast of Burden (×2)
        # 14 × 15 × 1 × 2 = 420
        assert mule.carrying_capacity_lbs == 420

    def test_vehicle_is_vehicle_flag(self):
        cart = mounts.get_mount("cart")
        assert cart.is_vehicle
        assert not mounts.get_mount("warhorse").is_vehicle

    def test_to_dict_includes_derived(self):
        d = mounts.get_mount("pegasus").to_dict()
        assert d["can_fly"] is True
        assert d["effective_speed"] == 90
        assert "speed_multiplier" in d and d["speed_multiplier"] == pytest.approx(3.0)
        assert "carrying_capacity_lbs" in d


# --------------------------------------------------------------------------- #
# MountState
# --------------------------------------------------------------------------- #

class TestMountState:
    def test_round_trip(self):
        s = mounts.MountState(
            mount_id="warhorse", current_hp=12, max_hp=19, mounted=True,
            conditions=["prone"], pace="fast", galloping=True,
        )
        d = s.to_dict()
        s2 = mounts.MountState.from_dict(d)
        assert s2 == s

    def test_from_dict_garbage_safe(self):
        s = mounts.MountState.from_dict(None)
        assert s.mount_id == "" and s.mounted is False
        s = mounts.MountState.from_dict({"mount_id": 7, "current_hp": "bad"})
        # Bad values fall back to defaults.
        assert s.current_hp == 0
        assert s.mount_id == "7"  # coerced to str

    def test_fresh_state(self):
        horse = mounts.get_mount("warhorse")
        s = mounts.fresh_state(horse)
        assert s.mount_id == "warhorse"
        assert s.current_hp == horse.hp
        assert s.max_hp == horse.hp
        assert s.mounted is True

    def test_has_mount_and_conscious(self):
        s = mounts.MountState(mount_id="warhorse", current_hp=5, max_hp=19, mounted=True)
        assert s.has_mount and s.is_conscious()
        s2 = mounts.MountState(mount_id="warhorse", current_hp=0, max_hp=19, mounted=True)
        assert s2.has_mount and not s2.is_conscious()
        s3 = mounts.MountState()  # no mount
        assert not s3.has_mount


# --------------------------------------------------------------------------- #
# Overland travel
# --------------------------------------------------------------------------- #

class TestTravelSpeed:
    def test_pace_multipliers_and_notes(self):
        assert mounts.pace_multiplier("slow") == pytest.approx(18 / 24)
        assert mounts.pace_multiplier("normal") == 1.0
        assert mounts.pace_multiplier("fast") == pytest.approx(30 / 24)
        assert mounts.pace_multiplier("weird") == 1.0  # unknown → normal
        assert "Slow pace" in mounts.pace_notes("slow")
        assert "Fast pace" in mounts.pace_notes("fast")
        assert "Normal pace" in mounts.pace_notes("normal")

    def test_on_foot_baseline(self):
        # No mount → pace × 1.0 mount mult.
        speed = mounts.adjust_travel_hours(24, mounts.MountState())
        assert speed.adjusted_hours == 24
        assert speed.mount_multiplier == 1.0
        assert speed.pace_multiplier == 1.0

    def test_horse_halves_travel_time(self):
        s = mounts.fresh_state(mounts.get_mount("riding_horse"))  # ×2
        speed = mounts.adjust_travel_hours(24, s)
        assert speed.adjusted_hours == 12
        assert speed.mount_multiplier == pytest.approx(2.0)

    def test_fast_pace_with_mount(self):
        s = mounts.MountState(mount_id="riding_horse", current_hp=13,
                              max_hp=13, mounted=True, pace="fast")
        speed = mounts.adjust_travel_hours(24, s)
        # 24 / (fast(1.25) × horse(2.0)) = 24 / 2.5 = 9.6 → round 10
        assert speed.adjusted_hours == 10

    def test_slow_pace_longer(self):
        s = mounts.MountState(mount_id="riding_horse", current_hp=13,
                              max_hp=13, mounted=True, pace="slow")
        speed = mounts.adjust_travel_hours(24, s)
        # 24 / (0.75 × 2.0) = 24 / 1.5 = 16
        assert speed.adjusted_hours == 16

    def test_gallop_short_trip_doubles_speed(self):
        s = mounts.MountState(mount_id="riding_horse", current_hp=13,
                              max_hp=13, mounted=True, galloping=True)
        # A 3-hour horse trip (→ 1.5h mount-scaled) fits inside the 2 mount-hour
        # gallop burst, so it halves again to 0.75 → clamped to min 1 hour.
        speed = mounts.adjust_travel_hours(3, s)
        assert speed.adjusted_hours == 1
        assert speed.galloping is True

    def test_gallop_long_trip_saves_one_hour(self):
        s = mounts.MountState(mount_id="riding_horse", current_hp=13,
                              max_hp=13, mounted=True, galloping=True)
        # 24h → 12h mount-scaled. Burst covers 2 mount-hours in 1 hour, remainder
        # (10) at normal speed → 1 + 10 = 11.
        speed = mounts.adjust_travel_hours(24, s)
        assert speed.adjusted_hours == 11

    def test_gallop_ignored_for_vehicle(self):
        s = mounts.MountState(mount_id="cart", current_hp=15, max_hp=15,
                              mounted=True, galloping=True)
        speed = mounts.adjust_travel_hours(24, s)
        # Cart speed 30 → mult 1.0; galloping ignored for vehicles.
        assert speed.adjusted_hours == 24
        assert speed.galloping is True  # flag preserved even though not applied

    def test_min_one_hour(self):
        s = mounts.fresh_state(mounts.get_mount("pegasus"))  # ×3
        speed = mounts.adjust_travel_hours(1, s)
        assert speed.adjusted_hours >= 1

    def test_travel_multiplier_combines_pace_and_mount(self):
        s = mounts.MountState(mount_id="riding_horse", current_hp=13,
                              max_hp=13, mounted=True, pace="fast")
        # fast(1.25) × horse(2.0) = 2.5
        assert mounts.travel_multiplier(s) == pytest.approx(2.5)


# --------------------------------------------------------------------------- #
# Mounted combat modifiers
# --------------------------------------------------------------------------- #

class TestMountedCombat:
    def test_no_mount_returns_empty(self):
        mods = mounts.rider_combat_modifiers(mounts.MountState())
        assert mods.mounted is False
        assert mods.melee_advantage is False
        assert mods.has_mounted_combatant_feat is False

    def test_downed_mount_rider_not_mounted(self):
        s = mounts.MountState(mount_id="warhorse", current_hp=0, max_hp=19, mounted=True)
        mods = mounts.rider_combat_modifiers(s)
        assert mods.mounted is False
        assert mods.melee_advantage is False
        assert any("downed" in n.lower() for n in mods.notes)

    def test_mounted_advantage(self):
        s = mounts.fresh_state(mounts.get_mount("warhorse"))
        mods = mounts.rider_combat_modifiers(s)
        assert mods.mounted is True
        assert mods.melee_advantage is True
        assert mods.mount_size == "large"
        assert mods.mount_speed == 60

    def test_mounted_combatant_feat(self):
        s = mounts.fresh_state(mounts.get_mount("warhorse"))
        mods = mounts.rider_combat_modifiers(s, has_mounted_combatant_feat=True)
        assert mods.has_mounted_combatant_feat
        assert mods.mount_dex_save_advantage
        assert mods.mount_evasion
        assert mods.can_redirect_attack_to_rider
        assert any("Mounted Combatant" in n for n in mods.notes)

    def test_controlled_vs_independent_notes(self):
        controlled = mounts.rider_combat_modifiers(mounts.fresh_state(mounts.get_mount("warhorse")))
        assert controlled.control_type == "controlled"
        assert any("Controlled mount" in n for n in controlled.notes)
        independent = mounts.rider_combat_modifiers(mounts.fresh_state(mounts.get_mount("pegasus")))
        assert independent.control_type == "independent"
        assert any("Independent mount" in n for n in independent.notes)

    def test_prone_mount_flagged(self):
        s = mounts.MountState(mount_id="warhorse", current_hp=19, max_hp=19,
                              mounted=True, conditions=["prone"])
        mods = mounts.rider_combat_modifiers(s)
        assert mods.mount_prone is True
        assert any("prone" in n.lower() for n in mods.notes)


class TestMeleeAdvantageApplies:
    def test_advantage_vs_smaller_unmounted(self):
        s = mounts.fresh_state(mounts.get_mount("warhorse"))  # large
        assert mounts.melee_advantage_applies(s, target_size="medium") is True
        assert mounts.melee_advantage_applies(s, target_size="small") is True

    def test_no_advantage_vs_same_or_larger(self):
        s = mounts.fresh_state(mounts.get_mount("warhorse"))  # large
        assert mounts.melee_advantage_applies(s, target_size="large") is False
        assert mounts.melee_advantage_applies(s, target_size="huge") is False

    def test_no_advantage_vs_mounted_target(self):
        s = mounts.fresh_state(mounts.get_mount("warhorse"))
        assert mounts.melee_advantage_applies(s, target_size="small", target_mounted=True) is False

    def test_no_advantage_when_not_mounted(self):
        s = mounts.MountState(mount_id="warhorse", current_hp=19, max_hp=19, mounted=False)
        assert mounts.melee_advantage_applies(s, target_size="tiny") is False

    def test_small_mount_vs_medium_no_advantage(self):
        # A mastiff is medium → no advantage vs medium targets.
        s = mounts.fresh_state(mounts.get_mount("mastiff"))
        assert mounts.melee_advantage_applies(s, target_size="medium") is False
        # …but advantage vs small/tiny.
        assert mounts.melee_advantage_applies(s, target_size="small") is True


# --------------------------------------------------------------------------- #
# Weapon-mounted rules
# --------------------------------------------------------------------------- #

class TestWeaponRules:
    def test_lance_rules(self):
        rules = mounts.weapon_mounted_rules("lance")
        assert rules["one_handed_while_mounted"] is True
        assert rules["two_handed_on_foot"] is True
        assert rules["reach"] is True
        assert rules["disadvantage_within_5ft"] is True

    def test_is_lance(self):
        assert mounts.is_lance("Lance") is True
        assert mounts.is_lance("heavy lance") is True
        assert mounts.is_lance("longsword") is False

    def test_substring_fallback(self):
        rules = mounts.weapon_mounted_rules("heavy crossbow")
        assert "notes" in rules
        # Falls back to the generic crossbow note.
        assert "Crossbow" in rules["notes"] or "crossbow" in rules["notes"]

    def test_unknown_weapon(self):
        rules = mounts.weapon_mounted_rules("longsword")
        assert "no special mounted" in rules["notes"].lower()


# --------------------------------------------------------------------------- #
# Dismount outcomes + damage/heal
# --------------------------------------------------------------------------- #

class TestDismount:
    def test_prone_outcome_pending(self):
        out = mounts.mount_prone_outcome()  # no save rolled
        assert out.forced_dismount is True
        assert out.dc == 10
        assert out.save_ability == "dexterity"

    def test_prone_outcome_success(self):
        out = mounts.mount_prone_outcome(save_total=10)
        assert out.forced_dismount is True
        assert out.rider_prone is False
        assert "feet" in out.message.lower()

    def test_prone_outcome_failure(self):
        out = mounts.mount_prone_outcome(save_total=9)
        assert out.rider_prone is True
        assert "prone" in out.message.lower()

    def test_downed_outcome(self):
        out = mounts.mount_downed_outcome()
        assert out.forced_dismount and out.rider_prone
        assert "collapses" in out.message.lower()

    def test_damage_below_zero_forces_dismount(self):
        s = mounts.fresh_state(mounts.get_mount("warhorse"))  # 19 hp
        new_s, out, overflow = mounts.damage_mount(s, 25)
        assert new_s.current_hp == 0
        assert new_s.mounted is False
        assert out.forced_dismount and out.rider_prone
        assert overflow == 6  # 25 - 19

    def test_damage_partial(self):
        s = mounts.fresh_state(mounts.get_mount("warhorse"))  # 19 hp
        new_s, out, overflow = mounts.damage_mount(s, 5)
        assert new_s.current_hp == 14
        assert out.forced_dismount is False
        assert overflow == 0
        assert "14/19" in out.message

    def test_damage_zero_or_noop(self):
        s = mounts.fresh_state(mounts.get_mount("warhorse"))
        new_s, out, _ = mounts.damage_mount(s, 0)
        assert new_s.current_hp == 19
        assert out.forced_dismount is False
        # No mount → no-op.
        empty = mounts.MountState()
        new_s, out, _ = mounts.damage_mount(empty, 10)
        assert out.forced_dismount is False

    def test_damage_does_not_mutate_input(self):
        s = mounts.fresh_state(mounts.get_mount("warhorse"))
        mounts.damage_mount(s, 5)
        assert s.current_hp == 19  # unchanged

    def test_heal_clamped(self):
        s = mounts.MountState(mount_id="warhorse", current_hp=10, max_hp=19, mounted=True)
        new_s, healed = mounts.heal_mount(s, 100)
        assert new_s.current_hp == 19
        assert healed == 9

    def test_heal_noop(self):
        s = mounts.fresh_state(mounts.get_mount("warhorse"))
        new_s, healed = mounts.heal_mount(s, 0)
        assert healed == 0
        empty = mounts.MountState()
        new_s, healed = mounts.heal_mount(empty, 5)
        assert healed == 0


# --------------------------------------------------------------------------- #
# DM / UI summary
# --------------------------------------------------------------------------- #

class TestSummary:
    def test_no_mount_summary(self):
        summ = mounts.mount_summary(mounts.MountState())
        assert summ["has_mount"] is False
        assert summ["mount"] is None

    def test_mounted_summary(self):
        s = mounts.fresh_state(mounts.get_mount("warhorse"))
        summ = mounts.mount_summary(s)
        assert summ["has_mount"] is True
        assert summ["mounted"] is True
        assert summ["mount"]["name"] == "Warhorse"
        assert summ["mount_hp"] == "19/19"

    def test_mount_for_dm_on_foot(self):
        assert mounts.mount_for_dm(mounts.MountState()) == "on foot"

    def test_mount_for_dm_mounted(self):
        s = mounts.fresh_state(mounts.get_mount("pegasus"))
        line = mounts.mount_for_dm(s)
        assert "Pegasus" in line
        assert "mounted" in line
        assert "[flying]" in line

    def test_mount_for_dm_leading_vehicle(self):
        s = mounts.MountState(mount_id="cart", current_hp=15, max_hp=15, mounted=False)
        line = mounts.mount_for_dm(s)
        assert "leading" in line
        assert "[vehicle]" in line


# --------------------------------------------------------------------------- #
# Navigation travel speed_multiplier integration
# --------------------------------------------------------------------------- #

class TestNavigationTravelIntegration:
    def test_navigation_travel_accepts_speed_multiplier(self):
        from app.engine.navigation import WorldMap
        world_data = {
            "regions": [
                {"name": "A", "description": "plains"},
                {"name": "B", "description": "plains"},
                {"name": "C", "description": "forest"},
            ],
            "starting_settlement": {"name": "A"},
        }
        wm = WorldMap.from_world_data(world_data, {})
        dest = wm.reachable_region_ids()[0]
        on_foot = wm.travel(dest, speed_multiplier=1.0)
        mounted = wm.travel(dest, speed_multiplier=2.0)
        assert mounted.travel_hours <= on_foot.travel_hours
