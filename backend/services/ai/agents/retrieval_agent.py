from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.embedding_service import EmbeddingService
from backend.services.ai.reranker_service import reranker_service
from backend.services.ai.vector_store import VectorStore
from backend.services.lexical_search_service import search_chunks_lexically


class RetrievalAgent(BaseAgent):
    agent_name = "retrieval_agent"
    DEFAULT_TOP_K = 5
    MAX_TOP_K = 25
    NON_LEGAL_FILENAME_MARKERS = (
        "runbook",
        "smoke",
        "test",
        "prompt",
        "readme",
        "draft",
        "notes",
        ".md",
    )
    NON_LEGAL_TEXT_MARKERS = (
        "<case_id>",
        "<document_id>",
        "what success looks like",
        "optimize prompt",
        "agent test runbook",
        "prompt examples",
        "pdf_ready.md",
    )
    FILTER_BYPASS_QUERY_MARKERS = (
        "runbook",
        "test",
        "prompt",
        "smoke",
        "workflow test",
        "eval",
    )

    def __init__(self, vector_store: VectorStore, embedding_service: EmbeddingService) -> None:
        self.vector_store = vector_store
        self.embedding_service = embedding_service

    def retrieve(
        self,
        *,
        db: Session,
        tenant_id: int,
        question: str,
        top_k: int = 5,
        case_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> AgentResult:
        normalized_question = (question or "").strip()
        if not normalized_question:
            return self.result(
                success=False,
                error="Question/query is empty.",
                trace=["Input validation failed: question was empty."],
            )
        safe_top_k = self._sanitize_top_k(top_k)

        trace = [
            f"Starting retrieval for tenant={tenant_id}.",
            f"Scope case_id={case_id}, document_id={document_id}, top_k={safe_top_k}.",
        ]

        lexical_results = search_chunks_lexically(
            db=db,
            tenant_id=tenant_id,
            query=normalized_question,
            top_k=max(safe_top_k * 3, 10),
            case_id=case_id,
            document_id=document_id,
        )
        trace.append(f"Lexical retrieval returned {len(lexical_results)} chunks.")

        query_embedding = self.embedding_service.embed_query(normalized_question)
        semantic_results = self.vector_store.search(
            query_embedding=query_embedding,
            top_k=max(safe_top_k * 3, 10),
            case_id=case_id,
            document_id=document_id,
            tenant_id=tenant_id,
        )
        trace.append(f"Semantic retrieval returned {len(semantic_results)} chunks.")

        lexical_norm = self._normalize_scores(lexical_results, "bm25_score")
        semantic_norm = self._normalize_scores(semantic_results, "semantic_score")
        lexical_weight, semantic_weight = self._resolve_hybrid_weights()

        merged: dict[Any, dict[str, Any]] = {}

        for item in semantic_results:
            chunk_id = item.get("chunk_id")
            if chunk_id is None:
                continue

            merged[chunk_id] = {
                "chunk_id": chunk_id,
                "document_id": item.get("document_id"),
                "case_id": item.get("case_id"),
                "filename": item.get("filename", "unknown"),
                "chunk_index": item.get("chunk_index", -1),
                "chunk_text": item.get("chunk_text", ""),
                "bm25_score": 0.0,
                "semantic_score": float(item.get("semantic_score", item.get("score", 0.0))),
                "score": 0.0,
                "retrieval_method": "semantic",
            }

        for item in lexical_results:
            chunk_id = item.get("chunk_id")
            if chunk_id is None:
                continue

            if chunk_id not in merged:
                merged[chunk_id] = {
                    "chunk_id": chunk_id,
                    "document_id": item.get("document_id"),
                    "case_id": item.get("case_id"),
                    "filename": item.get("filename", "unknown"),
                    "chunk_index": item.get("chunk_index", -1),
                    "chunk_text": item.get("chunk_text", ""),
                    "bm25_score": float(item.get("bm25_score", item.get("score", 0.0))),
                    "semantic_score": 0.0,
                    "score": 0.0,
                    "retrieval_method": "lexical",
                }
            else:
                merged[chunk_id]["bm25_score"] = float(item.get("bm25_score", item.get("score", 0.0)))
                merged[chunk_id]["retrieval_method"] = "hybrid"

        for chunk_id, item in merged.items():
            bm25_component = lexical_norm.get(chunk_id, 0.0)
            semantic_component = semantic_norm.get(chunk_id, 0.0)
            item["score"] = float((lexical_weight * bm25_component) + (semantic_weight * semantic_component))

            if item["bm25_score"] > 0 and item["semantic_score"] > 0:
                item["retrieval_method"] = "hybrid"
            elif item["bm25_score"] > 0:
                item["retrieval_method"] = "lexical"
            else:
                item["retrieval_method"] = "semantic"

        preliminary_results = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
        preliminary_results = self._prioritize_evidence_sources(preliminary_results)
        min_score = max(0.0, float(settings.RETRIEVAL_MIN_SCORE))
        if min_score > 0:
            preliminary_results = [item for item in preliminary_results if float(item.get("score", 0.0)) >= min_score]
            trace.append(f"Applied retrieval min score >= {min_score:.2f}; remaining {len(preliminary_results)} chunks.")

        if settings.RETRIEVAL_FILTER_NON_LEGAL_TEST:
            filtered_preliminary = self._filter_non_legal_test_chunks(
                question=normalized_question,
                chunks=preliminary_results,
            )
            if filtered_preliminary:
                removed = len(preliminary_results) - len(filtered_preliminary)
                if removed > 0:
                    trace.append(f"Filtered {removed} non-legal/test chunk(s) before reranking.")
                preliminary_results = filtered_preliminary
            elif preliminary_results:
                trace.append("Non-legal/test filter would remove all chunks; keeping original pool as fallback.")

        rerank_pool = preliminary_results[: max(safe_top_k * 4, 12)]
        trace.append(f"Hybrid ranking produced {len(preliminary_results)} merged chunks before reranking.")

        ranked_results, rerank_trace = reranker_service.rerank(
            normalized_question,
            rerank_pool,
            safe_top_k,
        )
        trace.extend(rerank_trace)

        if settings.RETRIEVAL_FILTER_NON_LEGAL_TEST and ranked_results:
            filtered_ranked = self._filter_non_legal_test_chunks(
                question=normalized_question,
                chunks=ranked_results,
            )
            if filtered_ranked:
                removed = len(ranked_results) - len(filtered_ranked)
                if removed > 0:
                    trace.append(f"Filtered {removed} non-legal/test chunk(s) after reranking.")
                ranked_results = filtered_ranked

        if min_score > 0 and ranked_results:
            ranked_results = [item for item in ranked_results if float(item.get("score", 0.0)) >= min_score]

        ranked_results = self._prioritize_evidence_sources(ranked_results)
        ranked_results = ranked_results[:safe_top_k]
        trace.append(f"Final retrieval returned {len(ranked_results)} chunks.")

        return self.result(
            success=True,
            payload={
                "query": normalized_question,
                "results": ranked_results,
            },
            trace=trace,
        )

    @classmethod
    def _sanitize_top_k(cls, top_k: int | None) -> int:
        if top_k is None:
            return cls.DEFAULT_TOP_K
        try:
            parsed = int(top_k)
        except (TypeError, ValueError):
            return cls.DEFAULT_TOP_K
        return max(1, min(parsed, cls.MAX_TOP_K))

    @staticmethod
    def _normalize_scores(items: list[dict[str, Any]], score_key: str) -> dict[Any, float]:
        positive_values = [
            float(item.get(score_key, 0.0))
            for item in items
            if float(item.get(score_key, 0.0)) > 0
        ]

        if not positive_values:
            return {}

        min_score = min(positive_values)
        max_score = max(positive_values)
        normalized: dict[Any, float] = {}

        for item in items:
            chunk_id = item.get("chunk_id")
            raw_score = float(item.get(score_key, 0.0))
            if chunk_id is None or raw_score <= 0:
                continue

            if max_score == min_score:
                normalized[chunk_id] = 1.0
            else:
                normalized[chunk_id] = (raw_score - min_score) / (max_score - min_score)

        return normalized

    @staticmethod
    def _resolve_hybrid_weights() -> tuple[float, float]:
        lexical_weight = max(0.0, float(settings.RETRIEVAL_LEXICAL_WEIGHT))
        semantic_weight = max(0.0, float(settings.RETRIEVAL_SEMANTIC_WEIGHT))
        total = lexical_weight + semantic_weight
        if total <= 0:
            return 0.4, 0.6
        return lexical_weight / total, semantic_weight / total

    @classmethod
    def _prioritize_evidence_sources(cls, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranked: list[dict[str, Any]] = []
        for item in chunks:
            row = dict(item)
            priority = cls._evidence_priority(row)
            row["evidence_priority"] = priority
            ranked.append(row)
        return sorted(
            ranked,
            key=lambda item: (
                int(item.get("evidence_priority") or 4),
                -float(item.get("score") or 0.0),
            ),
        )

    @staticmethod
    def _evidence_priority(item: dict[str, Any]) -> int:
        filename = str(item.get("filename") or "").strip().lower()
        text = str(item.get("chunk_text") or "").strip().lower()
        combined = f"{filename}\n{text}"

        legal_code_markers = (
            "code civil",
            "code des obligations",
            "code_succession",
            "code_international",
            "article ",
            "legal code",
            "law corpus",
        )
        timeline_markers = ("timeline", "chronology", "event", "notice date", "effective date", "deadline")
        financial_markers = ("invoice", "payment", "amount", "fee", "price", "kpi", "sla", "damages", "penalty")
        case_doc_markers = ("contract", "agreement", "notice", "email", "correspondence", "letter", "breach")

        if any(marker in combined for marker in case_doc_markers) and not any(marker in filename for marker in legal_code_markers):
            return 1
        if any(marker in combined for marker in timeline_markers):
            return 2
        if any(marker in combined for marker in financial_markers):
            return 3
        if any(marker in combined for marker in legal_code_markers):
            return 4
        return 2 if item.get("case_id") is not None else 4

    @classmethod
    def _filter_non_legal_test_chunks(
        cls,
        *,
        question: str,
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        lowered_question = (question or "").lower()
        if any(marker in lowered_question for marker in cls.FILTER_BYPASS_QUERY_MARKERS):
            return chunks

        filtered: list[dict[str, Any]] = []
        for item in chunks:
            if cls._looks_like_non_legal_test_chunk(item):
                continue
            filtered.append(item)
        return filtered

    @classmethod
    def _looks_like_non_legal_test_chunk(cls, item: dict[str, Any]) -> bool:
        filename = str(item.get("filename") or "").strip().lower()
        text = str(item.get("chunk_text") or "").strip().lower()

        filename_flag = any(marker in filename for marker in cls.NON_LEGAL_FILENAME_MARKERS)
        text_flag = any(marker in text for marker in cls.NON_LEGAL_TEXT_MARKERS)

        legal_signal = bool(
            re.search(
                r"\b(agreement|contract|breach|termination|invoice|clause|obligation|notice|dispute|liability|governing law)\b",
                text,
            )
        )
        # Keep chunks with strong legal signal even if filename looks noisy.
        if legal_signal and not text_flag:
            return False

        return filename_flag or text_flag
