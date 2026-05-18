"""Staff-side messaging: lawyers reply to clients on a case thread.

Reads/writes the same ``case_messages`` table as the client portal. Access
is tenant-scoped via the standard staff auth + ``apply_tenant_scope``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.deps import get_current_user, get_db
from backend.core.permissions import apply_tenant_scope
from backend.models.case import Case
from backend.models.case_message import CaseMessage
from backend.models.user import User
from backend.core.ws_manager import room_manager
from backend.services.case_messaging_service import mark_messages_read, serialize_message
from backend.services.storage_service import stream_file_response, upload_file


def _broadcast_message(case_id: int, message: CaseMessage) -> None:
    """Push a freshly-created message to both staff and portal sockets.

    Serialized without a viewer perspective; the client recomputes
    ``is_mine`` from ``sender_role``.
    """
    payload = serialize_message(message, viewer_role="__broadcast__")
    payload.pop("is_mine", None)
    room_manager.broadcast_threadsafe(case_id, {"type": "message", "message": payload})

router = APIRouter(prefix="/staff/messages", tags=["Staff Messaging"])

MESSAGE_ATTACHMENT_MAX_MB = 15


# ── Schemas ────────────────────────────────────────────────────────────────


class StaffThreadSummary(BaseModel):
    case_id: int
    case_title: str
    client_name: str | None = None
    last_message_preview: str | None = None
    last_message_at: str | None = None
    unread_count: int = 0


class StaffThreadResponse(BaseModel):
    case_id: int
    case_title: str
    client_name: str | None = None
    messages: list[dict] = Field(default_factory=list)


class StaffSendMessageRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    body: str = Field(..., min_length=1, max_length=8000)


class StaffUnreadResponse(BaseModel):
    unread_count: int = 0


# ── Helpers ────────────────────────────────────────────────────────────────


def get_staff_case_or_404(db: Session, current_user: User, case_id: int) -> Case:
    query = db.query(Case).filter(Case.id == case_id, Case.deleted_at.is_(None))
    case = apply_tenant_scope(query, Case.tenant_id, current_user).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")
    return case


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/threads", response_model=list[StaffThreadSummary])
def list_threads(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """All cases (in scope) that have at least one message, newest first."""
    case_query = db.query(Case).filter(Case.deleted_at.is_(None))
    case_query = apply_tenant_scope(case_query, Case.tenant_id, current_user)
    cases = {c.id: c for c in case_query.all()}
    if not cases:
        return []

    rows = (
        db.query(
            CaseMessage.case_id,
            func.count(CaseMessage.id).label("total"),
            func.max(CaseMessage.created_at).label("last_at"),
        )
        .filter(CaseMessage.case_id.in_(list(cases.keys())))
        .group_by(CaseMessage.case_id)
        .all()
    )

    summaries: list[dict] = []
    for case_id, _total, last_at in rows:
        case = cases.get(case_id)
        if case is None:
            continue

        last_message = (
            db.query(CaseMessage)
            .filter(CaseMessage.case_id == case_id)
            .order_by(CaseMessage.created_at.desc(), CaseMessage.id.desc())
            .first()
        )
        unread = (
            db.query(func.count(CaseMessage.id))
            .filter(
                CaseMessage.case_id == case_id,
                CaseMessage.sender_role == "client",
                CaseMessage.read_at.is_(None),
            )
            .scalar()
            or 0
        )

        preview = None
        if last_message is not None:
            preview = (last_message.body or "").strip()
            if not preview and last_message.attachment_filename:
                preview = f"📎 {last_message.attachment_filename}"

        summaries.append(
            {
                "case_id": case_id,
                "case_title": case.title,
                "client_name": case.client.name if case.client else None,
                "last_message_preview": preview,
                "last_message_at": last_at.isoformat() if last_at else None,
                "unread_count": int(unread),
            }
        )

    summaries.sort(key=lambda s: s["last_message_at"] or "", reverse=True)
    return summaries


@router.get("/unread-count", response_model=StaffUnreadResponse)
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case_query = db.query(Case.id).filter(Case.deleted_at.is_(None))
    case_query = apply_tenant_scope(case_query, Case.tenant_id, current_user)
    case_ids = [row[0] for row in case_query.all()]
    if not case_ids:
        return {"unread_count": 0}

    count = (
        db.query(func.count(CaseMessage.id))
        .filter(
            CaseMessage.case_id.in_(case_ids),
            CaseMessage.sender_role == "client",
            CaseMessage.read_at.is_(None),
        )
        .scalar()
        or 0
    )
    return {"unread_count": int(count)}


@router.get("/{case_id}", response_model=StaffThreadResponse)
def get_thread(
    case_id: int,
    after_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = get_staff_case_or_404(db, current_user, case_id)

    query = db.query(CaseMessage).filter(CaseMessage.case_id == case.id)
    if after_id is not None:
        # Delta fetch: only messages newer than the client's last known id.
        query = query.filter(CaseMessage.id > after_id)
    messages = query.order_by(
        CaseMessage.created_at.asc(), CaseMessage.id.asc()
    ).all()

    # Lawyer opened it: clear unseen client messages.
    mark_messages_read(db, case.id, from_role="client")

    return {
        "case_id": case.id,
        "case_title": case.title,
        "client_name": case.client.name if case.client else None,
        "messages": [serialize_message(m, viewer_role="lawyer") for m in messages],
    }


@router.post("/{case_id}", status_code=status.HTTP_201_CREATED)
def send_message(
    case_id: int,
    payload: StaffSendMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = get_staff_case_or_404(db, current_user, case_id)

    message = CaseMessage(
        tenant_id=case.tenant_id,
        case_id=case.id,
        portal_account_id=None,
        sender_user_id=current_user.id,
        sender_role="lawyer",
        sender_name=current_user.name,
        body=payload.body.strip(),
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    _broadcast_message(case.id, message)
    return serialize_message(message, viewer_role="lawyer")


@router.post("/{case_id}/attachment", status_code=status.HTTP_201_CREATED)
def send_message_attachment(
    case_id: int,
    body: str = Form(""),
    attachment: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = get_staff_case_or_404(db, current_user, case_id)

    if not attachment or not attachment.filename:
        raise HTTPException(status_code=400, detail="Attachment file is required.")

    attachment.file.seek(0, 2)
    size = attachment.file.tell()
    attachment.file.seek(0)
    max_bytes = MESSAGE_ATTACHMENT_MAX_MB * 1024 * 1024
    if size > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"Attachment too large. Maximum allowed size is {MESSAGE_ATTACHMENT_MAX_MB} MB.",
        )

    object_name = upload_file(attachment.file, attachment.filename, prefix="messages")

    message = CaseMessage(
        tenant_id=case.tenant_id,
        case_id=case.id,
        portal_account_id=None,
        sender_user_id=current_user.id,
        sender_role="lawyer",
        sender_name=current_user.name,
        body=(body or "").strip(),
        attachment_filename=attachment.filename,
        attachment_path=object_name,
        attachment_content_type=attachment.content_type,
        attachment_size=size,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    _broadcast_message(case.id, message)
    return serialize_message(message, viewer_role="lawyer")


@router.get("/{case_id}/attachment/{message_id}")
def download_attachment(
    case_id: int,
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = get_staff_case_or_404(db, current_user, case_id)

    message = (
        db.query(CaseMessage)
        .filter(
            CaseMessage.id == message_id,
            CaseMessage.case_id == case.id,
        )
        .first()
    )
    if not message or not message.attachment_path:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    return stream_file_response(
        message.attachment_path,
        media_type=message.attachment_content_type or "application/octet-stream",
        filename=message.attachment_filename or "attachment",
    )


# ── AI assist (lawyer-facing) ──────────────────────────────────────────────


class PiiScanRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field("", max_length=8000)


def _thread_messages(db: Session, case_id: int) -> list[CaseMessage]:
    return (
        db.query(CaseMessage)
        .filter(CaseMessage.case_id == case_id)
        .order_by(CaseMessage.created_at.asc(), CaseMessage.id.asc())
        .all()
    )


@router.post("/{case_id}/ai/suggest")
def ai_suggest_replies(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Draft 2-3 reply options for the lawyer, grounded in the thread."""
    from backend.services.ai.messaging_ai_service import suggest_replies

    case = get_staff_case_or_404(db, current_user, case_id)
    return suggest_replies(db, case, _thread_messages(db, case.id))


