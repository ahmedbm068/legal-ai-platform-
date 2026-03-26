import re

EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
PHONE_PATTERN = r"\b(?:\+?\d{1,3}[\s\-]?)?(?:\d{2,4}[\s\-]?){2,5}\d\b"
ID_PATTERN = r"\b[A-Z0-9]{6,20}\b"


def redact_pii(text: str) -> dict:
    if not text:
        return {
            "redacted_text": "",
            "pii_items": []
        }

    pii_items = []

    for match in re.finditer(EMAIL_PATTERN, text):
        pii_items.append({
            "type": "EMAIL",
            "value": match.group(0)
        })

    for match in re.finditer(PHONE_PATTERN, text):
        pii_items.append({
            "type": "PHONE",
            "value": match.group(0)
        })

    for match in re.finditer(ID_PATTERN, text):
        pii_items.append({
            "type": "ID",
            "value": match.group(0)
        })

    redacted_text = re.sub(EMAIL_PATTERN, "[REDACTED_EMAIL]", text)
    redacted_text = re.sub(PHONE_PATTERN, "[REDACTED_PHONE]", redacted_text)
    redacted_text = re.sub(ID_PATTERN, "[REDACTED_ID]", redacted_text)

    return {
        "redacted_text": redacted_text,
        "pii_items": pii_items
    }