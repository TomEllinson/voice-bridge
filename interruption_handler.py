"""Interruption handler for managing turn-taking in voice conversations.

Detects when user speaks during agent playback and handles the interruption
to provide natural conversation flow.
"""

import asyncio
import logging
from typing import Optional, Callable
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np

from vad_module import VoiceActivityDetector, VADConfig

logger = logging.getLogger(__name__)


class ConversationState(Enum):
    """States in the voice conversation."""
    IDLE = auto()
    USER_SPEAKING = auto()
    PROCESSING = auto()
    AGENT_SPEAKING = auto()
    INTERRUPTED = auto()


@dataclass
class InterruptionConfig:
    """Configuration for interruption detection."""
    # VAD threshold for interruption detection
    vad_threshold: float = 0.6
    # Minimum speech duration to trigger interruption (seconds)
    min_speech_duration: float = 0.3
    # Cooldown after interruption (seconds)
    cooldown_duration: float = 0.5
    # Number of consecutive speech frames to trigger interruption
    speech_frames_threshold: int = 3


class InterruptionHandler:
    """Manages turn-taking and interruption detection in voice conversations."""

    def __init__(self, config: Optional[InterruptionConfig] = None):
        self.config = config or InterruptionConfig()
        self.state = ConversationState.IDLE
        self.vad = VoiceActivityDetector(VADConfig(threshold=self.config.vad_threshold))

        # Callbacks
        self.on_interruption: Optional[Callable] = None
        self.on_state_change: Optional[Callable] = None
        self.on_user_speech: Optional[Callable] = None

        # State tracking
        self._speech_frames = 0
        self._is_playing = False
        self._lock = asyncio.Lock()

    async def set_state(self, new_state: ConversationState):
        """Set conversation state and notify listeners."""
        async with self._lock:
            if self.state != new_state:
                old_state = self.state
                self.state = new_state
                logger.info(f"State transition: {old_state.name} -> {new_state.name}")

                if self.on_state_change:
                    try:
                        self.on_state_change(old_state, new_state)
                    except Exception as e:
                        logger.error(f"State change callback error: {e}")

    def start_playback(self):
        """Mark that agent started speaking."""
        self._is_playing = True
        self._speech_frames = 0
        asyncio.create_task(self.set_state(ConversationState.AGENT_SPEAKING))
        logger.debug("Agent playback started - monitoring for interruptions")

    def stop_playback(self):
        """Mark that agent stopped speaking."""
        self._is_playing = False
        self._speech_frames = 0
        asyncio.create_task(self.set_state(ConversationState.IDLE))
        logger.debug("Agent playback stopped")

    async def process_audio(self, audio_data: bytes) -> dict:
        """Process audio chunk and handle interruptions.

        Args:
            audio_data: Raw audio bytes from microphone

        Returns:
            Dict with processing results
        """
        result = {
            'interrupted': False,
            'is_speech': False,
            'state': self.state.name
        }

        # Only process during agent playback or always-listening mode
        if not self._is_playing and self.state != ConversationState.IDLE:
            return result

        # Check for speech
        is_speech = self.vad.is_speech(audio_data)
        result['is_speech'] = is_speech

        if is_speech:
            self._speech_frames += 1

            # Check for interruption during playback
            if self._is_playing and self._speech_frames >= self.config.speech_frames_threshold:
                result['interrupted'] = True
                await self._handle_interruption()
        else:
            self._speech_frames = 0

        return result

    async def _handle_interruption(self):
        """Handle an interruption event."""
        logger.info("Interruption detected - user speaking during agent playback")

        await self.set_state(ConversationState.INTERRUPTED)

        if self.on_interruption:
            try:
                await self._call_interruption_callback()
            except Exception as e:
                logger.error(f"Interruption callback error: {e}")

    async def _call_interruption_callback(self):
        """Call interruption callback with error handling."""
        import inspect
        if inspect.iscoroutinefunction(self.on_interruption):
            await self.on_interruption()
        else:
            self.on_interruption()

    def user_started_speaking(self):
        """Notify that user started speaking."""
        asyncio.create_task(self.set_state(ConversationState.USER_SPEAKING))

    def user_stopped_speaking(self):
        """Notify that user stopped speaking."""
        asyncio.create_task(self.set_state(ConversationState.PROCESSING))

    def processing_complete(self):
        """Notify that processing is complete."""
        asyncio.create_task(self.set_state(ConversationState.IDLE))


