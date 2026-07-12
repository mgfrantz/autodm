"""
Tests for curated starter adventures — the engine registry and the REST API.

Covers:
- The registry (3 adventures, each with a shape-complete world_data payload)
- Lookup helpers (list / get / world_data_for)
- The /api/adventures endpoints (list, detail, detail 404, start creates a
  World, name override, start 404)
- That a started adventure's world_data round-trips through the World row
  and is compatible with what the game-start endpoint consumes.
"""
import json

from fastapi.testclient import TestClient

from app.main import app
from app.models.models import World
from app.engine.adventures import (
    STARTER_ADVENTURES,
    list_adventures,
    get_adventure,
    world_data_for,
    StarterAdventure,
)


# ---------------------------------------------------------------------------
# Registry / engine tests
# ---------------------------------------------------------------------------

def test_registry_has_three_adventures():
    assert len(STARTER_ADVENTURES) >= 3


def test_every_adventure_has_unique_id():
    ids = [a.id for a in STARTER_ADVENTURES]
    assert len(ids) == len(set(ids)), "Duplicate adventure ids"


def test_known_adventure_ids():
    ids = {a.id for a in STARTER_ADVENTURES}
    assert {"cursed-mines", "whispering-moor", "shattered-spires"}.issubset(ids)


def test_list_adventures_returns_all():
    advs = list_adventures()
    assert len(advs) == len(STARTER_ADVENTURES)


def test_get_adventure_found():
    adv = get_adventure("cursed-mines")
    assert adv is not None
    assert adv.name == "The Cursed Mines of Emberdeep"
    assert adv.tone == "heroic fantasy"


def test_get_adventure_not_found():
    assert get_adventure("does-not-exist") is None


def test_world_data_for_found():
    data = world_data_for("cursed-mines")
    assert data is not None
    assert data["name"] == "The Cursed Mines of Emberdeep"


def test_world_data_for_not_found():
    assert world_data_for("nope") is None


def test_world_data_for_returns_independent_copy():
    """Mutating the returned dict must not corrupt the registry."""
    data = world_data_for("cursed-mines")
    assert data is not None
    original_name = data["name"]
    data["name"] = "MUTATED"
    fresh = world_data_for("cursed-mines")
    assert fresh["name"] == original_name


# --- Shape-completeness: every world_data must carry the fields the game
# pipeline (game/start, game/create) reads. ---

REQUIRED_WORLD_KEYS = {
    "name", "description", "tone", "regions", "campaign_arc",
    "starting_settlement", "npcs", "factions", "hook",
}


def test_every_adventure_world_data_has_required_keys():
    for adv in STARTER_ADVENTURES:
        missing = REQUIRED_WORLD_KEYS - set(adv.world_data.keys())
        assert not missing, f"{adv.id} missing keys: {missing}"


def test_every_starting_settlement_has_a_name():
    for adv in STARTER_ADVENTURES:
        ss = adv.world_data.get("starting_settlement", {})
        assert ss.get("name"), f"{adv.id} starting_settlement has no name"


def test_every_adventure_has_regions():
    for adv in STARTER_ADVENTURES:
        regions = adv.world_data.get("regions", [])
        assert len(regions) >= 2, f"{adv.id} has too few regions"


def test_every_adventure_has_npcs_and_factions():
    for adv in STARTER_ADVENTURES:
        assert len(adv.world_data.get("npcs", [])) >= 3, f"{adv.id} has too few npcs"
        assert len(adv.world_data.get("factions", [])) >= 1, f"{adv.id} has no factions"


def test_to_dict_summary_omits_world_data():
    adv = get_adventure("cursed-mines")
    d = adv.to_dict(include_world_data=False)
    assert "world_data" not in d
    assert d["id"] == "cursed-mines"
    assert isinstance(d["tags"], list)


def test_to_dict_detail_includes_world_data():
    adv = get_adventure("cursed-mines")
    d = adv.to_dict(include_world_data=True)
    assert "world_data" in d
    assert d["world_data"]["hook"]


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

def test_api_list_adventures(client: TestClient):
    response = client.get("/api/adventures/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 3
    # Summary omits world_data.
    assert all("world_data" not in a for a in data)
    ids = {a["id"] for a in data}
    assert "cursed-mines" in ids
    # Each summary carries the metadata fields.
    sample = data[0]
    for key in ("id", "name", "tagline", "blurb", "tone", "recommended_level", "tags"):
        assert key in sample


def test_api_get_adventure_detail(client: TestClient):
    response = client.get("/api/adventures/cursed-mines")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "cursed-mines"
    assert data["name"] == "The Cursed Mines of Emberdeep"
    assert "world_data" in data
    assert data["world_data"]["starting_settlement"]["name"] == "Oakhollow"


def test_api_get_adventure_detail_not_found(client: TestClient):
    response = client.get("/api/adventures/does-not-exist")
    assert response.status_code == 404


def test_api_start_creates_world(client: TestClient, db_session):
    response = client.post(
        "/api/adventures/start",
        json={"adventure_id": "cursed-mines"},
    )
    assert response.status_code == 200
    world_id = response.json()["world_id"]
    assert world_id > 0

    world = db_session.query(World).filter(World.id == world_id).first()
    assert world is not None
    assert world.name == "The Cursed Mines of Emberdeep"
    assert world.tone == "heroic fantasy"
    # The persisted world_data round-trips back to a valid dict.
    wd = json.loads(world.world_data)
    assert wd["starting_settlement"]["name"] == "Oakhollow"
    assert wd["hook"]


def test_api_start_with_name_override(client: TestClient, db_session):
    response = client.post(
        "/api/adventures/start",
        json={"adventure_id": "whispering-moor", "name": "My Custom Moor"},
    )
    assert response.status_code == 200
    world_id = response.json()["world_id"]
    world = db_session.query(World).filter(World.id == world_id).first()
    assert world.name == "My Custom Moor"
    # The underlying world_data tone is preserved.
    assert json.loads(world.world_data)["tone"] == "gothic horror"


def test_api_start_not_found(client: TestClient):
    response = client.post(
        "/api/adventures/start",
        json={"adventure_id": "nope"},
    )
    assert response.status_code == 404


def test_started_world_is_compatible_with_game_pipeline(client: TestClient, db_session):
    """A world created from a starter adventure carries every field that the
    game/create and game/start endpoints read, so it's a true drop-in."""
    response = client.post(
        "/api/adventures/start",
        json={"adventure_id": "shattered-spires"},
    )
    assert response.status_code == 200
    world_id = response.json()["world_id"]
    world = db_session.query(World).filter(World.id == world_id).first()
    wd = json.loads(world.world_data)

    # These are exactly the lookups in api/game.py create + start.
    assert wd["starting_settlement"]["name"]  # starting_loc
    assert wd["description"]                   # setting
    assert wd["hook"]                          # adventure hook
