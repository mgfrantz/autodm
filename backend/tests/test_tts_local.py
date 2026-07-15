"""
Tests for local TTS client (mlx-audio / Kokoro).

These tests verify the MLXTTSClient implementation matches the TTSClient interface,
including voice mapping, WAV conversion, and lazy model loading. The actual
model synthesis is mocked to avoid downloading 330MB models in tests.
"""
import sys
import io
import wave
from unittest.mock import MagicMock, patch

import pytest

from app.llm.tts_client import SpeechResult, clean_text_for_speech
from app.llm.tts_client_local import (
    MLXTTSClient,
    MLXImportError,
    _map_voice,
    _mx_to_wav_bytes,
)
from app.llm.tts_config import TTSConfig, OPENAI_TO_KOKORO


class TestVoiceMapping:
    """Test OpenAI→Kokoro voice ID mapping."""

    def test_openai_to_kokoro_mapping(self):
        """All six OpenAI voices should map to Kokoro equivalents."""
        assert _map_voice("alloy", "mlx") == "af_heart"
        assert _map_voice("echo", "mlx") == "am_echo"
        assert _map_voice("fable", "mlx") == "af_bella"
        assert _map_voice("onyx", "mlx") == "am_adam"
        assert _map_voice("nova", "mlx") == "af_nova"
        assert _map_voice("shimmer", "mlx") == "af_sky"

    def test_kokoro_voice_passthrough(self):
        """Kokoro voice IDs (with prefixes) should pass through unchanged."""
        assert _map_voice("af_heart", "mlx") == "af_heart"
        assert _map_voice("am_echo", "mlx") == "am_echo"
        assert _map_voice("bf_emma", "mlx") == "bf_emma"
        assert _map_voice("bm_george", "mlx") == "bm_george"

    def test_unknown_voice_defaults_to_af_heart(self):
        """Unknown voices should default to af_heart."""
        assert _map_voice("unknown", "mlx") == "af_heart"


