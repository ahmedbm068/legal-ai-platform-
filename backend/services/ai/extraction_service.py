from __future__ import annotations

import os

from pypdf import PdfReader

from backend.core.config import settings
from backend.services.ai.scanned_document_service import scanned_document_service


def _looks_sparse(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return True
    return len(cleaned) < max(1, int(settings.SCANNED_PDF_MIN_NATIVE_TEXT_CHARS))


def extract_text_from_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    pages_text: list[str] = []

    for page in reader.pages:
        text = page.extract_text() or ""
        cleaned = text.strip()
        if cleaned:
            pages_text.append(cleaned)

    return "\n\n".join(pages_text).strip()


def extract_text_from_txt(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read().strip()


def extract_text_from_file(
    file_path: str,
    *,
    filename: str | None = None,
    use_ocr_fallback: bool = False,
) -> str:
    extension = os.path.splitext(file_path)[1].lower()

    if extension == ".pdf":
        extracted_text = extract_text_from_pdf(file_path)
        if use_ocr_fallback and _looks_sparse(extracted_text):
            with open(file_path, "rb") as file_handle:
                pdf_bytes = file_handle.read()
            ocr_result = scanned_document_service.extract_text_from_pdf(
                pdf_bytes=pdf_bytes,
                original_filename=filename or os.path.basename(file_path),
            )
            ocr_text = ocr_result.text.strip()
            if len(ocr_text) > len(extracted_text.strip()):
                return ocr_text
        return extracted_text

    if extension in {".txt", ".md"}:
        return extract_text_from_txt(file_path)

    raise ValueError(f"Unsupported file type for extraction: {extension}")