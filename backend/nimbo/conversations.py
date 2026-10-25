"""Open conversations and their expiry."""

import threading
import time
from collections.abc import Callable

from langgraph.checkpoint.base import BaseCheckpointSaver


class ConversationRegistry:
    """Maps each open conversation id to the time of its most recent answered question."""

    def __init__(
        self,
        checkpointer: BaseCheckpointSaver[str],
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._checkpointer = checkpointer
        self._ttl = ttl_seconds
        self._clock = clock
        self._last_answered: dict[str, float] = {}
        self._lock = threading.Lock()

    def is_open(self, conversation_id: str) -> bool:
        with self._lock:
            last = self._last_answered.get(conversation_id)
            return last is not None and self._clock() - last < self._ttl

    def touch(self, conversation_id: str) -> None:
        """Records an answered question. Call only after a successful answer."""
        with self._lock:
            self._last_answered[conversation_id] = self._clock()

    def sweep(self) -> None:
        """Forgets expired conversations, checkpoints included."""
        # ponytail: O(open conversations) on every request, fine for a demo's traffic; move to a
        # background timer, or PostgresSaver plus a DELETE job, if traffic grows.
        now = self._clock()
        with self._lock:
            expired = [i for i, last in self._last_answered.items() if now - last >= self._ttl]
            for conversation_id in expired:
                del self._last_answered[conversation_id]
        for conversation_id in expired:
            self._checkpointer.delete_thread(conversation_id)
