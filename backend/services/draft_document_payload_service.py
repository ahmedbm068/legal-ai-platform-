from __future__ import annotations

import html
import re
from typing import Any


DRAFT_INTENT_TOKENS = (
    "draft",
    "write an email",
    "write email",
    "prepare a letter",
    "generate a memo",
    "create a contract",
    "write a client update",
    "prepare a legal note",
    "client update",
    "demand letter",
    "legal memo",
    "contract clause",
    "case note",
)

DRAFT_INTENTS = {
    "draft_client_email_case",
    "draft_internal_email_case",
    "draft_partner_strategy_note_case",
    "draft_negotiation_strategy",
    "draft_contract_redline_case",
}


def is_drafting_request(message: str, parsed_intent: str | None = None, action_category: str | None = None) -> bool:
    if parsed_intent in DRAFT_INTENTS:
        return True
    if action_category == "document_generation":
        return True
    lowered = (message or "").lower()
    return any(token in lowered for token in DRAFT_INTENT_TOKENS)


def infer_document_type(message: str, parsed_intent: str | None = None) -> str:
    lowered = (message or "").lower()
    if parsed_intent == "draft_client_email_case" or "email" in lowered:
        return "email"
    if "memo" in lowered:
        return "legal_memo"
    if "letter" in lowered:
        return "letter"
    if "contract" in lowered or "clause" in lowered:
        return "contract_clause"
    if "client update" in lowered:
        return "client_update"
    if "note" in lowered:
        return "case_note"
    return "general_draft"


def title_for_draft(message: str, parsed_intent: str | None = None) -> str:
    doc_type = infer_document_type(message, parsed_intent)
    titles = {
        "email": "Client Follow-up Email",
        "legal_memo": "Legal Memo",
        "letter": "Legal Letter",
        "contract_clause": "Contract Clause",
        "client_update": "Client Update",
        "case_note": "Case Note",
    }
    return titles.get(doc_type, "Legal Draft")


def text_to_html(answer: str) -> str:
    blocks = [block.strip() for block in re.split(r"\n{2,}", answer or "") if block.strip()]
    if not blocks:
        return "<p></p>"
    html_blocks: list[str] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) > 1 and all(re.match(r"^([-*]|\d+\.)\s+", line) for line in lines):
            ordered = all(re.match(r"^\d+\.\s+", line) for line in lines)
            items = "".join(f"<li>{html.escape(re.sub(r'^([-*]|\\d+\\.)\\s+', '', line))}</li>" for line in lines)
            html_blocks.append(f"<ol>{items}</ol>" if ordered else f"<ul>{items}</ul>")
            continue
        if len(lines) == 1 and re.match(r"^[A-Z][A-Z0-9 /&-]{5,}$", lines[0]):
            html_blocks.append(f"<h2>{html.escape(lines[0])}</h2>")
            continue
        html_blocks.append(f"<p>{html.escape(' '.join(lines))}</p>")
    return "".join(html_blocks)


def build_draft_document_payload(
    *,
    prompt: str,
    answer: str,
    parsed_intent: str | None,
    case_id: int | None,
    sources: list[dict[str, Any]],
    citations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "title": title_for_draft(prompt, parsed_intent),
        "document_type": infer_document_type(prompt, parsed_intent),
        "case_id": case_id,
        "content_html": text_to_html(answer),
        "content_text": answer,
        "content_json": {
            "type": "doc",
            "source": "copilot_draft",
        },
        "citations": citations or [],
        "source_context": {
            "prompt": prompt,
            "sources": sources or [],
        },
    }
