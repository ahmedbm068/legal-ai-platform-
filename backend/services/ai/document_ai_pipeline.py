import os

from sqlalchemy.orm import Session

from backend.models.document import Document
from backend.models.document_chunk import DocumentChunk
from backend.models.document_entity import DocumentEntity

from backend.services.ai.extraction_service import extract_text_from_pdf
from backend.services.ai.chunking_service import chunk_text
from backend.services.ai.embedding_service import EmbeddingService
from backend.services.ai.vector_store import VectorStore
from backend.services.ai.ner_service import extract_entities
from backend.services.ai.pii_redaction_service import redact_pii
from backend.services.ai.text_cleaning_service import normalize_text
from backend.services.storage_service import download_file_to_temp


class DocumentAIPipeline:
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStore(dimension=384)

    def process_document(self, document: Document, db: Session) -> dict:
        temp_file_path = None

        try:
            document.processing_status = "processing"
            document.processing_error = None
            db.commit()

            temp_file_path = download_file_to_temp(document.storage_path)

            text = extract_text_from_pdf(temp_file_path)
            text = normalize_text(text)

            if not text:
                document.processing_status = "failed"
                document.processing_error = "No text could be extracted from the PDF."
                db.commit()

                return {
                    "success": False,
                    "message": document.processing_error,
                    "status": document.processing_status
                }

            document.extracted_text = text

            entities = extract_entities(text)

            db.query(DocumentEntity).filter(
                DocumentEntity.document_id == document.id
            ).delete()

            entity_rows = [
                DocumentEntity(
                    document_id=document.id,
                    label=e["label"],
                    value=e["value"],
                    start_char=e["start_char"],
                    end_char=e["end_char"]
                )
                for e in entities
            ]
            db.add_all(entity_rows)

            pii_result = redact_pii(text)
            redacted_text = pii_result["redacted_text"]
            pii_items = pii_result["pii_items"]

            document.redacted_text = redacted_text

            chunks = chunk_text(redacted_text)

            db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document.id
            ).delete()

            chunk_rows = []
            metadatas = []

            for i, chunk in enumerate(chunks):
                chunk_rows.append(
                    DocumentChunk(
                        document_id=document.id,
                        chunk_index=i,
                        content=chunk
                    )
                )

                metadatas.append({
                    "document_id": document.id,
                    "case_id": document.case_id,
                    "tenant_id": document.tenant_id,
                    "filename": document.filename,
                    "chunk_index": i,
                    "chunk_text": chunk,
                })

            db.add_all(chunk_rows)

            if chunks:
                embeddings = self.embedding_service.embed_texts(chunks)
                self.vector_store.add_embeddings(embeddings, metadatas)

            document.processing_status = "processed"
            document.processing_error = None
            db.commit()

            return {
                "success": True,
                "message": "Document processed successfully.",
                "chunks_count": len(chunks),
                "entities_extracted": len(entities),
                "pii_items_count": len(pii_items),
                "text_length": len(text),
                "status": document.processing_status
            }

        except Exception as e:
            db.rollback()
            document.processing_status = "failed"
            document.processing_error = str(e)
            db.commit()

            return {
                "success": False,
                "message": "Document processing failed.",
                "error": str(e),
                "status": document.processing_status
            }

        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)