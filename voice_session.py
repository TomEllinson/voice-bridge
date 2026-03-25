"""Voice session manager for conversation state across audio/text interactions."""

import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


@dataclass
class VoiceMessage:
    """Represents a voice message in the conversation."""
    role: str  # 'user' or 'assistant'
    text: str  # Transcribed text
    audio_data: Optional[bytes] = None  # Original audio bytes
    timestamp: float = field(default_factory=time.time)
    duration: Optional[float] = None  # Audio duration in seconds
    language: Optional[str] = None


@dataclass
class VoiceSession:
    """Manages conversation state for voice interactions."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    user_id: str = ""
    room_id: str = ""
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    messages: List[VoiceMessage] = field(default_factory=list)
    context_window: int = 10  # Keep last N messages for context
    language: Optional[str] = None  # Detected language
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, text: str, audio_data: Optional[bytes] = None, **kwargs):
        """Add a message to the conversation."""
        message = VoiceMessage(
            role=role,
            text=text,
            audio_data=audio_data,
            timestamp=time.time(),
            **kwargs
        )
        self.messages.append(message)
        self.last_activity = time.time()

        # Trim context window
        if len(self.messages) > self.context_window:
            self.messages = self.messages[-self.context_window:]

        # Update language if detected from user message
        if role == 'user' and kwargs.get('language'):
            self.language = kwargs['language']

    def get_context(self, max_messages: Optional[int] = None) -> List[Dict[str, str]]:
        """Get conversation context as list of role/content pairs.

        Returns:
            List of dicts with 'role' and 'content' keys
        """
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
            'metadata': self.metadata
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
        """Get existing session or create new one.

        Args:
            user_id: User identifier
            room_id: Room/channel identifier
            create_new: Force creation of new session

        Returns:
            VoiceSession instance
        """
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
