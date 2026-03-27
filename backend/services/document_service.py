from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models.document import Document


class DocumentService:
    def get_document_by_id(self, db: Session, document_id: int) -> Document | None:
        return db.query(Document).filter(Document.id == document_id).first()

    def update_processing_status(
        self,
        db: Session,
        document: Document,
        *,
        status: str,
        error: str | None = None
    ) -> Document:
        document.processing_status = status
        document.processing_error = error
        db.commit()
        db.refresh(document)
        return document

    def update_summary_status(
        self,
        db: Session,
        document: Document,
        *,
        status: str,
        error: str | None = None
    ) -> Document:
        document.summary_status = status
        document.summary_error = error
        db.commit()
        db.refresh(document)
        return document


document_service = DocumentService()