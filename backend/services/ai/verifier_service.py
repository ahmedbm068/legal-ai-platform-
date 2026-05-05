"""Phase A1 — Verifier service.

Maps the assembly-layer grounding label + raw signals onto the canonical
``verification_state`` taxonomy used by the lawyer UI and by the Big Agent
trace:

* ``grounded`` — answer is supported by case documents and/or legal sources.
* ``partial``  — answer is partially supported; counsel must verify.
* ``refused``  — too weak to surface; return a problem+json refusal.

This module is intentionally pure (no DB / no LLM / no IO). All decisions
are derived from the structured response payload produced upstream by
``copilot_response_assembly_service``. That keeps it deterministic and
unit-testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


# Canonical verification states surfaced to the frontend / trace.
STATE_GROUNDED = "grounded"
STATE_PARTIAL = "partial"
STATE_REFUSED = "refused"

# URN problem type emitted on refusal — stable contract consumed by the
# lawyer UI to render the "weak grounding" panel instead of the answer.
WEAK_GROUNDING_PROBLEM_TYPE = "urn:lai:weak-grounding"

# Internal labels the assembly service produces (see copilot_response_assembly_service).
_GROUNDING_CASE = "Case-grounded"
_GROUNDING_PARTIAL = "Partial"
_GROUNDING_NONE = "Not grounded"

# Confidence levels we treat as "too weak to surface" when sources are also missing.
_LOW_CONFIDENCE = "low"

# Modes where a hard refusal is appropriate. For drafting/explanation the
# user explicitly asked us to generate text from their own context, so we
# never refuse those — we degrade to ``partial`` instead.
_REFUSABLE_MODES = frozenset({"legal_search", "external", "default", "agent"})

# Intents where the absence of grounded sources should NEVER refuse — these
# are user-driven generation tasks (drafts, plain-language explanations).
_NEVER_REFUSE_INTENTS = frozenset(
    {
        "draft_client_email_case",
        "draft_legal_letter_case",
        "draft_motion_case",
        "draft_contract_case",
        "draft_pleading_case",
        "explain_to_client_case",
        "summarize_case",
        "summarize_document",
        "summarize_global",
    }
)


@dataclass(frozen=True)
class VerificationOutcome:
    """Result of verifying an assembled copilot response."""

    state: str
    reason: str
    should_refuse: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "reason": self.reason,
            "should_refuse": self.should_refuse,
        }


class VerifierService:
    """Stateless verifier — see module docstring."""

    def verify(self, response: Mapping[str, Any]) -> VerificationOutcome:
        """Inspect a copilot response and emit a ``VerificationOutcome``.

        The response payload is the dict returned by the orchestrator /
        assembly service. We tolerate missing keys — every signal is read
        defensively, because partial pipelines (e.g. tests) may not populate
        the full schema.
        """

        grounding = self._read_grounding(response)
        sources_count = self._read_sources_count(response)
        confidence = self._read_confidence(response)
        mode = self._read_str(response, "mode")
        intent = self._read_str(response, "parsed_intent") or self._read_str(response, "intent")

        # Strongest case: explicit "Case-grounded" with at least one source.
        if grounding == _GROUNDING_CASE and sources_count >= 1:
            return VerificationOutcome(
                state=STATE_GROUNDED,
                reason="Case-grounded answer with verifiable sources.",
                should_refuse=False,
            )

        # Hard refusal: only when ALL of the following hold —
        #  * grounding is "Not grounded"
        #  * zero sources
        #  * low confidence
        #  * mode is one of the refusable modes (legal_search / external / default / agent)
        #  * intent is not on the never-refuse list (drafts / explanations)
        if (
            grounding == _GROUNDING_NONE
            and sources_count == 0
            and confidence == _LOW_CONFIDENCE
            and mode in _REFUSABLE_MODES
            and intent not in _NEVER_REFUSE_INTENTS
        ):
            return VerificationOutcome(
                state=STATE_REFUSED,
                reason=(
                    "No grounded evidence was found and the model is not confident — "
                    "answer suppressed to avoid hallucinated legal advice."
                ),
                should_refuse=True,
            )

        # Everything else is partial — answer is shown, but the UI must
        # display the verification banner.
        return VerificationOutcome(
            state=STATE_PARTIAL,
            reason="Answer is partially supported; independent verification required.",
            should_refuse=False,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Defensive readers — never raise, always return a usable type.
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _read_grounding(response: Mapping[str, Any]) -> str:
        # Prefer the explicit top-level grounding label, fall back to the
        # AI-insight block where the assembly service mirrors it.
        explicit = response.get("grounding")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()
        ai_insight = response.get("ai_insight")
        if isinstance(ai_insight, Mapping):
            grounding_type = ai_insight.get("grounding_type")
            if isinstance(grounding_type, str) and grounding_type.strip():
                # "Case-grounded (document-based)" → "Case-grounded"
                return grounding_type.split("(")[0].strip()
        return ""

    @staticmethod
    def _read_sources_count(response: Mapping[str, Any]) -> int:
        sources = response.get("sources")
        if isinstance(sources, list):
            return len(sources)
        return 0

    @staticmethod
    def _read_confidence(response: Mapping[str, Any]) -> str:
        conf = response.get("confidence")
        if isinstance(conf, str) and conf.strip():
            return conf.strip().lower()
        ai_insight = response.get("ai_insight")
        if isinstance(ai_insight, Mapping):
            level = ai_insight.get("confidence_level")
            if isinstance(level, str) and level.strip():
                return level.strip().lower()
        return ""

    @staticmethod
    def _read_str(response: Mapping[str, Any], key: str) -> str:
        value = response.get(key)
        if isinstance(value, str):
            return value.strip()
        return ""


verifier_service = VerifierService()


def build_weak_grounding_problem(
    *,
    detail: str,
    instance: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """Build a problem+json body with the ``urn:lai:weak-grounding`` type.

    Returned dict is JSON-serializable and intended to be wrapped in a
    ``JSONResponse(content=..., media_type='application/problem+json',
    status_code=422)`` by the API layer.
    """

    body: dict[str, Any] = {
        "type": WEAK_GROUNDING_PROBLEM_TYPE,
        "title": "Weak grounding",
        "status": 422,
        "detail": detail,
    }
    if instance:
        body["instance"] = instance
    if reason:
        body["reason"] = reason
    return body


__all__ = [
    "STATE_GROUNDED",
    "STATE_PARTIAL",
    "STATE_REFUSED",
    "WEAK_GROUNDING_PROBLEM_TYPE",
    "VerificationOutcome",
    "VerifierService",
    "verifier_service",
    "build_weak_grounding_problem",
]
