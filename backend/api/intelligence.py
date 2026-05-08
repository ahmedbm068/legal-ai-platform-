import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status

logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session

from backend.core.deps import get_db, get_current_user
from backend.core.permissions import apply_tenant_scope
from backend.models.case import Case
from backend.models.user import User
from backend.models.document import Document
from backend.models.document_entity import DocumentEntity
from backend.services.ai.pii_redaction_service import redact_pii
from backend.services.ai.runtime_services import shared_document_pipeline
from backend.services.legal_date_extraction_service import legal_date_extraction_service
from backend.services.ai.summarization_service import summarization_service
from backend.api.intelligence_schema import (
    ProcessDocumentResponse,
    EntityOut,
    DocumentSummaryOut,
    DocumentSummarizeResponse,
    FullDocumentAnalysisOut,
    CaseReviewTableResponse,
)


router = APIRouter(prefix="/intelligence", tags=["Intelligence"])


def get_tenant_document_or_404(
    db: Session,
    document_id: int,
    current_user: User
) -> Document:
    document_query = db.query(Document).filter(Document.id == document_id)
    document = apply_tenant_scope(document_query, Document.tenant_id, current_user).first()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    return document


def get_tenant_case_or_404(
    db: Session,
    case_id: int,
    current_user: User
) -> Case:
    case_query = db.query(Case).filter(Case.id == case_id)
    case_item = apply_tenant_scope(case_query, Case.tenant_id, current_user).first()

    if not case_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found"
        )

    return case_item


def normalize_insights_payload(raw_insights: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not raw_insights:
        return None

    insights = dict(raw_insights)

    # Backward compatibility with older saved payloads
    if "recommended_next_actions" not in insights:
        insights["recommended_next_actions"] = insights.get("recommended_actions", [])

    # Safe defaults for required list fields
    insights.setdefault("key_points", [])
    insights.setdefault("important_dates", [])
    insights.setdefault("parties_detected", [])
    insights.setdefault("legal_risks", [])
    insights.setdefault("recommended_next_actions", [])

    return insights


@router.post("/documents/{document_id}/process", response_model=ProcessDocumentResponse)
def process_document_intelligence(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = get_tenant_document_or_404(db, document_id, current_user)

    result = shared_document_pipeline.process_document(document, db)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "Document processing failed")
        )

    db.refresh(document)
    calendar_sync = legal_date_extraction_service.extract_events_from_document(db=db, document=document)

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
        "pii_items_count": len(pii_result["pii_items"]),
        "calendar_sync": calendar_sync,
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

    except Exception as exc:  # noqa: BLE001 — summarization pipeline can raise diverse upstream errors
        logger.exception("summary_generation_failed", extra={"document_id": document_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Summary generation failed."
        ) from exc


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

    except Exception as exc:  # noqa: BLE001 — summarization pipeline can raise diverse upstream errors
        logger.exception("summary_regeneration_failed", extra={"document_id": document_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Summary regeneration failed."
        ) from exc


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
            parsed_insights = json.loads(document.insights_json)
            if isinstance(parsed_insights, dict):
                insights = normalize_insights_payload(parsed_insights)
        except json.JSONDecodeError:
            insights = None

    return {
        "document_id": document.id,
        "filename": document.filename,
        "processing_status": document.processing_status,
        "processing_error": document.processing_error,
        "summary_status": document.summary_status or "not_started",
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


@router.get(
    "/cases/{case_id}/review-table",
    response_model=CaseReviewTableResponse,
    status_code=status.HTTP_200_OK,
)
def get_case_review_table(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    case_item = get_tenant_case_or_404(db, case_id, current_user)

    documents = (
        apply_tenant_scope(
            db.query(Document).filter(Document.case_id == case_item.id),
            Document.tenant_id,
            current_user,
        )
        .order_by(Document.upload_timestamp.desc(), Document.id.desc())
        .all()
    )

    rows: list[dict[str, Any]] = []
    for document in documents:
        parsed_insights: dict[str, Any] | None = None
        if document.insights_json:
            try:
                loaded = json.loads(document.insights_json)
                if isinstance(loaded, dict):
                    parsed_insights = normalize_insights_payload(loaded)
            except json.JSONDecodeError:
                parsed_insights = None

        important_dates = []
        for item in (parsed_insights or {}).get("important_dates", [])[:5]:
            if isinstance(item, dict):
                label = str(item.get("label") or "Date").strip()
                value = str(item.get("value") or "").strip()
                if value:
                    important_dates.append(f"{label}: {value}")

        rows.append(
            {
                "document_id": document.id,
                "filename": document.filename,
                "processing_status": document.processing_status,
                "summary_status": document.summary_status,
                "document_type": document.document_type or (parsed_insights or {}).get("document_type"),
                "document_type_confidence": (parsed_insights or {}).get("document_type_confidence"),
                "parties": (parsed_insights or {}).get("parties_detected", [])[:5],
                "important_dates": important_dates,
                "legal_risks": (parsed_insights or {}).get("legal_risks", [])[:5],
                "recommended_actions": (parsed_insights or {}).get("recommended_next_actions", [])[:5],
                "source_kind": "ocr_generated" if document.source_image_batch_id else "uploaded",
            }
        )

    return {"case_id": case_item.id, "row_count": len(rows), "rows": rows}
