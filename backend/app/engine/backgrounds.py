"""
Character background system — DnD 5e backgrounds as a unified registry.

In DnD 5e a *background* is the third pillar of character creation (alongside
race and class). Each background grants:

- **Skill proficiencies** — two fixed skills (e.g., Soldier grants Athletics
  and Intimidation).
- **Tool proficiencies** — a fixed set plus an optional choice (e.g., Criminal
  grants Thieves' Tools and one gaming set).
- **Languages** — most backgrounds grant a choice of extra languages; some
  grant none. (Common + racial languages come from the race, not the
  background.)
- **Equipment** — a starting package of mundane gear and a small gold pouch.
- **Feature** — a unique roleplay/feature benefit (e.g., "Military Rank",
  "Shelter of the Faithful", "Wanderer") that opens narrative opportunities.
- **Suggested characteristics** — optional personality traits, ideals, bonds,
  and flaws tables for inspiration and DM hooks.

This module is the **single source of truth** for all of that data. The skill
engine (`engine/skills.py`) and the tool engine (`engine/tools.py`) derive
their per-background tables from here so the three never drift out of sync.

The engine is pure (no DB, no LLM). It operates only on the background name.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.engine.inventory import Item, ItemType, Rarity


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class BackgroundFeature:
    """A background's signature feature (narrative benefit)."""
    name: str
    description: str

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description}


@dataclass
class Background:
    """A full DnD 5e character background definition."""
    id: str                       # lowercase key, e.g. "acolyte"
    name: str                     # display name, e.g. "Acolyte"
    description: str              # one-paragraph flavour / who you were
    skill_proficiencies: list[str]              # the 2 (or variant) skills
    tool_fixed: list[str] = field(default_factory=list)            # fixed tool ids
    tool_choice: Optional[dict] = None          # {"count": int, "categories": [...]}
    languages: list[str] = field(default_factory=list)             # fixed languages
    extra_languages: int = 0                    # number of languages to choose
    equipment: list[Item] = field(default_factory=list)            # starting items
    equipment_gold: int = 0                     # gold pouch in gp
    feature: Optional[BackgroundFeature] = None
    personality_traits: list[str] = field(default_factory=list)
    ideals: list[str] = field(default_factory=list)
    bonds: list[str] = field(default_factory=list)
    flaws: list[str] = field(default_factory=list)
    variant_of: Optional[str] = None            # set if this is a variant of another bg

    # ---- convenience accessors ------------------------------------------- #

    def tool_grants(self) -> dict:
        """Return tool grants in the shape used by the tools engine."""
        return {
            "fixed": list(self.tool_fixed),
            "choice": dict(self.tool_choice) if self.tool_choice else None,
        }

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "skill_proficiencies": list(self.skill_proficiencies),
            "tool_proficiencies": self.tool_grants(),
            "languages": list(self.languages),
            "extra_languages": self.extra_languages,
            "equipment": [item.to_dict() for item in self.equipment],
            "equipment_gold": self.equipment_gold,
            "feature": self.feature.to_dict() if self.feature else None,
            "personality_traits": list(self.personality_traits),
            "ideals": list(self.ideals),
            "bonds": list(self.bonds),
            "flaws": list(self.flaws),
            "variant_of": self.variant_of,
        }


# --------------------------------------------------------------------------- #
# Item factory helpers (mundane background gear — modelled as MISC items)
# --------------------------------------------------------------------------- #

def _gear(
    name: str,
    description: str = "",
    value: int = 0,
    weight: float = 0.5,
    quantity: int = 1,
    rarity: Rarity = Rarity.COMMON,
) -> Item:
    """A generic piece of non-combat background equipment."""
    return Item(
        id="",  # auto-generated uuid
        name=name,
        item_type=ItemType.MISC,
        description=description or f"A {name.lower()}.",
        rarity=rarity,
        value=value,
        weight=weight,
        quantity=quantity,
    )


def _clothes(kind: str, value: int = 0) -> Item:
    label = "Fine Clothes" if kind == "fine" else f"{kind.capitalize()} Clothes"
    return _gear(label, f"A set of {label.lower()}.", value=value, weight=3.0)


def _pouch(gp: int) -> Item:
    return _gear("Pouch", f"A leather pouch containing {gp} gp.", value=gp, weight=1.0)


# --------------------------------------------------------------------------- #
# Registry — Player's Handbook backgrounds (+ common variants)
# --------------------------------------------------------------------------- #
# Faithful to PHB ch. 4 "Backgrounds". Variants (Spy, Gladiator, Knight,
# Pirate, Guild Merchant) share their parent's skills/tools/feature theme.

BACKGROUNDS: dict[str, Background] = {}


def _register(bg: Background) -> Background:
    """Add a background to the registry (idempotent, keyed by lowercase id)."""
    BACKGROUNDS[bg.id.lower()] = bg
    return bg


