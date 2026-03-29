"""Voice activity profiling module for user recognition and personalization.

Analyzes voice characteristics to identify speakers and adapt to individual
speaking patterns over time.
"""

import numpy as np
import logging
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
import hashlib
import time

logger = logging.getLogger(__name__)


@dataclass
class VoiceProfile:
    """Voice profile for a recognized user."""
    profile_id: str
    name: str = "Unknown"
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    # Voice characteristics
    pitch_mean: float = 0.0
    pitch_std: float = 0.0
    energy_mean: float = 0.0
    speaking_rate: float = 0.0
    spectral_centroid_mean: float = 0.0

    # Behavioral patterns
    avg_utterance_length: float = 0.0
    pause_pattern: float = 0.0  # Average pause duration
    vocabulary_fingerprint: str = ""  # Hash of common words

    # History
    sample_count: int = 0
    interaction_count: int = 0
    total_speaking_time: float = 0.0  # seconds

    # Preferences (learned over time)
    preferred_response_length: str = "medium"  # short, medium, long
    preferred_formality: float = 0.5  # 0=casual, 1=formal
    interrupt_frequency: float = 0.0  # How often they interrupt

    def to_dict(self) -> Dict:
        return {
            'profile_id': self.profile_id,
            'name': self.name,
            'created_at': self.created_at,
            'last_seen': self.last_seen,
            'pitch_mean': self.pitch_mean,
            'pitch_std': self.pitch_std,
            'energy_mean': self.energy_mean,
            'speaking_rate': self.speaking_rate,
            'spectral_centroid_mean': self.spectral_centroid_mean,
            'avg_utterance_length': self.avg_utterance_length,
            'pause_pattern': self.pause_pattern,
            'vocabulary_fingerprint': self.vocabulary_fingerprint,
            'sample_count': self.sample_count,
            'interaction_count': self.interaction_count,
            'total_speaking_time': self.total_speaking_time,
            'preferred_response_length': self.preferred_response_length,
            'preferred_formality': self.preferred_formality,
            'interrupt_frequency': self.interrupt_frequency,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "VoiceProfile":
        return cls(
            profile_id=data['profile_id'],
            name=data.get('name', 'Unknown'),
            created_at=data.get('created_at', time.time()),
            last_seen=data.get('last_seen', time.time()),
            pitch_mean=data.get('pitch_mean', 0.0),
            pitch_std=data.get('pitch_std', 0.0),
            energy_mean=data.get('energy_mean', 0.0),
            speaking_rate=data.get('speaking_rate', 0.0),
            spectral_centroid_mean=data.get('spectral_centroid_mean', 0.0),
            avg_utterance_length=data.get('avg_utterance_length', 0.0),
            pause_pattern=data.get('pause_pattern', 0.0),
            vocabulary_fingerprint=data.get('vocabulary_fingerprint', ''),
            sample_count=data.get('sample_count', 0),
            interaction_count=data.get('interaction_count', 0),
            total_speaking_time=data.get('total_speaking_time', 0.0),
            preferred_response_length=data.get('preferred_response_length', 'medium'),
            preferred_formality=data.get('preferred_formality', 0.5),
            interrupt_frequency=data.get('interrupt_frequency', 0.0),
        )


@dataclass
class VoiceFeatures:
    """Extracted voice features from an audio sample."""
    pitch_mean: float = 0.0
    pitch_std: float = 0.0
    energy_mean: float = 0.0
    speaking_rate: float = 0.0
    spectral_centroid: float = 0.0
    duration: float = 0.0
    transcript: str = ""

    def to_vector(self) -> np.ndarray:
        """Convert features to a vector for comparison."""
        return np.array([
            self.pitch_mean,
            self.pitch_std,
            self.energy_mean,
            self.speaking_rate,
            self.spectral_centroid,
        ])


class VoiceProfiler:
    """Profiles voices for user recognition and personalization."""

    def __init__(self, config_path: Optional[str] = None, similarity_threshold: float = 0.85):
        self.profiles: Dict[str, VoiceProfile] = {}
        self.config_path = config_path or os.path.expanduser("~/.voice_bridge/voice_profiles.json")
        self.similarity_threshold = similarity_threshold
        self.current_profile_id: Optional[str] = None
        self._load_profiles()

    def _load_profiles(self):
        """Load profiles from disk."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                    for profile_data in data.get('profiles', []):
                        profile = VoiceProfile.from_dict(profile_data)
                        self.profiles[profile.profile_id] = profile
                logger.info(f"Loaded {len(self.profiles)} voice profiles")
            except Exception as e:
                logger.error(f"Failed to load profiles: {e}")

    def save_profiles(self):
        """Save profiles to disk."""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            data = {
                'profiles': [p.to_dict() for p in self.profiles.values()],
                'saved_at': time.time(),
            }
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved {len(self.profiles)} voice profiles")
        except Exception as e:
            logger.error(f"Failed to save profiles: {e}")

    def extract_features(self, audio_data: np.ndarray, transcript: str = "",
                        sample_rate: int = 16000) -> VoiceFeatures:
        """Extract voice features from audio."""
        features = VoiceFeatures()
        features.duration = len(audio_data) / sample_rate
        features.transcript = transcript

        try:
            import librosa

            # Ensure audio is float
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32) / np.max(np.abs(audio_data) + 1e-10)

            # Pitch features
            try:
                f0, voiced_flag, _ = librosa.pyin(
                    audio_data,
                    fmin=librosa.note_to_hz('C2'),
                    fmax=librosa.note_to_hz('C7'),
                    sr=sample_rate
                )
                voiced_f0 = f0[voiced_flag] if voiced_flag is not None else f0[~np.isnan(f0)]
                if len(voiced_f0) > 0:
                    features.pitch_mean = float(np.nanmean(voiced_f0))
                    features.pitch_std = float(np.nanstd(voiced_f0))
            except Exception:
                pass

            # Energy
            features.energy_mean = float(np.sqrt(np.mean(audio_data ** 2)))

            # Spectral centroid
            spec_cent = librosa.feature.spectral_centroid(y=audio_data, sr=sample_rate)[0]
            features.spectral_centroid = float(np.mean(spec_cent))

            # Speaking rate (rough estimate)
            if transcript:
                word_count = len(transcript.split())
                if features.duration > 0:
                    features.speaking_rate = word_count / (features.duration / 60)

        except ImportError:
            logger.warning("librosa not available, using basic features")
            features.energy_mean = float(np.sqrt(np.mean(audio_data ** 2)))
        except Exception as e:
            logger.error(f"Feature extraction error: {e}")

        return features

    def _compute_similarity(self, features: VoiceFeatures, profile: VoiceProfile) -> float:
        """Compute similarity between features and a profile."""
        # Weighted feature comparison
        weights = {
            'pitch_mean': 0.3,
            'pitch_std': 0.15,
            'energy_mean': 0.2,
            'speaking_rate': 0.2,
            'spectral_centroid': 0.15,
        }

        similarities = []

        # Pitch similarity (relative difference)
        if features.pitch_mean > 0 and profile.pitch_mean > 0:
            pitch_diff = abs(features.pitch_mean - profile.pitch_mean) / max(features.pitch_mean, profile.pitch_mean)
            similarities.append((1.0 - min(pitch_diff, 1.0)) * weights['pitch_mean'])

        # Energy similarity
        if features.energy_mean > 0 and profile.energy_mean > 0:
            energy_diff = abs(features.energy_mean - profile.energy_mean) / max(features.energy_mean, profile.energy_mean)
            similarities.append((1.0 - min(energy_diff, 1.0)) * weights['energy_mean'])

        # Speaking rate similarity
        if features.speaking_rate > 0 and profile.speaking_rate > 0:
            rate_diff = abs(features.speaking_rate - profile.speaking_rate) / max(features.speaking_rate, profile.speaking_rate)
            similarities.append((1.0 - min(rate_diff, 1.0)) * weights['speaking_rate'])

        if not similarities:
            return 0.0

        return sum(similarities) / sum(weights[k] for k in ['pitch_mean', 'energy_mean', 'speaking_rate'])

    def identify_speaker(self, features: VoiceFeatures) -> Tuple[Optional[str], float]:
        """Identify which profile matches the given features.

        Returns:
            Tuple of (profile_id, confidence) or (None, 0.0) if no match
        """
        if not self.profiles:
            return None, 0.0

        best_match = None
        best_score = 0.0

        for profile_id, profile in self.profiles.items():
            similarity = self._compute_similarity(features, profile)
            if similarity > best_score:
                best_score = similarity
                best_match = profile_id

        if best_score >= self.similarity_threshold:
            logger.debug(f"Matched speaker {best_match} with confidence {best_score:.2f}")
            return best_match, best_score

        return None, best_score

    def create_profile(self, name: str, features: VoiceFeatures) -> VoiceProfile:
        """Create a new voice profile from features."""
        # Generate profile ID from name + timestamp hash
        profile_id = hashlib.md5(
            f"{name}_{time.time()}".encode()
        ).hexdigest()[:12]

        profile = VoiceProfile(
            profile_id=profile_id,
            name=name,
            pitch_mean=features.pitch_mean,
            pitch_std=features.pitch_std,
            energy_mean=features.energy_mean,
            speaking_rate=features.speaking_rate,
            spectral_centroid_mean=features.spectral_centroid,
            sample_count=1,
            total_speaking_time=features.duration,
        )

        self.profiles[profile_id] = profile
        self.current_profile_id = profile_id
        self.save_profiles()

        logger.info(f"Created voice profile for {name}")
        return profile

    def update_profile(self, profile_id: str, features: VoiceFeatures):
        """Update an existing profile with new features."""
        if profile_id not in self.profiles:
            return

        profile = self.profiles[profile_id]
        n = profile.sample_count

        # Rolling average update
        if n > 0:
            profile.pitch_mean = (profile.pitch_mean * n + features.pitch_mean) / (n + 1)
            profile.pitch_std = (profile.pitch_std * n + features.pitch_std) / (n + 1)
            profile.energy_mean = (profile.energy_mean * n + features.energy_mean) / (n + 1)
            profile.speaking_rate = (profile.speaking_rate * n + features.speaking_rate) / (n + 1)
            profile.spectral_centroid_mean = (profile.spectral_centroid_mean * n + features.spectral_centroid) / (n + 1)
        else:
            profile.pitch_mean = features.pitch_mean
            profile.pitch_std = features.pitch_std
            profile.energy_mean = features.energy_mean
            profile.speaking_rate = features.speaking_rate
            profile.spectral_centroid_mean = features.spectral_centroid

        profile.sample_count += 1
        profile.last_seen = time.time()
        profile.total_speaking_time += features.duration

        self.save_profiles()

    def process_utterance(self, audio_data: np.ndarray, transcript: str = "",
                         sample_rate: int = 16000) -> Tuple[Optional[str], float]:
        """Process an utterance and identify/update the speaker.

        Returns:
            Tuple of (profile_id, confidence)
        """
        features = self.extract_features(audio_data, transcript, sample_rate)

        # Try to identify existing speaker
        profile_id, confidence = self.identify_speaker(features)

        if profile_id:
            self.update_profile(profile_id, features)
            self.current_profile_id = profile_id
        else:
            # Could be a new speaker, but don't auto-create (require explicit registration)
            logger.debug("No matching voice profile found")

        return profile_id, confidence

    def register_speaker(self, name: str, audio_samples: List[np.ndarray],
                        transcripts: List[str] = None) -> VoiceProfile:
        """Register a new speaker with multiple samples."""
        if transcripts is None:
            transcripts = [""] * len(audio_samples)

        # Extract features from all samples and average
        all_features = []
        for audio, transcript in zip(audio_samples, transcripts):
            features = self.extract_features(audio, transcript)
            all_features.append(features)

        # Average features
        avg_features = VoiceFeatures()
        if all_features:
            for attr in ['pitch_mean', 'pitch_std', 'energy_mean', 'speaking_rate', 'spectral_centroid']:
                values = [getattr(f, attr) for f in all_features if getattr(f, attr) > 0]
                if values:
                    setattr(avg_features, attr, sum(values) / len(values))

        # Create profile
        return self.create_profile(name, avg_features)

    def get_current_profile(self) -> Optional[VoiceProfile]:
        """Get the currently identified profile."""
        if self.current_profile_id and self.current_profile_id in self.profiles:
            return self.profiles[self.current_profile_id]
        return None

    def update_preferences(self, profile_id: str, **kwargs):
        """Update user preferences for a profile."""
        if profile_id not in self.profiles:
            return

        profile = self.profiles[profile_id]

        if 'response_length' in kwargs:
            profile.preferred_response_length = kwargs['response_length']
        if 'formality' in kwargs:
            profile.preferred_formality = kwargs['formality']
        if 'interrupt_frequency' in kwargs:
            profile.interrupt_frequency = kwargs['interrupt_frequency']

        self.save_profiles()

    def get_adaptation_params(self, profile_id: Optional[str] = None) -> Dict:
        """Get parameters to adapt responses for a specific user."""
        pid = profile_id or self.current_profile_id
        if not pid or pid not in self.profiles:
            return {
                'response_length': 'medium',
                'formality': 0.5,
                'interrupt_tolerance': 0.5,
            }

        profile = self.profiles[pid]
        return {
            'response_length': profile.preferred_response_length,
            'formality': profile.preferred_formality,
            'interrupt_tolerance': profile.interrupt_frequency,
            'profile_name': profile.name,
        }

    def list_profiles(self) -> List[Dict]:
        """List all registered profiles."""
        return [
            {
                'id': pid,
                'name': p.name,
                'samples': p.sample_count,
                'last_seen': p.last_seen,
                'is_current': pid == self.current_profile_id,
            }
            for pid, p in self.profiles.items()
        ]

    def delete_profile(self, profile_id: str) -> bool:
        """Delete a voice profile."""
        if profile_id in self.profiles:
            del self.profiles[profile_id]
            if self.current_profile_id == profile_id:
                self.current_profile_id = None
            self.save_profiles()
            return True
        return False


def demo():
    """Demonstrate voice profiling."""
    import tempfile
    import soundfile as sf

    logging.basicConfig(level=logging.INFO)

    print("Voice Profiler Demo")
    print("-" * 40)

    profiler = VoiceProfiler()

    # Create synthetic voice samples
    sample_rate = 16000
    duration = 2.0
    t = np.linspace(0, duration, int(sample_rate * duration))

    # Simulate "Speaker 1" - lower pitch
    print("\n1. Creating profile for 'Alice' (lower pitch)...")
    voice1 = np.sin(2 * np.pi * 180 * t) * 0.3
    voice1 += np.random.randn(len(t)) * 0.05
    profile1 = profiler.register_speaker("Alice", [voice1])
    print(f"   Profile created: {profile1.profile_id}")

    # Simulate "Speaker 2" - higher pitch
    print("\n2. Creating profile for 'Bob' (higher pitch)...")
    voice2 = np.sin(2 * np.pi * 280 * t) * 0.25
    voice2 += np.random.randn(len(t)) * 0.05
    profile2 = profiler.register_speaker("Bob", [voice2])
    print(f"   Profile created: {profile2.profile_id}")

    # Test identification
    print("\n3. Testing speaker identification...")

    # Test with similar voice to Alice
    test_voice1 = np.sin(2 * np.pi * 185 * t) * 0.28
    test_voice1 += np.random.randn(len(t)) * 0.04
    features1 = profiler.extract_features(test_voice1)
    pid1, conf1 = profiler.identify_speaker(features1)
    print(f"   Alice-like voice -> {profiler.profiles.get(pid1, VoiceProfile('none')).name if pid1 else 'Unknown'} (confidence: {conf1:.2f})")

    # Test with similar voice to Bob
    test_voice2 = np.sin(2 * np.pi * 275 * t) * 0.26
    test_voice2 += np.random.randn(len(t)) * 0.04
    features2 = profiler.extract_features(test_voice2)
    pid2, conf2 = profiler.identify_speaker(features2)
    print(f"   Bob-like voice -> {profiler.profiles.get(pid2, VoiceProfile('none')).name if pid2 else 'Unknown'} (confidence: {conf2:.2f})")

    # List profiles
    print("\n4. Registered profiles:")
    for p in profiler.list_profiles():
        print(f"   - {p['name']}: {p['samples']} samples")

    print("\nVoice profiler ready!")


if __name__ == "__main__":
    demo()
