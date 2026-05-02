from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.core.config import settings
from backend.services.ai.agents.claim_validation_agent import claim_validation_agent
from backend.services.ai.agents.article_applicability_agent import article_applicability_agent
from backend.services.ai.agents.contradiction_detection_agent import contradiction_detection_agent
from backend.services.ai.agents.strict_verifier_agent import strict_verifier_agent
from backend.services.ai.legal_trust_models import EvidenceStrength
from backend.services.ai.output_contract_validator import (
    MANDATORY_LEGAL_SECTION_TITLES,
    output_contract_validator,
)


NOT_FOUND = "Not found in provided documents"
INSUFFICIENT_EVIDENCE_STATUS = "INSUFFICIENT_EVIDENCE"
INSUFFICIENT_EVIDENCE_MESSAGE = "Not enough grounded evidence to produce a reliable legal analysis."
DEFAULT_REQUIRED_DOCUMENTS = ["contract", "timeline", "notices", "correspondence"]


@dataclass(frozen=True)
class LegalTrustResult:
    answer: str
    trust_panel: dict[str, Any]
    validation: dict[str, Any]
    claim_validation: dict[str, Any]
    contradiction_detection: dict[str, Any]
    article_applicability: dict[str, Any] | None = None


class LegalTrustService:
    PROMPT_VERSION = "legal_trust_engine_v1"
    RESPONSE_VERSION = "legal_trust_response_v1"

    @staticmethod
    def _confidence_score(label: Any, *, penalty: float = 0.0) -> float:
        token = str(label or "").strip().lower()
        base = 0.82 if token == "high" else 0.64 if token == "medium" else 0.38
        return round(max(0.0, min(base - penalty, 1.0)), 4)

    @staticmethod
    def _compute_confidence_score(
        *,
        citation_coverage: float,
        hallucination_rate: float,
        contradiction_count: int,
        missing_information_count: int,
        has_fact_base: bool,
    ) -> float:
        score = 0.12
        if has_fact_base:
            score += 0.18
        score += max(0.0, min(citation_coverage, 1.0)) * 0.48
        score += max(0.0, 1.0 - min(hallucination_rate, 1.0)) * 0.18
        score -= min(0.18, contradiction_count * 0.06)
        score -= min(0.14, missing_information_count * 0.025)
        return round(max(0.0, min(score, 1.0)), 4)

    @staticmethod
    def _as_list(value: Any, *, limit: int = 8) -> list[Any]:
        if not isinstance(value, list):
            return []
        return value[:limit]

    @staticmethod
    def _string_list(value: Any, *, limit: int = 8) -> list[str]:
        rows: list[str] = []
        for item in LegalTrustService._as_list(value, limit=limit):
            text = str(item or "").strip()
            if text and text not in rows:
                rows.append(text)
        return rows

    @staticmethod
    def _source_key(item: dict[str, Any]) -> str:
        return "|".join(
            str(item.get(key) or "").strip().lower()
            for key in ("document_id", "chunk_id", "chunk_index", "filename", "label", "snippet", "chunk_text")
        )

    def _normalize_sources(self, *, result: dict[str, Any], output_contract: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for source in result.get("sources") or []:
            if not isinstance(source, dict):
                continue
            rows.append(
                {
                    "chunk_id": source.get("chunk_id"),
                    "document_id": source.get("document_id"),
                    "case_id": source.get("case_id"),
                    "filename": source.get("filename") or source.get("label") or "Source",
                    "chunk_index": source.get("chunk_index"),
                    "score": source.get("score", 0.0),
                    "snippet": source.get("snippet") or source.get("chunk_text") or "",
                    "chunk_text": source.get("chunk_text") or source.get("snippet") or "",
                }
            )

        for citation in result.get("citations") or []:
            if not isinstance(citation, dict):
                continue
            rows.append(
                {
                    "chunk_id": citation.get("chunk_id"),
                    "document_id": citation.get("document_id"),
                    "case_id": citation.get("case_id"),
                    "filename": citation.get("label") or "Citation",
                    "chunk_index": citation.get("chunk_index"),
                    "score": citation.get("score", 1.0),
                    "snippet": citation.get("snippet") or "",
                    "chunk_text": citation.get("snippet") or "",
                }
            )

        for source in output_contract.get("relevant_sources") or []:
            if not isinstance(source, dict):
                continue
            rows.append(
                {
                    "chunk_id": source.get("chunk_id"),
                    "document_id": source.get("document_id"),
                    "case_id": source.get("case_id"),
                    "filename": source.get("filename") or source.get("label") or "Relevant source",
                    "chunk_index": source.get("chunk_index"),
                    "score": source.get("score", 1.0),
                    "snippet": source.get("snippet") or "",
                    "chunk_text": source.get("chunk_text") or source.get("snippet") or "",
                }
            )

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            key = self._source_key(row)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return deduped[:20]

    @staticmethod
    def _claim_text_for_validation(*, answer: str, output_contract: dict[str, Any]) -> str:
        parts = [
            answer,
            output_contract.get("legal_issue"),
            output_contract.get("governing_rule"),
            output_contract.get("application"),
            output_contract.get("counter_analysis"),
            *(output_contract.get("confirmed_facts") or []),
            *(output_contract.get("inferred_facts") or []),
        ]
        joined = "\n".join(str(item or "").strip() for item in parts if str(item or "").strip())
        return joined or str(answer or "").strip()

    @staticmethod
    def _has_fact_base(*, sources: list[dict[str, Any]], output_contract: dict[str, Any]) -> bool:
        confirmed_facts = [
            str(item or "").strip()
            for item in (output_contract.get("confirmed_facts") or [])
            if str(item or "").strip()
        ]
        if confirmed_facts:
            return True
        for source in sources:
            if not isinstance(source, dict):
                continue
            has_document = source.get("document_id") is not None or source.get("chunk_id") is not None
            text = str(source.get("chunk_text") or source.get("snippet") or "").strip()
            if has_document and len(text) >= 24:
                return True
        return False

    def _insufficient_evidence_result(
        self,
        *,
        reason: str,
        claim_payload: dict[str, Any],
        contradiction_payload: dict[str, Any] | None = None,
    ) -> LegalTrustResult:
        metrics = {
            "citation_coverage": float(claim_payload.get("citation_coverage") or 0.0),
            "hallucination_rate": float(claim_payload.get("hallucination_rate") or 1.0),
            "total_claims": float(claim_payload.get("total_claims") or 0.0),
            "contradiction_count": float((contradiction_payload or {}).get("contradiction_count") or 0.0),
        }
        trust_panel = {
            "status": INSUFFICIENT_EVIDENCE_STATUS,
            "message": INSUFFICIENT_EVIDENCE_MESSAGE,
            "required_documents": DEFAULT_REQUIRED_DOCUMENTS,
            "reason": reason,
            "answer": INSUFFICIENT_EVIDENCE_MESSAGE,
            "confidence_score": 0.0,
            "evidence_strength": EvidenceStrength.NONE.value,
            "verified_claims": [],
            "unsupported_claims": claim_payload.get("unsupported_claims") or [],
            "sentence_to_source_mapping": claim_payload.get("sentence_to_source_mapping") or [],
            "contradictions": (contradiction_payload or {}).get("contradictions") or [],
            "missing_information": DEFAULT_REQUIRED_DOCUMENTS,
            "risk_summary": {
                "client": "Risk assessment blocked because the evidence base is incomplete.",
                "opposing_party": "Not found in provided documents",
            },
            "legal_reasoning_sections": [],
            "metrics": metrics,
            "response_version": self.RESPONSE_VERSION,
            "prompt_version": self.PROMPT_VERSION,
        }
        validation_result = output_contract_validator.validate_trust_panel(trust_panel)
        return LegalTrustResult(
            answer=INSUFFICIENT_EVIDENCE_MESSAGE,
            trust_panel=validation_result.normalized_payload or trust_panel,
            validation=validation_result.model_dump(mode="json"),
            claim_validation=claim_payload,
            contradiction_detection=contradiction_payload or {"contradictions": [], "contradiction_flags": False},
            article_applicability=None,
        )

    @staticmethod
    def _strength_from_claims(payload: dict[str, Any]) -> EvidenceStrength:
        counts = payload.get("evidence_strength_counts")
        if not isinstance(counts, dict):
            return EvidenceStrength.NONE
        for bucket in (EvidenceStrength.STRONG, EvidenceStrength.MEDIUM, EvidenceStrength.WEAK):
            try:
                if int(counts.get(bucket.value) or 0) > 0:
                    return bucket
            except (TypeError, ValueError):
                continue
        return EvidenceStrength.NONE

    def _section(self, *, title: str, content: str, confidence: str, citation_coverage: float) -> dict[str, Any]:
        clean_content = str(content or "").strip() or NOT_FOUND
        penalty = 0.25 if clean_content == NOT_FOUND else 0.0
        return {
            "title": title,
            "content": clean_content,
            "confidence_score": self._confidence_score(confidence, penalty=penalty),
            "citation_coverage": round(max(0.0, min(float(citation_coverage or 0.0), 1.0)), 4),
        }

    @staticmethod
    def _evidence_mapping_text(mappings: list[dict[str, Any]], *, limit: int = 10) -> str:
        if not mappings:
            return NOT_FOUND
        lines: list[str] = []
        for item in mappings[:limit]:
            sentence = str(item.get("sentence") or "").strip()
            source_label = str(item.get("source_label") or "No matching source").strip()
            strength = str(item.get("evidence_strength") or EvidenceStrength.NONE.value).strip()
            quote = str(item.get("quote") or "").strip() or NOT_FOUND
            lines.append(f"- Claim: {sentence} | Source: {source_label} | Evidence: {strength} | Quote: {quote}")
        return "\n".join(lines) if lines else NOT_FOUND

    @staticmethod
    def _risk_summary(output_contract: dict[str, Any]) -> dict[str, str]:
        risk = output_contract.get("client_risk_summary")
        if not isinstance(risk, dict):
            risk = {}
        client = str(risk.get("summary") or risk.get("legal_risk") or "").strip()
        opposing = str(output_contract.get("opposing_party_risk") or "").strip()
        return {
            "client": client or "Client risk remains provisional pending lawyer review and evidence completion.",
            "opposing_party": opposing or "Opposing-party risk is not found in provided documents.",
        }

    def _build_sections(
        self,
        *,
        output_contract: dict[str, Any],
        claim_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        confidence = str(output_contract.get("confidence") or "low").strip().lower()
        coverage = float(claim_payload.get("citation_coverage") or 0.0)
        risk = self._risk_summary(output_contract)
        missing = self._string_list(output_contract.get("missing_facts"), limit=12)
        next_steps = self._string_list(output_contract.get("next_steps"), limit=12)

        section_map = {
            "Issue Identification": str(output_contract.get("legal_issue") or "").strip(),
            "Applicable Rule / Law": str(output_contract.get("governing_rule") or "").strip(),
            "Application to Facts": str(output_contract.get("application") or "").strip(),
            "Evidence Mapping": self._evidence_mapping_text(claim_payload.get("sentence_to_source_mapping") or []),
            "Uncertainty / Missing Information": "\n".join(f"- {item}" for item in missing) if missing else NOT_FOUND,
            "Counter-Arguments / Alternative Interpretations": str(output_contract.get("counter_analysis") or "").strip(),
            "Risk Assessment (per party)": f"Client: {risk['client']}\nOpposing party: {risk['opposing_party']}",
            "Recommended Next Steps": "\n".join(f"- {item}" for item in next_steps) if next_steps else NOT_FOUND,
        }
        return [
            self._section(
                title=title,
                content=section_map.get(title, NOT_FOUND),
                confidence=confidence,
                citation_coverage=coverage,
            )
            for title in MANDATORY_LEGAL_SECTION_TITLES
        ]

    @staticmethod
    def _render_answer(sections: list[dict[str, Any]]) -> str:
        blocks: list[str] = []
        for index, section in enumerate(sections, start=1):
            title = str(section.get("title") or "").strip()
            content = str(section.get("content") or NOT_FOUND).strip()
            confidence = float(section.get("confidence_score") or 0.0)
            blocks.append(f"{index}. {title}\nConfidence: {confidence:.2f}\n{content}")
        return "\n\n".join(blocks).strip()

    def enforce_response(
        self,
        *,
        result: dict[str, Any],
        output_contract: dict[str, Any],
        case_context: dict[str, Any],
        force_structured_answer: bool = True,
    ) -> LegalTrustResult:
        answer = str(result.get("answer") or "").strip()

        # ── Case-context path: structured answer already generated by the service ──
        # When fallback_reason == "case_context_no_legal_provisions" the caller has
        # already produced a structured 5-section answer from case materials. The
        # trust engine must NOT replace it with an insufficient-evidence message.
        # Return a minimal trust panel that preserves the answer, with confidence=low
        # and evidence_strength=none (so grounding stays Partial / Not grounded).
        fallback_reason_raw = str(result.get("fallback_reason") or "").strip().lower()
        if fallback_reason_raw == "case_context_no_legal_provisions":
            empty_claim_payload: dict[str, Any] = {
                "sentence_to_source_mapping": [],
                "verified_claims": [],
                "unsupported_claims": [],
                "citation_coverage": 0.0,
                "hallucination_rate": 1.0,
            }
            trust_panel = {
                "answer": answer,
                "confidence_score": 0.0,
                "evidence_strength": EvidenceStrength.NONE.value,
                "verified_claims": [],
                "unsupported_claims": [],
                "sentence_to_source_mapping": [],
                "contradictions": [],
                "no_contradictions_statement": "",
                "missing_information": DEFAULT_REQUIRED_DOCUMENTS,
                "risk_summary": {
                    "client": "Case-context risk assessment provided; legal authority verification required.",
                    "opposing_party": "Not found in provided documents",
                },
                "legal_reasoning_sections": [],
                "metrics": {
                    "citation_coverage": 0.0,
                    "hallucination_rate": 1.0,
                    "total_claims": 0.0,
                    "contradiction_count": 0.0,
                },
                "response_version": self.RESPONSE_VERSION,
                "prompt_version": self.PROMPT_VERSION,
            }
            validation_result = output_contract_validator.validate_trust_panel(trust_panel)
            return LegalTrustResult(
                answer=answer,
                trust_panel=validation_result.normalized_payload or trust_panel,
                validation=validation_result.model_dump(mode="json"),
                claim_validation=empty_claim_payload,
                contradiction_detection={"contradictions": [], "contradiction_flags": False},
                article_applicability={},
            )
        # ── End case-context bypass ────────────────────────────────────────────

        sources = self._normalize_sources(result=result, output_contract=output_contract)
        has_fact_base = self._has_fact_base(sources=sources, output_contract=output_contract)

        claim_payload: dict[str, Any] = {
            "sentence_to_source_mapping": [],
            "verified_claims": [],
            "unsupported_claims": [],
            "citation_coverage": 0.0,
            "hallucination_rate": 1.0,
        }
        if settings.LEGAL_TRUST_AGENTS_ENABLED and settings.CLAIM_VALIDATION_AGENT_ENABLED:
            claim_result = claim_validation_agent.validate(
                answer=self._claim_text_for_validation(answer=answer, output_contract=output_contract),
                sources=sources,
            )
            if claim_result.success:
                claim_payload = claim_result.payload

        strict_payload: dict[str, Any] = {}
        if settings.LEGAL_TRUST_AGENTS_ENABLED and settings.CLAIM_VALIDATION_AGENT_ENABLED:
            strict_result = strict_verifier_agent.verify(
                answer=self._claim_text_for_validation(answer=answer, output_contract=output_contract),
                sources=sources,
                min_citation_coverage=float(settings.LEGAL_TRUST_MIN_CITATION_COVERAGE),
                reject_unsupported=bool(settings.LEGAL_TRUST_REJECT_UNSUPPORTED_CLAIMS),
            )
            strict_payload = strict_result.payload
            if not has_fact_base:
                return self._insufficient_evidence_result(
                    reason="empty_fact_base",
                    claim_payload=claim_payload,
                )
            if not strict_result.success:
                return self._insufficient_evidence_result(
                    reason=";".join(strict_payload.get("fail_reasons") or ["strict_verifier_rejected_answer"]),
                    claim_payload=claim_payload,
                )

        contradiction_payload: dict[str, Any] = {"contradictions": [], "contradiction_flags": False}
        if settings.LEGAL_TRUST_AGENTS_ENABLED and settings.CONTRADICTION_DETECTION_AGENT_ENABLED:
            contradiction_result = contradiction_detection_agent.detect(
                output_contract=output_contract,
                case_context=case_context,
                claim_validation_payload=claim_payload,
            )
            if contradiction_result.success:
                contradiction_payload = contradiction_result.payload

        article_applicability_payload = article_applicability_agent.review(
            issue=str(output_contract.get("legal_issue") or ""),
            application=str(output_contract.get("application") or ""),
            sources=sources,
        ).payload

        sections = self._build_sections(output_contract=output_contract, claim_payload=claim_payload)
        structured_answer = self._render_answer(sections)
        risk_summary = self._risk_summary(output_contract)
        evidence_strength = self._strength_from_claims(claim_payload)
        metrics = {
            "citation_coverage": float(claim_payload.get("citation_coverage") or 0.0),
            "hallucination_rate": float(claim_payload.get("hallucination_rate") or 0.0),
            "total_claims": float(claim_payload.get("total_claims") or 0.0),
            "contradiction_count": float(contradiction_payload.get("contradiction_count") or 0.0),
        }
        confidence_score = self._compute_confidence_score(
            citation_coverage=metrics["citation_coverage"],
            hallucination_rate=metrics["hallucination_rate"],
            contradiction_count=int(metrics["contradiction_count"]),
            missing_information_count=len(self._string_list(output_contract.get("missing_facts"), limit=12)),
            has_fact_base=has_fact_base,
        )

        trust_panel = {
            "answer": structured_answer if force_structured_answer else answer,
            "confidence_score": confidence_score,
            "evidence_strength": evidence_strength.value,
            "verified_claims": claim_payload.get("verified_claims") or [],
            "unsupported_claims": claim_payload.get("unsupported_claims") or [],
            "sentence_to_source_mapping": claim_payload.get("sentence_to_source_mapping") or [],
            "contradictions": contradiction_payload.get("contradictions") or [],
            "no_contradictions_statement": contradiction_payload.get("no_contradictions_statement") or "",
            "missing_information": self._string_list(output_contract.get("missing_facts"), limit=12),
            "risk_summary": risk_summary,
            "legal_reasoning_sections": sections,
            "metrics": metrics,
            "strict_verification": strict_payload,
            "article_applicability": article_applicability_payload,
            "response_version": self.RESPONSE_VERSION,
            "prompt_version": self.PROMPT_VERSION,
        }
        validation_result = output_contract_validator.validate_trust_panel(trust_panel)
        trust_panel = validation_result.normalized_payload or trust_panel

        final_answer = trust_panel["answer"] if force_structured_answer else answer
        return LegalTrustResult(
            answer=final_answer,
            trust_panel=trust_panel,
            validation=validation_result.model_dump(mode="json"),
            claim_validation=claim_payload,
            contradiction_detection=contradiction_payload,
            article_applicability=article_applicability_payload,
        )


legal_trust_service = LegalTrustService()
