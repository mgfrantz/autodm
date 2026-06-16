"""
Feat engine — DnD 5e feats as an alternative to Ability Score Improvements.

In 5e, whenever a class grants an Ability Score Improvement (ASI), the player may
instead choose a **feat**. Both options consume one ASI instance. This engine
models that choice:

- :class:`Feat` — a feat definition: description, prerequisites, and the
  mechanical *effects* it grants.
- A **feat registry** (~24 common feats) covering ability-boosting "half-feats"
  (Athlete, Resilient, ...), HP feats (Tough), derived-bonus feats (Alert,
  Mobile, Dual Wielder), saving-throw feats (Resilient), and combat-modifier
  feats (Sharpshooter, Great Weapon Master, ...) modeled as structured metadata
  for the combat engine / DM to read.
- :func:`check_prerequisites` — validate a character can take a feat.
- :func:`apply_feat` — compute the mechanical outcome (ability bumps, HP) so the
  API layer can persist it.

The engine is pure (no DB, no LLM) so it is trivially unit-testable. The API
layer feeds real character data in and persists the results.

Design notes
------------
- Feats that grant a ``+1`` to a chosen ability (e.g. Resilient, Athlete,
  Observant) expose ``ability_bonus_choices``; the caller passes the chosen
  ability to :func:`apply_feat`.
- Feats with fixed ability bumps (e.g. none currently — most are choices) use
  ``ability_bonus``.
- ``hp_per_level`` (Tough) increases max HP by ``hp_per_level * level`` and
  raises current HP by the same amount.
- ``combat_modifiers`` is free-form structured data (e.g.
  ``{"power_attack": {"attack_penalty": -5, "damage_bonus": 10}}``) that the
  combat engine / LLM DM can consult; it is not auto-applied to dice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.engine.leveling import clamp_score, MAX_ABILITY_SCORE, VALID_ABILITIES


# --------------------------------------------------------------------------- #
# Prerequisites                                                               #
# --------------------------------------------------------------------------- #

# Classes that can cast spells (used for "requires_caster" prerequisites).
# Mirrors the caster profile set in the spells engine.
CASTING_CLASSES: frozenset[str] = frozenset({
    "wizard", "sorcerer", "cleric", "druid", "bard",
    "warlock", "paladin", "ranger",
})

# Classes proficient with heavy armor by default (for Heavy Armor Master etc.).
HEAVY_ARMOR_CLASSES: frozenset[str] = frozenset({"fighter", "paladin", "cleric"})
# Classes proficient with medium armor by default.
MEDIUM_ARMOR_CLASSES: frozenset[str] = frozenset({
    "fighter", "paladin", "cleric", "ranger", "druid", "barbarian",
})
# Classes proficient with light armor by default (for Moderately Armored).
LIGHT_ARMOR_CLASSES: frozenset[str] = frozenset({
    "fighter", "paladin", "cleric", "ranger", "druid", "barbarian",
    "bard", "rogue", "warlock", "monk",
})


@dataclass
class FeatPrerequisite:
    """Requirements to take a feat.

    All fields are optional; a feat with no prerequisites can be taken by any
    character who has an ASI instance available.
    """
    min_level: int = 1
    min_abilities: dict[str, int] = field(default_factory=dict)
    requires_caster: bool = False                 # must have a casting class
    requires_class: str | None = None             # must have at least one level
    requires_armor_proficiency: str | None = None  # "heavy" | "medium" | "light"


def _has_armor_proficiency(
    classes: dict[str, int], armor_type: str
) -> bool:
    """Whether any of the character's classes grants the armor proficiency."""
    armor_type = armor_type.lower()
    names = {c.lower() for c in classes}
    if armor_type == "heavy":
        return bool(names & HEAVY_ARMOR_CLASSES)
    if armor_type == "medium":
        return bool(names & MEDIUM_ARMOR_CLASSES)
    if armor_type == "light":
        return bool(names & LIGHT_ARMOR_CLASSES)
    return False


@dataclass
class PrerequisiteCheck:
    """Result of validating feat prerequisites."""
    met: bool
    message: str
    missing: dict[str, Any] = field(default_factory=dict)


