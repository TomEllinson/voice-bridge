# Voice Bridge for OpenClaw

A voice interface for OpenClaw enabling real-time audio conversations via Matrix. Phase 1 focuses on clip-based audio exchange through Matrix/Element.

## Features

- **Voice Input**: Receive and transcribe voice messages from Matrix
- **Voice Output**: Respond with synthesized audio using Kokoro TTS
- **Conversation Context**: Maintains session state across voice/text exchanges
- **Low Latency**: Local Whisper transcription + fast TTS generation

## Architecture

```
[Matrix Voice Msg] → [Download] → [Whisper] → [OpenClaw] → [Kokoro TTS] → [Matrix Audio Msg]
                                    ↓
                            [Session Context]
```

## Quick Start

### Prerequisites

- Python 3.10+
- Matrix account with access token
- OpenClaw instance running (optional, will fall back to local mode)

### Installation

```bash
# Clone repository
git clone https://github.com/TomEllinson/voice-bridge.git
cd voice-bridge

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Download Whisper model (will happen automatically on first run)
```

### Configuration

Create a `.env` file:

```bash
MATRIX_HOMESERVER=https://matrix.org
MATRIX_USER_ID=@yourbot:matrix.org
MATRIX_ACCESS_TOKEN=your_access_token_here
OPENCLAW_URL=http://localhost:8000
WHISPER_MODEL=base
TTS_ENGINE=kokoro
```

Get a Matrix access token:
```bash
curl -X POST https://matrix.org/_matrix/client/r0/login \
  -d '{"type":"m.login.password","user":"username","password":"password"}'
```

### Running

```bash
# Run the voice bridge
python matrix_voice_bridge.py

# Or with options
python matrix_voice_bridge.py \
  --whisper-model small \
  --tts-engine kokoro \
  --verbose
```

## Testing

### Unit Tests

```bash
# Run unit tests
python test_voice_bridge.py

# Verify all modules import
python verify.py
```

### Demo Scripts

The `demo.py` script provides comprehensive testing without needing Matrix credentials:

```bash
# Test transcription on an audio file
python demo.py transcribe audio.ogg --model base

# Test TTS synthesis
python demo.py tts "Hello, this is a test"
python demo.py tts "Hello" --engine piper

# Test full voice-in/voice-out pipeline
python demo.py pipeline audio.ogg --model base --tts-engine kokoro

# Test session management
python demo.py session

# Test Matrix connection (requires credentials)
python demo.py matrix
```

### Manual Testing

```python
# Test transcription
from transcription import transcribe_audio
text = transcribe_audio('test_audio.ogg')
print(f'Transcription: {text}')

# Test TTS
from tts_engine import speak
audio = speak("Hello from Voice Bridge!")
```

## Modules

### `transcription.py`
Local Whisper transcription using `faster-whisper` (faster) or `openai-whisper` (fallback).

```python
from transcription import WhisperTranscriber

transcriber = WhisperTranscriber(model_size="base")
result = transcriber.transcribe("audio.ogg")
print(result['text'])  # Transcribed text
```

### `tts_engine.py`
Text-to-speech with multiple backends (Kokoro preferred, Piper fallback, pyttsx3 last resort).

```python
from tts_engine import SmartTTS

tts = SmartTTS(preferred_engine="kokoro")
audio = tts.synthesize("Hello from Voice Bridge!")
# audio is WAV bytes
```

### `voice_session.py`
Conversation state management with context window and session expiration.

```python
from voice_session import SessionManager

manager = SessionManager()
session = manager.get_or_create_session(user_id="@user:matrix.org", room_id="!room:matrix.org")
session.add_message("user", "Hello")
context = session.get_context()  # Last N messages for OpenClaw
```

### `matrix_voice_bridge.py`
Main entry point - handles Matrix events, orchestrates transcription/TTS, manages sessions.

## Development

### Adding a New TTS Engine

```python
from tts_engine import TTSEngine

class MyTTS(TTSEngine):
    def synthesize(self, text: str, voice: Optional[str] = None) -> bytes:
        # Your TTS logic here
        return audio_bytes
```

### Testing Transcription

```python
from transcription import WhisperTranscriber
import time

t = WhisperTranscriber(model_size="base")
start = time.time()
result = t.transcribe("test.ogg")
print(f"Took {time.time() - start:.2f}s")
print(f"Text: {result['text']}")
```

## Phase 1 Success Criteria

- [x] Can receive voice messages from Matrix
- [x] Can transcribe audio with local Whisper
- [x] Can synthesize responses with TTS
- [x] Can send audio back to Matrix
- [ ] Latency under 3 seconds for simple queries
- [ ] Maintains conversation context

## Phase 2: Android App

See `DESIGN.md` for Phase 2 plans (real-time streaming, VAD, interruption detection).

## License

MIT
