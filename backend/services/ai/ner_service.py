from __future__ import annotations

import re
from functools import lru_cache


ALLOWED_LABELS = {"PERSON", "ORG", "GPE", "LOC", "DATE", "MONEY"}

BLOCKED_ENTITY_VALUES = {
    "question answering",
    "sample document",
    "document overview",
    "key dates",
    "main parties",
    "recommended next steps",
    "invoice records",
    "warehouse logs",
    "order date",
    "invoice date",
    "invoice due date",
    "invoice number",
    "document type",
    "jurisdiction",
    "payment terms",
    "termination clause",
    "main issues",
    "legal risks",
    "missing evidence",
    "recommended actions",
    "client",
}

BLOCKED_PREFIXES = (
    "this document",
    "prepared for",
    "key dates for",
    "case file",
    "document type",
    "invoice number",
    "invoice date",
    "invoice due date",
    "order date",
    "summary:",
    "overview:",
    "main issues:",
    "legal risks:",
    "missing evidence:",
    "recommended next steps:",
    "recommended actions:",
)

BLOCKED_EXACT_SHORT_VALUES = {
    "v",
    "vs",
    "n/a",
    "none",
    "unknown",
    "yes",
    "no",
    "client",
    "confidential",
    "internal",
    "note",
}

ROLE_WORDS = {
    "landlord",
    "tenant",
    "buyer",
    "seller",
    "lessor",
    "lessee",
    "plaintiff",
    "defendant",
    "claimant",
    "respondent",
    "employer",
    "employee",
    "supplier",
    "recipient",
    "sender",
}

HEADING_WORDS = {
    "overview",
    "summary",
    "document",
    "type",
    "date",
    "dates",
    "issues",
    "risks",
    "actions",
    "evidence",
    "payment",
    "termination",
    "jurisdiction",
    "clause",
    "article",
    "section",
    "client",
    "confidential",
    "internal",
    "note",
    "preliminary",
    "case",
}

CITY_NAMES = {
    "tunis",
    "sfax",
    "sousse",
    "monastir",
    "nabeul",
    "bizerte",
    "kairouan",
    "gabes",
    "medenine",
    "mahdia",
    "gafsa",
    "tozeur",
    "kebili",
    "zaghouan",
    "beja",
    "jendouba",
    "siliana",
    "kef",
    "tataouine",
    "kasserine",
    "manouba",
    "ariana",
    "ben arous",
}

CURRENCY_CODES = {"TND", "USD", "EUR", "GBP", "MAD", "DZD", "QAR", "SAR"}

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
MONEY_PATTERN = re.compile(
    r"(?i)\b(?:USD|EUR|TND|GBP|MAD|DZD|QAR|SAR|\$|€|£)\s?\d[\d,]*(?:\.\d{1,2})?\b"
)
DATE_PATTERN = re.compile(
    r"(?ix)\b("
    r"\d{4}-\d{2}-\d{2}"
    r"|"
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|"
    r"\d{1,2}\s+"
    r"(january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+\d{4}"
    r")\b"
)
ORG_SUFFIX_PATTERN = re.compile(
    r"(?i)\b(SARL|LLC|LTD|INC|GMBH|SA|SAS|BV|PLC|CORP|CORPORATION|COMPANY)\b"
)
BAD_ORG_TAIL_PATTERN = re.compile(
    r"(?i)\b(date|mentioned|confidential|internal|note|preliminary|overview|summary)\b"
)
ORDER_OR_REFERENCE_PATTERN = re.compile(
    r"(?i)\b(order|orders|invoice|case|document|article|section|clause)\b"
)


@lru_cache(maxsize=1)
def _get_nlp():
    import spacy
    return spacy.load("en_core_web_sm")


def _clean_entity_value(value: str) -> str:
    value = value.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    value = re.sub(r"\s+", " ", value)
    value = value.strip(" \n\t-:;,.|/\\")
    value = re.sub(r"\s{2,}", " ", value)
    return value


def _strip_role_suffixes(value: str) -> str:
    cleaned = value

    cleaned = re.sub(
        r"(?i)\s*[-–—:]?\s*(claimant|respondent|buyer|supplier|plaintiff|defendant|landlord|tenant|sender|recipient)\s*/\s*(claimant|respondent|buyer|supplier|plaintiff|defendant|landlord|tenant|sender|recipient)\s*$",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)\s*[-–—:]?\s*(claimant|respondent|buyer|supplier|plaintiff|defendant|landlord|tenant|sender|recipient)\s*$",
        "",
        cleaned,
    )
    cleaned = re.sub(r"(?i)\s+\bv\b\s*\.?\s*$", "", cleaned)
    cleaned = re.sub(r"(?i)\s+\bvs\.?\b\s*$", "", cleaned)
    cleaned = re.sub(r"(?i)'s\b", "", cleaned)

    return _clean_entity_value(cleaned)


def _looks_like_heading(value: str) -> bool:
    lowered = value.lower().strip().rstrip(":")

    if value.strip().endswith(":"):
        return True

    words = [w for w in re.split(r"\s+", lowered) if w]
    if not words:
        return True

    if len(words) <= 4 and all(word in HEADING_WORDS for word in words):
        return True

    return False


def _looks_like_email_or_url(value: str) -> bool:
    if EMAIL_PATTERN.search(value):
        return True
    lowered = value.lower()
    if "http://" in lowered or "https://" in lowered or "www." in lowered:
        return True
    return False