class TurnTakingManager:
    """Manages conversation flow with proper turn-taking."""

    def __init__(self):
        self.interruption_handler = InterruptionHandler()
        self.current_speaker: Optional[str] = None
        self.speaking_queue = asyncio.Queue()

        # Stats
        self.interruption_count = 0
        self.total_turns = 0

        # Set up callbacks
        self.interruption_handler.on_interruption = self._on_interruption
        self.interruption_handler.on_state_change = self._on_state_change

    async def _on_interruption(self):
        """Handle interruption callback."""
        self.interruption_count += 1
        logger.info(f"Interruption #{self.interruption_count} detected")

        # Cancel current playback and switch to user
        await self._cancel_current_playback()

    async def _on_state_change(self, old_state: ConversationState, new_state: ConversationState):
        """Handle state changes."""
        if new_state == ConversationState.USER_SPEAKING:
            self.current_speaker = "user"
            self.total_turns += 1
        elif new_state == ConversationState.AGENT_SPEAKING:
            self.current_speaker = "agent"

    async def _cancel_current_playback(self):
        """Cancel current agent playback due to interruption."""
        logger.info("Cancelling agent playback")
        # This would be implemented to stop TTS/audio playback

    async def request_turn(self, speaker: str) -> bool:
        """Request a turn to speak.

        Args:
            speaker: 'user' or 'agent'

        Returns:
            True if turn granted
        """
        if self.current_speaker is None:
            self.current_speaker = speaker
            return True

        # Allow user to interrupt agent
        if speaker == "user" and self.current_speaker == "agent":
            await self.interruption_handler._handle_interruption()
            self.current_speaker = "user"
            return True

        # Queue if agent wants to speak while user is speaking
        if speaker == "agent" and self.current_speaker == "user":
            await self.speaking_queue.put(speaker)
            return False

        return False

    def release_turn(self, speaker: str):
        """Release the current turn."""
        if self.current_speaker == speaker:
            self.current_speaker = None

            # Check queue for next speaker
            if not self.speaking_queue.empty():
                next_speaker = self.speaking_queue.get_nowait()
                self.current_speaker = next_speaker

    def get_stats(self) -> dict:
        """Get conversation statistics."""
        return {
            'total_turns': self.total_turns,
            'interruptions': self.interruption_count,
            'current_speaker': self.current_speaker,
            'state': self.interruption_handler.state.name
        }


def demo():
    """Demonstrate interruption handling."""
    import tempfile
    import soundfile as sf
    import asyncio

    logging.basicConfig(level=logging.INFO)

    async def run_demo():
        print("Interruption Handler Demo")
        print("-" * 40)

        handler = InterruptionHandler()

        # Test state transitions
        print("Testing state transitions...")
        await handler.set_state(ConversationState.AGENT_SPEAKING)
        assert handler.state == ConversationState.AGENT_SPEAKING
        print("  Agent speaking state set")

        # Simulate user interrupting
        print("Simulating interruption...")
        handler._is_playing = True

        # Create fake speech audio
        speech = np.random.randn(16000).astype(np.float32) * 0.5
        speech_bytes = (speech * 32767).astype(np.int16).tobytes()

        result = await handler.process_audio(speech_bytes)
        print(f"  Interruption detected: {result['interrupted']}")

        print("\nInterruption handler ready!")

    asyncio.run(run_demo())


if __name__ == "__main__":
    demo()
