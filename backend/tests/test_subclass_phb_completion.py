"""
Tests for the PHB subclass-completion effort.

This run closed the registry's subclass gap: PHB ships a canonical set of
subclasses (archetypes / domains / origins / paths) per core class, and the
engine previously modelled a *representative* 29 of them — leaving four cleric
domains (Light, Nature, Tempest, Trickery), one monk tradition (Way of the
Four Elements), and six wizard schools (Conjuration, Divination, Enchantment,
Illusion, Necromancy, Transmutation) unregistered.

This file asserts:
  * the registry distribution milestone (total >= 40, per-class PHB coverage),
  * per-class PHB-completeness (the all-twelve-classes-PHB-complete milestone),
  * no-dup guards,
  * parametrized registration-shape (name / char_class / category / id for all
    11 new subclasses),
  * per-subclass mechanical correctness (feature progressions land at PHB
    levels; first feature at the class choice level; the signature PHB feature
    names appear),
  * lookup + validation behaviour for each new subclass.
"""
import pytest

from app.engine import subclasses as sc

# --------------------------------------------------------------------------- #
# The 11 PHB subclasses added in this run                                     #
# --------------------------------------------------------------------------- #

NEW_SUBCLASSES = [
    # cleric domains (Divine Domain, level 1)
    ("light-domain", "Light Domain", "cleric", "Divine Domain"),
    ("nature-domain", "Nature Domain", "cleric", "Divine Domain"),
    ("tempest-domain", "Tempest Domain", "cleric", "Divine Domain"),
    ("trickery-domain", "Trickery Domain", "cleric", "Divine Domain"),
    # monk tradition (Monastic Tradition, level 3)
    ("four-elements", "Way of the Four Elements", "monk", "Monastic Tradition"),
    # wizard schools (Arcane Tradition, level 2)
    ("conjuration", "School of Conjuration", "wizard", "Arcane Tradition"),
    ("divination", "School of Divination", "wizard", "Arcane Tradition"),
    ("enchantment", "School of Enchantment", "wizard", "Arcane Tradition"),
    ("illusion", "School of Illusion", "wizard", "Arcane Tradition"),
    ("necromancy", "School of Necromancy", "wizard", "Arcane Tradition"),
    ("transmutation", "School of Transmutation", "wizard", "Arcane Tradition"),
]

#: Canonical PHB subclass counts per core class (PHB p.45-118).
PHB_SUBCLASS_COUNTS = {
    "barbarian": 2,   # Berserker, Totem Warrior
    "bard": 2,        # Lore, Valor
    "cleric": 7,      # Knowledge, Life, Light, Nature, Tempest, Trickery, War
    "druid": 2,       # Land, Moon
    "fighter": 3,     # Champion, Battle Master, Eldritch Knight
    "monk": 3,        # Open Hand, Four Elements, Shadow
    "paladin": 3,     # Devotion, Ancients, Vengeance
    "ranger": 2,      # Hunter, Beast Master
    "rogue": 3,       # Thief, Assassin, Arcane Trickster
    "sorcerer": 2,    # Draconic Bloodline, Wild Magic
    "warlock": 3,     # Fiend, Archfey, Great Old One
    "wizard": 8,      # Abjuration, Conjuration, Divination, Enchantment,
                      # Evocation, Illusion, Necromancy, Transmutation
}


# --------------------------------------------------------------------------- #
# Registry distribution milestone                                             #
# --------------------------------------------------------------------------- #

def test_registry_meets_phb_total():
    # PHB ships 40 canonical subclasses across the 12 core classes.
    assert len(sc.all_subclasses()) >= 40


def test_registry_has_exactly_phb_set_now():
    # After this run the registry reaches the full PHB count of 40.
    assert len(sc.all_subclasses()) == 40


@pytest.mark.parametrize("char_class,expected", sorted(PHB_SUBCLASS_COUNTS.items()))
def test_each_class_has_phb_subclass_count(char_class, expected):
    actual = len(sc.subclasses_for_class(char_class))
    assert actual >= expected, (
        f"{char_class} has {actual} subclasses (PHB has {expected})"
    )


