"""
Text-to-Speech Configuration — provider-agnostic setup.

Mirrors the image-config pattern (``app.llm.image_config``). Configure via
environment variables or edit defaults here. Uses the OpenAI TTS API
(``tts-1``) or any OpenAI-compatible speech endpoint. Also supports local
on-device TTS via mlx-audio (Kokoro) on Apple Silicon.

Environment variables:
    TTS_PROVIDER   – "mlx" (local, default on Apple Silicon), "openai", or "none"
    TTS_API_KEY    – API key (falls back to LLM_API_KEY / OPENAI_API_KEY)
    TTS_MODEL      – model id (default "kokoro-82m" for mlx, "tts-1" for openai)
    TTS_BASE_URL   – override endpoint for compatible providers (openai only)
    TTS_VOICE      – voice id (default "af_heart" for mlx, "alloy" for openai)
    TTS_FORMAT     – response format (default "wav" for mlx, "mp3" for openai)
    TTS_SPEED      – playback speed 0.25–4.0 (default 1.0)
    TTS_CACHE      – whether to cache audio in game_state (default false for mlx)
"""
import os
import platform
from dataclasses import dataclass
from typing import Optional


@dataclass
class TTSConfig:
    """Provider-agnostic text-to-speech configuration."""
    provider: str            # "mlx", "openai", or "none"
    model: str               # e.g. "kokoro-82m" or "tts-1"
    api_key: str
    base_url: Optional[str] = None
    voice: str = "alloy"
    response_format: str = "mp3"
    speed: float = 1.0
    cache_audio: bool = False  # Whether to cache audio in game_state

    @property
    def is_configured(self) -> bool:
        """True when a provider is enabled and (if openai) an API key is present."""
        if self.provider == "mlx":
            # MLX provider is always available on Apple Silicon
            return True
        return self.provider != "none" and bool(self.api_key)


def _parse_speed(raw: Optional[str], default: float = 1.0) -> float:
    """Parse TTS_SPEED into a float clamped to the OpenAI-supported 0.25–4.0."""
    try:
        val = float(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default
    return max(0.25, min(4.0, val))


def _default_provider() -> str:
    """Return the default TTS provider based on platform."""
    # Default to mlx on Apple Silicon, otherwise openai
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return "mlx"
    return "openai"


def load_config() -> TTSConfig:
    """Load text-to-speech config from environment variables."""
    provider = os.getenv("TTS_PROVIDER", _default_provider())
    api_key = os.getenv(
        "TTS_API_KEY",
        os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")),
    )

    # Provider-specific defaults
    if provider == "mlx":
        model = os.getenv("TTS_MODEL", "kokoro-82m")
        voice = os.getenv("TTS_VOICE", "af_heart")
        response_format = os.getenv("TTS_FORMAT", "wav")
        cache_audio = os.getenv("TTS_CACHE", "false").lower() in ("true", "1", "yes")
    else:
        model = os.getenv("TTS_MODEL", "tts-1")
        voice = os.getenv("TTS_VOICE", "alloy")
        response_format = os.getenv("TTS_FORMAT", "mp3")
        cache_audio = os.getenv("TTS_CACHE", "true").lower() in ("true", "1", "yes")

    base_url = os.getenv("TTS_BASE_URL", None)
    speed = _parse_speed(os.getenv("TTS_SPEED"))
    return TTSConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        voice=voice,
        response_format=response_format,
        speed=speed,
        cache_audio=cache_audio,
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

#: Kokoro TTS voices for local MLX provider. Key voices for DnD narration.
KOKORO_VOICES: list[tuple[str, str, str]] = [
    ("af_heart", "Warm, neutral, American female", "Default narrator"),
    ("af_bella", "Bright, expressive, American female", "Female heroes, elves"),
    ("af_nova",  "Energetic, American female", "Young characters"),
    ("af_sky",   "Soft, ethereal, American female", "Clerics, spirits"),
    ("am_adam",  "Deep, steady, American male", "Villains, baritones"),
    ("am_echo",  "Warm, American male", "Warriors, dwarves, guards"),
    ("bm_george", "Deep British male", "Wise NPCs, mentors"),
    ("bf_emma", "Refined British female", "Nobles, royalty"),
    ("af_sarah", "Calm, professional", "Merchant, scholar"),
    ("am_michael", "Authoritative, commanding", "King, general"),
    ("bf_isabella", "Elegant, refined", "Queen, noblewoman"),
    ("am_eric", "Casual, friendly", "Commoner, innkeeper"),
]

#: Map OpenAI voice IDs to Kokoro voice IDs for NPC voice compatibility.
OPENAI_TO_KOKORO: dict[str, str] = {
    "alloy": "af_heart",
    "echo": "am_echo",
    "fable": "af_bella",
    "onyx": "am_adam",
    "nova": "af_nova",
    "shimmer": "af_sky",
}

#: Reverse map Kokoro to OpenAI for when MLX voice is saved but cloud TTS is used.
KOKORO_TO_OPENAI: dict[str, str] = {v: k for k, v in OPENAI_TO_KOKORO.items()}

#: Quick lookup set of valid voice ids.
_VALID_VOICES: set[str] = {v[0] for v in AVAILABLE_VOICES}
_KOKORO_VOICES_SET: set[str] = {v[0] for v in KOKORO_VOICES}

#: The default voice — first in the registry.
DEFAULT_VOICE: str = AVAILABLE_VOICES[0][0]


def get_available_voices(provider: str) -> list[tuple[str, str, str]]:
    """Return the voice registry for the given provider."""
    if provider == "mlx":
        return KOKORO_VOICES
    return AVAILABLE_VOICES


def is_valid_voice(voice: Optional[str], provider: str = "openai") -> bool:
    """True when ``voice`` is a recognised voice id for the provider (or empty/None)."""
    if not voice:
        return True
    if provider == "mlx":
        return voice in _KOKORO_VOICES_SET
    return voice in _VALID_VOICES


def voices_as_dicts(provider: str = "openai") -> list[dict[str, str]]:
    """Return the available voices as a list of JSON-serialisable dicts."""
    voices = get_available_voices(provider)
    return [
        {"id": vid, "description": desc, "suggested_use": use}
        for vid, desc, use in voices
    ]


def is_valid_voice(voice: Optional[str], provider: str = "openai") -> bool:
    """True when ``voice`` is a recognised voice id for the provider (or empty/None)."""
    if not voice:
        return True
    if provider == "mlx":
        return voice in _KOKORO_VOICES_SET
    return voice in _VALID_VOICES


# Default config (loaded once at import time, like app.llm.config / image_config)
config = load_config()
