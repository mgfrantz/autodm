"""
Tests for the character background system.

Covers:
- engine/backgrounds.py: registry completeness, per-background data fidelity,
  skill/tool/language/equipment/feature accessors, normalization, and the
  "single source of truth" contract with the skills and tools engines.
- api/backgrounds.py: registry listing/detail, character background resolution,
  and set-background (equipment + gold grant, idempotency, validation).
"""
import json

import pytest

from app.engine import backgrounds as bg_engine
from app.engine import skills as sk
from app.engine import tools as tl
from app.engine.inventory import ItemType, Rarity


# --------------------------------------------------------------------------- #
# Engine: registry shape & completeness
# --------------------------------------------------------------------------- #

class TestRegistry:
    def test_all_phb_backgrounds_present(self):
        names = {b.lower() for b in bg_engine.list_background_names()}
        expected = {
            "acolyte", "charlatan", "criminal", "entertainer", "folk hero",
            "guild artisan", "hermit", "noble", "outlander", "sage", "sailor",
            "soldier", "urchin",
        }
        assert expected.issubset(names), expected - names

    def test_variants_present(self):
        names = {b.lower() for b in bg_engine.list_background_names()}
        for v in ("spy", "gladiator", "knight", "pirate", "guild merchant"):
            assert v in names, f"variant {v} missing"

    def test_registry_count(self):
        # 13 PHB + 5 common variants = 18
        assert len(bg_engine.list_backgrounds()) == 18

    def test_each_background_has_required_fields(self):
        for bg in bg_engine.list_backgrounds():
            assert bg.id, bg
            assert bg.name, bg
            assert bg.description, bg
            assert isinstance(bg.skill_proficiencies, list)
            assert len(bg.skill_proficiencies) == 2, f"{bg.id} should grant 2 skills"
            assert bg.feature is not None, f"{bg.id} has no feature"
            assert bg.feature.name, f"{bg.id} feature has no name"
            assert bg.feature.description, f"{bg.id} feature has no description"

    def test_each_background_has_equipment_and_gold(self):
        for bg in bg_engine.list_backgrounds():
            assert isinstance(bg.equipment, list) and len(bg.equipment) >= 1, f"{bg.id} has no equipment"
            assert isinstance(bg.equipment_gold, int) and bg.equipment_gold >= 0, f"{bg.id} gold"

    def test_skill_proficiencies_are_real_skills(self):
        from app.engine.skills import ALL_SKILLS
        for bg in bg_engine.list_backgrounds():
            for s in bg.skill_proficiencies:
                assert s in ALL_SKILLS, f"{bg.id} has bogus skill {s}"

    def test_variant_of_chain(self):
        assert bg_engine.get_background("spy").variant_of == "criminal"
        assert bg_engine.get_background("gladiator").variant_of == "entertainer"
        assert bg_engine.get_background("knight").variant_of == "noble"
        assert bg_engine.get_background("pirate").variant_of == "sailor"
        assert bg_engine.get_background("guild merchant").variant_of == "guild artisan"
        # Non-variants have None
        assert bg_engine.get_background("soldier").variant_of is None

    def test_characteristics_present_for_core_backgrounds(self):
        # At least some flavor text for roleplay inspiration
        for bg_id in ("acolyte", "soldier", "sage", "noble", "charlatan"):
            bg = bg_engine.get_background(bg_id)
            assert len(bg.personality_traits) >= 3, f"{bg_id} personality_traits"
            assert len(bg.ideals) >= 3, f"{bg_id} ideals"
            assert len(bg.bonds) >= 3, f"{bg_id} bonds"
            assert len(bg.flaws) >= 3, f"{bg_id} flaws"


# --------------------------------------------------------------------------- #
# Engine: accessors & normalization
# --------------------------------------------------------------------------- #

