import os
from typing import List, Dict
from openai import OpenAI

from backend.services.ai.embedding_service import EmbeddingService
from backend.services.ai.vector_store import VectorStore


class RagService:
    def __init__(self, vector_store: VectorStore, embedding_service: EmbeddingService):
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def retrieve_context(self, question: str, top_k: int = 5) -> List[Dict]:
        query_embedding = self.embedding_service.embed_query(question)
        return self.vector_store.search(query_embedding, top_k=top_k)

    def answer_question(self, question: str, top_k: int = 5) -> str:
        results = self.retrieve_context(question, top_k=top_k)

        if not results:
            return "No relevant information was found in the uploaded documents."

        context_blocks = []
        for item in results:
            chunk_text = item.get("chunk_text", "")
            filename = item.get("filename", "unknown")
            chunk_index = item.get("chunk_index", -1)

            context_blocks.append(
                f"[Document: {filename} | Chunk: {chunk_index}]\n{chunk_text}"
            )

        context = "\n\n---\n\n".join(context_blocks)

        prompt = f"""
You are a legal AI assistant.
Answer the user's question using only the provided context.
If the answer is not in the context, say clearly that the answer was not found in the document.
Be precise and professional.

User question:
{question}

Context:
{context}
"""

        response = self.client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        )

        return response.output_text.strip()