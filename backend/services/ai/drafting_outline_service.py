"""Phase A2 — Drafting v2 outline service.

Builds a deterministic, intent-aware outline BEFORE the full LLM draft is
generated. The lawyer reviews and edits the outline first; only after
confirmation does the orchestrator call the heavy ``copilot_drafting_
execution_service`` to expand each section.

The service is intentionally pure (no DB, no LLM, no IO). It returns the
same shape regardless of network conditions, which makes the "outline
first" flow testable in isolation and immediate in the UI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


# Supported drafting intents. Mirrors `_DRAFTING_INTENTS` in the orchestrator
# but kept local to avoid a runtime import cycle on a pure service.
SUPPORTED_INTENTS: frozenset[str] = frozenset(
    {
        "draft_client_email_case",
        "draft_internal_email_case",
        "draft_partner_strategy_note_case",
        "draft_negotiation_strategy",
        "draft_contract_redline_case",
    }
)


@dataclass(frozen=True)
class OutlineSection:
    """A single section header in the drafting outline."""

    heading: str
    purpose: str
    suggested_citations: tuple[str, ...] = ()
    required: bool = True


@dataclass(frozen=True)
class DraftOutline:
    intent: str
    title: str
    tone: str
    audience: str
    sections: tuple[OutlineSection, ...]
    case_hints: tuple[str, ...] = field(default_factory=tuple)
    jurisdiction: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "title": self.title,
            "tone": self.tone,
            "audience": self.audience,
            "sections": [asdict(section) for section in self.sections],
            "case_hints": list(self.case_hints),
            "jurisdiction": self.jurisdiction,
        }


# ──────────────────────────────────────────────────────────────────────────
# Per-intent templates — single source of truth for outlines.
# ──────────────────────────────────────────────────────────────────────────

_TEMPLATES: dict[str, dict[str, Any]] = {
    "draft_client_email_case": {
        "title": "Client update email",
        "tone": "Professional, plain-language, reassuring",
        "audience": "Client (non-lawyer)",
        "sections": (
            OutlineSection("Subject line", "One sentence summarising the update."),
            OutlineSection("Greeting", "Address the client by their preferred form."),
            OutlineSection(
                "Status summary",
                "Plain-language recap of where the matter stands today.",
            ),
            OutlineSection(
                "What changed",
                "Concrete events since the last contact (filings, hearings, "
                "communications received).",
                suggested_citations=("Case file", "Recent correspondence"),
            ),
            OutlineSection(
                "What we recommend",
                "Concrete next step the client should take or approve.",
                required=True,
            ),
            OutlineSection(
                "Deadlines / next contact",
                "Any client-facing deadline and when we will follow up.",
                required=False,
            ),
            OutlineSection("Sign-off", "Polite professional close."),
        ),
    },
    "draft_internal_email_case": {
        "title": "Internal team email",
        "tone": "Concise, technical, action-oriented",
        "audience": "Colleague / supervising partner",
        "sections": (
            OutlineSection("Subject", "Case ref + 4-word topic."),
            OutlineSection(
                "Issue",
                "Single-paragraph statement of the legal or procedural issue.",
            ),
            OutlineSection(
                "Position so far",
                "What we have already done or argued.",
                suggested_citations=("Filed pleadings", "Internal notes"),
            ),
            OutlineSection(
                "Decision needed",
                "The exact question the recipient must decide.",
            ),
            OutlineSection(
                "Recommended action",
                "Our proposed answer + rationale in 2 sentences.",
            ),
            OutlineSection("Deadline", "When the decision is needed by.", required=False),
        ),
    },
    "draft_partner_strategy_note_case": {
        "title": "Partner strategy memo",
        "tone": "Analytical, evidence-anchored",
        "audience": "Partner / case lead",
        "sections": (
            OutlineSection("Matter snapshot", "Parties, posture, jurisdiction."),
            OutlineSection(
                "Strategic objective",
                "What outcome we are optimising for.",
            ),
            OutlineSection(
                "Key risks",
                "Top 3 substantive or procedural risks.",
                suggested_citations=("Case documents", "Applicable statutes"),
            ),
            OutlineSection(
                "Options analysis",
                "2–3 viable courses of action with trade-offs.",
            ),
            OutlineSection(
                "Recommendation",
                "The option we propose to pursue and why.",
            ),
            OutlineSection(
                "Open questions",
                "Items requiring partner input before execution.",
                required=False,
            ),
        ),
    },
    "draft_negotiation_strategy": {
        "title": "Negotiation strategy note",
        "tone": "Strategic, scenario-driven",
        "audience": "Internal team",
        "sections": (
            OutlineSection("Counterparty profile", "Who they are; their leverage."),
            OutlineSection("Our objectives", "Must-have vs nice-to-have outcomes."),
            OutlineSection(
                "BATNA",
                "Best alternative if no agreement is reached.",
            ),
            OutlineSection(
                "Opening move",
                "First proposal we put on the table and rationale.",
            ),
            OutlineSection(
                "Concession ladder",
                "Ordered list of concessions and what we want in return.",
            ),
            OutlineSection(
                "Walk-away triggers",
                "Conditions under which we end negotiations.",
            ),
        ),
    },
    "draft_contract_redline_case": {
        "title": "Contract redline plan",
        "tone": "Precise, clause-anchored",
        "audience": "Drafting attorney",
        "sections": (
            OutlineSection("Document under review", "Title + version + counterparty."),
            OutlineSection(
                "Critical clauses",
                "Clauses with material legal or commercial impact.",
                suggested_citations=("Original contract", "Standard playbook"),
            ),
            OutlineSection(
                "Proposed redlines",
                "Per-clause edits with rationale.",
            ),
            OutlineSection(
                "Fallback positions",
                "Acceptable alternatives if counterparty rejects.",
            ),
            OutlineSection(
                "Open questions",
                "Items requiring client input.",
                required=False,
            ),
        ),
    },
}


class DraftingOutlineService:
    """Stateless service. See module docstring."""

    def is_supported(self, intent: str) -> bool:
        return intent in SUPPORTED_INTENTS

    def build_outline(
        self,
        *,
        intent: str,
        objective: str | None = None,
        case_context: Mapping[str, Any] | None = None,
        jurisdiction: str | None = None,
    ) -> DraftOutline:
        """Return a deterministic outline for ``intent``.

        Raises ``ValueError`` for unsupported intents — callers must check
        ``is_supported()`` first or handle the exception at the API layer.
        """

        if intent not in _TEMPLATES:
            raise ValueError(f"Unsupported drafting intent: {intent!r}")

        template = _TEMPLATES[intent]
        case_hints = self._extract_case_hints(case_context, objective)

        return DraftOutline(
            intent=intent,
            title=template["title"],
            tone=template["tone"],
            audience=template["audience"],
            sections=template["sections"],
            case_hints=case_hints,
            jurisdiction=(jurisdiction or "").strip().lower() or None,
        )

    @staticmethod
    def _extract_case_hints(
        case_context: Mapping[str, Any] | None,
        objective: str | None,
    ) -> tuple[str, ...]:
        """Pull a small, deterministic set of case-aware hints from context.

        Hints are short bullets the UI can render below the outline so the
        lawyer can verify the outline reflects the actual case facts.
        """

        hints: list[str] = []
        objective_text = (objective or "").strip()
        if objective_text:
            hints.append(f"Objective: {objective_text[:200]}")

        if isinstance(case_context, Mapping):
            case_block = case_context.get("case")
            if isinstance(case_block, Mapping):
                title = str(case_block.get("title") or "").strip()
                if title:
                    hints.append(f"Case: {title[:120]}")
                country = str(case_block.get("jurisdiction_country") or "").strip()
                if country:
                    hints.append(f"Jurisdiction: {country}")
                doc_count = case_block.get("document_count")
                if isinstance(doc_count, int) and doc_count > 0:
                    hints.append(f"{doc_count} case document(s) available")

            risks = case_context.get("risk_signals")
            if isinstance(risks, list):
                for risk in risks[:2]:
                    text = str(risk or "").strip()
                    if text:
                        hints.append(f"Risk: {text[:160]}")

        # Deduplicate while preserving order.
        seen: set[str] = set()
        deduped: list[str] = []
        for hint in hints:
            if hint not in seen:
                seen.add(hint)
                deduped.append(hint)
        return tuple(deduped[:6])


drafting_outline_service = DraftingOutlineService()


__all__ = [
    "DraftOutline",
    "OutlineSection",
    "SUPPORTED_INTENTS",
    "DraftingOutlineService",
    "drafting_outline_service",
]
