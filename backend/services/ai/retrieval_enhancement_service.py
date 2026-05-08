"""Retrieval enhancement service.

Implements three orthogonal retrieval upgrades that compose into a single
high-recall retrieval call:

* **HyDE (Hypothetical Document Embeddings)** — ask the LLM to draft a
  short *hypothetical* legal answer to the user's question, then embed
  that synthetic answer instead of (or in addition to) the raw query.
  Captures the corpus's vocabulary, which is often nothing like how a
  layperson phrases a question.

* **Multi-query expansion** — ask the LLM to produce N paraphrases of
  the question (e.g. "what are the legal grounds for X?", "Article that
  governs X", "X under Tunisian civil code"). Each variant retrieves
  independently.

* **Reciprocal Rank Fusion (RRF)** — merge K ranked lists into one
  ranked list using the standard RRF formula
  ``score(d) = Σ 1 / (k + rank_i(d))`` with ``k = 60``. Ties are broken
  by the original first-list rank to keep behaviour deterministic.

The service is provider-agnostic: the caller supplies a ``retrieve_fn``
that takes a query string and returns a list of ranked items (any object
with a stable identifier). This keeps the module self-contained and
unit-testable in isolation — the existing FAISS / pgvector retrievers do
not need to change.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Hashable, Iterable, Sequence

from backend.services.ai.llm_gateway import llm_gateway


logger = logging.getLogger(__name__)


# RRF constant from Cormack et al. 2009. 60 is the canonical default.
RRF_K = 60


HYDE_SYSTEM_PROMPT = (
    "You are a Tunisian legal research assistant. Given a user's question, "
    "draft a short HYPOTHETICAL passage (3–6 sentences) that would plausibly "
    "appear in a legal code, ruling, or treatise and that would directly "
    "answer the question. Use formal legal vocabulary in the same language "
    "as the question. Do NOT add disclaimers or preambles — output ONLY the "
    "passage as if it were excerpted from a legal source."
)

MULTI_QUERY_SYSTEM_PROMPT = (
    "Generate {n} alternative phrasings of the following legal question. "
    "Vary vocabulary (formal, lay, code-specific), but keep the meaning "
    "identical. Output ONE phrasing per line, numbered '1.', '2.', etc. "
    "Do NOT add explanations."
)


@dataclass
class EnhancedRetrievalResult:
    """Result of an enhanced retrieval call — what to ship to the answer LLM
    plus a small audit trail for the trust drawer.
    """

    items: list[Any]
    used_hyde: bool
    used_multi_query: bool
    queries: list[str]
    hyde_passage: str | None
    fusion_method: str
    candidate_pool_size: int

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "used_hyde": self.used_hyde,
            "used_multi_query": self.used_multi_query,
            "queries": list(self.queries),
            "hyde_preview": (self.hyde_passage or "")[:240] or None,
            "fusion_method": self.fusion_method,
            "candidate_pool_size": self.candidate_pool_size,
            "final_count": len(self.items),
        }


class RetrievalEnhancementService:
    """Compose HyDE + multi-query expansion + RRF over an existing retriever."""

    def __init__(self, *, hyde_max_tokens: int = 220, multi_query_count: int = 3) -> None:
        self.hyde_max_tokens = hyde_max_tokens
        self.multi_query_count = max(1, multi_query_count)

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def enhance_and_retrieve(
        self,
        *,
        query: str,
        retrieve_fn: Callable[[str], Sequence[Any]],
        identify_fn: Callable[[Any], Hashable],
        top_k: int,
        use_hyde: bool = True,
        use_multi_query: bool = True,
    ) -> EnhancedRetrievalResult:
        """Run the enhanced retrieval pipeline.

        Parameters
        ----------
        query: original user question.
        retrieve_fn: callable that takes a string query and returns a ranked
            list of items (any callable that wraps your existing retrieval).
        identify_fn: callable returning a stable hashable id for an item
            (e.g. ``lambda x: x['chunk_id']``).
        top_k: number of items to return after fusion.
        use_hyde / use_multi_query: feature toggles for ablations.
        """

        clean_query = (query or "").strip()
        if not clean_query:
            return EnhancedRetrievalResult(
                items=[],
                used_hyde=False,
                used_multi_query=False,
                queries=[],
                hyde_passage=None,
                fusion_method="none",
                candidate_pool_size=0,
            )

        queries: list[str] = [clean_query]
        hyde_passage: str | None = None

        if use_multi_query:
            queries.extend(self._generate_paraphrases(clean_query))

        if use_hyde:
            hyde_passage = self._generate_hyde_passage(clean_query)
            if hyde_passage:
                queries.append(hyde_passage)

        # De-duplicate queries while preserving order.
        seen: set[str] = set()
        unique_queries: list[str] = []
        for q in queries:
            key = q.strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique_queries.append(q)

        ranked_lists: list[list[Any]] = []
        for q in unique_queries:
            try:
                items = list(retrieve_fn(q))
            except Exception as exc:  # noqa: BLE001 — never fail the user request
                logger.warning("retrieval_subquery_failed q=%r err=%s", q[:120], exc)
                items = []
            if items:
                ranked_lists.append(items)

        if not ranked_lists:
            return EnhancedRetrievalResult(
                items=[],
                used_hyde=use_hyde and hyde_passage is not None,
                used_multi_query=use_multi_query and len(unique_queries) > 1,
                queries=unique_queries,
                hyde_passage=hyde_passage,
                fusion_method="rrf" if len(ranked_lists) > 1 else "single",
                candidate_pool_size=0,
            )

        if len(ranked_lists) == 1:
            fused = list(ranked_lists[0])[:top_k]
            return EnhancedRetrievalResult(
                items=fused,
                used_hyde=use_hyde and hyde_passage is not None,
                used_multi_query=use_multi_query and len(unique_queries) > 1,
                queries=unique_queries,
                hyde_passage=hyde_passage,
                fusion_method="single",
                candidate_pool_size=len(ranked_lists[0]),
            )

        fused, pool_size = reciprocal_rank_fusion(
            ranked_lists, identify_fn=identify_fn, top_k=top_k
        )
        return EnhancedRetrievalResult(
            items=fused,
            used_hyde=use_hyde and hyde_passage is not None,
            used_multi_query=use_multi_query and len(unique_queries) > 1,
            queries=unique_queries,
            hyde_passage=hyde_passage,
            fusion_method="rrf",
            candidate_pool_size=pool_size,
        )

    # ──────────────────────────────────────────────────────────────────────
    # LLM-backed helpers
    # ──────────────────────────────────────────────────────────────────────

    def _generate_hyde_passage(self, query: str) -> str | None:
        client = llm_gateway.create_client()
        if client is None:
            return None
        try:
            completion = client.chat.completions.create(
                model=llm_gateway.resolve_model("text") or llm_gateway.default_model,
                messages=[
                    {"role": "system", "content": HYDE_SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                temperature=0.2,
                max_tokens=self.hyde_max_tokens,
            )
            text = llm_gateway.extract_output_text(completion).strip()
            return text or None
        except Exception as exc:  # noqa: BLE001 — best-effort enhancement
            logger.warning("hyde_generation_failed err=%s", exc, exc_info=True)
            return None

    def _generate_paraphrases(self, query: str) -> list[str]:
        client = llm_gateway.create_client()
        if client is None:
            return []
        n = self.multi_query_count
        try:
            completion = client.chat.completions.create(
                model=llm_gateway.resolve_model("text") or llm_gateway.default_model,
                messages=[
                    {
                        "role": "system",
                        "content": MULTI_QUERY_SYSTEM_PROMPT.format(n=n),
                    },
                    {"role": "user", "content": query},
                ],
                temperature=0.5,
                max_tokens=200,
            )
            text = llm_gateway.extract_output_text(completion).strip()
            return _parse_numbered_lines(text, max_items=n)
        except Exception as exc:  # noqa: BLE001 — best-effort enhancement
            logger.warning("multi_query_generation_failed err=%s", exc, exc_info=True)
            return []


# ──────────────────────────────────────────────────────────────────────────
# Pure helpers — unit-testable without any LLM dependency
# ──────────────────────────────────────────────────────────────────────────


def reciprocal_rank_fusion(
    ranked_lists: Iterable[Sequence[Any]],
    *,
    identify_fn: Callable[[Any], Hashable],
    top_k: int,
    k: int = RRF_K,
) -> tuple[list[Any], int]:
    """Merge multiple ranked lists with Reciprocal Rank Fusion.

    Returns ``(top_k_items, candidate_pool_size)``. ``candidate_pool_size``
    is the number of unique items across all input lists, useful for the
    audit trail.
    """

    scores: dict[Hashable, float] = {}
    representative: dict[Hashable, Any] = {}
    first_seen_rank: dict[Hashable, tuple[int, int]] = {}

    for list_index, items in enumerate(ranked_lists):
        for rank, item in enumerate(items):
            try:
                key = identify_fn(item)
            except Exception:  # noqa: BLE001
                continue
            if key is None:
                continue
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            representative.setdefault(key, item)
            first_seen_rank.setdefault(key, (list_index, rank))

    # Sort by RRF score desc, then by earliest rank in earliest list (deterministic).
    ordered_keys = sorted(
        scores.keys(),
        key=lambda key: (-scores[key], first_seen_rank[key][0], first_seen_rank[key][1]),
    )
    fused = [representative[k] for k in ordered_keys[:top_k]]
    return fused, len(scores)


def _parse_numbered_lines(text: str, *, max_items: int) -> list[str]:
    """Parse ``"1. foo\\n2. bar"`` into ``["foo", "bar"]``."""

    if not text:
        return []
    out: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Strip leading numbering: "1.", "1)", "(1)", "- ", "* "
        cleaned = line
        for prefix_pattern in (r"^\(?\d+[\).\-:]\s*", r"^[-*•]\s+"):
            import re

            cleaned = re.sub(prefix_pattern, "", cleaned, count=1)
        cleaned = cleaned.strip().strip('"').strip("'")
        if cleaned:
            out.append(cleaned)
        if len(out) >= max_items:
            break
    return out


retrieval_enhancement_service = RetrievalEnhancementService()


__all__ = [
    "RRF_K",
    "EnhancedRetrievalResult",
    "RetrievalEnhancementService",
    "reciprocal_rank_fusion",
    "retrieval_enhancement_service",
]
