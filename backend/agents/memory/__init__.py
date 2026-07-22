"""
Session-level conversation memory.

Maintains context within a single conversation for follow-up questions.
In-memory only (no persistent chat history yet).
"""

import threading
import time
from dataclasses import dataclass, field


@dataclass
class ConversationTurn:
    """A single conversation turn."""

    role: str  # "user" or "assistant"
    content: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }


@dataclass
class ConversationSession:
    """A conversation session with history."""

    session_id: str = ""
    turns: list[ConversationTurn] = field(default_factory=list)
    created_at: float = 0.0
    max_turns: int = 20

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()

    def add_turn(self, role: str, content: str) -> None:
        """Adds a turn to the conversation, evicting oldest if at capacity."""
        self.turns.append(ConversationTurn(role=role, content=content))
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]

    def get_history(self) -> list[dict]:
        """Returns conversation history as a list of dicts."""
        return [turn.to_dict() for turn in self.turns]

    def clear(self) -> None:
        """Clears conversation history."""
        self.turns = []


# Module-level session store (thread-safe, in-memory)
_sessions: dict[str, ConversationSession] = {}
_lock = threading.Lock()

# Sessions expire after 30 minutes of inactivity
SESSION_TTL_SECONDS = 1800


class ConversationMemory:
    """
    In-memory session management for conversations.

    Usage:
        session = ConversationMemory.get_or_create("session-123")
        session.add_turn("user", "What pump is in area 3?")
        session.add_turn("assistant", "P-101A is located in area 3.")
        history = session.get_history()
    """

    @classmethod
    def get_or_create(cls, session_id: str) -> ConversationSession:
        """Gets or creates a conversation session."""
        with _lock:
            cls._cleanup_expired()
            if session_id not in _sessions:
                _sessions[session_id] = ConversationSession(session_id=session_id)
            return _sessions[session_id]

    @classmethod
    def get(cls, session_id: str) -> ConversationSession | None:
        """Gets an existing session, or None."""
        with _lock:
            return _sessions.get(session_id)

    @classmethod
    def delete(cls, session_id: str) -> bool:
        """Deletes a session. Returns True if found."""
        with _lock:
            if session_id in _sessions:
                del _sessions[session_id]
                return True
            return False

    @classmethod
    def _cleanup_expired(cls) -> None:
        """Removes sessions that have been inactive for too long."""
        now = time.time()
        expired = [
            sid for sid, session in _sessions.items()
            if session.turns and (now - session.turns[-1].timestamp) > SESSION_TTL_SECONDS
        ]
        for sid in expired:
            del _sessions[sid]

    @classmethod
    def reset(cls) -> None:
        """Clears all sessions (for testing)."""
        with _lock:
            _sessions.clear()
