from __future__ import annotations

from typing import Any

from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.agents.claim_validation_agent import claim_validation_agent


class StrictVerifierAgent(BaseAgent):
    agent_name = "strict_verifier_agent"

    def verify(
        self,
        *,
        answer: str,
        sources: list[dict[str, Any]],
        min_citation_coverage: float = 0.70,
        reject_unsupported: bool = True,
    ) -> AgentResult:
        validation = claim_validation_agent.validate(answer=answer, sources=sources)
        if not validation.success:
            return self.result(
                success=False,
                error=validation.error or "Claim validation failed.",
                payload={
                    "status": "INSUFFICIENT_EVIDENCE",
                    "reason": "no_valid_claim_sentences",
                    "claim_validation": validation.payload,
                },
                trace=validation.trace,
            )

        payload = validation.payload
        coverage = float(payload.get("citation_coverage") or 0.0)
        unsupported_claims = payload.get("unsupported_claims") if isinstance(payload.get("unsupported_claims"), list) else []
        mappings = payload.get("sentence_to_source_mapping") if isinstance(payload.get("sentence_to_source_mapping"), list) else []
        missing_mappings = [
            row for row in mappings
            if isinstance(row, dict) and (
                not row.get("document_id")
                or not row.get("chunk_id")
                or not str(row.get("quote") or "").strip()
                or str(row.get("evidence_strength") or "").upper() == "NONE"
            )
        ]

        fail_reasons: list[str] = []
        if coverage < min_citation_coverage:
            fail_reasons.append("citation_coverage_below_threshold")
        if missing_mappings:
            fail_reasons.append("missing_sentence_source_mapping")
        if reject_unsupported and unsupported_claims:
            fail_reasons.append("unsupported_claims_present")

        status = "VERIFIED" if not fail_reasons else "INSUFFICIENT_EVIDENCE"
        return self.result(
            success=not fail_reasons,
            payload={
                "status": status,
                "fail_reasons": fail_reasons,
                "citation_coverage": coverage,
                "unsupported_claim_count": len(unsupported_claims),
                "missing_mapping_count": len(missing_mappings),
                "claim_validation": payload,
            },
            warnings=fail_reasons,
            trace=[
                f"Strict verifier status={status}; coverage={coverage:.2%}; unsupported={len(unsupported_claims)}; missing_mappings={len(missing_mappings)}."
            ],
        )


strict_verifier_agent = StrictVerifierAgent()
