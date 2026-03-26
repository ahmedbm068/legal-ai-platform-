from sqlalchemy.orm import Session

from backend.models.document_chunk import DocumentChunk
from backend.models.document import Document


def lexical_search_documents(db: Session, tenant_id: int, query: str):
    normalized_query = query.strip()
    if not normalized_query:
        return []

    rows = (
        db.query(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .filter(Document.tenant_id == tenant_id)
        .filter(DocumentChunk.content.ilike(f"%{normalized_query}%"))
        .all()
    )

    results = []

    for chunk, document in rows:
        content_lower = chunk.content.lower()
        query_lower = normalized_query.lower()

        occurrence_count = content_lower.count(query_lower)
        idx = content_lower.find(query_lower)

        if idx >= 0:
            start = max(0, idx - 80)
            end = min(len(chunk.content), idx + len(normalized_query) + 80)
            snippet = chunk.content[start:end]
        else:
            snippet = chunk.content[:160]

        results.append({
            "document_id": document.id,
            "filename": document.filename,
            "matched_text": snippet,
            "score": occurrence_count
        })

    results.sort(key=lambda item: item["score"], reverse=True)

    return [
        {
            "document_id": item["document_id"],
            "filename": item["filename"],
            "matched_text": item["matched_text"]
        }
        for item in results
    ]