_register(Background(
    id="acolyte",
    name="Acolyte",
    description=(
        "You have spent your life in the service of a temple, learning sacred "
        "rites and performing ceremonies. Your faith sustains you through "
        "trial and doubt, and the faithful recognise you as one of their own."
    ),
    skill_proficiencies=["insight", "religion"],
    tool_fixed=[],
    languages=[],
    extra_languages=2,
    equipment=[
        _gear("Holy Symbol", "A holy symbol of your deity.", value=5, weight=1.0),
        _gear("Prayer Book", "A prayer book or prayer wheel.", value=25, weight=5.0),
        _gear("Incense", "Five sticks of incense.", value=1, weight=0.1, quantity=5),
        _gear("Vestments", "Your ceremonial vestments.", value=15, weight=6.0),
        _clothes("common", value=0),
        _pouch(15),
    ],
    equipment_gold=15,
    feature=BackgroundFeature(
        name="Shelter of the Faithful",
        description=(
            "As an acolyte, you command the respect of those who share your "
            "faith, and you can perform the religious ceremonies of your deity. "
            "You and your adventuring companions can expect to receive free "
            "healing and care at a temple, shrine, or other established "
            "presence of your faith, though you must provide any material "
            "components needed for spells. Those who share your religion will "
            "support you at a modest lifestyle."
        ),
    ),
    personality_traits=[
        "I idolize a particular hero of my faith, and constantly refer to that person's deeds and example.",
        "I can find common ground between the fiercest enemies, empathizing with them and always working toward peace.",
        "I see omens in every event and action. The gods try to speak to us, we just need to listen.",
        "Nothing can shake my optimistic attitude.",
    ],
    ideals=[
        "Faith. I trust that my deity will guide my actions. (Good)",
        "Charity. I always try to help those in need, no matter what the personal cost. (Good)",
        "Tradition. The ancient traditions of worship and sacrifice must be preserved. (Lawful)",
        "Power. I hope to one day rise to the top of my faith's religious hierarchy. (Lawful)",
    ],
    bonds=[
        "I would die to recover an ancient relic of my faith that was lost long ago.",
        "I will someday get revenge on the corrupt religious hierarchy who branded me a heretic.",
        "I owe my life to the priest who took me in when my parents died.",
        "Everything I do is for the common people.",
    ],
    flaws=[
        "I judge others harshly, and myself even more severely.",
        "I put too much trust in those who wield power within my temple's hierarchy.",
        "My piety sometimes leads me to blindly trust those that profess faith in my god.",
        "I am inflexible in my thinking.",
    ],
))

_register(Background(
    id="charlatan",
    name="Charlatan",
    description=(
        "You have a knack for getting what you want through deception, sleight "
        "of hand, and a silver tongue. You live by your wits, always chasing "
        "the next mark and the next scheme."
    ),
    skill_proficiencies=["deception", "sleight_of_hand"],
    tool_fixed=["disguise_kit", "forgery_kit"],
    languages=[],
    extra_languages=0,
    equipment=[
        _clothes("fine", value=25),
        _gear("Disguise Kit", "A kit for disguises.", value=25, weight=3.0),
        _gear("Con Tools", "Tools of your chosen con (mark, game, or scam).", value=15, weight=5.0),
        _pouch(15),
    ],
    equipment_gold=15,
    feature=BackgroundFeature(
        name="False Identity",
        description=(
            "You have created a second identity that includes documentation, "
            "established acquaintances, and disguises that allow you to assume "
            "that persona. Additionally, you can forge documents including "
            "official papers and personal letters, as long as you have seen an "
            "example of the kind of document or the handwriting you are trying "
            "to copy."
        ),
    ),
    personality_traits=[
        "I fall in and out of love easily, and am always pursuing someone.",
        "I have a joke for every occasion, especially occasions where humor is inappropriate.",
        "Flattery is my preferred trick for getting what I want.",
        "I'm a born gambler who can't resist taking a risk for a potential payoff.",
    ],
    ideals=[
        "Independence. I am a free spirit—no one tells me what to do. (Chaotic)",
        "Fairness. I never target people who can't afford to lose a few coins. (Lawful)",
        "Charity. I distribute the money I acquire to the people who really need it. (Good)",
        "Greed. I will do whatever it takes to become wealthy. (Evil)",
    ],
    bonds=[
        "I fleeced the wrong person and must work to ensure that this individual never crosses paths with me or those I care about.",
        "Everything I do is for the common people. (Well, the common people I grew up with.)",
        "I owe everything to my mentor—a horrible person who's probably rotting in jail somewhere.",
        "My beloved was stolen from me by a noble's jealousy. I will win them back.",
    ],
    flaws=[
        "I can't resist a pretty face.",
        "I'm always in debt. I spend my ill-gotten gains on decadent luxuries faster than I bring them in.",
        "I'm convinced that no one could ever fool me the way I fool others.",
        "I'm greedy and will do anything to get rich.",
    ],
))

_register(Background(
    id="criminal",
    name="Criminal",
    description=(
        "You are an experienced criminal with a history of breaking the law. "
        "You know how the underworld works and have contacts on the wrong side "
        "of it."
    ),
    skill_proficiencies=["deception", "stealth"],
    tool_fixed=["thieves_tools"],
    tool_choice={"count": 1, "categories": ["gaming_set"]},
    languages=[],
    extra_languages=0,
    equipment=[
        _gear("Crowbar", "A sturdy iron crowbar.", value=2, weight=5.0),
        _clothes("dark common", value=0),
        _gear("Hood", "A dark hood for keeping a low profile.", value=0, weight=0.5),
        _pouch(15),
    ],
    equipment_gold=15,
    feature=BackgroundFeature(
        name="Criminal Contact",
        description=(
            "You have a reliable and trustworthy contact who acts as your "
            "liaison to a network of other criminals. You know how to get "
            "messages to and from your contact, even over great distances; "
            "specifically, you know the local messengers, corrupt caravan "
            "masters, and seedy sailors who can deliver messages for you."
        ),
    ),
    personality_traits=[
        "I always have a plan for what to do when things go wrong.",
        "I am always calm, no matter what the situation. I never raise my voice or let my emotions control me.",
        "The first thing I do in a new place is note the locations of everything valuable—or where such things could be hidden.",
        "I would rather make a new friend than a new enemy.",
    ],
    ideals=[
        "Honor. I don't steal from others in the trade. (Lawful)",
        "Freedom. Chains are meant to be broken, as are those who would forge them. (Chaotic)",
        "Charity. I steal from the wealthy so that I can help people in need. (Good)",
        "Greed. I will do whatever it takes to become wealthy. (Evil)",
    ],
    bonds=[
        "I'm guilty of a terrible crime. I hope I can redeem myself for it.",
        "Someone I loved died because of a mistake I made. That will never happen again.",
        "I would do anything for the members of my old gang.",
        "I owe a debt I can never repay to the person who took pity on me.",
    ],
    flaws=[
        "When I see something valuable, I can't think about anything but how to steal it.",
        "When faced with a choice between money and my friends, I usually choose the money.",
        "If there's a plan, I'll forget it. If I don't forget it, I'll ignore it.",
        "I have a 'tell' that reveals when I'm lying.",
    ],
))