class TestAccessors:
    def test_get_background_case_insensitive(self):
        assert bg_engine.get_background("Soldier").id == "soldier"
        assert bg_engine.get_background("SOLDIER").id == "soldier"
        assert bg_engine.get_background(" folk hero ").id == "folk hero"

    def test_get_background_unknown(self):
        assert bg_engine.get_background("astronaut") is None
        assert bg_engine.background_exists("astronaut") is False
        assert bg_engine.background_exists("acolyte") is True

    def test_get_background_skills(self):
        assert bg_engine.get_background_skills("soldier") == ["athletics", "intimidation"]
        assert bg_engine.get_background_skills("sage") == ["arcana", "history"]
        assert bg_engine.get_background_skills("astronaut") == []

    def test_get_background_feature(self):
        f = bg_engine.get_background_feature("acolyte")
        assert f is not None
        assert f.name == "Shelter of the Faithful"
        assert "temple" in f.description.lower() or "faith" in f.description.lower()

    def test_get_background_feature_unknown(self):
        assert bg_engine.get_background_feature("astronaut") is None

    def test_get_background_tool_grants(self):
        grants = bg_engine.get_background_tool_grants("criminal")
        assert "thieves_tools" in grants["fixed"]
        assert grants["choice"] is not None
        assert grants["choice"]["count"] == 1

    def test_get_background_tool_grants_no_choice(self):
        grants = bg_engine.get_background_tool_grants("charlatan")
        assert set(grants["fixed"]) == {"disguise_kit", "forgery_kit"}
        assert grants["choice"] is None

    def test_get_background_tool_grants_unknown(self):
        assert bg_engine.get_background_tool_grants("astronaut") == {"fixed": [], "choice": None}

    def test_get_background_languages(self):
        fixed, extra = bg_engine.get_background_languages("acolyte")
        assert fixed == []
        assert extra == 2  # PHB: two languages of your choice
        fixed, extra = bg_engine.get_background_languages("sage")
        assert extra == 2
        fixed, extra = bg_engine.get_background_languages("soldier")
        assert extra == 0
        # Unknown
        assert bg_engine.get_background_languages("astronaut") == ([], 0)

    def test_get_background_equipment_returns_fresh_items(self):
        items1 = bg_engine.get_background_equipment("soldier")
        items2 = bg_engine.get_background_equipment("soldier")
        assert len(items1) >= 1
        # Fresh instances: mutating one set must not affect the registry/other
        items1[0].quantity = 999
        assert items2[0].quantity != 999
        # Registry item untouched
        assert bg_engine.get_background("soldier").equipment[0].quantity != 999

    def test_get_background_equipment_gold(self):
        assert bg_engine.get_background_equipment_gold("noble") == 25
        assert bg_engine.get_background_equipment_gold("soldier") == 10
        assert bg_engine.get_background_equipment_gold("astronaut") == 0

    def test_equipment_items_have_valid_types(self):
        for bg in bg_engine.list_backgrounds():
            for item in bg.equipment:
                assert isinstance(item.item_type, ItemType)
                assert isinstance(item.rarity, Rarity)
                assert item.name, f"{bg.id} has unnamed item"

    def test_to_dict_roundtrip_shape(self):
        d = bg_engine.get_background("hermit").to_dict()
        assert d["id"] == "hermit"
        assert d["feature"]["name"] == "Discovery"
        assert isinstance(d["equipment"], list)
        assert all("name" in e for e in d["equipment"])
        assert "tool_proficiencies" in d
        assert d["tool_proficiencies"]["fixed"] == ["herbalism_kit"]

    def test_background_summary_shape(self):
        summary = bg_engine.background_summary()
        assert len(summary) == 18
        first = summary[0]
        assert {"id", "name", "description", "skill_proficiencies", "feature", "variant_of"} <= set(first)


# --------------------------------------------------------------------------- #
# Engine: single source of truth contract
# --------------------------------------------------------------------------- #

class TestSingleSourceOfTruth:
    def test_skills_engine_matches_registry(self):
        for bg in bg_engine.list_backgrounds():
            assert sk.get_background_skills(bg.id) == bg.skill_proficiencies

    def test_tools_engine_matches_registry(self):
        for bg in bg_engine.list_backgrounds():
            assert tl.get_background_tool_grants(bg.id) == bg.tool_grants()

    def test_skills_dict_covers_all_backgrounds(self):
        # _BACKGROUND_SKILLS must list every registry background
        assert set(sk._BACKGROUND_SKILLS.keys()) == set(bg_engine.BACKGROUNDS.keys())

    def test_tools_dict_covers_all_backgrounds(self):
        assert set(tl._BACKGROUND_TOOLS.keys()) == set(bg_engine.BACKGROUNDS.keys())

    def test_all_background_skills_valid_via_dict(self):
        from app.engine.skills import _BACKGROUND_SKILLS, ALL_SKILLS
        for bg, skills_list in _BACKGROUND_SKILLS.items():
            for s in skills_list:
                assert s in ALL_SKILLS


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #

