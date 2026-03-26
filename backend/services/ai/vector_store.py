from typing import List, Dict, Any
import faiss
import numpy as np


class VectorStore:
    def __init__(self, dimension: int):
        self.dimension = dimension
        self.index = faiss.IndexFlatL2(dimension)
        self.metadata: List[Dict[str, Any]] = []

    def add_embeddings(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]]) -> None:
        """
        Add embeddings and their metadata to the vector store.
        """
        if not embeddings:
            return

        vectors = np.array(embeddings, dtype="float32")
        self.index.add(vectors)
        self.metadata.extend(metadatas)

    def search(self, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search for the most relevant chunks.
        """
        if self.index.ntotal == 0:
            return []

        query_vector = np.array([query_embedding], dtype="float32")
        distances, indices = self.index.search(query_vector, top_k)

        results = []
        for distance, idx in zip(distances[0], indices[0]):
            if idx == -1 or idx >= len(self.metadata):
                continue

            item = self.metadata[idx].copy()
            item["score"] = float(distance)
            results.append(item)

        return results