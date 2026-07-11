"""
Image Generation Client — provider-agnostic image generation.

Uses a lazy-initialised singleton that talks to an OpenAI-compatible
image-generation API (DALL-E 3 by default). When no API key is configured,
``is_configured`` returns ``False`` and ``generate_image`` raises
``ImageNotConfiguredError`` so the API layer can surface a clean 503 to the
frontend instead of crashing.

Usage::

    from app.llm.image_client import get_image_client

    client = get_image_client()
    if client.is_configured:
        result = await client.generate_image("a dragon perched on a gold hoard")
        print(result.url)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.llm.image_config import ImageConfig, config as _default_config


class ImageNotConfiguredError(RuntimeError):
    """Raised when image generation is attempted without an API key."""


@dataclass
class ImageResult:
    """The result of a single image-generation call."""
    url: str
    revised_prompt: Optional[str] = None
    model: str = ""
    size: str = ""
    quality: str = ""
    prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "revised_prompt": self.revised_prompt,
            "model": self.model,
            "size": self.size,
            "quality": self.quality,
            "prompt": self.prompt,
        }


# --------------------------------------------------------------------------- #
# Prompt helpers
# --------------------------------------------------------------------------- #

# Truncate very long prompts — DALL-E 3 has a ~4000 char limit.
_MAX_PROMPT_LEN = 1000

_VISUAL_SUFFIX = (
    " Fantasy tabletop RPG illustration, dramatic lighting, highly detailed "
    "digital painting, rich colours, cinematic composition."
)


def build_scene_prompt(
    narration: str,
    *,
    location: str = "",
    character_name: str = "",
    character_race: str = "",
    character_class: str = "",
) -> str:
    """Build a visual image-generation prompt from DM narration + context.

    Strips non-visual prose, focuses on the most recent descriptive paragraph,
    and appends a consistent art-style suffix so every scene image looks like it
    belongs to the same campaign.
    """
    # Take the last meaningful chunk of narration (the freshest scene).
    text = narration.strip()
    if not text:
        text = location or "a mysterious fantasy location"

    # Prefer the final paragraph — usually the most evocative setting description.
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if paragraphs:
        text = paragraphs[-1]

    # Collapse whitespace and strip markdown-ish artefacts.
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[*_#>`]", "", text)

    # Trim to a reasonable length.
    if len(text) > _MAX_PROMPT_LEN:
        text = text[:_MAX_PROMPT_LEN].rsplit(" ", 1)[0] + "…"

    # Prepend character context for consistency.
    parts: list[str] = []
    if character_name or character_race or character_class:
        who = " ".join(
            p for p in [character_race, character_class] if p
        ).strip().capitalize()
        if character_name:
            who = f"{character_name}" + (f", {who}" if who else "")
        parts.append(f"{who} in")
    if location:
        parts.append(f"{location}:")
    parts.append(text)

    return " ".join(parts) + _VISUAL_SUFFIX


def build_portrait_prompt(
    name: str,
    description: str = "",
    *,
    race: str = "",
    char_class: str = "",
) -> str:
    """Build a portrait image-generation prompt for an NPC or character."""
    parts: list[str] = ["Portrait of"]
    if name:
        parts.append(name + ",")
    descriptors = " ".join(p for p in [race, char_class] if p).strip()
    if descriptors:
        parts.append(descriptors)
    if description:
        parts.append("—" + description)
    return " ".join(parts) + (
        " Fantasy character portrait, head and shoulders, detailed face, "
        "dramatic lighting, digital painting, rich colours."
    )


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #

class ImageClient:
    """Provider-agnostic image-generation client (lazy-initialised)."""

    def __init__(self, cfg: Optional[ImageConfig] = None):
        self._config = cfg or _default_config
        self._client = None  # lazy AsyncOpenAI

    @property
    def config(self) -> ImageConfig:
        return self._config

    @property
    def is_configured(self) -> bool:
        return self._config.is_configured

    def _get_client(self):
        """Lazy-initialise the OpenAI async client on first use."""
        if self._client is None:
            if not self.is_configured:
                raise ImageNotConfiguredError(
                    "Image generation is not configured. Set IMAGE_API_KEY "
                    "(or IMAGE_PROVIDER=none to disable)."
                )
            # Imported here so the module loads even without openai installed
            # during partial environments.
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=self._config.api_key,
                base_url=self._config.base_url if self._config.base_url else None,
            )
        return self._client

    async def generate_image(
        self,
        prompt: str,
        *,
        size: Optional[str] = None,
        quality: Optional[str] = None,
    ) -> ImageResult:
        """Generate a single image and return its URL + metadata.

        Raises ``ImageNotConfiguredError`` when no API key is set.
        """
        client = self._get_client()
        sz = size or self._config.size
        ql = quality or self._config.quality

        response = await client.images.generate(
            model=self._config.model,
            prompt=prompt,
            size=sz,  # type: ignore[arg-type]
            quality=ql,  # type: ignore[arg-type]
            n=1,
        )
        data = response.data[0] if response.data else None
        if data is None:
            raise RuntimeError("Image generation returned no data.")
        return ImageResult(
            url=data.url or "",
            revised_prompt=getattr(data, "revised_prompt", None),
            model=self._config.model,
            size=sz,
            quality=ql,
            prompt=prompt,
        )


# --------------------------------------------------------------------------- #
# Lazy singleton
# --------------------------------------------------------------------------- #

_image_client_instance: Optional[ImageClient] = None


def get_image_client() -> ImageClient:
    """Get the singleton image client (lazy-initialised)."""
    global _image_client_instance
    if _image_client_instance is None:
        _image_client_instance = ImageClient()
    return _image_client_instance


def reset_image_client() -> None:
    """Reset the singleton (used by tests to inject a mock config)."""
    global _image_client_instance
    _image_client_instance = None
