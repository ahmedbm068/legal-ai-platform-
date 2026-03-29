from __future__ import annotations

import os

from sqlalchemy.orm import Session

from backend.models.document_chunk import DocumentChunk
from backend.services.ai.chunking_service import chunk_text
from backend.services.ai.extraction_service import extract_text_from_file
from backend.services.ai.text_cleaning_service import normalize_text
from backend.services.storage_service import download_file_to_temp


def process_document_text(document, db: Session) -> str:
    temp_file_path: str | None = None

    try:
        storage_path = getattr(document, "storage_path", None)
        if not storage_path:
            raise ValueError("Document does not have a valid storage_path.")

        temp_file_path = download_file_to_temp(storage_path)

        extracted_text = extract_text_from_file(temp_file_path)
        cleaned_text = normalize_text(extracted_text)

        if not cleaned_text:
            return ""

        document.extracted_text = cleaned_text

        db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document.id
        ).delete(synchronize_session=False)

        chunks = chunk_text(cleaned_text)

        for idx, chunk in enumerate(chunks):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=idx,
                    content=chunk
                )
            )

        db.commit()
        db.refresh(document)

        return cleaned_text
    except Exception:
        db.rollback()
        raise
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass
