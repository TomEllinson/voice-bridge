#!/usr/bin/env python3
"""Test full voice pipeline with latency measurement."""

import time
from pathlib import Path
from transcription import WhisperTranscriber
from tts_engine import SmartTTS
from voice_session import SessionManager

print("=" * 60)
print("Voice Pipeline Latency Test")
print("=" * 60)

# Initialize components once (not part of latency measurement)
print("\n[Setup] Initializing components...")
transcriber = WhisperTranscriber(model_size="tiny", device="cpu", compute_type="int8")
tts = SmartTTS(preferred_engine="kokoro")
session_manager = SessionManager()

audio_file = "samples/tts_output.wav"
print(f"[Setup] Using audio file: {audio_file}")

# Measure full pipeline latency
print("\n[Pipeline] Starting voice-in/voice-out pipeline...")
total_start = time.time()

# Step 1: Transcribe
print("\n[1/3] Transcribing audio...")
step_start = time.time()
result = transcriber.transcribe(audio_file)
transcribe_time = time.time() - step_start
print(f"   Transcription: '{result['text']}'")
print(f"   Time: {transcribe_time:.2f}s")

# Step 2: Simulate OpenClaw processing
print("\n[2/3] Processing with OpenClaw...")
step_start = time.time()
session = session_manager.get_or_create_session("demo_user", "demo_room")
session.add_message("user", result['text'])
# Simulated response
response_text = f"You said: {result['text']}"
processing_time = time.time() - step_start
print(f"   Response: '{response_text}'")
print(f"   Time: {processing_time:.2f}s")

# Step 3: Generate TTS
print("\n[3/3] Generating audio response...")
step_start = time.time()
audio_data = tts.synthesize(response_text)
tts_time = time.time() - step_start
print(f"   Generated {len(audio_data)} bytes")
print(f"   Time: {tts_time:.2f}s")

# Total
pipeline_time = time.time() - total_start

print("\n" + "=" * 60)
print("LATENCY RESULTS")
print("=" * 60)
print(f"Transcription:  {transcribe_time:.2f}s")
print(f"Processing:     {processing_time:.2f}s")
print(f"TTS:            {tts_time:.2f}s")
print(f"------------------------")
print(f"TOTAL PIPELINE: {pipeline_time:.2f}s")
print(f"Target:         3.00s")
print(f"Status:         {'PASS' if pipeline_time < 3.0 else 'FAIL - needs optimization'}")
print("=" * 60)

# Save response
output_path = Path("samples/pipeline_response.wav")
output_path.write_bytes(audio_data)
print(f"\nSaved response audio to: {output_path}")
