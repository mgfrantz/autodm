"""
Tests for the subclass engine (pure, no DB).
"""
import pytest

from app.engine import subclasses as sc


# --------------------------------------------------------------------------- #
# Registry coverage                                                           #
# --------------------------------------------------------------------------- #

CORE_CLASSES = [
    "barbarian", "bard", "cleric", "druid", "fighter", "monk",
    "paladin", "ranger", "rogue", "sorcerer", "warlock", "wizard",
]


def test_every_core_class_has_subclasses():
    for cls in CORE_CLASSES:
        assert sc.has_subclasses(cls), f"{cls} has no subclasses"
        assert len(sc.subclasses_for_class(cls)) >= 2, (
            f"{cls} should have at least 2 subclasses"
        )


def test_registry_has_representative_count():
    # 12 classes * >=2 subclasses each → at least 24.
    assert len(sc.all_subclasses()) >= 24


def test_registry_ids_are_unique():
    ids = [s.id for s in sc.all_subclasses()]
    assert len(ids) == len(set(ids)), "duplicate subclass ids"


def test_registry_ids_are_lowercase_kebab():
    for s in sc.all_subclasses():
        assert s.id == s.id.lower(), f"id {s.id!r} not lowercase"
        assert " " not in s.id, f"id {s.id!r} contains spaces"


def test_each_subclass_belongs_to_its_class():
    for s in sc.all_subclasses():
        assert s.char_class in CORE_CLASSES
        # category must match the class's category
        assert s.category == sc.subclass_category(s.char_class)


def test_each_subclass_has_at_least_one_feature():
    for s in sc.all_subclasses():
        assert s.features, f"{s.id} has no features"
        # First feature must be at the class's choice level
        choice = sc.subclass_choice_level(s.char_class)
        assert min(s.features) <= choice + 1, (
            f"{s.id}'s first feature ({min(s.features)}) is too far past "
            f"choice level {choice}"
        )


def test_subclasses_for_class_sorted_by_name():
    for cls in CORE_CLASSES:
        names = [s.name for s in sc.subclasses_for_class(cls)]
        assert names == sorted(names)


# --------------------------------------------------------------------------- #
# Choice-level table                                                          #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("cls,expected", [
    ("cleric", 1), ("sorcerer", 1), ("warlock", 1),
    ("druid", 2), ("wizard", 2),
    ("barbarian", 3), ("bard", 3), ("fighter", 3), ("monk", 3),
    ("paladin", 3), ("ranger", 3), ("rogue", 3),
])
def test_subclass_choice_level(cls, expected):
    assert sc.subclass_choice_level(cls) == expected


def test_unknown_class_choice_level_is_zero():
    assert sc.subclass_choice_level("commoner") == 0


def test_choice_level_case_insensitive():
    assert sc.subclass_choice_level("Fighter") == 3
    assert sc.subclass_choice_level("WIZARD") == 2


def test_subclass_category_known():
    assert sc.subclass_category("fighter") == "Martial Archetype"
    assert sc.subclass_category("cleric") == "Divine Domain"
    assert sc.subclass_category("rogue") == "Roguish Archetype"


def test_subclass_category_unknown():
    assert sc.subclass_category("unknown") == "Subclass"


# --------------------------------------------------------------------------- #
# Lookups                                                                     #
# --------------------------------------------------------------------------- #

def test_get_subclass_found():
    sub = sc.get_subclass("champion")
    assert sub is not None
    assert sub.name == "Champion"
    assert sub.char_class == "fighter"


def test_get_subclass_case_insensitive():
    assert sc.get_subclass("Champion") is not None
    assert sc.get_subclass("LIFE-DOMAIN") is not None


def test_get_subclass_unknown_returns_none():
    assert sc.get_subclass("does-not-exist") is None


def test_get_subclass_empty_returns_none():
    assert sc.get_subclass("") is None
    assert sc.get_subclass(None) is None


# --------------------------------------------------------------------------- #
# Eligibility                                                                 #
# --------------------------------------------------------------------------- #

def test_can_choose_subclass_at_choice_level():
    # Fighter chooses at 3.
    assert sc.can_choose_subclass("fighter", 3) is True


def test_can_choose_subclass_below_level_false():
    assert sc.can_choose_subclass("fighter", 2) is False


def test_can_choose_subclass_already_chosen_false():
    assert sc.can_choose_subclass("fighter", 5, current_subclass="champion") is False


def test_can_choose_subclass_unknown_class_false():
    assert sc.can_choose_subclass("commoner", 20) is False


def test_can_choose_subclass_early_choice_classes():
    # Cleric/Sorcerer/Warlock choose at 1.
    assert sc.can_choose_subclass("cleric", 1) is True
    assert sc.can_choose_subclass("sorcerer", 1) is True
    assert sc.can_choose_subclass("warlock", 1) is True
    # Druid/Wizard choose at 2.
    assert sc.can_choose_subclass("druid", 2) is True
    assert sc.can_choose_subclass("wizard", 2) is True