class TestBackgroundsAPI:
    """REST API for the background system."""

    def _create_character(self, client, **overrides):
        payload = {
            "name": "Test Hero",
            "race": "Human",
            "char_class": "Fighter",
            "level": 1,
            "background": overrides.get("background"),
            "strength": 16,
            "dexterity": 14,
            "constitution": 14,
            "intelligence": 10,
            "wisdom": 12,
            "charisma": 10,
        }
        payload.update(overrides)
        payload.pop("background", None)  # set below if provided
        if "background" in overrides:
            payload["background"] = overrides["background"]
        r = client.post("/api/characters/", json=payload)
        assert r.status_code == 200, r.text
        return r.json()

    def test_list_backgrounds(self, client):
        r = client.get("/api/backgrounds")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 18
        ids = {b["id"] for b in data}
        assert "soldier" in ids and "acolyte" in ids
        # summary fields
        soldier = next(b for b in data if b["id"] == "soldier")
        assert soldier["name"] == "Soldier"
        assert "athletics" in soldier["skill_proficiencies"]
        assert soldier["feature"] == "Military Rank"

    def test_get_background_detail(self, client):
        r = client.get("/api/backgrounds/Acolyte")
        assert r.status_code == 200
        bg = r.json()
        assert bg["id"] == "acolyte"
        assert bg["name"] == "Acolyte"
        assert bg["feature"]["name"] == "Shelter of the Faithful"
        assert bg["extra_languages"] == 2
        assert len(bg["equipment"]) >= 1
        assert bg["equipment_gold"] == 15
        # equipment items are serialized
        assert all("item_type" in e for e in bg["equipment"])
        # tool grants shape
        assert "tool_proficiencies_fixed" in bg
        assert "tool_proficiencies_choice" in bg

    def test_get_background_detail_unknown_404(self, client):
        r = client.get("/api/backgrounds/astronaut")
        assert r.status_code == 404

    def test_get_background_by_id(self, client):
        # Detail lookup works with the lowercase id too
        r = client.get("/api/backgrounds/soldier")
        assert r.status_code == 200
        assert r.json()["name"] == "Soldier"

    def test_get_character_background_known(self, client):
        char = self._create_character(client, background="Soldier")
        r = client.get(f"/api/characters/{char['id']}/background")
        assert r.status_code == 200
        data = r.json()
        assert data["background_known"] is True
        assert data["background"] == "Soldier"
        assert data["detail"]["feature"]["name"] == "Military Rank"
        assert data["detail"]["skill_proficiencies"] == ["athletics", "intimidation"]

    def test_get_character_background_unknown_bg(self, client):
        char = self._create_character(client, background="Time Lord")
        r = client.get(f"/api/characters/{char['id']}/background")
        assert r.status_code == 200
        data = r.json()
        assert data["background_known"] is False
        assert data["detail"] is None
        assert data["background"] == "Time Lord"

    def test_get_character_background_none(self, client):
        char = self._create_character(client)
        r = client.get(f"/api/characters/{char['id']}/background")
        assert r.status_code == 200
        assert r.json()["background_known"] is False

    def test_get_character_background_missing_character_404(self, client):
        r = client.get("/api/characters/999999/background")
        assert r.status_code == 404

    def test_set_background_grants_equipment_and_gold(self, client):
        char = self._create_character(client)
        char_id = char["id"]
        starting_gold = char["gold"]

        r = client.post(
            f"/api/characters/{char_id}/background",
            json={"background": "Noble", "apply_equipment": True},
        )
        assert r.status_code == 200, r.text
        result = r.json()
        assert result["success"] is True
        assert result["background"] == "Noble"
        assert result["feature"] == "Position of Privilege"
        assert result["gold_granted"] == 25
        assert result["total_gold"] == starting_gold + 25
        assert len(result["equipment_granted"]) >= 1
        assert "Signet Ring" in result["equipment_granted"]

        # Equipment actually landed in inventory
        inv = client.get(f"/api/characters/{char_id}/inventory").json()
        names = [s["item"]["name"] for s in inv.get("slots", [])]
        assert "Signet Ring" in names

        # Background persisted
        char_after = client.get(f"/api/characters/{char_id}").json()
        assert char_after["background"] == "Noble"

    def test_set_background_apply_equipment_false(self, client):
        char = self._create_character(client)
        char_id = char["id"]
        starting_gold = char["gold"]

        r = client.post(
            f"/api/characters/{char_id}/background",
            json={"background": "Sage", "apply_equipment": False},
        )
        assert r.status_code == 200
        result = r.json()
        assert result["gold_granted"] == 0
        assert result["equipment_granted"] == []
        # gold unchanged
        assert result["total_gold"] == starting_gold
        # but background still set
        char_after = client.get(f"/api/characters/{char_id}").json()
        assert char_after["background"] == "Sage"

    def test_set_background_idempotent_no_double_grant(self, client):
        char = self._create_character(client, background="Acolyte")
        char_id = char["id"]
        gold_before = client.get(f"/api/characters/{char_id}").json()["gold"]

        # Setting the SAME background again should NOT grant equipment again
        r = client.post(
            f"/api/characters/{char_id}/background",
            json={"background": "Acolyte", "apply_equipment": True},
        )
        assert r.status_code == 200
        result = r.json()
        assert result["gold_granted"] == 0
        assert result["equipment_granted"] == []
        gold_after = client.get(f"/api/characters/{char_id}").json()["gold"]
        assert gold_after == gold_before

    def test_set_background_switch_grants_new_equipment(self, client):
        char = self._create_character(client, background="Soldier")
        char_id = char["id"]

        r = client.post(
            f"/api/characters/{char_id}/background",
            json={"background": "Sailor", "apply_equipment": True},
        )
        assert r.status_code == 200
        result = r.json()
        assert result["gold_granted"] == 10
        assert "Silk Rope" in result["equipment_granted"]
        assert "Belaying Pin" in result["equipment_granted"]

    def test_set_background_unknown_400(self, client):
        char = self._create_character(client)
        r = client.post(
            f"/api/characters/{char['id']}/background",
            json={"background": "Astronaut"},
        )
        assert r.status_code == 400

    def test_set_background_missing_character_404(self, client):
        r = client.post(
            "/api/characters/999999/background",
            json={"background": "Sage"},
        )
        assert r.status_code == 404

    def test_variants_resolve_in_api(self, client):
        r = client.get("/api/backgrounds/Spy")
        assert r.status_code == 200
        bg = r.json()
        assert bg["variant_of"] == "criminal"
        assert bg["skill_proficiencies"] == ["deception", "stealth"]