def check_prerequisites(
    feat: "Feat",
    ability_scores: dict[str, int],
    level: int,
    classes: dict[str, int],
) -> PrerequisiteCheck:
    """Check whether a character meets a feat's prerequisites.

    ``classes`` maps class name -> level (multiclass-safe). The check verifies
    minimum level, minimum ability scores, caster status, class membership, and
    armor proficiency as configured on the feat.
    """
    pre = feat.prerequisite
    if pre is None:
        return PrerequisiteCheck(True, f"{feat.name}: no prerequisites")

    names = {c.lower() for c in classes}
    missing: dict[str, Any] = {}

    if level < pre.min_level:
        missing["min_level"] = pre.min_level

    for ability, required in pre.min_abilities.items():
        if ability_scores.get(ability, 10) < required:
            missing.setdefault("min_abilities", {})[ability] = required

    if pre.requires_caster and not (names & CASTING_CLASSES):
        missing["requires_caster"] = True

    if pre.requires_class:
        if pre.requires_class.lower() not in names:
            missing["requires_class"] = pre.requires_class.lower()

    if pre.requires_armor_proficiency:
        if not _has_armor_proficiency(classes, pre.requires_armor_proficiency):
            missing["requires_armor_proficiency"] = pre.requires_armor_proficiency

    if missing:
        parts = []
        if "min_level" in missing:
            parts.append(f"level {missing['min_level']}+")
        if "min_abilities" in missing:
            parts.append(
                ", ".join(f"{a} {v}+" for a, v in missing["min_abilities"].items())
            )
        if "requires_caster" in missing:
            parts.append("spellcasting")
        if "requires_class" in missing:
            parts.append(f"{missing['requires_class']} class")
        if "requires_armor_proficiency" in missing:
            parts.append(f"{missing['requires_armor_proficiency']} armor proficiency")
        return PrerequisiteCheck(
            False,
            f"{feat.name} requires " + " and ".join(parts),
            missing=missing,
        )

    return PrerequisiteCheck(True, f"{feat.name}: prerequisites met")


# --------------------------------------------------------------------------- #
# Feat definition                                                             #
# --------------------------------------------------------------------------- #

