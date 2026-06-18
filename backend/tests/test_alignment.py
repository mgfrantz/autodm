"""
Tests for the alignment system.

Covers:
- engine/alignment.py: the nine-alignment registry, lookups & normalization,
  relationship/conflict scoring, race & class tendencies, DM-context helpers,
  and NPC-reaction summaries.
- api/alignment.py: registry listing/detail, compatibility query, character
  alignment resolution, set alignment, and suggested alignments.
"""
import pytest

from app.engine import alignment as align


# --------------------------------------------------------------------------- #
# Engine: registry shape & completeness
# --------------------------------------------------------------------------- #

class TestRegistry:
    def test_nine_alignments(self):
        assert len(align.ALIGNMENTS) == 9

    def test_nine_alignment_ids(self):
        expected = {
            "lawful_good", "neutral_good", "chaotic_good",
            "lawful_neutral", "neutral", "chaotic_neutral",
            "lawful_evil", "neutral_evil", "chaotic_evil",
        }
        assert set(align.ALIGNMENTS.keys()) == expected

    def test_list_alignments_count_and_order(self):
        items = align.list_alignments()
        assert len(items) == 9
        # First three are the good row (lawful/neutral/chaotic good)
        assert [a.morals for a in items[:3]] == ["good", "good", "good"]
        assert items[0].ethics == "lawful"
        assert items[2].ethics == "chaotic"
        # Last three are the evil row
        assert [a.morals for a in items[6:]] == ["evil", "evil", "evil"]

    def test_each_alignment_has_required_fields(self):
        for a in align.list_alignments():
            assert a.id
            assert a.name
            assert a.abbreviation
            assert a.ethics in align.ETHICS_VALUES
            assert a.morals in align.MORALS_VALUES
            assert a.description
            assert isinstance(a.roleplay_hooks, list) and len(a.roleplay_hooks) >= 2

    def test_unique_abbreviations(self):
        abbrevs = [a.abbreviation for a in align.list_alignments()]
        assert len(set(abbrevs)) == len(abbrevs)

    def test_summary_shape(self):
        summaries = align.list_alignment_summaries()
        assert len(summaries) == 9
        first = summaries[0]
        assert {"id", "name", "abbreviation", "ethics", "morals", "description"} <= set(first)

    def test_to_dict_roundtrip_shape(self):
        a = align.get_alignment("lawful_good")
        d = a.to_dict()
        assert d["id"] == "lawful_good"
        assert d["abbreviation"] == "LG"
        assert "roleplay_hooks" in d and isinstance(d["roleplay_hooks"], list)


# --------------------------------------------------------------------------- #
# Engine: lookups & normalization
# --------------------------------------------------------------------------- #

class TestLookup:
    @pytest.mark.parametrize("raw,expected_id", [
        ("lawful_good", "lawful_good"),
        ("Lawful Good", "lawful_good"),
        ("  lawful   good  ", "lawful_good"),
        ("LG", "lawful_good"),
        ("lg", "lawful_good"),
        ("chaotic evil", "chaotic_evil"),
        ("CE", "chaotic_evil"),
        ("true neutral", "neutral"),
        ("True Neutral", "neutral"),
        ("TN", "neutral"),
        ("N", "neutral"),
        ("neutral", "neutral"),
        ("true_neutral", "neutral"),
    ])
    def test_get_alignment_resolves(self, raw, expected_id):
        assert align.get_alignment(raw).id == expected_id

    def test_get_alignment_unknown(self):
        assert align.get_alignment(" lawful purple ") is None
        assert align.get_alignment(None) is None
        assert align.get_alignment("") is None

    def test_alignment_exists(self):
        assert align.alignment_exists("Lawful Good")
        assert not align.alignment_exists("Lawful Purple")
        assert align.is_valid_alignment("CG")

    def test_get_alignment_or_default(self):
        assert align.get_alignment_or_default("Chaotic Good").id == "chaotic_good"
        assert align.get_alignment_or_default("garbage").id == "neutral"
        assert align.get_alignment_or_default("garbage", default="LG").id == "lawful_good"
        # unknown default falls back to True Neutral, never raises
        assert align.get_alignment_or_default("garbage", default="purple").id == "neutral"