def test_all_twelve_core_classes_phb_complete():
    """The all-twelve-classes-PHB-complete milestone."""
    for cls, expected in PHB_SUBCLASS_COUNTS.items():
        actual = len(sc.subclasses_for_class(cls))
        assert actual >= expected, (
            f"{cls} not yet PHB-complete: {actual}/{expected}"
        )


# --------------------------------------------------------------------------- #
# No-dup guards                                                               #
# --------------------------------------------------------------------------- #

def test_new_subclass_ids_are_unique_in_registry():
    ids = [s.id for s in sc.all_subclasses()]
    assert len(ids) == len(set(ids)), "duplicate subclass ids"


def test_new_subclass_ids_unique_among_themselves():
    ids = [sub_id for sub_id, *_ in NEW_SUBCLASSES]
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------- #
# Parametrized registration-shape                                             #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("sub_id,name,char_class,category", NEW_SUBCLASSES)
def test_new_subclass_registered(sub_id, name, char_class, category):
    sub = sc.get_subclass(sub_id)
    assert sub is not None, f"{sub_id} not in registry"
    assert sub.name == name
    assert sub.char_class == char_class
    assert sub.category == category


@pytest.mark.parametrize("sub_id,name,char_class,category", NEW_SUBCLASSES)
def test_new_subclass_id_is_lowercase_kebab(sub_id, name, char_class, category):
    assert sub_id == sub_id.lower()
    assert " " not in sub_id


@pytest.mark.parametrize("sub_id,name,char_class,category", NEW_SUBCLASSES)
def test_new_subclass_appears_in_class_listing(sub_id, name, char_class, category):
    listing = sc.subclasses_for_class(char_class)
    assert any(s.id == sub_id for s in listing), (
        f"{sub_id} missing from {char_class} listing"
    )


@pytest.mark.parametrize("sub_id,name,char_class,category", NEW_SUBCLASSES)
def test_new_subclass_has_description(sub_id, name, char_class, category):
    sub = sc.get_subclass(sub_id)
    assert sub.description
    assert len(sub.description) > 20, f"{sub_id} description too short"


# --------------------------------------------------------------------------- #
# Feature-progression correctness                                            #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("sub_id,name,char_class,category", NEW_SUBCLASSES)
def test_new_subclass_has_features(sub_id, name, char_class, category):
    sub = sc.get_subclass(sub_id)
    assert sub.features, f"{sub_id} has no features"


@pytest.mark.parametrize("sub_id,name,char_class,category", NEW_SUBCLASSES)
def test_new_subclass_first_feature_at_choice_level(sub_id, name, char_class, category):
    """The first feature lands at the class's subclass choice level (PHB)."""
    sub = sc.get_subclass(sub_id)
    choice = sc.subclass_choice_level(char_class)
    assert min(sub.features) == choice, (
        f"{sub_id}'s first feature ({min(sub.features)}) != choice level {choice}"
    )


@pytest.mark.parametrize("sub_id,name,char_class,category", NEW_SUBCLASSES)
def test_new_subclass_to_dict_shape(sub_id, name, char_class, category):
    sub = sc.get_subclass(sub_id)
    d = sub.to_dict()
    assert d["id"] == sub_id
    assert d["name"] == name
    assert d["char_class"] == char_class
    assert d["category"] == category
    assert isinstance(d["features"], list)
    assert d["features"], f"{sub_id} has empty features list"
    levels = [f["level"] for f in d["features"]]
    assert levels == sorted(levels)


# --------------------------------------------------------------------------- #
# Cleric domain progression (features at 1, 2, 6, 8, 17 — PHB p.56-61)        #
# --------------------------------------------------------------------------- #

CLERIC_DOMAINS = [
    ("light-domain", "Warding Flare", "Radiance of the Dawn", "Corona of Light"),
    ("nature-domain", "Acolyte of Nature", "Charm Animals and Plants", "Master of Nature"),
    ("tempest-domain", "Wrath of the Storm", "Destructive Wrath", "Stormborn"),
    ("trickery-domain", "Blessing of the Trickster", "Invoke Duplicity", "Improved Duplicity"),
]


