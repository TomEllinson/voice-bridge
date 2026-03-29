"""Matrix voice message handler for OpenClaw.

Receives voice messages from Matrix/Element, transcribes with Whisper,
processes through OpenClaw, and responds with audio via TTS.
"""

import os
import sys
import asyncio
import tempfile
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
import io

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import local modules
from transcription import WhisperTranscriber, TranscriptionError
from tts_engine import SmartTTS, TTSError
from voice_session import SessionManager, VoiceSession


@dataclass
class VoiceBridgeConfig:
    """Configuration for the voice bridge."""
    # Matrix config
    homeserver_url: str = "https://matrix.org"
    access_token: str = ""
    user_id: str = ""
    device_id: str = "voice_bridge"

    # Audio config
    max_audio_duration: int = 300  # 5 minutes max
    supported_formats: tuple = ('audio/ogg', 'audio/mpeg', 'audio/wav', 'audio/mp4')

    # Transcription config
    whisper_model: str = "base"  # tiny, base, small, medium, large
    whisper_device: str = "auto"

    # TTS config
    tts_engine: str = "kokoro"  # kokoro, piper, pyttsx3
    tts_voice: Optional[str] = None

    # Session config
    session_timeout: int = 3600  # 1 hour

    # OpenClaw integration
    openclaw_url: str = "http://localhost:8000"
    openclaw_api_key: str = ""