# --------------------------------------------------------------------------- #
# Engine: relationship / conflict scoring
# --------------------------------------------------------------------------- #

class TestRelationship:
    def test_identical_is_friendly(self):
        rel = align.relationship("lawful_good", "lawful_good")
        assert rel.total_distance == 0
        assert rel.ethics_delta == 0
        assert rel.morals_delta == 0
        assert rel.disposition == "friendly"

    def test_one_step_cordial(self):
        # LG -> NG: share morals (good), adjacent on ethics
        rel = align.relationship("lawful_good", "neutral_good")
        assert rel.ethics_delta == 1
        assert rel.morals_delta == 0
        assert rel.total_distance == 1
        assert rel.disposition == "cordial"

    def test_diametrically_opposed_hostile(self):
        # LG vs CE: distance 4
        rel = align.relationship("lawful_good", "chaotic_evil")
        assert rel.total_distance == 4
        assert rel.disposition == "hostile"

    def test_opposed_single_axis(self):
        # LG vs LE: share ethics (lawful), opposed on morals
        rel = align.relationship("lawful_good", "lawful_evil")
        assert rel.ethics_delta == 0
        assert rel.morals_delta == 2
        assert rel.disposition in ("wary", "tense", "hostile")

    def test_relationship_unknown_returns_none(self):
        assert align.relationship("lawful_good", "purple") is None
        assert align.relationship(None, "lawful_good") is None

    def test_relationship_shape(self):
        rel = align.relationship("NG", "CE")
        d = rel.to_dict()
        assert {"other_id", "other_name", "ethics_delta", "morals_delta",
                "total_distance", "disposition", "description"} <= set(d)
        assert d["other_id"] == "chaotic_evil"

    def test_are_opposed(self):
        assert align.are_opposed("lawful_good", "chaotic_good") is True   # law vs chaos
        assert align.are_opposed("lawful_good", "lawful_evil") is True    # good vs evil
        assert align.are_opposed("lawful_good", "neutral_good") is False  # adjacent
        assert align.are_opposed("lawful_good", "lawful_good") is False
        assert align.are_opposed("lawful_good", "purple") is False

    def test_share_axis(self):
        assert align.share_axis("lawful_good", "lawful_evil") is True     # both lawful
        assert align.share_axis("lawful_good", "chaotic_good") is True    # both good
        assert align.share_axis("lawful_good", "chaotic_evil") is False   # share nothing
        # LG (lawful/good) vs True Neutral (neutral/neutral): agree on neither axis
        assert align.share_axis("lawful_good", "neutral") is False


# --------------------------------------------------------------------------- #
# Engine: tendencies
# --------------------------------------------------------------------------- #

class TestTendencies:
    def test_race_tendencies_present(self):
        for race in ("human", "elf", "dwarf", "halfling", "tiefling", "half-orc"):
            t = align.get_race_tendencies(race)
            assert len(t) >= 1, race
        # case/space insensitive
        assert align.get_race_tendencies("Half-Orc")
        assert align.get_race_tendencies("  half orc  ")
        # unknown -> empty
        assert align.get_race_tendencies("klingon") == []

    def test_class_tendencies_present(self):
        for cls in ("paladin", "rogue", "barbarian", "wizard", "cleric", "monk"):
            t = align.get_class_tendencies(cls)
            assert len(t) >= 1, cls
        # Paladin tends toward lawful good
        assert "lawful_good" in align.get_class_tendencies("paladin")
        assert align.get_class_tendencies("astronaut") == []

    def test_tendency_ids_are_valid(self):
        for ids in align.RACE_TENDENCIES.values():
            for a in ids:
                assert align.get_alignment(a) is not None, a
        for ids in align.CLASS_TENDENCIES.values():
            for a in ids:
                assert align.get_alignment(a) is not None, a

    def test_suggested_alignments_merges_race_and_class(self):
        # Paladin (human) — lawful_good should be high up (both suggest it)
        sug = align.suggested_alignments("human", "paladin")
        assert sug  # non-empty
        assert "lawful_good" in sug
        # de-duplicated
        assert len(sug) == len(set(sug))
        # both-agree items come first
        race_ids = align.get_race_tendencies("human")
        class_ids = align.get_class_tendencies("paladin")
        both = [a for a in race_ids if a in class_ids]
        if both:
            assert sug[0] in both

    def test_suggested_alignments_unknown_inputs(self):
        sug = align.suggested_alignments("klingon", "astronaut")
        assert sug == []


