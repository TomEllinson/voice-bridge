---
project: voice-bridge
type: software
priority: 2
repo: TomEllinson/voice-bridge
dir: /home/tom/software_projects/voice-bridge
branch_prefix: feature
permissions: unrestricted
budget:
  max_session_usd: 10
  max_daily_minutes: 120
  max_phase_sessions: 10
nfr:
  language: python
  test_framework: pytest
  min_test_coverage: 60
  lint: false
  ci: false
phases:
  - id: integration-testing
    name: "Integration & Testing"
    gate: "test -f /home/tom/software_projects/voice-bridge/TEST_RESULTS.md && grep -q 'ALL_TESTS.*PASS' /home/tom/software_projects/voice-bridge/TEST_RESULTS.md"
    actions:
      - id: websocket-startup
        do: "Test WebSocket server startup with auto-detected Tailscale IP"
        verify: "cd /home/tom/software_projects/voice-bridge && python3 -c 'import websocket_server' && echo OK"
        model: kimi
      - id: android-connection
        do: "Verify WebSocket connection from Android app"
        verify: "test -f /home/tom/software_projects/voice-bridge/TEST_RESULTS.md && grep -q 'WebSocket.*PASS' /home/tom/software_projects/voice-bridge/TEST_RESULTS.md"
        model: kimi
      - id: audio-pipeline
        do: "Verify audio pipeline: mic → Whisper → OpenClaw → TTS → speaker"
        verify: "test -f /home/tom/software_projects/voice-bridge/TEST_RESULTS.md && grep -q 'Audio.*PASS' /home/tom/software_projects/voice-bridge/TEST_RESULTS.md"
        model: kimi
      - id: latency-check
        do: "Verify latency under 3 seconds for simple queries"
        verify: "test -f /home/tom/software_projects/voice-bridge/TEST_RESULTS.md && grep -q 'Latency.*2.*s' /home/tom/software_projects/voice-bridge/TEST_RESULTS.md"
        model: kimi
      - id: bluetooth-test
        do: "Verify Bluetooth headset compatibility"
        verify: "test -f /home/tom/software_projects/voice-bridge/TEST_RESULTS.md && grep -q 'Bluetooth.*PASS' /home/tom/software_projects/voice-bridge/TEST_RESULTS.md"
        model: kimi
---

# Project: Voice Bridge

## Meta
- **Type:** software
- **Priority:** 1
- **Target Directory:** ~/software_projects/voice-bridge
- **GitHub Repo:** TomEllinson/voice-bridge
- **Estimated Scope:** large (weeks)

## Summary
A **standalone voice chat app for OpenClaw** that operates exclusively over Tailscale. **NOT a Matrix integration** — this is a separate, self-contained voice communication system. All traffic stays within your Tailscale network (100.x.x.x), providing end-to-end encryption via Tailscale's mesh network.

## Architecture: Tailscale-Only Voice Mesh

### Security Model
- **NO public endpoints** — App refuses to connect to non-Tailscale IPs
- **NO cloud services** — All traffic device-to-device via Tailscale
- **Tailscale IPs only** — 100.64.0.0/10 range enforced
- **Fail-closed** — If Tailscale disconnected, app shows "No Tailscale Connection"
- **E2E encryption** — Provided by Tailscale WireGuard mesh

### Network Flow
```
[Android Phone] ←Tailscale→ [MARDA-BRAIN:8765] ←→ [OpenClaw Agent]
     (mic/speaker)    (encrypted)     (voice processing)
```

### Components

#### 1. Android App (Kotlin/Jetpack Compose)
- **UI:** Simple voice chat interface (push-to-talk or always-listening)
- **Audio:** AudioRecord/AudioTrack for native audio
- **Network:** WebSocket client connecting to Tailscale IP only
- **Permissions:** Microphone, Bluetooth headset, foreground service

#### 2. WebSocket Server (Python/FastAPI)
- **Bind:** Tailscale IP only (100.x.x.x:8765)
- **Audio Pipeline:** 
  - Receive audio stream → Whisper transcription
  - Send to OpenClaw → Get response
  - TTS (Kokoro) → Stream audio back
- **Security:** Reject connections from non-Tailscale IPs

#### 3. OpenClaw Integration
- Receives transcribed text from voice bridge
- Processes normally
- Returns response via TTS

## Phase 1: Android Developer Agent
**Goal:** Create an agent that can develop Android apps

### Agent Capabilities
- Write Kotlin code for Android
- Use Jetpack Compose for UI
- Manage Gradle builds
- Handle Android permissions
- Build and test APKs
- Debug Android apps

### Files to Create
- `agents/android_dev.py` — Android development agent
- `AGENTS.md` — Android dev agent instructions

## Phase 2: WebSocket Server
**Goal:** Build backend that only accepts Tailscale connections

### Implementation
- FastAPI WebSocket server
- IP whitelist: 100.64.0.0/10 (Tailscale)
- Reject all other IPs with error
- Audio streaming with VAD (Silero)

### Files to Create
- `server/websocket_server.py` — Tailscale-only WebSocket
- `server/audio_pipeline.py` — Whisper → OpenClaw → TTS
- `server/tailscale_guard.py` — IP enforcement

## Phase 3: Android App
**Goal:** Native Android app that connects to Tailscale server

### Implementation
- Kotlin/Jetpack Compose
- Foreground service for persistent connection
- WebSocket client (using OkHttp)
- AudioRecord/AudioTrack for audio
- Push-to-talk or voice-activated (configurable)

### Files to Create
- `android/VoiceBridgeApp/` — Full Android project
- `android/app/src/...` — Kotlin source files
- `android/app/build.gradle.kts` — Dependencies

## Phase 4: Integration & Testing
**Goal:** Full end-to-end voice chat

### Testing Checklist
- [ ] Android app connects only to 100.x.x.x IPs
- [ ] WebSocket server rejects non-Tailscale IPs
- [ ] Audio flows: mic → Android → Server → Whisper → OpenClaw → TTS → Android → speaker
- [ ] Latency < 3 seconds for simple queries
- [ ] Works with Bluetooth headset
- [ ] Background service keeps connection alive

## Technology Stack

### Android
- **Language:** Kotlin
- **UI:** Jetpack Compose
- **Audio:** AudioRecord, AudioTrack
- **Networking:** OkHttp WebSocket
- **Build:** Gradle

### Server
- **Framework:** FastAPI
- **WebSocket:** python-socketio or native websockets
- **Transcription:** faster-whisper (local)
- **TTS:** kokoro (local)
- **VAD:** silero-vad

### Security
- **Network:** Tailscale mesh only
- **Binding:** 100.x.x.x:8765
- **Firewall:** Reject non-Tailscale at application level

## Success Criteria
- [ ] Android APK builds and installs
- [ ] App only connects via Tailscale (fails gracefully otherwise)
- [ ] Voice latency under 3 seconds
- [ ] Interrupt handling (barge-in detection)
- [ ] Works while driving (Bluetooth, background service)
- [ ] Battery efficient (VAD, efficient wake/sleep)

## Notes
- **Not Matrix:** This is a standalone app, not a Matrix client
- **Tailscale is the safety net:** All security comes from Tailscale mesh
- **Local processing:** Whisper and TTS run on MARDA-BRAIN (not cloud)
- **Future:** Could add multiple voice channels, group chat, etc.
