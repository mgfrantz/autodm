# Design Research: Local TTS via mlx-audio (Kokoro)

> **Status:** Staged for implementation — ready for dev agent execution
> **Created:** 2025-07-14
> **Goal:** Add on-device TTS using Apple's MLX framework so the game
> works out-of-the-box without a cloud API key. Default provider; cloud
> (OpenAI) remains as an optional upgrade.

## Why Local TTS?

The current TTS system requires a `TTS_API_KEY` (OpenAI or compatible) and
returns 503 when unconfigured. Local TTS means:

- **Zero-config voice narration** — works immediately on any Apple Silicon Mac
- **No API costs** — unlimited synthesis for free
- **Lower latency** — no network round-trip
- **Privacy** — narration text never leaves the machine

## mlx-audio Library

**Repo:** <https://github.com/Blaizzy/mlx-audio>
**Package:** `pip install mlx-audio` (also: `pip install misaki` for Kokoro text processing)
**Requirements:** Apple Silicon (M1/M2/M3/M4), Python 3.10+, MLX framework

### Kokoro Model

- **Model ID:** `mlx-community/Kokoro-82M-bf16`
- **Quantized variants:** 8bit, 6bit, 4bit (lower memory, slightly lower quality)
- **Size:** ~82M params (tiny — loads in seconds, uses <500MB RAM)
- **Languages:** EN (primary), JA, ZH, FR, ES, IT, PT, HI
- **Voices:** 54 presets (American/British English, Japanese, Chinese, etc.)
- **Sample rate:** 24000 Hz

### Python API

```python
from mlx_audio.tts.utils import load_model

# Load model (lazy — downloads from HuggingFace on first use, ~330MB)
model = load_model("mlx-community/Kokoro-82M-bf16")

# Generate speech (generator yields segments for long text)
for result in model.generate(
    text="Welcome to the adventure!",
    voice="af_heart",    # American female — warm, neutral
    speed=1.0,
    lang_code="a",        # American English
):
    audio = result.audio  # mx.array (1D waveform, float32, 24kHz)
```

### Voice Presets (Kokoro)

Kokoro has 54 voices. Key ones for DnD narration:

| Voice | Description | Good for |
|-------|-------------|----------|
| `af_heart` | Warm, neutral, American female | Default narrator |
| `af_bella` | Bright, expressive, American female | Female heroes, elves |
| `af_nova` | Energetic, American female | Young characters |
| `af_sky` | Soft, ethereal, American female | Clerics, spirits |
| `am_adam` | Deep, steady, American male | Villains, baritones |
| `am_echo` | Warm, male | Male warriors, dwarves |
| `bm_george` | Deep British male | Wise NPCs, mentors |
| `bf_emma` | Refined British female | Nobles, royalty |

### OpenAI Voice → Kokoro Voice Mapping

For compatibility with the existing NPC voice-mapping system (which uses
OpenAI voice IDs), map the 6 OpenAI voices to Kokoro equivalents:

| OpenAI | Kokoro | Rationale |
|--------|--------|-----------|
| `alloy` | `af_heart` | Neutral default |
| `echo` | `am_echo` | Warm male |
| `fable` | `af_bella` | Expressive |
| `onyx` | `am_adam` | Deep male |
| `nova` | `af_nova` | Bright female |
| `shimmer` | `af_sky` | Ethereal female |

When `TTS_PROVIDER=mlx`, the voice registry exposes Kokoro voices (mapped from
OpenAI names). The frontend doesn't need changes — it already sends voice IDs.

---

## Architecture: MLXTTSClient

The existing `TTSClient` is hardcoded to the OpenAI async client. We add a new
`MLXTTSClient` that implements the same interface (`synthesize()`,
`synthesize_chunks()`, `is_configured`) but uses mlx-audio locally.

### Provider Selection

```
TTS_PROVIDER=mlx    → MLXTTSClient (default on Apple Silicon)
TTS_PROVIDER=openai → TTSClient (existing, cloud)
TTS_PROVIDER=none   → disabled
```

A factory function `get_tts_client()` returns the right client based on config.

### MLXTTSClient Design

