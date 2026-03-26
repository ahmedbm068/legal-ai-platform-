from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.deps import get_db, get_current_user
from backend.models.user import User
from backend.models.document import Document
from backend.models.document_entity import DocumentEntity
from backend.services.ai.document_ai_pipeline import DocumentAIPipeline
from backend.services.ai.pii_redaction_service import redact_pii
from backend.api.intelligence_schema import ProcessDocumentResponse, EntityOut


router = APIRouter(prefix="/intelligence", tags=["Intelligence"])


@router.post("/documents/{document_id}/process", response_model=ProcessDocumentResponse)
def process_document_intelligence(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.tenant_id == current_user.tenant_id
        )
        .first()
    )

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    pipeline = DocumentAIPipeline()
    result = pipeline.process_document(document, db)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("message", "Document processing failed")
        )

    db.refresh(document)

    entities = (
        db.query(DocumentEntity)
        .filter(DocumentEntity.document_id == document.id)
        .order_by(DocumentEntity.start_char.asc())
        .all()
    )

    pii_result = redact_pii(document.extracted_text or "")

    return {
        "document_id": document.id,
        "extracted_text_length": len(document.extracted_text or ""),
        "entities": entities,
        "redacted_preview": (document.redacted_text or "")[:500],
        "status": document.processing_status,
        "pii_items_count": len(pii_result["pii_items"])
    }


@router.get("/documents/{document_id}/status")
def get_document_processing_status(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.tenant_id == current_user.tenant_id
        )
        .first()
    )

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "document_id": document.id,
        "status": document.processing_status,
        "error": document.processing_error
    }


@router.get("/documents/{document_id}/entities", response_model=list[EntityOut])
def get_document_entities(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.tenant_id == current_user.tenant_id
        )
        .first()
    )

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    entities = (
        db.query(DocumentEntity)
        .filter(DocumentEntity.document_id == document.id)
        .order_by(DocumentEntity.start_char.asc())
        .all()
    )

    return entities


@router.get("/documents/{document_id}/redacted")
def get_redacted_document_text(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.tenant_id == current_user.tenant_id
        )
        .first()
    )

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "document_id": document.id,
        "status": document.processing_status,
        "redacted_text": document.redacted_text or ""
    }