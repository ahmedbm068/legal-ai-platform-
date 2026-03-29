from __future__ import annotations

from typing import List

from sentence_transformers import SentenceTransformer


class EmbeddingService:
    MODEL_DIMENSIONS = {
        "all-MiniLM-L6-v2": 384,
        "sentence-transformers/all-MiniLM-L6-v2": 384,
    }

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model: SentenceTransformer | None = None

    def _get_model(self) -> SentenceTransformer:
        if self.model is None:
            self.model = SentenceTransformer(self.model_name)
        return self.model

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        cleaned = [text.strip() for text in texts if text and text.strip()]
        if not cleaned:
            return []

        embeddings = self._get_model().encode(
            cleaned,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        return embeddings.tolist()

    def embed_query(self, query: str) -> List[float]:
        if not query or not query.strip():
            return []

        embedding = self._get_model().encode(
            [query.strip()],
            convert_to_numpy=True,
            normalize_embeddings=True
        )[0]
        return embedding.tolist()

    @property
    def dimension(self) -> int:
        if self.model is not None:
            return int(self.model.get_sentence_embedding_dimension())

        known_dimension = self.MODEL_DIMENSIONS.get(self.model_name)
        if known_dimension:
            return known_dimension

        return int(self._get_model().get_sentence_embedding_dimension())


embedding_service = EmbeddingService()
