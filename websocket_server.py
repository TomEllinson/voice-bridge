"""WebSocket server for real-time audio streaming from Android app."""

import asyncio
import json
import logging
import wave
import io
from typing import Dict, Set, Optional
from dataclasses import dataclass
from datetime import datetime

import websockets
from websockets.server import WebSocketServerProtocol

from transcription import WhisperTranscriber
from tts_engine import SmartTTS
from voice_session import SessionManager

logger = logging.getLogger(__name__)


@dataclass
class AudioChunk:
    """Represents a chunk of audio data from the client."""
    data: bytes
    timestamp: float
    is_speech: bool = True


class AudioStreamBuffer:
    """Buffers audio chunks for a session until ready to process."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunks: list[AudioChunk] = []
        self.silence_threshold = 0.5  # seconds of silence to trigger processing

    def add_chunk(self, chunk: AudioChunk):
        """Add an audio chunk to the buffer."""
        self.chunks.append(chunk)

    def get_audio_for_processing(self) -> Optional[bytes]:
        """Get accumulated audio data ready for transcription."""
        if not self.chunks:
            return None

        # Concatenate all chunks
        audio_data = b''.join(chunk.data for chunk in self.chunks if chunk.is_speech)
        self.chunks = []
        return audio_data if audio_data else None

    def clear(self):
        """Clear the buffer."""
        self.chunks.clear()


class VoiceBridgeWebSocket:
    """WebSocket server for real-time voice streaming."""

    def __init__(
        self,
        host: str = None,  # Auto-detect Tailscale IP
        port: int = 8765,
        whisper_model: str = "tiny",
        tts_engine: str = "kokoro"
    ):
        # Auto-detect Tailscale IP if not provided
        if host is None:
            host = self._get_tailscale_ip() or "127.0.0.1"

        self.host = host
        self.port = port
        self.clients: Set[WebSocketServerProtocol] = set()
        self.sessions: Dict[str, AudioStreamBuffer] = {}
        self.session_manager = SessionManager()

        # Initialize models - MOVED OUT of _get_tailscale_ip method
        logger.info(f"Loading Whisper model: {whisper_model}")
        self.transcriber = WhisperTranscriber(
            model_size=whisper_model,
            device="cpu",
            compute_type="int8"
        )

        logger.info(f"Loading TTS engine: {tts_engine}")
        self.tts = SmartTTS(preferred_engine=tts_engine)

        # Pre-warm models
        self._warm_models()

    def _get_tailscale_ip(self) -> Optional[str]:
        """Auto-detect Tailscale IP address (100.x.x.x range)."""
        import socket
        try:
            # Try to find Tailscale interface
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Connect to a public address to get local IP
            sock.connect(("8.8.8.8", 80))
            local_ip = sock.getsockname()[0]
            sock.close()

            # Check if it's in Tailscale range
            if local_ip.startswith("100."):
                return local_ip

            # Try to get IP from tailscale0 interface specifically
            import subprocess
            result = subprocess.run(
                ["ip", "addr", "show", "tailscale0"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                import re
                match = re.search(r'inet (100\.\d+\.\d+\.\d+)', result.stdout)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return None

    def _warm_models(self):
        """Pre-load models to reduce latency."""
        logger.info("Warming up models...")
        try:
            # Warm up with dummy data
            import tempfile
            import numpy as np
            import soundfile as sf

            # Create a short test audio
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                signal = np.random.randn(1600).astype(np.float32) * 0.1
                sf.write(f.name, signal, 16000)
                self.transcriber.transcribe(f.name)

            # Warm up TTS
            self.tts.synthesize("Warm up")
            logger.info("Models warmed up")
        except Exception as e:
            logger.warning(f"Model warm-up failed: {e}")

    async def handle_client(self, websocket):
        """Handle a new WebSocket client connection."""
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        logger.info(f"Client connected: {client_id}")

        self.clients.add(websocket)
        self.sessions[client_id] = AudioStreamBuffer()

        try:
            async for message in websocket:
                await self._process_message(websocket, client_id, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client disconnected: {client_id}")
        finally:
            self.clients.discard(websocket)
            if client_id in self.sessions:
                del self.sessions[client_id]

    async def _process_message(
        self,
        websocket: WebSocketServerProtocol,
        client_id: str,
        message: bytes
    ):
        """Process incoming WebSocket message."""
        try:
            # Parse JSON control messages
            if isinstance(message, str) or message.startswith(b'{'):
                data = json.loads(message.decode() if isinstance(message, bytes) else message)
                await self._handle_control_message(websocket, client_id, data)
                return

            # Handle binary audio data
            await self._handle_audio_data(websocket, client_id, message)

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await self._send_error(websocket, str(e))

    async def _handle_control_message(
        self,
        websocket: WebSocketServerProtocol,
        client_id: str,
        data: dict
    ):
        """Handle control messages (start/stop/listening mode)."""
        msg_type = data.get('type')

        if msg_type == 'start_listening':
            self.sessions[client_id].clear()
            await self._send_status(websocket, 'listening_started')

        elif msg_type == 'stop_listening':
            # Process accumulated audio
            await self._process_accumulated_audio(websocket, client_id)

        elif msg_type == 'interrupt':
            # Handle interruption
            await self._handle_interruption(websocket, client_id)

        elif msg_type == 'ping':
            await websocket.send(json.dumps({'type': 'pong'}))

    async def _handle_audio_data(
        self,
        websocket: WebSocketServerProtocol,
        client_id: str,
        audio_data: bytes
    ):
        """Handle incoming audio data chunk."""
        buffer = self.sessions.get(client_id)
        if not buffer:
            return

        # Add chunk to buffer
        chunk = AudioChunk(
            data=audio_data,
            timestamp=datetime.now().timestamp()
        )
        buffer.add_chunk(chunk)

    async def _process_accumulated_audio(
        self,
        websocket: WebSocketServerProtocol,
        client_id: str
    ):
        """Process accumulated audio and send response."""
        import tempfile
        import soundfile as sf

        buffer = self.sessions.get(client_id)
        if not buffer:
            return

        # Get accumulated audio
        audio_bytes = buffer.get_audio_for_processing()
        if not audio_bytes:
            await self._send_status(websocket, 'no_audio')
            return

        try:
            # Convert to audio file for transcription
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                # Assume 16-bit PCM at 16kHz from client
                import numpy as np
                audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                sf.write(f.name, audio_array, 16000)

                # Transcribe
                result = self.transcriber.transcribe(f.name)
                transcription = result['text']

                await self._send_transcription(websocket, transcription)

                # Generate response (would connect to OpenClaw here)
                response_text = f"You said: {transcription}"

                # Synthesize response
                audio_response = self.tts.synthesize(response_text)

                # Send audio response
                await self._send_audio_response(websocket, audio_response, response_text)

        except Exception as e:
            logger.error(f"Processing failed: {e}")
            await self._send_error(websocket, f"Processing failed: {e}")

    async def _handle_interruption(
        self,
        websocket: WebSocketServerProtocol,
        client_id: str
    ):
        """Handle user interruption (barge-in)."""
        logger.info(f"Interruption from {client_id}")
        await self._send_status(websocket, 'interrupted')
        # Clear buffer and prepare for new input
        if client_id in self.sessions:
            self.sessions[client_id].clear()

    async def _send_status(self, websocket: WebSocketServerProtocol, status: str):
        """Send status message to client."""
        await websocket.send(json.dumps({
            'type': 'status',
            'status': status
        }))

    async def _send_transcription(self, websocket: WebSocketServerProtocol, text: str):
        """Send transcription result to client."""
        await websocket.send(json.dumps({
            'type': 'transcription',
            'text': text
        }))

    async def _send_audio_response(
        self,
        websocket: WebSocketServerProtocol,
        audio_data: bytes,
        text: str
    ):
        """Send audio response to client."""
        # Send metadata first
        await websocket.send(json.dumps({
            'type': 'response_start',
            'text': text,
            'audio_size': len(audio_data)
        }))

        # Send audio data in chunks
        chunk_size = 8192
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i+chunk_size]
            await websocket.send(chunk)

        # Send end marker
        await websocket.send(json.dumps({
            'type': 'response_end'
        }))

    async def _send_error(self, websocket: WebSocketServerProtocol, error: str):
        """Send error message to client."""
        await websocket.send(json.dumps({
            'type': 'error',
            'error': error
        }))

    async def start(self):
        """Start the WebSocket server."""
        logger.info(f"Starting WebSocket server on {self.host}:{self.port}")

        # Security: Only bind to Tailscale IP
        async with websockets.serve(
            self.handle_client,
            self.host,
            self.port,
            ping_interval=20,
            ping_timeout=10
        ):
            logger.info("WebSocket server started")
            await asyncio.Future()  # Run forever


def main():
    """Run the WebSocket server."""
    logging.basicConfig(level=logging.INFO)

    # Import numpy for warm-up
    try:
        import numpy
    except ImportError:
        logger.error("numpy required. Install with: pip install numpy")
        return

    server = VoiceBridgeWebSocket()
    asyncio.run(server.start())


if __name__ == '__main__':
    main()
