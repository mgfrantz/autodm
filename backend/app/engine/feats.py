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
    requires_race: list[str] | None = None        # XGE race feats; char must match one


def _matches_race(race: str | None, required_races: list[str]) -> bool:
    """Whether a character's ``race`` satisfies one of ``required_races``.

    Matching is case-insensitive and tolerant of subraces / multi-word race
    names: a required race matches if it equals the character's race exactly
    or appears as a substring of it. This lets ``["elf"]`` match ``"High Elf"``
    and ``"Half-Elf"`` (both eligible for *Elven Accuracy*), while
    ``["wood elf"]`` only matches Wood Elves (for *Wood Elf Magic*).
    """
    if not race:
        return False
    r = race.lower().strip()
    for req in required_races:
        req_l = req.lower().strip()
        if r == req_l or req_l in r:
            return True
    return False


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
    race: str | None = None,
) -> PrerequisiteCheck:
    """Check whether a character meets a feat's prerequisites.

    ``classes`` maps class name -> level (multiclass-safe). ``race`` is the
    character's race string (e.g. ``"High Elf"``, ``"Half-Orc"``). The check
    verifies minimum level, minimum ability scores, caster status, class
    membership, armor proficiency, and race as configured on the feat.
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

    if pre.requires_race:
        if not _matches_race(race, pre.requires_race):
            missing["requires_race"] = pre.requires_race

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
        if "requires_race" in missing:
            parts.append("race: " + "/".join(missing["requires_race"]))
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
        "requires_race": list(pre.requires_race) if pre.requires_race else None,
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


# --- PHB general feats (expanded registry) -----------------------------------

_register(Feat(
    name="Actor",
    description=(
        "Increase your Charisma by 1. You have advantage on Charisma "
        "(Deception) and Charisma (Performance) checks when trying to pass "
        "yourself off as a different person. You can mimic the speech of "
        "another person or the sounds made by a creature, and others have "
        "disadvantage on Insight checks against your disguise."
    ),
    ability_bonus_choices=["charisma"],
    combat_modifiers={
        "skill_advantage": ["deception", "performance"],
        "insight_disadvantage_vs_disguise": True,
    },
    notes=["advantage on Deception/Performance when impersonating", "mimic sounds"],
))

_register(Feat(
    name="Charger",
    description=(
        "When you use your action to Dash, you can use a bonus action to make "
        "one melee weapon attack or shove a creature. If you move at least 10 "
        "feet in a straight line immediately before taking this bonus action, "
        "you gain a +5 bonus to the attack's damage roll (if you chose to "
        "attack and not shove), or you have advantage on the shove (if you "
        "chose to shove and not attack)."
    ),
    combat_modifiers={
        "dash_bonus_action_attack": True,
        "straight_line_bonus": {"damage_bonus": 5, "min_distance_ft": 10},
    },
    notes=["bonus-action melee/shove after Dash", "+5 damage after 10 ft straight charge"],
))

_register(Feat(
    name="Durable",
    description=(
        "Increase your Constitution by 1. When you roll a Hit Die to regain "
        "hit points, the minimum number of hit points you regain from the roll "
        "equals twice your Constitution modifier (minimum 2)."
    ),
    ability_bonus_choices=["constitution"],
    combat_modifiers={"hit_die_minimum": "twice_con_mod_minimum_2"},
    notes=["Hit Die healing minimum = 2 × CON mod"],
))

_register(Feat(
    name="Elemental Adept",
    description=(
        "Choose one damage type: acid, cold, fire, lightning, poison, or "
        "thunder. Spells you cast of that type ignore resistance to that "
        "damage type, and when you roll damage for a spell of that type, you "
        "can treat any 1 on a damage die as a 2. (Requires the ability to "
        "cast at least one spell.)"
    ),
    combat_modifiers={
        "ignore_resistance": ["chosen_element"],
        "treat_ones_as_twos": True,
        "element_choices": ["acid", "cold", "fire", "lightning", "poison", "thunder"],
    },
    prerequisite=FeatPrerequisite(requires_caster=True),
    source="Player's Handbook",
))

_register(Feat(
    name="Grappler",
    description=(
        "You have advantage on attack rolls against a creature you are "
        "grappling. You can use your action to try to pin a creature grappled "
        "by you; to do so, make another grapple check. If you succeed, you "
        "and the creature are both restrained until the grapple ends."
    ),
    combat_modifiers={
        "advantage_vs_grappled": True,
        "pin_action": "both_restrained",
    },
    prerequisite=FeatPrerequisite(min_abilities={"strength": 13}),
    notes=["advantage vs grappled targets", "pin = both restrained"],
))

_register(Feat(
    name="Inspiring Leader",
    description=(
        "You can spend 10 minutes inspiring your companions, shoring up their "
        "resolve to fight. When you do so, choose up to six friendly creatures "
        "(which can include yourself) within 30 feet of you who can perceive "
        "you. Each gains temporary hit points equal to your level + your "
        "Charisma modifier. A creature can't gain temporary HP this way more "
        "than once per short rest. (Requires Charisma 13.)"
    ),
    combat_modifiers={
        "temp_hp_ritual": {"duration": "10 min", "targets": 6, "formula": "level + cha_mod"},
    },
    prerequisite=FeatPrerequisite(min_abilities={"charisma": 13}),
    notes=["temp HP = level + CHA mod to up to 6 allies"],
))

_register(Feat(
    name="Lightly Armored",
    description=(
        "Increase your Strength or Dexterity by 1 and gain proficiency with "
        "light armor and shields."
    ),
    ability_bonus_choices=["strength", "dexterity"],
    skill_proficiencies=["light armor", "shields"],
))

_register(Feat(
    name="Linguist",
    description=(
        "Increase your Intelligence by 1. You learn three languages of your "
        "choice. You can ably create written ciphers; others can't decipher a "
        "code you create unless you teach them or they succeed on an "
        "Intelligence check (DC = 8 + your proficiency bonus + your Int mod)."
    ),
    ability_bonus_choices=["intelligence"],
    skill_proficiencies=["3 languages (player choice)"],
    combat_modifiers={"cipher_creation_dc": "8 + prof + int_mod"},
    notes=["learn 3 languages", "create ciphers"],
))

_register(Feat(
    name="Magic Initiate",
    description=(
        "Choose a class: bard, cleric, druid, sorcerer, warlock, or wizard. "
        "You learn two cantrips of your choice from that class's spell list, "
        "and one 1st-level spell from that list. You can cast the 1st-level "
        "spell once at its lowest level without expending a spell slot, and "
        "you must finish a long rest before you can cast it this way again. "
        "Your spellcasting ability for these spells is that class's."
    ),
    combat_modifiers={
        "learn_cantrips": 2,
        "learn_spell": {"level": 1, "casts_per_long_rest": 1},
        "spell_class_choices": ["bard", "cleric", "druid", "sorcerer", "warlock", "wizard"],
    },
    notes=["2 cantrips + 1 1st-level spell from a chosen class"],
))

_register(Feat(
    name="Martial Adept",
    description=(
        "You learn two maneuvers of your choice from among those available to "
        "the Battle Master archetype. If a maneuver requires a saving throw, "
        "the DC is 8 + your proficiency bonus + your Strength or Dexterity "
        "modifier. You gain one superiority die (a d6), which is expended when "
        "you use a maneuver; you regain all expended superiority dice after a "
        "short or long rest."
    ),
    combat_modifiers={
        "maneuvers_learned": 2,
        "superiority_dice": {"count": 1, "sides": 6, "refresh": "short_rest"},
        "maneuver_save_dc": "8 + prof + str_or_dex_mod",
    },
    notes=["2 Battle Master maneuvers", "1 superiority die (d6) per short rest"],
))

_register(Feat(
    name="Medium Armor Master",
    description=(
        "Increase your Strength or Dexterity by 1. While wearing medium "
        "armor, you can add 3 (rather than 2) to your AC if you have a "
        "Dexterity of 16 or higher, and you don't have disadvantage on "
        "Stealth checks. (Requires medium armor proficiency.)"
    ),
    ability_bonus_choices=["strength", "dexterity"],
    combat_modifiers={
        "medium_armor_max_dex": 3,
        "no_stealth_disadvantage_medium_armor": True,
    },
    prerequisite=FeatPrerequisite(requires_armor_proficiency="medium"),
    notes=["+3 Dex to AC in medium armor (if Dex 16+)", "no stealth disadvantage in medium armor"],
))

_register(Feat(
    name="Mounted Combatant",
    description=(
        "While mounted and not incapacitated, you have advantage on melee "
        "attack rolls against unmounted creatures smaller than your mount. You "
        "can force an attack targeted at your mount to target you instead. If "
        "your mount is subjected to an effect that allows a Dexterity saving "
        "throw for half damage, it takes no damage on a success and half "
        "damage on a failure."
    ),
    combat_modifiers={
        "advantage_vs_unmounted_smaller": True,
        "redirect_attack_to_rider": True,
        "mount_evasion": True,
    },
    notes=["advantage vs unmounted smaller foes", "redirect attacks to self", "mount evasion"],
))

_register(Feat(
    name="Savage Attacker",
    description=(
        "Once per turn when you roll damage for a melee weapon attack, you "
        "can reroll the weapon's damage dice and use either total."
    ),
    combat_modifiers={"reroll_weapon_damage": {"per_turn": 1, "use_higher": True}},
    notes=["reroll melee weapon damage once per turn, keep higher"],
))

_register(Feat(
    name="Shield Master",
    description=(
        "You use shields not just for protection but also for offense. If you "
        "take the Attack action on your turn, you can use a bonus action to "
        "try to shove a creature with your shield. You don't suffer "
        "disadvantage on an attack roll as a result of the target being "
        "behind cover. When you are subjected to an effect that lets you make "
        "a Dexterity saving throw to take half damage, you can use your "
        "reaction to add your shield's AC bonus to the save."
    ),
    combat_modifiers={
        "bonus_action_shield_shove": True,
        "no_disadvantage_vs_cover": True,
        "reaction_shield_ac_to_dex_save": True,
    },
    notes=["bonus-action shove with shield", "add shield AC to Dex saves as reaction"],
))

_register(Feat(
    name="Skulker",
    description=(
        "You can try to hide when you are lightly obscured from the creature "
        "from which you are hiding. When you are hidden, dim light doesn't "
        "impose disadvantage on your Wisdom (Perception) checks. You can "
        "make ranged attacks without disadvantage when hidden in dim light. "
        "If you miss with a ranged weapon attack while hidden, the attack "
        "doesn't reveal your position."
    ),
    combat_modifiers={
        "hide_when_lightly_obscured": True,
        "no_dim_light_perception_disadvantage": True,
        "no_disadvantage_hidden_ranged_dim_light": True,
        "miss_doesnt_reveal_position": True,
    },
    notes=["hide when lightly obscured", "missed ranged attacks don't reveal position"],
))

_register(Feat(
    name="Weapon Master",
    description=(
        "Increase your Strength or Dexterity by 1. You gain proficiency with "
        "four weapons of your choice, each of which must be a melee or ranged "
        "weapon."
    ),
    ability_bonus_choices=["strength", "dexterity"],
    skill_proficiencies=["4 weapons (player choice)"],
))


# --- Xanathar's Guide race-specific feats ------------------------------------
# These feats require a specific race (or a set of races), gated by the
# ``requires_race`` prerequisite. Source: Xanathar's Guide to Everything.

_register(Feat(
    name="Bountiful Luck",
    description=(
        "When an ally you can see within 30 feet of you rolls a 1 on the d20 "
        "for an attack roll, an ability check, or a saving throw, you can use "
        "your reaction to allow the ally to reroll the die. The ally must use "
        "the new roll. (Halfling.)"
    ),
    combat_modifiers={
        "reaction_reroll_ally_nat1": {"range_ft": 30, "must_use_new": True},
    },
    prerequisite=FeatPrerequisite(requires_race=["halfling"]),
    source="Xanathar's Guide to Everything",
))

_register(Feat(
    name="Dragon Fear",
    description=(
        "Increase your Strength, Constitution, or Charisma by 1. When you "
        "take the Attack action, you can replace one attack with a fearsome "
        "roar; each creature of your choice within 30 ft that can hear you "
        "must make a Wisdom saving throw (DC 8 + prof + Cha mod) or become "
        "frightened until the end of your next turn. (Dragonborn.)"
    ),
    ability_bonus_choices=["strength", "constitution", "charisma"],
    combat_modifiers={
        "fear_roar": {"range_ft": 30, "save": "wisdom", "condition": "frightened"},
        "save_dc": "8 + prof + cha_mod",
    },
    prerequisite=FeatPrerequisite(requires_race=["dragonborn"]),
    source="Xanathar's Guide to Everything",
))

_register(Feat(
    name="Dragon Hide",
    description=(
        "Increase your Strength, Constitution, or Charisma by 1. Your scales "
        "become tougher; your AC equals 13 + Dex mod when not wearing armor "
        "or a shield. You can grow retractile claws as natural weapons "
        "(1d6 + Str slashing). You can use a reaction to deal your breath "
        "weapon damage to a melee attacker. (Dragonborn.)"
    ),
    ability_bonus_choices=["strength", "constitution", "charisma"],
    combat_modifiers={
        "natural_armor": "13 + dex_mod",
        "natural_weapon_claws": {"dice_count": 1, "dice_sides": 6, "ability": "strength"},
        "reaction_breath_damage": True,
    },
    prerequisite=FeatPrerequisite(requires_race=["dragonborn"]),
    source="Xanathar's Guide to Everything",
))

_register(Feat(
    name="Dwarven Fortitude",
    description=(
        "Increase your Constitution by 1. You have advantage on saving throws "
        "against poison, and you have resistance against poison damage. When "
        "you take the Dodge action in combat, you can spend one Hit Die to "
        "recover hit points. (Dwarf.)"
    ),
    ability_bonus_choices=["constitution"],
    combat_modifiers={
        "dodge_spend_hit_die": True,
        "poison_save_advantage": True,
        "poison_damage_resistance": True,
    },
    prerequisite=FeatPrerequisite(requires_race=["dwarf"]),
    source="Xanathar's Guide to Everything",
))

_register(Feat(
    name="Elven Accuracy",
    description=(
        "Increase your Dexterity, Intelligence, Wisdom, or Charisma by 1. "
        "Whenever you have advantage on an attack roll using Dexterity, "
        "Intelligence, Wisdom, or Charisma, you can reroll one of the dice "
        "once. (Elf or half-elf.)"
    ),
    ability_bonus_choices=["dexterity", "intelligence", "wisdom", "charisma"],
    combat_modifiers={
        "reroll_one_advantage_die": True,
        "applicable_abilities": ["dexterity", "intelligence", "wisdom", "charisma"],
    },
    prerequisite=FeatPrerequisite(requires_race=["elf", "half-elf"]),
    source="Xanathar's Guide to Everything",
))

_register(Feat(
    name="Fade Away",
    description=(
        "Increase your Dexterity or Intelligence by 1. When you take damage, "
        "you can use your reaction to turn invisible and teleport up to 60 "
        "feet to an unoccupied space. You remain invisible until the end of "
        "your next turn or until you attack, cast a spell, or deal damage. "
        "Once you use this ability, you can't use it again until you finish a "
        "short or long rest. (Gnome.)"
    ),
    ability_bonus_choices=["dexterity", "intelligence"],
    combat_modifiers={
        "reaction_invisible_teleport": {"range_ft": 60, "refresh": "short_rest"},
        "invisible_until": "end_of_next_turn_or_action",
    },
    prerequisite=FeatPrerequisite(requires_race=["gnome"]),
    source="Xanathar's Guide to Everything",
))

_register(Feat(
    name="Fey Teleportation",
    description=(
        "Increase your Intelligence or Charisma by 1. You learn the *misty "
        "step* spell and can cast it once without expending a spell slot; you "
        "regain the ability to cast it this way after a short or long rest. "
        "Intelligence is your spellcasting ability for it. You also learn "
        "one language of your choice. (High elf.)"
    ),
    ability_bonus_choices=["intelligence", "charisma"],
    skill_proficiencies=["1 language (player choice)"],
    combat_modifiers={
        "learn_spell": {"name": "misty step", "casts_per_short_rest": 1},
        "spellcasting_ability": "intelligence",
    },
    prerequisite=FeatPrerequisite(requires_race=["high elf", "elf"]),
    source="Xanathar's Guide to Everything",
))

_register(Feat(
    name="Flames of Phlegethos",
    description=(
        "Increase your Intelligence or Charisma by 1. When you roll fire "
        "damage for a spell you cast, you can reroll any 1 on the damage "
        "dice, but must use the new roll. When you cast a spell that deals "
        "fire damage, you can cause flames to wreathe you until the end of "
        "your next turn; a creature that hits you with a melee attack while "
        "these flames burn takes 1d4 fire damage. (Tiefling.)"
    ),
    ability_bonus_choices=["intelligence", "charisma"],
    combat_modifiers={
        "reroll_fire_damage_ones": True,
        "fire_wreathe_retaliation": {"dice_count": 1, "dice_sides": 4, "damage_type": "fire"},
    },
    prerequisite=FeatPrerequisite(requires_race=["tiefling"]),
    source="Xanathar's Guide to Everything",
))

_register(Feat(
    name="Infernal Constitution",
    description=(
        "Increase your Constitution by 1. You have resistance to cold and "
        "poison damage, and you have advantage on saving throws against being "
        "poisoned. (Tiefling.)"
    ),
    ability_bonus_choices=["constitution"],
    combat_modifiers={
        "damage_resistance": ["cold", "poison"],
        "poisoned_save_advantage": True,
    },
    prerequisite=FeatPrerequisite(requires_race=["tiefling"]),
    source="Xanathar's Guide to Everything",
))

_register(Feat(
    name="Orcish Fury",
    description=(
        "Increase your Strength or Constitution by 1. When you hit with a "
        "melee weapon attack, you can roll one of your weapon's damage dice "
        "an additional time and add it to the damage. You can use this once "
        "per short rest. When you use Relentless Endurance, you can also "
        "make a melee weapon attack as a reaction. (Half-orc.)"
    ),
    ability_bonus_choices=["strength", "constitution"],
    combat_modifiers={
        "extra_weapon_damage_die": {"per_short_rest": 1},
        "relentless_endurance_bonus_attack": True,
    },
    prerequisite=FeatPrerequisite(requires_race=["half-orc"]),
    source="Xanathar's Guide to Everything",
))

_register(Feat(
    name="Prodigy",
    description=(
        "Increase one ability score of your choice by 1. You gain proficiency "
        "in one skill, one tool, and one language of your choice. (Human, "
        "half-elf, or half-orc.)"
    ),
    ability_bonus_choices=list(VALID_ABILITIES),
    skill_proficiencies=["1 skill", "1 tool", "1 language"],
    prerequisite=FeatPrerequisite(requires_race=["human", "half-elf", "half-orc"]),
    source="Xanathar's Guide to Everything",
))

_register(Feat(
    name="Second Chance",
    description=(
        "Increase your Constitution, Dexterity, or Charisma by 1. When a "
        "creature you can see hits you with an attack roll, you can use your "
        "reaction to force that creature to reroll; you use the new roll. "
        "Once you use this ability, you can't use it again until you roll "
        "initiative or finish a short or long rest. (Halfling.)"
    ),
    ability_bonus_choices=["constitution", "dexterity", "charisma"],
    combat_modifiers={
        "reaction_force_reroll_attack": {"refresh": "initiative_or_rest", "must_use_new": True},
    },
    prerequisite=FeatPrerequisite(requires_race=["halfling"]),
    source="Xanathar's Guide to Everything",
))

_register(Feat(
    name="Squat Nimbleness",
    description=(
        "Increase your Strength or Dexterity by 1, and your walking speed "
        "increases by 5 feet. You gain proficiency in the Acrobatics or "
        "Athletics skill (your choice). You have advantage on any Strength "
        "(Athletics) or Dexterity (Acrobatics) check you make to escape from "
        "being grappled. (Dwarf.)"
    ),
    ability_bonus_choices=["strength", "dexterity"],
    speed_bonus=5,
    skill_proficiencies=["acrobatics or athletics (player choice)"],
    combat_modifiers={"escape_grapple_advantage": True},
    prerequisite=FeatPrerequisite(requires_race=["dwarf"]),
    source="Xanathar's Guide to Everything",
))

_register(Feat(
    name="Wood Elf Magic",
    description=(
        "You learn one cantrip and one 1st-level spell of your choice from "
        "the druid spell list. Wisdom is your spellcasting ability for them. "
        "You can cast the 1st-level spell once at its lowest level without "
        "expending a spell slot, regaining the ability after a long rest. "
        "(Wood elf.)"
    ),
    combat_modifiers={
        "learn_cantrip": 1,
        "learn_spell": {"level": 1, "casts_per_long_rest": 1, "list": "druid"},
        "spellcasting_ability": "wisdom",
    },
    prerequisite=FeatPrerequisite(requires_race=["wood elf"]),
    source="Xanathar's Guide to Everything",
))


# --- Tasha's Cauldron of Everything feats (TCoE p.79-91) --------------------
# 14 canonical feats from Tasha's Cauldron of Everything. Most are "half-feats"
# that grant a +1 to a chosen ability (the TCoE design philosophy: every feat
# gives *some* ability bump). They expose ``ability_bonus_choices`` where
# applicable and free-form ``combat_modifiers`` for the combat engine / DM.

_register(Feat(
    name="Chef",
    description=(
        "Increase your Constitution or Wisdom by 1. During a short or long "
        "rest, you can produce treats that grant temporary hit points. When "
        "you finish a long rest, you can end it early for one creature that "
        "also finished the rest; that creature can spend a Hit Die to regain "
        "hit points."
    ),
    ability_bonus_choices=["constitution", "wisdom"],
    combat_modifiers={
        "temp_hp_treats": {"during_rest": True, "refresh": "short_or_long_rest"},
        "short_rest_share_hit_die": True,
    },
    notes=[
        "craft treats during a rest that grant temporary hit points",
        "end a long rest early to let an ally spend a Hit Die",
    ],
    source="Tasha's Cauldron of Everything",
))

_register(Feat(
    name="Crusher",
    description=(
        "Increase your Strength or Constitution by 1. Once per turn, when you "
        "hit a creature with an attack that deals bludgeoning damage, you can "
        "move it 5 feet to an unoccupied space, provided the target is no more "
        "than one size larger than you. When you score a critical hit that "
        "deals bludgeoning damage to a creature, attack rolls against that "
        "creature have advantage until the start of your next turn."
    ),
    ability_bonus_choices=["strength", "constitution"],
    combat_modifiers={
        "bludgeoning_hit_push": {"feet": 5, "per_turn": 1, "size_limit": "one larger"},
        "crit_advantage_vs_target": {"damage_type": "bludgeoning", "duration": "start of next turn"},
    },
    notes=[
        "once per turn move target 5 ft on a bludgeoning hit",
        "bludgeoning crit grants advantage on attacks vs that target",
    ],
    source="Tasha's Cauldron of Everything",
))

_register(Feat(
    name="Eldritch Adept",
    description=(
        "Studying occult lore, you learn one Eldritch Invocation option of "
        "your choice from the warlock class. If the invocation has a "
        "prerequisite of any kind, you can choose that invocation only if "
        "you're a warlock and only if you meet the prerequisite. Whenever you "
        "gain a level, you can replace the invocation with another one. "
        "(Requires the ability to cast at least one spell.)"
    ),
    combat_modifiers={
        "learn_eldritch_invocation": 1,
        "change_on_level_up": True,
        "prerequisite_lock": "warlock-only invocations require warlock levels",
    },
    prerequisite=FeatPrerequisite(requires_caster=True),
    notes=["learn one Eldritch Invocation", "swap it whenever you gain a level"],
    source="Tasha's Cauldron of Everything",
))

_register(Feat(
    name="Fey Touched",
    description=(
        "Your exposure to the Feywild's magic has changed you. Increase your "
        "Intelligence, Wisdom, or Charisma by 1. You learn the Misty Step "
        "spell and one 1st-level spell of your choice from the divination or "
        "enchantment school. You can cast each of these spells once without "
        "expending a spell slot, and you regain the ability to do so when you "
        "finish a long rest. Your spellcasting ability for these spells is the "
        "ability increased by this feat."
    ),
    ability_bonus_choices=["intelligence", "wisdom", "charisma"],
    combat_modifiers={
        "learn_spell_fixed": {"name": "Misty Step", "level": 2, "casts_per_long_rest": 1},
        "learn_spell_choice": {
            "level": 1,
            "school": ["divination", "enchantment"],
            "casts_per_long_rest": 1,
        },
        "spellcasting_ability_choices": ["intelligence", "wisdom", "charisma"],
    },
    notes=[
        "learn Misty Step (once per long rest, no slot)",
        "learn a 1st-level divination or enchantment spell (once per long rest, no slot)",
    ],
    source="Tasha's Cauldron of Everything",
))

_register(Feat(
    name="Fighting Initiate",
    description=(
        "Your martial training has helped you develop a particular style of "
        "fighting. You adopt a style of fighting as your specialty. Choose a "
        "Fighting Style from the fighter class. You can't take the same "
        "Fighting Style option more than once. Whenever you gain a level, you "
        "can replace the style with a different one."
    ),
    combat_modifiers={
        "learn_fighting_style": 1,
        "style_choices": "fighter_list",
        "change_on_level_up": True,
    },
    notes=[
        "gain one Fighting Style from the fighter list",
        "swap it whenever you gain a level",
    ],
    source="Tasha's Cauldron of Everything",
))

_register(Feat(
    name="Gunner",
    description=(
        "Increase your Dexterity by 1. You gain proficiency with firearms. "
        "You ignore the loading property of firearms. Being within 5 feet of "
        "a hostile creature doesn't impose disadvantage on your ranged attack "
        "rolls with firearms."
    ),
    ability_bonus_choices=["dexterity"],
    skill_proficiencies=["firearms"],
    combat_modifiers={
        "ignore_loading_property": {"weapons": "firearms"},
        "ranged_no_disadvantage_in_melee": {"weapons": "firearms"},
    },
    notes=[
        "proficiency with firearms",
        "ignore the loading property of firearms",
        "no disadvantage on ranged firearm attacks in melee",
    ],
    source="Tasha's Cauldron of Everything",
))

_register(Feat(
    name="Metamagic Adept",
    description=(
        "You've learned how to exert your will on your spells to alter how "
        "they function. You learn two Metamagic options of your choice from "
        "the sorcerer class. You gain 2 sorcery points to spend on these "
        "options (refreshed when you finish a long rest). Whenever you gain a "
        "level, you can replace one of your Metamagic options with another "
        "one. (Requires sorcerer level 1+.)"
    ),
    combat_modifiers={
        "learn_metamagic": 2,
        "sorcery_points": {"amount": 2, "refresh": "long_rest"},
        "change_one_on_level_up": True,
    },
    prerequisite=FeatPrerequisite(requires_class="sorcerer"),
    notes=[
        "learn 2 Metamagic options from the sorcerer list",
        "gain 2 sorcery points (refresh on a long rest)",
    ],
    source="Tasha's Cauldron of Everything",
))

_register(Feat(
    name="Piercer",
    description=(
        "Increase your Strength, Dexterity, or Constitution by 1. Once per "
        "turn, when you hit a creature with an attack that deals piercing "
        "damage, you can reroll one of the attack's damage dice and use the "
        "higher roll. When you score a critical hit that deals piercing "
        "damage, you can roll one additional damage die when determining the "
        "extra damage for a critical hit."
    ),
    ability_bonus_choices=["strength", "dexterity", "constitution"],
    combat_modifiers={
        "reroll_damage_die": {"per_turn": 1, "damage_type": "piercing", "use_higher": True},
        "crit_extra_damage_die": {"damage_type": "piercing"},
    },
    notes=[
        "once per turn reroll a piercing damage die, keep higher",
        "piercing critical hits add one extra damage die",
    ],
    source="Tasha's Cauldron of Everything",
))

_register(Feat(
    name="Poisoner",
    description=(
        "You can prepare and deliver deadly poisons, gaining the following "
        "benefits: you can apply poison to a weapon or piece of ammunition as "
        "a bonus action instead of an action. Once per turn, when you cause "
        "a creature to take poison damage, you can also deal 2d8 poison "
        "damage to that creature. When you make a damage roll for the poison "
        "you applied with this feat, the poison's damage is 2d8. The DC for "
        "the saving throw against the poison is 8 + your proficiency bonus + "
        "your Intelligence modifier."
    ),
    combat_modifiers={
        "apply_poison_bonus_action": True,
        "bonus_poison_damage": {"dice": "2d8", "damage_type": "poison", "per_turn": 1},
        "poison_save_dc": "8 + prof + int_mod",
    },
    notes=[
        "apply poison as a bonus action",
        "2d8 poison damage once per turn (DC 8 + prof + Int)",
    ],
    source="Tasha's Cauldron of Everything",
))

_register(Feat(
    name="Shadow Touched",
    description=(
        "Your exposure to the Shadowfell's magic has changed you. Increase "
        "your Intelligence, Wisdom, or Charisma by 1. You learn the "
        "Invisibility spell and one 1st-level spell of your choice from the "
        "illusion or necromancy school. You can cast each of these spells "
        "once without expending a spell slot, and you regain the ability to "
        "do so when you finish a long rest. Your spellcasting ability for "
        "these spells is the ability increased by this feat."
    ),
    ability_bonus_choices=["intelligence", "wisdom", "charisma"],
    combat_modifiers={
        "learn_spell_fixed": {"name": "Invisibility", "level": 2, "casts_per_long_rest": 1},
        "learn_spell_choice": {
            "level": 1,
            "school": ["illusion", "necromancy"],
            "casts_per_long_rest": 1,
        },
        "spellcasting_ability_choices": ["intelligence", "wisdom", "charisma"],
    },
    notes=[
        "learn Invisibility (once per long rest, no slot)",
        "learn a 1st-level illusion or necromancy spell (once per long rest, no slot)",
    ],
    source="Tasha's Cauldron of Everything",
))

_register(Feat(
    name="Skill Expert",
    description=(
        "You have honed one ability. Choose one ability. Increase that "
        "ability by 1. You gain proficiency in one skill of your choice, and "
        "you gain expertise with that skill, which means your proficiency "
        "bonus is doubled for any ability check you make with it. The skill "
        "you choose must be one that isn't already benefiting from a feature, "
        "such as Expertise, that doubles your proficiency bonus."
    ),
    ability_bonus_choices=list(VALID_ABILITIES),
    skill_proficiencies=["1 skill (player choice)"],
    combat_modifiers={
        "expertise": {"count": 1, "applies_to": "chosen skill", "double_proficiency": True},
    },
    notes=[
        "+1 to one ability, proficiency in one skill",
        "expertise (double proficiency) in that skill",
    ],
    source="Tasha's Cauldron of Everything",
))

_register(Feat(
    name="Slasher",
    description=(
        "Increase your Strength or Dexterity by 1. Once per turn, when you "
        "hit a creature with an attack that deals slashing damage, you can "
        "reduce the speed of that creature by 10 feet until the start of "
        "your next turn. When you score a critical hit that deals slashing "
        "damage to a creature, you grievously wound it; until the start of "
        "your next turn, the target has disadvantage on all attack rolls."
    ),
    ability_bonus_choices=["strength", "dexterity"],
    combat_modifiers={
        "slashing_hit_speed_reduction": {"feet": 10, "per_turn": 1, "damage_type": "slashing", "duration": "start of next turn"},
        "crit_target_disadvantage": {"damage_type": "slashing", "duration": "start of next turn"},
    },
    notes=[
        "once per turn reduce target speed 10 ft on a slashing hit",
        "slashing crit gives the target disadvantage on attack rolls",
    ],
    source="Tasha's Cauldron of Everything",
))

_register(Feat(
    name="Telekinetic",
    description=(
        "You learn to move things with your mind. Increase your Intelligence, "
        "Wisdom, or Charisma by 1. You learn the Mage Hand cantrip, which "
        "doesn't require verbal or somatic components for you, and it can be "
        "cast as a bonus action. As a bonus action, you can try to "
        "telekinetically shove one creature you can see within 30 feet of "
        "you. The target must succeed on a Strength saving throw (DC 8 + "
        "your proficiency bonus + the ability modifier of the ability "
        "increased by this feat) or be moved 5 feet toward or away from you."
    ),
    ability_bonus_choices=["intelligence", "wisdom", "charisma"],
    combat_modifiers={
        "learn_cantrip_fixed": {"name": "Mage Hand", "no_verbal": True, "no_somatic": True, "bonus_action_cast": True},
        "telekinetic_shove": {
            "action": "bonus",
            "range_ft": 30,
            "save": "strength",
            "dc": "8 + prof + ability_mod",
            "push_pull_ft": 5,
        },
    },
    notes=[
        "learn Mage Hand (no verbal/somatic, bonus action)",
        "bonus-action shove: push or pull a creature 5 ft (Str save)",
    ],
    source="Tasha's Cauldron of Everything",
))

_register(Feat(
    name="Telepathic",
    description=(
        "You awaken the ability to mentally connect with others. Increase "
        "your Intelligence, Wisdom, or Charisma by 1. You can speak "
        "telepathically to any creature you can see within 60 feet of you. "
        "Your telepathic utterances are in a language you know, and the "
        "creature understands you only if it knows that language. As a bonus "
        "action, you can cast the Detect Thoughts spell, using the ability "
        "increased by this feat. You can cast it this way a number of times "
        "equal to your proficiency bonus, and you regain all expended uses "
        "when you finish a long rest."
    ),
    ability_bonus_choices=["intelligence", "wisdom", "charisma"],
    combat_modifiers={
        "telepathy": {"range_ft": 60, "shared_language_only": True},
        "cast_detect_thoughts": {
            "level": 2,
            "action": "bonus",
            "uses": "proficiency_bonus",
            "refresh": "long_rest",
            "dc": "8 + prof + ability_mod",
        },
    },
    notes=[
        "speak telepathically to creatures within 60 ft (shared language)",
        "bonus-action Detect Thoughts (proficiency-bonus uses per long rest)",
    ],
    source="Tasha's Cauldron of Everything",
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
    race: str | None = None,
) -> list[Feat]:
    """Feats a character could take right now.

    Filters out feats already known and feats whose prerequisites are not met.
    ``race`` is threaded through to :func:`check_prerequisites` so XGE
    race-specific feats are gated correctly.
    """
    known = {k.lower() for k in (known_feats or [])}
    out: list[Feat] = []
    for feat in list_feats():
        if feat.name.lower() in known:
            continue
        if check_prerequisites(feat, ability_scores, level, classes, race=race).met:
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
