from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from sqlalchemy.orm import Session

from backend.models.document import Document
from backend.services.ai.document_insight_service import document_insight_service
from backend.services.ai.legal_text_formatter import LegalTextFormatter


class SummarizationService:
    """
    Advanced legal summarization service for Sprint 6.

    Responsibilities:
    - read processed document text
    - generate structured legal insights
    - persist long summary + short summary
    - persist intelligence metadata
    """

    MIN_TEXT_LENGTH = 120
    MAX_INPUT_CHARS = 18000
    MAX_SHORT_SUMMARY_CHARS = 500

    def get_source_text(self, document: Document) -> str:
        source_text = document.redacted_text or document.extracted_text

        if not source_text or not source_text.strip():
            raise ValueError("Document has no processed text available for summarization.")

        return LegalTextFormatter.prepare_for_summary(source_text)

    def summarize_document(self, db: Session, document: Document) -> Document:
        document.summary_status = "processing"
        document.summary_error = None
        db.commit()
        db.refresh(document)

        try:
            text = self.get_source_text(document)

            if len(text) < self.MIN_TEXT_LENGTH:
                raise ValueError("Processed document text is too short to summarize reliably.")

            bounded_text = text[: self.MAX_INPUT_CHARS]

            temp_document = SimpleNamespace(
                extracted_text=bounded_text,
                redacted_text=None
            )

            insights = document_insight_service.build_insights(temp_document)

            long_summary = insights.get("general_summary", "")
            short_summary = self._generate_short_summary(long_summary)

            now = datetime.utcnow()

            document.summary = long_summary
            document.summary_short = short_summary
            document.summary_status = "completed"
            document.summary_error = None
            document.summary_generated_at = now

            document.document_type = insights.get("document_type")
            document.summary_version = insights.get("summary_version")
            document.summary_source = insights.get("summary_source")
            document.insights_json = document_insight_service.to_json_string(insights)
            document.last_intelligence_run_at = now

            db.commit()
            db.refresh(document)

            return document

        except Exception as exc:
            document.summary_status = "failed"
            document.summary_error = str(exc)
            document.last_intelligence_run_at = datetime.utcnow()

            db.commit()
            db.refresh(document)
            raise

    def regenerate_document_summary(self, db: Session, document: Document) -> Document:
        return self.summarize_document(db=db, document=document)

    def _generate_short_summary(self, summary: str) -> str:
        if not summary:
            return ""

        if len(summary) <= self.MAX_SHORT_SUMMARY_CHARS:
            return summary

        short = summary[: self.MAX_SHORT_SUMMARY_CHARS].rsplit(" ", 1)[0].strip()
        return short + "..."
    

summarization_service = SummarizationService()