class MatrixVoiceBridge:
    """Main voice bridge handler for Matrix voice messages."""

    def __init__(self, config: VoiceBridgeConfig):
        """Initialize the voice bridge.

        Args:
            config: Voice bridge configuration
        """
        self.config = config
        self.transcriber = WhisperTranscriber(
            model_size=config.whisper_model,
            device=config.whisper_device
        )
        self.tts = SmartTTS(preferred_engine=config.tts_engine)
        self.sessions = SessionManager(session_timeout=config.session_timeout)
        self.client = None
        self._shutdown = False

    async def initialize(self):
        """Initialize the Matrix client."""
        try:
            from matrix_client_async import AsyncClient

            self.client = AsyncClient(
                homeserver=self.config.homeserver_url,
                user_id=self.config.user_id,
                device_id=self.config.device_id
            )
            self.client.access_token = self.config.access_token

            # Sync to get current state
            await self.client.sync()
            logger.info(f"Matrix client initialized for {self.config.user_id}")

        except ImportError:
            logger.error("matrix-nio not installed. Install with: pip install matrix-nio")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Matrix client: {e}")
            raise

    async def run(self):
        """Main run loop."""
        await self.initialize()

        logger.info("Voice bridge running. Listening for voice messages...")

        while not self._shutdown:
            try:
                # Poll for new messages
                sync_response = await self.client.sync(timeout_ms=30000)

                # Process rooms
                for room_id, room_info in sync_response.rooms.join.items():
                    await self._process_room_messages(room_id, room_info)

                # Cleanup expired sessions
                self.sessions.cleanup_expired()

            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)

    async def _process_room_messages(self, room_id: str, room_info: Any):
        """Process messages from a room."""
        if not hasattr(room_info, 'timeline'):
            return

        for event in room_info.timeline:
            if event.get('type') != 'm.room.message':
                continue

            content = event.get('content', {})
            msg_type = content.get('msgtype', '')

            # Check if it's a voice/audio message
            if msg_type in ('m.audio', 'm.voice'):
                await self._handle_voice_message(
                    room_id=room_id,
                    event=event,
                    sender=event.get('sender', '')
                )

    async def _handle_voice_message(
        self,
        room_id: str,
        event: Dict[str, Any],
        sender: str
    ):
        """Handle an incoming voice message.

        Args:
            room_id: Matrix room ID
            event: Message event
            sender: Message sender
        """
        content = event.get('content', {})
        body = content.get('body', '')
        info = content.get('info', {})
        url = content.get('url', '')

        logger.info(f"Received voice message from {sender} in {room_id}")
        logger.debug(f"Audio info: {info}")

        try:
            # Get or create session
            session = self.sessions.get_or_create_session(
                user_id=sender,
                room_id=room_id
            )

            # Download audio
            audio_data = await self._download_audio(url)
            if not audio_data:
                logger.error("Failed to download audio")
                return

            # Validate audio size
            duration = info.get('duration', 0)
            if duration > self.config.max_audio_duration * 1000:
                logger.warning(f"Audio too long: {duration}ms")
                await self._send_text_response(
                    room_id,
                    "Audio message too long. Please keep it under 5 minutes."
                )
                return

            # Transcribe
            logger.info("Transcribing audio...")
            result = self.transcriber.transcribe_bytes(audio_data)
            transcription = result['text']

            if not transcription.strip():
                logger.warning("No speech detected in audio")
                await self._send_text_response(
                    room_id,
                    "I couldn't understand the audio. Could you try again?"
                )
                return

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
            response_text = await self._process_with_openclaw(session, transcription)

            if not response_text:
                response_text = "I'm sorry, I couldn't process that request."

            # Generate audio response
            logger.info("Generating audio response...")
            audio_response = await self._generate_audio_response(response_text)

            if audio_response:
                # Send audio response
                await self._send_audio_response(room_id, audio_response, response_text)

                # Also send transcription for accessibility
                await self._send_text_response(
                    room_id,
                    f"You said: \"{transcription}\"\n\nI said: \"{response_text}\"",
                    reply_to=event.get('event_id')
                )
            else:
                # Fallback to text only
                await self._send_text_response(
                    room_id,
                    response_text,
                    reply_to=event.get('event_id')
                )

            # Add assistant response to session
            session.add_message(role='assistant', text=response_text)

        except TranscriptionError as e:
            logger.error(f"Transcription error: {e}")
            await self._send_text_response(
                room_id,
                "Sorry, I had trouble transcribing your audio. Please try again."
            )
        except Exception as e:
            logger.error(f"Error handling voice message: {e}", exc_info=True)
            await self._send_text_response(
                room_id,
                "Sorry, something went wrong processing your voice message."
            )

    async def _download_audio(self, mxc_url: str) -> Optional[bytes]:
        """Download audio from Matrix content repository.

        Args:
            mxc_url: MXC URL (mxc://server/media_id)

        Returns:
            Audio bytes or None if failed
        """
        try:
            if not mxc_url.startswith('mxc://'):
                logger.error(f"Invalid MXC URL: {mxc_url}")
                return None

            # Parse MXC URL
            _, server_name, media_id = mxc_url.split('/')

            # Build download URL
            download_url = f"{self.config.homeserver_url}/_matrix/media/r0/download/{server_name}/{media_id}"

            # Download
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(download_url) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    else:
                        logger.error(f"Download failed: {resp.status}")
                        return None

        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
            return None

    async def _process_with_openclaw(
        self,
        session: VoiceSession,
        transcription: str
    ) -> str:
        """Process transcription through OpenClaw.

        Args:
            session: Current voice session
            transcription: Transcribed user text

        Returns:
            Response text from OpenClaw
        """
        try:
            import aiohttp

            # Build context from session
            context = session.get_context(max_messages=5)

            # Prepare request
            headers = {}
            if self.config.openclaw_api_key:
                headers['Authorization'] = f"Bearer {self.config.openclaw_api_key}"

            payload = {
                'message': transcription,
                'context': context,
                'session_id': session.session_id,
                'user_id': session.user_id,
                'source': 'voice'
            }

            async with aiohttp.ClientSession() as http:
                async with http.post(
                    f"{self.config.openclaw_url}/api/chat",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('response', '')
                    else:
                        logger.error(f"OpenClaw error: {resp.status}")
                        return "I'm having trouble connecting to my brain right now."

        except Exception as e:
            logger.error(f"Error calling OpenClaw: {e}")
            return "I'm having trouble processing that right now."

    async def _generate_audio_response(self, text: str) -> Optional[bytes]:
        """Generate audio from text using TTS.

        Args:
            text: Text to synthesize

        Returns:
            Audio bytes or None if failed
        """
        try:
            # Run TTS in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            audio_data = await loop.run_in_executor(
                None,
                lambda: self.tts.synthesize(text, self.config.tts_voice)
            )
            return audio_data
        except TTSError as e:
            logger.error(f"TTS error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected TTS error: {e}")
            return None

    async def _send_text_response(
        self,
        room_id: str,
        text: str,
        reply_to: Optional[str] = None
    ):
        """Send a text response to the room.

        Args:
            room_id: Room to send to
            text: Text message
            reply_to: Event ID to reply to
        """
        try:
            content = {
                'msgtype': 'm.text',
                'body': text
            }

            if reply_to:
                content['m.relates_to'] = {
                    'm.in_reply_to': {'event_id': reply_to}
                }

            await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=content
            )
            logger.debug(f"Sent text response to {room_id}")

        except Exception as e:
            logger.error(f"Failed to send text response: {e}")

    async def _send_audio_response(
        self,
        room_id: str,
        audio_data: bytes,
        transcript: str
    ):
        """Send an audio response to the room.

        Args:
            room_id: Room to send to
            audio_data: Audio bytes
            transcript: Text transcript for accessibility
        """
        try:
            # Upload audio to Matrix content repository
            from matrix_client_async import UploadResponse

            upload_response = await self.client.upload(
                data=io.BytesIO(audio_data),
                content_type="audio/wav"
            )

            if isinstance(upload_response, UploadResponse):
                mxc_url = upload_response.content_uri
            else:
                mxc_url = upload_response

            # Send audio message
            content = {
                'msgtype': 'm.audio',
                'body': transcript,
                'url': mxc_url,
                'info': {
                    'mimetype': 'audio/wav',
                    'size': len(audio_data)
                }
            }

            await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=content
            )
            logger.info(f"Sent audio response to {room_id}")

        except Exception as e:
            logger.error(f"Failed to send audio response: {e}")

    async def shutdown(self):
        """Shutdown the bridge gracefully."""
        self._shutdown = True
        if self.client:
            await self.client.close()
        logger.info("Voice bridge shut down")


