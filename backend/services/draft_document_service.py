from __future__ import annotations

import json
from html.parser import HTMLParser
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from backend.models.case import Case
from backend.models.draft_document import DraftDocument
from backend.models.draft_document_version import DraftDocumentVersion
from backend.models.user import User


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"p", "br", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def text(self) -> str:
        return " ".join("".join(self.parts).split())


def _json_dump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _json_load(value: str | None, fallback: Any):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def html_to_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value or "")
    return parser.text()


class DraftDocumentService:
    def tenant_id(self, current_user: User) -> int:
        tenant_id = int(current_user.tenant_id or 0)
        if tenant_id <= 0:
            raise HTTPException(status_code=403, detail="Current user is not attached to a tenant")
        return tenant_id

    def get_case_or_404(self, db: Session, *, current_user: User, case_id: int) -> Case:
        case = (
            db.query(Case)
            .filter(
                Case.id == case_id,
                Case.tenant_id == self.tenant_id(current_user),
                Case.deleted_at.is_(None),
            )
            .first()
        )
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        return case

    def get_document_or_404(self, db: Session, *, current_user: User, document_id: int) -> DraftDocument:
        document = (
            db.query(DraftDocument)
            .filter(
                DraftDocument.id == document_id,
                DraftDocument.tenant_id == self.tenant_id(current_user),
                DraftDocument.deleted_at.is_(None),
            )
            .first()
        )
        if not document:
            raise HTTPException(status_code=404, detail="Draft document not found")
        return document

    def serialize(self, document: DraftDocument) -> dict[str, Any]:
        return {
            "id": document.id,
            "tenant_id": document.tenant_id,
            "case_id": document.case_id,
            "created_by_user_id": document.created_by_user_id,
            "title": document.title,
            "document_type": document.document_type,
            "content_json": _json_load(document.content_json, {}),
            "content_html": document.content_html or "",
            "content_text": document.content_text or "",
            "status": document.status,
            "source_context_json": _json_load(document.source_context_json, {}),
            "citations_json": _json_load(document.citations_json, []),
            "version": document.version,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
            "deleted_at": document.deleted_at,
        }

    def serialize_version(self, version: DraftDocumentVersion) -> dict[str, Any]:
        return {
            "id": version.id,
            "draft_document_id": version.draft_document_id,
            "version_number": version.version_number,
            "content_json": _json_load(version.content_json, {}),
            "content_html": version.content_html or "",
            "content_text": version.content_text or "",
            "created_by_user_id": version.created_by_user_id,
            "change_summary": version.change_summary,
            "created_at": version.created_at,
        }

    def create_document(self, db: Session, *, current_user: User, payload) -> DraftDocument:
        if payload.case_id:
            self.get_case_or_404(db, current_user=current_user, case_id=payload.case_id)
        content_text = payload.content_text or html_to_text(payload.content_html)
        document = DraftDocument(
            tenant_id=self.tenant_id(current_user),
            case_id=payload.case_id,
            created_by_user_id=current_user.id,
            title=payload.title,
            document_type=payload.document_type,
            content_json=_json_dump(payload.content_json),
            content_html=payload.content_html or "",
            content_text=content_text,
            status=payload.status,
            source_context_json=_json_dump(payload.source_context_json),
            citations_json=_json_dump(payload.citations_json),
            version=1,
        )
        db.add(document)
        db.flush()
        self.create_version(db, document=document, current_user=current_user, change_summary="Initial draft")
        db.commit()
        db.refresh(document)
        return document

    def update_document(self, db: Session, *, document: DraftDocument, current_user: User, payload) -> DraftDocument:
        if payload.title is not None:
            document.title = payload.title
        if payload.document_type is not None:
            document.document_type = payload.document_type
        if payload.content_json is not None:
            document.content_json = _json_dump(payload.content_json)
        if payload.content_html is not None:
            document.content_html = payload.content_html
        if payload.content_text is not None:
            document.content_text = payload.content_text
        elif payload.content_html is not None:
            document.content_text = html_to_text(payload.content_html)
        if payload.status is not None:
            document.status = payload.status
        if payload.source_context_json is not None:
            document.source_context_json = _json_dump(payload.source_context_json)
        if payload.citations_json is not None:
            document.citations_json = _json_dump(payload.citations_json)

        if payload.create_version:
            document.version = int(document.version or 1) + 1
            db.flush()
            self.create_version(db, document=document, current_user=current_user, change_summary=payload.change_summary or "Document updated")

        db.commit()
        db.refresh(document)
        return document

    def create_version(
        self,
        db: Session,
        *,
        document: DraftDocument,
        current_user: User,
        change_summary: str | None = None,
        content_json: dict[str, Any] | None = None,
        content_html: str | None = None,
        content_text: str | None = None,
    ) -> DraftDocumentVersion:
        version = DraftDocumentVersion(
            draft_document_id=document.id,
            version_number=int(document.version or 1),
            content_json=_json_dump(content_json if content_json is not None else _json_load(document.content_json, {})),
            content_html=content_html if content_html is not None else (document.content_html or ""),
            content_text=content_text if content_text is not None else (document.content_text or ""),
            created_by_user_id=current_user.id,
            change_summary=change_summary,
        )
        db.add(version)
        return version

    def soft_delete(self, db: Session, *, document: DraftDocument) -> DraftDocument:
        document.deleted_at = func.now()
        document.status = "archived"
        db.commit()
        db.refresh(document)
        return document


draft_document_service = DraftDocumentService()
