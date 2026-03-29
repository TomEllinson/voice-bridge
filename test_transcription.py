#!/usr/bin/env python3
"""Test transcription with TTS-generated audio."""

import time
from transcription import WhisperTranscriber

print("Loading Whisper model...")
transcriber = WhisperTranscriber(model_size="tiny", device="cpu", compute_type="int8")

print("Transcribing TTS audio...")
start = time.time()
result = transcriber.transcribe("samples/tts_output.wav")
elapsed = time.time() - start

print(f"\n=== Transcription Results ===")
print(f"Time: {elapsed:.2f}s")
print(f"Text: {result['text']}")
print(f"Language: {result.get('language', 'unknown')}")
print(f"\nTranscription test PASSED")
