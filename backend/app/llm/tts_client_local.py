"""
Local TTS Client using mlx-audio (Kokoro model).

This implements the same interface as ``TTSClient`` (synthesize, synthesize_chunks,
is_configured) but uses the Kokoro-82M model running locally via mlx-audio on Apple
Silicon. No API key required, zero latency, privacy-friendly.

The model is lazy-loaded on first synthesis (downloads from HuggingFace, ~330MB)
and stays resident in memory for subsequent requests. Audio is generated as WAV
bytes in-memory — no file I/O, no caching by default.
"""
from __future__ import annotations

import asyncio
import io
import struct
import wave
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import numpy as np

from app.llm.tts_client import SpeechResult, clean_text_for_speech
from app.llm.tts_config import TTSConfig, OPENAI_TO_KOKORO


class MLXImportError(RuntimeError):
    """Raised when mlx-audio cannot be imported (non-Apple-Silicon or not installed)."""


def _map_voice(voice: str, provider: str) -> str:
    """Map OpenAI voice IDs to Kokoro voice IDs for compatibility.

    If the voice is already a Kokoro voice ID (starts with "af_", "am_", "bf_", "bm_"),
    return it as-is. Otherwise, look it up in the OpenAI→Kokoro mapping.

    Args:
        voice: The voice ID to map.
        provider: The TTS provider (for context).

    Returns:
        A valid Kokoro voice ID.
    """
    # Already a Kokoro voice prefix?
    if voice.startswith(("af_", "am_", "bf_", "bm_")):
        return voice

    # Map OpenAI voice to Kokoro
    return OPENAI_TO_KOKORO.get(voice, "af_heart")


def _mx_to_wav_bytes(audio_mx, sample_rate: int = 24000) -> bytes:
    """Convert an mlx array waveform to WAV bytes without writing to disk.

    Args:
        audio_mx: mlx array of float32 audio samples (normalized to [-1, 1]).
        sample_rate: Sample rate in Hz (Kokoro uses 24000 Hz).

    Returns:
        WAV-encoded audio as bytes.
    """
    import mlx.core as mx

    # mlx.array → numpy → 16-bit PCM
    samples = np.array(audio_mx, dtype=np.float32)
    # Normalize to [-1, 1] then convert to int16
    samples = np.clip(samples, -1.0, 1.0)
    samples_int16 = (samples * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)  # mono
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)  # 24000 Hz
        wf.writeframes(samples_int16.tobytes())
    return buf.getvalue()


class MLXTTSClient:
    """Local TTS client using mlx-audio (Kokoro). No API key needed."""

    def __init__(self, cfg: TTSConfig):
        self._config = cfg
        self._model = None  # lazy-loaded on first synthesis

    @property
    def config(self) -> TTSConfig:
        return self._config

    @property
    def is_configured(self) -> bool:
        # MLX provider is always available when selected (imports checked on use)
        return True

    def _get_model(self):
        """Lazy-load the Kokoro model on first use (singleton)."""
        if self._model is None:
            try:
                from mlx_audio.tts.utils import load_model
            except ImportError as exc:
                raise MLXImportError(
                    "mlx-audio is not available. Install with: "
                    "uv add mlx-audio misaki (Apple Silicon only)"
                ) from exc

            # Load Kokoro-82M model (downloads on first use, ~330MB)
            self._model = load_model("mlx-community/Kokoro-82M-bf16")
        return self._model

    async def synthesize(
        self,
        text: str,
        *,
        voice: Optional[str] = None,
        response_format: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> SpeechResult:
        """Synthesize speech audio for the given text using Kokoro.

        The text is cleaned for speech (markdown/dice/choices stripped) and
        truncated to the provider limit. Returns a :class:`SpeechResult`
        whose ``audio`` is raw WAV bytes.

        Args:
            text: Text to synthesize.
            voice: Voice ID (OpenAI or Kokoro). Maps OpenAI→Kokoro automatically.
            response_format: Ignored (always WAV for MLX).
            speed: Playback speed (0.25–4.0).

        Returns:
            SpeechResult with WAV audio bytes.
        """
        cleaned = clean_text_for_speech(text)
        if not cleaned:
            raise ValueError("No speakable text after cleaning.")

        model = self._get_model()
        kokoro_voice = _map_voice(voice or self._config.voice, self._config.provider)

        # mlx-audio generate() is synchronous — run in executor
        results = await asyncio.to_thread(
            list,
            model.generate(
                text=cleaned,
                voice=kokoro_voice,
                speed=speed or self._config.speed,
            ),
        )

        # Concatenate all segments (long text yields multiple)
        import mlx.core as mx
        all_audio = mx.concatenate([r.audio for r in results])

        # Convert mx.array → WAV bytes in memory
        wav_bytes = _mx_to_wav_bytes(all_audio, sample_rate=24000)

        return SpeechResult(
            audio=wav_bytes,
            model=self._config.model,
            voice=kokoro_voice,
            text=cleaned,
            response_format="wav",
            speed=speed or self._config.speed,
        )

    async def synthesize_chunks(
        self,
        chunks: list[str],
        *,
        voice: Optional[str] = None,
        response_format: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> AsyncIterator[tuple[int, SpeechResult]]:
        """Synthesize multiple text chunks, yielding results as they complete.

        Chunks are synthesized sequentially (to match OpenAI behavior).
        Yields ``(index, SpeechResult)`` tuples where ``index`` is the chunk's
        position in the input list.

        Args:
            chunks: List of text chunks to synthesize.
            voice: Voice ID (OpenAI or Kokoro).
            response_format: Ignored (always WAV for MLX).
            speed: Playback speed.

        Yields:
            (index, SpeechResult) for each non-empty chunk.
        """
        v = voice or self._config.voice
        sp = speed or self._config.speed

        for idx, chunk in enumerate(chunks):
            cleaned = clean_text_for_speech(chunk)
            if not cleaned:
                # Skip empty chunks but maintain index continuity
                continue
            result = await self.synthesize(
                cleaned,
                voice=v,
                speed=sp,
            )
            yield idx, result