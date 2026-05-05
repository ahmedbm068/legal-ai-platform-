"""Week 1 DoD coverage — rate limiter configuration contract.

Verifies the central `limiter` instance is configured as required by the
sprint plan: sliding-window strategy, headers enabled, single shared instance.
"""
from __future__ import annotations

import unittest

from backend.core.rate_limiter import limiter


class RateLimiterConfigTests(unittest.TestCase):
    def test_limiter_uses_moving_window_strategy(self) -> None:
        # The moving-window strategy is required to prevent the boundary-burst
        # attack that fixed-window suffers at window edges.
        # Read the underlying configuration from slowapi.
        strategy = getattr(limiter, "_strategy", None) or getattr(limiter, "strategy", None)
        # slowapi stores the raw strategy string passed to the constructor.
        self.assertIn(
            "moving",
            str(strategy or "").lower(),
            f"expected moving-window strategy, got {strategy!r}",
        )

    def test_limiter_emits_rate_limit_headers(self) -> None:
        # X-RateLimit-Limit / X-RateLimit-Remaining / Retry-After headers
        # must be enabled so clients can back off without guessing.
        headers_enabled = (
            getattr(limiter, "_headers_enabled", None)
            or getattr(limiter, "headers_enabled", None)
        )
        self.assertTrue(headers_enabled, "rate-limit headers must be enabled")

    def test_limiter_singleton_identity(self) -> None:
        # The same `limiter` import must yield the same object every time.
        from backend.core.rate_limiter import limiter as second
        self.assertIs(limiter, second)


if __name__ == "__main__":
    unittest.main()