_register(Background(
    id="spy",
    name="Spy",
    description=(
        "A variant of the Criminal background. Rather than a common thief, you "
        "plied your trade as a spy—gathering secrets, playing factions against "
        "one another, and selling information to the highest bidder."
    ),
    skill_proficiencies=["deception", "stealth"],
    tool_fixed=["thieves_tools"],
    tool_choice={"count": 1, "categories": ["gaming_set"]},
    languages=[],
    extra_languages=0,
    equipment=[
        _gear("Crowbar", "A sturdy iron crowbar.", value=2, weight=5.0),
        _clothes("dark common", value=0),
        _gear("Hood", "A dark hood for keeping a low profile.", value=0, weight=0.5),
        _pouch(15),
    ],
    equipment_gold=15,
    variant_of="criminal",
    feature=BackgroundFeature(
        name="Criminal Contact",
        description=(
            "You have a reliable and trustworthy contact who acts as your "
            "liaison to a network of other spies or informants. You know how "
            "to get messages to and from your contact, even over great "
            "distances."
        ),
    ),
))

_register(Background(
    id="entertainer",
    name="Entertainer",
    description=(
        "You thrive in front of an audience. Music, acrobatics, storytelling, "
        "or comedy—whatever your art, you know how to captivate a crowd."
    ),
    skill_proficiencies=["acrobatics", "performance"],
    tool_fixed=["disguise_kit"],
    tool_choice={"count": 1, "categories": ["musical_instrument"]},
    languages=[],
    extra_languages=0,
    equipment=[
        _gear("Musical Instrument", "Your favored musical instrument.", value=35, weight=3.0),
        _gear("Admirer's Favor", "A token of admiration from an admirer.", value=0, weight=0.2),
        _gear("Costume", "A costume befitting your act.", value=15, weight=4.0),
        _pouch(15),
    ],
    equipment_gold=15,
    feature=BackgroundFeature(
        name="By Popular Demand",
        description=(
            "You can always find a place to perform, usually in an inn or "
            "tavern but possibly with a circus, at a theater, or even in a "
            "noble's court. At such a place, you receive free lodging and food "
            "of a modest or comfortable standard (depending on the quality of "
            "the establishment), as long as you perform each night. In "
            "addition, your performance makes you something of a local figure. "
            "When strangers recognize you in a town where you have performed, "
            "they typically take a liking to you."
        ),
    ),
    personality_traits=[
        "I know a story relevant to almost every situation.",
        "Whenever I come to a new place, I collect local rumors and spread gossip.",
        "No one could ever doubt my courage, though I do my best to prove it whenever possible.",
        "I approach every situation expecting to win something.",
    ],
    ideals=[
        "Beauty. When I perform, I bring beauty to the world. (Good)",
        "Tradition. The stories and songs of the past must never be forgotten. (Lawful)",
        "Creativity. The world is in need of new ideas and bold action. (Chaotic)",
        "Greed. I'm only in it for the money and the fame. (Evil)",
    ],
    bonds=[
        "My instrument is my soul, and I'd be lost without it.",
        "Someone I loved was lost to me because I was not able to protect them.",
        "I want to be famous, whatever it takes.",
        "I idolize a hero of the old tales and measure my deeds against that person's legacy.",
    ],
    flaws=[
        "I'll do anything to win fame and renown.",
        "I use satire and mockery to hide my real feelings.",
        "I can't keep a secret to save my life—or anyone else's.",
        "I'm jealous of those who can do what I do, only better.",
    ],
))

_register(Background(
    id="gladiator",
    name="Gladiator",
    description=(
        "A variant of the Entertainer background. Instead of the stage, your "
        "arena was the fighting pit, where crowds roared for blood and you "
        "learned to make a show of violence."
    ),
    skill_proficiencies=["acrobatics", "performance"],
    tool_fixed=["disguise_kit"],
    tool_choice={"count": 1, "categories": ["musical_instrument"]},
    languages=[],
    extra_languages=0,
    equipment=[
        _gear("Musical Instrument", "An unusual weapon or signature prop from the arena.", value=35, weight=3.0),
        _gear("Admirer's Favor", "A token of admiration from an admirer.", value=0, weight=0.2),
        _gear("Costume", "A costume befitting your act.", value=15, weight=4.0),
        _pouch(15),
    ],
    equipment_gold=15,
    variant_of="entertainer",
    feature=BackgroundFeature(
        name="By Popular Demand",
        description=(
            "You can find a place to perform in any place that features combat "
            "for entertainment—or a stage. You receive free lodging and food in "
            "exchange for your performance, and the crowd recognizes you."
        ),
    ),
))

