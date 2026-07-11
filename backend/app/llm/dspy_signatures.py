"""DSPy signatures for character creation."""
import dspy

class GenerateCharacterFlavor(dspy.Signature):
    """You are an expert DnD 5e character creator. Given a character's
    identity (race, class, background, alignment) and ability scores,
    generate a fitting name AND a cohesive, vivid personality profile in
    the DnD 5e tradition: a backstory, two personality traits, one ideal,
    one bond, and one flaw. Make every element — including the name —
    reflect the character's race, class, background, alignment, and
    standout abilities.
    Tone: heroic fantasy — epic, personal, with real stakes."""

    race: str = dspy.InputField(desc="Character race (e.g. Human, Elf, Dwarf)")
    char_class: str = dspy.InputField(desc="Character class (e.g. Fighter, Wizard)")
    background: str = dspy.InputField(desc="Character background (e.g. Soldier, Sage)")
    alignment: str = dspy.InputField(desc="Alignment id (e.g. lawful_good, chaotic_neutral)")
    level: int = dspy.InputField(desc="Character level", default=1)
    strength: int = dspy.InputField(desc="Strength ability score 3-20")
    dexterity: int = dspy.InputField(desc="Dexterity ability score 3-20")
    constitution: int = dspy.InputField(desc="Constitution ability score 3-20")
    intelligence: int = dspy.InputField(desc="Intelligence ability score 3-20")
    wisdom: int = dspy.InputField(desc="Wisdom ability score 3-20")
    charisma: int = dspy.InputField(desc="Charisma ability score 3-20")

    name: str = dspy.OutputField(desc="A fitting character name reflecting race/class/background")
    backstory: str = dspy.OutputField(desc="2-3 paragraph character backstory")
    personality_traits: list[str] = dspy.OutputField(desc="Exactly two personality trait descriptions")
    ideal: str = dspy.OutputField(desc="One core ideal the character holds dear")
    bond: str = dspy.OutputField(desc="One bond linking the character to the world")
    flaw: str = dspy.OutputField(desc="One character flaw or weakness")


class GenerateWorld(dspy.Signature):
    """You are a world-building expert for DnD 5e single-player campaigns.
    Given a desired tone and optional character-tailoring context,
    generate a complete, living world: a unique name, an evocative
    description, 3-5 connected regions, a three-act campaign arc, a
    starting settlement, 5-8 key NPCs, 2-3 competing factions, and an
    immediate adventure hook. The world should feel alive and reactive.

    Regions must include coordinates (normalized [x, y] in 0..1) and
    connections (names of adjacent regions) so they can be laid out on
    a map. Make every element reflect the requested tone and, when
    provided, the player's character."""

    tone: str = dspy.InputField(desc="Desired tone, e.g. 'heroic fantasy', 'dark grimdark'")
    character_context: str = dspy.InputField(desc="Optional character info to tailor the world to the player", default="")

    name: str = dspy.OutputField(desc="Unique, evocative world/campaign name")
    description: str = dspy.OutputField(desc="2-3 paragraph world description setting the stage")
    world_tone: str = dspy.OutputField(desc="The resulting tone / atmosphere of the world")
    regions: list[dict] = dspy.OutputField(desc="3-5 regions; each a dict with keys: name, description, terrain, settlements (list[str]), dangers (list[str]), coordinates ([x,y] in 0..1), connections (list[str] of adjacent region names)")
    campaign_arc: dict = dspy.OutputField(desc="Dict with keys: central_conflict, act_1, act_2, act_3")
    starting_settlement: dict = dspy.OutputField(desc="Dict with keys: name, description, notable_locations (list[str])")
    npcs: list[dict] = dspy.OutputField(desc="5-8 NPCs; each a dict with keys: name, role, motivation")
    factions: list[dict] = dspy.OutputField(desc="2-3 factions; each a dict with keys: name, goal, alignment")
    hook: str = dspy.OutputField(desc="An immediate adventure hook that pulls the player in")


class DMNarration(dspy.Signature):
    """You are an expert Dungeon Master for a single-player Dungeons &
    Dragons 5th Edition game. You create immersive, exciting, and
    balanced adventures.

    Your responsibilities:
    - Narrate scenes vividly but concisely (2-4 paragraphs max unless
      asked for detail)
    - Present clear, meaningful choices to the player
    - Adjudicate rules fairly using DnD 5e mechanics
    - Track HP, conditions, inventory, and quest state
    - Scale encounters to match the character's level and abilities
    - React creatively to unexpected player actions
    - Never kill the character unfairly — always offer a path forward
    - Maintain consistent NPCs, locations, and lore

    Tone: Heroic fantasy. Epic moments, real danger, but the player is
    the hero. When the player attempts something, ask for a roll only
    when the outcome is uncertain."""

    situation: str = dspy.InputField(desc="Full scene context: world setting, character state (HP, conditions, location), recent story events, and the action or scene to narrate")
    narration: str = dspy.OutputField(desc="The DM's vivid narration of the scene outcome (2-4 paragraphs), ending with clear choices when appropriate")


class SummarizeStory(dspy.Signature):
    """You are a Dungeon Master creating a concise summary of past game
    events. Given the story log entries to summarize — and, when merging
    with earlier work, a 'PREVIOUS SUMMARY:' block followed by 'NEW
    EVENTS:' — produce a structured summary that captures what actually
    happened.

    Focus on:
    - What actually happened (not what almost happened)
    - Important NPCs and their roles
    - Current location and where the player is headed
    - Active objectives
    - Story progress (which act, approximate percentage)"""

    story_entries: str = dspy.InputField(desc="Formatted story log entries to summarize; may begin with 'PREVIOUS SUMMARY:' followed by 'NEW EVENTS:' when merging with an earlier summary")
    summary: str = dspy.OutputField(desc="1-2 paragraph prose summary of key events")
    npcs_met: list[str] = dspy.OutputField(desc="Names and brief descriptions of NPCs encountered, e.g. ['Aldric - wise old wizard']")
    key_locations: list[str] = dspy.OutputField(desc="Important places visited")
    active_quests: list[str] = dspy.OutputField(desc="Current quest objectives")
    completed_quests: list[str] = dspy.OutputField(desc="Finished quests")
    current_act: int = dspy.OutputField(desc="Story act number (1, 2, or 3)")
