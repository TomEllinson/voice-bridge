#!/usr/bin/env python3
"""Create a simple test audio file for transcription testing."""

import numpy as np
import soundfile as sf
import os

os.makedirs('samples', exist_ok=True)

# Create a simple sine wave with some variation (simulating speech-like audio)
duration = 3.0  # seconds
sample_rate = 16000
t = np.linspace(0, duration, int(sample_rate * duration))

# Multi-frequency tone to simulate speech
freq1 = 440  # A4
freq2 = 880  # A5
signal = 0.5 * np.sin(2 * np.pi * freq1 * t) + 0.3 * np.sin(2 * np.pi * freq2 * t)

# Add some amplitude modulation (like speech patterns)
signal *= (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t))

# Normalize
signal = signal / np.max(np.abs(signal)) * 0.8

# Save as WAV
sf.write('samples/test_speech.wav', signal, sample_rate)
print('Created samples/test_speech.wav')