_register(Background(
    id="folk hero",
    name="Folk Hero",
    description=(
        "You come from a humble background, but you are destined for greater "
        "things. Already you have taken a stand against injustice, and the "
        "common folk look up to you."
    ),
    skill_proficiencies=["animal_handling", "survival"],
    tool_fixed=["land_vehicle"],
    tool_choice={"count": 1, "categories": ["artisan"]},
    languages=[],
    extra_languages=0,
    equipment=[
        _gear("Artisan's Tools", "A set of artisan's tools.", value=5, weight=5.0),
        _gear("Shovel", "An iron-headed shovel.", value=2, weight=5.0),
        _gear("Iron Pot", "A sturdy iron pot.", value=2, weight=10.0),
        _clothes("common", value=0),
        _pouch(10),
    ],
    equipment_gold=10,
    feature=BackgroundFeature(
        name="Rustic Hospitality",
        description=(
            "Since you come from the ranks of the common folk, you fit in "
            "among them with ease. You can find a place to hide, rest, or "
            "recuperate among other commoners, unless you have shown yourself "
            "to be a danger to them. They will shield you from the law or "
            "anyone else searching for you, though they will not risk their "
            "lives for you."
        ),
    ),
    personality_traits=[
        "I judge people by their actions, not their words.",
        "If someone is in trouble, I'm always ready to lend help.",
        "When I set my mind to something, I follow through no matter what gets in my way.",
        "I have a strong sense of fair play and always try to find the most equitable solution.",
    ],
    ideals=[
        "Respect. People deserve to be treated with dignity and respect. (Good)",
        "Fairness. No one should get preferential treatment before the law, and no one is above the law. (Lawful)",
        "Freedom. Tyrants and oppressors should not be tolerated. (Chaotic)",
        "Might. If I become strong, I can take what I want. (Evil)",
    ],
    bonds=[
        "I protect those who cannot protect themselves.",
        "I work the land, and I love the people who work it alongside me.",
        "I dream of bringing ruin to the tyrants who oppressed my people.",
        "Everything I do is for the common people.",
    ],
    flaws=[
        "The tyrant who rules my people will stop at nothing to see me destroyed.",
        "I am convinced of the significance of my destiny, and blind to my shortcomings and the risk of failure.",
        "The people who knew me when I was young know my shameful secret, so I can never go home again.",
        "I have a weakness for the vices of the city.",
    ],
))

_register(Background(
    id="guild artisan",
    name="Guild Artisan",
    description=(
        "You are a member of an artisan's guild, skilled in a particular field "
        "and well established among the merchants and crafters of your trade."
    ),
    skill_proficiencies=["insight", "persuasion"],
    tool_fixed=[],
    tool_choice={"count": 1, "categories": ["artisan"]},
    languages=[],
    extra_languages=1,
    equipment=[
        _gear("Artisan's Tools", "A set of artisan's tools.", value=5, weight=5.0),
        _gear("Letter of Introduction", "A letter of introduction from your guild.", value=0, weight=0.1),
        _clothes("traveler's", value=0),
        _gear("Traveler's Clothes", "Sturdy clothes for the road.", value=2, weight=4.0),
        _pouch(15),
    ],
    equipment_gold=15,
    feature=BackgroundFeature(
        name="Guild Membership",
        description=(
            "As an established and respected member of a guild or other "
            "professional association, you can rely on certain benefits. Your "
            "fellow guild members will provide you with lodging and food if "
            "necessary, and pay for your funeral if needed. In some cities and "
            "towns, a guildhall offers a central place to meet other members "
            "of your profession. If you are accused of a crime, your guild "
            "will support you, whether you are guilty or not."
        ),
    ),
    personality_traits=[
        "I believe that anything worth doing is worth doing right. I can't help it—I'm a perfectionist.",
        "I'm a snob who looks down on those who can't appreciate fine art.",
        "I always want to know how things work and what makes people tick.",
        "I'm full of witty aphorisms and have a proverb for every occasion.",
    ],
    ideals=[
        "Community. It is the duty of all civilized people to strengthen the bonds of community. (Good)",
        "Generosity. My talents were given to me so that I could use them to benefit the world. (Good)",
        "Tradition. The ancient ways must be preserved. (Lawful)",
        "Independence. I must prove that I can handle myself without the crutch of my guild. (Chaotic)",
    ],
    bonds=[
        "The workshop where I learned my trade is the most important place in the world to me.",
        "I created a great work for someone, and then found them unworthy to receive it. I'm still looking for someone worthy.",
        "I owe my guild a great debt for forging me into the person I am today.",
        "I pursue wealth to secure someone's love.",
    ],
    flaws=[
        "I'll do anything to get my hands on something rare or priceless.",
        "I'm quick to assume that someone is trying to cheat me.",
        "No one must ever learn that I was once a criminal.",
        "I'm never satisfied with what I have—I always want more.",
    ],
))

_register(Background(
    id="guild merchant",
    name="Guild Merchant",
    description=(
        "A variant of the Guild Artisan background. Rather than crafting, you "
        "made your living as a trader and merchant within the guild, moving "
        "goods and coin across the land."
    ),
    skill_proficiencies=["insight", "persuasion"],
    tool_fixed=[],
    tool_choice={"count": 1, "categories": ["artisan"]},
    languages=[],
    extra_languages=1,
    equipment=[
        _gear("Artisan's Tools or Navigation", "Navigator's tools or a set of artisan's tools.", value=5, weight=5.0),
        _gear("Letter of Introduction", "A letter of introduction from your guild.", value=0, weight=0.1),
        _clothes("traveler's", value=0),
        _gear("Traveler's Clothes", "Sturdy clothes for the road.", value=2, weight=4.0),
        _pouch(15),
    ],
    equipment_gold=15,
    variant_of="guild artisan",
    feature=BackgroundFeature(
        name="Guild Membership",
        description=(
            "As a respected member of a merchant's guild, you enjoy the "
            "support of fellow members, who can provide lodging, food, and "
            "legal support, and offer a guildhall to conduct business."
        ),
    ),
))

