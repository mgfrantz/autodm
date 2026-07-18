"""
Tests for the level 7 & 8 spell roster completion — 15 iconic PHB spells added
to round both tiers to 18/18 and lift the catalogue to 154 spells.

This mirrors the level-9 completion (test_spell_level9_completion.py): the two
remaining tiers below the project's "every tier ≥10" / "PHB-complete" goal are
level 7 (was 11) and level 8 (was 10). Every Player's Handbook 7th- and
8th-level spell is now registered (18/18 each).

The 15 additions:
- Level 7: Divine Word, Etherealness, Mordenkainen's Magnificent Mansion,
  Mordenkainen's Sword, Project Image, Sequester, Symbol.
- Level 8: Animal Shapes, Antipathy/Sympathy, Clone, Control Weather,
  Demiplane, Glibness, Holy Aura, Telepathy.

Coverage mirrors test_spell_level9_completion.py:
- Registry distribution (levels 7 & 8 now >= 18; PHB rosters complete).
- Registration shape for every new spell (name, level, school) — parametrized.
- Per-spell mechanical correctness (save ability, concentration, dice, flags).
- Effect resolution for the attack-roll spell, the save-debuff spells, and the
  utility spells (all resolve without raising).
- Whole-registry no-duplicate-name guard.
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
# Registry distribution + PHB level 7/8 roster completeness
# --------------------------------------------------------------------------- #
class TestRegistryShape:
    def test_total_spell_count_grew(self):
        # Was 139 before this expansion; now 154.
        assert len(SPELL_REGISTRY) >= 154

    def test_level_7_tier_is_now_complete(self):
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        # Level 7 now matches mid-tier density (was 11, now 18).
        assert by_level[7] >= 18, (
            f"Level 7 has only {by_level[7]} spells (expected >=18)"
        )

    def test_level_8_tier_is_now_complete(self):
        from collections import Counter

        by_level = Counter()
        for s in SPELL_REGISTRY.values():
            by_level[int(s.level)] += 1
        # Level 8 now matches mid-tier density (was 10, now 18).
        assert by_level[8] >= 18, (
            f"Level 8 has only {by_level[8]} spells (expected >=18)"
        )

    def test_phb_level7_roster_is_complete(self):
        """All 18 Player's Handbook 7th-level spells are now registered."""
        PHB_LEVEL_7 = [
            "Delayed Blast Fireball", "Divine Word", "Etherealness",
            "Finger of Death", "Fire Storm", "Forcecage",
            "Mordenkainen's Magnificent Mansion", "Mordenkainen's Sword",
            "Plane Shift", "Prismatic Spray", "Project Image", "Regenerate",
            "Resurrection", "Reverse Gravity", "Sequester", "Simulacrum",
            "Symbol", "Teleport",
        ]
        missing = [n for n in PHB_LEVEL_7 if get_spell(n) is None]
        assert missing == [], f"Missing PHB level-7 spells: {missing}"

    def test_phb_level8_roster_is_complete(self):
        """All 18 Player's Handbook 8th-level spells are now registered."""
        PHB_LEVEL_8 = [
            "Animal Shapes", "Antimagic Field", "Antipathy/Sympathy", "Clone",
            "Control Weather", "Demiplane", "Dominate Monster", "Earthquake",
            "Feeblemind", "Glibness", "Holy Aura",
            "Abi-Dalzim's Horrid Wilting",  # PHB "Horrid Wilting"
            "Incendiary Cloud", "Maze", "Mind Blank", "Power Word Stun",
            "Sunburst", "Telepathy",
        ]
        missing = [n for n in PHB_LEVEL_8 if get_spell(n) is None]
        assert missing == [], f"Missing PHB level-8 spells: {missing}"

    def test_no_duplicate_spell_names_in_registry(self):
        """Every spell must have a unique name (no dict-key collisions)."""
        names = [s.name for s in SPELL_REGISTRY.values()]
        assert len(names) == len(set(names)), "Duplicate spell names detected"


