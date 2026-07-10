"""
Image Generation Configuration — provider-agnostic setup.

Mirrors the LLM config pattern (``app.llm.config``). Configure via environment
variables or edit defaults here. Uses the OpenAI image-generation API (DALL-E 3)
or any OpenAI-compatible image endpoint.

Environment variables:
    IMAGE_PROVIDER   – "openai" (default) or "none" to disable
    IMAGE_API_KEY    – API key (falls back to LLM_API_KEY / OPENAI_API_KEY)
    IMAGE_MODEL      – model id (default "dall-e-3")
    IMAGE_BASE_URL   – override endpoint for compatible providers
    IMAGE_SIZE       – "1024x1024" (default), "1792x1024", or "1024x1792"
    IMAGE_QUALITY    – "standard" (default) or "hd"
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class ImageConfig:
    """Provider-agnostic image-generation configuration."""
    provider: str            # "openai" or "none"
    model: str               # e.g. "dall-e-3"
    api_key: str
    base_url: Optional[str] = None
    size: str = "1024x1024"
    quality: str = "standard"

    @property
    def is_configured(self) -> bool:
        """True when a provider is enabled and an API key is present."""
        return self.provider != "none" and bool(self.api_key)


def load_config() -> ImageConfig:
    """Load image-generation config from environment variables."""
    provider = os.getenv("IMAGE_PROVIDER", "openai")
    api_key = os.getenv(
        "IMAGE_API_KEY",
        os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")),
    )
    model = os.getenv("IMAGE_MODEL", "dall-e-3")
    base_url = os.getenv("IMAGE_BASE_URL", None)
    size = os.getenv("IMAGE_SIZE", "1024x1024")
    quality = os.getenv("IMAGE_QUALITY", "standard")
    return ImageConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        size=size,
        quality=quality,
    )


# Default config (loaded once at import time, like app.llm.config)
config = load_config()