_register(Background(
    id="hermit",
    name="Hermit",
    description=(
        "You lived in seclusion, seeking enlightenment, mourning, or simply "
        "peace. In your solitude you made a discovery of great importance—"
        "something you now carry with you into the world."
    ),
    skill_proficiencies=["medicine", "religion"],
    tool_fixed=["herbalism_kit"],
    languages=[],
    extra_languages=1,
    equipment=[
        _gear("Scroll Case", "A scroll case stuffed with notes from your studies.", value=1, weight=1.0),
        _gear("Notes", "Detailed notes on your research and discoveries.", value=0, weight=1.0),
        _gear("Winter Blanket", "A thick winter blanket.", value=5, weight=3.0),
        _clothes("common", value=0),
        _gear("Herbalism Kit", "A kit for gathering and preparing herbs.", value=5, weight=3.0),
        _pouch(5),
    ],
    equipment_gold=5,
    feature=BackgroundFeature(
        name="Discovery",
        description=(
            "The quiet seclusion of your extended hermitage gave you access to "
            "a unique and powerful discovery. The exact nature of this "
            "revelation depends on the nature of your seclusion. It might be a "
            "great truth about the cosmos, the deities, the powerful beings of "
            "the outer planes, or the forces of nature. Work with your DM to "
            "determine the details."
        ),
    ),
    personality_traits=[
        "I've been isolated for so long that I rarely speak, preferring gestures and the occasional grunt.",
        "The world would be better off if everyone were more like me.",
        "I've spent so long in solitude that I have problems relating to other people.",
        "I don't much care for the company of others.",
    ],
    ideals=[
        "Greater Good. My gifts are meant to be shared with all, not used for my own benefit. (Good)",
        "Logic. Emotions must not cloud our sense of what is right and true. (Lawful)",
        "Free Thinking. Inquiry and curiosity are the pillars of progress. (Chaotic)",
        "Power. Solitude and contemplation are paths toward mystical or magical power. (Evil)",
    ],
    bonds=[
        "Nothing is more important than the other members of my hermitage, order, or affiliation.",
        "I entered seclusion to hide from the ones who might still be hunting me. I must someday confront them.",
        "I was a curse to my community. They cast me out, and I deserve it.",
        "I'm still seeking the enlightenment I pursued in my seclusion, and it still eludes me.",
    ],
    flaws=[
        "Now that I've returned to the world, I enjoy its delights a little too much.",
        "I am dogmatic in my thoughts and philosophy.",
        "I am suspicious of everyone I meet.",
        "I'd risk too much to uncover a lost piece of knowledge.",
    ],
))

_register(Background(
    id="noble",
    name="Noble",
    description=(
        "You understand wealth, power, and privilege. You carry a noble title, "
        "and your family was (or still is) influential in the realm."
    ),
    skill_proficiencies=["history", "persuasion"],
    tool_fixed=[],
    tool_choice={"count": 1, "categories": ["gaming_set"]},
    languages=[],
    extra_languages=1,
    equipment=[
        _clothes("fine", value=25),
        _gear("Signet Ring", "A signet ring bearing your family's crest.", value=5, weight=0.1),
        _gear("Pedigree Scroll", "A scroll certifying your lineage.", value=0, weight=0.2),
        _pouch(25),
    ],
    equipment_gold=25,
    feature=BackgroundFeature(
        name="Position of Privilege",
        description=(
            "Thanks to your noble birth, people are inclined to think the best "
            "of you. You are welcome in high society, and people assume you "
            "have the right to be wherever you are. The common folk and "
            "merchants make every effort to accommodate you and avoid your "
            "displeasure, and other people of high birth treat you as a member "
            "of the same social sphere. You can secure an audience with a "
            "local noble if you need to."
        ),
    ),
    personality_traits=[
        "My favor, once lost, is lost forever.",
        "I am used to having my way, and I find the troubles of others tiresome.",
        "No one could ever doubt my courage, though I do my best to prove it whenever possible.",
        "If you do me an injury, I will crush you, ruin your name, and salt your fields.",
    ],
    ideals=[
        "Respect. Respect is due to me because of my position, but all people regardless of station deserve to be treated with dignity. (Good)",
        "Noble Obligation. It is my duty to protect and care for the people beneath me. (Good)",
        "Tradition. The ancient ways must be upheld and preserved. (Lawful)",
        "Power. When I acquire power, I will use it to destroy those who wronged me. (Evil)",
    ],
    bonds=[
        "I will face any challenge to win the approval of my family.",
        "My house's alliance with another noble family must be sustained at all costs.",
        "Nothing is more important than securing my family's legacy.",
        "I am in love with the heir of a family that my family despises.",
    ],
    flaws=[
        "My envy consumes me. I can't stand being outshone.",
        "I am too quick to assume that my way is the only way.",
        "I have an inflated sense of my own importance.",
        "By my words and actions, I often bring shame to my family.",
    ],
))

