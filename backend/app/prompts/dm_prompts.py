"""
DM Prompt Templates — encounter templates for the LLM Dungeon Master.

The DM persona itself lives in the ``DMNarration`` DSPy signature
(``app.llm.dspy_signatures.DMNarration``), which is the single source of
truth shared by both the non-streaming ``DMNarrationModule`` and the
streaming ``stream_narration_dspy`` helper.
"""

# Encounter template — the per-action framing passed to the DM as the
# situation to narrate (filled with live game state).
ENCOUNTER_PROMPT = """\
You are narrating the next beat of the adventure.

Current location: {location}
Player status: HP {hp}/{max_hp}, Conditions: {conditions}
Recent events: {recent_events}

The player's action: {player_action}

Narrate the outcome. If the action requires a check, describe what happens and
whether it succeeds or fails based on a d20 roll. If combat begins, set the scene.
"""
