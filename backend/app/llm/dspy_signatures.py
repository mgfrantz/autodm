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


class DetectQuests(dspy.Signature):
    """You are analyzing a Dungeon Master's narration to detect quest-related
    events. Given the DM's narration text and a list of currently active quest
    titles, identify any new quests being offered, quests being completed,
    quests being failed, and any important information revealed about the world
    or characters.

    Quest detection:
    - A quest is OFFERED when the DM presents a task or objective to the player
      (e.g., "I need you to retrieve the stolen amulet").
    - A quest is COMPLETED when the DM confirms the player has fulfilled a
      quest's objectives (e.g., "You have successfully rescued the villagers").
    - A quest is FAILED when the DM confirms the player has failed to complete
      a quest (e.g., "The portal closes, and the artifact is lost forever").

    For quests offered, include:
    - title: A concise, memorable quest title
    - description: A brief description of the quest
    - giver: The NPC name offering the quest (if any)
    - objective: The primary objective

    For quests completed/failed, match to the closest active quest title
    (case-insensitive partial match)."""

    narration: str = dspy.InputField(desc="The DM's narration text to analyze")
    existing_quests: list[str] = dspy.InputField(desc="List of currently active quest titles for matching completion/failure", default=[])
    quests_offered: list[dict] = dspy.OutputField(desc="Quests offered in this narration; each a dict with keys: title, description, giver (optional), objective (optional)")
    quests_completed: list[str] = dspy.OutputField(desc="Titles of quests completed in this narration (partial matches allowed)")
    quests_failed: list[str] = dspy.OutputField(desc="Titles of quests failed in this narration (partial matches allowed)")
    information_revealed: list[str] = dspy.OutputField(desc="Important information revealed about the world, NPCs, or lore")


class DetectNPCMoodChanges(dspy.Signature):
    """You are analyzing a Dungeon Master's narration to detect NPC mood or
    relationship changes. Given the DM's narration text, identify any NPCs whose
    disposition toward the player has shifted and the nature of that change.

    Mood detection:
    - A POSITIVE mood change occurs when an NPC shows approval, gratitude,
      respect, trust, or warmth toward the player (e.g., "Eldrin smiles warmly",
      "The captain thanks you for your help", "The shopkeeper gives you a
      discount because she trusts you").
    - A NEGATIVE mood change occurs when an NPC shows disapproval, anger,
      suspicion, distrust, or hostility toward the player (e.g., "The guard
      glares at you", "The merchant accuses you of theft", "The king furrows his
      brow in disappointment").
    - NEUTRAL changes are minor interactions that don't significantly shift the
      relationship (e.g., simple greetings, factual exchanges).

    For each NPC with a mood change, include:
    - npc_name: The NPC's name (exactly as mentioned in narration)
    - mood_change: 'positive', 'negative', or 'neutral'
    - trust_change: Estimated trust change on a scale of -20 to +20
      (negative for mood_change=negative, positive for mood_change=positive,
      near-zero for neutral)
    - reason: Brief explanation of what caused the change

    Only include NPCs whose mood meaningfully shifts. Don't include NPCs who are
    merely present without interaction or whose disposition remains the same."""

    narration: str = dspy.InputField(desc="The DM's narration text to analyze")
    npc_mood_changes: list[dict] = dspy.OutputField(desc="NPC mood changes; each a dict with keys: npc_name, mood_change (positive/negative/neutral), trust_change (-20 to +20), reason (brief explanation)")


class DetectGameFlags(dspy.Signature):
    """You are analyzing a Dungeon Master's narration to detect game flags that
    should be set or cleared. Game flags are simple boolean markers that track
    branching narrative state (e.g., "met_king", "saved_village", "found_secret_passage").

    Flag detection:
    - SET a flag when the DM confirms the player has accomplished something
      (e.g., "You have finally met King Aldric" → set "met_king").
    - CLEAR a flag when the DM confirms the player has undone something or
      circumstances have changed (e.g., "The village has been destroyed" → clear "saved_village").
    - Use descriptive flag names that are clear and specific (snake_case, lowercase).

    Only detect flags that are meaningful for branching narrative state. Don't
    include trivial details (e.g., "looked_at_wall" or "walked_north"). Focus on
    events that could affect future story branches, NPC reactions, or quest outcomes."""

    narration: str = dspy.InputField(desc="The DM's narration text to analyze")
    flags_to_set: list[str] = dspy.OutputField(desc="Flag names to set to True (e.g., ['met_king', 'found_secret_passage'])")
    flags_to_clear: list[str] = dspy.OutputField(desc="Flag names to clear/set to False (e.g., ['village_safe', 'prisoner_alive'])")


