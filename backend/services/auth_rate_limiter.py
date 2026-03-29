from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from math import ceil
from threading import RLock
from time import monotonic

from fastapi import HTTPException, status


def _normalized(value: str | None, fallback: str = "unknown") -> str:
    normalized = (value or "").strip().lower()
    return normalized or fallback


@dataclass(frozen=True)
class RateLimitConfig:
    max_attempts: int
    window_seconds: int
    block_seconds: int

    @classmethod
    def safe(cls, *, max_attempts: int, window_seconds: int, block_seconds: int) -> "RateLimitConfig":
        return cls(
            max_attempts=max(1, int(max_attempts)),
            window_seconds=max(1, int(window_seconds)),
            block_seconds=max(1, int(block_seconds)),
        )


class AuthRateLimiter:
    def __init__(self) -> None:
        self._lock = RLock()
        self._attempts: dict[tuple[str, str, str], deque[float]] = defaultdict(deque)
        self._blocked_until: dict[tuple[str, str, str], float] = {}

    def _key(self, *, scope: str, identifier: str | None, client_ip: str | None) -> tuple[str, str, str]:
        return (
            _normalized(scope, fallback="auth"),
            _normalized(identifier),
            _normalized(client_ip),
        )

    def assert_allowed(
        self,
        *,
        scope: str,
        identifier: str | None,
        client_ip: str | None,
        config: RateLimitConfig,
    ) -> None:
        key = self._key(scope=scope, identifier=identifier, client_ip=client_ip)
        now = monotonic()

        with self._lock:
            blocked_until = self._blocked_until.get(key)
            if blocked_until and blocked_until > now:
                retry_after_seconds = max(1, ceil(blocked_until - now))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many failed attempts. Try again in {retry_after_seconds} seconds.",
                    headers={"Retry-After": str(retry_after_seconds)},
                )

            self._blocked_until.pop(key, None)
            self._prune_attempts_locked(key=key, now=now, window_seconds=config.window_seconds)

    def record_failure(
        self,
        *,
        scope: str,
        identifier: str | None,
        client_ip: str | None,
        config: RateLimitConfig,
    ) -> None:
        key = self._key(scope=scope, identifier=identifier, client_ip=client_ip)
        now = monotonic()

        with self._lock:
            self._prune_attempts_locked(key=key, now=now, window_seconds=config.window_seconds)
            attempts = self._attempts[key]
            attempts.append(now)

            if len(attempts) >= config.max_attempts:
                self._blocked_until[key] = now + config.block_seconds
                attempts.clear()

    def record_success(self, *, scope: str, identifier: str | None, client_ip: str | None) -> None:
        key = self._key(scope=scope, identifier=identifier, client_ip=client_ip)

        with self._lock:
            self._attempts.pop(key, None)
            self._blocked_until.pop(key, None)

    def _prune_attempts_locked(self, *, key: tuple[str, str, str], now: float, window_seconds: int) -> None:
        attempts = self._attempts.get(key)
        if not attempts:
            return

        cutoff = now - window_seconds
        while attempts and attempts[0] < cutoff:
            attempts.popleft()

        if not attempts:
            self._attempts.pop(key, None)


auth_rate_limiter = AuthRateLimiter()
