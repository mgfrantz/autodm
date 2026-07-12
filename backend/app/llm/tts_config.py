"""
Text-to-Speech Configuration — provider-agnostic setup.

Mirrors the image-config pattern (``app.llm.image_config``). Configure via
environment variables or edit defaults here. Uses the OpenAI TTS API
(``tts-1``) or any OpenAI-compatible speech endpoint.

Environment variables:
    TTS_PROVIDER   – "openai" (default) or "none" to disable
    TTS_API_KEY    – API key (falls back to LLM_API_KEY / OPENAI_API_KEY)
    TTS_MODEL      – model id (default "tts-1"; "tts-1-hd" for higher quality)
    TTS_BASE_URL   – override endpoint for compatible providers
    TTS_VOICE      – "alloy" (default), "echo", "fable", "onyx", "nova", "shimmer"
    TTS_FORMAT     – response format (default "mp3")
    TTS_SPEED      – playback speed 0.25–4.0 (default 1.0)
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class TTSConfig:
    """Provider-agnostic text-to-speech configuration."""
    provider: str            # "openai" or "none"
    model: str               # e.g. "tts-1"
    api_key: str
    base_url: Optional[str] = None
    voice: str = "alloy"
    response_format: str = "mp3"
    speed: float = 1.0

    @property
    def is_configured(self) -> bool:
        """True when a provider is enabled and an API key is present."""
        return self.provider != "none" and bool(self.api_key)


def _parse_speed(raw: Optional[str], default: float = 1.0) -> float:
    """Parse TTS_SPEED into a float clamped to the OpenAI-supported 0.25–4.0."""
    try:
        val = float(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default
    return max(0.25, min(4.0, val))


def load_config() -> TTSConfig:
    """Load text-to-speech config from environment variables."""
    provider = os.getenv("TTS_PROVIDER", "openai")
    api_key = os.getenv(
        "TTS_API_KEY",
        os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")),
    )
    model = os.getenv("TTS_MODEL", "tts-1")
    base_url = os.getenv("TTS_BASE_URL", None)
    voice = os.getenv("TTS_VOICE", "alloy")
    response_format = os.getenv("TTS_FORMAT", "mp3")
    speed = _parse_speed(os.getenv("TTS_SPEED"))
    return TTSConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        voice=voice,
        response_format=response_format,
        speed=speed,
    )


# --------------------------------------------------------------------------- #
# Available voices
# --------------------------------------------------------------------------- #

#: The six standard OpenAI ``tts-1`` voices. These are also accepted by every
#: OpenAI-compatible TTS endpoint we've tested. Each entry is
#: ``(voice_id, human description, suggested use)`` — the description helps
#: the player pick a fitting voice for a character in the UI.
AVAILABLE_VOICES: list[tuple[str, str, str]] = [
    ("alloy",   "Neutral, balanced, and clear",  "Default narrator / general purpose"),
    ("echo",    "Warm, steady, male-presenting", "Male warriors, dwarves, guards"),
    ("fable",   "Expressive, slightly eccentric","Wizards, sages, fey creatures"),
    ("onyx",    "Deep, resonant, male-presenting","Villains, dragons, baritones"),
    ("nova",    "Bright, female-presenting",     "Female heroes, elves, nobles"),
    ("shimmer", "Soft, ethereal, female-presenting","Clerics, spirits, mystical beings"),
]

#: Quick lookup set of valid voice ids.
_VALID_VOICES: set[str] = {v[0] for v in AVAILABLE_VOICES}

#: The default voice — first in the registry.
DEFAULT_VOICE: str = AVAILABLE_VOICES[0][0]


def voices_as_dicts() -> list[dict[str, str]]:
    """Return the available voices as a list of JSON-serialisable dicts."""
    return [
        {"id": vid, "description": desc, "suggested_use": use}
        for vid, desc, use in AVAILABLE_VOICES
    ]


def is_valid_voice(voice: Optional[str]) -> bool:
    """True when ``voice`` is a recognised voice id (or empty/None)."""
    if not voice:
        return True
    return voice in _VALID_VOICES


# Default config (loaded once at import time, like app.llm.config / image_config)
config = load_config()