class GenerateActionSuggestions(dspy.Signature):
    """You are a Dungeon Master generating contextually appropriate action
    suggestions for a player. Given the DM's narration of a scene, produce 4-6
    brief, specific action suggestions that the player could take next.

    Action suggestions should:
    - Be specific to the current scene (location, NPCs present, situation)
    - Cover different approaches (social, combat, exploration, investigation)
    - Be concise (3-8 words each, verb-first)
    - Avoid repeating the DM's explicit choices if they're already clear
    - Reflect the character's likely capabilities (don't suggest spells for a fighter)

    Examples of good suggestions:
    - "Ask the innkeeper about rumors"
    - "Search the chest for traps"
    - "Attack the goblin archer"
    - "Sneak past the sleeping guards"
    - "Inspect the ancient mural"

    Avoid trivial actions like "wait" or "do nothing." Focus on actions that
    advance the story or reveal something interesting."""

    narration: str = dspy.InputField(desc="The DM's narration text to analyze")
    action_suggestions: list[str] = dspy.OutputField(desc="4-6 brief, scene-specific action suggestions (verb-first, 3-8 words each)")


class DMActionableNarration(dspy.Signature):
    """You are an expert Dungeon Master for a single-player DnD 5e game.

    In addition to narrating the scene, you output structured game_actions
    that the backend will resolve mechanically. This ensures dice rolls,
    checks, and other mechanical outcomes are REAL — not fabricated text.

    Rules for game_actions:
    - Include a roll_dice action whenever the outcome of an action is
      uncertain and warrants a check (attack, save, skill check, damage)
    - Use request_check when YOU (the DM) want the PLAYER to roll
      (e.g., "Roll a Perception check")
    - For COMBAT actions in an active encounter:
      - Use attack when a combatant makes a weapon/spell attack. You must
        reference the combatant by ID (see COMBATANT_IDS in the situation).
        Args: {"attacker_id": "...", "target_id": "...", "attack_index": 0}
      - Use damage for direct damage without an attack roll (spell AoE,
        trap damage, falling damage). Args: {"target_id": "...", "amount": 10,
        "damage_type": "fire"}
      - Use roll_initiative at the start of combat to establish turn order.
        No args needed.
      - Combatant IDs are provided in the situation prompt under
        COMBATANT_ROSTER (id, name, side, HP, AC). Always use the exact id.
    - For SPELL CASTING (any time a character or NPC casts a spell):
      - Use cast_spell for ANY spell cast — cantrip or leveled. Reference a
        REAL spell_id from the AVAILABLE_SPELLS roster in the situation prompt.
        Args: {"spell_id": "fire_bolt", "target_id": "goblin_1",
               "slot_level": null}
      - The backend consumes the real spell slot and rolls the real
        attack/damage/save. NEVER fabricate spell outcomes, damage, or saves
        in the narration — describe the INTENT (e.g., "the wizard hurls a
        Fire Bolt at the goblin") and let the backend resolve the result.
      - slot_level: null (auto/lowest) or an int for upcasting.
      - target_id: a combatant id from the COMBATANT_ROSTER (for attack/save/
        damage spells), or omit for self/utility spells (Cure Wounds on self,
        Mage Armor, etc.).
      - Available spell ids are provided under AVAILABLE_SPELLS (id, name,
        school, level) with REMAINING_SLOTS. Only emit cast_spell for spells
        in that roster.
      - For AoE SPELLS (Fireball, Lightning Bolt, Shatter, Burning Hands, Ice
        Storm, etc. — any spell that affects multiple creatures in an area):
        use cast_spell_aoe to hit MULTIPLE combatants with ONE cast. This
        consumes ONE spell slot and rolls damage ONCE; each target rolls its
        own save against that shared damage. NEVER emit multiple cast_spell
        actions for one AoE spell (that would burn multiple slots).
        Args: {"spell_id": "fireball",
               "target_ids": ["goblin_1", "goblin_2", "goblin_3"],
               "slot_level": null}
        target_ids is a LIST of combatant IDs from COMBATANT_ROSTER. Use
        cast_spell_aoe for any spell whose description mentions an area
        (sphere, cone, line, radius, cylinder) or "each creature in". Use
        single-target cast_spell when only ONE creature is affected.
    - For INVENTORY operations:
      - Use give_item when the player ACQUIRES an item (loot, reward,
        purchase, gift, found treasure). Provide construction details:
        Args: {"item_name": "Health Potion", "item_type": "potion",
               "quantity": 2, "rarity": "common", "value": 50,
               "description": "Restores 2d4+2 HP"}
        Optional details: rarity, value, damage_dice + damage_type (weapons),
        armor_type (light/medium/heavy/shield) + armor_bonus (armor),
        description (potions = effect text), uses (consumable charges).
        item_type is one of: weapon, armor, potion, scroll, misc, quest.
      - Use remove_item when the player LOSES an item (consumed, stolen,
        given away, sacrificed, dropped). Reference the item_id from
        INVENTORY_ROSTER. Args: {"item_id": "...", "quantity": 1}
      - Use equip_item when the player dons gear (equip found armor, wield a
        found weapon). Reference item_id from INVENTORY_ROSTER.
        Args: {"item_id": "..."}
      - Use use_item when a consumable is used (drink a potion, read a
        scroll). Reference item_id from INVENTORY_ROSTER.
        Args: {"item_id": "..."}
      - The DM should ONLY give items that make narrative sense. Don't spawn
        legendary items from thin air. Follow the scene's logic.
      - Current inventory items are listed under INVENTORY_ROSTER (id, name,
        type, qty, equipped, rarity). Use those exact ids for remove_item,
        equip_item, and use_item.
    - For CONDITION operations:
      - Use apply_condition when a creature gains a status condition (poisoned
        by a bite, frightened by a dragon's presence, blinded by a flash,
        grappled by a tentacle, restrained by a net, knocked prone, etc.).
        Args: {"condition": "poisoned", "target": "player",
               "duration": 3}
        "condition" is one of the 14 core DnD 5e conditions: blinded, charmed,
        deafened, frightened, grappled, incapacitated, invisible, paralyzed,
        petrified, poisoned, prone, restrained, stunned, unconscious.
        "target" is "player" (or omitted for the player) or a combatant ID from
        COMBATANT_ROSTER (e.g. "goblin_1").
        "duration" is optional rounds (e.g. 3 = "for 3 rounds"). Omit for a
        permanent condition (until removed).
      - Use remove_condition when a condition ends (player shakes off fear,
        ally dispels paralysis, condition expires). Use the same target.
        Args: {"condition": "frightened", "target": "player"}
      - The player's current conditions are listed in the Conditions line of
        the character context. Use those exact names for remove_condition.
    - For CONCENTRATION (player caster only):
      - Concentration STARTS automatically when the player casts a concentration
        spell (Shield, Hold Person, Bless, Hunter's Mark, Faerie Fire, etc.) —
        you do NOT need an action for this; the backend handles it.
      - Concentration BREAKS automatically when the player takes damage (a Con
        save is rolled) or gains an incapacitating condition (stunned,
        paralyzed, petrified, unconscious) — again, no action needed.
      - Use end_concentration ONLY when the player VOLUNTARILY drops
        concentration (chooses to stop the spell) or a concentration spell ends
        naturally (duration expires, target dies, etc.).
        Args: {"reason": "Player drops Hold Person"}
      - The player's active concentration is shown under PLAYER_CONCENTRATION
        in the situation prompt. If a concentration spell should end for a
        reason not covered by damage/conditions, emit end_concentration.
    - Do NOT fabricate dice results in the narration text — describe
      the ATTEMPT and let the backend resolve the outcome
    - Do NOT state HP numbers, damage amounts, or initiative order in narration;
      the backend will provide these via game_actions
    - If an action has a certain outcome, no game_action is needed
    - Reference the action's label in narration (e.g., "You attempt to
      pick the lock...") so the player knows what's being resolved

    Each game_action is a dict with:
    - "function": "roll_dice" | "request_check" | "attack" | "damage" |
                  "roll_initiative" | "cast_spell" | "cast_spell_aoe" |
                  "give_item" | "remove_item" | "equip_item" | "use_item" |
                  "apply_condition" | "remove_condition" | "end_concentration"
    - "label": short description (e.g., "Perception Check", "Goblin strikes",
                  "Fireball engulfs enemies", "Wizard casts Fire Bolt",
                  "Found a Health Potion")
    - "args": function-specific arguments
      - roll_dice: {"sides": 20, "modifier": 3, "advantage": false,
                     "dc": 15, "disadvantage": false}
      - request_check: {"skill": "Perception", "dc": 15, "reason": "..."}
      - attack: {"attacker_id": "...", "target_id": "...", "attack_index": 0}
      - damage: {"target_id": "...", "amount": 10, "damage_type": "fire"}
      - roll_initiative: {} (no args)
      - cast_spell: {"spell_id": "fire_bolt", "target_id": "goblin_1",
                     "slot_level": null}
      - cast_spell_aoe: {"spell_id": "fireball",
                         "target_ids": ["goblin_1", "goblin_2"],
                         "slot_level": null}
      - give_item: {"item_name": "Health Potion", "item_type": "potion",
                    "quantity": 2, "rarity": "common", "value": 50}
      - remove_item: {"item_id": "...", "quantity": 1}
      - equip_item: {"item_id": "..."}
      - use_item: {"item_id": "..."}
      - apply_condition: {"condition": "poisoned", "target": "player",
                          "duration": 3}
      - remove_condition: {"condition": "frightened", "target": "player"}
      - end_concentration: {"reason": "Player drops the spell"}
    """

    situation: str = dspy.InputField(desc="Full scene context: world, character state, recent events, player action. Includes COMBATANT_ROSTER with id/name/side/HP/AC for active encounters.")
    narration: str = dspy.OutputField(desc="Vivid narration of the scene. Describe attempts and outcomes — but for uncertain actions, describe the ATTEMPT and let game_actions resolve the result. For combat, describe the narrative action (e.g., 'The goblin lunges at you') but do NOT fabricate hit/miss/crit/damage numbers or HP totals.")
    game_actions: list[dict] = dspy.OutputField(desc="Structured actions to resolve mechanically. Empty list if no mechanical resolution needed.")


