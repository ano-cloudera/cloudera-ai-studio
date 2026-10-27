from __future__ import annotations

import time
from threading import RLock
from typing import Any


class MetadataCache:
    def __init__(self, ttl_seconds: int = 60) -> None:
        self._ttl = max(0, ttl_seconds)
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = RLock()

    def get(self, key: str) -> Any | None:
        if self._ttl <= 0:
            return None
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            expires, value = entry
            if time.monotonic() > expires:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        if self._ttl <= 0:
            return
        with self._lock:
            self._store[key] = (time.monotonic() + self._ttl, value)

    def invalidate_prefix(self, prefix: str) -> None:
        with self._lock:
            for key in list(self._store):
                if key.startswith(prefix):
                    del self._store[key]
