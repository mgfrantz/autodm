"""
Subclass engine — DnD 5e subclasses (archetypes / domains / origins / paths).

In 5e, every class gains a **subclass** at a class-specific level (1, 2, or 3).
The subclass defines the character's archetype and grants a progression of
features at set levels. Until now the engine surfaced the *choice point* (e.g.
``("fighter", 3): "Martial Archetype"``) but had no model of the subclasses
themselves, so the choice was flavour-only.

This engine models the subclass layer:

- :class:`Subclass` — a subclass definition: the parent class, the category
  name (e.g. "Martial Archetype", "Divine Domain"), a description, and the
  features it grants keyed by character level.
- :data:`SUBCLASS_REGISTRY` — a representative set of official subclasses
  (2–3 per core class) covering all 12 PHB classes.
- :func:`subclass_choice_level` — when a class picks its subclass (1/2/3).
- :func:`subclasses_for_class` / :func:`get_subclass` — registry lookups.
- :func:`can_choose_subclass` / :func:`validate_subclass_choice` — eligibility.
- :func:`features_at_level` / :func:`features_through_level` — feature
  progression for a chosen subclass.
- :func:`subclass_summary_for_dm` — a one-line DM-context helper.

The engine is pure (no DB, no LLM) so it is trivially unit-testable. The API
layer feeds real character data in and persists the choice.

Design notes
------------
- A subclass always belongs to exactly one parent class; multiclassed
  characters may hold one subclass per class they have levels in.
- Feature levels follow the 5e standard per choice tier:

  * chosen at level 1  → features at 1, 2, 6, 8, 10, 14, 17, 20 (cleric /
    sorcerer / warlock — some classes use 18 instead of 17)
  * chosen at level 2  → features at 2, 6, 10, 14 (druid / wizard)
  * chosen at level 3  → features at 3, 7, 15, 20 (most martial classes),
    with extra stops for some (e.g. rogue at 9/13/17, monk at 6/11/17)

  Each subclass records only the levels at which it actually grants a
  feature, so missing levels simply yield nothing.
- The registry is intentionally a *representative* (not exhaustive) subset of
  the official subclasses; it is structured so more can be appended freely.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
# Choice-level table                                                          #
# --------------------------------------------------------------------------- #

#: The character level at which each class chooses its subclass.
_SUBCLASS_CHOICE_LEVEL: dict[str, int] = {
    "cleric": 1,
    "sorcerer": 1,
    "warlock": 1,
    "druid": 2,
    "wizard": 2,
    "barbarian": 3,
    "bard": 3,
    "fighter": 3,
    "monk": 3,
    "paladin": 3,
    "ranger": 3,
    "rogue": 3,
}

#: Display name for each class's subclass category.
_SUBCLASS_CATEGORY: dict[str, str] = {
    "barbarian": "Primal Path",
    "bard": "Bard College",
    "cleric": "Divine Domain",
    "druid": "Druid Circle",
    "fighter": "Martial Archetype",
    "monk": "Monastic Tradition",
    "paladin": "Sacred Oath",
    "ranger": "Ranger Archetype",
    "rogue": "Roguish Archetype",
    "sorcerer": "Sorcerous Origin",
    "warlock": "Otherworldly Patron",
    "wizard": "Arcane Tradition",
}


# --------------------------------------------------------------------------- #
# Data model                                                                  #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Subclass:
    """A single DnD 5e subclass.

    ``features`` maps the character level at which a feature is granted to a
    short, evocative description (the feature name plus a clause). Levels with
    no feature are simply absent.
    """
    id: str
    name: str
    char_class: str
    category: str
    description: str
    features: dict[int, str] = field(default_factory=dict)

    def feature_at(self, level: int) -> str:
        """Feature description gained at exactly ``level`` ("" if none)."""
        return self.features.get(level, "")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "char_class": self.char_class,
            "category": self.category,
            "description": self.description,
            "features": [
                {"level": lvl, "feature": feat}
                for lvl, feat in sorted(self.features.items())
            ],
        }


# --------------------------------------------------------------------------- #
# Registry — representative official subclasses (2–3 per core class)          #
# --------------------------------------------------------------------------- #

SUBCLASS_REGISTRY: list[Subclass] = [
    # ---- Barbarian (Primal Path, level 3) --------------------------------- #
    Subclass(
        id="berserker",
        name="Path of the Berserker",
        char_class="barbarian",
        category="Primal Path",
        description=(
            "A barbarian who channels towering fury into a battle trance, "
            "fighting with heedless, exhilarating abandon."
        ),
        features={
            3: "Frenzy — enter a raging frenzy to make a single melee weapon "
               "attack as a bonus action each turn while raging",
            6: "Mindless Rage — immune to the charmed and frightened conditions "
               "while raging",
            10: "Intimidating Presence — frighten a creature as an action "
               "(DC 8 + proficiency + Cha mod)",
            14: "Retaliation — react to being damaged by a creature within 5 ft "
               "with a melee weapon attack",
        },
    ),
    Subclass(
        id="totem-warrior",
        name="Path of the Totem Warrior",
        char_class="barbarian",
        category="Primal Path",
        description=(
            "A barbarian who draws spiritual power from a totem animal, "
            "gaining its aspect while raging."
        ),
        features={
            3: "Spirit Seeker / Totem Spirit (Bear) — bear aspect grants "
               "resistance to all damage except psychic while raging",
            6: "Aspect of the Beast (Eagle) — advantage on Perception and "
               "farseeing sight",
            10: "Spirit Walker — commune with nature spirits via augury and "
               "clairvoyance",
            14: "Totemic Attunement (Bear) — force attackers within 5 ft to "
               "make a Wisdom save or be frightened",
        },
    ),

    # ---- Bard (Bard College, level 3) ------------------------------------- #
    Subclass(
        id="lore",
        name="College of Lore",
        char_class="bard",
        category="Bard College",
        description=(
            "Bards devoted to gathering knowledge and lore, whose cutting "
            "words can derail any foe."
        ),
        features={
            3: "Proficiency in three skills; Cutting Words — spend a Bardic "
               "Inspiration die to reduce an enemy's attack/ability/damage roll",
            6: "Additional Magical Secrets — learn two spells from any class",
            14: "Peerless Skill — add a Bardic Inspiration die to any ability "
               "check",
        },
    ),
    Subclass(
        id="valor",
        name="College of Valor",
        char_class="bard",
        category="Bard College",
        description=(
            "Skaldic bards who inspire courage on the battlefield, blending "
            "spell and steel."
        ),
        features={
            3: "Combat Inspiration — allies can add a Bardic Inspiration die "
               "to weapon damage or AC; medium armor, shields, martial weapons",
            6: "Extra Attack — attack twice when taking the Attack action",
            14: "Battle Magic — cast a bard spell and make one weapon attack as "
               "a bonus action",
        },
    ),

    # ---- Cleric (Divine Domain, level 1) ---------------------------------- #
    Subclass(
        id="life-domain",
        name="Life Domain",
        char_class="cleric",
        category="Divine Domain",
        description=(
            "Clerics of healing and vitality, sworn to preserve life and ease "
            "suffering. The premier healers of the realms."
        ),
        features={
            1: "Disciple of Life — healing spells restore extra HP (2 + spell "
               "level); heavy armor proficiency; bless and cure wounds",
            2: "Channel Divinity: Preserve Life — restore up to 5×cleric level "
               "HP across creatures",
            6: "Blessed Healer — when you heal another, you regain HP equal to "
               "2 + spell level",
            8: "Divine Strike — weapon attacks deal an extra 1d8 radiant damage",
            17: "Supreme Healing — all healing spells automatically roll their "
               "maximum dice",
        },
    ),
    Subclass(
        id="war-domain",
        name="War Domain",
        char_class="cleric",
        category="Divine Domain",
        description=(
            "Clerics of war gods who inspire allies to feats of martial "
            "prowess and smite the faithless."
        ),
        features={
            1: "War Priest — bonus action attack (uses Wis mod/long); martial "
               "weapons and heavy armor; guidance and shield of faith",
            2: "Channel Divinity: Guided Strike — +10 to an attack roll",
            6: "Channel Divinity: War God's Blessing — grant an ally a +10 "
               "attack roll as a reaction",
            8: "Divine Strike — weapon attacks deal an extra 1d8 damage (same "
               "type as the weapon)",
            17: "Avatar of Battle — resistance to bludgeoning, piercing, and "
               "slashing from nonmagical weapons",
        },
    ),
    Subclass(
        id="knowledge-domain",
        name="Knowledge Domain",
        char_class="cleric",
        category="Divine Domain",
        description=(
            "Clerics of gods of learning who value lore, secrets, and "
            "understanding above all."
        ),
        features={
            1: "Blessings of Knowledge — proficiency in two skills and two "
               "languages; command and identify",
            2: "Channel Divinity: Knowledge of the Ages — gain proficiency in "
               "any skill or tool for 10 minutes",
            6: "Channel Divinity: Read Thoughts — read a creature's surface "
               "thoughts and suggest actions",
            8: "Divine Strike — weapon attacks deal an extra 1d8 psychic "
               "damage",
            17: "Visions of the Past — glean history from objects and locations",
        },
    ),
    Subclass(
        id="light-domain",
        name="Light Domain",
        char_class="cleric",
        category="Divine Domain",
        description=(
            "Clerics of gods of light — sun, dawn, truth — who banish "
            "darkness and illuminate the way with radiant fire."
        ),
        features={
            1: "Warding Flare — reaction to impose disadvantage on an "
               "attack against you (Wis mod/long); light, fire, and "
               "radiant cantrips; burning hands and faerie fire domain "
               "spells",
            2: "Channel Divinity: Radiance of the Dawn — dispel magical "
               "darkness within 30 ft and deal 2d10 + cleric level radiant "
               "damage to foes",
            6: "Improved Flare — use Warding Flare to protect allies "
               "within 30 ft of you",
            8: "Divine Strike — weapon attacks deal an extra 1d8 radiant "
               "damage (2d8 at level 14)",
            17: "Corona of Light — emanate bright sunlight for 1 minute; "
               "enemies have disadvantage on saves against your fire and "
               "radiant spells",
        },
    ),
    Subclass(
        id="nature-domain",
        name="Nature Domain",
        char_class="cleric",
        category="Divine Domain",
        description=(
            "Clerics who guard sacred groves and untamed wilds, "
            "channeling the wrath and bounty of the natural world."
        ),
        features={
            1: "Acolyte of Nature — learn a druid cantrip and gain "
               "proficiency in one skill (Animal Handling, Nature, or "
               "Survival); heavy armor; animal friendship and speak with "
               "animals domain spells",
            2: "Channel Divinity: Charm Animals and Plants — charm beasts "
               "and plant creatures within 30 ft for 1 minute",
            6: "Dampen Elements — reaction to grant resistance to acid, "
               "cold, fire, lightning, or thunder damage to a creature "
               "within 30 ft",
            8: "Divine Strike — weapon attacks deal an extra 1d8 cold, "
               "fire, or lightning damage (your choice; 2d8 at level 14)",
            17: "Master of Nature — creatures you have charmed gain no "
               "saving throw against your commands",
        },
    ),
    Subclass(
        id="tempest-domain",
        name="Tempest Domain",
        char_class="cleric",
        category="Divine Domain",
        description=(
            "Clerics of storm and sea gods whose righteous wrath crashes "
            "down like thunder upon the wicked."
        ),
        features={
            1: "Wrath of the Storm — reaction to deal 2d8 lightning or "
               "thunder damage when hit by a melee attack (Wis mod/long); "
               "martial weapons and heavy armor; fog cloud and "
               "thunderwave domain spells",
            2: "Channel Divinity: Destructive Wrath — maximize the damage "
               "of a lightning or thunder roll (instead of rolling it)",
            6: "Thunderbolt Strike — when you deal lightning damage to a "
               "Large or smaller creature, push it 10 ft away",
            8: "Divine Strike — weapon attacks deal an extra 1d8 thunder "
               "damage (2d8 at level 14)",
            17: "Stormborn — gain a flying speed equal to your walking "
               "speed while outdoors",
        },
    ),
    Subclass(
        id="trickery-domain",
        name="Trickery Domain",
        char_class="cleric",
        category="Divine Domain",
        description=(
            "Clerics of gods of mischief and deception who trade in "
            "illusions, secrets, and the art of the confidence game."
        ),
        features={
            1: "Blessing of the Trickster — touch a creature to grant "
               "advantage on Stealth checks (action); charm person and "
               "disguise self domain spells",
            2: "Channel Divinity: Invoke Duplicity — create an illusory "
               "duplicate of yourself; cast spells as if from its space "
               "and gain advantage when it is within 5 ft of a foe",
            6: "Channel Divinity: Cloak of Shadows — become invisible "
               "until the end of your next turn",
            8: "Divine Strike — weapon attacks deal an extra 1d8 poison "
               "damage (2d8 at level 14)",
            17: "Improved Duplicity — create up to four illusory "
               "duplicates at once (each moves and mimics you)",
        },
    ),

    # ---- Druid (Druid Circle, level 2) ------------------------------------ #
    Subclass(
        id="land",
        name="Circle of the Land",
        char_class="druid",
        category="Druid Circle",
        description=(
            "Mystics and sages of nature who gather in the wild places, "
            "wardens of the untamed land."
        ),
        features={
            2: "Druidcraft cantrip; Natural Recovery — recover spell slots "
               "(total level = druid level/2) on a short rest once per long "
               "rest; bonus circle spells by terrain",
            6: "Land's Stride — move through difficult terrain and nonmagical "
               "plants unhindered; advantage vs plant entanglement",
            10: "Nature's Ward — immune to poison and disease; immunity to "
               "being charmed or frightened by elementals or fey",
            14: "Nature's Sanctuary — beasts and plants have disadvantage on "
               "attacks against you",
        },
    ),
    Subclass(
        id="moon",
        name="Circle of the Moon",
        char_class="druid",
        category="Druid Circle",
        description=(
            "Fierce guardians of the wilds who prowl the deepest forests in "
            "the shapes of mighty beasts."
        ),
        features={
            2: "Combat Wild Shape — wild shape as a bonus action; heal as a "
               "bonus action; can take CR 1 (and higher) beast forms",
            6: "Primal Strike — beast-form attacks count as magical for "
               "overcoming resistance",
            10: "Elemental Wild Shape — expend two wild-shape uses to take an "
               "elemental form",
            14: "Thousand Forms — cast alter self at will",
        },
    ),

    # ---- Fighter (Martial Archetype, level 3) ----------------------------- #
    Subclass(
        id="champion",
        name="Champion",
        char_class="fighter",
        category="Martial Archetype",
        description=(
            "A fighter who relentlessly hones physical talent, aiming to "
            "become the deadliest warrior possible."
        ),
        features={
            3: "Improved Critical — critical hits on a 19 or 20",
            7: "Remarkable Athlete — add half proficiency (rounded up) to "
               "Str/Dex/Con checks lacking proficiency; +1 to running long jump",
            10: "Additional Fighting Style — pick a second fighting style",
            15: "Superior Critical — critical hits on an 18, 19, or 20",
            18: "Survivor — regain 5 + Con mod HP at the start of each turn if "
               "below half HP",
        },
    ),
    Subclass(
        id="battle-master",
        name="Battle Master",
        char_class="fighter",
        category="Martial Archetype",
        description=(
            "A fighter whose combat skill transcends mere muscle — a student "
            "of war who turns battle into an art."
        ),
        features={
            3: "Combat Superiority — learn 3 maneuvers with 4 superiority "
               "dice (d8); Student of War (artisan's tools proficiency)",
            7: "Know Your Enemy — study a creature for 1 minute to learn if "
               "its physical stats outclass yours; gain 1 maneuver + 1 die",
            10: "Gain 2 maneuvers and an extra superiority die (d10)",
            15: "Gain 2 maneuvers and an extra superiority die (d10)",
            18: "Relentless — recover one superiority die on initiative if you "
               "have none left",
        },
    ),
    Subclass(
        id="eldritch-knight",
        name="Eldritch Knight",
        char_class="fighter",
        category="Martial Archetype",
        description=(
            "An arcane warrior who blends the mastery of weapons with the "
            "power of the Art."
        ),
        features={
            3: "Spellcasting (wizard spells) — two cantrips and a spellbook; "
               "Weapon Bond — never be disarmed of a bonded weapon",
            7: "War Magic — cast a cantrip and make one weapon attack as a "
               "bonus action",
            10: "Eldritch Strike — hitting a creature gives it disadvantage on "
               "your next spell save against it",
            15: "Arcane Charge — teleport up to 30 ft when you use Action Surge",
            18: "Improved War Magic — cast a spell (1 action) and make a weapon "
               "attack as a bonus action",
        },
    ),

    # ---- Monk (Monastic Tradition, level 3) ------------------------------- #
    Subclass(
        id="open-hand",
        name="Way of the Open Hand",
        char_class="monk",
        category="Monastic Tradition",
        description=(
            "Monks who are the ultimate masters of martial arts, striking "
            "with precision and Ki-fueled control."
        ),
        features={
            3: "Open Hand Technique — when you Flurry of Blows, each hit can "
               "push, knock prone, or prevent reactions",
            6: "Wholeness of Body — heal yourself for 3×monk level HP once per "
               "long rest",
            11: "Tranquility — sanctuary on yourself at the end of a long rest",
            17: "Quivering Palm — set up a fatal vibration in a creature's body",
        },
    ),
    Subclass(
        id="shadow",
        name="Way of Shadow",
        char_class="monk",
        category="Monastic Tradition",
        description=(
            "Monks who follow the ninja tradition, masters of stealth and "
            "illusion who slip through the shadows."
        ),
        features={
            3: "Shadow Arts — minor illusion cantrip; Shadow Step — teleport "
               "between dim light/darkness (level 6)",
            6: "Shadow Step — teleport 60 ft between shadows as a bonus action; "
               "advantage on the first melee attack afterward",
            11: "Cloak of Shadows — become invisible in dim light/darkness by "
               "spending 1 Ki",
            17: "Opportunist — reaction to make a melee attack against a "
               "creature hit by an ally",
        },
    ),
    Subclass(
        id="four-elements",
        name="Way of the Four Elements",
        char_class="monk",
        category="Monastic Tradition",
        description=(
            "Monks who channel the raw power of the elements — earth, "
            "air, fire, and water — through disciplined mastery of Ki."
        ),
        features={
            3: "Disciple of the Elements — learn three elemental "
               "disciplines (including Elemental Attunement) that let you "
               "spend Ki to shape the elements (Fist of Unbroken Air, "
               "Fist of Four Thunders, Rush of the Gale Spirits, etc.)",
            6: "Learn one additional elemental discipline; many "
               "disciplines cost less Ki to use",
            11: "Learn one additional elemental discipline of your choice "
               "(Water Whip, Clench of the North Wind, Gong of the Summit)",
            17: "Learn one additional elemental discipline of your choice "
               "(Breath of Winter, Eternal Mountain Defense, Flames of the "
               "Phoenix, Mist Stance, River of Hungry Flame)",
        },
    ),

    # ---- Paladin (Sacred Oath, level 3) ----------------------------------- #
    Subclass(
        id="devotion",
        name="Oath of Devotion",
        char_class="paladin",
        category="Sacred Oath",
        description=(
            "Paladins who uphold the loftiest ideals of justice, virtue, and "
            "order — the classic shining knight."
        ),
        features={
            3: "Channel Divinity: Sacred Weapon (+Cha to attacks) and Turn "
               "the Unholy; oath spells (protection from evil, sanctuary)",
            7: "Aura of Devotion — you and allies within 10 ft are immune to "
               "the charmed condition",
            15: "Purity of Spirit — protected from evil and good on yourself at "
               "all times",
            20: "Holy Nimbus — emanate sunlight that blinds foes and deals "
               "radiant damage for 1 minute",
        },
    ),
    Subclass(
        id="ancients",
        name="Oath of the Ancients",
        char_class="paladin",
        category="Sacred Oath",
        description=(
            "Paladins who swear to the light of the primeval world, "
            "defenders of all that is beautiful and alive."
        ),
        features={
            3: "Channel Divinity: Nature's Wrath (restraining vines) and Turn "
               "the Faithless; oath spells (ensnaring strike, speak with animals)",
            7: "Aura of Warding — you and allies within 10 ft have resistance "
               "to spell damage",
            15: "Undying Sentinel — when reduced to 0 HP, drop to 1 instead "
               "(once per long rest)",
            20: "Elder Champion — become a force of nature for 1 minute "
               "(regen, faster spells, ally healing)",
        },
    ),
    Subclass(
        id="vengeance",
        name="Oath of Vengeance",
        char_class="paladin",
        category="Sacred Oath",
        description=(
            "Paladins who have sworn to smite the wicked by any means, "
            "relentless avengers of grievous wrongs."
        ),
        features={
            3: "Channel Divinity: Abjure Enemy (frighten) and Vow of Enmity "
               "(advantage vs one foe); oath spells (bane, hunter's mark)",
            7: "Relentless Avenger — when you hit with an opportunity attack, "
               "move up to half your speed as part of the reaction",
            15: "Soul of Vengeance — make a melee attack against your Vow of "
               "Enmity target as a bonus action each turn",
            20: "Avenging Angel — sprout wings, gain a flying speed and a "
               "frightful aura for 1 hour",
        },
    ),

    # ---- Ranger (Ranger Archetype, level 3) ------------------------------- #
    Subclass(
        id="hunter",
        name="Hunter",
        char_class="ranger",
        category="Ranger Archetype",
        description=(
            "Rangers who embody the apex predator, masters of the hunt who "
            "track and slay the deadliest prey."
        ),
        features={
            3: "Hunter's Prey — choose Colossus Slayer (+1d8 to wounded foes), "
               "Giant Killer (reaction attack vs larger foes), or Horde Breaker "
               "(extra attack vs adjacent foe)",
            7: "Defensive Tactics — choose resistance to one damage type, "
               "evasion, or no disadvantage on ranged attacks in melee",
            11: "Multiattack — attack all adjacent, volley, or whirlwind",
            15: "Superior Hunter's Defense — stand against the horde, evade, "
               "or uncanny dodge",
        },
    ),
    Subclass(
        id="beast-master",
        name="Beast Master",
        char_class="ranger",
        category="Ranger Archetype",
        description=(
            "Rangers bound to a loyal animal companion who fights at their "
            "side as one."
        ),
        features={
            3: "Ranger's Companion — tame a beast (CR 1/4) that obeys your "
               "commands and gains your proficiency bonus to stats",
            7: "Exceptional Training — your companion can use its reaction to "
               "make an attack; it obeys commands without an action",
            11: "Bestial Fury — your companion can make a second attack when "
               "you command it",
            15: "Share Spells — any spell you cast on yourself also affects "
               "your companion if within 30 ft",
        },
    ),

    # ---- Rogue (Roguish Archetype, level 3) ------------------------------- #
    Subclass(
        id="thief",
        name="Thief",
        char_class="rogue",
        category="Roguish Archetype",
        description=(
            "Rogues who hone the arts of stealth, agility, and larceny — the "
            "quintessential second-story worker."
        ),
        features={
            3: "Fast Hands — use Sleight of Hand / thieves' tools / Use an "
               "Object as a bonus action; Second-Story Work — climb faster and "
               "jump higher",
            9: "Supreme Sneak — advantage on Stealth when moving no more than "
               "half speed",
            13: "Use Magic Device — ignore class/race/level requirements on "
               "magic items",
            17: "Thief's Reflexes — take two turns in the first round of combat",
        },
    ),
    Subclass(
        id="assassin",
        name="Assassin",
        char_class="rogue",
        category="Roguish Archetype",
        description=(
            "Rogues who focus on the art of death, masters of disguise and "
            "lethal surprise."
        ),
        features={
            3: "Assassinate — advantage against creatures that haven't taken a "
               "turn yet; any hit against a surprised creature is a critical hit",
            9: "Infiltration Expertise — forge identities and documents to "
               "establish a cover",
            13: "Impostor — mimic the behavior and speech of any creature you "
               "studied",
            17: "Death Strike — double damage on a surprised foe that fails a "
               "Con save (else +1× damage)",
        },
    ),
    Subclass(
        id="arcane-trickster",
        name="Arcane Trickster",
        char_class="rogue",
        category="Roguish Archetype",
        description=(
            "Rogues who combine stealth with arcane guile, using spellcraft to "
            "enrich their larceny."
        ),
        features={
            3: "Spellcasting (wizard spells, mostly enchantment/illusion); "
               "Mage Hand Legerdemain — perform Sleight of Hand through the "
               "invisible hand",
            9: "Magical Ambush — advantage on spell saves against creatures "
               "that can't see you",
            13: "Versatile Trickster — distract foes with the mage hand to "
               "gain advantage on attacks",
            17: "Spell Thief — steal a spell cast at you and cast it back",
        },
    ),

    # ---- Sorcerer (Sorcerous Origin, level 1) ----------------------------- #
    Subclass(
        id="draconic-bloodline",
        name="Draconic Bloodline",
        char_class="sorcerer",
        category="Sorcerous Origin",
        description=(
            "Sorcerers whose magic springs from a draconic ancestor, granting "
            "raw power and a touch of the dragon's majesty."
        ),
        features={
            1: "Draconic Resilience — +1 HP/level and a natural AC of 13 + Dex "
               "mod; Draconic language",
            6: "Elemental Affinity — add your Charisma mod to damage of spells "
               "matching your dragon's damage type; spend 1 sorcery point for "
               "resistance",
            14: "Elemental Wings — sprout wings for 1 hour (fly speed 20)",
            18: "Draconic Presence — frighten nearby enemies as an action by "
               "spending sorcery points",
        },
    ),
    Subclass(
        id="wild-magic",
        name="Wild Magic",
        char_class="sorcerer",
        category="Sorcerous Origin",
        description=(
            "Sorcerers whose magic wells up untamed and chaotic, bursting "
            "forth in unpredictable surges."
        ),
        features={
            1: "Wild Magic Surge — roll on the surge table when you cast a "
               "spell (1 on a d20); Tides of Chaos — gain advantage on a roll, "
               "then surge",
            6: "Bend Luck — spend 2 sorcery points to add/subtract 1d4 from a "
               "creature's roll",
            14: "Controlled Chaos — reroll any die on the wild surge table",
            18: "Spell Bombardment — once per turn, a spell dealing damage rolls "
               "an extra die on its highest die (max +3)",
        },
    ),

    # ---- Warlock (Otherworldly Patron, level 1) --------------------------- #
    Subclass(
        id="the-fiend",
        name="The Fiend",
        char_class="warlock",
        category="Otherworldly Patron",
        description=(
            "Warlocks whose patron is a powerful fiend — a bargain granting "
            "dark power and damning temptation."
        ),
        features={
            1: "Dark One's Blessing — gain temporary HP equal to Cha mod + "
               "warlock level when you reduce a creature to 0 HP",
            6: "Dark One's Own Luck — add 1d10 to an ability or save roll once "
               "per short rest",
            10: "Fiendish Resilience — choose a damage type to gain resistance "
               "to (changes on a short rest)",
            14: "Hurl Through Hell — banish a hit creature to the lower planes, "
               "dealing 10d10 psychic damage (once per long rest)",
        },
    ),
    Subclass(
        id="the-archfey",
        name="The Archfey",
        char_class="warlock",
        category="Otherworldly Patron",
        description=(
            "Warlocks whose patron is a lord or lady of the Feywild, masters "
            "of beguilement and capricious enchantment."
        ),
        features={
            1: "Fey Presence — charm or frighten creatures in a 10-ft cube "
               "(save vs your warlock spell save)",
            6: "Misty Escape — teleport 60 ft and turn invisible when damaged "
               "(once per short rest)",
            10: "Beguiling Defenses — immune to charm; turn the charmer's "
               "spell back on them",
            14: "Dark Delirium — charm or frighten a creature with an otherworldly "
               "perception (once per long rest)",
        },
    ),
    Subclass(
        id="the-great-old-one",
        name="The Great Old One",
        char_class="warlock",
        category="Otherworldly Patron",
        description=(
            "Warlocks whose patron is an alien entity from the Far Realm, "
            "whispers of cosmic madness made manifest."
        ),
        features={
            1: "Awakened Mind — communicate telepathically with any creature "
               "within 30 ft that shares a language",
            6: "Entropic Warding — when missed, your next attack gains "
               "advantage (once per short rest)",
            10: "Thought Shield — immune to telepathy read; resistance to "
               "psychic; attackers take psychic damage",
            14: "Create Thrall — touch a charmed creature to embed a telepathic "
               "command while it remains charmed",
        },
    ),

    # ---- Wizard (Arcane Tradition, level 2) ------------------------------- #
    Subclass(
        id="evocation",
        name="School of Evocation",
        char_class="wizard",
        category="Arcane Tradition",
        description=(
            "Wizards who specialize in evocation — the art of channeling raw "
            "magical energy into destructive force."
        ),
        features={
            2: "Savant — halve the gold/time to copy evocation spells; "
               "Sculpt Spells — protect allies from your evocations (no damage "
               "on save, half on fail)",
            6: "Potent Cantrip — cantrips deal half damage on a failed save "
               "against a creature",
            10: "Empowered Evocation — add your Intelligence mod to the damage "
               "of one evocation spell per turn",
            14: "Overchannel — maximize the damage of an evocation spell of 5th "
               "level or lower (escalating damage risk)",
        },
    ),
    Subclass(
        id="abjuration",
        name="School of Abjuration",
        char_class="wizard",
        category="Arcane Tradition",
        description=(
            "Wizards who weave protective wards and dispel hostile magic — "
            "masters of magical defense."
        ),
        features={
            2: "Savant — halve the gold/time to copy abjuration spells; "
               "Arcane Ward — casting abjurations charges a ward that absorbs "
               "damage for you",
            6: "Projected Ward — spend ward HP to shield an ally from damage",
            10: "Improved Abjuration — add your proficiency bonus to ability "
               "checks made as part of abjuration spells",
            14: "Spell Resistance — advantage on saves against spells and "
               "resistance to spell damage",
        },
    ),
    Subclass(
        id="conjuration",
        name="School of Conjuration",
        char_class="wizard",
        category="Arcane Tradition",
        description=(
            "Wizards who specialize in conjuration — the art of "
            "transporting creatures and objects across space and even "
            "the planes of existence."
        ),
        features={
            2: "Savant — halve the gold/time to copy conjuration spells; "
               "Minor Conjuration — create a tiny, weightless object in "
               "your hand or an unoccupied space within 10 ft",
            6: "Benign Transposition — after you cast a conjuration spell "
               "of 1st level or higher, teleport up to 30 ft or swap "
               "places with an ally within 30 ft (once per turn)",
            10: "Focused Conjuration — concentration on a conjuration spell "
               "cannot be broken by you taking damage",
            14: "Durable Summons — any creature you summon or create gains "
               "+30 temporary HP",
        },
    ),
    Subclass(
        id="divination",
        name="School of Divination",
        char_class="wizard",
        category="Arcane Tradition",
        description=(
            "Wizards who glimpse beyond the veil of time, reading the "
            "threads of fate to see what is yet to come."
        ),
        features={
            2: "Savant — halve the gold/time to copy divination spells; "
               "Portent — after a long rest, roll two d20 'foretelling "
               "dice' and use each once to replace any attack roll, saving "
               "throw, or ability check",
            6: "Expert Divination — when you cast a divination spell of "
               "2nd level or higher using a spell slot, regain a spent "
               "slot of a lower level",
            10: "The Third Eye — spend an action to gain one benefit "
               "(darkvision 60 ft, ethereal sight 60 ft, greater "
               "comprehension, or see invisibility) for 10 minutes",
            14: "Greater Portent — roll three foretelling dice instead of "
               "two",
        },
    ),
    Subclass(
        id="enchantment",
        name="School of Enchantment",
        char_class="wizard",
        category="Arcane Tradition",
        description=(
            "Wizards who bend minds and charm hearts, weaving subtle "
            "influence over the thoughts and wills of others."
        ),
        features={
            2: "Savant — halve the gold/time to copy enchantment spells; "
               "Hypnotic Gaze — action to charm and incapacitate a "
               "creature within 5 ft (save vs your spell save)",
            6: "Instinctive Charm — reaction to divert a melee attack "
               "against you onto another creature within 30 ft (no repeat "
               "against the same attacker until your next rest)",
            10: "Split Enchantment — your enchantment spells of 2nd level "
               "or higher can target one additional creature",
            14: "Alter Memories — a creature charmed by you for 5+ minutes "
               "forgets being charmed; you may modify its memory of that "
               "time",
        },
    ),
    Subclass(
        id="illusion",
        name="School of Illusion",
        char_class="wizard",
        category="Arcane Tradition",
        description=(
            "Wizards who weave phantasms and mirages, blurring the line "
            "between what is real and what merely seems to be."
        ),
        features={
            2: "Savant — halve the gold/time to copy illusion spells; "
               "Improved Minor Illusion — know minor illusion and can "
               "create both its sound and image at once",
            6: "Malleable Illusions — use an action to change the nature "
               "of an illusion spell you cast and are concentrating on",
            10: "Illusory Self — reaction to cause an attack that hits "
               "you to miss instead (once per short rest)",
            14: "Illusory Reality — make one object in your illusion real "
               "for 1 minute (it cannot deal damage or heal)",
        },
    ),
    Subclass(
        id="necromancy",
        name="School of Necromancy",
        char_class="wizard",
        category="Arcane Tradition",
        description=(
            "Wizards who study the forces of life and death, commanding "
            "the undead and siphoning vital essence."
        ),
        features={
            2: "Savant — halve the gold/time to copy necromancy spells; "
               "Grim Harvest — once per turn when you kill a creature with "
               "a spell, regain HP equal to 3× the spell level (3× the "
               "level + 2 for necromancy spells)",
            6: "Undead Thralls — learn animate dead; when you cast it you "
               "raise one additional undead; your undead gain HP equal to "
               "your wizard level",
            10: "Inured to Undeath — resistance to necrotic damage, and "
               "your HP maximum cannot be reduced",
            14: "Command Undead — use an action to attempt to seize "
               "control of an undead within 60 ft (target makes a Charisma "
               "save vs your spell save)",
        },
    ),
    Subclass(
        id="transmutation",
        name="School of Transmutation",
        char_class="wizard",
        category="Arcane Tradition",
        description=(
            "Wizards who alter the nature of matter and energy, "
            "reshaping the physical world to their will."
        ),
        features={
            2: "Savant — halve the gold/time to copy transmutation spells; "
               "Minor Alchemy — transform a cubic foot of wood, stone, "
               "iron, copper, or silver into another of those materials "
               "(10 minutes per cubic foot)",
            6: "Transmuter's Stone — spend 8 hours creating a stone "
               "granting one benefit (darkvision 60 ft, +10 speed, an "
               "extra language, or resistance to one damage type); change "
               "the benefit when you cast a transmutation spell of 1st "
               "level or higher",
            10: "Shapechanger — cast polymorph on yourself without "
               "expending a spell slot or requiring components (once per "
               "short rest)",
            14: "Master Transmuter — consume the Transmuter's Stone in a "
               "10-minute ritual to apply greater restoration, remove "
               "curse, panacea, raise dead, or restore youth",
        },
    ),
]


# --------------------------------------------------------------------------- #
# Indexes & lookups                                                           #
# --------------------------------------------------------------------------- #

_BY_ID: dict[str, Subclass] = {s.id: s for s in SUBCLASS_REGISTRY}


def all_subclasses() -> list[Subclass]:
    """All subclasses in the registry (sorted by class then name)."""
    return sorted(SUBCLASS_REGISTRY, key=lambda s: (s.char_class, s.name))


def subclasses_for_class(char_class: str) -> list[Subclass]:
    """All subclasses available to a given parent class."""
    cls = char_class.lower()
    return sorted(
        (s for s in SUBCLASS_REGISTRY if s.char_class == cls),
        key=lambda s: s.name,
    )


def get_subclass(subclass_id: str | None) -> Subclass | None:
    """Look up a subclass by id (case-insensitive). Returns None if not found."""
    if not subclass_id:
        return None
    return _BY_ID.get(subclass_id.lower())


def has_subclasses(char_class: str) -> bool:
    """Whether the registry offers any subclass for the given class."""
    return bool(subclasses_for_class(char_class))


def subclass_choice_level(char_class: str) -> int:
    """The character level at which ``char_class`` chooses its subclass.

    Returns 0 for unknown classes (i.e. no subclass modelled).
    """
    return _SUBCLASS_CHOICE_LEVEL.get(char_class.lower(), 0)


def subclass_category(char_class: str) -> str:
    """The display name of a class's subclass category (e.g. 'Divine Domain')."""
    return _SUBCLASS_CATEGORY.get(char_class.lower(), "Subclass")