_register(Background(
    id="knight",
    name="Knight",
    description=(
        "A variant of the Noble background. You hold a knightly title, "
        "bestowed for valor or bloodline, and are bound by the code of "
        "chivalry (for better or worse)."
    ),
    skill_proficiencies=["history", "persuasion"],
    tool_fixed=[],
    tool_choice={"count": 1, "categories": ["gaming_set"]},
    languages=[],
    extra_languages=1,
    equipment=[
        _clothes("fine", value=25),
        _gear("Signet Ring", "A signet ring bearing your crest.", value=5, weight=0.1),
        _gear("Pedigree Scroll", "A scroll certifying your lineage.", value=0, weight=0.2),
        _pouch(25),
    ],
    equipment_gold=25,
    variant_of="noble",
    feature=BackgroundFeature(
        name="Retainers",
        description=(
            "You have the service of three retainers loyal to your family. "
            "They are commoners who can perform mundane tasks for you, but "
            "they do not fight for you, will not follow into obviously "
            "dangerous areas, and will leave if they are frequently endangered "
            "or abused."
        ),
    ),
))

_register(Background(
    id="outlander",
    name="Outlander",
    description=(
        "You grew up in the wilds, far from civilization. You are a traveler "
        "and a survivor, at home in the untamed places of the world."
    ),
    skill_proficiencies=["athletics", "survival"],
    tool_fixed=[],
    tool_choice={"count": 1, "categories": ["musical_instrument"]},
    languages=[],
    extra_languages=1,
    equipment=[
        _gear("Staff", "A sturdy wooden staff (can be used as a quarterstaff).", value=2, weight=4.0),
        _gear("Hunting Trap", "A trap for catching small game.", value=5, weight=25.0),
        _gear("Animal Trophy", "A trophy from an animal you hunted.", value=0, weight=2.0),
        _clothes("traveler's", value=0),
        _gear("Traveler's Clothes", "Sturdy clothes for the road.", value=2, weight=4.0),
        _pouch(10),
    ],
    equipment_gold=10,
    feature=BackgroundFeature(
        name="Wanderer",
        description=(
            "You have an excellent memory for maps and geography, and you can "
            "always recall the general layout of terrain, settlements, and "
            "other features around you. In addition, you can find food and "
            "fresh water for yourself and up to five other people each day, "
            "provided that the land offers berries, small game, water, and so "
            "forth."
        ),
    ),
    personality_traits=[
        "I'm driven by a wanderlust that led me away from home.",
        "I like to get my hands dirty and solve problems firsthand.",
        "I feel tremendous empathy for all who suffer.",
        "I'm oblivious to etiquette and social expectations.",
    ],
    ideals=[
        "Change. Life is like the seasons, in constant change, and we must change with it. (Chaotic)",
        "Greater Good. It is each person's responsibility to make the most happiness for the whole world. (Good)",
        "Nature. The natural world is more important than all the constructs of civilization. (Neutral)",
        "Might. The strongest are meant to rule. (Evil)",
    ],
    bonds=[
        "My family, clan, or tribe is the most important thing in my life, even when they are far from me.",
        "An injury to the unspoiled wilderness is an injury to me.",
        "I suffer awful visions of a coming disaster and will do anything to prevent it.",
        "I would still lay down my life for the people I served with.",
    ],
    flaws=[
        "I am too enamored of ale, wine, and other intoxicants.",
        "There's no room for caution in a life lived to the fullest.",
        "I remember every insult I've received and nurse a quiet bitterness for each one.",
        "I am stubborn and slow to trust those who are not kin to me.",
    ],
))

_register(Background(
    id="sage",
    name="Sage",
    description=(
        "You spent years learning the lore of the multiverse, poring over "
        "ancient manuscripts and studying under masters. Knowledge is your "
        "trade and your passion."
    ),
    skill_proficiencies=["arcana", "history"],
    tool_fixed=[],
    languages=[],
    extra_languages=2,
    equipment=[
        _gear("Black Ink", "A bottle of black ink.", value=10, weight=0.1),
        _gear("Quill", "A quill pen.", value=0, weight=0.0),
        _gear("Small Knife", "A small knife.", value=0, weight=1.0),
        _gear("Letter from Colleague", "A letter from a dead colleague posing a question you have not yet been able to answer.", value=0, weight=0.1),
        _clothes("common", value=0),
        _pouch(10),
    ],
    equipment_gold=10,
    feature=BackgroundFeature(
        name="Researcher",
        description=(
            "When you attempt to learn or recall a piece of lore, if you do "
            "not know that information, you often know where and from whom you "
            "can obtain it. Usually, this information comes from a library, "
            "scriptorium, university, or a sage or other learned person or "
            "creature. Your DM might rule that the knowledge you seek is "
            "secreted away in an almost inaccessible place, or that it simply "
            "cannot be found. Unearthing the deepest secrets of the "
            "multiverse can require an adventure or even a whole campaign."
        ),
    ),
    personality_traits=[
        "I use polysyllabic words that convey the impression of great erudition.",
        "I've read every book in the world's greatest libraries—or I like to boast that I have.",
        "I'm used to helping out those who aren't as smart as I am, and I patiently explain anything and everything to others.",
        "There's nothing I like more than a good mystery.",
    ],
    ideals=[
        "Knowledge. The path to power and self-improvement is through knowledge. (Neutral)",
        "Beauty. What is beautiful points us beyond itself toward what is true. (Good)",
        "Logic. Emotions must not cloud our logical thinking. (Lawful)",
        "Power. Knowledge is the path to power and domination. (Evil)",
    ],
    bonds=[
        "It is my duty to protect my students.",
        "I have an ancient text that holds terrible secrets that must not fall into the wrong hands.",
        "I work to preserve a library, university, scriptorium, or monastery.",
        "My life's work is a series of tomes related to a specific field of lore.",
    ],
    flaws=[
        "I am easily distracted by the promise of information.",
        "Most people scream and run when they see a demon. I stop and take notes on its anatomy.",
        "Unlocking an ancient mystery is more important to me than my own life.",
        "I'm willing to answer any question truthfully, even if it endangers me.",
    ],
))

