#!/usr/bin/env python3
"""Test Phase 3 modules."""

from websocket_server import VoiceBridgeWebSocket, AudioStreamBuffer
from prosody_detector import ProsodyDetector
from voice_persona import VoicePersonaManager
from voice_profiler import VoiceProfiler
from interruption_handler import InterruptionHandler

print('All Phase 3 modules import successfully:')
print('  ✓ WebSocket server (websocket_server.py)')
print('  ✓ Audio stream buffer')
print('  ✓ Prosody detector (prosody_detector.py)')
print('  ✓ Voice persona manager (voice_persona.py)')
print('  ✓ Voice profiler (voice_profiler.py)')
print('  ✓ Interruption handler (interruption_handler.py)')

# Test audio buffer
buffer = AudioStreamBuffer()
print('\nAudioStreamBuffer initialized:')
print(f'  - Sample rate: {buffer.sample_rate}')
print(f'  - Channels: {buffer.channels}')
print(f'  - Silence threshold: {buffer.silence_threshold}s')

# Test prosody detector
detector = ProsodyDetector()
print('\nProsodyDetector initialized:')
print(f'  - Sample rate: {detector.sample_rate}')

# Test voice persona manager
persona_manager = VoicePersonaManager()
print('\nVoicePersonaManager initialized:')
print(f'  - Built-in personas: {len(persona_manager.personas)}')

# Test voice profiler
profiler = VoiceProfiler()
print('\nVoiceProfiler initialized:')
print(f'  - Profiles: {len(profiler.profiles)}')
print(f'  - Similarity threshold: {profiler.similarity_threshold}')

# Test interruption handler
handler = InterruptionHandler()
print('\nInterruptionHandler initialized:')
print(f'  - State: {handler.state}')

print('\n✓ All Phase 3 advanced features are ready!')
