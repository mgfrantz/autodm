"""
Tests for the iconic PHB level-1 spell **completion** — 16 spells added to round
out the most-played tier to full PHB coverage (level 1: 37 → 53; total 170 → 186).

This is the third tier-completion run in the catalogue-wide "PHB completeness"
effort: levels 7/8/9 were completed first, then the level-1 *expansion* (+16),
and this run finishes level 1 by adding the **remaining** iconic PHB level-1
spells that were still missing. With these additions, every PHB level-1 spell is
now registered.

The 16 additions (all iconic PHB level-1 spells), grouped by resolution path:
- Save-debuff (no damage): Animal Friendship (Wis), Compelled Duel (Wis).
- Healing (consumable berries): Goodberry.
- Utility / buff / ritual: Color Spray, Create or Destroy Water, Detect Evil
  and Good, Detect Poison and Disease, Expeditious Retreat, Feather Fall,
  Heroism, Jump, Purify Food and Drink, Silent Image, Tenser's Floating Disk,
  Unseen Servant, Wrathful Smite.

Coverage mirrors test_spell_level1_expansion.py / test_spell_level7_8_completion.py:
- Registry distribution (level 1 grew from 37 to 53 — PHB-complete; total grew
  to 186).
- Registration shape for every new spell (name, level, school) — parametrized.
- Per-spell mechanical correctness (save ability, concentration, ritual, dice,
  casting time, range, duration).
- Effect resolution for the save-debuff spells, the healing spell (Goodberry),
  and the utility/buff spells (all resolve without raising).
- Whole-registry no-duplicate-name / no-duplicate-id guards.
"""
import pytest

from app.engine.spells import (
    Spell,
    SpellSchool,
    SPELL_REGISTRY,
    get_spell,
    resolve_spell_effect,
)


def _spell(name: str) -> Spell:
    """Look up a spell by name/id and assert it is registered."""
    spell = get_spell(name)
    assert spell is not None, f"{name!r} should be registered"
    return spell


# --------------------------------------------------------------------------- #
# Registry distribution
# --------------------------------------------------------------------------- #
class TestRegistryShape:
    def test_total_spell_count_grew(self):
        # Was 170 before this completion; now 186.
        assert len(SPELL_REGISTRY) >= 186

    def test_level_1_tier_is_phb_complete(self):
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        # Level 1 grew from 37 to 53 — now PHB-complete.
        assert by_level[1] >= 53, (
            f"Level 1 has only {by_level[1]} spells (expected >=53 for PHB coverage)"
        )

    def test_phb_level1_completion_subset_present(self):
        """The 16 newly-added iconic PHB level-1 spells are all registered."""
        COMPLETION = [
            "Animal Friendship", "Color Spray", "Compelled Duel",
            "Create or Destroy Water", "Detect Evil and Good",
            "Detect Poison and Disease", "Expeditious Retreat", "Feather Fall",
            "Goodberry", "Heroism", "Jump", "Purify Food and Drink",
            "Silent Image", "Tenser's Floating Disk", "Unseen Servant",
            "Wrathful Smite",
        ]
        missing = [n for n in COMPLETION if get_spell(n) is None]
        assert missing == [], f"Missing iconic PHB level-1 spells: {missing}"

    def test_no_duplicate_spell_names_in_registry(self):
        """Every spell must have a unique name (no dict-key collisions)."""
        names = [s.name for s in SPELL_REGISTRY.values()]
        assert len(names) == len(set(names)), "Duplicate spell names detected"


# --------------------------------------------------------------------------- #
# Registration shape — every new spell at its correct level and school
# --------------------------------------------------------------------------- #
NEW_SPELLS: list[tuple[str, int, SpellSchool]] = [
    ("Animal Friendship", 1, SpellSchool.ENCHANTMENT),
    ("Color Spray", 1, SpellSchool.ILLUSION),
    ("Compelled Duel", 1, SpellSchool.ABJURATION),
    ("Create or Destroy Water", 1, SpellSchool.TRANSMUTATION),
    ("Detect Evil and Good", 1, SpellSchool.DIVINATION),
    ("Detect Poison and Disease", 1, SpellSchool.DIVINATION),
    ("Expeditious Retreat", 1, SpellSchool.TRANSMUTATION),
    ("Feather Fall", 1, SpellSchool.TRANSMUTATION),
    ("Goodberry", 1, SpellSchool.TRANSMUTATION),
    ("Heroism", 1, SpellSchool.ENCHANTMENT),
    ("Jump", 1, SpellSchool.TRANSMUTATION),
    ("Purify Food and Drink", 1, SpellSchool.TRANSMUTATION),
    ("Silent Image", 1, SpellSchool.ILLUSION),
    ("Tenser's Floating Disk", 1, SpellSchool.CONJURATION),
    ("Unseen Servant", 1, SpellSchool.CONJURATION),
    ("Wrathful Smite", 1, SpellSchool.EVOCATION),
]


