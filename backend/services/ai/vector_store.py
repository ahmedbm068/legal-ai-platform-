from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional

import faiss
import numpy as np
from sqlalchemy import text

from backend.database.database import engine

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(
        self,
        dimension: int,
        index_path: str = "faiss_index.bin",
        metadata_path: str = "faiss_metadata.json",
    ):
        self.dimension = dimension
        self.index_path = index_path
        self.metadata_path = metadata_path
        self._lock = threading.RLock()
        self._database_backend_enabled = self._detect_database_backend()

        if self._database_backend_enabled:
            self.index = None
            self.metadata: List[Dict[str, Any]] = []
        else:
            self.index = self._load_or_create_index()
            self.metadata = self._load_metadata()

            if self.index.ntotal != len(self.metadata):
                with self._lock:
                    self._rebuild_index_from_metadata_embeddings()
                    self.save()

    def _detect_database_backend(self) -> bool:
        try:
            if engine.dialect.name != "postgresql":
                return False

            with engine.begin() as connection:
                extension = connection.execute(
                    text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
                ).scalar()
                table_exists = connection.execute(
                    text("SELECT to_regclass('public.document_chunk_embeddings')")
                ).scalar()
            return bool(extension) and bool(table_exists)
        except Exception:
            return False

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
        if self._database_backend_enabled:
            return

        with self._lock:
            index_dir = os.path.dirname(os.path.abspath(self.index_path)) or "."
            metadata_dir = os.path.dirname(os.path.abspath(self.metadata_path)) or "."
            fd_index, temp_index_path = tempfile.mkstemp(prefix="faiss_index_", suffix=".bin", dir=index_dir)
            fd_metadata, temp_metadata_path = tempfile.mkstemp(
                prefix="faiss_metadata_", suffix=".json", dir=metadata_dir
            )
            try:
                os.close(fd_index)
                faiss.write_index(self.index, temp_index_path)

                with os.fdopen(fd_metadata, "w", encoding="utf-8") as f:
                    json.dump(self.metadata, f, ensure_ascii=False, indent=2)

                self._atomic_replace_with_retry(temp_index_path, self.index_path)
                self._atomic_replace_with_retry(temp_metadata_path, self.metadata_path)
            finally:
                if os.path.exists(temp_index_path):
                    os.remove(temp_index_path)
                if os.path.exists(temp_metadata_path):
                    os.remove(temp_metadata_path)

    def _atomic_replace_with_retry(self, source_path: str, destination_path: str) -> None:
        attempts = 5
        base_delay_seconds = 0.05

        for attempt in range(attempts):
            try:
                os.replace(source_path, destination_path)
                return
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                delay = base_delay_seconds * (2 ** attempt)
                logger.warning(
                    "Atomic replace was temporarily blocked for '%s'. Retrying in %.2fs.",
                    destination_path,
                    delay,
                )
                time.sleep(delay)

    def _rebuild_index_from_metadata_embeddings(self) -> None:
        if self._database_backend_enabled:
            return

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
        if self._database_backend_enabled:
            with engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM document_chunk_embeddings WHERE document_id = :document_id"),
                    {"document_id": int(document_id)},
                )
            return

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

        if self._database_backend_enabled:
            self._upsert_database_embeddings(clean_embeddings, enriched_metadatas)
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
        tenant_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if self._database_backend_enabled:
            return self._search_database(
                query_embedding=query_embedding,
                top_k=top_k,
                case_id=case_id,
                document_id=document_id,
                tenant_id=tenant_id,
            )

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

    def _upsert_database_embeddings(
        self,
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        statement = text(
            """
            INSERT INTO document_chunk_embeddings (
                chunk_id,
                document_id,
                case_id,
                tenant_id,
                filename,
                chunk_index,
                chunk_text,
                embedding
            )
            VALUES (
                :chunk_id,
                :document_id,
                :case_id,
                :tenant_id,
                :filename,
                :chunk_index,
                :chunk_text,
                CAST(:embedding AS vector)
            )
            ON CONFLICT (chunk_id) DO UPDATE SET
                document_id = EXCLUDED.document_id,
                case_id = EXCLUDED.case_id,
                tenant_id = EXCLUDED.tenant_id,
                filename = EXCLUDED.filename,
                chunk_index = EXCLUDED.chunk_index,
                chunk_text = EXCLUDED.chunk_text,
                embedding = EXCLUDED.embedding,
                updated_at = NOW()
            """
        )
        rows = []
        for embedding, metadata in zip(embeddings, metadatas):
            rows.append(
                {
                    "chunk_id": metadata.get("chunk_id"),
                    "document_id": metadata.get("document_id"),
                    "case_id": metadata.get("case_id"),
                    "tenant_id": metadata.get("tenant_id"),
                    "filename": metadata.get("filename"),
                    "chunk_index": metadata.get("chunk_index"),
                    "chunk_text": metadata.get("chunk_text"),
                    "embedding": self._vector_literal(embedding),
                }
            )

        with engine.begin() as connection:
            connection.execute(statement, rows)

    def _search_database(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        case_id: int | None,
        document_id: int | None,
        tenant_id: int | None,
    ) -> list[dict[str, Any]]:
        if not query_embedding:
            return []

        search_k = max(int(top_k) * 10, 30)
        query = text(
            """
            SELECT
                chunk_id,
                document_id,
                case_id,
                tenant_id,
                filename,
                chunk_index,
                chunk_text,
                1 - (embedding <=> CAST(:query_embedding AS vector)) AS semantic_score
            FROM document_chunk_embeddings
            WHERE (:tenant_id IS NULL OR tenant_id = :tenant_id)
              AND (:case_id IS NULL OR case_id = :case_id)
              AND (:document_id IS NULL OR document_id = :document_id)
            ORDER BY embedding <=> CAST(:query_embedding AS vector)
            LIMIT :search_k
            """
        )
        with engine.begin() as connection:
            rows = connection.execute(
                query,
                {
                    "query_embedding": self._vector_literal(query_embedding),
                    "tenant_id": tenant_id,
                    "case_id": case_id,
                    "document_id": document_id,
                    "search_k": search_k,
                },
            ).mappings().all()

        results = []
        for row in rows:
            semantic_score = float(row.get("semantic_score") or 0.0)
            results.append(
                {
                    "chunk_id": row.get("chunk_id"),
                    "document_id": row.get("document_id"),
                    "case_id": row.get("case_id"),
                    "tenant_id": row.get("tenant_id"),
                    "filename": row.get("filename") or "unknown",
                    "chunk_index": row.get("chunk_index"),
                    "chunk_text": row.get("chunk_text") or "",
                    "score": semantic_score,
                    "semantic_score": semantic_score,
                    "bm25_score": 0.0,
                    "retrieval_method": "semantic",
                }
            )
        return results[:top_k]

    @staticmethod
    def _vector_literal(values: list[float]) -> str:
        cleaned = [f"{float(value):.8f}" for value in values]
        return "[" + ",".join(cleaned) + "]"
