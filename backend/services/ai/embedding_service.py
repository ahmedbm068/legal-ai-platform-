from __future__ import annotations

from typing import List

from sentence_transformers import SentenceTransformer


class EmbeddingService:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        cleaned = [text.strip() for text in texts if text and text.strip()]
        if not cleaned:
            return []

        embeddings = self.model.encode(
            cleaned,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        return embeddings.tolist()

    def embed_query(self, query: str) -> List[float]:
        if not query or not query.strip():
            return []

        embedding = self.model.encode(
            [query.strip()],
            convert_to_numpy=True,
            normalize_embeddings=True
        )[0]
        return embedding.tolist()

    @property
    def dimension(self) -> int:
        return int(self.model.get_sentence_embedding_dimension())


embedding_service = EmbeddingService()