# --------------------------------------------------------------------------- #
# Eligibility & validation                                                    #
# --------------------------------------------------------------------------- #

@dataclass
class SubclassChoiceResult:
    """Outcome of validating / computing a subclass choice."""
    success: bool
    message: str
    char_class: str = ""
    subclass: Subclass | None = None


def can_choose_subclass(
    char_class: str, level: int, current_subclass: str | None = None
) -> bool:
    """Whether a character of ``char_class`` at ``level`` may pick a subclass.

    True when the character has reached the choice level for the class and has
    not already chosen a subclass for it.
    """
    choice_lvl = subclass_choice_level(char_class)
    if choice_lvl == 0:
        return False
    if level < choice_lvl:
        return False
    if current_subclass:
        return False
    return True


def validate_subclass_choice(
    char_class: str,
    subclass_id: str,
    level: int,
    current_subclass: str | None = None,
) -> SubclassChoiceResult:
    """Validate a subclass choice, returning a descriptive result.

    Checks that the subclass exists, belongs to the named parent class, and
    that the character is eligible (right level, not already chosen).
    """
    sub = get_subclass(subclass_id)
    if sub is None:
        return SubclassChoiceResult(
            False, f"Unknown subclass '{subclass_id}'."
        )
    if sub.char_class != char_class.lower():
        return SubclassChoiceResult(
            False,
            f"{sub.name} is a {sub.char_class} subclass, not a "
            f"{char_class} subclass.",
        )
    choice_lvl = subclass_choice_level(char_class)
    if choice_lvl == 0:
        return SubclassChoiceResult(
            False, f"No subclass is modelled for '{char_class}'."
        )
    if level < choice_lvl:
        return SubclassChoiceResult(
            False,
            f"{char_class.capitalize()} chooses its {subclass_category(char_class)} "
            f"at level {choice_lvl} (currently level {level}).",
        )
    if current_subclass:
        existing = get_subclass(current_subclass)
        label = existing.name if existing else current_subclass
        return SubclassChoiceResult(
            False,
            f"Already a {label} (subclass choice is permanent).",
        )
    return SubclassChoiceResult(
        True,
        f"Chose {sub.name} ({sub.category}).",
        char_class=char_class.lower(),
        subclass=sub,
    )


