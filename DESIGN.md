# Project: Voice Bridge

## Meta
- **Type:** software
- **Priority:** 1
- **Target Directory:** ~/software_projects/voice-bridge
- **GitHub Repo:** TomEllinson/voice-bridge
- **Estimated Scope:** large (weeks)

## Summary
A voice interface for OpenClaw enabling real-time audio conversations. Two-phase approach: (1) Matrix audio clip exchange for baseline functionality, (2) Android app for seamless mobile voice interaction with interruption detection and turn-taking.

## Goals
1. Enable voice input/output for OpenClaw conversations
2. Support hands-free operation during physical activities (driving, walking)
3. Implement natural conversation flow with interruption detection
4. Maintain OpenClaw's autonomous agent capabilities via voice
5. Create seamless mobile experience for supervision-on-the-go

## Phase 1: Matrix Audio Baseline
### Objectives
- Receive voice messages from Matrix/Element
- Transcribe audio to text (local Whisper or API)
- Send succinct audio responses back to Matrix
- Maintain conversation context across audio/text

### Technical Approach
- Matrix bot extension for voice message handling
- Local Whisper integration for transcription (privacy, offline)
- TTS for responses (Kokoro, Piper, or cloud)
- Audio file management (cleanup, compression)

### Files to Create
- `matrix_voice_bridge.py` - Voice message handler
- `transcription.py` - Whisper integration
- `tts_engine.py` - Text-to-speech
- `voice_session.py` - Conversation state management

## Phase 2: Android App
### Objectives
- Native Android voice chat interface
- Real-time streaming (not clip-based)
- Push-to-talk or always-listening modes
- Background operation with notification
- Interruption detection and handling

### Technical Approach
- Kotlin/Android native app
- WebSocket connection to OpenClaw gateway
- Audio streaming with VAD (voice activity detection)
- Local wake word detection (optional)
- Bluetooth headset support

### Files to Create
- `VoiceBridgeApp/` - Android project
- `websocket_server.py` - Real-time audio streaming backend
- `vad_module.py` - Voice activity detection
- `interruption_handler.py` - Turn-taking logic

## Phase 3: Advanced Features
### Objectives
- Interruption-aware responses (Claude/Grok style)
- Prosody detection (emotional tone)
- Multiple voice personas
- Conversation memory optimization for voice

### Key Features
- Barge-in detection (user speaks while agent speaking)
- Adaptive response length based on context
- Voice activity profiling
- Background noise filtering

## Architecture

### Voice Pipeline
```
[Android Mic] → [VAD] → [Stream] → [Whisper] → [OpenClaw] → [TTS] → [Speaker]
                ↓                           ↓
         [Wake Word]                   [Interruption Detection]
```

### Components
1. **Audio Ingestion**: Capture, VAD, streaming
2. **Transcription**: Real-time Whisper or API
3. **Agent Processing**: Standard OpenClaw agent loop
4. **Response Generation**: TTS with voice selection
5. **Output**: Audio playback with interruption monitoring

## Security & Network Constraints
**CRITICAL: Tailscale-Only Networking**
- Android app MUST only communicate over Tailscale (100.x.x.x addresses)
- WebSocket server binds to Tailscale IP only (not 0.0.0.0)
- No public internet exposure — all traffic through encrypted Tailscale mesh
- Certificate pinning for Tailscale IPs
- Fail-closed: If Tailscale not connected, app refuses to function

**Rationale:** Voice contains sensitive personal data. No cloud services, no public endpoints, only device-to-device through your private network.

## Technology Stack
- **Transcription**: Whisper (local) or Deepgram/AssemblyAI (cloud)
- **TTS**: Kokoro-TTS, Piper, or ElevenLabs
- **VAD**: Silero VAD or WebRTC VAD
- **Android**: Kotlin, Jetpack Compose, WebSocket
- **Backend**: Python, FastAPI, WebSocket

## Risks & Mitigations
- **Latency**: Use local Whisper, optimize TTS caching
- **Battery**: Efficient VAD, background service management
- **Privacy**: Local transcription preferred, encrypted transport
- **Interruptions**: Complex state machine, clear turn signaling

## Success Criteria
- [ ] Can send voice message in Matrix, get voice response
- [ ] Android app provides hands-free operation
- [ ] Interruption detection works 90%+ of time
- [ ] Latency under 3 seconds for simple queries
- [ ] Works reliably in car/driving scenarios

## BMAD Alignment
- **Self-Documentation**: All decisions in DESIGN.md
- **Autonomy**: Agent determines when to speak vs text
- **Quality Gates**: Latency benchmarks, interruption accuracy
- **Git Hygiene**: Feature branches, meaningful commits
