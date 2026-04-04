from __future__ import annotations

import json
import threading
import time
from typing import Any

from backend.core.config import settings


class CacheService:
    def __init__(self) -> None:
        self._client = None
        self._client_checked = False
        self._memory: dict[str, tuple[float, str]] = {}
        self._lock = threading.RLock()

    def _get_client(self):
        if self._client_checked:
            return self._client

        self._client_checked = True
        try:
            import redis  # type: ignore

            client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
            client.ping()
            self._client = client
        except Exception:
            self._client = None
        return self._client

    @property
    def available(self) -> bool:
        return self._get_client() is not None

    @staticmethod
    def build_key(*parts: Any) -> str:
        cleaned = [str(part).strip().replace(" ", "_") for part in parts if str(part).strip()]
        return ":".join(cleaned)

    def get_json(self, key: str) -> dict[str, Any] | list[Any] | None:
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
        serialized = json.dumps(value, ensure_ascii=False)
        client = self._get_client()
        if client is not None:
            client.setex(key, max(1, int(ttl_seconds)), serialized)
            return

        with self._lock:
            self._memory[key] = (time.time() + max(1, int(ttl_seconds)), serialized)

    def delete(self, key: str) -> None:
        client = self._get_client()
        if client is not None:
            client.delete(key)
            return

        with self._lock:
            self._memory.pop(key, None)


cache_service = CacheService()