# --------------------------------------------------------------------------- #
# Feature progression                                                         #
# --------------------------------------------------------------------------- #

def features_at_level(subclass_id: str, level: int) -> str:
    """Subclass feature gained at exactly ``level`` ("" if none / unknown)."""
    sub = get_subclass(subclass_id)
    if sub is None:
        return ""
    return sub.feature_at(level)


def features_through_level(
    subclass_id: str, level: int
) -> list[tuple[int, str]]:
    """All ``(level, feature)`` pairs a subclass grants through ``level``.

    Sorted ascending by level. Empty if the subclass is unknown.
    """
    sub = get_subclass(subclass_id)
    if sub is None:
        return []
    out = [
        (lvl, feat)
        for lvl, feat in sub.features.items()
        if lvl <= level
    ]
    out.sort(key=lambda t: t[0])
    return out


def next_subclass_feature(subclass_id: str, level: int) -> tuple[int, str] | None:
    """The next ``(level, feature)`` a subclass grants after ``level``.

    Returns None if there is no further feature (or the subclass is unknown).
    """
    sub = get_subclass(subclass_id)
    if sub is None:
        return None
    upcoming = [(lvl, feat) for lvl, feat in sub.features.items() if lvl > level]
    if not upcoming:
        return None
    return min(upcoming, key=lambda t: t[0])