# CLI entry point
def main():
    """Run the voice bridge from command line."""
    import argparse

    parser = argparse.ArgumentParser(description='Matrix Voice Bridge for OpenClaw')
    parser.add_argument('--homeserver', default=os.getenv('MATRIX_HOMESERVER', 'https://matrix.org'))
    parser.add_argument('--token', default=os.getenv('MATRIX_ACCESS_TOKEN', ''))
    parser.add_argument('--user-id', default=os.getenv('MATRIX_USER_ID', ''))
    parser.add_argument('--whisper-model', default='base', choices=['tiny', 'base', 'small', 'medium', 'large'])
    parser.add_argument('--tts-engine', default='kokoro', choices=['kokoro', 'piper', 'pyttsx3'])
    parser.add_argument('--openclaw-url', default=os.getenv('OPENCLAW_URL', 'http://localhost:8000'))
    parser.add_argument('--verbose', '-v', action='store_true')

    args = parser.parse_args()

    if not args.token or not args.user_id:
        print("Error: Matrix access token and user ID required")
        print("Set MATRIX_ACCESS_TOKEN and MATRIX_USER_ID environment variables")
        sys.exit(1)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config = VoiceBridgeConfig(
        homeserver_url=args.homeserver,
        access_token=args.token,
        user_id=args.user_id,
        whisper_model=args.whisper_model,
        tts_engine=args.tts_engine,
        openclaw_url=args.openclaw_url
    )

    bridge = MatrixVoiceBridge(config)

    try:
        asyncio.run(bridge.run())
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        asyncio.run(bridge.shutdown())


if __name__ == '__main__':
    main()
