"""
LLM Configuration — provider-agnostic setup.

Configure via environment variables or edit defaults here.
Supports OpenAI, Anthropic, or any OpenAI-compatible endpoint (e.g. local models).
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMConfig:
    provider: str  # "openai", "anthropic", "openai-compatible"
    model: str
    api_key: str
    base_url: Optional[str] = None  # For OpenAI-compatible local models
    max_tokens: int = 4096
    temperature: float = 0.8  # Slightly creative for DM narration


def load_config() -> LLMConfig:
    """Load LLM config from environment variables."""
    provider = os.getenv("LLM_PROVIDER", "openai")
    model = os.getenv("LLM_MODEL", "gpt-4o")
    api_key = os.getenv("LLM_API_KEY", os.getenv("OPENROUTER_API_KEY", os.getenv("OPENAI_API_KEY", "")))
    base_url = os.getenv("LLM_BASE_URL", None)  # e.g. http://localhost:11434/v1 for Ollama

    return LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )


# Default config
config = load_config()
