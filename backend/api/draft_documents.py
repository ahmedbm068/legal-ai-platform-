from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query, status
from sqlalchemy.orm import Session

from backend.core.rate_limiter import limiter
from backend.api.draft_document_schema import (
    DraftDocumentActionResponse,
    DraftDocumentAiEditRequest,
    DraftDocumentAiEditResponse,
    DraftDocumentCreate,
    DraftDocumentOut,
    DraftDocumentSendEmailRequest,
    DraftDocumentUpdate,
    DraftDocumentVersionCreate,
    DraftDocumentVersionOut,
)
from backend.core.deps import get_current_user, get_db
from backend.core.llm_call_context import llm_call_context_dep
from backend.core.permissions import require_lawyer
from backend.models.draft_document import DraftDocument
from backend.models.draft_document_version import DraftDocumentVersion
from backend.models.user import User
from backend.services.docx_export_service import docx_export_service
from backend.services.draft_document_service import draft_document_service
from backend.services.editor_ai_service import editor_ai_service
from backend.services.email_send_service import email_send_service
from backend.services.pdf_export_service import pdf_export_service


router = APIRouter(prefix="/draft-documents", tags=["Draft Documents"])


@router.post("", response_model=DraftDocumentOut, status_code=status.HTTP_201_CREATED)
def create_draft_document(
    payload: DraftDocumentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
):
    document = draft_document_service.create_document(db, current_user=current_user, payload=payload)
    return draft_document_service.serialize(document)


@router.get("", response_model=list[DraftDocumentOut])
def list_draft_documents(
    case_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(DraftDocument).filter(
        DraftDocument.tenant_id == draft_document_service.tenant_id(current_user),
        DraftDocument.deleted_at.is_(None),
    )
    if case_id is not None:
        draft_document_service.get_case_or_404(db, current_user=current_user, case_id=case_id)
        query = query.filter(DraftDocument.case_id == case_id)
    rows = query.order_by(DraftDocument.updated_at.desc()).limit(limit).all()
    return [draft_document_service.serialize(row) for row in rows]


@router.get("/{document_id}", response_model=DraftDocumentOut)
def get_draft_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return draft_document_service.serialize(
        draft_document_service.get_document_or_404(db, current_user=current_user, document_id=document_id)
    )


@router.patch("/{document_id}", response_model=DraftDocumentOut)
def update_draft_document(
    document_id: int,
    payload: DraftDocumentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
):
    document = draft_document_service.get_document_or_404(db, current_user=current_user, document_id=document_id)
    updated = draft_document_service.update_document(db, document=document, current_user=current_user, payload=payload)
    return draft_document_service.serialize(updated)


@router.delete("/{document_id}", response_model=DraftDocumentActionResponse)
def delete_draft_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
):
    document = draft_document_service.get_document_or_404(db, current_user=current_user, document_id=document_id)
    deleted = draft_document_service.soft_delete(db, document=document)
    return {"message": "Draft document archived.", "document": draft_document_service.serialize(deleted)}


@router.post("/{document_id}/versions", response_model=DraftDocumentVersionOut, status_code=status.HTTP_201_CREATED)
def create_draft_document_version(
    document_id: int,
    payload: DraftDocumentVersionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
):
    document = draft_document_service.get_document_or_404(db, current_user=current_user, document_id=document_id)
    document.version = int(document.version or 1) + 1
    version = draft_document_service.create_version(
        db,
        document=document,
        current_user=current_user,
        change_summary=payload.change_summary or "Manual version snapshot",
        content_json=payload.content_json,
        content_html=payload.content_html,
        content_text=payload.content_text,
    )
    db.commit()
    db.refresh(version)
    return draft_document_service.serialize_version(version)


@router.get("/{document_id}/versions", response_model=list[DraftDocumentVersionOut])
def list_draft_document_versions(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = draft_document_service.get_document_or_404(db, current_user=current_user, document_id=document_id)
    rows = (
        db.query(DraftDocumentVersion)
        .filter(DraftDocumentVersion.draft_document_id == document.id)
        .order_by(DraftDocumentVersion.version_number.desc(), DraftDocumentVersion.created_at.desc())
        .all()
    )
    return [draft_document_service.serialize_version(row) for row in rows]


@router.post("/{document_id}/ai-edit", response_model=DraftDocumentAiEditResponse)
@limiter.limit("30/minute")
def propose_ai_edit(
    request: Request,
    document_id: int,
    payload: DraftDocumentAiEditRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _llm_ctx: str = Depends(llm_call_context_dep),
):
    document = draft_document_service.get_document_or_404(db, current_user=current_user, document_id=document_id)
    if payload.case_id:
        draft_document_service.get_case_or_404(db, current_user=current_user, case_id=payload.case_id)
    citations = draft_document_service.serialize(document)["citations_json"]
    return editor_ai_service.propose_edit(
        selected_text=payload.selected_text,
        instruction=payload.instruction,
        full_document_context=payload.full_document_context or document.content_text or "",
        citations=citations,
        citation_mode=payload.citation_mode,
    )


@router.post("/{document_id}/export/docx")
@limiter.limit("60/minute")
def export_draft_document_docx(
    request: Request,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = draft_document_service.get_document_or_404(db, current_user=current_user, document_id=document_id)
    serialized = draft_document_service.serialize(document)
    data = docx_export_service.build_docx(
        title=document.title,
        content_html=document.content_html,
        citations=serialized["citations_json"],
    )
    filename = f"{document.title[:80].replace(' ', '_') or 'draft'}.docx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{document_id}/export/pdf")
@limiter.limit("60/minute")
def export_draft_document_pdf(
    request: Request,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = draft_document_service.get_document_or_404(db, current_user=current_user, document_id=document_id)
    serialized = draft_document_service.serialize(document)
    data = pdf_export_service.build_pdf(
        title=document.title,
        content_html=document.content_html,
        citations=serialized["citations_json"],
    )
    filename = f"{document.title[:80].replace(' ', '_') or 'draft'}.pdf"
    return Response(content=data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/{document_id}/send-email", response_model=DraftDocumentActionResponse)
@limiter.limit("10/minute")
def send_draft_document_email(
    request: Request,
    document_id: int,
    payload: DraftDocumentSendEmailRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
):
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Email sending requires explicit confirmation.")
    document = draft_document_service.get_document_or_404(db, current_user=current_user, document_id=document_id)
    channel = email_send_service.send_email(
        to=str(payload.to),
        subject=payload.subject,
        body_html=payload.body_html if payload.body_html is not None else document.content_html,
        body_text=payload.body_text if payload.body_text is not None else document.content_text,
        cc=[str(item) for item in payload.cc],
    )
    document.status = "sent"
    db.commit()
    db.refresh(document)
    return {"message": f"Email {channel} delivery completed.", "document": draft_document_service.serialize(document)}