class ResolveSkillCheck(dspy.Signature):
    """You are a Dungeon Master resolving a freeform player action that doesn't
    map to a standard DnD 5e mechanic (e.g., persuasion attempts, investigation
    checks, creative problem-solving, unconventional tactics). Given the player's
    action description, the character's capabilities, and the current scene
    context, determine the outcome and any mechanical consequences.

    Resolution guidelines:
    - Consider the character's relevant ability scores, skills, and class features
    - Factor in the difficulty and circumstances of the action
    - Be fair but generous — this is a heroic fantasy game
    - Success should feel earned but failure should have clear consequences
    - Reward creativity and clever approaches
    - Keep stat changes moderate (usually -5 to +5, rarely more extreme)
    - XP rewards should scale with difficulty (10-50 for minor successes, 50-200 for major achievements)

    Outputs:
    - success: Whether the action succeeds overall
    - degree: How well/poorly the action went ('great_success', 'success', 'partial_success', 'failure', 'critical_failure')
    - stat_changes: Dictionary of character stat changes (e.g., {"gold": 10, "hp": -5})
    - items_gained: List of items obtained (if any)
    - experience_gained: XP awarded for the action
    - narrative_notes: Brief explanation of why the resolution went this way

    Only include items gained if they're clearly obtained in the action (found,
    looted, gifted, etc.). Don't invent items unless the context makes it obvious.
    Stat changes should be direct consequences (HP loss from a fall, gold from a
    reward, etc.), not speculative or long-term effects."""

    action: str = dspy.InputField(desc="The player's freeform action description")
    character_context: str = dspy.InputField(desc="Character info: level, class, relevant ability scores, skills, and any relevant features")
    scene_context: str = dspy.InputField(desc="Current scene: location, NPCs present, situation, any relevant conditions or obstacles")
    success: bool = dspy.OutputField(desc="Whether the action succeeds overall")
    degree: str = dspy.OutputField(desc="Degree of success/failure: 'great_success', 'success', 'partial_success', 'failure', or 'critical_failure'")
    stat_changes: dict = dspy.OutputField(desc="Dictionary of stat changes (e.g., {\"gold\": 10, \"hp\": -5})")
    items_gained: list[str] = dspy.OutputField(desc="List of items obtained (if any)")
    experience_gained: int = dspy.OutputField(desc="XP awarded for the action")
    narrative_notes: str = dspy.OutputField(desc="Brief explanation of why the resolution went this way")