# --------------------------------------------------------------------------- #
# Registration shape — every new spell at its correct level and school
# --------------------------------------------------------------------------- #
NEW_SPELLS: list[tuple[str, int, SpellSchool]] = [
    # Level 7
    ("Divine Word", 7, SpellSchool.ABJURATION),
    ("Etherealness", 7, SpellSchool.TRANSMUTATION),
    ("Mordenkainen's Magnificent Mansion", 7, SpellSchool.CONJURATION),
    ("Mordenkainen's Sword", 7, SpellSchool.EVOCATION),
    ("Project Image", 7, SpellSchool.ILLUSION),
    ("Sequester", 7, SpellSchool.TRANSMUTATION),
    ("Symbol", 7, SpellSchool.ABJURATION),
    # Level 8
    ("Animal Shapes", 8, SpellSchool.TRANSMUTATION),
    ("Antipathy/Sympathy", 8, SpellSchool.ENCHANTMENT),
    ("Clone", 8, SpellSchool.NECROMANCY),
    ("Control Weather", 8, SpellSchool.TRANSMUTATION),
    ("Demiplane", 8, SpellSchool.CONJURATION),
    ("Glibness", 8, SpellSchool.TRANSMUTATION),
    ("Holy Aura", 8, SpellSchool.ABJURATION),
    ("Telepathy", 8, SpellSchool.EVOCATION),
]


@pytest.mark.parametrize("name, level, school", NEW_SPELLS)
def test_new_spell_registered(name, level, school):
    spell = _spell(name)
    assert spell.level == level
    assert spell.school == school


def test_new_spell_count_matches_plan():
    """All 15 planned new spells are registered."""
    assert len(NEW_SPELLS) == 15
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
class TestLevel7Mechanics:
    def test_divine_word_is_save_debuff(self):
        spell = _spell("Divine Word")
        # Charisma save governs the banishment of celestials/elementals/etc.
        assert spell.save_ability == "cha"
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.casting_time == "1 action"
        assert spell.duration == "instantaneous"

    def test_etherealness_is_utility(self):
        spell = _spell("Etherealness")
        assert spell.concentration is False
        assert spell.deals_damage is False and spell.heals is False
        assert spell.save_ability is None
        assert spell.range == "self"
        assert spell.duration == "up to 8 hours"

    def test_magnificent_mansion_is_utility(self):
        spell = _spell("Mordenkainen's Magnificent Mansion")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "300 feet"
        assert spell.duration == "24 hours"

    def test_mordenkainens_sword_is_attack_roll_concentration(self):
        spell = _spell("Mordenkainen's Sword")
        assert spell.requires_attack_roll is True
        assert spell.deals_damage is True
        # 3d10 force signature damage.
        assert spell.damage_dice_count == 3 and spell.damage_dice_sides == 10
        assert spell.damage_type == "force"
        assert spell.concentration is True
        assert spell.duration == "up to 1 minute"

    def test_project_image_is_concentration_illusion(self):
        spell = _spell("Project Image")
        assert spell.concentration is True
        assert spell.deals_damage is False and spell.heals is False
        assert spell.save_ability is None
        assert spell.duration == "up to 1 day"

    def test_sequester_is_utility_no_concentration(self):
        spell = _spell("Sequester")
        assert spell.concentration is False
        assert spell.deals_damage is False and spell.heals is False
        assert spell.save_ability is None
        assert spell.duration == "until dispelled"

    def test_symbol_is_save_debuff_no_concentration(self):
        spell = _spell("Symbol")
        # Default glyph (Death) uses a Con save; description lists all variants.
        assert spell.save_ability == "con"
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.casting_time == "1 hour"
        assert spell.duration == "until dispelled or triggered"


