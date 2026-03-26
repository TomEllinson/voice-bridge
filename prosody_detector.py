"""Prosody detection module for emotional tone analysis in voice conversations.

Analyzes pitch, energy, tempo, and spectral features to detect emotional states
like excitement, frustration, calmness, and urgency.
"""

import numpy as np
import logging
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time

logger = logging.getLogger(__name__)


class EmotionalTone(Enum):
    """Detected emotional tones in voice."""
    NEUTRAL = "neutral"
    CALM = "calm"
    EXCITED = "excited"
    FRUSTRATED = "frustrated"
    CONFUSED = "confused"
    URGENT = "urgent"
    HAPPY = "happy"
    SAD = "sad"


class SpeakingPace(Enum):
    """Detected speaking pace."""
    SLOW = "slow"      # < 100 words per minute
    NORMAL = "normal"  # 100-160 wpm
    FAST = "fast"      # > 160 wpm


@dataclass
class ProsodyFeatures:
    """Extracted prosodic features from audio."""
    # Pitch features (fundamental frequency)
    pitch_mean: float = 0.0
    pitch_std: float = 0.0
    pitch_range: float = 0.0
    pitch_contour: List[float] = field(default_factory=list)

    # Energy/volume features
    energy_mean: float = 0.0
    energy_std: float = 0.0
    energy_range: float = 0.0
    rms_energy: float = 0.0

    # Timing features
    speaking_rate: float = 0.0  # Estimated words per minute
    pause_ratio: float = 0.0    # Ratio of pause time to total time
    pause_count: int = 0

    # Spectral features
    spectral_centroid: float = 0.0
    spectral_rolloff: float = 0.0
    spectral_flux: float = 0.0
    zcr: float = 0.0  # Zero crossing rate

    # Voice quality
    jitter: float = 0.0  # Pitch instability
    shimmer: float = 0.0  # Amplitude instability
    hnr: float = 0.0  # Harmonic-to-noise ratio

    def to_dict(self) -> Dict:
        """Convert to dictionary (excluding large contour data)."""
        return {
            'pitch_mean': self.pitch_mean,
            'pitch_std': self.pitch_std,
            'pitch_range': self.pitch_range,
            'energy_mean': self.energy_mean,
            'energy_std': self.energy_std,
            'energy_range': self.energy_range,
            'rms_energy': self.rms_energy,
            'speaking_rate': self.speaking_rate,
            'pause_ratio': self.pause_ratio,
            'pause_count': self.pause_count,
            'spectral_centroid': self.spectral_centroid,
            'spectral_rolloff': self.spectral_rolloff,
            'spectral_flux': self.spectral_flux,
            'zcr': self.zcr,
            'jitter': self.jitter,
            'shimmer': self.shimmer,
            'hnr': self.hnr,
        }


@dataclass
class ProsodyAnalysis:
    """Result of prosody analysis."""
    primary_tone: EmotionalTone = EmotionalTone.NEUTRAL
    secondary_tone: Optional[EmotionalTone] = None
    confidence: float = 0.0
    features: ProsodyFeatures = field(default_factory=ProsodyFeatures)
    pace: SpeakingPace = SpeakingPace.NORMAL
    urgency_score: float = 0.0  # 0-1 scale
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'primary_tone': self.primary_tone.value,
            'secondary_tone': self.secondary_tone.value if self.secondary_tone else None,
            'confidence': self.confidence,
            'features': self.features.to_dict(),
            'pace': self.pace.value,
            'urgency_score': self.urgency_score,
            'timestamp': self.timestamp,
        }