@pytest.mark.parametrize("sub_id,f1,f2,f17", CLERIC_DOMAINS)
def test_cleric_domain_feature_progression(sub_id, f1, f2, f17):
    sub = sc.get_subclass(sub_id)
    assert sub.char_class == "cleric"
    # All cleric domains have features at the canonical 1/2/6/8/17 stops.
    for lvl in (1, 2, 6, 8, 17):
        assert lvl in sub.features, f"{sub_id} missing level {lvl} feature"
    assert f1 in sub.features[1]
    assert f2 in sub.features[2]
    assert f17 in sub.features[17]
    # Divine Strike at 8 (every PHB domain gets it).
    assert "Divine Strike" in sub.features[8]


@pytest.mark.parametrize("sub_id,f1,f2,f17", CLERIC_DOMAINS)
def test_cleric_domain_choice_level_is_one(sub_id, f1, f2, f17):
    assert sc.subclass_choice_level("cleric") == 1
    sub = sc.get_subclass(sub_id)
    assert min(sub.features) == 1


def test_cleric_domains_count_is_phb_complete():
    # PHB ships exactly 7 cleric domains.
    assert len(sc.subclasses_for_class("cleric")) == 7


def test_all_seven_phb_cleric_domains_registered():
    names = {s.name for s in sc.subclasses_for_class("cleric")}
    expected = {
        "Life Domain", "War Domain", "Knowledge Domain",
        "Light Domain", "Nature Domain", "Tempest Domain", "Trickery Domain",
    }
    assert expected <= names


# --------------------------------------------------------------------------- #
# Monk tradition progression (features at 3, 6, 11, 17 — PHB p.76-81)         #
# --------------------------------------------------------------------------- #

def test_four_elements_feature_progression():
    sub = sc.get_subclass("four-elements")
    assert sub.char_class == "monk"
    # Monastic Traditions progress at 3 / 6 / 11 / 17 (PHB p.77).
    for lvl in (3, 6, 11, 17):
        assert lvl in sub.features
    assert "Disciple of the Elements" in sub.features[3]


def test_four_elements_choice_level_is_three():
    assert sc.subclass_choice_level("monk") == 3


def test_monk_traditions_count_is_phb_complete():
    # PHB ships exactly 3 monk traditions.
    assert len(sc.subclasses_for_class("monk")) == 3


def test_all_three_phb_monk_traditions_registered():
    names = {s.name for s in sc.subclasses_for_class("monk")}
    expected = {
        "Way of the Open Hand", "Way of Shadow", "Way of the Four Elements",
    }
    assert expected <= names


# --------------------------------------------------------------------------- #
# Wizard school progression (features at 2, 6, 10, 14 — PHB p.115-119)        #
# --------------------------------------------------------------------------- #

WIZARD_SCHOOLS = [
    ("conjuration", "Minor Conjuration", "Benign Transposition", "Durable Summons"),
    ("divination", "Portent", "Expert Divination", "Greater Portent"),
    ("enchantment", "Hypnotic Gaze", "Instinctive Charm", "Alter Memories"),
    ("illusion", "Improved Minor Illusion", "Malleable Illusions", "Illusory Reality"),
    ("necromancy", "Grim Harvest", "Undead Thralls", "Command Undead"),
    ("transmutation", "Minor Alchemy", "Transmuter's Stone", "Master Transmuter"),
]


@pytest.mark.parametrize("sub_id,f2,f6,f14", WIZARD_SCHOOLS)
def test_wizard_school_feature_progression(sub_id, f2, f6, f14):
    sub = sc.get_subclass(sub_id)
    assert sub.char_class == "wizard"
    # Arcane Traditions progress at 2 / 6 / 10 / 14 (PHB p.115).
    for lvl in (2, 6, 10, 14):
        assert lvl in sub.features, f"{sub_id} missing level {lvl}"
    assert f2 in sub.features[2]
    assert f6 in sub.features[6]
    assert f14 in sub.features[14]


