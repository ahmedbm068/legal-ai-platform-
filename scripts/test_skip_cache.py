"""Smoke test for the skip_cache flag on the /ai/copilot endpoint.

Run with: python scripts/test_skip_cache.py
"""
import sys
import time

import requests

BASE_URL = "http://127.0.0.1:8000"
MSG = "draft an email to my client saying the meeting is postponed for case 29"

r = requests.post(f"{BASE_URL}/auth/login",
                  json={"email": "ahmed@example.com", "password": "12345678"},
                  timeout=15)
r.raise_for_status()
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

payload_base = {"message": MSG, "mode": "default", "workspace_case_id": 29}

# ── call 1: warm up the cache ────────────────────────────────────────────────
r1 = requests.post(f"{BASE_URL}/ai/copilot", headers=headers,
                   json=payload_base, timeout=120)
r1.raise_for_status()
print(f"call1 (warm-up)  cache.hit={r1.json().get('cache', {}).get('hit')}")

# ── call 2: should be a cache hit ───────────────────────────────────────────
r2 = requests.post(f"{BASE_URL}/ai/copilot", headers=headers,
                   json=payload_base, timeout=120)
r2.raise_for_status()
print(f"call2 (no-skip)  cache.hit={r2.json().get('cache', {}).get('hit')}")

# ── call 3: skip_cache=True must bypass cache ────────────────────────────────
t0 = time.time()
r3 = requests.post(f"{BASE_URL}/ai/copilot", headers=headers,
                   json={**payload_base, "skip_cache": True}, timeout=120)
r3.raise_for_status()
elapsed = round(time.time() - t0, 2)
d3 = r3.json()
cache_hit = d3.get("cache", {}).get("hit")
print(f"call3 (skip)     cache.hit={cache_hit}  elapsed={elapsed}s")

if cache_hit is True:
    print("FAIL: cache was still hit despite skip_cache=True")
    sys.exit(1)

print("PASS: skip_cache correctly bypassed the cache")
