"""Quick test script for voice bridge components."""

import logging
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_transcription():
    """Test transcription module."""
    try:
        from transcription import WhisperTranscriber
        transcriber = WhisperTranscriber(model_size="tiny")
        logger.info("Transcription module initialized (tiny model for testing)")
        return True
    except Exception as e:
        logger.error(f"Transcription test failed: {e}")
        return False


def test_session_manager():
    """Test session manager."""
    try:
        from voice_session import SessionManager
        manager = SessionManager()

        # Create session
        session = manager.get_or_create_session("user1", "room1")
        assert session is not None

        # Add messages
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi there")

        # Get context
        context = session.get_context()
        assert len(context) == 2

        # Get stats
        stats = manager.get_stats()
        assert stats["active_sessions"] == 1

        logger.info("Session manager test passed")
        return True
    except Exception as e:
        logger.error(f"Session manager test failed: {e}")
        return False


def test_tts():
    """Test TTS module (just import, not synthesis)."""
    try:
        from tts_engine import SmartTTS
        tts = SmartTTS()
        logger.info("TTS module initialized")
        return True
    except Exception as e:
        logger.error(f"TTS test failed: {e}")
        return False


def main():
    """Run all tests."""
    tests = [
        ("Transcription", test_transcription),
        ("Session Manager", test_session_manager),
        ("TTS", test_tts),
    ]

    results = []
    for name, test_fn in tests:
        logger.info(f"\nTesting {name}...")
        passed = test_fn()
        results.append((name, passed))

    logger.info("\n" + "=" * 40)
    logger.info("Test Results:")
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        logger.info(f"  {name}: {status}")

    all_passed = all(p for _, p in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
