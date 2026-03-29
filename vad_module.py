"""Voice Activity Detection module for real-time audio streaming."""

import numpy as np
import logging
from typing import Optional, Callable
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class VADConfig:
    """Configuration for VAD."""
    sample_rate: int = 16000
    frame_duration_ms: int = 30
    threshold: float = 0.5
    min_speech_duration_ms: int = 250
    min_silence_duration_ms: int = 500
    padding_duration_ms: int = 300


class VoiceActivityDetector:
    """Voice Activity Detection using Silero VAD or WebRTC VAD fallback."""

    def __init__(self, config: Optional[VADConfig] = None):
        self.config = config or VADConfig()
        self._vad = None
        self._use_silero = False

        # Buffer for audio frames
        self.frame_size = int(self.config.sample_rate * self.config.frame_duration_ms / 1000)
        self.audio_buffer = deque(maxlen=1000)

        # Speech detection state
        self.is_speech_active = False
        self.speech_start_time: Optional[float] = None
        self.speech_end_time: Optional[float] = None
        self.silence_start_time: Optional[float] = None

        self._load_vad()

    def _load_vad(self):
        """Load VAD model."""
        try:
            # Try Silero VAD first (more accurate)
            import torch
            torch.set_num_threads(1)

            model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False
            )

            (get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks) = utils

            self._vad = model
            self._vad_iterator = VADIterator(model)
            self._use_silero = True
            logger.info("Loaded Silero VAD")

        except Exception as e:
            logger.warning(f"Silero VAD not available: {e}")
            try:
                # Fallback to WebRTC VAD
                import webrtcvad
                self._vad = webrtcvad.Vad(2)  # Aggressiveness 0-3
                self._use_silero = False
                logger.info("Loaded WebRTC VAD")
            except ImportError:
                logger.error("No VAD available. Install silero or webrtcvad.")
                self._vad = None

    def process_frame(self, audio_frame: np.ndarray) -> dict:
        """Process a single audio frame and return speech detection results."""
        if self._vad is None:
            return {'is_speech': False, 'confidence': 0.0}

        try:
            if self._use_silero:
                return self._process_silero(audio_frame)
            else:
                return self._process_webrtc(audio_frame)
        except Exception as e:
            logger.error(f"VAD processing error: {e}")
            return {'is_speech': False, 'confidence': 0.0}

    def _process_silero(self, audio_frame: np.ndarray) -> dict:
        """Process frame with Silero VAD."""
        import torch

        # Convert to tensor
        tensor = torch.from_numpy(audio_frame).float()

        # Get speech probability
        speech_prob = self._vad(tensor, self.config.sample_rate).item()

        is_speech = speech_prob > self.config.threshold

        return {
            'is_speech': is_speech,
            'confidence': speech_prob,
            'speech_prob': speech_prob
        }

    def _process_webrtc(self, audio_frame: np.ndarray) -> dict:
        """Process frame with WebRTC VAD."""
        # WebRTC expects 16-bit PCM
        pcm_data = (audio_frame * 32767).astype(np.int16).tobytes()

        is_speech = self._vad.is_speech(pcm_data, self.config.sample_rate)

        return {
            'is_speech': is_speech,
            'confidence': 1.0 if is_speech else 0.0
        }

    def process_stream(
        self,
        audio_data: bytes,
        callback: Optional[Callable] = None
    ) -> list:
        """Process a stream of audio data and detect speech segments."""
        # Convert bytes to numpy array
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        # Split into frames
        frame_size = self.frame_size
        frames = [
            audio_array[i:i + frame_size]
            for i in range(0, len(audio_array), frame_size)
        ]

        speech_segments = []
        current_segment_start = None

        for frame in frames:
            if len(frame) < frame_size:
                continue  # Skip incomplete frames

            result = self.process_frame(frame)

            if result['is_speech']:
                if current_segment_start is None:
                    current_segment_start = len(speech_segments)
                self.is_speech_active = True
            else:
                if self.is_speech_active and current_segment_start is not None:
                    # End of speech segment
                    speech_segments.append({
                        'start': current_segment_start * self.config.frame_duration_ms,
                        'end': len(speech_segments) * self.config.frame_duration_ms,
                        'is_speech': True
                    })
                    current_segment_start = None
                self.is_speech_active = False

            if callback:
                callback(result)

        return speech_segments

    def is_speech(self, audio_data: bytes) -> bool:
        """Quick check if audio contains speech."""
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        # Process a few frames
        frame_size = self.frame_size
        frames_processed = 0
        speech_frames = 0

        for i in range(0, len(audio_array), frame_size):
            frame = audio_array[i:i + frame_size]
            if len(frame) < frame_size:
                continue

            result = self.process_frame(frame)
            frames_processed += 1
            if result['is_speech']:
                speech_frames += 1

        if frames_processed == 0:
            return False

        # Speech if more than 30% of frames contain speech
        return (speech_frames / frames_processed) > 0.3


class StreamingVAD:
    """VAD optimized for streaming audio from Android client."""

    def __init__(self, config: Optional[VADConfig] = None):
        self.config = config or VADConfig()
        self.vad = VoiceActivityDetector(self.config)

        # State machine
        self.state = 'idle'  # idle, speech, silence
        self.speech_buffer = bytearray()
        self.silence_frames = 0
        self.speech_frames = 0

        # Callbacks
        self.on_speech_start: Optional[Callable] = None
        self.on_speech_end: Optional[Callable] = None
        self.on_speech_chunk: Optional[Callable] = None

    def process_chunk(self, audio_chunk: bytes) -> Optional[dict]:
        """Process an audio chunk from the stream."""
        # Detect speech in chunk
        is_speech = self.vad.is_speech(audio_chunk)

        result = {
            'state': self.state,
            'is_speech': is_speech,
            'audio_data': audio_chunk
        }

        if is_speech:
            self.speech_frames += 1
            self.silence_frames = 0

            if self.state == 'idle':
                # Start of speech
                self.state = 'speech'
                self.speech_buffer = bytearray(audio_chunk)
                if self.on_speech_start:
                    self.on_speech_start()
            elif self.state == 'speech':
                # Continue speech
                self.speech_buffer.extend(audio_chunk)
                if self.on_speech_chunk:
                    self.on_speech_chunk(audio_chunk)
        else:
            self.silence_frames += 1

            if self.state == 'speech':
                # Check if silence is long enough to end speech
                silence_duration = self.silence_frames * self.config.frame_duration_ms
                if silence_duration >= self.config.min_silence_duration_ms:
                    # End of speech
                    speech_data = bytes(self.speech_buffer)
                    self.state = 'idle'
                    self.speech_buffer = bytearray()
                    self.silence_frames = 0

                    result['speech_data'] = speech_data
                    result['state'] = 'speech_end'

                    if self.on_speech_end:
                        self.on_speech_end(speech_data)

        return result

    def reset(self):
        """Reset VAD state."""
        self.state = 'idle'
        self.speech_buffer = bytearray()
        self.silence_frames = 0
        self.speech_frames = 0
