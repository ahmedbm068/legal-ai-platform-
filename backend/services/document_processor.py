from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models.document_chunk import DocumentChunk
from backend.services.ai.chunking_service import chunk_text
from backend.services.ai.extraction_service import extract_text_from_file
from backend.services.ai.text_cleaning_service import normalize_text
from backend.services.storage_service import download_file_to_temp


def process_document_text(document, db: Session) -> str:
    temp_file_path = download_file_to_temp(document.file_path)

    extracted_text = extract_text_from_file(temp_file_path)
    cleaned_text = normalize_text(extracted_text)

    if not cleaned_text:
        return ""

    document.extracted_text = cleaned_text

    db.query(DocumentChunk).filter(
        DocumentChunk.document_id == document.id
    ).delete()

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