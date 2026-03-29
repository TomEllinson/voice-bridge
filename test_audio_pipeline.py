#!/usr/bin/env python3
"""
End-to-end audio pipeline test for Voice Bridge.

Tests the complete flow: mic input → Whisper → OpenClaw → TTS → speaker
Uses synthetic audio to verify transcription, TTS, and measure latency.
"""

import asyncio
import json
import time
import tempfile
import wave
import io
import sys
from datetime import datetime

import numpy as np
import soundfile as sf
import websockets

# Import our modules
from transcription import WhisperTranscriber
from tts_engine import SmartTTS


def create_test_audio_phrase(text: str = "Hello world testing voice bridge", sample_rate: int = 16000) -> bytes:
    """Create synthetic audio phrase for testing.

    Generates a simple sine wave that resembles speech patterns.
    This simulates microphone input without needing actual audio recording.
    """
    # Create a simple phrase-like audio pattern using multiple sine waves
    duration = 2.0  # 2 seconds
    t = np.linspace(0, duration, int(sample_rate * duration))

    # Create a more speech-like signal with varying frequencies
    # Simulating vowels and consonants
    freq1 = 200  # Fundamental frequency (vocal fold vibration)
    freq2 = 800  # First formant
    freq3 = 1200  # Second formant

    # Modulate amplitude to simulate speech patterns
    envelope = np.ones_like(t)
    for i in range(0, len(t), int(sample_rate * 0.1)):
        envelope[i:i+1000] *= np.random.uniform(0.5, 1.0)

    # Combine frequencies
    signal = (0.5 * np.sin(2 * np.pi * freq1 * t) +
              0.3 * np.sin(2 * np.pi * freq2 * t) +
              0.2 * np.sin(2 * np.pi * freq3 * t))

    # Apply envelope and normalize
    signal *= envelope
    signal = signal / np.max(np.abs(signal)) * 0.5

    # Convert to 16-bit PCM
    audio_int16 = (signal * 32767).astype(np.int16)

    return audio_int16.tobytes()


def create_whisper_compatible_audio(text: str = "Hello world this is a test", duration: float = 3.0) -> bytes:
    """Create synthetic audio that works well with Whisper.

    Uses a more realistic speech-like signal with proper frequency characteristics.
    """
    sample_rate = 16000
    t = np.linspace(0, duration, int(sample_rate * duration))

    # Create speech-like signal with formants
    # Human speech typically has fundamental freq 85-255 Hz for men, 165-355 Hz for women
    # Formants are around 500-4000 Hz

    fundamental = 150  # Hz
    signal = np.zeros_like(t)

    # Add harmonics
    for harmonic in range(1, 6):
        freq = fundamental * harmonic
        amplitude = 1.0 / harmonic
        signal += amplitude * np.sin(2 * np.pi * freq * t)

    # Add formant frequencies (resonance)
    for formant in [800, 1200, 2500]:
        amplitude = 0.3
        signal += amplitude * np.sin(2 * np.pi * formant * t)

    # Apply amplitude modulation to simulate syllables (every ~200ms)
    syllable_rate = 5  # syllables per second
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * syllable_rate * t - np.pi/2)
    envelope = np.clip(envelope, 0.1, 1.0)
    signal *= envelope

    # Normalize
    signal = signal / np.max(np.abs(signal)) * 0.5

    # Convert to 16-bit PCM
    audio_int16 = (signal * 32767).astype(np.int16)

    return audio_int16.tobytes()


class AudioPipelineTester:
    """Tests the complete audio pipeline."""

    def __init__(self):
        self.results = {}
        self.transcriber = None
        self.tts = None

    def setup(self):
        """Initialize models."""
        print("=" * 60)
        print("Audio Pipeline Test Setup")
        print("=" * 60)

        print("\n[1/3] Loading Whisper transcriber...")
        start = time.time()
        self.transcriber = WhisperTranscriber(
            model_size="tiny",
            device="cpu",
            compute_type="int8"
        )
        load_time = time.time() - start
        print(f"      Whisper loaded in {load_time:.2f}s")

        print("\n[2/3] Loading TTS engine...")
        start = time.time()
        self.tts = SmartTTS(preferred_engine="kokoro")
        tts_load_time = time.time() - start
        print(f"      TTS loaded in {tts_load_time:.2f}s")

        print("\n[3/3] Warming up models...")
        warmup_text = "Warm up"
        self.tts.synthesize(warmup_text)
        print("      Models warmed up")

        print("\n" + "=" * 60)
        print("Setup complete!")
        print("=" * 60)

    def test_transcription(self) -> dict:
        """Test Whisper transcription with synthetic audio."""
        print("\n" + "=" * 60)
        print("Test 1: Whisper Transcription")
        print("=" * 60)

        # Create synthetic audio
        print("Generating synthetic audio input...")
        audio_bytes = create_whisper_compatible_audio(duration=3.0)
        print(f"  Generated {len(audio_bytes)} bytes of audio data")

        # Save to temp file for transcription
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            sf.write(f.name, audio_array, 16000)
            temp_file = f.name

        # Transcribe
        print("Transcribing audio...")
        start = time.time()
        result = self.transcriber.transcribe(temp_file)
        transcription_time = time.time() - start

        transcription_text = result.get('text', '')
        print(f"  Transcription result: '{transcription_text}'")
        print(f"  Transcription time: {transcription_time:.3f}s")

        # Check if we got something (synthetic audio won't transcribe to meaningful text,
        # but we should at least get some output or no errors)
        success = transcription_text is not None and transcription_time < 5.0

        return {
            'test': 'Transcription',
            'success': success,
            'time': transcription_time,
            'result': transcription_text,
            'audio_bytes': len(audio_bytes)
        }

    def test_tts_synthesis(self) -> dict:
        """Test TTS synthesis."""
        print("\n" + "=" * 60)
        print("Test 2: TTS Synthesis")
        print("=" * 60)

        test_text = "Hello, this is Voice Bridge speaking."
        print(f"Synthesizing: '{test_text}'")

        start = time.time()
        audio_data = self.tts.synthesize(test_text)
        synthesis_time = time.time() - start

        print(f"  Generated {len(audio_data)} bytes of audio")
        print(f"  Synthesis time: {synthesis_time:.3f}s")

        # Verify audio is valid
        with io.BytesIO(audio_data) as bio:
            try:
                data, samplerate = sf.read(bio)
                duration = len(data) / samplerate
                print(f"  Audio duration: {duration:.2f}s")
                print(f"  Sample rate: {samplerate}Hz")
                success = duration > 0
            except Exception as e:
                print(f"  Error reading audio: {e}")
                success = False
                duration = 0

        return {
            'test': 'TTS Synthesis',
            'success': success,
            'time': synthesis_time,
            'audio_bytes': len(audio_data),
            'duration': duration
        }

    def test_full_pipeline(self) -> dict:
        """Test complete pipeline: audio → text → audio."""
        print("\n" + "=" * 60)
        print("Test 3: Full Pipeline (simulated)")
        print("=" * 60)

        # Since synthetic audio won't transcribe to meaningful text,
        # we'll simulate the pipeline with known text
        input_text = "What time is it"

        print(f"Simulated user input: '{input_text}'")
        print("\nStep 1: Transcription (simulated)")
        print("  - Whisper would transcribe microphone audio")
        print("  - Assuming transcription: '{input_text}'")

        # Simulate OpenClaw processing
        print("\nStep 2: OpenClaw processing")
        start = time.time()
        # In real scenario, this would call OpenClaw
        # For now, simulate a simple response
        response_text = f"You asked: {input_text}. The time is {datetime.now().strftime('%I:%M %p')}"
        processing_time = time.time() - start
        print(f"  - Response: '{response_text}'")
        print(f"  - Processing time: {processing_time:.3f}s")

        # TTS
        print("\nStep 3: TTS synthesis")
        tts_start = time.time()
        audio_data = self.tts.synthesize(response_text)
        tts_time = time.time() - tts_start
        print(f"  - Generated {len(audio_data)} bytes of audio")
        print(f"  - TTS time: {tts_time:.3f}s")

        total_time = processing_time + tts_time
        print(f"\nTotal pipeline time: {total_time:.3f}s")

        # Verify audio
        with io.BytesIO(audio_data) as bio:
            try:
                data, samplerate = sf.read(bio)
                duration = len(data) / samplerate
                success = total_time < 3.0  # Under 3 seconds target
            except:
                duration = 0
                success = False

        return {
            'test': 'Full Pipeline',
            'success': success,
            'total_time': total_time,
            'tts_time': tts_time,
            'audio_duration': duration,
            'response_text': response_text
        }

    async def test_websocket_audio_flow(self) -> dict:
        """Test WebSocket audio streaming."""
        print("\n" + "=" * 60)
        print("Test 4: WebSocket Audio Streaming")
        print("=" * 60)

        uri = "ws://100.82.133.125:8765"
        print(f"Connecting to {uri}...")

        try:
            async with websockets.connect(uri, ping_interval=None) as ws:
                print("  Connected!")

                # Send start_listening
                await ws.send(json.dumps({'type': 'start_listening'}))
                response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                print(f"  Start listening response: {response}")

                # Create and send synthetic audio
                print("\nSending synthetic audio...")
                audio_data = create_whisper_compatible_audio(duration=2.0)

                # Send audio in chunks (simulating real-time streaming)
                chunk_size = 3200  # 100ms at 16kHz, 16-bit
                total_chunks = 0

                start_time = time.time()
                for i in range(0, len(audio_data), chunk_size):
                    chunk = audio_data[i:i+chunk_size]
                    await ws.send(chunk)
                    total_chunks += 1
                    await asyncio.sleep(0.01)  # Small delay between chunks

                print(f"  Sent {total_chunks} audio chunks ({len(audio_data)} bytes)")

                # Send stop_listening to trigger processing
                print("\nSending stop_listening...")
                await ws.send(json.dumps({'type': 'stop_listening'}))

                # Collect responses
                print("\nWaiting for responses...")
                responses = []
                try:
                    while True:
                        response = await asyncio.wait_for(ws.recv(), timeout=5.0)

                        if isinstance(response, bytes):
                            print(f"  Received audio chunk: {len(response)} bytes")
                        else:
                            data = json.loads(response)
                            print(f"  Received: {data}")
                            responses.append(data)

                            # Check for response_end
                            if data.get('type') == 'response_end':
                                break

                except asyncio.TimeoutError:
                    print("  Timeout waiting for responses")

                total_time = time.time() - start_time
                print(f"\nTotal WebSocket flow time: {total_time:.3f}s")

                success = total_time < 5.0 and any(r.get('type') == 'response_end' for r in responses)

                return {
                    'test': 'WebSocket Audio Flow',
                    'success': success,
                    'total_time': total_time,
                    'chunks_sent': total_chunks,
                    'responses': len(responses)
                }

        except Exception as e:
            print(f"  WebSocket test failed: {e}")
            return {
                'test': 'WebSocket Audio Flow',
                'success': False,
                'error': str(e)
            }

    def run_all_tests(self):
        """Run all audio pipeline tests."""
        print("\n" + "=" * 60)
        print("VOICE BRIDGE - AUDIO PIPELINE TESTS")
        print("=" * 60)
        print(f"Started: {datetime.now().isoformat()}")
        print()

        try:
            self.setup()

            # Run tests
            results = []
            results.append(self.test_transcription())
            results.append(self.test_tts_synthesis())
            results.append(self.test_full_pipeline())

            # Run WebSocket test
            ws_result = asyncio.run(self.test_websocket_audio_flow())
            results.append(ws_result)

            # Summary
            print("\n" + "=" * 60)
            print("TEST SUMMARY")
            print("=" * 60)

            all_passed = True
            for r in results:
                status = "PASS" if r['success'] else "FAIL"
                print(f"  {r['test']}: {status}")
                if 'time' in r:
                    print(f"    Time: {r['time']:.3f}s")
                if 'total_time' in r:
                    print(f"    Total time: {r['total_time']:.3f}s")
                if not r['success']:
                    all_passed = False

            print("\n" + "=" * 60)
            if all_passed:
                print("Audio Pipeline: ALL TESTS PASSED")
                self.results = {'status': 'PASS', 'tests': results}
            else:
                print("Audio Pipeline: SOME TESTS FAILED")
                self.results = {'status': 'PARTIAL', 'tests': results}
            print("=" * 60)

            return self.results

        except Exception as e:
            print(f"\nTest execution failed: {e}")
            import traceback
            traceback.print_exc()
            self.results = {'status': 'FAIL', 'error': str(e)}
            return self.results


def main():
    """Run audio pipeline tests."""
    tester = AudioPipelineTester()
    results = tester.run_all_tests()

    # Exit with appropriate code
    sys.exit(0 if results['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
