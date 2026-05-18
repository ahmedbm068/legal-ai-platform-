"""AI helpers scoped to the case messaging thread.

Lawyer-facing first: reply suggestions and thread summaries are grounded
in the conversation plus lightweight case context. PII scanning and
attachment insight reuse existing services so behaviour stays consistent
with the rest of the platform.

Everything here is advisory — nothing is auto-sent. Endpoints call these
helpers; the lawyer always reviews and edits before anything leaves.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from backend.models.case import Case
from backend.models.case_message import CaseMessage
from backend.models.document import Document
from backend.services.ai.case_context_service import CaseContextService
from backend.services.ai.document_insight_service import DocumentInsightService
from backend.services.ai.llm_gateway import llm_gateway
from backend.services.ai.pii_redaction_service import redact_pii

_MAX_THREAD_TURNS = 20
_MAX_BODY_CHARS = 600

_DISCLAIMER = (
    "AI-drafted suggestion. Review, verify against the file, and edit before sending."
)


def _transcript(messages: list[CaseMessage]) -> str:
    """Compact, role-tagged transcript of the most recent turns."""
    recent = messages[-_MAX_THREAD_TURNS:]
    lines: list[str] = []
    for m in recent:
        who = "Lawyer" if m.sender_role == "lawyer" else "Client"
        body = (m.body or "").strip()
        if not body and m.attachment_filename:
            body = f"[sent an attachment: {m.attachment_filename}]"
        if len(body) > _MAX_BODY_CHARS:
            body = body[:_MAX_BODY_CHARS] + "…"
        if body:
            lines.append(f"{who}: {body}")
    return "\n".join(lines)


def _case_brief(db: Session, case: Case) -> str:
    """One short paragraph of case context for grounding the model."""
    try:
        ctx = CaseContextService().build_context(
            db=db, tenant_id=case.tenant_id, case_id=case.id
        )
    except Exception:
        ctx = {}

    parts = [f"Matter: {case.title}"]
    if case.description:
        parts.append(f"Summary: {case.description.strip()[:400]}")
    if getattr(case, "jurisdiction_country", None):
        parts.append(f"Jurisdiction: {case.jurisdiction_country}")
    risks = ctx.get("risk_signals") if isinstance(ctx, dict) else None
    if risks:
        flat = ", ".join(str(r) for r in risks[:3] if r)
        if flat:
            parts.append(f"Risk signals: {flat}")
    return " | ".join(parts)


def suggest_replies(
    db: Session, case: Case, messages: list[CaseMessage]
) -> dict[str, Any]:
    """Produce 2-3 reply options for the lawyer, grounded in the thread.

    Falls back to a single safe holding reply if the model is unavailable.
    """
    client = llm_gateway.create_client(tier="standard")
    transcript = _transcript(messages)
    brief = _case_brief(db, case)

    fallback = {
        "suggestions": [
            "Thank you for your message — I've noted this and will review the "
            "case file, then come back to you shortly.",
        ],
        "disclaimer": _DISCLAIMER,
        "model_used": False,
    }

    if client is None or not transcript:
        return fallback

    prompt = (
        "You are assisting a lawyer replying to their client in a private "
        "case messaging thread. Draft 3 short, professional reply options "
        "the lawyer could send. Be concrete and helpful, never invent facts "
        "or legal conclusions, never give a definitive legal opinion, and "
        "keep each reply under 90 words. If the client asked something the "
        "lawyer must decide, propose a reply that acknowledges and sets next "
        "steps rather than guessing.\n\n"
        f"CASE CONTEXT: {brief}\n\n"
        f"CONVERSATION (most recent last):\n{transcript}\n\n"
        'Return ONLY JSON: {"suggestions": ["...", "...", "..."]}'
    )

    try:
        response = client.responses.create(
            model=llm_gateway.resolve_model("standard"),
            input=prompt,
        )
        raw = llm_gateway.extract_output_text(response).strip()
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start : end + 1]) if start != -1 else {}
        suggestions = [
            str(s).strip()
            for s in data.get("suggestions", [])
            if str(s).strip()
        ][:3]
        if not suggestions:
            return fallback
        return {
            "suggestions": suggestions,
            "disclaimer": _DISCLAIMER,
            "model_used": True,
        }
    except Exception:
        return fallback


def summarize_thread(
    db: Session, case: Case, messages: list[CaseMessage]
) -> dict[str, Any]:
    """Concise summary of the conversation for a lawyer picking it up."""
    transcript = _transcript(messages)
    if not transcript:
        return {"summary": "No messages in this conversation yet.", "model_used": False}

    client = llm_gateway.create_client(tier="summary")
    if client is None:
        # Heuristic fallback: last few turns verbatim.
        tail = transcript.split("\n")[-6:]
        return {"summary": "Recent activity:\n" + "\n".join(tail), "model_used": False}

    prompt = (
        "Summarize this lawyer–client conversation for the lawyer in 3-5 "
        "bullet points: what the client wants, what was agreed, open "
        "questions, and any deadlines mentioned. Be factual; do not add "
        "legal advice.\n\n"
        f"Matter: {case.title}\n\n{transcript}"
    )
    try:
        response = client.responses.create(
            model=llm_gateway.resolve_model("summary"),
            input=prompt,
        )
        summary = llm_gateway.extract_output_text(response).strip()
        return {"summary": summary or "Unable to summarize.", "model_used": True}
    except Exception:
        tail = transcript.split("\n")[-6:]
        return {"summary": "Recent activity:\n" + "\n".join(tail), "model_used": False}


def scan_pii(text: str) -> dict[str, Any]:
    """Detect PII in a draft message before it is sent.

    Returns the redaction preview plus a simple flag the UI can act on.
    Thin wrapper over the platform's existing redactor.
    """
    result = redact_pii(text or "")
    items = result.get("pii_items", [])
    return {
        "has_pii": bool(items),
        "pii_items": items,
        "redacted_text": result.get("redacted_text", text or ""),
    }


def analyze_attachment(message: CaseMessage, document: Document | None) -> dict[str, Any]:
    """Lightweight insight for a document shared in chat.

    Uses the existing DocumentInsightService when the attachment was
    persisted as a Document; otherwise returns a filename-based hint.
    """
    if document is not None:
        try:
            insights = DocumentInsightService().build_insights(document)
            return {
                "available": True,
                "document_type": insights.get("document_type"),
                "summary": insights.get("summary") or insights.get("general_summary"),
                "key_points": insights.get("key_points", [])[:5],
                "parties": insights.get("parties", [])[:6],
                "important_dates": insights.get("important_dates", [])[:5],
            }
        except Exception:
            pass

    name = message.attachment_filename or "attachment"
    ctype = message.attachment_content_type or ""
    guess = "document"
    lowered = name.lower()
    if "contract" in lowered:
        guess = "contract"
    elif "invoice" in lowered or "facture" in lowered:
        guess = "invoice"
    elif ctype.startswith("image/"):
        guess = "image / scan"
    return {
        "available": False,
        "document_type": guess,
        "summary": f"Shared file: {name}. Open it to review the full content.",
        "key_points": [],
        "parties": [],
        "important_dates": [],
    }
