"""Voice session manager for conversation state across audio/text interactions.

Optimized for voice context with features like:
- Audio-aware context prioritization
- Turn-taking memory
- User preference tracking
- Voice-specific metadata
"""

import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set
from datetime import datetime
from enum import Enum
import uuid

logger = logging.getLogger(__name__)


class MessagePriority(Enum):
    """Priority levels for voice messages in context."""
    CRITICAL = 4     # Interrupts, corrections
    HIGH = 3         # Direct questions, commands
    NORMAL = 2       # Standard responses
    LOW = 1          # Background info
    FILLER = 0       # Acknowledgments, ums


@dataclass
class VoiceMessage:
    """Represents a voice message in the conversation."""
    role: str  # 'user' or 'assistant'
    text: str  # Transcribed text
    audio_data: Optional[bytes] = None  # Original audio bytes
    timestamp: float = field(default_factory=time.time)
    duration: Optional[float] = None  # Audio duration in seconds
    language: Optional[str] = None
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # Voice context features
    priority: MessagePriority = MessagePriority.NORMAL
    was_interrupted: bool = False  # If this message was interrupted
    interruption_point: Optional[float] = None  # Seconds into audio where interrupted
    prosody: Optional[Dict] = None  # Emotional tone data
    speaking_pace: Optional[str] = None  # 'slow', 'normal', 'fast'
    confidence: float = 1.0  # Transcription confidence

    # Context flags
    requires_follow_up: bool = False  # If assistant needs to follow up
    is_follow_up: bool = False  # If this message follows up on previous
    references_message: Optional[str] = None  # ID of referenced message

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'role': self.role,
            'text': self.text,
            'timestamp': self.timestamp,
            'duration': self.duration,
            'language': self.language,
            'was_interrupted': self.was_interrupted,
            'prosody': self.prosody,
            'speaking_pace': self.speaking_pace,
            'confidence': self.confidence,
            'priority': self.priority.value,
            'requires_follow_up': self.requires_follow_up,
            'is_follow_up': self.is_follow_up,
        }


