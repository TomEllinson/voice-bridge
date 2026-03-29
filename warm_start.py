#!/usr/bin/env python3
"""
Warm start script to pre-load models and reduce latency.
Run this once to keep models in memory for faster subsequent requests.
"""
import os
import sys
import time
from pathlib import Path

# Ensure modules are in path
sys.path.insert(0, str(Path(__file__).parent))

def warm_models():
    """Pre-load all models to reduce latency."""
    print("Warming up Voice Bridge models...")
    start = time.time()

    # Warm up transcription model
    print("  Loading Whisper (tiny) for transcription...")
    from transcription import WhisperTranscriber
    transcriber = WhisperTranscriber(model_size="tiny")
    print(f"  ✓ Transcription ready")

    # Warm up TTS model
    print("  Loading Kokoro TTS...")
    from tts_engine import TTSEngine
    tts = TTSEngine(engine="kokoro")
    print(f"  ✓ TTS ready")

    elapsed = time.time() - start
    print(f"\nAll models warmed up in {elapsed:.2f}s")
    print("Keep this running for fast voice processing, or use as a service.")

    return transcriber, tts

if __name__ == "__main__":
    try:
        transcriber, tts = warm_models()

        # Keep script running to maintain model cache
        print("\nPress Ctrl+C to exit (models will be unloaded)")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down, models unloaded.")
        sys.exit(0)
    except Exception as e:
        print(f"\nError during warm-up: {e}")
        sys.exit(1)
