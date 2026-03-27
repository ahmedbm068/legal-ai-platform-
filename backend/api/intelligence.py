import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.deps import get_db, get_current_user
from backend.models.user import User
from backend.models.document import Document
from backend.models.document_entity import DocumentEntity
from backend.services.ai.document_ai_pipeline import DocumentAIPipeline
from backend.services.ai.pii_redaction_service import redact_pii
from backend.services.ai.summarization_service import summarization_service
from backend.api.intelligence_schema import (
    ProcessDocumentResponse,
    EntityOut,
    DocumentSummaryOut,
    DocumentSummarizeResponse,
    FullDocumentAnalysisOut,
)


router = APIRouter(prefix="/intelligence", tags=["Intelligence"])


def get_tenant_document_or_404(
    db: Session,
    document_id: int,
    current_user: User
) -> Document:
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.tenant_id == current_user.tenant_id
        )
        .first()
    )

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    return document


@router.post("/documents/{document_id}/process", response_model=ProcessDocumentResponse)
def process_document_intelligence(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = get_tenant_document_or_404(db, document_id, current_user)

    pipeline = DocumentAIPipeline()
    result = pipeline.process_document(document, db)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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
    document = get_tenant_document_or_404(db, document_id, current_user)

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
    document = get_tenant_document_or_404(db, document_id, current_user)

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
    document = get_tenant_document_or_404(db, document_id, current_user)

    return {
        "document_id": document.id,
        "status": document.processing_status,
        "redacted_text": document.redacted_text or ""
    }


@router.post(
    "/documents/{document_id}/summarize",
    response_model=DocumentSummarizeResponse,
    status_code=status.HTTP_200_OK
)
def summarize_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = get_tenant_document_or_404(db, document_id, current_user)

    try:
        updated_document = summarization_service.summarize_document(
            db=db,
            document=document
        )

        return {
            "message": "Document summarized successfully.",
            "data": {
                "document_id": updated_document.id,
                "summary": updated_document.summary,
                "summary_short": updated_document.summary_short,
                "summary_status": updated_document.summary_status,
                "summary_error": updated_document.summary_error,
                "summary_generated_at": updated_document.summary_generated_at,
                "document_type": updated_document.document_type,
                "summary_version": updated_document.summary_version,
                "summary_source": updated_document.summary_source,
            }
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Summary generation failed: {str(exc)}"
        )


@router.get(
    "/documents/{document_id}/summary",
    response_model=DocumentSummaryOut,
    status_code=status.HTTP_200_OK
)
def get_document_summary(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = get_tenant_document_or_404(db, document_id, current_user)

    return {
        "document_id": document.id,
        "summary": document.summary,
        "summary_short": document.summary_short,
        "summary_status": document.summary_status or "not_started",
        "summary_error": document.summary_error,
        "summary_generated_at": document.summary_generated_at,
        "document_type": document.document_type,
        "summary_version": document.summary_version,
        "summary_source": document.summary_source,
    }


@router.post(
    "/documents/{document_id}/summary/regenerate",
    response_model=DocumentSummarizeResponse,
    status_code=status.HTTP_200_OK
)
def regenerate_document_summary(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = get_tenant_document_or_404(db, document_id, current_user)

    try:
        updated_document = summarization_service.regenerate_document_summary(
            db=db,
            document=document
        )

        return {
            "message": "Document summary regenerated successfully.",
            "data": {
                "document_id": updated_document.id,
                "summary": updated_document.summary,
                "summary_short": updated_document.summary_short,
                "summary_status": updated_document.summary_status,
                "summary_error": updated_document.summary_error,
                "summary_generated_at": updated_document.summary_generated_at,
                "document_type": updated_document.document_type,
                "summary_version": updated_document.summary_version,
                "summary_source": updated_document.summary_source,
            }
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Summary regeneration failed: {str(exc)}"
        )


@router.get(
    "/documents/{document_id}/full-analysis",
    response_model=FullDocumentAnalysisOut,
    status_code=status.HTTP_200_OK
)
def get_full_document_analysis(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = get_tenant_document_or_404(db, document_id, current_user)

    entities = (
        db.query(DocumentEntity)
        .filter(DocumentEntity.document_id == document.id)
        .order_by(DocumentEntity.start_char.asc())
        .all()
    )

    insights = None
    if document.insights_json:
        try:
            insights = json.loads(document.insights_json)
        except json.JSONDecodeError:
            insights = None

    return {
        "document_id": document.id,
        "filename": document.filename,
        "processing_status": document.processing_status,
        "processing_error": document.processing_error,
        "summary_status": document.summary_status,
        "summary_error": document.summary_error,
        "extracted_text_length": len(document.extracted_text or ""),
        "redacted_preview": (document.redacted_text or "")[:500],
        "entity_count": len(entities),
        "entities": entities,
        "summary": document.summary,
        "summary_short": document.summary_short,
        "document_type": document.document_type,
        "summary_version": document.summary_version,
        "summary_source": document.summary_source,
        "last_intelligence_run_at": document.last_intelligence_run_at,
        "insights": insights,
    }