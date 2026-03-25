"""OpenClaw Matrix Provider Integration Adapter.

This module provides a clean interface for integrating the Voice Bridge
with OpenClaw's existing Matrix provider. It can be imported and used
as a plugin/extension.

Usage in OpenClaw:
    from voice_bridge.openclaw_integration import VoiceBridgePlugin

    # In your Matrix provider:
    plugin = VoiceBridgePlugin(openclaw_client=client, config={...})
    await plugin.initialize()

    # Handle voice messages through the plugin
    if event.is_voice_message():
        response = await plugin.handle_voice_message(event, room)
"""

import asyncio
import logging
from typing import Optional, Dict, Any, Callable
from pathlib import Path

from transcription import WhisperTranscriber, TranscriptionError
from tts_engine import SmartTTS, TTSError
from voice_session import SessionManager, VoiceSession

logger = logging.getLogger(__name__)


class VoiceBridgePlugin:
    """Plugin adapter for integrating Voice Bridge with OpenClaw Matrix provider.

    This class provides a clean interface that can be used by OpenClaw's
    existing Matrix provider to add voice message handling capabilities.
    """

    def __init__(
        self,
        openclaw_client: Any,
        config: Optional[Dict[str, Any]] = None
    ):
        """Initialize the voice bridge plugin.

        Args:
            openclaw_client: OpenClaw client instance for processing messages
            config: Configuration dictionary with keys:
                - whisper_model: Model size (tiny, base, small, medium, large)
                - whisper_device: Device (cpu, cuda, auto)
                - tts_engine: Preferred TTS engine (kokoro, piper, pyttsx3)
                - tts_voice: Voice ID to use
                - session_timeout: Session timeout in seconds
                - max_audio_duration: Max audio duration in seconds
        """
        self.openclaw = openclaw_client
        self.config = config or {}

        # Initialize components
        self.transcriber = WhisperTranscriber(
            model_size=self.config.get('whisper_model', 'base'),
            device=self.config.get('whisper_device', 'auto')
        )

        self.tts = SmartTTS(
            preferred_engine=self.config.get('tts_engine', 'kokoro')
        )

        self.sessions = SessionManager(
            session_timeout=self.config.get('session_timeout', 3600)
        )

        self.max_duration = self.config.get('max_audio_duration', 300)

        # Stats tracking
        self.stats = {
            'voice_messages_received': 0,
            'voice_messages_processed': 0,
            'transcription_errors': 0,
            'tts_errors': 0,
            'total_latency_ms': 0
        }

    async def initialize(self):
        """Initialize the plugin. Called before first use."""
        logger.info("Voice Bridge Plugin initialized")
        logger.info(f"  Whisper model: {self.config.get('whisper_model', 'base')}")
        logger.info(f"  TTS engine: {self.config.get('tts_engine', 'kokoro')}")

    async def handle_voice_message(
        self,
        event: Any,
        room: Any,
        download_func: Callable[[str], bytes]
    ) -> Dict[str, Any]:
        """Handle an incoming voice message.

        Args:
            event: Matrix message event
            room: Matrix room object
            download_func: Async function to download audio bytes from MXC URL

        Returns:
            Dict with keys:
                - success: bool
                - transcription: str (if success)
                - response_text: str (if success)
                - audio_data: bytes (if success and TTS succeeded)
                - error: str (if not success)
                - latency_ms: int
        """
        import time
        start_time = time.time()

        self.stats['voice_messages_received'] += 1

        # Extract event data
        sender = getattr(event, 'sender', 'unknown')
        room_id = getattr(room, 'room_id', 'unknown')
        content = getattr(event, 'content', {})

        try:
            # Get audio URL
            url = content.get('url', '')
            if not url:
                return {'success': False, 'error': 'No audio URL in message'}

            info = content.get('info', {})
            duration = info.get('duration', 0)

            # Check duration
            if duration > self.max_duration * 1000:
                return {
                    'success': False,
                    'error': f'Audio too long ({duration}ms > {self.max_duration * 1000}ms)'
                }

            # Get or create session
            session = self.sessions.get_or_create_session(sender, room_id)

            # Download audio
            logger.info(f"Downloading audio from {url}")
            audio_data = await download_func(url)
            if not audio_data:
                return {'success': False, 'error': 'Failed to download audio'}

            # Transcribe
            logger.info("Transcribing audio...")
            result = self.transcriber.transcribe_bytes(audio_data)
            transcription = result['text'].strip()

            if not transcription:
                return {'success': False, 'error': 'No speech detected'}

            logger.info(f"Transcription: {transcription}")

            # Add to session
            session.add_message(
                role='user',
                text=transcription,
                audio_data=audio_data,
                duration=duration / 1000 if duration else None,
                language=result.get('language')
            )

            # Process through OpenClaw
            logger.info("Processing with OpenClaw...")
            response_text = await self._call_openclaw(session, transcription)

            if not response_text:
                response_text = "I'm sorry, I couldn't process that request."

            # Generate audio response
            logger.info("Generating audio response...")
            audio_response = await self._generate_audio(response_text)

            # Add assistant response to session
            session.add_message(role='assistant', text=response_text)

            latency_ms = int((time.time() - start_time) * 1000)
            self.stats['voice_messages_processed'] += 1
            self.stats['total_latency_ms'] += latency_ms

            return {
                'success': True,
                'transcription': transcription,
                'response_text': response_text,
                'audio_data': audio_response,
                'latency_ms': latency_ms
            }

        except TranscriptionError as e:
            self.stats['transcription_errors'] += 1
            logger.error(f"Transcription error: {e}")
            return {'success': False, 'error': f'Transcription failed: {e}'}

        except Exception as e:
            logger.error(f"Error handling voice message: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    async def _call_openclaw(self, session: VoiceSession, message: str) -> str:
        """Call OpenClaw to process the transcribed message.

        Args:
            session: Current voice session
            message: Transcribed user message

        Returns:
            Response text from OpenClaw
        """
        try:
            # Get conversation context
            context = session.get_context(max_messages=5)

            # Call OpenClaw client
            if hasattr(self.openclaw, 'process_message'):
                # Direct method call
                return await self.openclaw.process_message(
                    message=message,
                    context=context,
                    session_id=session.session_id,
                    user_id=session.user_id,
                    source='voice'
                )
            elif hasattr(self.openclaw, 'chat'):
                # Alternative interface
                return await self.openclaw.chat(
                    message,
                    context=context,
                    session_id=session.session_id
                )
            else:
                logger.warning("OpenClaw client has no recognized method")
                return "I'm having trouble connecting to my brain right now."

        except Exception as e:
            logger.error(f"Error calling OpenClaw: {e}")
            return "I'm having trouble processing that right now."

    async def _generate_audio(self, text: str) -> Optional[bytes]:
        """Generate audio from text using TTS.

        Args:
            text: Text to synthesize

        Returns:
            Audio bytes or None if failed
        """
        try:
            loop = asyncio.get_event_loop()
            audio_data = await loop.run_in_executor(
                None,
                lambda: self.tts.synthesize(text, self.config.get('tts_voice'))
            )
            return audio_data
        except TTSError as e:
            self.stats['tts_errors'] += 1
            logger.error(f"TTS error: {e}")
            return None
        except Exception as e:
            self.stats['tts_errors'] += 1
            logger.error(f"Unexpected TTS error: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get plugin statistics."""
        processed = self.stats['voice_messages_processed']
        total_latency = self.stats['total_latency_ms']
        avg_latency = total_latency / processed if processed > 0 else 0

        return {
            **self.stats,
            'average_latency_ms': int(avg_latency),
            'active_sessions': len(self.sessions.sessions)
        }

    def cleanup_expired_sessions(self):
        """Clean up expired voice sessions."""
        self.sessions.cleanup_expired()

    async def shutdown(self):
        """Shutdown the plugin gracefully."""
        logger.info("Voice Bridge Plugin shutting down")
        logger.info(f"Final stats: {self.get_stats()}")


# Convenience function for simple integration
def create_voice_bridge(
    openclaw_client: Any,
    whisper_model: str = 'base',
    tts_engine: str = 'kokoro'
) -> VoiceBridgePlugin:
    """Create a voice bridge plugin with default configuration.

    Args:
        openclaw_client: OpenClaw client instance
        whisper_model: Whisper model size
        tts_engine: TTS engine preference

    Returns:
        Configured VoiceBridgePlugin instance
    """
    config = {
        'whisper_model': whisper_model,
        'tts_engine': tts_engine
    }
    return VoiceBridgePlugin(openclaw_client, config)
