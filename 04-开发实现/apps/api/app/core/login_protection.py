from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Protocol


class LoginRateLimiter(Protocol):
    def allow(self, key: str) -> bool: ...
    def record_failure(self, key: str) -> None: ...
    def clear(self, key: str) -> None: ...


class MemoryLoginRateLimiter:
    def __init__(self, attempts: int, window_seconds: int) -> None:
        self._attempts = attempts
        self._window = timedelta(seconds=window_seconds)
        self._events: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = RLock()

    def allow(self, key: str) -> bool:
        now = datetime.now(timezone.utc)
        with self._lock:
            events = self._events[key]
            while events and now - events[0] >= self._window:
                events.popleft()
            return len(events) < self._attempts

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._events[key].append(datetime.now(timezone.utc))

    def clear(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


class RedisRateLimitBackend(Protocol):
    def allow(self, key: str, attempts: int, window_seconds: int) -> bool: ...
    def record_failure(self, key: str, window_seconds: int) -> None: ...
    def clear(self, key: str) -> None: ...


class RedisLoginRateLimiter:
    def __init__(self, backend: RedisRateLimitBackend, attempts: int, window_seconds: int) -> None:
        self._backend = backend
        self._attempts = attempts
        self._window_seconds = window_seconds

    def allow(self, key: str) -> bool:
        return self._backend.allow(key, self._attempts, self._window_seconds)

    def record_failure(self, key: str) -> None:
        self._backend.record_failure(key, self._window_seconds)

    def clear(self, key: str) -> None:
        self._backend.clear(key)


class GatewayLoginRateLimiter:
    """Contract for an approved gateway/WAF that rejects excess traffic upstream."""

    def allow(self, key: str) -> bool:
        del key
        return True

    def record_failure(self, key: str) -> None:
        del key

    def clear(self, key: str) -> None:
        del key
