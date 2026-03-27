from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from openai import APIError, AuthenticationError, OpenAI, RateLimitError
from sqlalchemy.orm import Session

from backend.services.ai.embedding_service import EmbeddingService
from backend.services.ai.vector_store import VectorStore
from backend.services.lexical_search_service import search_chunks_lexically


SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!?])\s+")


class RagService:
    def __init__(self, vector_store: VectorStore, embedding_service: EmbeddingService):
        self.vector_store = vector_store
        self.embedding_service = embedding_service

        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key) if api_key else None

    @staticmethod
    def _get_scope(case_id: Optional[int], document_id: Optional[int]) -> str:
        if document_id is not None:
            return "document"
        if case_id is not None:
            return "case"
        return "global"

    def _normalize_scores(self, items: List[Dict[str, Any]], score_key: str) -> Dict[Any, float]:
        positive_values = [
            float(item.get(score_key, 0.0))
            for item in items
            if float(item.get(score_key, 0.0)) > 0
        ]

        if not positive_values:
            return {}

        min_score = min(positive_values)
        max_score = max(positive_values)
        normalized: Dict[Any, float] = {}

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

    def retrieve_context(
        self,
        db: Session,
        tenant_id: int,
        question: str,
        top_k: int = 5,
        case_id: Optional[int] = None,
        document_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        lexical_results = search_chunks_lexically(
            db=db,
            tenant_id=tenant_id,
            query=question,
            top_k=max(top_k * 3, 10),
            case_id=case_id,
            document_id=document_id
        )

        query_embedding = self.embedding_service.embed_query(question)
        semantic_results = self.vector_store.search(
            query_embedding=query_embedding,
            top_k=max(top_k * 3, 10),
            case_id=case_id,
            document_id=document_id,
            tenant_id=tenant_id
        )

        lexical_norm = self._normalize_scores(lexical_results, "bm25_score")
        semantic_norm = self._normalize_scores(semantic_results, "semantic_score")

        merged: Dict[Any, Dict[str, Any]] = {}

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
                "retrieval_method": "semantic"
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
                    "retrieval_method": "lexical"
                }
            else:
                merged[chunk_id]["bm25_score"] = float(item.get("bm25_score", item.get("score", 0.0)))
                merged[chunk_id]["retrieval_method"] = "hybrid"

        for chunk_id, item in merged.items():
            bm25_component = lexical_norm.get(chunk_id, 0.0)
            semantic_component = semantic_norm.get(chunk_id, 0.0)

            final_score = (0.4 * bm25_component) + (0.6 * semantic_component)
            item["score"] = float(final_score)

            if item["bm25_score"] > 0 and item["semantic_score"] > 0:
                item["retrieval_method"] = "hybrid"
            elif item["bm25_score"] > 0:
                item["retrieval_method"] = "lexical"
            else:
                item["retrieval_method"] = "semantic"

        ranked_results = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
        return ranked_results[:top_k]

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

    def search_chunks(
        self,
        db: Session,
        tenant_id: int,
        query: str,
        top_k: int = 5,
        case_id: Optional[int] = None,
        document_id: Optional[int] = None
    ) -> Dict[str, Any]:
        results = self.retrieve_context(
            db=db,
            tenant_id=tenant_id,
            question=query,
            top_k=top_k,
            case_id=case_id,
            document_id=document_id
        )

        return {
            "query": query,
            "top_k": top_k,
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
        results = self.retrieve_context(
            db=db,
            tenant_id=tenant_id,
            question=question,
            top_k=top_k,
            case_id=case_id,
            document_id=document_id
        )

        scope = self._get_scope(case_id=case_id, document_id=document_id)

        if not results:
            return {
                "answer": "I could not find enough evidence in the indexed documents.",
                "used_fallback": True,
                "fallback_reason": "No relevant chunks found",
                "confidence": "low",
                "scope": scope,
                "sources": []
            }

        confidence = self._estimate_confidence(results)
        formatted_sources = self._format_sources(results)

        if confidence == "low":
            return {
                "answer": "I could not find enough evidence in the indexed documents.",
                "used_fallback": True,
                "fallback_reason": "Retrieval confidence too low",
                "confidence": confidence,
                "scope": scope,
                "sources": formatted_sources
            }

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
{question}

Context:
{context}
"""

        if not self.client:
            return {
                "answer": self._extractive_fallback_answer(question, results),
                "used_fallback": True,
                "fallback_reason": "OPENAI_API_KEY not configured",
                "confidence": confidence,
                "scope": scope,
                "sources": formatted_sources
            }

        try:
            response = self.client.responses.create(
                model="gpt-4o-mini",
                input=prompt
            )

            answer_text = (response.output_text or "").strip()
            if not answer_text:
                answer_text = self._extractive_fallback_answer(question, results)

            return {
                "answer": answer_text,
                "used_fallback": False,
                "fallback_reason": None,
                "confidence": confidence,
                "scope": scope,
                "sources": formatted_sources
            }

        except (RateLimitError, APIError, AuthenticationError) as exc:
            return {
                "answer": self._extractive_fallback_answer(question, results),
                "used_fallback": True,
                "fallback_reason": str(exc),
                "confidence": confidence,
                "scope": scope,
                "sources": formatted_sources
            }

        except Exception as exc:
            return {
                "answer": self._extractive_fallback_answer(question, results),
                "used_fallback": True,
                "fallback_reason": f"Unexpected generation error: {exc}",
                "confidence": confidence,
                "scope": scope,
                "sources": formatted_sources
            }