_register(Background(
    id="sailor",
    name="Sailor",
    description=(
        "You sailed on a seagoing vessel for years, learning to survive the "
        "rigors of the waves and the demands of ship life. The sea is in your "
        "blood."
    ),
    skill_proficiencies=["athletics", "perception"],
    tool_fixed=["navigator_tools", "water_vehicle"],
    languages=[],
    extra_languages=0,
    equipment=[
        _gear("Belaying Pin", "A belaying pin (can be used as a club).", value=0, weight=2.0),
        _gear("Silk Rope", "50 feet of silk rope.", value=10, weight=5.0),
        _gear("Lucky Charm", "A lucky charm such as a rabbit's foot or a small stone.", value=0, weight=0.1),
        _clothes("common", value=0),
        _pouch(10),
    ],
    equipment_gold=10,
    feature=BackgroundFeature(
        name="Ship's Passage",
        description=(
            "When you need to, you can secure free passage on a ship for "
            "yourself and your adventuring companions. You might sail on the "
            "ship you served on, or another ship you have good relations with. "
            "Because you're calling in a favor, you can't be certain of a "
            "schedule or route that meets your every need. In return for your "
            "free passage, you and your companions are expected to assist the "
            "crew in the daily workings of the vessel."
        ),
    ),
    personality_traits=[
        "My friends know they can rely on me, no matter what.",
        "I work hard so that I can play hard when the work is done.",
        "I enjoy sailing into new ports and making new friends over a flagon of ale.",
        "I get bitter if I'm not the center of attention.",
    ],
    ideals=[
        "Respect. The thing that keeps a ship together is mutual respect. (Good)",
        "Fairness. We all do the work, so we all share in the rewards. (Lawful)",
        "Freedom. The sea is freedom—the freedom to go anywhere and do anything. (Chaotic)",
        "Mastery. I'm a predator, and the other ships on the sea are my prey. (Evil)",
    ],
    bonds=[
        "I'm loyal to my captain first, everything else second.",
        "The ship is most important—crewmates and captains come and go.",
        "I'll always remember my first ship.",
        "I've been sailing my whole life, and I've lost many a friend to the sea.",
    ],
    flaws=[
        "I follow orders, even if I think they're wrong.",
        "I'm quite opinionated, and I think anyone who doesn't agree with me is wrong.",
        "I hold a personal grudge against a former captain or crewmate.",
        "I drink to forget the screams of the crew I could not save.",
    ],
))

_register(Background(
    id="pirate",
    name="Pirate",
    description=(
        "A variant of the Sailor background. You sailed under a black flag, "
        "taking what you wanted from those too weak to keep it."
    ),
    skill_proficiencies=["athletics", "perception"],
    tool_fixed=["navigator_tools", "water_vehicle"],
    languages=[],
    extra_languages=0,
    equipment=[
        _gear("Belaying Pin", "A belaying pin (can be used as a club).", value=0, weight=2.0),
        _gear("Silk Rope", "50 feet of silk rope.", value=10, weight=5.0),
        _gear("Lucky Charm", "A lucky charm such as a rabbit's foot or a small stone.", value=0, weight=0.1),
        _clothes("common", value=0),
        _pouch(10),
    ],
    equipment_gold=10,
    variant_of="sailor",
    feature=BackgroundFeature(
        name="Bad Reputation",
        description=(
            "If your character has a sailor background, then this feature "
            "reflects your days as a pirate. No matter where you go, people "
            "are afraid of you due to your reputation. When you are in a "
            "civilized settlement, you can get away with minor criminal "
            "offenses, such as refusing to pay for food at a tavern or "
            "breaking down doors at a local shop, since most people will not "
            "report your activity to the authorities."
        ),
    ),
))

_register(Background(
    id="soldier",
    name="Soldier",
    description=(
        "War has been your life for as long as you care to remember. You "
        "trained as a youth, learned to fight with weapon and discipline, and "
        "saw comrades fall beside you."
    ),
    skill_proficiencies=["athletics", "intimidation"],
    tool_fixed=["land_vehicle"],
    tool_choice={"count": 1, "categories": ["gaming_set"]},
    languages=[],
    extra_languages=0,
    equipment=[
        _gear("Rank Insignia", "An insignia of your military rank.", value=0, weight=0.1),
        _gear("War Trophy", "A trophy taken from a fallen enemy.", value=0, weight=1.0),
        _gear("Dice or Cards", "A set of bone dice or playing cards.", value=1, weight=0.5),
        _clothes("common", value=0),
        _pouch(10),
    ],
    equipment_gold=10,
    feature=BackgroundFeature(
        name="Military Rank",
        description=(
            "You have a military rank from your career as a soldier. Soldiers "
            "loyal to your former military organization still recognize your "
            "authority and influence, and they defer to you if they are of a "
            "lower rank. You can invoke your rank to exert influence over "
            "other soldiers and requisition simple equipment or horses for "
            "temporary use. You can also usually gain access to friendly "
            "military encampments and fortresses where your rank is "
            "recognized."
        ),
    ),
    personality_traits=[
        "I'm always polite and respectful.",
        "I'm haunted by memories of war. I can't get the images of violence out of my mind.",
        "I have a crude sense of humor.",
        "I face problems head-on. A simple, direct solution is the best path to success.",
    ],
    ideals=[
        "Greater Good. Our lot is to lay down our lives in defense of others. (Good)",
        "Responsibility. I do what I must and obey just authority. (Lawful)",
        "Independence. When people follow orders blindly, they embrace a kind of tyranny. (Chaotic)",
        "Might. In life as in war, the stronger force wins. (Evil)",
    ],
    bonds=[
        "I would still lay down my life for the people I served with.",
        "Someone saved my life on the battlefield. To this day, I will never leave a friend behind.",
        "My honor is my life.",
        "I'll never forget the crushing defeat my company suffered or the enemies who dealt it.",
    ],
    flaws=[
        "The monstrous enemy we faced in battle still leaves me quivering with fear.",
        "I have little respect for anyone who is not a proven warrior.",
        "I made a terrible mistake in battle that cost many lives—and I would do anything to keep that mistake secret.",
        "My hatred of my enemies is blind and unreasoning.",
    ],
))