def _looks_like_code_or_reference(value: str) -> bool:
    lowered = value.lower()

    reference_patterns = [
        r"\binv-\d{4}-\d+\b",
        r"\border\s+[a-z0-9\-]+\b",
        r"\borders\s+[a-z0-9\-]+\b",
        r"\bcase\s+(id|no|number)\b",
        r"\border\s+date\b",
        r"\binvoice\s+number\b",
        r"\binvoice\s+date\b",
        r"\binvoice\s+due\s+date\b",
        r"\bdelivery\s+date\s+mentioned\b",
        r"\barticle\s+\d+(\.\d+)?\b",
        r"\bsection\s+\d+(\.\d+)?\b",
        r"\bclause\s+\d+(\.\d+)?\b",
    ]

    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in reference_patterns)


def _looks_like_bad_org_or_person(value: str) -> bool:
    lowered = value.lower()

    if lowered in BLOCKED_EXACT_SHORT_VALUES:
        return True

    if any(fragment in lowered for fragment in BLOCKED_ENTITY_VALUES):
        return True

    if any(lowered.startswith(prefix) for prefix in BLOCKED_PREFIXES):
        return True

    if _looks_like_heading(value):
        return True

    if _looks_like_email_or_url(value):
        return True

    if _looks_like_code_or_reference(value):
        return True

    if re.fullmatch(r"[=\-._/\\\d\s]+", value):
        return True

    if len(value.split()) > 8:
        return True

    blocked_fragments = [
        "invoice number",
        "invoice date",
        "due date",
        "order date",
        "amount due",
        "late penalty",
        "question answering",
        "used to test",
        "sample document",
        "recommended next steps",
        "this case concerns",
        "commercial dispute between",
        "document type",
        "prepared for testing",
        "confidential internal note",
        "date mentioned",
    ]

    if any(fragment in lowered for fragment in blocked_fragments):
        return True

    return False


def _is_valid_person(value: str) -> bool:
    if _looks_like_bad_org_or_person(value):
        return False

    words = value.split()
    if len(words) > 5:
        return False

    if len(words) == 1 and value.lower() in ROLE_WORDS:
        return False

    if ORG_SUFFIX_PATTERN.search(value):
        return False

    if not re.search(r"[A-Za-z]", value):
        return False

    return True


def _is_valid_org(value: str) -> bool:
    if _looks_like_bad_org_or_person(value):
        return False

    if len(value) > 70:
        return False

    if not re.search(r"[A-Za-z]", value):
        return False

    if value.upper() in CURRENCY_CODES:
        return False

    lowered = value.lower()

    if lowered in CITY_NAMES:
        return False

    if BAD_ORG_TAIL_PATTERN.search(value):
        return False

    if ORDER_OR_REFERENCE_PATTERN.search(value) and not ORG_SUFFIX_PATTERN.search(value):
        return False

    if "," in value:
        return False

    return True


def _is_valid_location(value: str) -> bool:
    lowered = value.lower()

    if _looks_like_email_or_url(value):
        return False

    if _looks_like_code_or_reference(value):
        return False

    if lowered in BLOCKED_EXACT_SHORT_VALUES:
        return False

    if lowered in BLOCKED_ENTITY_VALUES:
        return False

    if any(lowered.startswith(prefix) for prefix in BLOCKED_PREFIXES):
        return False

    blocked_location_fragments = [
        "invoice",
        "order",
        "contract",
        "summary",
        "overview",
        "payment",
        "evidence",
        "risk",
        "issue",
        "client",
        "confidential",
    ]
    if any(word in lowered for word in blocked_location_fragments):
        return False

    if re.fullmatch(r"[=\-._/\\\d\s]+", value):
        return False

    return 2 <= len(value) <= 60


def _is_valid_date(value: str) -> bool:
    return bool(DATE_PATTERN.search(value))


def _is_valid_money(value: str) -> bool:
    return bool(MONEY_PATTERN.search(value)) or bool(re.search(r"\b\d[\d,]*(?:\.\d{1,2})?\b", value))


def _is_valid_entity(label: str, value: str) -> bool:
    cleaned = _strip_role_suffixes(_clean_entity_value(value))

    if not cleaned:
        return False

    if label not in ALLOWED_LABELS:
        return False

    if len(cleaned) < 2 or len(cleaned) > 80:
        return False

    if label == "PERSON":
        return _is_valid_person(cleaned)

    if label == "ORG":
        return _is_valid_org(cleaned)

    if label in {"GPE", "LOC"}:
        return _is_valid_location(cleaned)

    if label == "DATE":
        return _is_valid_date(cleaned)

    if label == "MONEY":
        return _is_valid_money(cleaned)

    return False


def _normalize_for_dedup(label: str, value: str) -> tuple[str, str]:
    cleaned = _strip_role_suffixes(_clean_entity_value(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return label, cleaned.lower()


def extract_entities(text: str) -> list[dict]:
    if not text or not text.strip():
        return []

    nlp = _get_nlp()
    doc = nlp(text)

    entities: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for ent in doc.ents:
        cleaned_value = _strip_role_suffixes(_clean_entity_value(ent.text))

        if not _is_valid_entity(ent.label_, cleaned_value):
            continue

        key = _normalize_for_dedup(ent.label_, cleaned_value)
        if key in seen:
            continue
        seen.add(key)

        entities.append({
            "label": ent.label_,
            "value": cleaned_value,
            "start_char": ent.start_char,
            "end_char": ent.end_char,
        })

    return entities