@pytest.mark.parametrize("name, level, school", NEW_SPELLS)
def test_new_spell_registered(name, level, school):
    spell = _spell(name)
    assert spell.level == level
    assert spell.school == school


def test_new_spell_count_matches_plan():
    """All 16 planned new spells are registered."""
    assert len(NEW_SPELLS) == 16
    for name, _, _ in NEW_SPELLS:
        assert get_spell(name) is not None, f"{name!r} missing from registry"


def test_new_spell_ids_are_stable():
    """Each spell's id derives cleanly from its name (no collisions)."""
    for name, _, _ in NEW_SPELLS:
        spell = _spell(name)
        assert spell.id == name.lower().replace(" ", "_")
        # The registry key must match the id (no overwrite surprises).
        assert SPELL_REGISTRY[spell.id] is spell


def test_registry_keys_are_unique():
    """No two registered spells share the same id key."""
    keys = list(SPELL_REGISTRY.keys())
    assert len(keys) == len(set(keys))


# --------------------------------------------------------------------------- #
# Per-spell mechanical correctness
# --------------------------------------------------------------------------- #
class TestLevel1CompletionMechanics:
    def test_animal_friendship_is_wis_save_debuff(self):
        spell = _spell("Animal Friendship")
        assert spell.save_ability == "wis"
        assert spell.concentration is False
        assert spell.deals_damage is False and spell.heals is False
        assert spell.range == "30 feet"
        assert spell.duration == "24 hours"

    def test_color_spray_is_hp_threshold_no_save(self):
        spell = _spell("Color Spray")
        # Color Spray has no save and no engine damage dice — the 6d10
        # hit-point budget is described in text (mirrors Sleep).
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.school == SpellSchool.ILLUSION
        assert "15-foot cone" in spell.range
        assert spell.duration == "1 round"

    def test_compelled_duel_is_bonus_action_wis_save_concentration(self):
        spell = _spell("Compelled Duel")
        assert spell.save_ability == "wis"
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.casting_time == "1 bonus action"
        assert spell.range == "30 feet"
        assert spell.duration == "up to 1 minute"

    def test_create_or_destroy_water_is_utility(self):
        spell = _spell("Create or Destroy Water")
        assert spell.save_ability is None
        assert spell.concentration is False
        assert spell.deals_damage is False and spell.heals is False
        assert spell.range == "30 feet"

    def test_detect_evil_and_good_is_concentration_self_buff(self):
        spell = _spell("Detect Evil and Good")
        assert spell.concentration is True
        assert spell.ritual is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "self"
        assert spell.duration == "up to 10 minutes"

    def test_detect_poison_and_disease_is_concentration_ritual(self):
        spell = _spell("Detect Poison and Disease")
        assert spell.concentration is True
        assert spell.ritual is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "self"
        assert spell.duration == "up to 10 minutes"

    def test_expeditious_retreat_is_bonus_action_concentration(self):
        spell = _spell("Expeditious Retreat")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "1 bonus action"
        assert spell.range == "self"
        assert spell.duration == "up to 10 minutes"

    def test_feather_fall_is_reaction_utility(self):
        spell = _spell("Feather Fall")
        assert spell.casting_time == "1 reaction"
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "60 feet"
        assert spell.duration == "1 minute"

    def test_goodberry_is_healing(self):
        spell = _spell("Goodberry")
        # Ten berries, each restoring 1 HP → 10d1 = 10 total healing capacity.
        assert spell.heals is True
        assert spell.healing_dice_count == 10 and spell.healing_dice_sides == 1
        assert spell.healing_bonus == 0
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "24 hours"

    def test_heroism_is_concentration_touch_buff(self):
        spell = _spell("Heroism")
        # Temp HP equals the spellcasting modifier (described, not rolled);
        # modeled as a buff with effects in the description, like Bless.
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False and spell.heals is False
        assert spell.range == "touch"
        assert spell.duration == "up to 1 minute"

    def test_jump_is_touch_buff(self):
        spell = _spell("Jump")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False and spell.heals is False
        assert spell.range == "touch"
        assert spell.duration == "1 minute"

    def test_purify_food_and_drink_is_ritual_utility(self):
        spell = _spell("Purify Food and Drink")
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False and spell.heals is False
        assert spell.range == "10 feet"

    def test_silent_image_is_concentration_illusion(self):
        spell = _spell("Silent Image")
        # The Investigation check is an ability check (not a saving throw), so
        # save_ability is left None (mirrors Disguise Self).
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.school == SpellSchool.ILLUSION
        assert spell.deals_damage is False
        assert spell.range == "60 feet"
        assert spell.duration == "up to 10 minutes"

    def test_tensers_floating_disk_is_ritual_utility(self):
        spell = _spell("Tenser's Floating Disk")
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False and spell.heals is False
        assert spell.duration == "1 hour"

    def test_unseen_servant_is_ritual_utility(self):
        spell = _spell("Unseen Servant")
        assert spell.ritual is True
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False and spell.heals is False
        assert spell.range == "60 feet"
        assert spell.duration == "1 hour"

    def test_wrathful_smite_is_concentration_buff(self):
        spell = _spell("Wrathful Smite")
        # The 1d6 psychic rider and Wis-save frightened rider are described in
        # text (mirrors Hunter's Mark / Hex); no engine damage dice.
        assert spell.concentration is True
        assert spell.casting_time == "1 bonus action"
        assert spell.range == "self"
        assert spell.deals_damage is False
        assert spell.duration == "up to 1 minute"