# --------------------------------------------------------------------------- #
# Engine: DM context helpers
# --------------------------------------------------------------------------- #

class TestDMContext:
    def test_alignment_context_known(self):
        ctx = align.alignment_context("Lawful Good")
        assert "Lawful Good" in ctx
        assert "LG" in ctx
        assert "Roleplay:" in ctx

    def test_alignment_context_unknown_empty(self):
        assert align.alignment_context("purple") == ""
        assert align.alignment_context(None) == ""

    def test_dm_prompt_summary(self):
        assert align.dm_prompt_summary("LG") == "Lawful Good (LG)"
        assert align.dm_prompt_summary("Chaotic Evil") == "Chaotic Evil (CE)"
        assert align.dm_prompt_summary(None) == ""

    def test_npc_reaction_summary(self):
        s = align.npc_reaction_summary("lawful_good", "chaotic_evil")
        assert s is not None
        assert "hostile" in s.lower()
        s2 = align.npc_reaction_summary("lawful_good", "lawful_good")
        assert s2 is not None and "friendly" in s2.lower()

    def test_npc_reaction_summary_unknown(self):
        assert align.npc_reaction_summary("purple", "lawful_good") is None
        assert align.npc_reaction_summary(None, None) is None


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #

class TestAlignmentAPI:
    """REST API for the alignment system."""

    def _create_character(self, client, **overrides):
        payload = {
            "name": "Aligned Hero",
            "race": "Human",
            "char_class": "Fighter",
            "level": 1,
            "strength": 16,
            "dexterity": 14,
            "constitution": 14,
            "intelligence": 10,
            "wisdom": 12,
            "charisma": 10,
        }
        payload.update(overrides)
        r = client.post("/api/characters/", json=payload)
        assert r.status_code == 200, r.text
        return r.json()

    def test_list_alignments(self, client):
        r = client.get("/api/alignment")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 9
        ids = {a["id"] for a in data}
        assert "lawful_good" in ids and "chaotic_evil" in ids
        first = data[0]
        assert first["name"] == "Lawful Good"
        assert first["abbreviation"] == "LG"
        assert first["ethics"] == "lawful"
        assert first["morals"] == "good"

    def test_get_alignment_detail(self, client):
        r = client.get("/api/alignment/Chaotic Evil")
        assert r.status_code == 200
        a = r.json()
        assert a["id"] == "chaotic_evil"
        assert a["abbreviation"] == "CE"
        assert len(a["roleplay_hooks"]) >= 2

    def test_get_alignment_by_id_and_abbr(self, client):
        assert client.get("/api/alignment/lawful_good").json()["id"] == "lawful_good"
        assert client.get("/api/alignment/LG").json()["id"] == "lawful_good"

    def test_get_alignment_unknown_404(self, client):
        r = client.get("/api/alignment/purple")
        assert r.status_code == 404

    def test_compatibility_identical(self, client):
        r = client.get("/api/alignment/compatibility", params={"a": "LG", "b": "LG"})
        assert r.status_code == 200
        data = r.json()
        assert data["alignment_a"] == "lawful_good"
        assert data["alignment_b"] == "lawful_good"
        assert data["relationship"]["total_distance"] == 0
        assert data["relationship"]["disposition"] == "friendly"

    def test_compatibility_opposed(self, client):
        r = client.get("/api/alignment/compatibility", params={"a": "LG", "b": "CE"})
        assert r.status_code == 200
        data = r.json()
        assert data["relationship"]["total_distance"] == 4
        assert data["relationship"]["disposition"] == "hostile"

    def test_compatibility_unknown(self, client):
        r = client.get("/api/alignment/compatibility", params={"a": "LG", "b": "purple"})
        assert r.status_code == 200
        data = r.json()
        assert data["alignment_a"] == "lawful_good"
        assert data["alignment_b"] is None
        assert data["relationship"] is None

    def test_character_alignment_none(self, client):
        char = self._create_character(client)
        r = client.get(f"/api/characters/{char['id']}/alignment")
        assert r.status_code == 200
        data = r.json()
        assert data["alignment_known"] is False
        assert data["detail"] is None

    def test_character_alignment_set_on_create(self, client):
        char = self._create_character(client, alignment="Lawful Good")
        # Stored as canonical id in the response
        assert char["alignment"] == "lawful_good"
        r = client.get(f"/api/characters/{char['id']}/alignment")
        assert r.status_code == 200
        data = r.json()
        assert data["alignment_known"] is True
        assert data["detail"]["abbreviation"] == "LG"

    def test_set_character_alignment(self, client):
        char = self._create_character(client)
        r = client.post(
            f"/api/characters/{char['id']}/alignment",
            json={"alignment": "Chaotic Neutral"},
        )
        assert r.status_code == 200
        result = r.json()
        assert result["alignment"] == "chaotic_neutral"
        assert result["abbreviation"] == "CN"

        # Persisted
        got = client.get(f"/api/characters/{char['id']}/alignment").json()
        assert got["alignment"] == "chaotic_neutral"

    def test_set_character_alignment_by_abbr(self, client):
        char = self._create_character(client)
        r = client.post(
            f"/api/characters/{char['id']}/alignment",
            json={"alignment": "CE"},
        )
        assert r.status_code == 200
        assert r.json()["alignment"] == "chaotic_evil"

    def test_set_character_alignment_unknown_400(self, client):
        char = self._create_character(client)
        r = client.post(
            f"/api/characters/{char['id']}/alignment",
            json={"alignment": "Lawful Purple"},
        )
        assert r.status_code == 400

    def test_set_character_alignment_missing_character_404(self, client):
        r = client.post(
            "/api/characters/999999/alignment",
            json={"alignment": "LG"},
        )
        assert r.status_code == 404

    def test_get_character_alignment_missing_character_404(self, client):
        r = client.get("/api/characters/999999/alignment")
        assert r.status_code == 404

    def test_suggested_alignments(self, client):
        char = self._create_character(client, race="Human", char_class="Paladin")
        r = client.get(f"/api/characters/{char['id']}/alignment/suggested")
        assert r.status_code == 200
        data = r.json()
        assert data["race"] == "Human"
        assert data["char_class"] == "Paladin"
        assert len(data["suggested"]) >= 1
        assert "lawful_good" in data["suggested"]
        assert isinstance(data["race_tendencies"], list)
        assert isinstance(data["class_tendencies"], list)


