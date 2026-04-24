from __future__ import annotations

from typing import Any

from backend.services.ai.legal_trust_models import OutputContractValidationResult


MANDATORY_LEGAL_SECTION_TITLES: tuple[str, ...] = (
    "Issue Identification",
    "Applicable Rule / Law",
    "Application to Facts",
    "Evidence Mapping",
    "Uncertainty / Missing Information",
    "Counter-Arguments / Alternative Interpretations",
    "Risk Assessment (per party)",
    "Recommended Next Steps",
)


class OutputContractValidator:
    MIN_CITATION_COVERAGE = 0.95
    MAX_HALLUCINATION_RATE = 0.05

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(parsed, 1.0))

    @staticmethod
    def _contains_not_found(value: Any) -> bool:
        return "not found in provided documents" in str(value or "").strip().lower()

    def validate_trust_panel(self, payload: dict[str, Any]) -> OutputContractValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if not isinstance(payload, dict):
            return OutputContractValidationResult(
                is_valid=False,
                errors=["Trust panel payload must be an object."],
            )

        if str(payload.get("status") or "").strip().upper() == "INSUFFICIENT_EVIDENCE":
            required_documents = payload.get("required_documents")
            if not str(payload.get("message") or "").strip():
                errors.append("insufficient-evidence response requires message.")
            if not isinstance(required_documents, list) or not required_documents:
                errors.append("insufficient-evidence response requires required_documents.")
            metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
            return OutputContractValidationResult(
                is_valid=not errors,
                errors=errors,
                warnings=["Full legal answer blocked by evidence gate."],
                metrics={
                    "citation_coverage": self._as_float(metrics.get("citation_coverage")),
                    "hallucination_rate": self._as_float(metrics.get("hallucination_rate"), default=1.0),
                    "confidence_score": self._as_float(payload.get("confidence_score")),
                },
                normalized_payload=payload,
            )

        answer = str(payload.get("answer") or "").strip()
        if not answer:
            errors.append("answer is required.")

        sections = payload.get("legal_reasoning_sections")
        if not isinstance(sections, list):
            errors.append("legal_reasoning_sections must be a list.")
            sections = []

        present_titles: set[str] = set()
        for item in sections:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            content = str(item.get("content") or "").strip()
            if title:
                present_titles.add(title)
            if title in MANDATORY_LEGAL_SECTION_TITLES and not content:
                errors.append(f"{title} content is required.")

        for title in MANDATORY_LEGAL_SECTION_TITLES:
            if title not in present_titles:
                errors.append(f"Missing mandatory section: {title}.")

        verified_claims = payload.get("verified_claims")
        unsupported_claims = payload.get("unsupported_claims")
        sentence_mappings = payload.get("sentence_to_source_mapping")
        if not isinstance(verified_claims, list):
            errors.append("verified_claims must be a list.")
            verified_claims = []
        if not isinstance(unsupported_claims, list):
            errors.append("unsupported_claims must be a list.")
            unsupported_claims = []
        if not isinstance(sentence_mappings, list):
            errors.append("sentence_to_source_mapping must be a list.")
            sentence_mappings = []
        if not sentence_mappings:
            errors.append("sentence_to_source_mapping is required for legal trust responses.")

        metrics = payload.get("metrics")
        if not isinstance(metrics, dict):
            metrics = {}

        citation_coverage = self._as_float(metrics.get("citation_coverage"))
        hallucination_rate = self._as_float(metrics.get("hallucination_rate"))
        confidence_score = self._as_float(payload.get("confidence_score"))

        if sentence_mappings and citation_coverage < self.MIN_CITATION_COVERAGE:
            warnings.append(
                f"Citation coverage {citation_coverage:.1%} is below production gate "
                f"{self.MIN_CITATION_COVERAGE:.1%}."
            )
        if unsupported_claims and hallucination_rate > self.MAX_HALLUCINATION_RATE:
            errors.append(
                f"Unsupported-claim rate {hallucination_rate:.1%} exceeds production gate "
                f"{self.MAX_HALLUCINATION_RATE:.1%}."
            )

        if not verified_claims and not any(self._contains_not_found(item.get("content")) for item in sections if isinstance(item, dict)):
            warnings.append("No verified claims were produced; response requires lawyer review.")

        normalized_payload = dict(payload)
        normalized_payload["metrics"] = {
            **metrics,
            "citation_coverage": round(citation_coverage, 4),
            "hallucination_rate": round(hallucination_rate, 4),
            "confidence_score": round(confidence_score, 4),
        }

        return OutputContractValidationResult(
            is_valid=not errors,
            errors=errors,
            warnings=warnings,
            metrics=normalized_payload["metrics"],
            normalized_payload=normalized_payload,
        )


output_contract_validator = OutputContractValidator()
