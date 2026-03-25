"""Text-to-speech engine using Kokoro or Piper for voice responses."""

import os
import tempfile
import logging
from pathlib import Path
from typing import Optional, Union
import io

logger = logging.getLogger(__name__)


class TTSEngine:
    """Base class for TTS engines."""

    def synthesize(self, text: str, voice: Optional[str] = None) -> bytes:
        """Synthesize text to audio bytes.

        Args:
            text: Text to speak
            voice: Voice ID to use

        Returns:
            Audio data as bytes
        """
        raise NotImplementedError

    def synthesize_to_file(
        self, text: str, output_path: str, voice: Optional[str] = None
    ) -> str:
        """Synthesize text and save to file.

        Args:
            text: Text to speak
            output_path: Output file path
            voice: Voice ID to use

        Returns:
            Path to output file
        """
        audio_data = self.synthesize(text, voice)
        with open(output_path, 'wb') as f:
            f.write(audio_data)
        return output_path


class KokoroTTS(TTSEngine):
    """Kokoro TTS engine - fast, local, high quality."""

    def __init__(self, voice: str = "af_bella"):
        """Initialize Kokoro TTS.

        Args:
            voice: Default voice ID (e.g., 'af_bella', 'af_sarah', 'am_adam')
        """
        self.default_voice = voice
        self._pipeline = None

    def _load_pipeline(self):
        """Lazy load the Kokoro pipeline."""
        if self._pipeline is None:
            try:
                from kokoro import KPipeline
                import torch

                # Use CPU for compatibility (CUDA capability issues on some GPUs)
                device = "cpu"
                logger.info(f"Loading Kokoro TTS on {device}")

                self._pipeline = KPipeline(lang_code='a', device=device)
            except ImportError:
                raise TTSError("Kokoro TTS not installed. Install with: pip install kokoro")

        return self._pipeline

    def synthesize(self, text: str, voice: Optional[str] = None) -> bytes:
        """Synthesize text using Kokoro."""
        pipeline = self._load_pipeline()
        voice_id = voice or self.default_voice

        try:
            # Generate audio
            generator = pipeline(text, voice=voice_id, speed=1.0)

            # Collect audio segments
            audio_segments = []
            for _, _, audio in generator:
                if audio is not None:
                    audio_segments.append(audio)

            if not audio_segments:
                raise TTSError("No audio generated")

            # Concatenate segments
            import torch
            full_audio = torch.cat(audio_segments, dim=0)

            # Convert to WAV bytes
            import soundfile as sf
            buffer = io.BytesIO()
            sf.write(buffer, full_audio.numpy(), 24000, format='WAV')
            buffer.seek(0)

            return buffer.read()

        except Exception as e:
            logger.error(f"Kokoro synthesis failed: {e}")
            raise TTSError(f"Failed to synthesize speech: {e}") from e


class PiperTTS(TTSEngine):
    """Piper TTS engine - lightweight, local."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        voice: str = "en_US-lessac-medium"
    ):
        """Initialize Piper TTS.

        Args:
            model_path: Path to Piper model directory
            voice: Voice model name
        """
        self.model_path = model_path or os.path.expanduser("~/.local/share/piper")
        self.voice = voice
        self._voice_path = None

    def _get_voice_path(self) -> str:
        """Get the voice model file path."""
        if self._voice_path is None:
            voice_file = Path(self.model_path) / f"{self.voice}.onnx"
            if not voice_file.exists():
                raise TTSError(
                    f"Piper voice not found: {voice_file}. "
                    "Download voices from: https://github.com/rhasspy/piper/releases"
                )
            self._voice_path = str(voice_file)
        return self._voice_path

    def synthesize(self, text: str, voice: Optional[str] = None) -> bytes:
        """Synthesize text using Piper."""
        try:
            from piper import PiperVoice
            import wave
            import io

            voice_path = self._get_voice_path() if voice is None else voice

            # Load voice
            synthesizer = PiperVoice.load(voice_path)

            # Generate audio
            audio_buffer = io.BytesIO()
            with wave.open(audio_buffer, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(synthesizer.config.sample_rate)

                # Synthesize
                synthesizer.synthesize(text, wav_file.write)

            audio_buffer.seek(0)
            return audio_buffer.read()

        except ImportError:
            raise TTSError("Piper TTS not installed. Install with: pip install piper-tts")
        except Exception as e:
            logger.error(f"Piper synthesis failed: {e}")
            raise TTSError(f"Failed to synthesize speech: {e}") from e


class FallbackTTS(TTSEngine):
    """Fallback TTS using pyttsx3 (system voices)."""

    def __init__(self):
        self._engine = None

    def _get_engine(self):
        """Lazy load pyttsx3."""
        if self._engine is None:
            try:
                import pyttsx3
                self._engine = pyttsx3.init()
                self._engine.setProperty('rate', 175)
            except ImportError:
                raise TTSError("No TTS engine available. Install kokoro, piper-tts, or pyttsx3")
        return self._engine

    def synthesize(self, text: str, voice: Optional[str] = None) -> bytes:
        """Synthesize using pyttsx3 (saves to temp file then reads)."""
        import tempfile

        engine = self._get_engine()

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            temp_path = f.name

        try:
            engine.save_to_file(text, temp_path)
            engine.runAndWait()

            with open(temp_path, 'rb') as f:
                return f.read()
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


class SmartTTS(TTSEngine):
    """Smart TTS that tries engines in order of preference."""

    def __init__(
        self,
        preferred_engine: Optional[str] = None,
        kokoro_voice: str = "af_bella",
        piper_voice: str = "en_US-lessac-medium"
    ):
        """Initialize smart TTS with fallback.

        Args:
            preferred_engine: Preferred engine ('kokoro', 'piper', 'pyttsx3')
            kokoro_voice: Default Kokoro voice
            piper_voice: Default Piper voice
        """
        self.preferred = preferred_engine
        self.kokoro_voice = kokoro_voice
        self.piper_voice = piper_voice
        self._engines = {}

    def _get_engine(self, name: str) -> Optional[TTSEngine]:
        """Get or create an engine by name."""
        if name not in self._engines:
            try:
                if name == 'kokoro':
                    self._engines[name] = KokoroTTS(self.kokoro_voice)
                elif name == 'piper':
                    self._engines[name] = PiperTTS(voice=self.piper_voice)
                elif name == 'pyttsx3':
                    self._engines[name] = FallbackTTS()
            except Exception as e:
                logger.warning(f"Failed to load {name} TTS: {e}")
                return None

        return self._engines.get(name)

    def synthesize(self, text: str, voice: Optional[str] = None) -> bytes:
        """Synthesize using best available engine."""
        engines_to_try = []

        if self.preferred:
            engines_to_try.append(self.preferred)
        engines_to_try.extend(['kokoro', 'piper', 'pyttsx3'])

        for engine_name in engines_to_try:
            engine = self._get_engine(engine_name)
            if engine:
                try:
                    logger.debug(f"Using {engine_name} TTS")
                    return engine.synthesize(text, voice)
                except Exception as e:
                    logger.warning(f"{engine_name} TTS failed: {e}")
                    continue

        raise TTSError("All TTS engines failed")


class TTSError(Exception):
    """Error during text-to-speech."""
    pass


# Convenience function
def speak(text: str, engine: Optional[str] = None) -> bytes:
    """Quick synthesize text to audio.

    Args:
        text: Text to speak
        engine: Preferred engine

    Returns:
        Audio data as WAV bytes
    """
    tts = SmartTTS(preferred_engine=engine)
    return tts.synthesize(text)
