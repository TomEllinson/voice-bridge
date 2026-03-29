"""Voice persona system for managing multiple TTS voices and personalities.

Provides different voice personas with distinct characteristics for various
conversation contexts (professional, friendly, assistant, etc.).
"""

import logging
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum
import json
import os

logger = logging.getLogger(__name__)


class PersonaType(Enum):
    """Types of voice personas available."""
    ASSISTANT = "assistant"      # Default helpful assistant
    PROFESSIONAL = "professional"  # Formal, business-like
    FRIENDLY = "friendly"       # Warm, casual
    CONCISE = "concise"         # Brief, to-the-point
    EMPATHETIC = "empathetic"   # Understanding, supportive
    ENERGETIC = "energetic"     # Enthusiastic, upbeat


@dataclass
class VoiceSettings:
    """TTS voice settings for a persona."""
    engine: str = "kokoro"      # kokoro, piper, etc.
    voice_id: str = "af_bella"  # Voice identifier
    speed: float = 1.0          # Speech rate
    pitch: float = 1.0          # Pitch modifier
    volume: float = 1.0         # Volume modifier

    def to_dict(self) -> Dict:
        return {
            'engine': self.engine,
            'voice_id': self.voice_id,
            'speed': self.speed,
            'pitch': self.pitch,
            'volume': self.volume,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "VoiceSettings":
        return cls(
            engine=data.get('engine', 'kokoro'),
            voice_id=data.get('voice_id', 'af_bella'),
            speed=data.get('speed', 1.0),
            pitch=data.get('pitch', 1.0),
            volume=data.get('volume', 1.0),
        )


@dataclass
class ResponseStyle:
    """Response style configuration for a persona."""
    # Length preferences
    preferred_length: str = "medium"  # short, medium, long
    max_words: int = 150
    greeting_style: str = "casual"    # formal, casual, none

    # Language patterns
    use_emojis: bool = False
    use_contractions: bool = True
    technical_level: str = "medium"   # low, medium, high

    # Turn-taking behavior
    allow_interruptions: bool = True
    pause_between_sentences: float = 0.5  # seconds

    # Context awareness
    remember_preferences: bool = True
    proactive_suggestions: bool = False

    def to_dict(self) -> Dict:
        return {
            'preferred_length': self.preferred_length,
            'max_words': self.max_words,
            'greeting_style': self.greeting_style,
            'use_emojis': self.use_emojis,
            'use_contractions': self.use_contractions,
            'technical_level': self.technical_level,
            'allow_interruptions': self.allow_interruptions,
            'pause_between_sentences': self.pause_between_sentences,
            'remember_preferences': self.remember_preferences,
            'proactive_suggestions': self.proactive_suggestions,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ResponseStyle":
        return cls(
            preferred_length=data.get('preferred_length', 'medium'),
            max_words=data.get('max_words', 150),
            greeting_style=data.get('greeting_style', 'casual'),
            use_emojis=data.get('use_emojis', False),
            use_contractions=data.get('use_contractions', True),
            technical_level=data.get('technical_level', 'medium'),
            allow_interruptions=data.get('allow_interruptions', True),
            pause_between_sentences=data.get('pause_between_sentences', 0.5),
            remember_preferences=data.get('remember_preferences', True),
            proactive_suggestions=data.get('proactive_suggestions', False),
        )


@dataclass
class VoicePersona:
    """Complete voice persona configuration."""
    persona_id: str
    name: str
    description: str
    type: PersonaType
    voice_settings: VoiceSettings = field(default_factory=VoiceSettings)
    response_style: ResponseStyle = field(default_factory=ResponseStyle)
    system_prompt: str = ""
    greeting_phrases: List[str] = field(default_factory=list)
    sample_responses: Dict[str, str] = field(default_factory=dict)
    is_active: bool = True

    def to_dict(self) -> Dict:
        return {
            'persona_id': self.persona_id,
            'name': self.name,
            'description': self.description,
            'type': self.type.value,
            'voice_settings': self.voice_settings.to_dict(),
            'response_style': self.response_style.to_dict(),
            'system_prompt': self.system_prompt,
            'greeting_phrases': self.greeting_phrases,
            'sample_responses': self.sample_responses,
            'is_active': self.is_active,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "VoicePersona":
        return cls(
            persona_id=data['persona_id'],
            name=data['name'],
            description=data['description'],
            type=PersonaType(data['type']),
            voice_settings=VoiceSettings.from_dict(data.get('voice_settings', {})),
            response_style=ResponseStyle.from_dict(data.get('response_style', {})),
            system_prompt=data.get('system_prompt', ''),
            greeting_phrases=data.get('greeting_phrases', []),
            sample_responses=data.get('sample_responses', {}),
            is_active=data.get('is_active', True),
        )


class VoicePersonaManager:
    """Manages multiple voice personas and provides selection logic."""

    # Available Kokoro voices
    KOKORO_VOICES = [
        "af_bella",    # American female
        "af_sarah",    # American female
        "am_adam",     # American male
        "am_michael",  # American male
        "bf_emma",     # British female
        "bf_isabella", # British female
        "bm_george",   # British male
        "bm_lewis",    # British male
    ]

    def __init__(self, config_path: Optional[str] = None):
        self.personas: Dict[str, VoicePersona] = {}
        self.active_persona_id: Optional[str] = None
        self.config_path = config_path or os.path.expanduser("~/.voice_bridge/personas.json")
        self._create_default_personas()
        self._load_personas()

    def _create_default_personas(self):
        """Create default voice personas."""
        # Default Assistant
        assistant = VoicePersona(
            persona_id="default_assistant",
            name="Assistant",
            description="A helpful, general-purpose assistant",
            type=PersonaType.ASSISTANT,
            voice_settings=VoiceSettings(
                engine="kokoro",
                voice_id="af_bella",
                speed=1.0,
                pitch=1.0,
            ),
            response_style=ResponseStyle(
                preferred_length="medium",
                max_words=150,
                greeting_style="casual",
                use_contractions=True,
            ),
            system_prompt=(
                "You are a helpful voice assistant. Keep responses concise "
                "and natural for voice conversations. Avoid long lists or "
                "complex formatting."
            ),
            greeting_phrases=[
                "Hello! How can I help you today?",
                "Hi there! What can I do for you?",
                "Hey! I'm ready to help.",
            ],
        )
        self.personas[assistant.persona_id] = assistant

        # Professional
        professional = VoicePersona(
            persona_id="professional",
            name="Professional",
            description="Formal, business-oriented voice",
            type=PersonaType.PROFESSIONAL,
            voice_settings=VoiceSettings(
                engine="kokoro",
                voice_id="bm_george",
                speed=0.95,
                pitch=1.0,
            ),
            response_style=ResponseStyle(
                preferred_length="medium",
                max_words=120,
                greeting_style="formal",
                use_contractions=False,
                technical_level="high",
            ),
            system_prompt=(
                "You are a professional assistant. Use formal language, "
                "avoid contractions, and maintain a respectful tone. "
                "Be precise and thorough."
            ),
            greeting_phrases=[
                "Good day. How may I assist you?",
                "Hello. I'm ready to help with your inquiry.",
            ],
        )
        self.personas[professional.persona_id] = professional

        # Friendly
        friendly = VoicePersona(
            persona_id="friendly",
            name="Friendly",
            description="Warm, casual, and conversational",
            type=PersonaType.FRIENDLY,
            voice_settings=VoiceSettings(
                engine="kokoro",
                voice_id="af_sarah",
                speed=1.05,
                pitch=1.02,
            ),
            response_style=ResponseStyle(
                preferred_length="medium",
                max_words=150,
                greeting_style="casual",
                use_contractions=True,
                proactive_suggestions=True,
            ),
            system_prompt=(
                "You are a friendly conversational partner. Be warm, use "
                "contractions, and engage naturally. Feel free to be "
                "enthusiastic and supportive."
            ),
            greeting_phrases=[
                "Hey there! What's on your mind?",
                "Hi! Great to hear from you. What's up?",
                "Hello! How's it going?",
            ],
        )
        self.personas[friendly.persona_id] = friendly

        # Concise
        concise = VoicePersona(
            persona_id="concise",
            name="Concise",
            description="Brief and to-the-point responses",
            type=PersonaType.CONCISE,
            voice_settings=VoiceSettings(
                engine="kokoro",
                voice_id="am_michael",
                speed=1.1,
                pitch=1.0,
            ),
            response_style=ResponseStyle(
                preferred_length="short",
                max_words=50,
                greeting_style="none",
                use_contractions=True,
            ),
            system_prompt=(
                "You are a direct, efficient assistant. Give brief, "
                "factual answers. Minimize filler words and get straight "
                "to the point."
            ),
            greeting_phrases=[
                "Ready.",
                "Go ahead.",
            ],
        )
        self.personas[concise.persona_id] = concise

        # Empathetic
        empathetic = VoicePersona(
            persona_id="empathetic",
            name="Empathetic",
            description="Supportive and understanding",
            type=PersonaType.EMPATHETIC,
            voice_settings=VoiceSettings(
                engine="kokoro",
                voice_id="bf_emma",
                speed=0.95,
                pitch=0.98,
            ),
            response_style=ResponseStyle(
                preferred_length="medium",
                max_words=150,
                greeting_style="casual",
                use_contractions=True,
            ),
            system_prompt=(
                "You are a supportive, empathetic assistant. Show understanding "
                "and compassion. Use a gentle, reassuring tone. Validate "
                "feelings when appropriate."
            ),
            greeting_phrases=[
                "Hi there. I'm here for you. What's on your mind?",
                "Hello. I'm listening. How can I support you today?",
            ],
        )
        self.personas[empathetic.persona_id] = empathetic

        # Energetic
        energetic = VoicePersona(
            persona_id="energetic",
            name="Energetic",
            description="Enthusiastic and upbeat",
            type=PersonaType.ENERGETIC,
            voice_settings=VoiceSettings(
                engine="kokoro",
                voice_id="am_adam",
                speed=1.1,
                pitch=1.05,
            ),
            response_style=ResponseStyle(
                preferred_length="medium",
                max_words=150,
                greeting_style="casual",
                use_contractions=True,
                proactive_suggestions=True,
            ),
            system_prompt=(
                "You are an enthusiastic, energetic assistant. Be upbeat and "
                "positive. Show excitement about helping. Use enthusiastic "
                "language while staying helpful."
            ),
            greeting_phrases=[
                "Hey! Awesome to hear from you! What are we doing today?",
                "Hi there! Ready to rock! What's up?",
                "Hello! Great day to be productive! What can I help with?",
            ],
        )
        self.personas[energetic.persona_id] = energetic

        # Set default active persona
        self.active_persona_id = "default_assistant"

    def _load_personas(self):
        """Load custom personas from config file."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                    for persona_data in data.get('personas', []):
                        persona = VoicePersona.from_dict(persona_data)
                        self.personas[persona.persona_id] = persona
                    self.active_persona_id = data.get('active_persona', self.active_persona_id)
                logger.info(f"Loaded {len(data.get('personas', []))} custom personas")
            except Exception as e:
                logger.error(f"Failed to load personas: {e}")

    def save_personas(self):
        """Save personas to config file."""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            data = {
                'personas': [p.to_dict() for p in self.personas.values()],
                'active_persona': self.active_persona_id,
            }
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved {len(self.personas)} personas")
        except Exception as e:
            logger.error(f"Failed to save personas: {e}")

    def get_persona(self, persona_id: Optional[str] = None) -> VoicePersona:
        """Get a persona by ID or the active persona."""
        pid = persona_id or self.active_persona_id
        if pid in self.personas:
            return self.personas[pid]
        return self.personas.get("default_assistant", list(self.personas.values())[0])

    def get_active_persona(self) -> VoicePersona:
        """Get the currently active persona."""
        return self.get_persona(self.active_persona_id)

    def set_active_persona(self, persona_id: str) -> bool:
        """Set the active persona."""
        if persona_id in self.personas:
            self.active_persona_id = persona_id
            logger.info(f"Switched to persona: {self.personas[persona_id].name}")
            return True
        logger.warning(f"Persona not found: {persona_id}")
        return False

    def list_personas(self) -> List[Dict]:
        """List all available personas."""
        return [
            {
                'id': pid,
                'name': p.name,
                'description': p.description,
                'type': p.type.value,
                'is_active': pid == self.active_persona_id,
            }
            for pid, p in self.personas.items()
        ]

    def create_persona(self, name: str, description: str, voice_id: str,
                      persona_type: PersonaType = PersonaType.ASSISTANT,
                      **kwargs) -> VoicePersona:
        """Create a new custom persona."""
        persona_id = f"custom_{name.lower().replace(' ', '_')}"

        # Avoid duplicates
        counter = 1
        base_id = persona_id
        while persona_id in self.personas:
            persona_id = f"{base_id}_{counter}"
            counter += 1

        persona = VoicePersona(
            persona_id=persona_id,
            name=name,
            description=description,
            type=persona_type,
            voice_settings=VoiceSettings(
                voice_id=voice_id,
                **{k: v for k, v in kwargs.items() if k in ['engine', 'speed', 'pitch', 'volume']}
            ),
            response_style=ResponseStyle(
                **{k: v for k, v in kwargs.items() if k in [
                    'preferred_length', 'max_words', 'greeting_style',
                    'use_emojis', 'use_contractions', 'technical_level',
                    'allow_interruptions', 'proactive_suggestions'
                ]}
            ),
            system_prompt=kwargs.get('system_prompt', ''),
        )

        self.personas[persona_id] = persona
        self.save_personas()
        return persona

    def delete_persona(self, persona_id: str) -> bool:
        """Delete a custom persona."""
        if persona_id in self.personas and persona_id.startswith("custom_"):
            del self.personas[persona_id]
            if self.active_persona_id == persona_id:
                self.active_persona_id = "default_assistant"
            self.save_personas()
            return True
        return False

    def select_persona_for_context(self, context: Dict) -> str:
        """Intelligently select a persona based on conversation context.

        Args:
            context: Dict with keys like 'urgency', 'formality', 'emotional_tone'

        Returns:
            persona_id for the best matching persona
        """
        urgency = context.get('urgency', 0.0)
        formality = context.get('formality', 0.5)
        emotional_tone = context.get('emotional_tone', 'neutral')

        # High urgency -> Concise
        if urgency > 0.7:
            return "concise"

        # Formal context -> Professional
        if formality > 0.7:
            return "professional"

        # Emotional context -> Empathetic
        if emotional_tone in ['frustrated', 'sad', 'confused']:
            return "empathetic"

        # Excited context -> Energetic
        if emotional_tone == 'excited':
            return "energetic"

        # Return current active or default
        return self.active_persona_id or "default_assistant"


def demo():
    """Demonstrate voice persona system."""
    logging.basicConfig(level=logging.INFO)

    print("Voice Persona System Demo")
    print("-" * 40)

    manager = VoicePersonaManager()

    # List available personas
    print("\nAvailable personas:")
    for p in manager.list_personas():
        status = " (active)" if p['is_active'] else ""
        print(f"  - {p['name']}: {p['description']}{status}")

    # Get active persona
    active = manager.get_active_persona()
    print(f"\nActive persona: {active.name}")
    print(f"  Voice: {active.voice_settings.voice_id}")
    print(f"  Speed: {active.voice_settings.speed}")
    print(f"  Max words: {active.response_style.max_words}")

    # Switch personas
    print("\nSwitching to Professional persona...")
    manager.set_active_persona("professional")
    active = manager.get_active_persona()
    print(f"  System prompt: {active.system_prompt[:50]}...")

    # Context-based selection
    print("\nContext-based selection:")
    contexts = [
        {'urgency': 0.8, 'formality': 0.3},
        {'urgency': 0.2, 'formality': 0.8},
        {'emotional_tone': 'frustrated'},
        {'emotional_tone': 'excited'},
    ]
    for ctx in contexts:
        pid = manager.select_persona_for_context(ctx)
        print(f"  {ctx} -> {manager.get_persona(pid).name}")

    print("\nVoice persona system ready!")


if __name__ == "__main__":
    demo()
