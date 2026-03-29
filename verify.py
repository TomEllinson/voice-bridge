"""Quick verification that all modules import correctly."""

import sys


def test_imports():
    """Test that all modules can be imported."""
    errors = []

    try:
        from transcription import WhisperTranscriber, TranscriptionError
        print("OK: transcription module")
    except Exception as e:
        errors.append(f"transcription: {e}")
        print(f"FAIL: transcription module: {e}")

    try:
        from tts_engine import SmartTTS, TTSError, speak
        print("OK: tts_engine module")
    except Exception as e:
        errors.append(f"tts_engine: {e}")
        print(f"FAIL: tts_engine module: {e}")

    try:
        from voice_session import VoiceSession, SessionManager
        print("OK: voice_session module")
    except Exception as e:
        errors.append(f"voice_session: {e}")
        print(f"FAIL: voice_session module: {e}")

    try:
        from matrix_voice_bridge import MatrixVoiceBridge, VoiceBridgeConfig
        print("OK: matrix_voice_bridge module")
    except Exception as e:
        errors.append(f"matrix_voice_bridge: {e}")
        print(f"FAIL: matrix_voice_bridge module: {e}")

    if errors:
        print(f"\n{len(errors)} import errors found")
        return 1
    else:
        print("\nAll modules imported successfully!")
        return 0


if __name__ == "__main__":
    sys.exit(test_imports())
