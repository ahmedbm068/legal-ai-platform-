from __future__ import annotations

import re
from typing import Any


EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"

PHONE_PATTERN = (
    r"(?<![A-Z0-9\-])"
    r"(?:\+?\d{1,3}[\s\-]?)?"
    r"(?:\(?\d{2,4}\)?[\s\-]?)"
    r"(?:\d[\s\-]?){5,10}\d"
    r"(?![A-Z0-9\-])"
)

PERSONAL_ID_PATTERNS = [
    r"\b(?:CIN|ID|Passport|Passport No|National ID|Identity Card)\s*[:#]?\s*[A-Z0-9\-]{5,25}\b",
    r"\b\d{8,14}\b",
]

SAFE_LEGAL_REFERENCE_PATTERNS = [
    r"\bINV-\d{4}-\d+\b",
    r"\b[A-Z]{2,10}-[A-Z]{2,10}-\d{1,6}\b",
    r"\bClause\s+\d+(\.\d+)?\b",
    r"\bArticle\s+\d+(\.\d+)?\b",
    r"\bSection\s+\d+(\.\d+)?\b",
    r"\bCase\s+(ID|No\.?|Number)\s*[:#]?\s*\d+\b",
    r"\bOrder\s+No\.?\s*[:#]?\s*[A-Z0-9\-]+\b",
]


def _collect_safe_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []

    for pattern in SAFE_LEGAL_REFERENCE_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            spans.append(match.span())

    return spans


def _overlaps_safe_span(start: int, end: int, safe_spans: list[tuple[int, int]]) -> bool:
    for safe_start, safe_end in safe_spans:
        if start < safe_end and end > safe_start:
            return True
    return False


def redact_pii(text: str) -> dict[str, Any]:
    if not text:
        return {
            "redacted_text": "",
            "pii_items": []
        }

    pii_items: list[dict[str, str]] = []
    replacements: list[tuple[int, int, str, str]] = []
    safe_spans = _collect_safe_spans(text)

    for match in re.finditer(EMAIL_PATTERN, text):
        replacements.append((match.start(), match.end(), "[REDACTED_EMAIL]", "EMAIL"))

    for match in re.finditer(PHONE_PATTERN, text):
        if _overlaps_safe_span(match.start(), match.end(), safe_spans):
            continue
        replacements.append((match.start(), match.end(), "[REDACTED_PHONE]", "PHONE"))

    for pattern in PERSONAL_ID_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            if _overlaps_safe_span(match.start(), match.end(), safe_spans):
                continue
            replacements.append((match.start(), match.end(), "[REDACTED_ID]", "ID"))

    replacements.sort(key=lambda item: (item[0], item[1]))

    filtered: list[tuple[int, int, str, str]] = []
    last_end = -1

    for start, end, token, pii_type in replacements:
        if start < last_end:
            continue
        filtered.append((start, end, token, pii_type))
        last_end = end

    redacted_parts = []
    cursor = 0

    for start, end, token, pii_type in filtered:
        redacted_parts.append(text[cursor:start])
        redacted_parts.append(token)

        pii_items.append({
            "type": pii_type,
            "value": text[start:end]
        })

        cursor = end

    redacted_parts.append(text[cursor:])

    return {
        "redacted_text": "".join(redacted_parts),
        "pii_items": pii_items
    }