# --------------------------------------------------------------------------- #
# DM / UI helpers                                                             #
# --------------------------------------------------------------------------- #

def subclass_summary_for_dm(
    char_class: str, subclass_id: str | None, level: int
) -> str:
    """A short DM-context line describing the character's subclass.

    Returns 'none (chooses at level N)' if not yet chosen but eligible, or
    'none' if the class has no modelled subclass. Otherwise the subclass name
    plus the features currently in effect.
    """
    choice_lvl = subclass_choice_level(char_class)
    if not subclass_id:
        if choice_lvl == 0:
            return "none"
        if level < choice_lvl:
            return f"none (chooses {subclass_category(char_class)} at level {choice_lvl})"
        return f"none (should choose a {subclass_category(char_class)})"
    sub = get_subclass(subclass_id)
    if sub is None:
        return f"unknown ({subclass_id})"
    active = features_through_level(subclass_id, level)
    if active:
        # One short clause: the subclass name + active feature names.
        names = "; ".join(feat.split("—")[0].split("—")[0].strip() for _, feat in active)
        return f"{sub.name}: {names}"
    return sub.name


def subclass_for_dm(
    char_class: str, subclass_id: str | None, level: int
) -> str:
    """Alias of :func:`subclass_summary_for_dm` for naming consistency."""
    return subclass_summary_for_dm(char_class, subclass_id, level)


def combined_features_through_level(
    char_class: str,
    level: int,
    subclass_id: str | None = None,
) -> list[dict[str, object]]:
    """Merge class + subclass features through ``level`` into one timeline.

    Returns a list of ``{"level", "source", "feature"}`` dicts sorted by level.
    ``source`` is "class" or the subclass's short name. The class-feature table
    is read lazily to avoid an import cycle at module load.
    """
    from app.engine.leveling import features_through_level as class_feats

    out: list[dict[str, object]] = []
    for lvl, feat in class_feats(char_class, level):
        out.append({"level": lvl, "source": "class", "feature": feat})
    if subclass_id:
        sub = get_subclass(subclass_id)
        if sub is not None:
            short = sub.name
            for lvl, feat in features_through_level(subclass_id, level):
                out.append(
                    {"level": lvl, "source": short, "feature": feat}
                )
    out.sort(key=lambda d: (d["level"], str(d["source"])))
    return out