class ProsodyDetector:
    """Detects emotional tone and prosodic features from audio."""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.feature_history: List[ProsodyFeatures] = []
        self.max_history = 10

    def analyze(self, audio_data: np.ndarray) -> ProsodyAnalysis:
        """Analyze audio for prosodic features and emotional tone.

        Args:
            audio_data: Audio samples as numpy array

        Returns:
            ProsodyAnalysis with detected tone and features
        """
        features = self._extract_features(audio_data)
        self.feature_history.append(features)
        if len(self.feature_history) > self.max_history:
            self.feature_history.pop(0)

        tone, secondary, confidence = self._detect_emotion(features)
        pace = self._detect_pace(features)
        urgency = self._calculate_urgency(features)

        return ProsodyAnalysis(
            primary_tone=tone,
            secondary_tone=secondary,
            confidence=confidence,
            features=features,
            pace=pace,
            urgency_score=urgency
        )

    def _extract_features(self, audio_data: np.ndarray) -> ProsodyFeatures:
        """Extract prosodic features from audio."""
        try:
            import librosa

            features = ProsodyFeatures()

            # Ensure audio is float and normalized
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32) / np.max(np.abs(audio_data))

            # Pitch extraction using librosa
            try:
                f0, voiced_flag, _ = librosa.pyin(
                    audio_data,
                    fmin=librosa.note_to_hz('C2'),
                    fmax=librosa.note_to_hz('C7'),
                    sr=self.sample_rate
                )
                voiced_f0 = f0[voiced_flag] if voiced_flag is not None else f0[~np.isnan(f0)]

                if len(voiced_f0) > 0:
                    features.pitch_mean = float(np.nanmean(voiced_f0))
                    features.pitch_std = float(np.nanstd(voiced_f0))
                    features.pitch_range = float(np.nanmax(voiced_f0) - np.nanmin(voiced_f0))
                    features.pitch_contour = f0.tolist()
            except Exception as e:
                logger.debug(f"Pitch extraction failed: {e}")

            # Energy features
            features.rms_energy = float(np.sqrt(np.mean(audio_data ** 2)))
            frame_length = int(self.sample_rate * 0.025)  # 25ms frames
            hop_length = int(self.sample_rate * 0.010)    # 10ms hop

            rms = librosa.feature.rms(
                y=audio_data,
                frame_length=frame_length,
                hop_length=hop_length
            )[0]

            features.energy_mean = float(np.mean(rms))
            features.energy_std = float(np.std(rms))
            features.energy_range = float(np.max(rms) - np.min(rms))

            # Spectral features
            spec_cent = librosa.feature.spectral_centroid(
                y=audio_data,
                sr=self.sample_rate,
                hop_length=hop_length
            )[0]
            features.spectral_centroid = float(np.mean(spec_cent))

            spec_roll = librosa.feature.spectral_rolloff(
                y=audio_data,
                sr=self.sample_rate,
                hop_length=hop_length
            )[0]
            features.spectral_rolloff = float(np.mean(spec_roll))

            # Zero crossing rate (indicates noisiness)
            zcr = librosa.feature.zero_crossing_rate(
                audio_data,
                frame_length=frame_length,
                hop_length=hop_length
            )[0]
            features.zcr = float(np.mean(zcr))

            # Spectral flux (rate of change in spectrum)
            spec_flux = librosa.onset.onset_strength(
                y=audio_data,
                sr=self.sample_rate,
                hop_length=hop_length
            )
            features.spectral_flux = float(np.mean(spec_flux))

            # Estimate speaking rate based on syllable detection
            onset_env = librosa.onset.onset_strength(y=audio_data, sr=self.sample_rate)
            onsets = librosa.onset.onset_detect(
                onset_envelope=onset_env,
                sr=self.sample_rate
            )
            duration_minutes = len(audio_data) / self.sample_rate / 60
            if duration_minutes > 0:
                # Rough estimate: ~2 syllables per word on average
                features.speaking_rate = len(onsets) / duration_minutes / 2

            # Detect pauses
            energy_threshold = features.energy_mean * 0.3
            is_silence = rms < energy_threshold
            silence_runs = self._find_runs(is_silence)
            features.pause_count = len(silence_runs)
            features.pause_ratio = float(np.sum(is_silence)) / len(is_silence)

            # Voice quality metrics (simplified)
            if len(voiced_f0) > 1:
                # Jitter: variation in pitch period
                periods = self.sample_rate / voiced_f0[voiced_f0 > 0]
                if len(periods) > 1:
                    features.jitter = float(np.std(np.diff(periods)) / np.mean(periods))

                # Shimmer: variation in amplitude
                if len(rms) > 1:
                    features.shimmer = float(np.std(np.diff(rms)) / np.mean(rms))

                # HNR: harmonic to noise ratio
                try:
                    features.hnr = self._estimate_hnr(audio_data)
                except Exception:
                    pass

            return features

        except ImportError:
            logger.warning("librosa not available, using basic features")
            return self._basic_features(audio_data)
        except Exception as e:
            logger.error(f"Feature extraction error: {e}")
            return ProsodyFeatures()

    def _basic_features(self, audio_data: np.ndarray) -> ProsodyFeatures:
        """Extract basic features without librosa."""
        features = ProsodyFeatures()

        if len(audio_data) == 0:
            return features

        # Normalize
        audio_norm = audio_data.astype(np.float32)
        if np.max(np.abs(audio_norm)) > 0:
            audio_norm = audio_norm / np.max(np.abs(audio_norm))

        # RMS energy
        features.rms_energy = float(np.sqrt(np.mean(audio_norm ** 2)))
        features.energy_mean = features.rms_energy

        # Simple ZCR
        zero_crossings = np.sum(np.diff(np.sign(audio_norm)) != 0)
        features.zcr = zero_crossings / len(audio_norm)

        return features

    def _detect_emotion(self, features: ProsodyFeatures) -> Tuple[EmotionalTone, Optional[EmotionalTone], float]:
        """Detect emotional tone from features using rule-based approach.

        Returns:
            Tuple of (primary_tone, secondary_tone, confidence)
        """
        # Scores for each emotion based on feature patterns
        scores = {tone: 0.0 for tone in EmotionalTone}

        # High pitch variation + high energy = excited
        if features.pitch_std > features.pitch_mean * 0.2 and features.energy_mean > 0.1:
            scores[EmotionalTone.EXCITED] += 2.0
            scores[EmotionalTone.HAPPY] += 1.0

        # Very low pitch + low energy = sad
        if features.pitch_mean < 150 and features.energy_mean < 0.05:
            scores[EmotionalTone.SAD] += 2.0

        # High pitch + irregular timing = frustrated
        if features.pitch_mean > 200 and features.pause_ratio > 0.3:
            scores[EmotionalTone.FRUSTRATED] += 2.0

        # Very high energy + fast rate + high flux = urgent
        if features.energy_mean > 0.15 and features.speaking_rate > 180 and features.spectral_flux > 10:
            scores[EmotionalTone.URGENT] += 2.5

        # Low energy + low rate + many pauses = confused
        if features.energy_mean < 0.08 and features.pause_ratio > 0.4:
            scores[EmotionalTone.CONFUSED] += 2.0

        # Stable pitch + moderate energy = calm
        if features.pitch_std < features.pitch_mean * 0.1 and 0.03 < features.energy_mean < 0.1:
            scores[EmotionalTone.CALM] += 2.0

        # Find primary and secondary tones
        sorted_tones = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary = sorted_tones[0][0]
        confidence = min(sorted_tones[0][1] / 5.0, 1.0)  # Normalize to 0-1

        secondary = None
        if len(sorted_tones) > 1 and sorted_tones[1][1] > 0.5:
            secondary = sorted_tones[1][0]

        return primary, secondary, confidence

    def _detect_pace(self, features: ProsodyFeatures) -> SpeakingPace:
        """Detect speaking pace."""
        if features.speaking_rate < 100:
            return SpeakingPace.SLOW
        elif features.speaking_rate > 160:
            return SpeakingPace.FAST
        return SpeakingPace.NORMAL

    def _calculate_urgency(self, features: ProsodyFeatures) -> float:
        """Calculate urgency score (0-1)."""
        urgency = 0.0

        # Fast speech indicates urgency
        if features.speaking_rate > 180:
            urgency += 0.3

        # High energy
        if features.energy_mean > 0.12:
            urgency += 0.2

        # High pitch with variation
        if features.pitch_mean > 180 and features.pitch_std > 30:
            urgency += 0.2

        # Many short pauses
        if features.pause_count > 5 and features.pause_ratio < 0.3:
            urgency += 0.2

        # High spectral flux (active speech)
        if features.spectral_flux > 8:
            urgency += 0.1

        return min(urgency, 1.0)

    def _find_runs(self, arr: np.ndarray) -> List[Tuple[int, int]]:
        """Find consecutive runs of True values."""
        if len(arr) == 0:
            return []

        runs = []
        start = None

        for i, val in enumerate(arr):
            if val and start is None:
                start = i
            elif not val and start is not None:
                runs.append((start, i))
                start = None

        if start is not None:
            runs.append((start, len(arr)))

        return runs

    def _estimate_hnr(self, audio_data: np.ndarray) -> float:
        """Estimate harmonic-to-noise ratio."""
        try:
            import librosa

            # Use autocorrelation to estimate periodicity
            r = np.correlate(audio_data, audio_data, mode='full')
            r = r[len(r)//2:]

            # Find first peak after zero
            if len(r) > 1:
                peaks = []
                for i in range(1, len(r) - 1):
                    if r[i] > r[i-1] and r[i] > r[i+1]:
                        peaks.append((i, r[i]))

                if peaks:
                    # HNR approximation
                    peak_idx, peak_val = max(peaks, key=lambda x: x[1])
                    noise_floor = np.mean(r[100:]) if len(r) > 100 else 0.001
                    hnr = 10 * np.log10(peak_val / (noise_floor + 1e-10))
                    return float(np.clip(hnr / 40, 0, 1))  # Normalize

        except Exception:
            pass

        return 0.5  # Default

    def get_trend(self, window: int = 5) -> Optional[EmotionalTone]:
        """Get the trending emotional tone over recent history."""
        if len(self.feature_history) < window:
            return None

        recent = self.feature_history[-window:]
        tones = []

        for feat in recent:
            tone, _, _ = self._detect_emotion(feat)
            tones.append(tone)

        # Most common tone in window
        from collections import Counter
        most_common = Counter(tones).most_common(1)
        return most_common[0][0] if most_common else None

    def clear_history(self):
        """Clear feature history."""
        self.feature_history.clear()


def demo():
    """Demonstrate prosody detection."""
    import tempfile
    import soundfile as sf
    import asyncio

    logging.basicConfig(level=logging.INFO)

    print("Prosody Detector Demo")
    print("-" * 40)

    detector = ProsodyDetector()

    # Create test audio with different characteristics
    sample_rate = 16000
    duration = 2.0
    t = np.linspace(0, duration, int(sample_rate * duration))

    # Test 1: Neutral tone
    print("\n1. Testing neutral tone...")
    signal = np.sin(2 * np.pi * 200 * t) * 0.1
    result = detector.analyze(signal)
    print(f"   Detected: {result.primary_tone.value} (confidence: {result.confidence:.2f})")
    print(f"   Pace: {result.pace.value}, Urgency: {result.urgency_score:.2f}")

    # Test 2: Excited tone (high pitch, high energy)
    print("\n2. Testing excited tone...")
    signal = np.sin(2 * np.pi * (300 + 100 * np.sin(2 * np.pi * 5 * t)) * t) * 0.3
    result = detector.analyze(signal)
    print(f"   Detected: {result.primary_tone.value} (confidence: {result.confidence:.2f})")

    # Test 3: Urgent tone (fast, high energy)
    print("\n3. Testing urgent tone...")
    signal = np.sin(2 * np.pi * 400 * t) * 0.4
    # Add rapid onsets
    for i in range(0, len(t), int(sample_rate * 0.1)):
        if i < len(signal):
            signal[i:i+100] *= 1.5
    result = detector.analyze(signal)
    print(f"   Detected: {result.primary_tone.value} (confidence: {result.confidence:.2f})")
    print(f"   Urgency: {result.urgency_score:.2f}")

    print("\nProsody detector ready!")


if __name__ == "__main__":
    demo()
