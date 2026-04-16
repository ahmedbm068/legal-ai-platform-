from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.core.config import settings
from backend.services.ai.ocr_service import ocr_service

try:
    import fitz
except Exception:  # pragma: no cover - optional dependency guard
    fitz = None


@dataclass
class ScannedPdfPage:
    page_order: int
    filename: str
    image_bytes: bytes
    mime_type: str = "image/png"


@dataclass
class ScannedPdfExtraction:
    text: str
    pages: list[dict[str, Any]] = field(default_factory=list)
    detected_language: str | None = None
    confidence: float = 0.0
    key_fields: list[dict[str, str]] = field(default_factory=list)
    layout_notes: list[str] = field(default_factory=list)
    provider: str = "unavailable"


class ScannedDocumentService:
    def render_pdf_pages(
        self,
        *,
        pdf_bytes: bytes,
        original_filename: str,
    ) -> list[ScannedPdfPage]:
        if not pdf_bytes:
            raise ValueError("No PDF bytes were provided for rendering.")
        if fitz is None:
            raise RuntimeError("PyMuPDF is required for scanned PDF rendering. Install the pymupdf package.")

        try:
            document = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            raise RuntimeError(f"Unable to open the scanned PDF '{original_filename}': {exc}") from exc

        pages: list[ScannedPdfPage] = []
        safe_stem = self._safe_stem(Path(original_filename or "scanned_document").stem)
        render_scale = max(1.0, float(settings.SCANNED_PDF_RENDER_SCALE or 2.0))
        max_pages = max(1, int(settings.SCANNED_PDF_MAX_PAGES or 80))

        try:
            for page_index, page in enumerate(document, start=1):
                if page_index > max_pages:
                    break
                pixmap = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale), alpha=False)
                pages.append(
                    ScannedPdfPage(
                        page_order=page_index,
                        filename=f"{safe_stem}_page_{page_index:03d}.png",
                        image_bytes=pixmap.tobytes("png"),
                    )
                )
        finally:
            document.close()

        if not pages:
            raise RuntimeError(f"No renderable pages were found in the scanned PDF '{original_filename}'.")
        return pages

    def extract_text_from_pdf(
        self,
        *,
        pdf_bytes: bytes,
        original_filename: str,
        instruction: str | None = None,
    ) -> ScannedPdfExtraction:
        pages = self.render_pdf_pages(pdf_bytes=pdf_bytes, original_filename=original_filename)

        combined_text_parts: list[str] = []
        page_payloads: list[dict[str, Any]] = []
        key_fields: list[dict[str, str]] = []
        layout_notes: list[str] = []
        detected_language: str | None = None
        confidence_total = 0.0
        provider = ocr_service.model if ocr_service.available else "unavailable"

        for page in pages:
            ocr_result = ocr_service.extract_from_image_bytes(
                image_bytes=page.image_bytes,
                mime_type=page.mime_type,
                filename=page.filename,
                instruction=instruction
                or "Focus on legal-document text, dates, signatures, stamps, and identifiers.",
            )
            page_text = ocr_result.text.strip()
            if page_text:
                combined_text_parts.append(f"Page {page.page_order}: {page_text}")
            if ocr_result.detected_language and not detected_language:
                detected_language = ocr_result.detected_language
            confidence_total += float(ocr_result.confidence or 0.0)
            for field in ocr_result.key_fields:
                if field not in key_fields:
                    key_fields.append(field)
            for note in ocr_result.layout_notes:
                cleaned_note = str(note).strip()
                if cleaned_note and cleaned_note not in layout_notes:
                    layout_notes.append(cleaned_note)
            page_payloads.append(
                {
                    "page_order": page.page_order,
                    "filename": page.filename,
                    "text": page_text,
                    "language": ocr_result.detected_language,
                    "ocr_confidence": ocr_result.confidence,
                    "key_fields": ocr_result.key_fields,
                    "layout_notes": ocr_result.layout_notes,
                }
            )

        combined_text = "\n\n".join(part for part in combined_text_parts if part.strip()).strip()
        return ScannedPdfExtraction(
            text=combined_text,
            pages=page_payloads,
            detected_language=detected_language,
            confidence=confidence_total / max(1, len(pages)),
            key_fields=key_fields,
            layout_notes=layout_notes,
            provider=provider,
        )

    @staticmethod
    def _safe_stem(value: str) -> str:
        stem = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in (value or "scanned_document"))
        stem = stem.strip("_") or "scanned_document"
        return stem[:80]


scanned_document_service = ScannedDocumentService()