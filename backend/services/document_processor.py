from backend.services.storage_service import download_file
from backend.services.ai.extraction_service import extract_text_from_file
from backend.services.ai.chunking_service import chunk_text

from backend.models.document_chunk import DocumentChunk


def process_document_text(document, db):
    file_bytes = download_file(document.filename)

    extracted_text = extract_text_from_file(document.filename, file_bytes)

    if not extracted_text:
        return ""

    document.extracted_text = extracted_text

    db.query(DocumentChunk).filter(
        DocumentChunk.document_id == document.id
    ).delete()

    chunks = chunk_text(extracted_text)

    for idx, chunk in enumerate(chunks):
        db.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=idx,
                content=chunk
            )
        )

    db.commit()

    return extracted_text