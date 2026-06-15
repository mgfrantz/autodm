"""
Tests for the navigation engine and API.

Covers:
- terrain classification
- map construction from world data (coordinate/connection auto-layout)
- travel validation, random encounters, and persistence
- the navigation REST endpoints
"""
import json
import random

import pytest
from fastapi.testclient import TestClient

from app.engine.navigation import (
    RegionNode,
    TravelResult,
    WorldMap,
    classify_terrain,
    terrain_encounter_rate,
    TERRAIN_ENCOUNTER_RATE,
    _connected_components,
    _slugify,
)
from app.models.models import Character, World, GameSave


# --- Fixtures -----------------------------------------------------------------

def _world_data(num_regions=5):
    """A small but representative world for tests."""
    regions = [
        {
            "name": "Oakhaven Vale",
            "description": "A peaceful green valley dotted with farms.",
            "settlements": ["Oakhaven", "Millbrook"],
            "dangers": ["Wolves prowling the farms"],
        },
        {
            "name": "Whisperwood",
            "description": "A dense ancient forest shrouded in mist.",
            "settlements": ["Sylvanpost"],
            "dangers": ["Spider ambush", "Blink dog pack"],
        },
        {
            "name": "Frostpeak Mountains",
            "description": "Snow-capped peaks and frozen passes.",
            "settlements": [],
            "dangers": ["Frost giant patrol", "Avalanche"],
        },
        {
            "name": "Sunken Mire",
            "description": "A treacherous marsh and bog.",
            "settlements": ["Reedham"],
            "dangers": ["Bog hag coven"],
        },
        {
            "name": "Port Maris",
            "description": "A bustling coastal port city by the sea.",
            "settlements": ["Port Maris"],
            "dangers": ["Smuggler ambush"],
        },
    ][:num_regions]
    return {
        "name": "Testoria",
        "description": "A land of adventure.",
        "regions": regions,
        "starting_settlement": {"name": "Oakhaven", "description": "A friendly town."},
        "hook": "Something stirs.",
    }


@pytest.fixture
def game_save(db_session):
    """Create a character, world, and game save, returning the save."""
    char = Character(
        name="Test Hero",
        race="Human",
        char_class="Fighter",
        level=1,
        strength=16, dexterity=12, constitution=14,
        intelligence=10, wisdom=10, charisma=10,
        max_hp=12, current_hp=12, armor_class=16, speed=30,
    )
    db_session.add(char)
    db_session.flush()

    world = World(
        name="Testoria",
        description="A land of adventure.",
        world_data=json.dumps(_world_data()),
        tone="heroic fantasy",
    )
    db_session.add(world)
    db_session.flush()

    save = GameSave(
        name="Test Game",
        character_id=char.id,
        world_id=world.id,
        game_state=json.dumps({"location": "Oakhaven"}),
        story_log="[]",
    )
    db_session.add(save)
    db_session.commit()
    return save


# --- Terrain classification ---------------------------------------------------

class TestTerrainClassification:
    def test_forest(self):
        assert classify_terrain("Whisperwood a dense forest") == "forest"

    def test_mountain(self):
        assert classify_terrain("Stonecrags rocky mountain peaks") == "mountain"

    def test_swamp(self):
        assert classify_terrain("Sunken Mire a marsh bog") == "swamp"

    def test_coast(self):
        assert classify_terrain("Port Maris by the sea coast") == "coast"

    def test_city(self):
        assert classify_terrain("Marisburg a grand city metropolis") == "city"

    def test_desert(self):
        assert classify_terrain("The Burning Wastes desert sands") == "desert"

    def test_tundra(self):
        assert classify_terrain("Frozen tundra ice fields") == "tundra"

    def test_underground(self):
        assert classify_terrain("Deep cavern dungeons") == "underground"

    def test_plains_default(self):
        assert classify_terrain("Endless rolling land") == "plains"

    def test_empty_string(self):
        assert classify_terrain("") == "plains"

    def test_encounter_rate_lookup(self):
        assert terrain_encounter_rate("city") == 0.05
        assert terrain_encounter_rate("forest") == 0.20
        assert terrain_encounter_rate("unknown") == 0.15
        assert 0 < terrain_encounter_rate("mountain") <= 1

    def test_all_terrains_have_rates(self):
        for terrain in ("underground", "tundra", "desert", "swamp", "mountain",
                        "coast", "forest", "city", "plains"):
            assert terrain in TERRAIN_ENCOUNTER_RATE


# --- RegionNode ---------------------------------------------------------------

class TestRegionNode:
    def test_from_raw_basic(self):
        node = RegionNode.from_raw({
            "name": "Dark Forest",
            "description": "A scary wood",
            "settlements": ["Camp"],
            "dangers": ["Spiders"],
        })
        assert node.id == "dark-forest"
        assert node.terrain == "forest"
        assert node.settlements == ["Camp"]
        assert node.dangers == ["Spiders"]

    def test_from_raw_uses_explicit_coordinates(self):
        node = RegionNode.from_raw({"name": "R", "coordinates": [0.2, 0.8]})
        assert node.coordinates == (0.2, 0.8)

    def test_from_raw_clamps_coordinates(self):
        node = RegionNode.from_raw({"name": "R", "coordinates": [-1, 5]})
        assert node.coordinates == (0.0, 1.0)

    def test_from_raw_uses_explicit_terrain(self):
        node = RegionNode.from_raw({"name": "R", "terrain": "desert"})
        assert node.terrain == "desert"

    def test_from_raw_uses_explicit_connections(self):
        node = RegionNode.from_raw({"name": "R", "connections": ["Other"]})
        assert node.connections == ["Other"]

    def test_to_dict_serializes(self):
        node = RegionNode.from_raw({"name": "R", "description": "d", "settlements": ["s"], "dangers": ["x"]})
        d = node.to_dict()
        assert d["coordinates"][0] == d["coordinates"][1]  # placeholder 0.5
        assert d["icon"]
        assert d["id"] == "r"

    def test_slugify_handles_special_chars(self):
        assert _slugify("Frostpeak Mountains!") == "frostpeak-mountains"
        assert _slugify("   ") == "region"


# --- WorldMap construction ----------------------------------------------------

class TestWorldMapConstruction:
    def test_builds_all_regions(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        assert len(wm.regions) == 5

    def test_starting_region_chosen_by_settlement(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        # Oakhaven is in the Oakhaven Vale region's settlements.
        assert wm.current_region_id == "oakhaven-vale"

    def test_graph_is_connected(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        resolved = {rid: set(node.connections) for rid, node in wm.regions.items()}
        components = _connected_components(list(wm.regions), resolved)
        assert len(components) == 1, "Map should be fully connected"

    def test_connections_are_bidirectional(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        for rid, node in wm.regions.items():
            for conn in node.connections:
                assert rid in wm.regions[conn].connections, f"{rid}->{conn} not bidirectional"

    def test_auto_assigned_coordinates_in_bounds(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        for node in wm.regions.values():
            x, y = node.coordinates
            assert 0.0 <= x <= 1.0
            assert 0.0 <= y <= 1.0

    def test_no_two_unplaced_regions_overlap(self):
        wm = WorldMap.from_world_data(_world_data(4), {})
        placed = [n.coordinates for n in wm.regions.values()]
        # All auto-placed (circle) coords should be distinct.
        assert len(set(placed)) == len(placed)

    def test_single_region_world(self):
        wd = {"regions": [{"name": "Only Place", "description": "d", "settlements": [], "dangers": []}],
              "starting_settlement": {"name": "Only Place"}}
        wm = WorldMap.from_world_data(wd, {})
        assert len(wm.regions) == 1
        assert wm.current_region_id == "only-place"

    def test_empty_regions_synthesises_one(self):
        wm = WorldMap.from_world_data({"starting_settlement": {"name": "Nowhere"}}, {})
        assert len(wm.regions) == 1
        assert wm.current_region().name == "Nowhere"

    def test_restores_position_from_game_state(self):
        gs = {"current_region_id": "frostpeak-mountains", "visited_regions": ["frostpeak-mountains"]}
        wm = WorldMap.from_world_data(_world_data(), gs)
        assert wm.current_region_id == "frostpeak-mountains"

    def test_invalid_saved_region_falls_back(self):
        gs = {"current_region_id": "does-not-exist"}
        wm = WorldMap.from_world_data(_world_data(), gs)
        assert wm.current_region_id == "oakhaven-vale"

    def test_respects_explicit_connections(self):
        wd = {"regions": [
            {"name": "A", "connections": ["B"], "settlements": ["A"], "dangers": []},
            {"name": "B", "connections": ["A"], "settlements": [], "dangers": []},
            {"name": "C", "settlements": [], "dangers": []},
        ], "starting_settlement": {"name": "A"}}
        wm = WorldMap.from_world_data(wd, {})
        assert "b" in wm.regions["a"].connections
        # C has no explicit connections -> auto-connected to keep graph whole.
        assert wm.regions["c"].connections, "C should be auto-connected into the graph"

    def test_to_dict_shape(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        d = wm.to_dict()
        assert d["current_region_id"] == wm.current_region_id
        assert "current_region" in d
        assert "reachable_region_ids" in d
        assert len(d["regions"]) == 5
        assert "coordinates" in d["regions"][0]

    def test_to_game_state(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        gs = wm.to_game_state()
        assert gs["current_region_id"] == wm.current_region_id
        assert wm.current_region_id in gs["visited_regions"]


# --- Travel mechanics ---------------------------------------------------------

class TestTravel:
    def test_reachable_regions_are_connected(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        reachable = set(wm.reachable_region_ids())
        assert reachable, "Starting region should have reachable neighbours"
        assert reachable.issubset(set(wm.current_region().connections))

    def test_can_travel_to_reachable(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        dest = wm.reachable_region_ids()[0]
        assert wm.can_travel(dest)

    def test_travel_succeeds_and_moves(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        dest = wm.reachable_region_ids()[0]
        # Force no encounter.
        rng = random.Random(0)
        result = wm.travel(dest, rng=rng)
        assert result.success
        assert result.to_region.id == dest
        assert wm.current_region_id == dest
        assert dest in wm.visited_region_ids
        assert result.travel_hours >= 4

    def test_travel_marks_visited(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        dest = wm.reachable_region_ids()[0]
        wm.travel(dest, rng=random.Random(1))
        assert wm.is_visited(dest)

    def test_travel_to_current_region_fails(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        result = wm.travel(wm.current_region_id)
        assert not result.success
        assert "already" in result.message.lower()

    def test_travel_to_non_adjacent_region_fails(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        non_adjacent = [rid for rid in wm.regions if rid not in wm.current_region().connections and rid != wm.current_region_id]
        assert non_adjacent, "Test world should have a non-adjacent region"
        result = wm.travel(non_adjacent[0])
        assert not result.success
        assert "not connected" in result.message.lower() or "no direct route" in result.message.lower()

    def test_travel_to_unknown_region_fails(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        result = wm.travel("nonexistent")
        assert not result.success
        assert "unknown" in result.message.lower()

    def test_encounter_triggered_with_danger(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        dest = wm.reachable_region_ids()[0]
        dest_node = wm.regions[dest]

        class ForceEncounterRNG(random.Random):
            def random(self):
                return 0.0  # always below any positive chance

        result = wm.travel(dest, rng=ForceEncounterRNG(0))
        assert result.encounter_triggered
        # Danger should come from the destination's dangers (if any).
        if dest_node.dangers:
            assert result.encounter_danger in dest_node.dangers

    def test_no_encounter_when_roll_high(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        dest = wm.reachable_region_ids()[0]

        class NoEncounterRNG(random.Random):
            def random(self):
                return 0.99  # above any terrain rate

        result = wm.travel(dest, rng=NoEncounterRNG(0))
        assert not result.encounter_triggered
        assert result.encounter_danger is None

    def test_encounter_chance_zero_when_no_dangers(self):
        wd = {"regions": [
            {"name": "Safe Town", "settlements": ["Safe Town"], "dangers": [], "terrain": "city"},
            {"name": "Next Town", "settlements": [], "dangers": [], "terrain": "city", "connections": ["Safe Town"]},
        ], "starting_settlement": {"name": "Safe Town"}}
        wm = WorldMap.from_world_data(wd, {})
        dest = wm.reachable_region_ids()[0]

        class ForceRNG(random.Random):
            def random(self):
                return 0.0

        result = wm.travel(dest, rng=ForceRNG(0))
        # Triggered by roll but no danger available.
        assert result.encounter_triggered
        assert result.encounter_danger is None

    def test_travel_result_to_dict(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        dest = wm.reachable_region_ids()[0]
        result = wm.travel(dest, rng=random.Random(7))
        d = result.to_dict()
        assert d["success"] is True
        assert d["to_region"]["id"] == dest
        assert isinstance(d["travel_hours"], int)
        assert "message" in d

    def test_travel_hours_scale_with_distance(self):
        wm = WorldMap.from_world_data(_world_data(), {})
        # Manually place two regions far apart and check hours.
        from app.engine.navigation import _distance
        a = wm.current_region()
        dest_id = wm.reachable_region_ids()[0]
        b = wm.regions[dest_id]
        dist = _distance(a.coordinates, b.coordinates)
        expected = max(4, round(dist * 48))
        result = wm.travel(dest_id, rng=random.Random(0))
        assert result.travel_hours == expected


# --- API tests ----------------------------------------------------------------

class TestNavigationAPI:
    def test_get_map(self, client: TestClient, game_save):
        r = client.get(f"/api/navigation/{game_save.id}/map")
        assert r.status_code == 200
        data = r.json()
        assert data["current_region_id"] == "oakhaven-vale"
        assert len(data["regions"]) == 5
        assert "reachable_region_ids" in data
        assert data["reachable_region_ids"], "Starting region should have neighbours"

    def test_list_regions(self, client: TestClient, game_save):
        r = client.get(f"/api/navigation/{game_save.id}/regions")
        assert r.status_code == 200
        data = r.json()
        assert data["current_region_id"] == "oakhaven-vale"
        current = [rg for rg in data["regions"] if rg["current"]]
        assert len(current) == 1
        assert current[0]["visited"] is True
        reachable = [rg for rg in data["regions"] if rg["reachable"]]
        assert reachable, "Some regions should be reachable"

    def test_travel_endpoint(self, client: TestClient, game_save):
        # First get the map to find a reachable region.
        m = client.get(f"/api/navigation/{game_save.id}/map").json()
        dest = m["reachable_region_ids"][0]
        r = client.post(f"/api/navigation/{game_save.id}/travel", json={"region_id": dest})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["to_region"]["id"] == dest

        # Position should persist in game state.
        m2 = client.get(f"/api/navigation/{game_save.id}/map").json()
        assert m2["current_region_id"] == dest
        assert dest in m2["visited_region_ids"]

    def test_travel_updates_location(self, client: TestClient, game_save):
        m = client.get(f"/api/navigation/{game_save.id}/map").json()
        dest = m["reachable_region_ids"][0]
        client.post(f"/api/navigation/{game_save.id}/travel", json={"region_id": dest})
        state = client.get(f"/api/game/{game_save.id}/state").json()
        dest_name = m["regions"][0]["name"]
        # location should now be the destination region's name
        names = [rg["name"] for rg in m["regions"] if rg["id"] == dest]
        assert state["game_state"]["location"] in names or state["game_state"]["location"] in state["game_state"]["visited_locations"]

    def test_travel_to_unknown_region_404(self, client: TestClient, game_save):
        r = client.post(f"/api/navigation/{game_save.id}/travel", json={"region_id": "nope"})
        assert r.status_code == 404

    def test_travel_to_non_adjacent_returns_unsuccessful(self, client: TestClient, game_save):
        m = client.get(f"/api/navigation/{game_save.id}/map").json()
        reachable = set(m["reachable_region_ids"])
        non_adjacent = [rg["id"] for rg in m["regions"]
                        if rg["id"] != m["current_region_id"] and rg["id"] not in reachable]
        assert non_adjacent, "Need a non-adjacent region for this test"
        r = client.post(f"/api/navigation/{game_save.id}/travel", json={"region_id": non_adjacent[0]})
        assert r.status_code == 200
        assert r.json()["success"] is False

    def test_map_not_found(self, client: TestClient):
        r = client.get("/api/navigation/9999/map")
        assert r.status_code == 404

    def test_explicit_connections_respected_via_api(self, client: TestClient, db_session):
        char = Character(name="H", race="Human", char_class="Fighter", level=1,
                         max_hp=10, current_hp=10, armor_class=10)
        db_session.add(char)
        db_session.flush()
        wd = {"regions": [
            {"name": "A", "connections": ["B"], "settlements": ["A"], "dangers": []},
            {"name": "B", "connections": ["A"], "settlements": [], "dangers": []},
            {"name": "C", "settlements": [], "dangers": []},
        ], "starting_settlement": {"name": "A"}}
        world = World(name="W", description="d", world_data=json.dumps(wd))
        db_session.add(world)
        db_session.flush()
        save = GameSave(name="G", character_id=char.id, world_id=world.id,
                        game_state='{"location": "A"}', story_log="[]")
        db_session.add(save)
        db_session.commit()

        m = client.get(f"/api/navigation/{save.id}/map").json()
        # From A, only B is directly connected (C is auto-bridged elsewhere).
        assert "b" in m["reachable_region_ids"]
        # Travel to B works.
        r = client.post(f"/api/navigation/{save.id}/travel", json={"region_id": "b"})
        assert r.status_code == 200
        assert r.json()["success"] is True
