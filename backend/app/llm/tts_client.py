"""
Text-to-Speech Client — provider-agnostic voice narration.

Uses a lazy-initialised singleton that talks to an OpenAI-compatible speech
API (``tts-1`` by default; works with local / self-hosted endpoints via
``TTS_BASE_URL``). When no API key is configured, ``is_configured`` returns
``False`` and ``synthesize`` raises ``TTSNotConfiguredError`` so the API
layer can surface a clean 503 to the frontend instead of crashing.

Usage::

    from app.llm.tts_client import get_tts_client

    client = get_tts_client()
    if client.is_configured:
        speech = await client.synthesize("The dragon rears back...")
        # speech.audio is raw MP3 bytes
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any, Optional

from app.llm.tts_config import TTSConfig, config as _default_config


class TTSNotConfiguredError(RuntimeError):
    """Raised when text-to-speech is attempted without an API key."""


@dataclass
class SpeechResult:
    """The result of a single text-to-speech call."""
    audio: bytes
    model: str
    voice: str
    text: str
    response_format: str = "mp3"
    speed: float = 1.0

    @property
    def size_bytes(self) -> int:
        return len(self.audio or b"")

    @property
    def audio_b64(self) -> str:
        """Base64-encoded audio for JSON persistence / transport."""
        return base64.b64encode(self.audio or b"").decode("ascii")

    def to_dict(self) -> dict[str, Any]:
        return {
            "audio_b64": self.audio_b64,
            "size_bytes": self.size_bytes,
            "model": self.model,
            "voice": self.voice,
            "format": self.response_format,
            "speed": self.speed,
            "text": self.text,
        }


# --------------------------------------------------------------------------- #
# Text preparation helpers
# --------------------------------------------------------------------------- #

# OpenAI tts-1 input limit is ~4096 characters. Keep a margin.
_MAX_INPUT_LEN = 4000

# Markdown / formatting artefacts that should not be read aloud.
_MARKDOWN_RE = re.compile(r"[*_#>`~]")
# Dice-roll annotations the DM sometimes emits, e.g. "[dex check: 14]".
_DICE_ANNOT_RE = re.compile(r"\[[^\]]*\b(check|roll|save|hit|dmg|damage|dc)\b[^\]]*\]", re.IGNORECASE)
# Trailing choice prompts like "What do you do?" / "1. ..." lists.
_CHOICE_LINE_RE = re.compile(r"^\s*(\d+[.)]|[-*•])\s+", re.MULTILINE)
_WHAT_DO_YOU_DO_RE = re.compile(
    r"\b(what do you do\??|what will you do\??|how do you respond\??|your move\.?)\s*$",
    re.IGNORECASE,
)


def clean_text_for_speech(text: str) -> str:
    """Clean narration text so it reads naturally when spoken aloud.

    Strips markdown emphasis, dice-roll annotations, numbered/bulleted choice
    lists, and trailing "what do you do?" prompts (the DM asks the *player*,
    not the listener). Collapses whitespace and truncates to the TTS limit.
    """
    if not text:
        return ""
    out = _DICE_ANNOT_RE.sub("", text)
    out = _CHOICE_LINE_RE.sub("", out)
    out = _WHAT_DO_YOU_DO_RE.sub("", out)
    out = _MARKDOWN_RE.sub("", out)
    out = re.sub(r"\s+", " ", out).strip()
    if len(out) > _MAX_INPUT_LEN:
        out = out[:_MAX_INPUT_LEN].rsplit(" ", 1)[0] + "…"
    return out


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #

class TTSClient:
    """Provider-agnostic text-to-speech client (lazy-initialised)."""

    def __init__(self, cfg: Optional[TTSConfig] = None):
        self._config = cfg or _default_config
        self._client = None  # lazy AsyncOpenAI

    @property
    def config(self) -> TTSConfig:
        return self._config

    @property
    def is_configured(self) -> bool:
        return self._config.is_configured

    def _get_client(self):
        """Lazy-initialise the OpenAI async client on first use."""
        if self._client is None:
            if not self.is_configured:
                raise TTSNotConfiguredError(
                    "Text-to-speech is not configured. Set TTS_API_KEY "
                    "(or TTS_PROVIDER=none to disable)."
                )
            # Imported here so the module loads even without openai installed
            # during partial environments.
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=self._config.api_key,
                base_url=self._config.base_url if self._config.base_url else None,
            )
        return self._client

    async def synthesize(
        self,
        text: str,
        *,
        voice: Optional[str] = None,
        response_format: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> SpeechResult:
        """Synthesize speech audio for the given text.

        The text is cleaned for speech (markdown/dice/choices stripped) and
        truncated to the provider limit. Returns a :class:`SpeechResult`
        whose ``audio`` is raw bytes in the requested format (MP3 by default).

        Raises ``TTSNotConfiguredError`` when no API key is set.
        """
        cleaned = clean_text_for_speech(text)
        if not cleaned:
            raise ValueError("No speakable text after cleaning.")

        client = self._get_client()
        v = voice or self._config.voice
        fmt = (response_format or self._config.response_format or "mp3").lower()
        sp = self._config.speed if speed is None else speed

        response = await client.audio.speech.create(
            model=self._config.model,
            voice=v,  # type: ignore[arg-type]
            input=cleaned,
            response_format=fmt,  # type: ignore[arg-type]
            speed=sp,
        )
        # Non-streaming speech synthesis returns a fully-materialised object
        # whose ``.content`` holds the raw audio bytes (OpenAI + compatible
        # endpoints). Defensive: tolerate a missing/empty attribute.
        audio = getattr(response, "content", None) or b""
        if not isinstance(audio, (bytes, bytearray)):
            audio = bytes(audio)
        return SpeechResult(
            audio=bytes(audio),
            model=self._config.model,
            voice=v,
            text=cleaned,
            response_format=fmt,
            speed=sp,
        )


# --------------------------------------------------------------------------- #
# Lazy singleton
# --------------------------------------------------------------------------- #

_tts_client_instance: Optional[TTSClient] = None


def get_tts_client() -> TTSClient:
    """Get the singleton TTS client (lazy-initialised)."""
    global _tts_client_instance
    if _tts_client_instance is None:
        _tts_client_instance = TTSClient()
    return _tts_client_instance


def reset_tts_client() -> None:
    """Reset the singleton (used by tests to inject a mock config)."""
    global _tts_client_instance
    _tts_client_instance = None
