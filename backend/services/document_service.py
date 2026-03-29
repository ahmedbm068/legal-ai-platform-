from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from backend.models.document import Document

ProcessingStatus = Literal["pending", "processing", "processed", "failed"]
SummaryStatus = Literal["not_started", "processing", "completed", "failed"]


class DocumentService:
    def get_document_by_id(
        self,
        db: Session,
        document_id: int,
        *,
        tenant_id: int | None = None,
    ) -> Document | None:
        query = db.query(Document).filter(Document.id == document_id)
        if tenant_id is not None:
            query = query.filter(Document.tenant_id == tenant_id)
        return query.first()

    def update_processing_status(
        self,
        db: Session,
        document: Document,
        *,
        status: ProcessingStatus,
        error: str | None = None
    ) -> Document:
        self._apply_and_commit(
            db=db,
            document=document,
            processing_status=status,
            processing_error=error,
        )
        return document

    def update_summary_status(
        self,
        db: Session,
        document: Document,
        *,
        status: SummaryStatus,
        error: str | None = None
    ) -> Document:
        self._apply_and_commit(
            db=db,
            document=document,
            summary_status=status,
            summary_error=error,
        )
        return document

    def _apply_and_commit(self, db: Session, document: Document, **updates) -> None:
        for key, value in updates.items():
            setattr(document, key, value)

        try:
            db.commit()
            db.refresh(document)
        except Exception:
            db.rollback()
            raise


document_service = DocumentService()