@dataclass
class VoiceSession:
    """Manages conversation state for voice interactions with memory optimization."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    user_id: str = ""
    room_id: str = ""
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    messages: List[VoiceMessage] = field(default_factory=list)
    context_window: int = 10  # Keep last N messages for context
    language: Optional[str] = None  # Detected language
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Voice context features
    turn_count: int = 0
    current_speaker: str = "none"  # 'user', 'assistant', 'none'
    user_speaking_time: float = 0.0  # Total user speaking time
    assistant_speaking_time: float = 0.0  # Total assistant speaking time
    interruption_count: int = 0

    # Memory optimization
    message_topics: Set[str] = field(default_factory=set)
    unresolved_questions: List[str] = field(default_factory=list)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    preferred_response_length: str = "medium"  # 'short', 'medium', 'long'
    user_formality_level: float = 0.5  # 0=casual, 1=formal

    def add_message(self, role: str, text: str, audio_data: Optional[bytes] = None, **kwargs):
        """Add a message to the conversation with voice context."""
        message = VoiceMessage(
            role=role,
            text=text,
            audio_data=audio_data,
            timestamp=time.time(),
            **kwargs
        )
        self.messages.append(message)
        self.last_activity = time.time()

        # Update turn tracking
        if role == 'user':
            if self.current_speaker != 'user':
                self.turn_count += 1
            self.current_speaker = 'user'
            if kwargs.get('duration'):
                self.user_speaking_time += kwargs['duration']
        else:
            self.current_speaker = 'assistant'
            if kwargs.get('duration'):
                self.assistant_speaking_time += kwargs['duration']

        # Track interruptions
        if kwargs.get('was_interrupted'):
            self.interruption_count += 1

        # Update topics from message (simple keyword extraction)
        self._extract_topics(text)

        # Trim context window but preserve critical messages
        self._optimize_context()

        # Update language if detected
        if role == 'user' and kwargs.get('language'):
            self.language = kwargs['language']

    def _extract_topics(self, text: str):
        """Extract and track conversation topics."""
        # Simple topic extraction - could be enhanced with NLP
        keywords = [
            'schedule', 'meeting', 'reminder', 'task',
            'weather', 'news', 'email', 'message',
            'music', 'call', 'direction', 'time',
            'question', 'help', 'error', 'problem'
        ]
        text_lower = text.lower()
        for keyword in keywords:
            if keyword in text_lower:
                self.message_topics.add(keyword)

    def _optimize_context(self):
        """Optimize context window for voice conversations.

        Strategy:
        1. Always keep critical and high priority messages
        2. Keep recent messages within window
        3. Summarize older messages if needed
        """
        if len(self.messages) <= self.context_window:
            return

        # Count non-critical messages
        critical_messages = [m for m in self.messages
                            if m.priority in [MessagePriority.CRITICAL, MessagePriority.HIGH]]
        other_messages = [m for m in self.messages
                         if m.priority not in [MessagePriority.CRITICAL, MessagePriority.HIGH]]

        # Keep critical messages and recent non-critical ones
        if len(critical_messages) >= self.context_window:
            # Too many critical messages, keep only the most recent
            self.messages = self.messages[-self.context_window:]
        else:
            # Keep critical + recent others
            keep_count = self.context_window - len(critical_messages)
            self.messages = critical_messages + other_messages[-keep_count:]

        # Sort by timestamp to maintain order
        self.messages.sort(key=lambda m: m.timestamp)

    def mark_interrupted(self, message_id: str, interruption_point: float):
        """Mark a message as interrupted."""
        for msg in self.messages:
            if msg.message_id == message_id:
                msg.was_interrupted = True
                msg.interruption_point = interruption_point
                msg.priority = MessagePriority.CRITICAL
                self.interruption_count += 1
                break

    def set_follow_up_required(self, question: str):
        """Track that a follow-up is required."""
        self.unresolved_questions.append(question)

    def resolve_follow_up(self, question: str):
        """Mark a follow-up as resolved."""
        if question in self.unresolved_questions:
            self.unresolved_questions.remove(question)

    def get_voice_optimized_context(self, max_messages: Optional[int] = None) -> List[Dict[str, str]]:
        """Get conversation context optimized for voice interactions.

        Prioritizes:
        1. Uninterrupted complete exchanges
        2. Recent messages
        3. Messages with high confidence
        4. Messages matching current topic
        """
        limit = max_messages or self.context_window

        # Sort by priority then by recency
        def message_priority(msg: VoiceMessage):
            base_score = msg.priority.value * 100
            # Boost recent messages
            recency_boost = min((time.time() - msg.timestamp) / 3600, 1) * 10
            # Penalize interrupted messages (may be incomplete)
            if msg.was_interrupted:
                base_score -= 50
            # Boost high confidence
            confidence_boost = msg.confidence * 5
            return base_score - recency_boost + confidence_boost

        sorted_messages = sorted(self.messages, key=message_priority, reverse=True)
        selected = sorted_messages[:limit]

        # Sort back by timestamp
        selected.sort(key=lambda m: m.timestamp)

        context = []
        for msg in selected:
            content = msg.text
            if msg.was_interrupted:
                content = f"[Interrupted] {content}"
            context.append({
                'role': msg.role,
                'content': content,
                'priority': msg.priority.name if msg.priority != MessagePriority.NORMAL else None
            })

        return context

    def get_unresolved_context(self) -> List[str]:
        """Get list of unresolved questions/topics."""
        return self.unresolved_questions.copy()

    def update_user_preference(self, key: str, value: Any):
        """Track a user preference."""
        self.user_preferences[key] = {
            'value': value,
            'timestamp': time.time(),
            'confirmed': True
        }
        # Update derived preferences
        if key == 'response_length':
            self.preferred_response_length = value
        elif key == 'formality':
            self.user_formality_level = value

    def get_user_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference."""
        pref = self.user_preferences.get(key)
        return pref['value'] if pref else default

    def get_voice_stats(self) -> Dict[str, Any]:
        """Get voice conversation statistics."""
        return {
            'turn_count': self.turn_count,
            'user_speaking_time': round(self.user_speaking_time, 2),
            'assistant_speaking_time': round(self.assistant_speaking_time, 2),
            'interruption_count': self.interruption_count,
            'interruption_rate': round(self.interruption_count / max(self.turn_count, 1), 2),
            'topics': list(self.message_topics),
            'unresolved_questions': self.unresolved_questions,
        }

    def get_context(self, max_messages: Optional[int] = None) -> List[Dict[str, str]]:
        """Get conversation context as list of role/content pairs."""
        limit = max_messages or self.context_window
        messages = self.messages[-limit:]

        return [
            {'role': msg.role, 'content': msg.text}
            for msg in messages
        ]

    def get_last_n(self, n: int = 1) -> List[VoiceMessage]:
        """Get last N messages."""
        return self.messages[-n:] if self.messages else []

    def is_expired(self, timeout_seconds: float = 3600) -> bool:
        """Check if session has expired due to inactivity."""
        return (time.time() - self.last_activity) > timeout_seconds

    def clear(self):
        """Clear all messages but keep session metadata."""
        self.messages = []
        self.last_activity = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dict."""
        return {
            'session_id': self.session_id,
            'user_id': self.user_id,
            'room_id': self.room_id,
            'created_at': self.created_at,
            'last_activity': self.last_activity,
            'message_count': len(self.messages),
            'language': self.language,
            'metadata': self.metadata,
            'turn_count': self.turn_count,
            'interruption_count': self.interruption_count,
            'topics': list(self.message_topics),
        }


class SessionManager:
    """Manages multiple voice sessions."""

    def __init__(self, session_timeout: float = 3600):
        """Initialize session manager.

        Args:
            session_timeout: Seconds before session expires
        """
        self.sessions: Dict[str, VoiceSession] = {}
        self.user_room_map: Dict[tuple, str] = {}  # (user_id, room_id) -> session_id
        self.session_timeout = session_timeout

    def get_or_create_session(
        self,
        user_id: str,
        room_id: str,
        create_new: bool = False
    ) -> VoiceSession:
        """Get existing session or create new one."""
        key = (user_id, room_id)

        if not create_new and key in self.user_room_map:
            session_id = self.user_room_map[key]
            if session_id in self.sessions:
                session = self.sessions[session_id]
                if not session.is_expired(self.session_timeout):
                    session.last_activity = time.time()
                    return session
                else:
                    # Session expired, remove it
                    del self.sessions[session_id]

        # Create new session
        session = VoiceSession(user_id=user_id, room_id=room_id)
        self.sessions[session.session_id] = session
        self.user_room_map[key] = session.session_id

        logger.info(f"Created new session {session.session_id} for {user_id} in {room_id}")
        return session

    def get_session(self, session_id: str) -> Optional[VoiceSession]:
        """Get session by ID."""
        session = self.sessions.get(session_id)
        if session and session.is_expired(self.session_timeout):
            self.cleanup_session(session_id)
            return None
        return session

    def cleanup_session(self, session_id: str):
        """Remove a session."""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            key = (session.user_id, session.room_id)
            if key in self.user_room_map:
                del self.user_room_map[key]
            del self.sessions[session_id]
            logger.info(f"Cleaned up session {session_id}")

    def cleanup_expired(self):
        """Remove all expired sessions."""
        expired_ids = [
            sid for sid, session in self.sessions.items()
            if session.is_expired(self.session_timeout)
        ]
        for sid in expired_ids:
            self.cleanup_session(sid)
        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired sessions")

    def get_stats(self) -> Dict[str, Any]:
        """Get session manager statistics."""
        self.cleanup_expired()
        return {
            'active_sessions': len(self.sessions),
            'session_timeout': self.session_timeout,
            'total_mapped': len(self.user_room_map)
        }
