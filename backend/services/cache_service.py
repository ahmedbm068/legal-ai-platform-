from __future__ import annotations

import json
import threading
import time
from contextvars import ContextVar
from typing import Any

from backend.core.config import settings

# Dev-only flag: set to True via _SKIP_CACHE.set(True) to bypass cache for a request.
# Uses ContextVar so it is isolated per async task / thread.
_SKIP_CACHE: ContextVar[bool] = ContextVar("_skip_cache", default=False)

# Maximum number of entries held in the in-memory fallback store.
# When the limit is reached, the oldest *expired* entries are evicted first;
# if still over the cap, the oldest entries by insertion order are dropped.
_MAX_MEMORY_ENTRIES = 512


class CacheService:
    def __init__(self) -> None:
        self._client = None
        self._client_initialized = False
        self._init_lock = threading.Lock()
        self._memory: dict[str, tuple[float, str]] = {}
        self._lock = threading.RLock()

    def _get_client(self):
        # Fast path — already initialized (no lock needed for reads after init)
        if self._client_initialized:
            return self._client

        with self._init_lock:
            # Re-check inside the lock to handle concurrent first calls
            if self._client_initialized:
                return self._client
            try:
                import redis  # type: ignore

                client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
                client.ping()
                self._client = client
            except Exception:
                self._client = None
            finally:
                # Always mark initialized so we don't retry on every call
                self._client_initialized = True
        return self._client

    @property
    def available(self) -> bool:
        return self._get_client() is not None

    @staticmethod
    def build_key(*parts: Any) -> str:
        cleaned = [str(part).strip().replace(" ", "_") for part in parts if str(part).strip()]
        return ":".join(cleaned)

    def _evict_memory(self) -> None:
        """Remove expired entries; if still over the cap, drop the oldest."""
        now = time.time()
        expired = [k for k, (exp, _) in self._memory.items() if exp <= now]
        for k in expired:
            self._memory.pop(k, None)
        # If still over cap, evict oldest by insertion order (dict preserves order in Py 3.7+)
        overflow = len(self._memory) - _MAX_MEMORY_ENTRIES
        if overflow > 0:
            for k in list(self._memory.keys())[:overflow]:
                self._memory.pop(k, None)

    def get_json(self, key: str) -> dict[str, Any] | list[Any] | None:
        if _SKIP_CACHE.get():
            return None
        client = self._get_client()
        if client is not None:
            raw = client.get(key)
            if not raw:
                return None
            try:
                payload = json.loads(raw)
                return payload if isinstance(payload, (dict, list)) else None
            except Exception:
                return None

        with self._lock:
            current = self._memory.get(key)
            if not current:
                return None
            expires_at, raw = current
            if expires_at <= time.time():
                self._memory.pop(key, None)
                return None
            try:
                payload = json.loads(raw)
                return payload if isinstance(payload, (dict, list)) else None
            except Exception:
                return None

    def set_json(self, key: str, value: dict[str, Any] | list[Any], ttl_seconds: int = 300) -> None:
        if _SKIP_CACHE.get():
            return
        serialized = json.dumps(value, ensure_ascii=False)
        client = self._get_client()
        if client is not None:
            client.setex(key, max(1, int(ttl_seconds)), serialized)
            return

        with self._lock:
            # Evict before inserting to keep memory bounded
            if len(self._memory) >= _MAX_MEMORY_ENTRIES:
                self._evict_memory()
            self._memory[key] = (time.time() + max(1, int(ttl_seconds)), serialized)

    def delete(self, key: str) -> None:
        client = self._get_client()
        if client is not None:
            client.delete(key)
            return

        with self._lock:
            self._memory.pop(key, None)


cache_service = CacheService()
