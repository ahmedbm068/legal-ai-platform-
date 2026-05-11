"""Semantic prompt+answer cache for the copilot pipeline.

Goal
----
When a user asks a question that is *semantically* close to one that was
already answered (same tenant, same case, same mode, same language), we
return the previously-computed ``CopilotResponse`` instantly instead of
re-running the orchestrator. This is "Flavor B" of the cache plan in
the conversation that produced this file.

Why semantic and not exact-match
--------------------------------
Lawyers paraphrase: "summarize case 24" / "give me a summary of this
case" / "résume-moi ce dossier" are the same question. An exact-match
cache misses all of these. We embed every question, store it next to
its response, and on a new query we return the nearest neighbour above
a strict similarity threshold.

Safety
------
A wrong cache hit on a legal product is catastrophic, so we err
conservatively:
  * **Strict scoping** — a cached entry only matches when *every* scope
    component is identical: tenant id, user id, case id, document id,
    mode, output language, agent flag. We never return a Tunisian
    succession answer to a German civil-law question even if the two
    questions embed similarly.
  * **High similarity threshold** (default 0.95). At MiniLM-L6's scale
    this means near-duplicate paraphrases only.
  * **Bounded scope** — at most ~200 entries per scope key, oldest
    entries fall off (keeps memory and lookup cost flat).
  * **TTL** — entries expire after ``CACHE_TTL_SECONDS`` (same setting
    used by the existing rag_service cache).

Storage
-------
Reuses ``cache_service`` (Redis or in-memory fallback). One JSON blob
per scope key holds the rolling list of ``CachedEntry`` rows. No new
database table, no migration. Good for ≤ 10 000 entries per tenant.

Public API
----------
* ``semantic_cache_service.lookup(...)`` → ``CachedHit | None``
* ``semantic_cache_service.store(...)`` → ``None``
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from backend.core.config import settings
from backend.services.ai.embedding_service import EmbeddingService, embedding_service
from backend.services.cache_service import cache_service


logger = logging.getLogger(__name__)


# Multilingual embedder used *only* by the semantic cache, so AR/FR/EN
# paraphrases of the same legal question hit the same cache row. We keep
# this isolated from the retrieval pipeline (which still uses MiniLM-L6
# against the already-stored 384-d vectors) so swapping it can never
# silently degrade retrieval recall.
_CACHE_EMBED_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_cache_embedder_lock = threading.Lock()
_cache_embedder: EmbeddingService | None = None


def _get_cache_embedder() -> EmbeddingService:
    """Return the multilingual embedder, lazily loading on first use.

    Falls back to the shared MiniLM-L6 embedder if the multilingual
    model fails to load (e.g. no network on first boot, disk full).
    The cache still works in that fallback — only cross-language
    paraphrase hits become weaker.
    """
    global _cache_embedder
    if _cache_embedder is not None:
        return _cache_embedder
    with _cache_embedder_lock:
        if _cache_embedder is not None:
            return _cache_embedder
        try:
            candidate = EmbeddingService(model_name=_CACHE_EMBED_MODEL_NAME)
            # Force model load now so any failure surfaces here, not on
            # the first user query.
            candidate._get_model()
            _cache_embedder = candidate
            logger.info("[semantic_cache] using multilingual embedder %s", _CACHE_EMBED_MODEL_NAME)
        except Exception:
            logger.exception(
                "[semantic_cache] failed to load %s, falling back to retrieval embedder",
                _CACHE_EMBED_MODEL_NAME,
            )
            _cache_embedder = embedding_service
        return _cache_embedder


# --------------------------------------------------------------------------- #
# Tunables
# --------------------------------------------------------------------------- #

# Cosine similarity threshold above which two questions are considered
# the same. 0.95 is intentionally strict for a legal product.
DEFAULT_SIMILARITY_THRESHOLD = 0.95

# Maximum entries kept per (tenant, case, mode, language, ...) scope.
MAX_ENTRIES_PER_SCOPE = 200

# Cache key namespace.
NAMESPACE = "semantic_cache:v1"


# --------------------------------------------------------------------------- #
# Data containers
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ScopeKey:
    tenant_id: int
    user_id: int | None
    case_id: int | None
    document_id: int | None
    mode: str
    output_language: str
    agent_mode: bool

    def to_redis_key(self) -> str:
        parts = [
            NAMESPACE,
            f"t{self.tenant_id}",
            f"u{self.user_id or 0}",
            f"c{self.case_id or 0}",
            f"d{self.document_id or 0}",
            f"m{(self.mode or 'default').lower()}",
            f"lng{(self.output_language or 'auto').lower()}",
            f"agent{1 if self.agent_mode else 0}",
        ]
        return ":".join(parts)


@dataclass(frozen=True)
class CachedHit:
    response: dict[str, Any]
    similarity: float
    original_question: str
    cached_at: float


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _normalize_question(question: str) -> str:
    """Light normalisation; the embedding model handles real semantics."""
    return " ".join(question.strip().lower().split())


def _question_fingerprint(question: str) -> str:
    """Stable short id used for de-dup when storing."""
    return hashlib.sha1(_normalize_question(question).encode("utf-8")).hexdigest()[:16]


def _cosine(vec_a: list[float], vec_b: list[float]) -> float:
    """Cosine similarity for already-normalised vectors.

    The embedding service returns L2-normalised vectors (see
    ``EmbeddingService.embed_query``), so cosine reduces to the dot
    product. We keep the magnitude check anyway as belt-and-braces:
    if either vector ever arrives un-normalised, we still get the
    correct value rather than a confusingly large number.
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for a, b in zip(vec_a, vec_b):
        dot += a * b
        norm_a += a * a
        norm_b += b * b
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))