# --------------------------------------------------------------------------- #
# Validation                                                                  #
# --------------------------------------------------------------------------- #

def test_validate_valid_choice():
    res = sc.validate_subclass_choice("fighter", "champion", 3)
    assert res.success
    assert res.subclass is not None
    assert res.subclass.name == "Champion"
    assert res.char_class == "fighter"


def test_validate_unknown_subclass():
    res = sc.validate_subclass_choice("fighter", "nope", 3)
    assert not res.success
    assert "Unknown" in res.message


def test_validate_wrong_class():
    res = sc.validate_subclass_choice("wizard", "champion", 3)
    assert not res.success
    assert "fighter" in res.message.lower() or "wizard" in res.message.lower()


def test_validate_below_level():
    res = sc.validate_subclass_choice("fighter", "champion", 2)
    assert not res.success
    assert "level 3" in res.message


def test_validate_already_chosen():
    res = sc.validate_subclass_choice("fighter", "champion", 5, current_subclass="berserker")
    assert not res.success
    assert res.message.startswith("Already")


def test_validate_case_insensitive_class():
    res = sc.validate_subclass_choice("Fighter", "Champion", 3)
    assert res.success


# --------------------------------------------------------------------------- #
# Feature progression                                                         #
# --------------------------------------------------------------------------- #

def test_features_at_level_known():
    # Champion gets Improved Critical at 3.
    feat = sc.features_at_level("champion", 3)
    assert "Improved Critical" in feat


def test_features_at_level_none():
    # Champion has nothing at 4.
    assert sc.features_at_level("champion", 4) == ""


def test_features_at_level_unknown_subclass():
    assert sc.features_at_level("nope", 3) == ""


def test_features_through_level():
    feats = sc.features_through_level("champion", 10)
    levels = [lvl for lvl, _ in feats]
    # 3 and 7 are <= 10; 15, 18 are not.
    assert 3 in levels
    assert 7 in levels
    assert 10 in levels  # Additional Fighting Style
    assert 15 not in levels
    assert levels == sorted(levels)


def test_features_through_level_capped():
    feats = sc.features_through_level("champion", 20)
    levels = [lvl for lvl, _ in feats]
    assert max(levels) <= 20
    assert 18 in levels  # Survivor


def test_features_through_level_unknown():
    assert sc.features_through_level("nope", 20) == []


def test_next_subclass_feature():
    nxt = sc.next_subclass_feature("champion", 3)
    assert nxt is not None
    lvl, feat = nxt
    assert lvl == 7
    assert "Athlete" in feat or "Remarkable" in feat


def test_next_subclass_feature_none_at_cap():
    # Champion's last feature is 18; beyond that nothing.
    assert sc.next_subclass_feature("champion", 18) is None


def test_next_subclass_feature_unknown():
    assert sc.next_subclass_feature("nope", 1) is None


# --------------------------------------------------------------------------- #
# DM / UI helpers                                                             #
# --------------------------------------------------------------------------- #

def test_summary_dm_no_subclass_below_choice():
    line = sc.subclass_summary_for_dm("fighter", None, 2)
    assert "level 3" in line


def test_summary_dm_no_subclass_eligible():
    line = sc.subclass_summary_for_dm("fighter", None, 5)
    assert "should choose" in line or "Martial Archetype" in line


def test_summary_dm_with_subclass():
    line = sc.subclass_summary_for_dm("fighter", "champion", 7)
    assert "Champion" in line
    # Active features (3, 7) should be mentioned.
    assert "Improved Critical" in line or "Remarkable" in line


def test_summary_dm_unknown_class():
    assert sc.subclass_summary_for_dm("commoner", None, 5) == "none"


def test_summary_dm_subclass_alias():
    a = sc.subclass_summary_for_dm("cleric", "life-domain", 6)
    b = sc.subclass_for_dm("cleric", "life-domain", 6)
    assert a == b


def test_combined_features_merges_class_and_subclass():
    combined = sc.combined_features_through_level("fighter", 7, "champion")
    sources = {entry["source"] for entry in combined}
    assert "class" in sources
    assert "Champion" in sources
    # Sorted by level.
    levels = [entry["level"] for entry in combined]
    assert levels == sorted(levels)


def test_combined_features_no_subclass():
    combined = sc.combined_features_through_level("fighter", 5)
    assert all(entry["source"] == "class" for entry in combined)


def test_to_dict_shape():
    sub = sc.get_subclass("life-domain")
    assert sub is not None
    d = sub.to_dict()
    assert d["id"] == "life-domain"
    assert d["char_class"] == "cleric"
    assert d["category"] == "Divine Domain"
    assert isinstance(d["features"], list)
    assert all("level" in f and "feature" in f for f in d["features"])
    # Features sorted by level.
    feat_levels = [f["level"] for f in d["features"]]
    assert feat_levels == sorted(feat_levels)


def test_feature_at_helper():
    sub = sc.get_subclass("berserker")
    assert sub is not None
    assert "Frenzy" in sub.feature_at(3)
    assert sub.feature_at(4) == ""
