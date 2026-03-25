"""Demo script for testing transcription and TTS without Matrix connection.

This script allows you to:
1. Record or load an audio file and transcribe it
2. Test TTS synthesis with different engines
3. Verify the complete voice pipeline works

Usage:
    python demo.py transcribe <audio_file> [--model tiny]
    python demo.py tts "Hello, this is a test" [--engine kokoro]
    python demo.py pipeline <audio_file>  # Full voice-in/voice-out demo
"""

import argparse
import asyncio
import logging
import sys
import tempfile
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)


def demo_transcribe(audio_path: str, model_size: str = "base"):
    """Demo transcription on an audio file."""
    from transcription import WhisperTranscriber

    logger.info(f"Loading Whisper model: {model_size}")
    transcriber = WhisperTranscriber(model_size=model_size)

    logger.info(f"Transcribing: {audio_path}")
    start_time = time.time()

    try:
        result = transcriber.transcribe(audio_path)

        elapsed = time.time() - start_time
        logger.info(f"Transcription completed in {elapsed:.2f}s")
        logger.info(f"Detected language: {result.get('language', 'unknown')}")
        logger.info(f"Text: {result['text']}")

        if result.get('segments'):
            logger.info("\nSegments:")
            for seg in result['segments'][:5]:
                logger.info(f"  [{seg['start']:.2f}s - {seg['end']:.2f}s]: {seg['text']}")

        return result['text']

    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return None


def demo_tts(text: str, engine: str = "kokoro", output_file: str = None):
    """Demo TTS synthesis."""
    from tts_engine import SmartTTS

    logger.info(f"Initializing TTS engine: {engine}")
    tts = SmartTTS(preferred_engine=engine)

    logger.info(f"Synthesizing: '{text}'")
    start_time = time.time()

    try:
        audio_data = tts.synthesize(text)

        elapsed = time.time() - start_time
        logger.info(f"Synthesis completed in {elapsed:.2f}s")
        logger.info(f"Audio size: {len(audio_data)} bytes")

        # Save to file
        if output_file:
            output_path = Path(output_file)
        else:
            output_path = Path(tempfile.gettempdir()) / f"tts_demo_{engine}.wav"

        output_path.write_bytes(audio_data)
        logger.info(f"Saved to: {output_path}")

        return audio_data

    except Exception as e:
        logger.error(f"TTS failed: {e}")
        return None


def demo_pipeline(audio_path: str, model_size: str = "base", tts_engine: str = "kokoro"):
    """Demo the full voice-in/voice-out pipeline."""
    from transcription import WhisperTranscriber
    from tts_engine import SmartTTS
    from voice_session import SessionManager

    logger.info("=" * 50)
    logger.info("Voice Pipeline Demo")
    logger.info("=" * 50)

    total_start = time.time()

    # Step 1: Transcribe
    logger.info("\n[1/3] Transcribing audio...")
    transcriber = WhisperTranscriber(model_size=model_size)

    try:
        result = transcriber.transcribe(audio_path)
        transcription = result['text']
        logger.info(f"Transcription: {transcription}")
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return

    # Step 2: Simulate OpenClaw processing
    logger.info("\n[2/3] Processing with OpenClaw...")
    session_manager = SessionManager()
    session = session_manager.get_or_create_session("demo_user", "demo_room")
    session.add_message("user", transcription)

    # Simulate response (replace with actual OpenClaw call)
    response_text = f"You said: {transcription}. This is a simulated response."
    logger.info(f"Response: {response_text}")

    # Step 3: Generate audio response
    logger.info("\n[3/3] Generating audio response...")
    tts = SmartTTS(preferred_engine=tts_engine)

    try:
        audio_data = tts.synthesize(response_text)
        logger.info(f"Generated {len(audio_data)} bytes of audio")

        # Save response
        output_path = Path(tempfile.gettempdir()) / "voice_response.wav"
        output_path.write_bytes(audio_data)
        logger.info(f"Saved response to: {output_path}")

    except Exception as e:
        logger.error(f"TTS failed: {e}")

    total_elapsed = time.time() - total_start
    logger.info(f"\nTotal pipeline time: {total_elapsed:.2f}s")
    logger.info("=" * 50)


def demo_session():
    """Demo session management."""
    from voice_session import SessionManager

    logger.info("Session Management Demo")

    manager = SessionManager(session_timeout=60)

    # Create session
    session = manager.get_or_create_session("user1", "room1")
    logger.info(f"Created session: {session.session_id}")

    # Add messages
    session.add_message("user", "Hello", duration=2.5)
    session.add_message("assistant", "Hi there!")
    session.add_message("user", "How are you?", duration=1.5)

    # Get context
    context = session.get_context()
    logger.info(f"Context has {len(context)} messages")
    for msg in context:
        logger.info(f"  {msg['role']}: {msg['content']}")

    # Get stats
    stats = manager.get_stats()
    logger.info(f"Active sessions: {stats['active_sessions']}")


async def demo_matrix_client():
    """Demo Matrix client connection (requires credentials)."""
    from matrix_voice_bridge import MatrixVoiceBridge, VoiceBridgeConfig

    logger.info("Matrix Client Demo (requires valid credentials)")

    config = VoiceBridgeConfig()

    if not config.access_token:
        logger.error("No MATRIX_ACCESS_TOKEN set. Set it in your environment.")
        return

    bridge = MatrixVoiceBridge(config)

    try:
        await bridge.initialize()
        logger.info("Matrix client initialized successfully!")
        await bridge.shutdown()
    except Exception as e:
        logger.error(f"Matrix client failed: {e}")


def main():
    parser = argparse.ArgumentParser(description='Voice Bridge Demo')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Transcribe command
    transcribe_cmd = subparsers.add_parser('transcribe', help='Transcribe an audio file')
    transcribe_cmd.add_argument('audio_file', help='Path to audio file')
    transcribe_cmd.add_argument('--model', default='base', choices=['tiny', 'base', 'small', 'medium', 'large'])

    # TTS command
    tts_cmd = subparsers.add_parser('tts', help='Synthesize text to speech')
    tts_cmd.add_argument('text', help='Text to synthesize')
    tts_cmd.add_argument('--engine', default='kokoro', choices=['kokoro', 'piper', 'pyttsx3'])
    tts_cmd.add_argument('--output', '-o', help='Output file path')

    # Pipeline command
    pipeline_cmd = subparsers.add_parser('pipeline', help='Run full voice pipeline')
    pipeline_cmd.add_argument('audio_file', help='Path to audio file')
    pipeline_cmd.add_argument('--model', default='base')
    pipeline_cmd.add_argument('--tts-engine', default='kokoro')

    # Session command
    session_cmd = subparsers.add_parser('session', help='Demo session management')

    # Matrix command
    matrix_cmd = subparsers.add_parser('matrix', help='Test Matrix connection')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == 'transcribe':
        demo_transcribe(args.audio_file, args.model)
    elif args.command == 'tts':
        demo_tts(args.text, args.engine, args.output)
    elif args.command == 'pipeline':
        demo_pipeline(args.audio_file, args.model, args.tts_engine)
    elif args.command == 'session':
        demo_session()
    elif args.command == 'matrix':
        asyncio.run(demo_matrix_client())


if __name__ == '__main__':
    main()
