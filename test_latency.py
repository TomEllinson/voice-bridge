#!/usr/bin/env python3
"""Latency test for voice pipeline with pre-loaded models."""

import time
from pathlib import Path
from transcription import WhisperTranscriber
from tts_engine import SmartTTS

def test_latency():
    """Test latency with pre-loaded models."""
    audio_path = "samples/test_tts.wav"

    print("=" * 60)
    print("Voice Bridge Latency Test (Pre-loaded Models)")
    print("=" * 60)

    # Pre-load models (this is initialization time, not counted)
    print("\n[INIT] Loading models...")
    init_start = time.time()
    transcriber = WhisperTranscriber(model_size="tiny", device="cpu", compute_type="int8")
    tts = SmartTTS(preferred_engine="kokoro")

    # Warm up - first transcription loads model
    print("[INIT] Warming up transcription model...")
    _ = transcriber.transcribe(audio_path)

    # Warm up - first TTS synthesis loads model
    print("[INIT] Warming up TTS model...")
    _ = tts.synthesize("Warm up")

    init_elapsed = time.time() - init_start
    print(f"[INIT] Completed in {init_elapsed:.2f}s")

    # Now measure actual processing latency
    print("\n" + "=" * 60)
    print("Latency Test - Running pipeline...")
    print("=" * 60)

    total_start = time.time()

    # Step 1: Transcription
    t1_start = time.time()
    result = transcriber.transcribe(audio_path)
    transcription = result['text']
    t1_elapsed = time.time() - t1_start
    print(f"[1/3] Transcription: {t1_elapsed:.2f}s")
    print(f"      Text: {transcription[:60]}...")

    # Step 2: Simulate OpenClaw processing (minimal)
    t2_start = time.time()
    response_text = f"Response to: {transcription[:50]}"
    t2_elapsed = time.time() - t2_start
    print(f"[2/3] Processing: {t2_elapsed:.3f}s")

    # Step 3: TTS
    t3_start = time.time()
    audio_data = tts.synthesize(response_text)
    t3_elapsed = time.time() - t3_start
    print(f"[3/3] TTS: {t3_elapsed:.2f}s")
    print(f"      Generated {len(audio_data)} bytes")

    total_elapsed = time.time() - total_start
    print("\n" + "=" * 60)
    print(f"TOTAL LATENCY: {total_elapsed:.2f}s")
    print("=" * 60)

    if total_elapsed < 3.0:
        print("✓ PASS: Latency under 3 second target")
    else:
        print(f"⚠ NOTE: Latency {total_elapsed - 3.0:.2f}s over target")
        print("  (This is expected on CPU without optimization)")

    return total_elapsed

if __name__ == "__main__":
    test_latency()
