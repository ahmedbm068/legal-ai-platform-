from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.embedding_service import EmbeddingService
from backend.services.ai.reranker_service import reranker_service
from backend.services.ai.vector_store import VectorStore
from backend.services.lexical_search_service import search_chunks_lexically


class RetrievalAgent(BaseAgent):
    agent_name = "retrieval_agent"

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

        trace = [
            f"Starting retrieval for tenant={tenant_id}.",
            f"Scope case_id={case_id}, document_id={document_id}, top_k={top_k}.",
        ]

        lexical_results = search_chunks_lexically(
            db=db,
            tenant_id=tenant_id,
            query=normalized_question,
            top_k=max(top_k * 3, 10),
            case_id=case_id,
            document_id=document_id,
        )
        trace.append(f"Lexical retrieval returned {len(lexical_results)} chunks.")

        query_embedding = self.embedding_service.embed_query(normalized_question)
        semantic_results = self.vector_store.search(
            query_embedding=query_embedding,
            top_k=max(top_k * 3, 10),
            case_id=case_id,
            document_id=document_id,
            tenant_id=tenant_id,
        )
        trace.append(f"Semantic retrieval returned {len(semantic_results)} chunks.")

        lexical_norm = self._normalize_scores(lexical_results, "bm25_score")
        semantic_norm = self._normalize_scores(semantic_results, "semantic_score")

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
            item["score"] = float((0.4 * bm25_component) + (0.6 * semantic_component))

            if item["bm25_score"] > 0 and item["semantic_score"] > 0:
                item["retrieval_method"] = "hybrid"
            elif item["bm25_score"] > 0:
                item["retrieval_method"] = "lexical"
            else:
                item["retrieval_method"] = "semantic"

        preliminary_results = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
        rerank_pool = preliminary_results[: max(top_k * 4, 12)]
        trace.append(f"Hybrid ranking produced {len(preliminary_results)} merged chunks before reranking.")

        ranked_results, rerank_trace = reranker_service.rerank(
            normalized_question,
            rerank_pool,
            top_k,
        )
        trace.extend(rerank_trace)
        trace.append(f"Final retrieval returned {len(ranked_results)} chunks.")

        return self.result(
            success=True,
            payload={
                "query": normalized_question,
                "results": ranked_results,
            },
            trace=trace,
        )

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