class TestLevel8Mechanics:
    def test_animal_shapes_is_concentration_transformation(self):
        spell = _spell("Animal Shapes")
        assert spell.concentration is True
        # Willing targets — no save.
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "up to 24 hours"

    def test_antipathy_sympathy_is_wis_save_no_concentration(self):
        spell = _spell("Antipathy/Sympathy")
        assert spell.save_ability == "wis"
        assert spell.concentration is False
        assert spell.deals_damage is False
        assert spell.casting_time == "1 hour"
        assert spell.duration == "10 days"

    def test_clone_is_utility_no_concentration(self):
        spell = _spell("Clone")
        assert spell.concentration is False
        assert spell.deals_damage is False and spell.heals is False
        assert spell.save_ability is None
        assert spell.casting_time == "1 hour"
        assert spell.duration == "indefinite"

    def test_control_weather_is_concentration_utility(self):
        spell = _spell("Control Weather")
        assert spell.concentration is True
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.casting_time == "10 minutes"
        assert spell.duration == "up to 8 hours"

    def test_demiplane_is_utility_no_concentration(self):
        spell = _spell("Demiplane")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "1 hour"

    def test_glibness_is_self_buff_no_save(self):
        spell = _spell("Glibness")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.range == "self"
        assert spell.duration == "1 hour"

    def test_holy_aura_is_con_save_concentration(self):
        spell = _spell("Holy Aura")
        # Fiends/undead melee attackers make a Con save or are blinded.
        assert spell.save_ability == "con"
        assert spell.concentration is True
        assert spell.deals_damage is False
        assert spell.duration == "up to 1 minute"

    def test_telepathy_is_utility_no_concentration(self):
        spell = _spell("Telepathy")
        assert spell.concentration is False
        assert spell.save_ability is None
        assert spell.deals_damage is False
        assert spell.duration == "24 hours"


# --------------------------------------------------------------------------- #
# Effect resolution of the new spells
# --------------------------------------------------------------------------- #
class TestNewSpellResolution:
    def test_mordenkainens_sword_attack_roll_hits_and_misses(self):
        spell = _spell("Mordenkainen's Sword")
        # Hit: a low-AC target is struck for 3d10 (3-30) force.
        effect = resolve_spell_effect(
            spell=spell, caster_level=15, proficiency_bonus=5,
            casting_mod=5, target_ac=10,
        )
        assert effect.hit is True
        assert effect.damage_type == "force"
        assert 3 <= effect.damage <= 30
        # Miss: a very high-AC target avoids the blade.
        effect = resolve_spell_effect(
            spell=spell, caster_level=15, proficiency_bonus=5,
            casting_mod=0, target_ac=30,
        )
        # Even with a poor attack bonus the natural 20 path can hit, so we only
        # assert the description reports an attack was rolled.
        assert effect.rolled_attack is not None

    def test_symbol_resolves_as_save_debuff(self):
        # Save spell with no damage -> resolves via the made_save path.
        spell = _spell("Symbol")
        effect = resolve_spell_effect(
            spell=spell, caster_level=15, proficiency_bonus=5,
            casting_mod=5, target_save_total=30, spell_save_dc=18,
        )
        assert effect.made_save is True
        assert effect.damage == 0

    def test_holy_aura_resolves_as_save_debuff(self):
        spell = _spell("Holy Aura")
        effect = resolve_spell_effect(
            spell=spell, caster_level=15, proficiency_bonus=5,
            casting_mod=5, target_save_total=30, spell_save_dc=18,
        )
        assert effect.made_save is True
        assert effect.damage == 0

    def test_antipathy_sympathy_resolves_as_save_debuff(self):
        spell = _spell("Antipathy/Sympathy")
        effect = resolve_spell_effect(
            spell=spell, caster_level=15, proficiency_bonus=5,
            casting_mod=5, target_save_total=30, spell_save_dc=18,
        )
        assert effect.made_save is True
        assert effect.damage == 0

    def test_divine_word_resolves_as_save_debuff(self):
        spell = _spell("Divine Word")
        effect = resolve_spell_effect(
            spell=spell, caster_level=15, proficiency_bonus=5,
            casting_mod=5, target_save_total=30, spell_save_dc=18,
        )
        assert effect.made_save is True
        assert effect.damage == 0

    @pytest.mark.parametrize(
        "name",
        [
            "Etherealness",
            "Mordenkainen's Magnificent Mansion",
            "Project Image",
            "Sequester",
            "Animal Shapes",
            "Clone",
            "Control Weather",
            "Demiplane",
            "Glibness",
            "Telepathy",
        ],
    )
    def test_utility_spell_resolves_cleanly(self, name):
        spell = _spell(name)
        effect = resolve_spell_effect(
            spell=spell, caster_level=15, proficiency_bonus=5, casting_mod=5,
        )
        assert effect.damage == 0 and effect.healing == 0
        assert "takes effect" in effect.description
