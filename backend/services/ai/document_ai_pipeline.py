from __future__ import annotations

import os
from typing import Any, Dict

from sqlalchemy.orm import Session

from backend.models.document import Document
from backend.models.document_chunk import DocumentChunk
from backend.models.document_entity import DocumentEntity
from backend.core.config import settings
from backend.services.ai.chunking_service import chunk_text
from backend.services.ai.embedding_service import EmbeddingService
from backend.services.ai.extraction_service import extract_text_from_file
from backend.services.ai.ner_service import extract_entities
from backend.services.ai.pii_redaction_service import redact_pii
from backend.services.ai.text_cleaning_service import normalize_text
from backend.services.ai.vector_store import VectorStore
from backend.services.storage_service import download_file_to_temp


class DocumentAIPipeline:
    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        vector_store: VectorStore | None = None
    ):
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_store = vector_store or VectorStore(dimension=self.embedding_service.dimension)

    def process_document(self, document: Document, db: Session) -> Dict[str, Any]:
        temp_file_path: str | None = None

        try:
            self._mark_processing(db=db, document=document, status_value="processing", error=None)

            temp_file_path = download_file_to_temp(document.storage_path)
            text = extract_text_from_file(
                temp_file_path,
                filename=document.filename,
                use_ocr_fallback=True,
            )
            text = normalize_text(text)

            if not text.strip():
                self._mark_processing(
                    db=db,
                    document=document,
                    status_value="failed",
                    error="No text could be extracted from the file."
                )
                return {
                    "success": False,
                    "message": "No text could be extracted from the file.",
                    "status": document.processing_status
                }

            document.extracted_text = text

            entities = extract_entities(text)
            pii_result = redact_pii(text)
            redacted_text = pii_result["redacted_text"]
            pii_items = pii_result["pii_items"]
            chunks = chunk_text(
                redacted_text,
                chunk_size=max(300, int(settings.CHUNK_SIZE)),
                overlap=max(0, int(settings.CHUNK_OVERLAP)),
            )

            document.redacted_text = redacted_text

            self._replace_entities(db=db, document=document, entities=entities)
            self._replace_chunks(db=db, document=document, chunks=chunks)
            self.vector_store.remove_document_embeddings(document.id)
            self._index_chunks(db=db, document=document)

            self._mark_processing(db=db, document=document, status_value="processed", error=None)

            return {
                "success": True,
                "message": "Document processed successfully.",
                "chunks_count": len(chunks),
                "entities_extracted": len(entities),
                "pii_items_count": len(pii_items),
                "text_length": len(text),
                "status": document.processing_status
            }

        except Exception as exc:
            db.rollback()

            document.processing_status = "failed"
            document.processing_error = str(exc)
            db.commit()
            db.refresh(document)

            return {
                "success": False,
                "message": "Document processing failed.",
                "error": str(exc),
                "status": document.processing_status
            }

        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except OSError:
                    pass

    def _mark_processing(
        self,
        db: Session,
        document: Document,
        *,
        status_value: str,
        error: str | None
    ) -> None:
        document.processing_status = status_value
        document.processing_error = error
        db.commit()
        db.refresh(document)

    def _replace_entities(
        self,
        db: Session,
        document: Document,
        entities: list[dict]
    ) -> None:
        db.query(DocumentEntity).filter(
            DocumentEntity.document_id == document.id
        ).delete()

        entity_rows = [
            DocumentEntity(
                document_id=document.id,
                label=entity["label"],
                value=entity["value"],
                start_char=entity.get("start_char"),
                end_char=entity.get("end_char")
            )
            for entity in entities
        ]

        if entity_rows:
            db.add_all(entity_rows)

        db.commit()

    def _replace_chunks(
        self,
        db: Session,
        document: Document,
        chunks: list[str]
    ) -> None:
        db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document.id
        ).delete()
        db.commit()

        chunk_rows = [
            DocumentChunk(
                document_id=document.id,
                case_id=document.case_id,
                tenant_id=document.tenant_id,
                chunk_index=index,
                content=chunk
            )
            for index, chunk in enumerate(chunks)
        ]

        if chunk_rows:
            db.add_all(chunk_rows)

        db.commit()

    def _index_chunks(self, db: Session, document: Document) -> None:
        saved_chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )

        if not saved_chunks:
            return

        chunk_texts: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for chunk_row in saved_chunks:
            chunk_texts.append(chunk_row.content)
            metadatas.append({
                "chunk_id": chunk_row.id,
                "document_id": document.id,
                "case_id": document.case_id,
                "tenant_id": document.tenant_id,
                "filename": document.filename,
                "chunk_index": chunk_row.chunk_index,
                "chunk_text": chunk_row.content,
            })

        embeddings = self.embedding_service.embed_texts(chunk_texts)
        self.vector_store.add_embeddings(embeddings, metadatas)
