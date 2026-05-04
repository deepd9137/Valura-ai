"""
In-memory session store.

Maps session_id → deque of prior user turns (oldest first, capped at max_turns).
Resets on process restart — acceptable for this assignment; document in README.
"""
from collections import deque
from typing import Dict, List

from src.settings import Settings

_settings = Settings()


class SessionStore:
    def __init__(self, max_turns: int = _settings.session_max_turns) -> None:
        self._max_turns = max_turns
        self._store: Dict[str, deque] = {}

    def append(self, session_id: str, turn: str) -> None:
        """Add a user turn to the session history."""
        if session_id not in self._store:
            self._store[session_id] = deque(maxlen=self._max_turns)
        self._store[session_id].append(turn)

    def get(self, session_id: str) -> List[str]:
        """Return prior turns for a session (oldest first). Empty list if unknown."""
        return list(self._store.get(session_id, []))

    def clear(self, session_id: str) -> None:
        """Remove all turns for a session."""
        self._store.pop(session_id, None)

    def __len__(self) -> int:
        return len(self._store)
