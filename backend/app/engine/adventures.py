"""
Curated starter adventures — hand-authored worlds that work out-of-the-box
without an LLM key.

Each :class:`StarterAdventure` produces a ``world_data`` dict that is
shape-compatible with the LLM-generated world (see
``WorldGenerationModule.to_world_dict``), so the existing game-start and
player-action endpoints work unchanged.  Players can pick a curated
adventure instead of asking the DM to generate a world — useful for a
consistent first-run experience or when no LLM provider is configured.

The registry is a plain module-level list (``STARTER_ADVENTURES``) so new
adventures can be added by appending a :class:`StarterAdventure` instance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StarterAdventure:
    """A hand-authored, ready-to-play adventure world."""

    id: str
    name: str
    tagline: str
    blurb: str
    tone: str
    recommended_level: int = 1
    tags: tuple[str, ...] = ()
    # Full world_data payload (shape-compatible with the LLM generator).
    world_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, include_world_data: bool = True) -> dict[str, Any]:
        """Serialise for API responses.

        ``include_world_data=False`` omits the (potentially large) world
        payload — used by the list endpoint so listings stay light.
        """
        out: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "tagline": self.tagline,
            "blurb": self.blurb,
            "tone": self.tone,
            "recommended_level": self.recommended_level,
            "tags": list(self.tags),
        }
        if include_world_data:
            out["world_data"] = self.world_data
        return out


# ---------------------------------------------------------------------------
# Curated adventures
# ---------------------------------------------------------------------------

_CURSED_MINES_DATA: dict[str, Any] = {
    "name": "The Cursed Mines of Emberdeep",
    "description": (
        "The dwarven stronghold of Emberdeep once flowed with gold and iron, "
        "until the miners broke through into a forgotten cavern and woke "
        "something ancient. Now the mine has fallen silent, the few survivors "
        "speak of living shadows, and the nearby town of Oakhollow fears the "
        "darkness will spread. A reward waits for anyone brave enough to "
        "descend and discover the fate of Emberdeep."
    ),
    "tone": "heroic fantasy",
    "regions": [
        {
            "name": "Oakhollow Vale",
            "description": "A peaceful farming valley in the shadow of the Emberpeak range.",
            "terrain": "hills",
            "settlements": ["Oakhollow"],
            "dangers": ["wolves", "bandits"],
            "coordinates": [0.4, 0.6],
            "connections": ["Emberpeak Mountains"],
        },
        {
            "name": "Emberpeak Mountains",
            "description": "Jagged peaks riddled with dwarven tunnels and abandoned mines.",
            "terrain": "mountain",
            "settlements": ["Emberdeep (abandoned)"],
            "dangers": ["living shadows", "corrupted dwarves", "cave oozes"],
            "coordinates": [0.5, 0.3],
            "connections": ["Oakhollow Vale", "The Sunless Deeps"],
        },
        {
            "name": "The Sunless Deeps",
            "description": "A vast cavern system beneath the mountains, source of the curse.",
            "terrain": "underground",
            "settlements": [],
            "dangers": ["shadow cultists", "the Forgotten One"],
            "coordinates": [0.5, 0.5],
            "connections": ["Emberpeak Mountains"],
        },
    ],
    "campaign_arc": {
        "central_conflict": "An ancient shadow entity sealed beneath Emberdeep has been awakened.",
        "act_1": "Investigate the silent mine, rescue survivors, and learn the source of the curse.",
        "act_2": "Descend into the Sunless Deeps and confront the shadow cult feeding the entity.",
        "act_3": "Seal (or destroy) the Forgotten One before the darkness spreads to Oakhollow.",
    },
    "starting_settlement": {
        "name": "Oakhollow",
        "description": "A stout-walled farming town of three hundred souls, built around a mossy old well. The inn, The Pick & Lantern, is where rumors and jobs change hands.",
        "notable_locations": ["The Pick & Lantern (inn)", "Mayor Thilda's Hall", "The Old Well", "Emberdeep Trailhead"],
    },
    "npcs": [
        {"name": "Mayor Thilda Brokestone", "role": "Town mayor; offers the reward for clearing the mine", "motivation": "Protect her people and restore the town's trade"},
        {"name": "Borrum Ironvein", "role": "Surviving miner; sole witness to the cave-in", "motivation": "Wants revenge for his fallen brethren"},
        {"name": "Sister Lyra", "role": "Cleric of the Morninglord; healer at the shrine", "motivation": "Sense the curse is unnatural and must be ended"},
        {"name": "Grenda Stoneback", "role": "Dwarven prospector and guide", "motivation": "Reclaim Emberdeep for her clan"},
        {"name": "Vael the Quiet", "role": "Mysterious traveler who knows too much", "motivation": "Secretly a former shadow cultist seeking redemption"},
    ],
    "factions": [
        {"name": "The Emberdeep Clan", "goal": "Reclaim their ancestral mine and seal the darkness", "alignment": "lawful good"},
        {"name": "The Whispering Shadow", "goal": "Free the Forgotten One and drown the surface in darkness", "alignment": "chaotic evil"},
    ],
    "hook": (
        "You arrive in Oakhollow as dusk falls. The streets are emptier than "
        "they should be. At The Pick & Lantern, a grim-faced woman pins a "
        "parchment to the door: *500 gold to whoever ends the curse of "
        "Emberdeep.* She looks up at you and asks, plainly, whether you intend "
        "to answer."
    ),
}

_EMBERDEEP = StarterAdventure(
    id="cursed-mines",
    name="The Cursed Mines of Emberdeep",
    tagline="A classic dungeon crawl — dwarven ruins, a shadow curse, and a town in need of heroes.",
    blurb=(
        "When the dwarven mine of Emberdeep broke into a sealed cavern, "
        "something woke. The town of Oakhollow offers gold to anyone who "
        "will descend and end the curse. A beginner-friendly dungeon "
        "adventure with investigation, combat, and a moral choice at the end."
    ),
    tone="heroic fantasy",
    recommended_level=1,
    tags=("dungeon", "dwarves", "investigation", "classic"),
    world_data=_CURSED_MINES_DATA,
)


_HOLLOW_MOOR_DATA: dict[str, Any] = {
    "name": "The Whispering Moor",
    "description": (
        "The moorland of Dunhollow has always been a place of fog and old "
        "superstition, but lately the dead have stopped resting. livestock "
        "vanish, travelers speak of lights in the bogs, and the village "
        "gravedigger swears he has buried the same man twice. Something in "
        "the old barrow has stirred, and the moor is creeping toward the "
        "village one foggy night at a time."
    ),
    "tone": "gothic horror",
    "regions": [
        {
            "name": "Dunhollow Village",
            "description": "A dreary hamlet of slate roofs and narrow lanes, perpetually damp.",
            "terrain": "marsh",
            "settlements": ["Dunhollow"],
            "dangers": ["restless dead", "bog mists"],
            "coordinates": [0.3, 0.5],
            "connections": ["The Whispering Moor"],
        },
        {
            "name": "The Whispering Moor",
            "description": "A vast fog-shrouded bog dotted with ancient standing stones and sunken barrows.",
            "terrain": "swamp",
            "settlements": ["The Hag's Hut (rumored)"],
            "dangers": ["will-o'-wisps", "bog zombies", "will o'the wisps"],
            "coordinates": [0.6, 0.5],
            "connections": ["Dunhollow Village", "The Barrow Downs"],
        },
        {
            "name": "The Barrow Downs",
            "description": "Grass-covered burial mounds older than memory, where the first kings were laid to rest.",
            "terrain": "hills",
            "settlements": [],
            "dangers": ["wights", "the Barrow King"],
            "coordinates": [0.7, 0.3],
            "connections": ["The Whispering Moor"],
        },
    ],
    "campaign_arc": {
        "central_conflict": "A necromancer has reawakened the Barrow King, whose influence is raising the moor's dead.",
        "act_1": "Investigate the disappearances in Dunhollow and learn what stirs on the moor.",
        "act_2": "Cross the treacherous bog, survive its haunts, and find the barrow entrance.",
        "act_3": "Defeat the Barrow King and his necromancer master to put the dead to rest.",
    },
    "starting_settlement": {
        "name": "Dunhollow",
        "description": "A gloomy village of fifty families huddled against the moor. Candles burn in every window, and doors are barred before sundown. The Drowned Rat tavern is the only place that welcomes strangers.",
        "notable_locations": ["The Drowned Rat (tavern)", "The Chapel of the Mournful Vigil", "Old Garrick's Graveyard", "The Moor Road"],
    },
    "npcs": [
        {"name": "Elder Mortimer Crane", "role": "Village elder; desperate for outside help", "motivation": "Save his village before the dead walk its streets"},
        {"name": "Helga Crowfoot", "role": "The reclusive hedge-witch of the moor's edge", "motivation": "Knows the barrow's history but fears to speak of it"},
        {"name": "Constable Bram", "role": "The overworked village watchman", "motivation": "Keep order as panic spreads"},
        {"name": "Sister Marisol", "role": "The last priest of the failing chapel", "motivation": "Her faith is being tested by the rising dead"},
        {"name": "The Drowned Man", "role": "A ghostly figure seen on the moor at night", "motivation": "A tragic soul trying to warn the living"},
    ],
    "factions": [
        {"name": "The Vigil of the Mournful", "goal": "Maintain the old rites that keep the dead sleeping", "alignment": "lawful neutral"},
        {"name": "The Cult of the Barrow King", "goal": "Raise an undead army from the ancient dead", "alignment": "neutral evil"},
    ],
    "hook": (
        "Your coach loses a wheel a mile from Dunhollow, forcing you to walk "
        "the rest in thickening fog. As you near the village, a cold hand "
        "closes on your ankle — a corpse, half-buried in the peat, is "
        "clawing its way toward the road. Behind you, more shapes rise from "
        "the bog. The village lights flicker ahead. Run, or stand and fight?"
    ),
}

_HOLLOW_MOOR = StarterAdventure(
    id="whispering-moor",
    name="The Whispering Moor",
    tagline="A gothic horror mystery — restless dead, a haunted bog, and secrets beneath the barrows.",
    blurb=(
        "The dead of Dunhollow have stopped resting. Cross a fog-shrouded "
        "moor, unravel a necromantic plot, and face the ancient Barrow King. "
        "An atmospheric mystery-horror adventure heavier on investigation "
        "and dread than on open combat."
    ),
    tone="gothic horror",
    recommended_level=2,
    tags=("mystery", "undead", "gothic", "swamp"),
    world_data=_HOLLOW_MOOR_DATA,
)


_SHATTERED_Spires_DATA: dict[str, Any] = {
    "name": "The Shattered Spires",
    "description": (
        "A century ago the floating city of Aetheria shattered and rained "
        "ruin across the land. Now scavengers pick through the fallen "
        "spires for relics of the old magocracy, and a warlord has begun "
        "assembling the pieces — seeking to reassemble a weapon that "
        "leveled a civilization. The race is on to reach the heart of the "
        "ruins before he does."
    ),
    "tone": "high magic",
    "regions": [
        {
            "name": "Lantern's Reach",
            "description": "A boomtown built on the edge of the ruins, where scavengers trade salvage for coin.",
            "terrain": "plains",
            "settlements": ["Lantern's Reach"],
            "dangers": ["salvage bandits", "unstable magic"],
            "coordinates": [0.5, 0.7],
            "connections": ["The Fallen Spires"],
        },
        {
            "name": "The Fallen Spires",
            "description": "Towering fragments of the shattered city, still humming with dormant magic and patrolled by old constructs.",
            "terrain": "ruins",
            "settlements": ["The Spire Camp (warlord's base)"],
            "dangers": ["arcane guardians", "wild magic zones", "warlord's soldiers"],
            "coordinates": [0.5, 0.5],
            "connections": ["Lantern's Reach", "The Core"],
        },
        {
            "name": "The Core",
            "description": "The fused heart of Aetheria, where the city's power source still burns cold and blue.",
            "terrain": "ruins",
            "settlements": [],
            "dangers": ["the Shatterlord", "mana storms"],
            "coordinates": [0.5, 0.35],
            "connections": ["The Fallen Spires"],
        },
    ],
    "campaign_arc": {
        "central_conflict": "Warlord Kaelen Vorsh aims to reactivate the Aetherian Core as a weapon of conquest.",
        "act_1": "Reach Lantern's Reach, gather intelligence on Vorsh's plans, and secure passage into the ruins.",
        "act_2": "Navigate the Fallen Spires, overcome his forces and the city's lingering defenses, and find the Core.",
        "act_3": "Reach the Core before Vorsh and decide the fate of a weapon that destroyed a civilization.",
    },
    "starting_settlement": {
        "name": "Lantern's Reach",
        "description": "A sprawling, lawless boomtown of tents, scaffolding, and salvaged stone. Lanterns hang from every beam, giving the town its name. The Broken Compass saloon is where deals are struck and secrets sold.",
        "notable_locations": ["The Broken Compass (saloon)", "The Salvager's Market", "Magistrate's Tent", "The Ruin Road"],
    },
    "npcs": [
        {"name": "Magistrate Sera Voss", "role": "The town's reluctant authority; wants the ruins kept stable", "motivation": "Prevent another catastrophe and keep trade flowing"},
        {"name": "Old Pell", "role": "A half-mad salvage veteran who survived the Core's outer wards", "motivation": "Warn people off — but knows the way in"},
        {"name": "Tessa Quick", "role": "A rival scavenger and sometime ally", "motivation": "Get rich, but not die trying"},
        {"name": "Warlord Kaelen Vorsh", "role": "The antagonist; assembling the weapon", "motivation": "Believes the Core will let him unite the warring lands by force"},
        {"name": "Echo", "role": "A fragmented intelligence — a ghost of Aetheria's old governing mind", "motivation": "Wants the Core shut down forever, or to be made whole again"},
    ],
    "factions": [
        {"name": "The Salvager's Guild", "goal": "Profit from the ruins while keeping them from exploding again", "alignment": "neutral"},
        {"name": "Vorsh's Legion", "goal": "Reactivate the Core and use it to conquer the region", "alignment": "lawful evil"},
    ],
    "hook": (
        "You arrive in Lantern's Reach to find the town buzzing: Warlord "
        "Vorsh's soldiers have sealed the Ruin Road, and rumor says he's "
        "found the path to the Core. At the Broken Compass, a nervous "
        "salvager slides into the seat across from you and whispers that he "
        "knows another way in — for a price."
    ),
}

_SHATTERED_SPIRES = StarterAdventure(
    id="shattered-spires",
    name="The Shattered Spires",
    tagline="A high-magic adventure — fallen arcane ruins, salvage politics, and a weapon that leveled a city.",
    blurb=(
        "A century after the floating magocracy of Aetheria shattered, a "
        "warlord races to reactivate its world-ending Core. Scavenge the "
        "fallen spires, navigate wild magic and old constructs, and decide "
        "the fate of a weapon of mass destruction. Best for characters who "
        "like exploration, faction politics, and hard choices."
    ),
    tone="high magic",
    recommended_level=3,
    tags=("ruins", "magic", "exploration", "faction-politics"),
    world_data=_SHATTERED_Spires_DATA,
)


# The public registry — append new adventures here.
STARTER_ADVENTURES: list[StarterAdventure] = [
    _EMBERDEEP,
    _HOLLOW_MOOR,
    _SHATTERED_SPIRES,
]


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def _index() -> dict[str, StarterAdventure]:
    return {a.id: a for a in STARTER_ADVENTURES}


def list_adventures() -> list[StarterAdventure]:
    """Return all curated starter adventures."""
    return list(STARTER_ADVENTURES)


def get_adventure(adventure_id: str) -> StarterAdventure | None:
    """Return a single adventure by id, or ``None`` if not found."""
    return _index().get(adventure_id)


def world_data_for(adventure_id: str) -> dict[str, Any] | None:
    """Return the world_data payload for an adventure, or ``None``."""
    adv = get_adventure(adventure_id)
    if adv is None:
        return None
    # Return a deep-ish copy so callers can mutate freely.
    return {k: (list(v) if isinstance(v, list) else v) for k, v in adv.world_data.items()}
