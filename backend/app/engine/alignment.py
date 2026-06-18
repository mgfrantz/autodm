"""
Alignment system — DnD 5e moral & ethical alignment axes.

In DnD 5e a creature's **alignment** is a broad description of its moral and
personal attitudes. It is built from two independent axes (PHB ch.4
"Personality and Background"):

- **Ethics (Law vs Chaos)** — ``lawful`` / ``neutral`` / ``chaotic``
- **Morals (Good vs Evil)** — ``good`` / ``neutral`` / ``evil``

Each axis has three positions, producing the classic **nine alignments**:

    Lawful Good      Neutral Good     Chaotic Good
    Lawful Neutral   True Neutral     Chaotic Neutral
    Lawful Evil      Neutral Evil     Chaotic Evil

This engine is pure (no DB, no LLM). It provides:

- the canonical nine alignments with descriptions and roleplay hooks
- typical alignment tendencies by race and class (suggestions for character
  creation and DM tailoring — never hard restrictions in 5e)
- inter-alignment **relationship scoring** for NPC reaction hooks
- opposition detection for conflict-driven narration
- a helper to render the alignment context string for DM prompts

Alignment is descriptive, not prescriptive: individuals can vary widely from
their listed norm. The data here is a starting point for roleplay, not a
straightjacket.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# --------------------------------------------------------------------------- #
# Axis values
# --------------------------------------------------------------------------- #

# Ethics axis (order vs freedom)
LAWFUL = "lawful"
NEUTRAL_E = "neutral"
CHAOTIC = "chaotic"

# Morals axis (altruism vs selfishness)
GOOD = "good"
NEUTRAL_M = "neutral"
EVIL = "evil"

ETHICS_VALUES: tuple[str, ...] = (LAWFUL, NEUTRAL_E, CHAOTIC)
MORALS_VALUES: tuple[str, ...] = (GOOD, NEUTRAL_M, EVIL)


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Alignment:
    """A single DnD 5e alignment (one cell of the 3x3 grid)."""
    id: str                       # canonical id, e.g. "lawful_good"
    name: str                     # display name, e.g. "Lawful Good"
    abbreviation: str             # e.g. "LG"
    ethics: str                   # lawful | neutral | chaotic
    morals: str                   # good | neutral | evil
    description: str              # one-paragraph PHB-style description
    roleplay_hooks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "abbreviation": self.abbreviation,
            "ethics": self.ethics,
            "morals": self.morals,
            "description": self.description,
            "roleplay_hooks": list(self.roleplay_hooks),
        }


@dataclass(frozen=True)
class AlignmentRelationship:
    """How one alignment relates to another (for NPC reaction hooks)."""
    other_id: str
    other_name: str
    # Raw per-axis deltas in {-2,-1,0}: 0 = same, 1 = one step, 2 = opposed.
    ethics_delta: int
    morals_delta: int
    total_distance: int           # 0..4, how far apart on the grid
    disposition: str              # friendly / cordial / wary / hostile
    description: str              # human-readable explanation

    def to_dict(self) -> dict:
        return {
            "other_id": self.other_id,
            "other_name": self.other_name,
            "ethics_delta": self.ethics_delta,
            "morals_delta": self.morals_delta,
            "total_distance": self.total_distance,
            "disposition": self.disposition,
            "description": self.description,
        }


# --------------------------------------------------------------------------- #
# The canonical nine alignments (PHB ch.4)
# --------------------------------------------------------------------------- #

ALIGNMENTS: dict[str, Alignment] = {a.id: a for a in [
    Alignment(
        id="lawful_good",
        name="Lawful Good",
        abbreviation="LG",
        ethics=LAWFUL,
        morals=GOOD,
        description=(
            "Lawful Good creatures act as a good person is expected or required "
            "to act. They combine a commitment to oppose evil with the "
            "discipline to fight relentlessly. They tell the truth, keep their "
            "word, help those in need, and speak out against injustice. "
            "Lawful Good is the best alignment for someone who honors the "
            "spirit as well as the letter of the law."
        ),
        roleplay_hooks=[
            "Upholds a personal or societal code of honour above all else.",
            "Will not break an oath or abandon the innocent, even at great cost.",
            "Seeks to reform corrupt institutions from within rather than topple them.",
            "Mentally profiles everyone: ally, victim, or lawbreaker.",
        ],
    ),
    Alignment(
        id="neutral_good",
        name="Neutral Good",
        abbreviation="NG",
        ethics=NEUTRAL_E,
        morals=GOOD,
        description=(
            "Neutral Good creatures do the best that a good person can do. "
            "They are devoted to helping others, working with kings and "
            "magistrates but not feeling beholden to them. They have no "
            "particular objection to working against a bad law if doing so "
            "would help people. Neutral Good is the best alignment for someone "
            "who is driven by conscience above both law and chaos."
        ),
        roleplay_hooks=[
            "Helps others regardless of whether the law permits it.",
            "Pragmatic about means; focused on the good outcome.",
            "Mediates between rigid order and reckless freedom.",
            "Quietly reliable — the one who shows up when it matters.",
        ],
    ),
    Alignment(
        id="chaotic_good",
        name="Chaotic Good",
        abbreviation="CG",
        ethics=CHAOTIC,
        morals=GOOD,
        description=(
            "Chaotic Good creatures act as their conscience directs with "
            "little regard for what others expect. They believe in goodness "
            "and right but have little use for laws and regulations, which "
            "they see as needlessly restrictive. They follow their own moral "
            "compass, which, though well-intentioned, may not agree with the "
            "prevailing view of society. Chaotic Good is the best alignment "
            "for free spirits whose heart is in the right place."
        ),
        roleplay_hooks=[
            "Defies unjust authority and breaks oppressive rules to do right.",
            "Values individual freedom over institutional order.",
            "Mistrustful of organised power, even benevolent-seeming power.",
            "A Robin Hood: generous to the downtrodden, reckless with the law.",
        ],
    ),
    Alignment(
        id="lawful_neutral",
        name="Lawful Neutral",
        abbreviation="LN",
        ethics=LAWFUL,
        morals=NEUTRAL_M,
        description=(
            "Lawful Neutral creatures act in accordance with law, tradition, "
            "or personal codes. Many monks and some wizards follow this path. "
            "Order and organisation are paramount: the rules matter more than "
            "who they help or harm. Lawful Neutral is the best alignment for "
            "someone who is reliable and honourable, but without being "
            "particularly good-hearted."
        ),
        roleplay_hooks=[
            "Follows the letter of the law or a personal code, indifferent to good or evil.",
            "A judge, bureaucrat, or mercenary who honours every contract.",
            "Dislikes chaos and disorder on principle.",
            "Treats friends and enemies by the same impartial standard.",
        ],
    ),
    Alignment(
        id="neutral",
        name="True Neutral",
        abbreviation="N",
        ethics=NEUTRAL_E,
        morals=NEUTRAL_M,
        description=(
            "True Neutral creatures do what seems natural to them, without "
            "prejudice or compulsion. They lack any commitment to maintaining "
            "order or tearing it down, and have no strong bent toward helping "
            "or harming others. Many animals and creatures of the wild act "
            "this way, as do some druids who seek to balance all things. True "
            "Neutral is the best alignment for someone who takes a neutral, "
            "balanced view of the world."
        ),
        roleplay_hooks=[
            "Acts from instinct, survival, or careful balance rather than ideology.",
            "Sees good/evil and law/chaos as passing forces, not crusades.",
            "A druid defending nature's balance, or an animal following its nature.",
            "Swings toward whichever side is losing to keep equilibrium.",
        ],
    ),
    Alignment(
        id="chaotic_neutral",
        name="Chaotic Neutral",
        abbreviation="CN",
        ethics=CHAOTIC,
        morals=NEUTRAL_M,
        description=(
            "Chaotic Neutral creatures follow their whims, holding their "
            "personal freedom above all else. Many barbarians and rogues, and "
            "some bards, fall into this alignment. They value their own "
            "liberty but do not actively strive to protect others' freedom. "
            "Chaotic Neutral is the best alignment for free spirits who prize "
            "independence above both order and altruism."
        ),
        roleplay_hooks=[
            "Drinks freedom like water and resents being told what to do.",
            "Unpredictable — noble one moment, selfish the next.",
            "Neither malicious nor charitable; simply self-directed.",
            "A mercenary who takes the job that sounds most interesting today.",
        ],
    ),
    Alignment(
        id="lawful_evil",
        name="Lawful Evil",
        abbreviation="LE",
        ethics=LAWFUL,
        morals=EVIL,
        description=(
            "Lawful Evil creatures methodically take what they want within a "
            "code of tradition, loyalty, or order. Devils are the canonical "
            "example. They play by the rules but without mercy or compassion, "
            "and they expect others to serve them. Lawful Evil is the best "
            "alignment for someone who is a methodical conqueror or tyrant who "
            "imposes order through fear."
        ),
        roleplay_hooks=[
            "Honours contracts and hierarchy — but twists them to dominate others.",
            "A tyrant, crime lord, or devil who weaponises the rules.",
            "Loyal to an organisation or cause that serves their ambition.",
            "Keeps their word to the letter while engineering ruin.",
        ],
    ),
    Alignment(
        id="neutral_evil",
        name="Neutral Evil",
        abbreviation="NE",
        ethics=NEUTRAL_E,
        morals=EVIL,
        description=(
            "Neutral Evil creatures are the definition of pure, uncompromising "
            "selfishness. They do whatever they can get away with, without "
            "compassion or qualms. Many drow, some ogres, and various "
            "monsters fall here. They have no love of order and no objection "
            "to chaos. Neutral Evil is the best alignment for someone who "
            "cares only about themselves and will harm others to get ahead."
        ),
        roleplay_hooks=[
            "Coldly self-serving — betrays anyone when convenient.",
            "No loyalty to law or freedom, only to personal gain.",
            "Calculates the most profitable betrayal at every turn.",
            "A hired killer or thief with no ideology beyond the coin.",
        ],
    ),
    Alignment(
        id="chaotic_evil",
        name="Chaotic Evil",
        abbreviation="CE",
        ethics=CHAOTIC,
        morals=EVIL,
        description=(
            "Chaotic Evil creatures act with arbitrary violence, spurred by "
            "greed, hatred, or destructive bloodlust. Demons and many "
            "monstrous humanoids follow this path. They have no plan beyond "
            "wreaking havoc, and no regard for life, freedom, or order. "
            "Chaotic Evil is the best alignment for destroyers whose only goal "
            "is ruin."
        ),
        roleplay_hooks=[
            "Burns the world for the pleasure of the flames.",
            "Trusts no one, plans nothing, and revels in cruelty.",
            "The berserker or demon who kills because it can.",
            "Cannot be reasoned with, bargained with, or contained.",
        ],
    ),
]}


# Stable display order: the classic grid (good row, neutral row, evil row;
# lawful → chaotic within each row).
_ALIGNMENT_ORDER: tuple[str, ...] = (
    "lawful_good", "neutral_good", "chaotic_good",
    "lawful_neutral", "neutral", "chaotic_neutral",
    "lawful_evil", "neutral_evil", "chaotic_evil",
)


# --------------------------------------------------------------------------- #
# Normalization & lookup
# --------------------------------------------------------------------------- #

def _normalize(value: Optional[str]) -> str:
    """Lowercase + collapse whitespace so lookups are forgiving."""
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def get_alignment(name: Optional[str]) -> Optional[Alignment]:
    """Look up an alignment by id, name, or abbreviation (case-insensitive).

    Accepts ``"lawful good"``, ``"Lawful Good"``, ``"lawful_good"``,
    ``"LG"``, ``"lg"`` etc. Returns ``None`` for unknown values.
    """
    key = _normalize(name)
    if not key:
        return None
    # Direct id match (handles "lawful_good" and "lawful good")
    normalized_key = key.replace(" ", "_")
    if normalized_key in ALIGNMENTS:
        return ALIGNMENTS[normalized_key]
    # Special case: plain "neutral" or "true neutral" / "tn" → true neutral
    if normalized_key in ("neutral", "true_neutral") or key in ("n", "tn"):
        return ALIGNMENTS["neutral"]
    # Name match
    for a in ALIGNMENTS.values():
        if _normalize(a.name) == key:
            return a
    # Abbreviation match
    for a in ALIGNMENTS.values():
        if a.abbreviation.lower() == key:
            return a
    return None


def get_alignment_or_default(name: Optional[str], default: str = "neutral") -> Alignment:
    """Like ``get_alignment`` but always returns an alignment (default True Neutral).

    If ``default`` itself is unknown, falls back to True Neutral so this never
    raises for any input.
    """
    a = get_alignment(name)
    if a is not None:
        return a
    fallback = get_alignment(default)
    return fallback if fallback is not None else ALIGNMENTS["neutral"]


def alignment_exists(name: Optional[str]) -> bool:
    return get_alignment(name) is not None


def is_valid_alignment(name: Optional[str]) -> bool:
    return get_alignment(name) is not None


def list_alignments() -> list[Alignment]:
    """All nine alignments in canonical grid order."""
    return [ALIGNMENTS[a] for a in _ALIGNMENT_ORDER]


def list_alignment_summaries() -> list[dict]:
    """Lightweight summary list (for pickers / API listing)."""
    return [
        {
            "id": a.id,
            "name": a.name,
            "abbreviation": a.abbreviation,
            "ethics": a.ethics,
            "morals": a.morals,
            "description": a.description,
        }
        for a in list_alignments()
    ]


# --------------------------------------------------------------------------- #
# Relationship / conflict scoring
# --------------------------------------------------------------------------- #

def _axis_index(axis_value: str, axis: tuple[str, ...]) -> int:
    """Position (0/1/2) of an axis value, defensive against junk."""
    try:
        return axis.index(axis_value)
    except ValueError:
        return 1  # treat unknown as neutral


def _axis_delta(a: str, b: str, axis: tuple[str, ...]) -> int:
    """Absolute step distance along one axis (0 = same, 2 = fully opposed)."""
    return abs(_axis_index(a, axis) - _axis_index(b, axis))


def _disposition(total_distance: int) -> tuple[str, str]:
    """Map a grid distance (0-4) to a disposition label + description."""
    if total_distance <= 0:
        return ("friendly", "Shares the same worldview — natural allies who see eye to eye.")
    if total_distance == 1:
        return ("cordial", "Close in outlook; minor friction but broadly compatible.")
    if total_distance == 2:
        return ("wary", "Differ on at least one axis — tension and mutual suspicion.")
    if total_distance == 3:
        return ("tense", "Strongly opposed; cooperation requires extraordinary cause.")
    return ("hostile", "Diametrically opposed worldviews — outright hostility is likely.")


def relationship(a: Optional[str], b: Optional[str]) -> Optional[AlignmentRelationship]:
    """Score how alignment ``a`` relates to alignment ``b``.

    Returns ``None`` if either alignment is unknown. Distance is the sum of
    the per-axis step deltas (0-4): 0 = identical, 4 = lawful-good vs
    chaotic-evil (the two corners).
    """
    align_a = get_alignment(a)
    align_b = get_alignment(b)
    if align_a is None or align_b is None:
        return None

    ethics_delta = _axis_delta(align_a.ethics, align_b.ethics, ETHICS_VALUES)
    morals_delta = _axis_delta(align_a.morals, align_b.morals, MORALS_VALUES)
    total = ethics_delta + morals_delta
    disposition, description = _disposition(total)
    return AlignmentRelationship(
        other_id=align_b.id,
        other_name=align_b.name,
        ethics_delta=ethics_delta,
        morals_delta=morals_delta,
        total_distance=total,
        disposition=disposition,
        description=description,
    )


def are_opposed(a: Optional[str], b: Optional[str]) -> bool:
    """True when two alignments are fully opposed on at least one axis.

    Good vs Evil and Lawful vs Chaotic both count. Useful for quick
    conflict detection (e.g. a Good-aligned NPC should distrust an
    Evil-aligned one).
    """
    rel = relationship(a, b)
    if rel is None:
        return False
    return rel.ethics_delta == 2 or rel.morals_delta == 2


def share_axis(a: Optional[str], b: Optional[str]) -> bool:
    """True when two alignments agree on at least one axis (ethics or morals)."""
    rel = relationship(a, b)
    if rel is None:
        return False
    return rel.ethics_delta == 0 or rel.morals_delta == 0


# --------------------------------------------------------------------------- #
# Tendencies: typical alignments by race and class (suggestions only)
# --------------------------------------------------------------------------- #

# Typical / typical-suggested alignments per race (PHB racial descriptions).
# Listed most-typical first. These are flavour suggestions, never restrictions
# in DnD 5e.
RACE_TENDENCIES: dict[str, list[str]] = {
    "human": ["neutral", "lawful_good", "chaotic_good", "lawful_neutral", "chaotic_neutral"],
    "elf": ["chaotic_good", "neutral_good", "chaotic_neutral"],
    "dwarf": ["lawful_good", "lawful_neutral", "neutral_good"],
    "halfling": ["lawful_good", "neutral_good", "neutral"],
    "gnome": ["neutral_good", "lawful_good", "chaotic_good"],
    "half_elf": ["chaotic_good", "neutral_good", "chaotic_neutral"],
    "half_orc": ["chaotic_neutral", "chaotic_evil", "neutral"],
    "tiefling": ["chaotic_neutral", "chaotic_evil", "neutral_evil", "lawful_evil"],
    "dragonborn": ["lawful_good", "neutral", "lawful_neutral"],
}

# Typical alignments per class (drawn from PHB class flavour text).
CLASS_TENDENCIES: dict[str, list[str]] = {
    "barbarian": ["chaotic_neutral", "chaotic_good", "neutral"],
    "bard": ["chaotic_good", "chaotic_neutral", "neutral_good"],
    "cleric": ["lawful_good", "neutral_good", "lawful_neutral"],
    "druid": ["neutral", "neutral_good", "chaotic_neutral"],
    "fighter": ["lawful_good", "neutral", "lawful_neutral", "chaotic_neutral"],
    "monk": ["lawful_good", "lawful_neutral", "lawful_evil"],
    "paladin": ["lawful_good", "neutral_good", "lawful_neutral"],
    "ranger": ["chaotic_good", "neutral", "chaotic_neutral", "neutral_good"],
    "rogue": ["chaotic_neutral", "chaotic_good", "neutral_evil", "neutral"],
    "sorcerer": ["chaotic_good", "chaotic_neutral", "neutral_good"],
    "warlock": ["chaotic_evil", "lawful_evil", "chaotic_neutral", "neutral"],
    "wizard": ["lawful_neutral", "neutral", "neutral_good", "chaotic_good"],
}


def get_race_tendencies(race: Optional[str]) -> list[str]:
    """Suggested alignments for a race (ids), defensive lookup.

    Handles ``half-orc``/``half orc``/``Half-Orc`` uniformly.
    """
    key = _normalize(race).replace(" ", "_").replace("-", "_")
    return list(RACE_TENDENCIES.get(key, []))


def get_class_tendencies(char_class: Optional[str]) -> list[str]:
    """Suggested alignments for a class (ids), defensive lookup."""
    key = _normalize(char_class).replace(" ", "_").replace("-", "_")
    return list(CLASS_TENDENCIES.get(key, []))


def suggested_alignments(
    race: Optional[str],
    char_class: Optional[str],
) -> list[str]:
    """Merge race + class tendencies into a de-duplicated suggestion list.

    Alignments suggested by *both* race and class come first (strongest
    signal), followed by the rest. Returns alignment ids.
    """
    race_ids = get_race_tendencies(race)
    class_ids = get_class_tendencies(char_class)
    seen: set[str] = set()
    merged: list[str] = []
    # Both agree first
    for a in race_ids:
        if a in class_ids and a not in seen:
            merged.append(a)
            seen.add(a)
    # Then the rest, race first then class
    for a in race_ids + class_ids:
        if a not in seen:
            merged.append(a)
            seen.add(a)
    return merged


# --------------------------------------------------------------------------- #
# DM context helpers
# --------------------------------------------------------------------------- #

def alignment_context(name: Optional[str]) -> str:
    """Render a short alignment context string for DM prompts.

    Empty string for unknown/missing alignment so callers can safely splice it
    into a prompt without extra guards.
    """
    a = get_alignment(name)
    if a is None:
        return ""
    hooks = "; ".join(a.roleplay_hooks[:2])
    return f"{a.name} ({a.abbreviation}) — {a.description} Roleplay: {hooks}"


def dm_prompt_summary(name: Optional[str]) -> str:
    """A one-line alignment summary suitable for the DM's character context."""
    a = get_alignment(name)
    if a is None:
        return ""
    return f"{a.name} ({a.abbreviation})"


# --------------------------------------------------------------------------- #
# Compatibility helpers for NPC interaction
# --------------------------------------------------------------------------- #

def npc_reaction_summary(
    character_alignment: Optional[str],
    npc_alignment: Optional[str],
) -> Optional[str]:
    """A human-readable sentence describing how an NPC might react to the PC.

    Returns ``None`` if either alignment is unknown. Intended as a DM hook for
    colouring social encounters based on alignment friction.
    """
    rel = relationship(character_alignment, npc_alignment)
    if rel is None:
        return None
    char = get_alignment(character_alignment)
    npc = get_alignment(npc_alignment)
    # Both are guaranteed non-None because relationship() returned a value.
    char_name = char.name if char else "unknown"
    npc_name = npc.name if npc else "unknown"
    return (
        f"A {npc_name} NPC tends to feel {rel.disposition} toward a "
        f"{char_name} character. {rel.description}"
    )
