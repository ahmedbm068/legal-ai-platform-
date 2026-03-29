from __future__ import annotations

import json
import os
import tempfile
import threading
from typing import Any, Dict, List, Optional

import faiss
import numpy as np


class VectorStore:
    def __init__(
        self,
        dimension: int,
        index_path: str = "faiss_index.bin",
        metadata_path: str = "faiss_metadata.json"
    ):
        self.dimension = dimension
        self.index_path = index_path
        self.metadata_path = metadata_path
        self._lock = threading.RLock()

        self.index = self._load_or_create_index()
        self.metadata = self._load_metadata()

        if self.index.ntotal != len(self.metadata):
            with self._lock:
                self._rebuild_index_from_metadata_embeddings()
                self.save()

    def _load_or_create_index(self):
        if os.path.exists(self.index_path):
            return faiss.read_index(self.index_path)
        return faiss.IndexFlatIP(self.dimension)

    def _load_metadata(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.metadata_path):
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def save(self) -> None:
        with self._lock:
            faiss.write_index(self.index, self.index_path)
            metadata_dir = os.path.dirname(os.path.abspath(self.metadata_path)) or "."
            fd, temp_path = tempfile.mkstemp(prefix="faiss_metadata_", suffix=".json", dir=metadata_dir)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.metadata, f, ensure_ascii=False, indent=2)
                os.replace(temp_path, self.metadata_path)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

    def _rebuild_index_from_metadata_embeddings(self) -> None:
        # Caller must hold self._lock when mutating index/metadata.
        self.index = faiss.IndexFlatIP(self.dimension)

        vectors = []
        for item in self.metadata:
            embedding = item.get("embedding")
            if embedding:
                vectors.append(embedding)

        if vectors:
            np_vectors = np.array(vectors, dtype="float32")
            self.index.add(np_vectors)

    def remove_document_embeddings(self, document_id: int) -> None:
        with self._lock:
            self.metadata = [
                item for item in self.metadata
                if item.get("document_id") != document_id
            ]
            self._rebuild_index_from_metadata_embeddings()
            self.save()

    def add_embeddings(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]]) -> None:
        if not embeddings:
            return

        if len(embeddings) != len(metadatas):
            raise ValueError("embeddings and metadatas must have the same length")

        enriched_metadatas = []
        clean_embeddings = []

        for embedding, metadata in zip(embeddings, metadatas):
            if not embedding:
                continue

            item = dict(metadata)
            item["embedding"] = embedding

            enriched_metadatas.append(item)
            clean_embeddings.append(embedding)

        if not clean_embeddings:
            return

        with self._lock:
            vectors = np.array(clean_embeddings, dtype="float32")
            self.index.add(vectors)
            self.metadata.extend(enriched_metadatas)
            self.save()

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        case_id: Optional[int] = None,
        document_id: Optional[int] = None,
        tenant_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        with self._lock:
            if not query_embedding or self.index.ntotal == 0:
                return []

            query_vector = np.array([query_embedding], dtype="float32")
            search_k = min(max(top_k * 10, 30), self.index.ntotal)

            scores, indices = self.index.search(query_vector, search_k)

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx == -1 or idx >= len(self.metadata):
                    continue

                item = self.metadata[idx]

                if tenant_id is not None and item.get("tenant_id") != tenant_id:
                    continue

                if case_id is not None and item.get("case_id") != case_id:
                    continue

                if document_id is not None and item.get("document_id") != document_id:
                    continue

                semantic_score = float(score)

                result = item.copy()
                result["score"] = semantic_score
                result["semantic_score"] = semantic_score
                result["bm25_score"] = 0.0
                result["retrieval_method"] = "semantic"
                results.append(result)

                if len(results) >= top_k:
                    break

            return results
