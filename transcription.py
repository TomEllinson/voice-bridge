"""Transcription module using local Whisper for voice-to-text."""

import os
import tempfile
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class WhisperTranscriber:
    """Local Whisper transcription with faster-whisper backend."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "default"
    ):
        """Initialize the Whisper transcriber.

        Args:
            model_size: Model size (tiny, base, small, medium, large)
            device: Device to use (cpu, cuda, auto)
            compute_type: Compute type (default, int8, float16)
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def _load_model(self):
        """Lazy load the Whisper model."""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
                logger.info(f"Loading Whisper model: {self.model_size}")
                self._model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type
                )
            except ImportError:
                logger.error("faster_whisper not installed. Falling back to openai-whisper")
                import whisper
                self._model = whisper.load_model(self.model_size)
                self._use_faster = False
            else:
                self._use_faster = True
        return self._model

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        task: str = "transcribe"
    ) -> dict:
        """Transcribe an audio file to text.

        Args:
            audio_path: Path to the audio file
            language: Optional language code (e.g., 'en', 'es')
            task: Task type ('transcribe' or 'translate')

        Returns:
            Dict with 'text', 'segments', and 'language' keys
        """
        model = self._load_model()

        try:
            if hasattr(self, '_use_faster') and self._use_faster:
                # faster-whisper API
                segments, info = model.transcribe(
                    audio_path,
                    language=language,
                    task=task,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=500)
                )

                text_parts = []
                segment_list = []
                for segment in segments:
                    text_parts.append(segment.text)
                    segment_list.append({
                        'start': segment.start,
                        'end': segment.end,
                        'text': segment.text
                    })

                return {
                    'text': ' '.join(text_parts).strip(),
                    'segments': segment_list,
                    'language': info.language,
                    'duration': info.duration
                }
            else:
                # openai-whisper API
                result = model.transcribe(
                    audio_path,
                    language=language,
                    task=task
                )
                return {
                    'text': result['text'].strip(),
                    'segments': result.get('segments', []),
                    'language': result.get('language', 'unknown'),
                    'duration': None
                }

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise TranscriptionError(f"Failed to transcribe audio: {e}") from e

    def transcribe_bytes(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
        task: str = "transcribe"
    ) -> dict:
        """Transcribe audio from bytes.

        Args:
            audio_data: Raw audio bytes
            language: Optional language code
            task: Task type

        Returns:
            Dict with transcription results
        """
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as f:
            f.write(audio_data)
            temp_path = f.name

        try:
            return self.transcribe(temp_path, language, task)
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


class TranscriptionError(Exception):
    """Error during transcription."""
    pass


# Convenience function for quick transcription
def transcribe_audio(audio_path: str, model_size: str = "base") -> str:
    """Quick transcribe an audio file to text.

    Args:
        audio_path: Path to audio file
        model_size: Whisper model size

    Returns:
        Transcribed text
    """
    transcriber = WhisperTranscriber(model_size=model_size)
    result = transcriber.transcribe(audio_path)
    return result['text']