def _ttl_seconds() -> int:
    raw = getattr(settings, "CACHE_TTL_SECONDS", 300)
    try:
        return max(60, int(raw))
    except (TypeError, ValueError):
        return 300


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #

class SemanticCacheService:
    def __init__(
        self,
        *,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        max_entries_per_scope: int = MAX_ENTRIES_PER_SCOPE,
    ) -> None:
        self.similarity_threshold = similarity_threshold
        self.max_entries_per_scope = max_entries_per_scope

    # --- helpers ---------------------------------------------------------- #

    def _read_bucket(self, scope: ScopeKey) -> list[dict[str, Any]]:
        raw = cache_service.get_json(scope.to_redis_key())
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        return []

    def _write_bucket(self, scope: ScopeKey, entries: list[dict[str, Any]]) -> None:
        cache_service.set_json(scope.to_redis_key(), entries, ttl_seconds=_ttl_seconds())

    # --- public API ------------------------------------------------------- #

    def lookup(
        self,
        *,
        question: str,
        scope: ScopeKey,
    ) -> CachedHit | None:
        """Return the best cached response for this question, if any.

        We compute the embedding once and pick the entry with the highest
        cosine similarity within the scope. The match is only accepted
        when the score is above ``similarity_threshold``; otherwise we
        return ``None`` so the orchestrator runs normally.
        """
        question_text = _normalize_question(question)
        if not question_text:
            return None

        bucket = self._read_bucket(scope)
        if not bucket:
            return None

        # Fast path — if the exact normalised text was already cached we
        # don't need to embed again. This shaves ~30ms off the hot path
        # for legitimate exact repeats and makes "summarize" / "Summarize"
        # / "  summarize  " all collide as the same row.
        fp = _question_fingerprint(question_text)
        for entry in bucket:
            if entry.get("fingerprint") == fp:
                response = entry.get("response")
                if isinstance(response, dict):
                    return CachedHit(
                        response=response,
                        similarity=1.0,
                        original_question=str(entry.get("question") or ""),
                        cached_at=float(entry.get("cached_at") or 0.0),
                    )

        try:
            query_vec = _get_cache_embedder().embed_query(question_text)
        except Exception:
            logger.exception("[semantic_cache] embed_query failed; skipping lookup")
            return None
        if not query_vec:
            return None

        best_score = -1.0
        best_entry: dict[str, Any] | None = None
        for entry in bucket:
            vec = entry.get("embedding")
            if not isinstance(vec, list):
                continue
            score = _cosine(query_vec, vec)
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry is None or best_score < self.similarity_threshold:
            return None

        response = best_entry.get("response")
        if not isinstance(response, dict):
            return None

        return CachedHit(
            response=response,
            similarity=float(best_score),
            original_question=str(best_entry.get("question") or ""),
            cached_at=float(best_entry.get("cached_at") or 0.0),
        )

    def store(
        self,
        *,
        question: str,
        scope: ScopeKey,
        response: dict[str, Any],
    ) -> None:
        """Cache a freshly-computed response under the given scope.

        Skips entries that look unsafe to cache (e.g. answers flagged as
        permission-denied or those that signal insufficient grounding) so
        we never replay a known-bad answer.
        """
        question_text = _normalize_question(question)
        if not question_text or not isinstance(response, dict):
            return
        if response.get("permission_denied"):
            return
        if response.get("used_fallback") and (response.get("confidence") or "").lower() == "low":
            # Low-confidence fallback answers are not worth caching; the
            # next run might succeed properly.
            return

        try:
            embedding = _get_cache_embedder().embed_query(question_text)
        except Exception:
            logger.exception("[semantic_cache] embed_query failed; skipping store")
            return
        if not embedding:
            return

        fp = _question_fingerprint(question_text)

        # Strip volatile / noisy fields so the cached payload is small
        # and stable when replayed.
        cached_response = dict(response)
        cached_response.pop("execution_trace", None)
        # Always mark the cached payload as having come from cache so that
        # downstream code does not double-count latency stats.
        cached_response["cache"] = {
            "key": fp,
            "hit": False,  # this is the *source* row — hit becomes True on lookup
            "backend": "semantic",
        }

        new_entry = {
            "question": question_text,
            "fingerprint": fp,
            "embedding": embedding,
            "response": cached_response,
            "cached_at": time.time(),
        }

        bucket = self._read_bucket(scope)
        # De-dup pass 1: drop any existing entry with the same fingerprint
        # (= same normalised question text).
        bucket = [e for e in bucket if e.get("fingerprint") != fp]
        # De-dup pass 2: drop any entry whose embedding is *very* close to
        # the new one (cosine ≥ 0.99). Without this, three paraphrases of
        # the same question would each create their own row even though
        # they all answer to the same cache hit on lookup.
        deduped: list[dict[str, Any]] = []
        for existing in bucket:
            existing_vec = existing.get("embedding")
            if isinstance(existing_vec, list) and _cosine(existing_vec, embedding) >= 0.99:
                continue
            deduped.append(existing)
        deduped.append(new_entry)
        # Bound the bucket size — keep the most recent entries.
        if len(deduped) > self.max_entries_per_scope:
            deduped = deduped[-self.max_entries_per_scope:]
        self._write_bucket(scope, deduped)


semantic_cache_service = SemanticCacheService()