@router.post("/{case_id}/ai/summarize")
def ai_summarize_thread(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Concise summary of the conversation for the lawyer."""
    from backend.services.ai.messaging_ai_service import summarize_thread

    case = get_staff_case_or_404(db, current_user, case_id)
    return summarize_thread(db, case, _thread_messages(db, case.id))


@router.post("/ai/scan-pii")
def ai_scan_pii(
    payload: PiiScanRequest,
    current_user: User = Depends(get_current_user),
):
    """Flag PII in a draft message before it is sent."""
    from backend.services.ai.messaging_ai_service import scan_pii

    return scan_pii(payload.text)


@router.post("/{case_id}/ai/analyze-attachment/{message_id}")
def ai_analyze_attachment(
    case_id: int,
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lightweight insight for a document shared in this thread."""
    from backend.models.document import Document
    from backend.services.ai.messaging_ai_service import analyze_attachment

    case = get_staff_case_or_404(db, current_user, case_id)
    message = (
        db.query(CaseMessage)
        .filter(CaseMessage.id == message_id, CaseMessage.case_id == case.id)
        .first()
    )
    if not message or not message.attachment_filename:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    # Best-effort link to a persisted Document on the same case by filename.
    document = (
        db.query(Document)
        .filter(
            Document.case_id == case.id,
            Document.filename == message.attachment_filename,
        )
        .order_by(Document.id.desc())
        .first()
    )
    return analyze_attachment(message, document)