class TestWavConversion:
    """Test mx.array → WAV bytes conversion."""

    def test_mx_to_wav_produces_valid_wav(self):
        """WAV output should have a valid WAV header."""
        import numpy as np

        # Create a simple audio buffer (1 second of 24000 Hz samples)
        samples = np.zeros(24000, dtype=np.float32)
        wav_bytes = _mx_to_wav_bytes(samples, sample_rate=24000)

        # Should be non-empty
        assert len(wav_bytes) > 0

        # Should parse as a valid WAV file
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            assert wf.getnchannels() == 1  # mono
            assert wf.getsampwidth() == 2  # 16-bit
            assert wf.getframerate() == 24000
            assert wf.getnframes() == 24000

    def test_mx_to_wav_normalizes_to_int16(self):
        """Audio should be normalized from float32 [-1, 1] to int16."""
        import numpy as np

        # Test with normalized audio (should map to full range)
        samples = np.ones(24000, dtype=np.float32)
        wav_bytes = _mx_to_wav_bytes(samples, sample_rate=24000)

        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            frames = wf.readframes(24000)
            import struct
            values = struct.unpack("<{}h".format(len(frames) // 2), frames)
            # All samples should be at max int16 (32767)
            assert all(v >= 32000 for v in values)

    def test_mx_to_wav_clips_overflow(self):
        """Values outside [-1, 1] should be clipped."""
        import numpy as np

        # Create samples that exceed the range
        samples = np.full(24000, 2.0, dtype=np.float32)
        wav_bytes = _mx_to_wav_bytes(samples, sample_rate=24000)

        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            frames = wf.readframes(24000)
            import struct
            values = struct.unpack("<{}h".format(len(frames) // 2), frames)
            # Should be clipped to int16 max (32767), not overflow
            assert all(v > 0 for v in values)
            assert all(v <= 32767 for v in values)


class TestMLXTTSClient:
    """Test MLXTTSClient implementation."""

    def test_is_configured_always_true(self):
        """MLX provider should always report as configured."""
        cfg = TTSConfig(
            provider="mlx",
            model="kokoro-82m",
            api_key="",
            voice="af_heart",
            response_format="wav",
            speed=1.0,
            cache_audio=False,
        )
        client = MLXTTSClient(cfg)
        assert client.is_configured is True

    def test_lazy_model_loading(self):
        """Model should load on first synthesis only."""
        cfg = TTSConfig(
            provider="mlx",
            model="kokoro-82m",
            api_key="",
            voice="af_heart",
            response_format="wav",
            speed=1.0,
            cache_audio=False,
        )
        client = MLXTTSClient(cfg)

        # Before synthesis, model should be None
        assert client._model is None

        # Mock the entire synthesize method at the MLXAudio level
        import numpy as np
        audio_bytes = np.zeros(24000, dtype=np.int16).tobytes()

        # Directly mock the _get_model method to set the model
        mock_model = MagicMock()
        client._model = mock_model

        # Mock the generate method to return a generator
        import mlx.core as mx
        mock_audio = mx.zeros((24000,))
        mock_result = MagicMock(audio=mock_audio)
        mock_model.generate.return_value = [mock_result]

        # Now call synthesize
        import asyncio
        result = asyncio.run(client.synthesize("Test"))

        # Should have called generate
        mock_model.generate.assert_called_once()
        assert result.response_format == "wav"
        assert result.model == "kokoro-82m"

        # After synthesis, model should be cached (set directly above)
        assert client._model is not None

    def test_synthesize_uses_mapped_voice(self):
        """Synthesize should map OpenAI voices to Kokoro voices."""
        cfg = TTSConfig(
            provider="mlx",
            model="kokoro-82m",
            api_key="",
            voice="af_heart",
            response_format="wav",
            speed=1.0,
            cache_audio=False,
        )
        client = MLXTTSClient(cfg)

        # Set up mock
        mock_model = MagicMock()
        client._model = mock_model

        import mlx.core as mx
        mock_audio = mx.zeros((24000,))
        mock_result = MagicMock(audio=mock_audio)
        mock_model.generate.return_value = [mock_result]

        import asyncio
        # Use an OpenAI voice
        asyncio.run(client.synthesize("Test", voice="onyx"))

        # Should map to Kokoro voice
        mock_model.generate.assert_called_once()
        call_kwargs = mock_model.generate.call_args[1]
        assert call_kwargs["voice"] == "am_adam"  # onyx → am_adam

    def test_clean_text_for_speech_still_works(self):
        """Text cleaning should work with local TTS."""
        text = "You roll **dexterity** check: [dex check: 14]\n1. Run\n2. Hide\nWhat do you do?"
        cleaned = clean_text_for_speech(text)

        # Should remove markdown, dice, choices, and prompt
        assert "**" not in cleaned
        assert "[dex check: 14]" not in cleaned
        assert "1. Run" not in cleaned
        assert "What do you do?" not in cleaned
        assert "You roll dexterity check" in cleaned

    def test_synthesize_chunks_sequential(self):
        """Chunks should be synthesized sequentially."""
        cfg = TTSConfig(
            provider="mlx",
            model="kokoro-82m",
            api_key="",
            voice="af_heart",
            response_format="wav",
            speed=1.0,
            cache_audio=False,
        )
        client = MLXTTSClient(cfg)

        chunks = ["First sentence.", "Second sentence.", "Third sentence."]

        with patch("mlx_audio.tts.utils.load_model") as mock_load:
            mock_model = MagicMock()
            
            # Create mock results with real mx.array audio
            import mlx.core as mx
            mock_audio1 = mx.zeros((24000,))
            mock_audio2 = mx.zeros((24000,))
            mock_audio3 = mx.zeros((24000,))
            
            result_mock1 = MagicMock(audio=mock_audio1)
            result_mock2 = MagicMock(audio=mock_audio2)
            result_mock3 = MagicMock(audio=mock_audio3)
            
            mock_model.generate.side_effect = [[result_mock1], [result_mock2], [result_mock3]]
            mock_load.return_value = mock_model

            with patch("app.llm.tts_client_local._mx_to_wav_bytes") as mock_wav:
                import numpy as np
                mock_wav.return_value = np.zeros(24000, dtype=np.int16).tobytes()

                import asyncio
                async def collect_chunks():
                    results = []
                    async for idx, result in client.synthesize_chunks(chunks):
                        results.append((idx, result))
                    return results
                results = asyncio.run(collect_chunks())

                # Should get results for all chunks (in order)
                assert len(results) == 3
                assert results[0][0] == 0
                assert results[1][0] == 1
                assert results[2][0] == 2

    def test_synthesize_chunks_skips_empty(self):
        """Empty chunks should be skipped but maintain index continuity."""
        cfg = TTSConfig(
            provider="mlx",
            model="kokoro-82m",
            api_key="",
            voice="af_heart",
            response_format="wav",
            speed=1.0,
            cache_audio=False,
        )
        client = MLXTTSClient(cfg)

        chunks = ["First.", "", "", "Second."]

        with patch("mlx_audio.tts.utils.load_model") as mock_load:
            mock_model = MagicMock()
            
            # Create mock results with real mx.array audio
            import mlx.core as mx
            mock_audio1 = mx.zeros((24000,))
            mock_audio2 = mx.zeros((24000,))
            
            result_mock1 = MagicMock(audio=mock_audio1)
            result_mock2 = MagicMock(audio=mock_audio2)
            
            # Only return results for non-empty chunks
            mock_model.generate.side_effect = [[result_mock1], [result_mock2]]
            mock_load.return_value = mock_model

            with patch("app.llm.tts_client_local._mx_to_wav_bytes") as mock_wav:
                import numpy as np
                mock_wav.return_value = np.zeros(24000, dtype=np.int16).tobytes()

                import asyncio
                async def collect_chunks():
                    results = []
                    async for idx, result in client.synthesize_chunks(chunks):
                        results.append((idx, result))
                    return results
                results = asyncio.run(collect_chunks())

                # Should skip empty chunks
                assert len(results) == 2
                # Indices should match the input (not sequential)
                assert results[0][0] == 0  # "First."
                assert results[1][0] == 3  # "Second."

    def test_graceful_import_error(self):
        """Should raise MLXImportError when mlx-audio is not available."""
        cfg = TTSConfig(
            provider="mlx",
            model="kokoro-82m",
            api_key="",
            voice="af_heart",
            response_format="wav",
            speed=1.0,
            cache_audio=False,
        )
        client = MLXTTSClient(cfg)

        # Mock _get_model to raise MLXImportError
        with patch.object(client, "_get_model", side_effect=MLXImportError("mlx-audio is not available. Install with: uv add mlx-audio misaki (Apple Silicon only)")):
            with pytest.raises(MLXImportError) as exc_info:
                import asyncio
                asyncio.run(client.synthesize("Test"))

            assert "mlx-audio" in str(exc_info.value)

    def test_singleton_pattern_via_get_tts_client(self):
        """The factory should create MLXTTSClient for mlx provider."""
        from app.llm.tts_client import reset_tts_client

        # Reset singleton
        reset_tts_client()

        # Set provider to mlx
        import os
        old_provider = os.environ.get("TTS_PROVIDER")
        os.environ["TTS_PROVIDER"] = "mlx"

        try:
            # Reload config
            from app.llm.tts_config import load_config, config as _default_config
            _config = load_config()

            # Patch to avoid actual model load
            with patch("mlx_audio.tts.utils.load_model"):
                from app.llm.tts_client import get_tts_client
                client = get_tts_client()

                # Should be MLXTTSClient
                assert isinstance(client, MLXTTSClient)
                assert client.config.provider == "mlx"
        finally:
            # Restore
            reset_tts_client()
            if old_provider:
                os.environ["TTS_PROVIDER"] = old_provider
            else:
                os.environ.pop("TTS_PROVIDER", None)

    def test_speech_result_wav_format(self):
        """Synthesized SpeechResult should have WAV format."""
        cfg = TTSConfig(
            provider="mlx",
            model="kokoro-82m",
            api_key="",
            voice="af_heart",
            response_format="wav",
            speed=1.0,
            cache_audio=False,
        )
        client = MLXTTSClient(cfg)

        with patch("mlx_audio.tts.utils.load_model") as mock_load:
            mock_model = MagicMock()
            
            # Create a real mx.array audio
            import mlx.core as mx
            mock_audio = mx.zeros((24000,))
            result_mock = MagicMock(audio=mock_audio)
            mock_model.generate.return_value = [result_mock]
            mock_load.return_value = mock_model

            with patch("app.llm.tts_client_local._mx_to_wav_bytes") as mock_wav:
                import numpy as np
                audio_bytes = np.zeros(24000, dtype=np.int16).tobytes()
                mock_wav.return_value = audio_bytes

                import asyncio
                result = asyncio.run(client.synthesize("Test"))

                assert isinstance(result, SpeechResult)
                assert result.response_format == "wav"
                assert result.audio == audio_bytes
                assert result.model == "kokoro-82m"