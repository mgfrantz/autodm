"""
DM Prompt Templates — encounter templates for the LLM Dungeon Master.

The DM persona itself lives in the ``DMNarration`` DSPy signature
(``app.llm.dspy_signatures.DMNarration``), which is the single source of
truth shared by both the non-streaming ``DMNarrationModule`` and the
streaming ``stream_narration_dspy`` helper.
"""

# Encounter template — the per-action framing passed to the DM as the
# situation to narrate (filled with live game state).
#
# NOTE: The DM must NOT fabricate dice results or check outcomes in the
# narration. The backend resolves all checks via game_actions BEFORE the
# narration is generated, and the actual results are appended to the
# situation as "CHECK_RESULTS" — the DM should narrate the outcome
# consistent with those results.
ENCOUNTER_PROMPT = """\
You are narrating the next beat of the adventure.

Current location: {location}
Player status: HP {hp}/{max_hp}, Conditions: {conditions}
Recent events: {recent_events}

The player's action: {player_action}

Narrate the outcome. If CHECK_RESULTS appear below, they have ALREADY been
rolled by the backend — narrate the scene consistent with those results.
If no CHECK_RESULTS appear, the action does not require a mechanical check;
narrate the outcome directly.
"""
