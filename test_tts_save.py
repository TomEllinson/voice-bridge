#!/usr/bin/env python3
"""Generate TTS audio for transcription testing."""

from tts_engine import SmartTTS

tts = SmartTTS(preferred_engine='kokoro')
audio = tts.synthesize('Hello, this is a test of the voice bridge system.')

# Save to file
with open('samples/tts_output.wav', 'wb') as f:
    f.write(audio)
print('Saved TTS audio to samples/tts_output.wav')