@pytest.mark.parametrize("sub_id,f2,f6,f14", WIZARD_SCHOOLS)
def test_wizard_school_savant_feature(sub_id, f2, f6, f14):
    """Every PHB wizard school grants a Savant feature at level 2."""
    sub = sc.get_subclass(sub_id)
    assert "Savant" in sub.features[2]


@pytest.mark.parametrize("sub_id,f2,f6,f14", WIZARD_SCHOOLS)
def test_wizard_school_choice_level_is_two(sub_id, f2, f6, f14):
    assert sc.subclass_choice_level("wizard") == 2
    sub = sc.get_subclass(sub_id)
    assert min(sub.features) == 2


def test_wizard_schools_count_is_phb_complete():
    # PHB ships exactly 8 wizard schools (one per school of magic).
    assert len(sc.subclasses_for_class("wizard")) == 8


def test_all_eight_phb_wizard_schools_registered():
    names = {s.name for s in sc.subclasses_for_class("wizard")}
    expected = {
        "School of Abjuration", "School of Conjuration", "School of Divination",
        "School of Enchantment", "School of Evocation", "School of Illusion",
        "School of Necromancy", "School of Transmutation",
    }
    assert expected <= names


# --------------------------------------------------------------------------- #
# Validation behaviour for new subclasses                                     #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("sub_id,name,char_class,category", NEW_SUBCLASSES)
def test_validate_new_subclass_at_choice_level(sub_id, name, char_class, category):
    choice = sc.subclass_choice_level(char_class)
    res = sc.validate_subclass_choice(char_class, sub_id, choice)
    assert res.success, f"choosing {sub_id} at level {choice} failed: {res.message}"
    assert res.subclass is not None
    assert res.subclass.id == sub_id


@pytest.mark.parametrize("sub_id,name,char_class,category", NEW_SUBCLASSES)
def test_validate_new_subclass_below_choice_level(sub_id, name, char_class, category):
    choice = sc.subclass_choice_level(char_class)
    res = sc.validate_subclass_choice(char_class, sub_id, choice - 1)
    assert not res.success
    assert f"level {choice}" in res.message


@pytest.mark.parametrize("sub_id,name,char_class,category", NEW_SUBCLASSES)
def test_can_choose_new_subclass(sub_id, name, char_class, category):
    choice = sc.subclass_choice_level(char_class)
    assert sc.can_choose_subclass(char_class, choice) is True


@pytest.mark.parametrize("sub_id,name,char_class,category", NEW_SUBCLASSES)
def test_new_subclass_case_insensitive_lookup(sub_id, name, char_class, category):
    assert sc.get_subclass(sub_id.upper()) is not None


# --------------------------------------------------------------------------- #
# DM-context helper sanity                                                    #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("sub_id,name,char_class,category", NEW_SUBCLASSES)
def test_subclass_summary_for_dm_renders_new_subclass(sub_id, name, char_class, category):
    """A new subclass with at least one active feature renders its name."""
    choice = sc.subclass_choice_level(char_class)
    line = sc.subclass_summary_for_dm(char_class, sub_id, choice)
    assert name in line


def test_subclass_summary_alias_consistent_for_new_subclass():
    a = sc.subclass_summary_for_dm("wizard", "necromancy", 10)
    b = sc.subclass_for_dm("wizard", "necromancy", 10)
    assert a == b
    assert "Necromancy" in a


# --------------------------------------------------------------------------- #
# Cross-cutting milestone: all-twelve-classes-PHB-complete                    #
# --------------------------------------------------------------------------- #

def test_total_phb_subclass_coverage():
    """Sum of PHB counts == 40; registry now matches the full PHB set."""
    assert sum(PHB_SUBCLASS_COUNTS.values()) == 40
    assert len(sc.all_subclasses()) >= sum(PHB_SUBCLASS_COUNTS.values())
