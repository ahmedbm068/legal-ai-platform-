"""Shared helpers for the case message thread (client <-> lawyer).

Both the client portal (`/portal/messages`) and the staff app
(`/staff/messages`) read and write the same ``case_messages`` table. The
only per-viewer difference is ``is_mine``: a message is "mine" when its
``sender_role`` matches the role of whoever is looking at the thread.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.models.case_message import CaseMessage


def serialize_message(message: CaseMessage, viewer_role: str) -> dict:
    """Serialize a message from the perspective of ``viewer_role``.

    ``viewer_role`` is "client" or "lawyer".
    """
    return {
        "id": message.id,
        "case_id": message.case_id,
        "sender_role": message.sender_role,
        "sender_name": message.sender_name,
        "body": message.body or "",
        "attachment_filename": message.attachment_filename,
        "attachment_content_type": message.attachment_content_type,
        "attachment_size": message.attachment_size,
        "is_mine": message.sender_role == viewer_role,
        "read_at": message.read_at,
        "created_at": message.created_at,
    }


def mark_messages_read(db: Session, case_id: int, *, from_role: str) -> None:
    """Mark unseen messages authored by ``from_role`` on a case as read.

    When the client opens a thread we clear unseen *lawyer* messages
    (``from_role="lawyer"``); when a lawyer opens it we clear unseen
    *client* messages (``from_role="client"``).
    """
    now = datetime.now(timezone.utc)
    (
        db.query(CaseMessage)
        .filter(
            CaseMessage.case_id == case_id,
            CaseMessage.sender_role == from_role,
            CaseMessage.read_at.is_(None),
        )
        .update({CaseMessage.read_at: now}, synchronize_session=False)
    )
    db.commit()