# --------------------------------------------------------------------------- #
# Effect resolution of the new spells
# --------------------------------------------------------------------------- #
class TestNewSpellCompletionResolution:
    def test_animal_friendship_resolves_as_save_debuff(self):
        spell = _spell("Animal Friendship")
        # Failed save.
        effect = resolve_spell_effect(
            spell=spell, caster_level=3, proficiency_bonus=2,
            casting_mod=4, target_save_total=5, spell_save_dc=15,
        )
        assert effect.made_save is False
        assert effect.damage == 0
        # Made save.
        effect = resolve_spell_effect(
            spell=spell, caster_level=3, proficiency_bonus=2,
            casting_mod=4, target_save_total=20, spell_save_dc=15,
        )
        assert effect.made_save is True
        assert effect.damage == 0

    def test_compelled_duel_resolves_as_save_debuff(self):
        spell = _spell("Compelled Duel")
        effect = resolve_spell_effect(
            spell=spell, caster_level=3, proficiency_bonus=2,
            casting_mod=4, target_save_total=5, spell_save_dc=15,
        )
        assert effect.made_save is False
        assert effect.damage == 0

    def test_goodberry_heals(self):
        spell = _spell("Goodberry")
        effect = resolve_spell_effect(
            spell=spell, caster_level=3, proficiency_bonus=2, casting_mod=4,
        )
        # Ten berries × 1 HP = exactly 10 total healing.
        assert effect.healing == 10
        assert effect.damage == 0

    @pytest.mark.parametrize(
        "name",
        [
            "Color Spray",
            "Create or Destroy Water",
            "Detect Evil and Good",
            "Detect Poison and Disease",
            "Expeditious Retreat",
            "Feather Fall",
            "Heroism",
            "Jump",
            "Purify Food and Drink",
            "Silent Image",
            "Tenser's Floating Disk",
            "Unseen Servant",
            "Wrathful Smite",
        ],
    )
    def test_utility_spell_resolves_cleanly(self, name):
        spell = _spell(name)
        effect = resolve_spell_effect(
            spell=spell, caster_level=3, proficiency_bonus=2, casting_mod=4,
        )
        assert effect.damage == 0 and effect.healing == 0
        assert "takes effect" in effect.description