```python
class MLXTTSClient:
    """Local TTS client using mlx-audio (Kokoro). No API key needed."""

    def __init__(self, cfg: TTSConfig):
        self._config = cfg
        self._model = None  # lazy-loaded on first synthesis

    @property
    def is_configured(self) -> bool:
        return True  # always configured when mlx provider is selected

    def _get_model(self):
        """Lazy-load the Kokoro model on first use (singleton)."""
        if self._model is None:
            from mlx_audio.tts.utils import load_model
            self._model = load_model("mlx-community/Kokoro-82M-bf16")
        return self._model

    async def synthesize(self, text, *, voice=None, **kwargs) -> SpeechResult:
        model = self._get_model()
        kokoro_voice = _map_voice(voice or self._config.voice)

        # mlx-audio generate() is synchronous — run in executor
        import asyncio
        results = await asyncio.to_thread(
            list, model.generate(text=text, voice=kokoro_voice, speed=self._config.speed)
        )
        # Concatenate all segments (long text yields multiple)
        import mlx.core as mx
        all_audio = mx.concatenate([r.audio for r in results])

        # Convert mx.array → WAV bytes in memory (no file I/O)
        wav_bytes = _mx_to_wav_bytes(all_audio, sample_rate=24000)

        return SpeechResult(
            audio=wav_bytes,
            model="kokoro-82m",
            voice=kokoro_voice,
            text=text,
            response_format="wav",
            speed=self._config.speed,
        )

    async def synthesize_chunks(self, chunks, *, voice=None, **kwargs):
        """Same interface as TTSClient.synthesize_chunks — sequential."""
        v = voice or self._config.voice
        for idx, chunk in enumerate(chunks):
            cleaned = clean_text_for_speech(chunk)
            if not cleaned:
                continue
            result = await self.synthesize(cleaned, voice=v)
            yield idx, result
```

### mx.array → WAV Bytes (In-Memory)

```python
import io
import wave
import struct

def _mx_to_wav_bytes(audio_mx, sample_rate: int = 24000) -> bytes:
    """Convert an mlx array waveform to WAV bytes without writing to disk."""
    import mlx.core as mx
    import numpy as np

    # mx.array → numpy → 16-bit PCM
    samples = np.array(audio_mx, dtype=np.float32)
    # Normalize to [-1, 1] then convert to int16
    samples = np.clip(samples, -1.0, 1.0)
    samples_int16 = (samples * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)            # mono
        wf.setsampwidth(2)            # 16-bit
        wf.setframerate(sample_rate)  # 24000 Hz
        wf.writeframes(samples_int16.tobytes())
    return buf.getvalue()
```

**No files. No caching. Pure in-memory bytes.**

### No Audio Caching

Mike's requirement: **don't store bloated audio files.** The current system
caches base64-encoded audio in `game_state["audio"]`, which bloats the SQLite
database (each narration = ~100KB-500KB of base64).

For local TTS, we **disable caching by default**:

- `POST /tts/narrate` — synthesizes on demand, returns audio bytes directly
  (like `/tts/synthesize` does today). Does NOT write to `game_state["audio"]`.
- `POST /tts/narrate/stream` — streams chunks as before, but does NOT cache
  the concatenated result. Each chunk is ephemeral.
- `GET /tts/audio/{id}` — returns 404 for local TTS (nothing cached).
- `GET /tts` (list) — returns empty list for local TTS.
- `DELETE /tts/{id}` — no-op for local TTS.

The frontend auto-narrate feature still works — it calls `/tts/narrate` (or
stream), gets audio bytes, plays them, and discards. No persistence.

**Config flag:** `TTS_CACHE=false` (default when `TTS_PROVIDER=mlx`). Can be
set to `true` to enable caching (for cloud providers where re-synthesis costs
money).

---

## Implementation Plan

### Backend

#### 1. Dependencies — `pyproject.toml` (MODIFY)

Add to project dependencies:
```toml
mlx-audio = {version = ">=0.1.0", markers = "sys_platform == 'darwin'"}
misaki = {version = ">=0.1.0", markers = "sys_platform == 'darwin'"}
```

Platform-marked so the package installs cleanly on non-Mac (CI, etc.) — it
just won't be importable there, which is fine since `TTS_PROVIDER=mlx` is
only used on Apple Silicon.

#### 2. Config — `backend/app/llm/tts_config.py` (MODIFY)