@dataclass
class Feat:
    """A single DnD 5e feat.

    Mechanical effects live directly on the feat as typed fields so they can be
    auto-applied; free-form combat/utility modifiers live in ``combat_modifiers``
    for the combat engine / DM to consult.
    """
    name: str
    description: str

    # Ability bumps.
    ability_bonus: dict[str, int] = field(default_factory=dict)
    # If non-empty, the feat grants +1 to ONE ability from this list (player choice).
    ability_bonus_choices: list[str] = field(default_factory=list)

    # Derived mechanical effects.
    saving_throw_proficiency: str | None = None  # ability whose save is gained
    hp_per_level: int = 0          # Tough = 2
    initiative_bonus: int = 0      # Alert = 5
    speed_bonus: int = 0           # Mobile = 10
    ac_bonus: int = 0              # Dual Wielder-style unconditional AC
    skill_proficiencies: list[str] = field(default_factory=list)

    # Free-form metadata for the combat engine / DM (not auto-applied).
    combat_modifiers: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    prerequisite: FeatPrerequisite | None = None
    source: str = "Player's Handbook"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for API responses / persistence."""
        return {
            "name": self.name,
            "description": self.description,
            "ability_bonus": dict(self.ability_bonus),
            "ability_bonus_choices": list(self.ability_bonus_choices),
            "saving_throw_proficiency": self.saving_throw_proficiency,
            "hp_per_level": self.hp_per_level,
            "initiative_bonus": self.initiative_bonus,
            "speed_bonus": self.speed_bonus,
            "ac_bonus": self.ac_bonus,
            "skill_proficiencies": list(self.skill_proficiencies),
            "combat_modifiers": dict(self.combat_modifiers),
            "notes": list(self.notes),
            "prerequisite": _prerequisite_to_dict(self.prerequisite),
            "source": self.source,
        }


def _prerequisite_to_dict(pre: FeatPrerequisite | None) -> dict[str, Any] | None:
    if pre is None:
        return None
    return {
        "min_level": pre.min_level,
        "min_abilities": dict(pre.min_abilities),
        "requires_caster": pre.requires_caster,
        "requires_class": pre.requires_class,
        "requires_armor_proficiency": pre.requires_armor_proficiency,
    }


# --------------------------------------------------------------------------- #
# Feat registry                                                               #
# --------------------------------------------------------------------------- #

_POWER_ATTACK = {"power_attack": {"attack_penalty": -5, "damage_bonus": 10}}

_FEATS: dict[str, Feat] = {}


def _register(feat: Feat) -> Feat:
    """Register a feat (keyed by lowercased name). Returns the feat."""
    _FEATS[feat.name.lower()] = feat
    return feat


# --- Ability-boosting "half-feats" (grant a +1 to a chosen ability) ---------

_register(Feat(
    name="Athlete",
    description=(
        "Increase your Strength or Dexterity by 1. When prone, standing uses "
        "only 5 ft of movement. You can make a running long/high jump after "
        "moving only 5 ft on your turn."
    ),
    ability_bonus_choices=["strength", "dexterity"],
    notes=["stand from prone for 5 ft", "running jump after 5 ft of movement"],
))

_register(Feat(
    name="Keen Mind",
    description=(
        "Increase your Intelligence by 1. You always know which way is north, "
        "the number of hours left before sunrise/sunset, and can accurately "
        "recall anything you've seen or heard in the past month."
    ),
    ability_bonus_choices=["intelligence"],
    notes=["perfect sense of direction", "accurate memory of last month"],
))

_register(Feat(
    name="Observant",
    description=(
        "Increase your Intelligence or Wisdom by 1. Your passive Perception "
        "and Investigation increase by 5. You can read the lips of a creature "
        "you can see."
    ),
    ability_bonus_choices=["intelligence", "wisdom"],
    notes=["+5 passive Perception & Investigation", "lip reading"],
))

_register(Feat(
    name="Resilient",
    description=(
        "Increase an ability score of your choice by 1, and gain proficiency "
        "in saving throws using that ability."
    ),
    ability_bonus_choices=list(VALID_ABILITIES),
    notes=["proficiency in chosen ability's saving throw"],
))

_register(Feat(
    name="Tavern Brawler",
    description=(
        "Increase your Strength, Constitution, or Charisma by 1. You are "
        "proficient with improvised weapons and unarmed strikes. After hitting "
        "with one, you can attempt to grapple as a bonus action."
    ),
    ability_bonus_choices=["strength", "constitution", "charisma"],
    skill_proficiencies=["improvised weapons", "unarmed strikes"],
    notes=["grapple as bonus action after unarmed/improvised hit"],
))

_register(Feat(
    name="Heavily Armored",
    description=(
        "Increase your Strength by 1 and gain proficiency with heavy armor. "
        "(Requires medium armor proficiency.)"
    ),
    ability_bonus={"strength": 1},
    skill_proficiencies=["heavy armor"],
    prerequisite=FeatPrerequisite(requires_armor_proficiency="medium"),
))

_register(Feat(
    name="Heavy Armor Master",
    description=(
        "Increase your Strength by 1. While wearing heavy armor, you "
        "reduce bludgeoning, piercing, and slashing damage by 3. "
        "(Requires heavy armor proficiency.)"
    ),
    ability_bonus={"strength": 1},
    combat_modifiers={"damage_reduction_heavy_armor": {"damage_types": ["bludgeoning", "piercing", "slashing"], "amount": 3}},
    prerequisite=FeatPrerequisite(requires_armor_proficiency="heavy"),
))

_register(Feat(
    name="Moderately Armored",
    description=(
        "Increase your Strength or Dexterity by 1 and gain proficiency with "
        "medium armor and shields. (Requires light armor proficiency.)"
    ),
    ability_bonus_choices=["strength", "dexterity"],
    skill_proficiencies=["medium armor", "shields"],
    prerequisite=FeatPrerequisite(requires_armor_proficiency="light"),
))

# --- HP / survivability ------------------------------------------------------

_register(Feat(
    name="Tough",
    description=(
        "Your hit point maximum increases by 2 for every level you have "
        "attained, and increases by 2 again each time you gain a level."
    ),
    hp_per_level=2,
))

# --- Derived-bonus feats -----------------------------------------------------

_register(Feat(
    name="Alert",
    description=(
        "You gain a +5 bonus to initiative. You can't be surprised while "
        "conscious, and other creatures don't gain advantage on attack rolls "
        "against you as a result of being hidden from you."
    ),
    initiative_bonus=5,
    notes=["cannot be surprised while conscious", "no advantage from hidden foes"],
))

_register(Feat(
    name="Mobile",
    description=(
        "Your speed increases by 10 feet. When you use the Dash action, "
        "difficult terrain doesn't cost extra movement. You don't provoke "
        "opportunity attacks from creatures you've attacked this turn."
    ),
    speed_bonus=10,
    notes=["ignore difficult terrain when dashing", "no opportunity attacks from hit foes"],
))

_register(Feat(
    name="Dual Wielder",
    description=(
        "You gain a +1 bonus to AC while wielding two melee weapons. You can "
        "use two-weapon fighting with any one-handed melee weapons, even if "
        "they aren't light. You can draw or stow two weapons at once."
    ),
    ac_bonus=1,
    combat_modifiers={"two_weapon_any_one_handed": True},
    notes=["+1 AC while dual wielding", "draw/stow two weapons at once"],
))

# --- Combat feats (modeled as structured metadata) --------------------------

_register(Feat(
    name="Great Weapon Master",
    description=(
        "When you score a critical hit or reduce a creature to 0 HP with a "
        "melee weapon, you can make one melee weapon attack as a bonus action. "
        "Before making a melee attack with a heavy weapon, you can take a -5 "
        "penalty to the attack roll to add +10 to the damage."
    ),
    combat_modifiers={
        "bonus_action_attack_on_crit_or_kill": True,
        **_POWER_ATTACK,
    },
))

_register(Feat(
    name="Sharpshooter",
    description=(
        "Attacking at long range doesn't impose disadvantage, and your ranged "
        "attacks ignore half and three-quarters cover. Before making a ranged "
        "attack, you can take a -5 penalty to the attack roll to add +10 damage."
    ),
    combat_modifiers={
        "no_long_range_disadvantage": True,
        "ignore_cover": ["half", "three_quarters"],
        **_POWER_ATTACK,
    },
))

_register(Feat(
    name="Crossbow Expert",
    description=(
        "You ignore the loading quality of crossbows. Being within 5 ft of a "
        "hostile creature doesn't impose disadvantage on ranged attack rolls. "
        "When you attack with a one-handed weapon, you can fire a hand crossbow "
        "as a bonus action."
    ),
    combat_modifiers={
        "ignore_loading": True,
        "no_disadvantage_in_melee_ranged": True,
        "hand_crossbow_bonus_action": True,
    },
))

_register(Feat(
    name="Polearm Master",
    description=(
        "When you take the Attack action with a glaive, halberd, or quarterstaff, "
        "you can use a bonus action for an additional 1d4 damage attack. "
        "Other creatures provoke an opportunity attack when they enter your reach."
    ),
    combat_modifiers={
        "bonus_action_attack": {"dice_count": 1, "dice_sides": 4},
        "opportunity_attack_on_enter_reach": True,
    },
    prerequisite=FeatPrerequisite(),
))

_register(Feat(
    name="Sentinel",
    description=(
        "When you hit a creature with an opportunity attack, its speed drops to "
        "0. You make opportunity attacks without reaction limits, and can make "
        "a melee weapon attack as a reaction when a creature attacks an ally "
        "next to you."
    ),
    combat_modifiers={
        "stop_speed_on_opportunity_attack": True,
        "unlimited_opportunity_attacks": True,
        "reaction_attack_vs_ally_attackers": True,
    },
))

_register(Feat(
    name="Mage Slayer",
    description=(
        "When a creature within 5 ft casts a spell, you can use your reaction "
        "to make a melee attack. You have advantage on saving throws against "
        "spells cast by creatures within 5 ft. When you damage a concentrating "
        "caster, they have disadvantage on the concentration check."
    ),
    combat_modifiers={
        "reaction_attack_vs_caster": True,
        "advantage_saves_vs_nearby_spells": True,
        "concentration_disadvantage_on_hit": True,
    },
))

# --- Spellcaster feats -------------------------------------------------------

_register(Feat(
    name="War Caster",
    description=(
        "You have advantage on Constitution saving throws to maintain "
        "concentration when you take damage. You can perform somatic components "
        "even with weapons/shields in hand. You can cast a spell as an "
        "opportunity attack."
    ),
    combat_modifiers={
        "concentration_advantage_on_damage": True,
        "cast_with_occupied_hands": True,
        "spell_opportunity_attack": True,
    },
    prerequisite=FeatPrerequisite(requires_caster=True),
))

_register(Feat(
    name="Spell Sniper",
    description=(
        "When you cast a spell that requires an attack roll, its range is "
        "doubled. You ignore half and three-quarters cover, and learn one "
        "additional cantrip. (Requires the ability to cast at least one spell.)"
    ),
    combat_modifiers={
        "double_spell_attack_range": True,
        "ignore_cover": ["half", "three_quarters"],
    },
    prerequisite=FeatPrerequisite(requires_caster=True),
))

# --- Skill / utility feats ---------------------------------------------------

_register(Feat(
    name="Skilled",
    description=(
        "You gain proficiency in any combination of three skills or tools of "
        "your choice."
    ),
    skill_proficiencies=["3 skills or tools (player choice)"],
))

_register(Feat(
    name="Lucky",
    description=(
        "You have 3 luck points. You can spend one to roll an additional d20 "
        "when you attack, cast, or make a check/save, and choose which die to "
        "use. You can also spend one when a creature attacks you, forcing them "
        "to roll an additional d20. Points refresh on a long rest."
    ),
    combat_modifiers={"luck_points": 3, "luck_points_refresh": "long_rest"},
))

_register(Feat(
    name="Defensive Duelist",
    description=(
        "When attacked while wielding a finesse weapon, you can use your "
        "reaction to add your proficiency bonus to AC for that attack."
    ),
    combat_modifiers={"reaction_ac_vs_melee": "proficiency_bonus", "requires_finesse_weapon": True},
    prerequisite=FeatPrerequisite(min_level=1),
))


# --------------------------------------------------------------------------- #
# Registry access                                                             #
# --------------------------------------------------------------------------- #

def get_feat(name: str) -> Optional[Feat]:
    """Look up a feat by name (case-insensitive). Returns None if unknown."""
    return _FEATS.get(name.lower())


def list_feats() -> list[Feat]:
    """All registered feats, alphabetically by name."""
    return sorted(_FEATS.values(), key=lambda f: f.name.lower())


def list_feat_names() -> list[str]:
    """All registered feat names, alphabetically."""
    return sorted(f.name for f in _FEATS.values())


def list_available_feats(
    ability_scores: dict[str, int],
    level: int,
    classes: dict[str, int],
    known_feats: list[str] | None = None,
) -> list[Feat]:
    """Feats a character could take right now.

    Filters out feats already known and feats whose prerequisites are not met.
    """
    known = {k.lower() for k in (known_feats or [])}
    out: list[Feat] = []
    for feat in list_feats():
        if feat.name.lower() in known:
            continue
        if check_prerequisites(feat, ability_scores, level, classes).met:
            out.append(feat)
    return out


# --------------------------------------------------------------------------- #
# Applying a feat                                                             #
# --------------------------------------------------------------------------- #

@dataclass
class ApplyFeatResult:
    """Outcome of applying a feat to a character."""
    success: bool
    message: str
    feat_name: str = ""
    ability_changes: dict[str, int] = field(default_factory=dict)
    max_hp_change: int = 0
    current_hp_change: int = 0
    saving_throw_proficiency: str | None = None
    effects_applied: dict[str, Any] = field(default_factory=dict)


def apply_feat(
    feat: Feat,
    abilities: dict[str, int],
    level: int,
    max_hp: int,
    current_hp: int,
    chosen_ability: str | None = None,
) -> ApplyFeatResult:
    """Compute the mechanical effect of a character taking ``feat``.

    This is a **pure** function: it does not mutate the inputs. It returns an
    :class:`ApplyFeatResult` describing the ability bumps, HP changes, and other
    effects so the API layer can persist them.

    ``chosen_ability`` is required for choice feats (those with a non-empty
    ``ability_bonus_choices``) and must be one of the valid choices.

    HP changes (Tough's ``hp_per_level``) increase both max and current HP by
    ``hp_per_level * level`` (the feat is taken at ``level``, so prior levels
    are accounted for retroactively, matching 5e).
    """
    # Resolve the ability bump.
    bumps: dict[str, int] = dict(feat.ability_bonus)

    if feat.ability_bonus_choices:
        if chosen_ability is None:
            return ApplyFeatResult(
                False,
                f"{feat.name} requires choosing an ability to increase "
                f"(one of: {', '.join(feat.ability_bonus_choices)})",
                feat_name=feat.name,
            )
        chosen = chosen_ability.lower()
        if chosen not in feat.ability_bonus_choices:
            return ApplyFeatResult(
                False,
                f"{feat.name}: '{chosen_ability}' is not a valid choice "
                f"(choose from {', '.join(feat.ability_bonus_choices)})",
                feat_name=feat.name,
            )
        bumps[chosen] = bumps.get(chosen, 0) + 1

    # Clamp and detect over-cap (mirrors apply_asi behavior).
    new_scores = dict(abilities)
    applied_changes: dict[str, int] = {}
    for ability, amount in bumps.items():
        if ability not in VALID_ABILITIES:
            return ApplyFeatResult(
                False, f"{feat.name}: unknown ability '{ability}'", feat_name=feat.name
            )
        before = new_scores.get(ability, 10)
        after = clamp_score(before + amount)
        if after == before and amount > 0:
            return ApplyFeatResult(
                False,
                f"{feat.name}: {ability} is already at the cap ({MAX_ABILITY_SCORE})",
                feat_name=feat.name,
            )
        new_scores[ability] = after
        applied_changes[ability] = after - before

    # HP change (Tough).
    max_hp_change = feat.hp_per_level * max(1, level)
    # Tough increases current HP by the same amount (it raises your HP total).
    current_hp_change = max_hp_change

    # Build the effects summary for persistence / display.
    effects: dict[str, Any] = {}
    if feat.initiative_bonus:
        effects["initiative_bonus"] = feat.initiative_bonus
    if feat.speed_bonus:
        effects["speed_bonus"] = feat.speed_bonus
    if feat.ac_bonus:
        effects["ac_bonus"] = feat.ac_bonus
    if feat.skill_proficiencies:
        effects["skill_proficiencies"] = list(feat.skill_proficiencies)
    if feat.combat_modifiers:
        effects["combat_modifiers"] = dict(feat.combat_modifiers)
    if feat.notes:
        effects["notes"] = list(feat.notes)

    # For Resilient: saving throw proficiency is the chosen ability
    save_proficiency = feat.saving_throw_proficiency
    if feat.name == "Resilient" and chosen_ability:
        save_proficiency = chosen_ability.lower()
        # Add to effects for persistence
        effects["saving_throw_proficiency"] = save_proficiency
    # Add saving_throw_proficiency to effects if set by feat
    elif save_proficiency:
        effects["saving_throw_proficiency"] = save_proficiency

    parts = []
    if applied_changes:
        parts.append(
            "ability: " + ", ".join(f"{a} +{amt}" for a, amt in applied_changes.items())
        )
    if max_hp_change:
        parts.append(f"+{max_hp_change} HP")
    if save_proficiency:
        parts.append(f"{save_proficiency} save proficiency")
    if effects:
        parts.append(f"{len(effects)} effect(s)")
    summary = "; ".join(parts) if parts else "no mechanical effects tracked"

    return ApplyFeatResult(
        success=True,
        message=f"{feat.name} learned ({summary})",
        feat_name=feat.name,
        ability_changes=applied_changes,
        max_hp_change=max_hp_change,
        current_hp_change=current_hp_change,
        saving_throw_proficiency=save_proficiency,
        effects_applied=effects,
    )
