from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from openai import APIError, AuthenticationError, RateLimitError
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.services.cache_service import cache_service
from backend.services.ai.agents.retrieval_agent import RetrievalAgent
from backend.services.ai.agents.verifier_agent import verifier_agent
from backend.services.ai.embedding_service import EmbeddingService
from backend.services.ai.llm_gateway import llm_gateway
from backend.services.ai.vector_store import VectorStore


SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!?])\s+")


class RagService:
    def __init__(self, vector_store: VectorStore, embedding_service: EmbeddingService):
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.retrieval_agent = RetrievalAgent(vector_store=vector_store, embedding_service=embedding_service)
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    @staticmethod
    def _get_scope(case_id: Optional[int], document_id: Optional[int]) -> str:
        if document_id is not None:
            return "document"
        if case_id is not None:
            return "case"
        return "global"

    @staticmethod
    def _sanitize_top_k(top_k: int) -> int:
        try:
            parsed = int(top_k)
        except (TypeError, ValueError):
            return 5
        return max(1, min(parsed, 25))

    def retrieve_context(
        self,
        db: Session,
        tenant_id: int,
        question: str,
        top_k: int = 5,
        case_id: Optional[int] = None,
        document_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        safe_question = (question or "").strip()
        if not safe_question:
            return []

        safe_top_k = self._sanitize_top_k(top_k)

        agent_result = self.retrieval_agent.retrieve(
            db=db,
            tenant_id=tenant_id,
            question=safe_question,
            top_k=max(safe_top_k * 3, 10),
            case_id=case_id,
            document_id=document_id,
        )

        if not agent_result.success:
            return []

        return (agent_result.payload.get("results") or [])[:safe_top_k]

    def _build_context(self, results: List[Dict[str, Any]]) -> str:
        blocks = []
        for item in results:
            blocks.append(
                f"[Document: {item.get('filename', 'unknown')} - chunk {item.get('chunk_index', -1)}]\n"
                f"{item.get('chunk_text', '')}"
            )
        return "\n\n---\n\n".join(blocks)

    def _format_sources(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "chunk_id": item.get("chunk_id"),
                "document_id": item.get("document_id"),
                "case_id": item.get("case_id"),
                "filename": item.get("filename"),
                "chunk_index": item.get("chunk_index"),
                "score": round(float(item.get("score", 0.0)), 4),
                "snippet": item.get("chunk_text", "")[:300]
            }
            for item in results
        ]

    @staticmethod
    def _format_citations(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for item in results[:8]:
            label = str(item.get("filename") or "Source").strip()
            chunk_index = item.get("chunk_index")
            if chunk_index is not None:
                label = f"{label} - chunk {chunk_index}"
            key = (label, item.get("document_id"), item.get("case_id"))
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                {
                    "label": label,
                    "document_id": item.get("document_id"),
                    "case_id": item.get("case_id"),
                    "snippet": str(item.get("chunk_text") or "").strip()[:280],
                }
            )
        return citations

    @staticmethod
    def _estimate_confidence(results: List[Dict[str, Any]]) -> str:
        if not results:
            return "low"

        top_score = float(results[0].get("score", 0.0))

        if top_score >= 0.7:
            return "high"
        if top_score >= 0.4:
            return "medium"
        return "low"

    def _extractive_fallback_answer(self, question: str, results: List[Dict[str, Any]]) -> str:
        if not results:
            return "I could not find enough evidence in the indexed documents."

        query_terms = set(re.findall(r"\w+", question.lower()))
        best_sentence: str | None = None
        best_score = -1

        for item in results:
            chunk_text = item.get("chunk_text", "")
            for sentence in SENTENCE_SPLIT_REGEX.split(chunk_text):
                stripped = sentence.strip()
                if not stripped:
                    continue

                sentence_terms = set(re.findall(r"\w+", stripped.lower()))
                overlap = len(query_terms.intersection(sentence_terms))

                if overlap > best_score:
                    best_score = overlap
                    best_sentence = stripped

        if best_sentence:
            return best_sentence

        return results[0].get("chunk_text", "")[:500] or "I could not find enough evidence in the indexed documents."

    @staticmethod
    def _cache_backend() -> str:
        return "redis" if cache_service.available else "memory"

    def _build_cache_key(
        self,
        *,
        tenant_id: int,
        question: str,
        top_k: int,
        case_id: Optional[int],
        document_id: Optional[int],
    ) -> str:
        return cache_service.build_key(
            "rag_answer",
            f"tenant={tenant_id}",
            f"case={case_id or 'none'}",
            f"document={document_id or 'none'}",
            f"top_k={top_k}",
            question.strip().lower(),
        )

    @staticmethod
    def _with_cache_metadata(payload: Dict[str, Any], *, key: str, hit: bool) -> Dict[str, Any]:
        response = dict(payload)
        response["cache"] = {
            "key": key,
            "hit": hit,
            "backend": RagService._cache_backend(),
        }
        return response

    def search_chunks(
        self,
        db: Session,
        tenant_id: int,
        query: str,
        top_k: int = 5,
        case_id: Optional[int] = None,
        document_id: Optional[int] = None
    ) -> Dict[str, Any]:
        safe_top_k = self._sanitize_top_k(top_k)
        results = self.retrieve_context(
            db=db,
            tenant_id=tenant_id,
            question=query,
            top_k=safe_top_k,
            case_id=case_id,
            document_id=document_id
        )

        return {
            "query": query,
            "top_k": safe_top_k,
            "scope": self._get_scope(case_id=case_id, document_id=document_id),
            "results": results
        }

    def answer_question(
        self,
        db: Session,
        tenant_id: int,
        question: str,
        top_k: int = 5,
        case_id: Optional[int] = None,
        document_id: Optional[int] = None
    ) -> Dict[str, Any]:
        safe_question = (question or "").strip()
        safe_top_k = self._sanitize_top_k(top_k)
        cache_key = self._build_cache_key(
            tenant_id=tenant_id,
            question=safe_question,
            top_k=safe_top_k,
            case_id=case_id,
            document_id=document_id,
        )
        cached_payload = cache_service.get_json(cache_key)
        if isinstance(cached_payload, dict):
            return self._with_cache_metadata(cached_payload, key=cache_key, hit=True)

        results = self.retrieve_context(
            db=db,
            tenant_id=tenant_id,
            question=safe_question,
            top_k=safe_top_k,
            case_id=case_id,
            document_id=document_id
        )

        scope = self._get_scope(case_id=case_id, document_id=document_id)

        if not results:
            response = {
                "answer": "I could not find enough evidence in the indexed documents.",
                "used_fallback": True,
                "fallback_reason": "No relevant chunks found",
                "confidence": "low",
                "scope": scope,
                "sources": [],
                "citations": [],
            }
            cache_service.set_json(cache_key, response, ttl_seconds=settings.CACHE_TTL_SECONDS)
            return self._with_cache_metadata(response, key=cache_key, hit=False)

        confidence = self._estimate_confidence(results)
        formatted_sources = self._format_sources(results)
        citations = self._format_citations(results)

        if confidence == "low":
            response = {
                "answer": "I could not find enough evidence in the indexed documents.",
                "used_fallback": True,
                "fallback_reason": "Retrieval confidence too low",
                "confidence": confidence,
                "scope": scope,
                "sources": formatted_sources,
                "citations": citations,
            }
            cache_service.set_json(cache_key, response, ttl_seconds=settings.CACHE_TTL_SECONDS)
            return self._with_cache_metadata(response, key=cache_key, hit=False)

        context = self._build_context(results)

        prompt = f"""
You are a legal AI assistant.
Answer only using the provided context.
If the answer is not present in the context, say that clearly.
Do not invent facts.
Keep the answer concise and grounded.
When helpful, cite support in this format:
[filename - chunk X]

Question:
{safe_question}

Context:
{context}
"""

        if not self.client:
            fallback_answer = self._extractive_fallback_answer(safe_question, results)
            response = {
                "answer": fallback_answer,
                "used_fallback": True,
                "fallback_reason": "No LLM provider API key is configured",
                "confidence": confidence,
                "scope": scope,
                "sources": formatted_sources,
                "citations": citations,
            }
            cache_service.set_json(cache_key, response, ttl_seconds=settings.CACHE_TTL_SECONDS)
            return self._with_cache_metadata(response, key=cache_key, hit=False)

        try:
            response = self.client.responses.create(
                model=self.model,
                input=prompt
            )

            answer_text = (response.output_text or "").strip()
            if not answer_text:
                answer_text = self._extractive_fallback_answer(safe_question, results)

            verified_answer = answer_text
            verified_confidence = confidence
            used_fallback = False
            fallback_reason = None

            if confidence != "high":
                verification = verifier_agent.verify_answer(
                    question=safe_question,
                    answer=answer_text,
                    sources=formatted_sources,
                )
                verified_answer = verification.payload.get("supported_answer") or answer_text
                verified_confidence = verification.payload.get("confidence") or confidence
                if not verification.success:
                    verified_answer = verification.payload.get("supported_answer") or self._extractive_fallback_answer(
                        safe_question,
                        results,
                    )
                    used_fallback = True
                    fallback_reason = "Verifier agent flagged the generated answer as insufficiently grounded"

            payload = {
                "answer": verified_answer,
                "used_fallback": used_fallback,
                "fallback_reason": fallback_reason,
                "confidence": verified_confidence,
                "scope": scope,
                "sources": formatted_sources,
                "citations": citations,
            }
            cache_service.set_json(cache_key, payload, ttl_seconds=settings.CACHE_TTL_SECONDS)
            return self._with_cache_metadata(payload, key=cache_key, hit=False)

        except (RateLimitError, APIError, AuthenticationError) as exc:
            fallback_answer = self._extractive_fallback_answer(safe_question, results)
            payload = {
                "answer": fallback_answer,
                "used_fallback": True,
                "fallback_reason": str(exc),
                "confidence": confidence,
                "scope": scope,
                "sources": formatted_sources,
                "citations": citations,
            }
            cache_service.set_json(cache_key, payload, ttl_seconds=settings.CACHE_TTL_SECONDS)
            return self._with_cache_metadata(payload, key=cache_key, hit=False)

        except Exception as exc:
            fallback_answer = self._extractive_fallback_answer(safe_question, results)
            payload = {
                "answer": fallback_answer,
                "used_fallback": True,
                "fallback_reason": f"Unexpected generation error: {exc}",
                "confidence": confidence,
                "scope": scope,
                "sources": formatted_sources,
                "citations": citations,
            }
            cache_service.set_json(cache_key, payload, ttl_seconds=settings.CACHE_TTL_SECONDS)
            return self._with_cache_metadata(payload, key=cache_key, hit=False)
