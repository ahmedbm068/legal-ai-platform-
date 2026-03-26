import json
import os
from typing import List, Dict, Any, Optional

import faiss
import numpy as np


class VectorStore:
    def __init__(self, dimension: int, index_path: str = "faiss_index.bin", metadata_path: str = "faiss_metadata.json"):
        self.dimension = dimension
        self.index_path = index_path
        self.metadata_path = metadata_path

        if os.path.exists(self.index_path):
            self.index = faiss.read_index(self.index_path)
        else:
            self.index = faiss.IndexFlatL2(dimension)

        if os.path.exists(self.metadata_path):
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                self.metadata: List[Dict[str, Any]] = json.load(f)
        else:
            self.metadata = []

    def save(self) -> None:
        faiss.write_index(self.index, self.index_path)
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

    def add_embeddings(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]]) -> None:
        if not embeddings:
            return

        vectors = np.array(embeddings, dtype="float32")
        self.index.add(vectors)
        self.metadata.extend(metadatas)
        self.save()

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        case_id: Optional[int] = None,
        document_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        if self.index.ntotal == 0:
            return []

        query_vector = np.array([query_embedding], dtype="float32")
        search_k = max(top_k * 5, 20)
        distances, indices = self.index.search(query_vector, min(search_k, self.index.ntotal))

        results = []
        for distance, idx in zip(distances[0], indices[0]):
            if idx == -1 or idx >= len(self.metadata):
                continue

            item = self.metadata[idx]

            if case_id is not None and item.get("case_id") != case_id:
                continue

            if document_id is not None and item.get("document_id") != document_id:
                continue

            result = item.copy()
            result["score"] = float(distance)
            results.append(result)

            if len(results) >= top_k:
                break

        return results