```python
@dataclass
class TTSConfig:
    provider: str            # "mlx", "openai", or "none"
    model: str               # "kokoro-82m" or "tts-1"
    api_key: str
    base_url: Optional[str] = None
    voice: str = "af_heart"  # Kokoro default when provider=mlx
    response_format: str = "wav"   # WAV for local (no ffmpeg needed)
    speed: float = 1.0
    cache_audio: bool = False      # NEW — false by default for mlx

    @property
    def is_configured(self) -> bool:
        if self.provider == "mlx":
            return True   # always available on Apple Silicon
        return self.provider != "none" and bool(self.api_key)
```

Default provider changes based on platform:
```python
def _default_provider() -> str:
    import platform
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return "mlx"
    return "openai"
```

Add Kokoro voice registry:
```python
KOKORO_VOICES: list[tuple[str, str, str]] = [
    ("af_heart", "Warm, neutral, American female", "Default narrator"),
    ("af_bella", "Bright, expressive, American female", "Female heroes, elves"),
    ("af_nova",  "Energetic, American female", "Young characters"),
    ("af_sky",   "Soft, ethereal, American female", "Clerics, spirits"),
    ("am_adam",  "Deep, steady, American male", "Villains, baritones"),
    ("am_echo",  "Warm, American male", "Warriors, dwarves, guards"),
    # ... more available
]

OPENAI_TO_KOKORO: dict[str, str] = {
    "alloy": "af_heart", "echo": "am_echo", "fable": "af_bella",
    "onyx": "am_adam", "nova": "af_nova", "shimmer": "af_sky",
}
```

#### 3. MLX TTS Client — `backend/app/llm/tts_client_local.py` (NEW)

`MLXTTSClient` class as described above, plus:
- `_mx_to_wav_bytes()` helper (in-memory WAV conversion)
- `_map_voice()` — OpenAI voice → Kokoro voice mapping
- Lazy model loading (singleton — model stays loaded between requests)
- `asyncio.to_thread()` wrapping the synchronous `model.generate()` call

