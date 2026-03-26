import os
from typing import List, Dict, Optional

from openai import OpenAI
from openai import RateLimitError, APIError, AuthenticationError

from backend.services.ai.embedding_service import EmbeddingService
from backend.services.ai.vector_store import VectorStore


class RagService:
    def __init__(self, vector_store: VectorStore, embedding_service: EmbeddingService):
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key) if api_key else None

    def retrieve_context(
        self,
        question: str,
        top_k: int = 5,
        case_id: Optional[int] = None,
        document_id: Optional[int] = None
    ) -> List[Dict]:
        query_embedding = self.embedding_service.embed_query(question)
        return self.vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k,
            case_id=case_id,
            document_id=document_id
        )

    def _build_context(self, results: List[Dict]) -> str:
        blocks = []
        for item in results:
            blocks.append(
                f"[Document: {item.get('filename', 'unknown')} - chunk {item.get('chunk_index', -1)}]\n"
                f"{item.get('chunk_text', '')}"
            )
        return "\n\n---\n\n".join(blocks)

    def _format_sources(self, results: List[Dict]) -> List[Dict]:
        formatted = []
        for item in results:
            formatted.append({
                "document_id": item.get("document_id"),
                "case_id": item.get("case_id"),
                "filename": item.get("filename"),
                "chunk_index": item.get("chunk_index"),
                "score": item.get("score"),
                "snippet": item.get("chunk_text", "")[:300]
            })
        return formatted

    def answer_question(
        self,
        question: str,
        top_k: int = 5,
        case_id: Optional[int] = None,
        document_id: Optional[int] = None
    ) -> Dict:
        results = self.retrieve_context(
            question=question,
            top_k=top_k,
            case_id=case_id,
            document_id=document_id
        )

        if not results:
            return {
                "answer": "No relevant information was found in the indexed documents.",
                "used_fallback": True,
                "sources": []
            }

        context = self._build_context(results)

        prompt = f"""
You are a legal AI assistant.
Answer only using the provided context.
If the answer is not present in the context, say that clearly.
Do not invent facts.
When possible, mention the supporting source as:
[filename - chunk X]

Question:
{question}

Context:
{context}
"""

        formatted_sources = self._format_sources(results)

        if not self.client:
            return {
                "answer": results[0]["chunk_text"],
                "used_fallback": True,
                "fallback_reason": "OPENAI_API_KEY not configured",
                "sources": formatted_sources
            }

        try:
            response = self.client.responses.create(
                model="gpt-4o-mini",
                input=prompt
            )

            return {
                "answer": response.output_text.strip(),
                "used_fallback": False,
                "sources": formatted_sources
            }

        except (RateLimitError, APIError, AuthenticationError) as e:
            return {
                "answer": results[0]["chunk_text"],
                "used_fallback": True,
                "fallback_reason": str(e),
                "sources": formatted_sources
            }