# --------------------------------------------------------------------------- #
# Cross-system: character creation stores alignment + game state surfaces it
# --------------------------------------------------------------------------- #

class TestCharacterCreationAlignment:
    def test_create_normalizes_alignment(self, client):
        # Pass by display name; stored as canonical id
        r = client.post("/api/characters/", json={
            "name": "Norm", "race": "Human", "char_class": "Fighter",
            "strength": 12, "dexterity": 12, "constitution": 12,
            "intelligence": 10, "wisdom": 10, "charisma": 10,
            "alignment": "Chaotic Good",
        })
        assert r.status_code == 200
        assert r.json()["alignment"] == "chaotic_good"

    def test_create_unknown_alignment_is_none(self, client):
        r = client.post("/api/characters/", json={
            "name": "Norm2", "race": "Human", "char_class": "Fighter",
            "strength": 12, "dexterity": 12, "constitution": 12,
            "intelligence": 10, "wisdom": 10, "charisma": 10,
            "alignment": "Lawful Purple",
        })
        assert r.status_code == 200
        assert r.json()["alignment"] is None

    def test_alignment_persists_across_get(self, client):
        r = client.post("/api/characters/", json={
            "name": "Persist", "race": "Elf", "char_class": "Rogue",
            "strength": 10, "dexterity": 16, "constitution": 12,
            "intelligence": 12, "wisdom": 10, "charisma": 10,
            "alignment": "cn",
        })
        char_id = r.json()["id"]
        got = client.get(f"/api/characters/{char_id}").json()
        assert got["alignment"] == "chaotic_neutral"
