"""Sliding-window rate limiter keyed by client IP."""

import math
import threading
import time
from collections import deque
from collections.abc import Callable


class RateLimiter:
    # ponytail: in-process and single-instance; move to Redis if the API ever runs replicated.
    def __init__(
        self,
        limit: int = 10,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> int | None:
        """Records a request. Returns None if allowed, else the seconds to wait (Retry-After).

        Rejected requests are not recorded, so hammering does not extend the window.
        """
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                return max(1, math.ceil(hits[0] + self._window - now))
            hits.append(now)
            return None