**Tests** (`backend/tests/test_tts_local.py`):
- Voice mapping (all 6 OpenAI voices → Kokoro)
- `_mx_to_wav_bytes` produces valid WAV header
- WAV bytes are non-empty
- `MLXTTSClient.is_configured` is always True
- `synthesize()` returns `SpeechResult` with WAV bytes
- `synthesize_chunks()` yields sequential results
- Model lazy-loading (singleton — doesn't reload on second call)
- Graceful error on mlx-audio import failure (non-Apple-Silicon)
- `clean_text_for_speech` still works with local client

#### 4. Client Factory — `backend/app/llm/tts_client.py` (MODIFY)

Update `get_tts_client()` to dispatch based on provider:
```python
def get_tts_client():
    global _tts_client_instance
    if _tts_client_instance is None:
        if _default_config.provider == "mlx":
            from app.llm.tts_client_local import MLXTTSClient
            _tts_client_instance = MLXTTSClient(_default_config)
        else:
            _tts_client_instance = TTSClient(_default_config)
    return _tts_client_instance
```

Both clients implement the same interface: `is_configured`, `synthesize()`,
`synthesize_chunks()`, `config`. The API layer (`api/tts.py`) doesn't need to
know which one it's using.

#### 5. API Caching Behavior — `backend/app/api/tts.py` (MODIFY)

- `_cache_speech()` calls become conditional: `if client.config.cache_audio:`
- `narrate_latest()` — when caching disabled, return audio bytes directly
  (like `synthesize_speech` does) instead of metadata + separate audio fetch
- `narrate_latest_stream()` — skip the concatenation + caching step
- `get_audio_bytes()` — return 404 when caching disabled
- `list_audio()` — return empty when caching disabled

#### 6. Voice Registry Update — `backend/app/llm/tts_config.py` (MODIFY)

`voices_as_dicts()` and `AVAILABLE_VOICES` should return Kokoro voices when
`provider == "mlx"`. Add a function that picks the right registry:
```python
def get_available_voices(provider: str) -> list[tuple[str, str, str]]:
    if provider == "mlx":
        return KOKORO_VOICES
    return AVAILABLE_VOICES  # existing OpenAI voices
```

### Frontend

Minimal changes — the frontend already handles audio bytes from the TTS
endpoints. The key change is **not assuming audio is cached**:

#### 7. Types — `frontend/src/types/index.ts` (MODIFY)

Add `cache_audio?: boolean` to TTS status response (optional).

#### 8. VoicePanel — `frontend/src/components/VoicePanel.tsx` (MODIFY)

- Voice dropdown should show Kokoro voice names when provider is mlx
  (the backend already returns the right voices via `/tts/voices`)
- "Cached Narrations" section: hide when `cache_audio === false`
- No other changes needed — synthesis + playback work the same

#### 9. Auto-narrate — no changes

The auto-narrate feature calls `/tts/narrate` or `/tts/narrate/stream`, gets
audio bytes, plays them. This works identically with local TTS — just faster.

---

## .env Configuration

```bash
# Local TTS (default on Apple Silicon) — zero config needed
TTS_PROVIDER=mlx                    # "mlx" (local), "openai" (cloud), "none"
TTS_MODEL=kokoro-82m                # model identifier
TTS_VOICE=af_heart                  # default Kokoro voice
TTS_SPEED=1.0                       # playback speed

# Optional: enable audio caching (off by default for local)
TTS_CACHE=false

# Cloud TTS (optional upgrade)
# TTS_PROVIDER=openai
# TTS_API_KEY=sk-...
# TTS_MODEL=tts-1
```

---

## Test Plan Summary

| Layer | File | Tests |
|-------|------|-------|
| Config | `test_tts_config.py` (extend) | 4 — default provider on Mac, mlx voice registry, OpenAI→Kokoro mapping, cache_audio flag |
| Client | `test_tts_local.py` (NEW) | 9 — voice mapping, WAV conversion, is_configured, synthesize, synthesize_chunks, lazy model loading, import error, text cleaning, singleton |
| API | `test_tts.py` (extend) | 5 — narrate without caching, stream without caching, audio 404 when uncached, list empty when uncached, voices endpoint returns Kokoro voices |
| **Total** | | **~18 new tests** |

### Verification Checklist
- [ ] `uv add mlx-audio misaki` works on Apple Silicon
- [ ] `uv run pytest` — all existing tests pass + new tests green
- [ ] `cd frontend && npx tsc --noEmit` — clean
- [ ] `cd frontend && npm run build` — clean
- [ ] `cd frontend && npm test` — all frontend tests pass
- [ ] Manual: start backend with `TTS_PROVIDER=mlx`, call `/tts/narrate`,
      hear audio. Check game_state does NOT contain cached audio.
- [ ] PROGRESS.md updated
- [ ] Commit: `feat: local TTS via mlx-audio (Kokoro) — on-demand, no caching`
- [ ] Push to `develop`

---

## Key Design Decisions

1. **mlx as default provider on Apple Silicon** — zero-config out of the box
2. **Same interface as cloud TTS** — `MLXTTSClient` implements the same
   `synthesize()` / `synthesize_chunks()` / `is_configured` interface
3. **WAV not MP3** — avoids ffmpeg dependency; WAV works natively
4. **No audio caching by default** — on-demand generation, no bloated DB.
   `TTS_CACHE=true` re-enables it for cloud providers.
5. **Voice mapping** — existing NPC voice assignments (stored as OpenAI voice
   IDs) work seamlessly via `OPENAI_TO_KOKORO` mapping
6. **Lazy model loading** — Kokoro model (~330MB) loads on first synthesis,
   stays resident in memory for subsequent requests
7. **`asyncio.to_thread`** — mlx-audio's `generate()` is synchronous; wrapping
   in a thread keeps the async API non-blocking

## What This Does NOT Include (future enhancements)
- Per-NPC Kokoro voice picker (currently uses OpenAI→Kokoro mapping)
- Voice cloning (mlx-audio supports it for some models, not Kokoro)
- STT (mlx-audio has Whisper support — could add voice input later)
- Kokoro quantized variants (8bit/4bit for lower memory Macs — config option)
- A/B quality comparison between local and cloud TTS
- Streaming chunk-level playback from mlx-audio's generator (currently we
  concatenate segments before returning; could stream per-segment for lower
  latency on long narrations)

## Changelog
- 2025-07-14: Initial design — staged by Mike for next-session implementation