_register(Background(
    id="urchin",
    name="Urchin",
    description=(
        "You grew up on the streets, alone and orphaned. You learned to "
        "survive by your wits, scavenging and stealing to stay alive."
    ),
    skill_proficiencies=["sleight_of_hand", "stealth"],
    tool_fixed=["disguise_kit", "forgery_kit"],
    languages=[],
    extra_languages=0,
    equipment=[
        _gear("Small Knife", "A small knife.", value=0, weight=1.0),
        _gear("City Map", "A map of the city you grew up in.", value=0, weight=0.2),
        _gear("Pet Mouse", "A pet mouse that you taught tricks to.", value=0, weight=0.1),
        _gear("Parents' Token", "A token to remember your parents by.", value=0, weight=0.1),
        _clothes("common", value=0),
        _pouch(10),
    ],
    equipment_gold=10,
    feature=BackgroundFeature(
        name="City Secrets",
        description=(
            "You know the secret patterns and flow to cities, and can find "
            "passages through the urban sprawl that others would miss. When "
            "you are not in combat, you (and companions you lead) can travel "
            "between any two locations in the city twice as fast as your speed "
            "would normally allow."
        ),
    ),
    personality_traits=[
        "I isolate myself from the people around me and resent the way they treat me.",
        "I sleep with a weapon near to hand and a coin purse never far away.",
        "I think of everything in terms of what I can scavenge or steal.",
        "I refuse to take the easy path and always look for the way no one else would go.",
    ],
    ideals=[
        "Respect. All people, rich or poor, deserve respect. (Good)",
        "Community. We have to take care of each other, because no one else will. (Good)",
        "Change. The low are lifted up, and the high are brought down. Change is the nature of things. (Chaotic)",
        "People. I'm loyal to my friends, not to any ideals. (Neutral)",
    ],
    bonds=[
        "My town or city is my home, and I'll fight to defend it.",
        "I sponsor an orphanage to keep other children off the streets.",
        "I owe my survival to another urchin who taught me how to live on the streets.",
        "I stole from the wrong person and I'm always looking over my shoulder.",
    ],
    flaws=[
        "If I'm outnumbered, I will run away from a fight.",
        "I tend to assess social interactions by whether someone could help me get what I want.",
        "I've stolen from people who trusted me, more than once.",
        "People who seem respectable often turn out to be dangerous, and I act on that assumption.",
    ],
))


# --------------------------------------------------------------------------- #
# Public registry accessors
# --------------------------------------------------------------------------- #

def normalize_background(name: str) -> str:
    """Normalize a background name to its lowercase registry key."""
    return (name or "").strip().lower()


def get_background(name: str) -> Optional[Background]:
    """Look up a background by name (None if unknown)."""
    return BACKGROUNDS.get(normalize_background(name))


def background_exists(name: str) -> bool:
    """Whether a background with the given name is registered."""
    return normalize_background(name) in BACKGROUNDS


def list_backgrounds() -> list[Background]:
    """All registered backgrounds (stable insertion order)."""
    return list(BACKGROUNDS.values())


def list_background_names() -> list[str]:
    """Display names of all registered backgrounds."""
    return [bg.name for bg in BACKGROUNDS.values()]


def get_background_feature(name: str) -> Optional[BackgroundFeature]:
    """The background's signature feature, or None."""
    bg = get_background(name)
    return bg.feature if bg else None


def get_background_skills(name: str) -> list[str]:
    """The two skill proficiencies granted by the background (empty if unknown)."""
    bg = get_background(name)
    return list(bg.skill_proficiencies) if bg else []


def get_background_tool_grants(name: str) -> dict:
    """Tool grants in the shape ``{"fixed": [...], "choice": {...}|None}``."""
    bg = get_background(name)
    if not bg:
        return {"fixed": [], "choice": None}
    return bg.tool_grants()


def get_background_languages(name: str) -> tuple[list[str], int]:
    """Return (fixed_languages, extra_language_choices) for a background."""
    bg = get_background(name)
    if not bg:
        return ([], 0)
    return (list(bg.languages), bg.extra_languages)


def get_background_equipment(name: str) -> list[Item]:
    """The starting equipment items for a background (empty if unknown).

    Returns fresh Item instances so callers can add them to an inventory
    without aliasing the registry's canonical objects.
    """
    bg = get_background(name)
    if not bg:
        return []
    # Re-create via to_dict/from_dict to avoid shared mutable Item objects
    return [Item.from_dict(item.to_dict()) for item in bg.equipment]


def get_background_equipment_gold(name: str) -> int:
    """The gold pouch (gp) granted by a background (0 if unknown)."""
    bg = get_background(name)
    return bg.equipment_gold if bg else 0


def background_summary() -> list[dict]:
    """A lightweight summary of every background (id/name/description/skills/feature)."""
    out = []
    for bg in BACKGROUNDS.values():
        out.append({
            "id": bg.id,
            "name": bg.name,
            "description": bg.description,
            "skill_proficiencies": list(bg.skill_proficiencies),
            "feature": bg.feature.name if bg.feature else None,
            "variant_of": bg.variant_of,
        })
    return out
