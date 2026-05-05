from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Single shared limiter instance — imported by main.py and all routers.
# strategy="moving-window": true sliding-window algorithm; immune to the
# boundary-burst attack that fixed-window suffers at window edges.
# headers_enabled exposes X-RateLimit-Limit / X-RateLimit-Remaining /
# Retry-After so clients can back off gracefully without guessing.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    strategy="moving-window",
    headers_enabled=True,
)
