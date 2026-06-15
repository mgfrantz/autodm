"""
LLM Orchestrator — manages DM responses, world generation, and prompt construction.

This is the brain of the game. It:
1. Builds prompts with game state context
2. Calls the LLM
3. Parses structured (JSON) or free-text (narration) responses
4. Manages context window efficiency
"""
import json
from typing import Any, Optional

from openai import AsyncOpenAI

from app.llm.config import config


class LLMOrchestrator:
    """Manages all LLM interactions for the game."""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url if config.base_url else None,
        )
        self.model = config.model

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Generate a structured JSON response from the LLM."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Append schema instruction if provided
        if response_schema:
            schema_text = json.dumps(response_schema, indent=2)
            messages.append({
                "role": "system",
                "content": f"Respond ONLY with valid JSON matching this schema:\n{schema_text}"
            })

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        return json.loads(content)

    async def generate_narration(
        self,
        system_prompt: str,
        user_prompt: str,
        context: Optional[str] = None,
    ) -> str:
        """Generate free-text narration from the LLM (DM voice)."""
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        if context:
            messages.append({"role": "system", "content": f"Game Context:\n{context}"})
        messages.append({"role": "user", "content": user_prompt})

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )

        return response.choices[0].message.content


# Singleton
orchestrator = LLMOrchestrator()
