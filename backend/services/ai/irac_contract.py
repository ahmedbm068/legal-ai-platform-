"""Structured-IRAC answer contract for legal-search mode.

Promotes the previously prose-only "5 numbered sections" structure
(case_risks / applicable_law / legal_assessment / missing_facts /
counsel_note) into a Pydantic-validated object so the orchestrator
can fail-soft with a single repair retry and otherwise serve a
provably structured answer the frontend can render as discrete blocks.

The contract is deliberately conservative:
- All fields are required, but ``applicable_law`` and ``missing_facts``
  may be empty lists (a valid grounded answer can legitimately have
  zero applicable articles or zero missing facts).
- ``confidence`` is constrained to the same enum the response-assembly
  service already emits for unstructured answers, so downstream code
  does not need a translation table.
- The model exposes ``to_prose()`` so the existing renderer keeps
  working unchanged when structured mode is on; this also doubles as
  the ``answer`` field on the response dict.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.services.ai.agent_contracts import extract_json_object


logger = logging.getLogger(__name__)


# Per-request slot for the parsed IRAC dict — populated when
# `try_generate_structured_irac` succeeds, consumed by
# `copilot_response_assembly_service` so the dict reaches
# ``response["irac"]`` without changing public function signatures.
_IRAC_PAYLOAD_VAR: ContextVar[dict[str, Any] | None] = ContextVar(
    "irac_payload", default=None
)


def get_pending_irac_payload() -> dict[str, Any] | None:
    return _IRAC_PAYLOAD_VAR.get()


def reset_pending_irac_payload() -> None:
    _IRAC_PAYLOAD_VAR.set(None)


class ArticleCitation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reference: str = Field(..., min_length=1, max_length=240)
    code_family: str | None = Field(default=None, max_length=120)
    summary: str = Field(..., min_length=1, max_length=600)
    applicability: Literal["direct", "partial", "uncertain"] = "direct"


class IRACAnswer(BaseModel):
    """Pydantic schema mirroring the 5-section legal-search prompt."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    case_risks: str = Field(..., min_length=1)
    applicable_law: list[ArticleCitation] = Field(default_factory=list, max_length=12)
    legal_assessment: str = Field(..., min_length=1)
    missing_facts: list[str] = Field(default_factory=list, max_length=20)
    counsel_note: str = Field(..., min_length=1)
    confidence: Literal["high", "medium", "low"] = "medium"

    def to_prose(self, *, include_english_summary: bool = False) -> str:
        """Render the structured payload as the same numbered-section prose
        the legacy free-form path emits — keeps downstream renderers
        (citation extraction, trust badges) working unchanged."""

        applicable = (
            "\n".join(
                f"- {item.reference}"
                + (f" ({item.code_family})" if item.code_family else "")
                + f" — {item.summary}"
                + (
                    f" [applicability: {item.applicability}]"
                    if item.applicability != "direct"
                    else ""
                )
                for item in self.applicable_law
            )
            if self.applicable_law
            else "No directly applicable legal provision was confidently identified in the selected jurisdiction/domain corpus."
        )
        missing = (
            "\n".join(f"- {fact}" for fact in self.missing_facts)
            if self.missing_facts
            else "None flagged at this stage."
        )
        body = (
            "1. Case risks\n"
            f"{self.case_risks.strip()}\n\n"
            "2. Applicable law\n"
            f"{applicable}\n\n"
            "3. Legal assessment\n"
            f"{self.legal_assessment.strip()}\n\n"
            "4. Missing facts / verification needed\n"
            f"{missing}\n\n"
            "5. Counsel note\n"
            f"{self.counsel_note.strip()}"
        )
        if include_english_summary:
            body += "\n\nEnglish summary: structured legal analysis produced from grounded sources."
        return body


IRAC_JSON_SCHEMA_HINT = """{
  "case_risks": "<string — concrete risks present in the case context>",
  "applicable_law": [
    {"reference": "<article ref, e.g. Art. 583 CC>",
     "code_family": "<Code civil | Code de succession | Code IPP | …>",
     "summary": "<one-line plain-language rule summary>",
     "applicability": "direct" | "partial" | "uncertain"}
  ],
  "legal_assessment": "<rule-to-facts mapping; cautious language; flag gaps>",
  "missing_facts": ["<specific fact, document, or evidence to verify>", "..."],
  "counsel_note": "<final judgment note for the lawyer>",
  "confidence": "high" | "medium" | "low"
}"""


def try_parse_irac(raw_text: str) -> IRACAnswer | None:
    """Attempt to parse a raw LLM output into ``IRACAnswer``.

    Returns ``None`` when the text contains no JSON object, the JSON
    is malformed, or schema validation fails. Never raises.
    """
    payload = extract_json_object(raw_text)
    if payload is None:
        return None
    try:
        return IRACAnswer.model_validate(payload)
    except ValidationError as exc:
        logger.debug("irac_validation_failed | err=%s", exc)
        return None


__all__ = [
    "ArticleCitation",
    "IRACAnswer",
    "IRAC_JSON_SCHEMA_HINT",
    "try_parse_irac",
    "get_pending_irac_payload",
    "reset_pending_irac_payload",
    "_IRAC_PAYLOAD_VAR",
]
