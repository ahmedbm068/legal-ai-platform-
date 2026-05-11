"""Logic smoke test for semantic_cache_service — no model load, no Redis.

Verifies the *plumbing* without needing the multilingual embedder
download or a running Redis. We monkey-patch:

  * ``_get_cache_embedder`` → returns a fake embedder where
    "summarize" / "summary" / "résumé" all map to one cluster vector
    and "delete" / "remove" map to a different cluster vector. Pure
    Python, instant.
  * ``cache_service`` → an in-memory dict so we don't need Redis.

Then we run the same scenarios you'd run end-to-end:
  1. store(Q1) → lookup(Q1) → must HIT, similarity 1.0 (fingerprint).
  2. lookup(Q2) where Q2 is a paraphrase → must HIT via embedding.
  3. lookup(Q3) where Q3 is unrelated → must MISS.
  4. store under scope A, lookup under scope B → must MISS.
  5. response with ``permission_denied=True`` → must NOT be stored.

Run::

    python scripts/smoke_test_semantic_cache.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the backend importable when running from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.ai import semantic_cache_service as scs  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeEmbedder:
    """Map a fixed set of phrases to deterministic 4-d vectors.

    Phrases that share a 'cluster' get nearly the same vector → cosine ~1.
    Different clusters → cosine ~0.
    """
    CLUSTERS = {
        "summary": [1.0, 0.05, 0.0, 0.0],
        "delete": [0.0, 0.0, 1.0, 0.05],
        "other": [0.05, 1.0, 0.0, 0.0],
    }
    PHRASE_TO_CLUSTER = {
        "summarize this case": "summary",
        "give me a summary": "summary",
        "résume ce dossier": "summary",
        "delete this file": "delete",
        "remove this document": "delete",
        "what is the weather": "other",
    }

    def embed_query(self, text):
        cluster = self.PHRASE_TO_CLUSTER.get(text.strip().lower(), "other")
        return list(self.CLUSTERS[cluster])


class _FakeCache:
    def __init__(self):
        self.store = {}

    def get_json(self, key):
        return self.store.get(key)

    def set_json(self, key, value, ttl_seconds=300):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def _install_fakes():
    fake_cache = _FakeCache()
    fake_embedder = _FakeEmbedder()
    scs.cache_service = fake_cache
    scs._get_cache_embedder = lambda: fake_embedder
    return fake_cache


def _scope(case_id=24):
    return scs.ScopeKey(
        tenant_id=1,
        user_id=42,
        case_id=case_id,
        document_id=None,
        mode="default",
        output_language="auto",
        agent_mode=False,
    )


def _assert(condition, message):
    if not condition:
        print(f"  FAIL — {message}")
        sys.exit(1)
    print(f"  ok   — {message}")


def main() -> int:
    fake_cache = _install_fakes()
    svc = scs.SemanticCacheService(similarity_threshold=0.95)

    print("\n[1] store + exact lookup")
    svc.store(
        question="summarize this case",
        scope=_scope(),
        response={"answer": "case 24 summary text", "confidence": "high"},
    )
    hit = svc.lookup(question="summarize this case", scope=_scope())
    _assert(hit is not None, "exact same query hits")
    _assert(hit and hit.similarity == 1.0, "exact-match similarity is 1.0 (fingerprint path)")

    print("\n[2] paraphrase lookup")
    hit2 = svc.lookup(question="give me a summary", scope=_scope())
    _assert(hit2 is not None, "paraphrase 'give me a summary' hits")
    _assert(hit2 and hit2.similarity < 1.0, "paraphrase similarity < 1.0 (embedding path)")
    _assert(hit2 and hit2.similarity >= 0.95, "paraphrase similarity >= threshold")

    print("\n[3] cross-language paraphrase")
    hit3 = svc.lookup(question="résume ce dossier", scope=_scope())
    _assert(hit3 is not None, "FR paraphrase hits an EN-cached entry")

    print("\n[4] unrelated query misses")
    miss = svc.lookup(question="what is the weather", scope=_scope())
    _assert(miss is None, "unrelated 'what is the weather' misses")

    print("\n[5] different scope (different case_id) misses")
    miss2 = svc.lookup(question="summarize this case", scope=_scope(case_id=99))
    _assert(miss2 is None, "same query under different case_id misses (scope isolation)")

    print("\n[6] permission-denied responses are not stored")
    fake_cache.store.clear()
    svc.store(
        question="delete this file",
        scope=_scope(),
        response={"answer": "no", "permission_denied": True},
    )
    miss3 = svc.lookup(question="delete this file", scope=_scope())
    _assert(miss3 is None, "permission_denied response was correctly skipped")

    print("\n[7] low-confidence fallback responses are not stored")
    fake_cache.store.clear()
    svc.store(
        question="delete this file",
        scope=_scope(),
        response={"answer": "I'm not sure", "used_fallback": True, "confidence": "low"},
    )
    miss4 = svc.lookup(question="delete this file", scope=_scope())
    _assert(miss4 is None, "low-confidence fallback was correctly skipped")

    print("\n[8] cache field is populated on hits")
    fake_cache.store.clear()
    svc.store(
        question="summarize this case",
        scope=_scope(),
        response={"answer": "case 24 summary", "confidence": "high"},
    )
    hit4 = svc.lookup(question="summarize this case", scope=_scope())
    _assert(hit4 is not None, "cache hit on stored entry")
    _assert(
        hit4 and hit4.response.get("cache", {}).get("backend") == "semantic",
        "cache.backend = 'semantic' on stored response",
    )

    print("\n[9] embedding de-dup on store")
    fake_cache.store.clear()
    svc.store(
        question="summarize this case",
        scope=_scope(),
        response={"answer": "v1", "confidence": "high"},
    )
    svc.store(
        question="give me a summary",  # same cluster vector → ≥0.99 cosine
        scope=_scope(),
        response={"answer": "v2", "confidence": "high"},
    )
    bucket = fake_cache.store[_scope().to_redis_key()]
    _assert(len(bucket) == 1, f"de-dup collapsed near-identical embeddings (got {len(bucket)})")
    _assert(bucket[0]["response"]["answer"] == "v2", "the latest entry wins after de-dup")

    print("\nOK all 9 scenarios passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
