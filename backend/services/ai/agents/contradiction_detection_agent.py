from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.core.config import settings
from backend.services.ai.agent_contracts import validate_json_model
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.llm_gateway import llm_gateway
from backend.services.ai.legal_trust_models import ContradictionRecord, ContradictionSourceReference


DATE_PATTERNS = (
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b\d{2}/\d{2}/\d{4}\b",
    r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b",
)
AMOUNT_PATTERNS = (
    r"\b(?:TND|EUR|USD)\s?\d{1,3}(?:[\s,]\d{3})*(?:\.\d{2})?\b",
    r"\b\d{1,3}(?:[\s,]\d{3})*(?:\.\d{2})?\s?(?:TND|EUR|USD|DINAR|dinar|euros?|dollars?)\b",
)


class _LLMContradictionRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    contradiction_type: str = "legal_interpretation_conflict"
    description: str = ""
    severity_score: float = Field(default=0.5, ge=0.0, le=1.0)
    conflicting_sources: list[str] = Field(default_factory=list)


class _LLMContradictionContract(BaseModel):
    model_config = ConfigDict(extra="ignore")

    contradictions: list[_LLMContradictionRow] = Field(default_factory=list)


class ContradictionDetectionAgent(BaseAgent):
    agent_name = "contradiction_detection_agent"

    PROMPT = """You are the ContradictionDetectionAgent in a legal AI trust pipeline.

Detect explicit contradictions and output JSON only.
Target categories:
- conflicting_dates
- mismatched_financial_amounts
- sla_inconsistency
- legal_interpretation_conflict
- unsupported_claim_conflict

Rules:
- Be strict and evidence-grounded.
- Do not fabricate contradictions.
- If uncertain, lower severity.
"""

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.resolve_model("standard")

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip())

    @staticmethod
    def _normalize_list(values: Any, *, limit: int = 10) -> list[str]:
        if not isinstance(values, list):
            return []
        rows: list[str] = []
        for item in values:
            cleaned = ContradictionDetectionAgent._normalize_text(item)
            if cleaned and cleaned not in rows:
                rows.append(cleaned)
            if len(rows) >= limit:
                break
        return rows

    @staticmethod
    def _extract_dates(text: str) -> list[str]:
        dates: list[str] = []
        raw = str(text or "")
        for pattern in DATE_PATTERNS:
            for match in re.findall(pattern, raw):
                date_value = str(match).strip()
                if date_value and date_value not in dates:
                    dates.append(date_value)
        return dates

    @staticmethod
    def _extract_amounts(text: str) -> list[str]:
        amounts: list[str] = []
        raw = str(text or "")
        for pattern in AMOUNT_PATTERNS:
            for match in re.findall(pattern, raw):
                amount = str(match).strip()
                if amount and amount not in amounts:
                    amounts.append(amount)
        return amounts

    @staticmethod
    def _parse_date(value: str) -> datetime | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _make_source_ref(*, label: str, snippet: str = "") -> dict[str, Any]:
        return ContradictionSourceReference(
            source_label=label or "Source",
            snippet=snippet[:300],
        ).model_dump(mode="json")

    def _detect_timeline_conflicts(
        self,
        *,
        timeline_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        contradictions: list[dict[str, Any]] = []
        by_event: dict[str, set[str]] = {}
        for row in timeline_rows:
            event = self._normalize_text(row.get("label") or row.get("event_type") or row.get("event"))
            date_text = self._normalize_text(row.get("date") or row.get("created_at") or "")
            if not event or not date_text:
                continue
            dates = self._extract_dates(date_text)
            if not dates:
                parsed = self._parse_date(date_text)
                if parsed is not None:
                    dates = [parsed.strftime("%Y-%m-%d")]
            if not dates:
                continue
            key = event.lower()
            by_event.setdefault(key, set()).update(dates)

        for event, date_set in by_event.items():
            if len(date_set) <= 1:
                continue
            sorted_dates = sorted(date_set)
            contradictions.append(
                ContradictionRecord(
                    contradiction_type="conflicting_dates",
                    description=f"Event '{event}' appears with conflicting dates: {', '.join(sorted_dates)}.",
                    conflicting_sources=[
                        ContradictionSourceReference(source_label="fact_timeline", snippet=f"{event} -> {', '.join(sorted_dates)}")
                    ],
                    severity_score=0.85,
                ).model_dump(mode="json")
            )

        return contradictions

    def _detect_amount_conflicts(
        self,
        *,
        claim_validation_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        contradictions: list[dict[str, Any]] = []
        mappings = claim_validation_payload.get("sentence_to_source_mapping")
        if not isinstance(mappings, list):
            return contradictions

        payment_sentences: list[dict[str, Any]] = []
        for row in mappings:
            if not isinstance(row, dict):
                continue
            sentence = self._normalize_text(row.get("sentence"))
            lowered = sentence.lower()
            if not any(token in lowered for token in ("payment", "invoice", "amount", "damages", "fee", "price", "compensation")):
                continue
            amounts = self._extract_amounts(sentence)
            if not amounts:
                continue
            payment_sentences.append({"sentence": sentence, "amounts": amounts, "source": row})

        unique_amounts: set[str] = set()
        for row in payment_sentences:
            unique_amounts.update(row["amounts"])

        if len(unique_amounts) >= 2:
            source_refs: list[ContradictionSourceReference] = []
            for row in payment_sentences[:4]:
                source = row.get("source") if isinstance(row.get("source"), dict) else {}
                source_refs.append(
                    ContradictionSourceReference(
                        source_label=self._normalize_text(source.get("source_label") or "claim_mapping"),
                        snippet=row["sentence"][:300],
                        document_id=source.get("document_id") if isinstance(source.get("document_id"), int) else None,
                        chunk_id=source.get("chunk_id") if isinstance(source.get("chunk_id"), int) else None,
                    )
                )
            contradictions.append(
                ContradictionRecord(
                    contradiction_type="mismatched_financial_amounts",
                    description=(
                        "Potential financial inconsistency detected across claim sentences with different amounts: "
                        + ", ".join(sorted(unique_amounts)[:5])
                    ),
                    conflicting_sources=source_refs,
                    severity_score=0.78,
                ).model_dump(mode="json")
            )

        return contradictions

    def _detect_source_fact_conflicts(
        self,
        *,
        output_contract: dict[str, Any],
    ) -> list[dict[str, Any]]:
        contradictions: list[dict[str, Any]] = []
        sources = output_contract.get("relevant_sources")
        if not isinstance(sources, list):
            return contradictions

        date_rows: list[dict[str, Any]] = []
        amount_rows: list[dict[str, Any]] = []
        for source in sources:
            if not isinstance(source, dict):
                continue
            label = self._normalize_text(source.get("filename") or source.get("label") or "source")
            snippet = self._normalize_text(source.get("chunk_text") or source.get("snippet") or "")
            if not snippet:
                continue
            lowered = snippet.lower()
            for date in self._extract_dates(snippet):
                if any(marker in lowered for marker in ("effective", "notice", "deadline", "due", "delivery", "termination")):
                    date_rows.append({"value": date, "label": label, "snippet": snippet})
            for amount in self._extract_amounts(snippet):
                if any(marker in lowered for marker in ("payment", "invoice", "amount", "damages", "fee", "price", "penalty", "compensation")):
                    amount_rows.append({"value": amount, "label": label, "snippet": snippet})

        unique_dates = {row["value"] for row in date_rows}
        if len(unique_dates) >= 2 and len(date_rows) >= 2:
            contradictions.append(
                ContradictionRecord(
                    contradiction_type="conflicting_dates",
                    description="Potential date inconsistency detected across retrieved evidence: " + ", ".join(sorted(unique_dates)[:6]),
                    conflicting_sources=[
                        ContradictionSourceReference(source_label=row["label"], snippet=row["snippet"][:260])
                        for row in date_rows[:4]
                    ],
                    severity_score=0.68,
                ).model_dump(mode="json")
            )

        unique_amounts = {row["value"] for row in amount_rows}
        if len(unique_amounts) >= 2 and len(amount_rows) >= 2:
            contradictions.append(
                ContradictionRecord(
                    contradiction_type="mismatched_financial_amounts",
                    description="Potential amount inconsistency detected across retrieved evidence: " + ", ".join(sorted(unique_amounts)[:6]),
                    conflicting_sources=[
                        ContradictionSourceReference(source_label=row["label"], snippet=row["snippet"][:260])
                        for row in amount_rows[:4]
                    ],
                    severity_score=0.72,
                ).model_dump(mode="json")
            )

        return contradictions

    def _detect_sla_conflicts(
        self,
        *,
        claim_validation_payload: dict[str, Any],
        case_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        contradictions: list[dict[str, Any]] = []
        text_rows: list[str] = []

        mappings = claim_validation_payload.get("sentence_to_source_mapping")
        if isinstance(mappings, list):
            for row in mappings:
                if isinstance(row, dict):
                    text_rows.append(self._normalize_text(row.get("sentence")))

        for signal in case_context.get("risk_signals") or []:
            text_rows.append(self._normalize_text(signal))

        has_sla = any("sla" in row.lower() or "service level" in row.lower() for row in text_rows)
        if not has_sla:
            return contradictions

        has_met = any(
            any(token in row.lower() for token in ("sla met", "compliant", "fulfilled sla", "on target"))
            for row in text_rows
        )
        has_missed = any(
            any(token in row.lower() for token in ("sla missed", "breach", "failed sla", "underperformance", "non-compliance"))
            for row in text_rows
        )

        if has_met and has_missed:
            contradictions.append(
                ContradictionRecord(
                    contradiction_type="sla_inconsistency",
                    description="SLA posture appears inconsistent: both compliance and breach language are present.",
                    conflicting_sources=[
                        ContradictionSourceReference(source_label="risk_signals", snippet="SLA compliance and breach indicators coexist."),
                    ],
                    severity_score=0.72,
                ).model_dump(mode="json")
            )

        return contradictions

    def _detect_legal_interpretation_conflicts(
        self,
        *,
        output_contract: dict[str, Any],
    ) -> list[dict[str, Any]]:
        contradictions: list[dict[str, Any]] = []
        application = self._normalize_text(output_contract.get("application"))
        counter_analysis = self._normalize_text(output_contract.get("counter_analysis"))

        if application and counter_analysis:
            contradictions.append(
                ContradictionRecord(
                    contradiction_type="legal_interpretation_conflict",
                    description="Primary application and counter-analysis indicate competing legal interpretations that require lawyer resolution.",
                    conflicting_sources=[
                        ContradictionSourceReference(source_label="application", snippet=application[:280]),
                        ContradictionSourceReference(source_label="counter_analysis", snippet=counter_analysis[:280]),
                    ],
                    severity_score=0.64,
                ).model_dump(mode="json")
            )

        return contradictions

    def _detect_unsupported_claim_conflicts(
        self,
        *,
        claim_validation_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        contradictions: list[dict[str, Any]] = []
        unsupported_claims = claim_validation_payload.get("unsupported_claims")
        if not isinstance(unsupported_claims, list):
            return contradictions

        for row in unsupported_claims[:6]:
            if not isinstance(row, dict):
                continue
            claim = self._normalize_text(row.get("claim"))
            if not claim:
                continue
            contradictions.append(
                ContradictionRecord(
                    contradiction_type="unsupported_claim_conflict",
                    description=f"Unsupported legal claim detected: {claim}",
                    conflicting_sources=[
                        ContradictionSourceReference(source_label="claim_validation", snippet=claim[:280]),
                    ],
                    severity_score=0.82,
                ).model_dump(mode="json")
            )

        return contradictions

    def _merge_rows(self, rows: list[dict[str, Any]], *, limit: int = 12) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            fingerprint = (
                f"{row.get('contradiction_type')}|{row.get('description')}|"
                f"{round(float(row.get('severity_score') or 0.0), 3)}"
            ).lower()
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            deduped.append(row)
            if len(deduped) >= limit:
                break
        return deduped

    def _llm_refine(
        self,
        *,
        output_contract: dict[str, Any],
        case_context: dict[str, Any],
        claim_validation_payload: dict[str, Any],
        deterministic_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not settings.LEGAL_WORKFLOW_LLM_AGENTS_ENABLED or self.client is None:
            return deterministic_rows

        prompt = f"""
{self.PROMPT}

Return VALID JSON only with this schema:
{{
  "contradictions": [
    {{
      "contradiction_type": "",
      "description": "",
      "severity_score": 0.0,
      "conflicting_sources": [""]
    }}
  ]
}}

Known deterministic contradictions:
{json.dumps(deterministic_rows, ensure_ascii=True, indent=2)}

Output contract:
{json.dumps(output_contract, ensure_ascii=True, indent=2)}

Case context:
{json.dumps(case_context, ensure_ascii=True, indent=2)}

Claim validation summary:
{json.dumps({
    'unsupported_claims': claim_validation_payload.get('unsupported_claims'),
    'citation_coverage': claim_validation_payload.get('citation_coverage'),
    'hallucination_rate': claim_validation_payload.get('hallucination_rate'),
}, ensure_ascii=True, indent=2)}
"""
        try:
            response = self.client.responses.create(
                model=self.model,
                input=prompt,
                max_output_tokens=900,
            )
            raw = llm_gateway.extract_output_text(response).strip()
            contract = validate_json_model(raw, _LLMContradictionContract)
            if contract is None:
                return deterministic_rows

            llm_rows: list[dict[str, Any]] = []
            for row in contract.contradictions:
                refs = [
                    ContradictionSourceReference(source_label=label)
                    for label in self._normalize_list(row.conflicting_sources, limit=5)
                ]
                llm_rows.append(
                    ContradictionRecord(
                        contradiction_type=self._normalize_text(row.contradiction_type) or "legal_interpretation_conflict",
                        description=self._normalize_text(row.description) or "Potential legal contradiction requiring review.",
                        conflicting_sources=refs,
                        severity_score=max(0.0, min(float(row.severity_score or 0.0), 1.0)),
                    ).model_dump(mode="json")
                )
            merged = self._merge_rows([*deterministic_rows, *llm_rows], limit=12)
            return merged or deterministic_rows
        except Exception:
            return deterministic_rows

    def detect(
        self,
        *,
        output_contract: dict[str, Any],
        case_context: dict[str, Any],
        claim_validation_payload: dict[str, Any],
    ) -> AgentResult:
        timeline_rows = case_context.get("timeline") if isinstance(case_context.get("timeline"), list) else []

        deterministic_rows = [
            *self._detect_source_fact_conflicts(output_contract=output_contract),
            *self._detect_timeline_conflicts(timeline_rows=timeline_rows),
            *self._detect_amount_conflicts(claim_validation_payload=claim_validation_payload),
            *self._detect_sla_conflicts(
                claim_validation_payload=claim_validation_payload,
                case_context=case_context,
            ),
            *self._detect_legal_interpretation_conflicts(output_contract=output_contract),
            *self._detect_unsupported_claim_conflicts(claim_validation_payload=claim_validation_payload),
        ]
        deterministic_rows = self._merge_rows(deterministic_rows, limit=12)
        final_rows = self._llm_refine(
            output_contract=output_contract,
            case_context=case_context,
            claim_validation_payload=claim_validation_payload,
            deterministic_rows=deterministic_rows,
        )
        max_severity = max((float(item.get("severity_score") or 0.0) for item in final_rows), default=0.0)

        return self.result(
            success=True,
            payload={
                "contradictions": final_rows,
                "contradiction_count": len(final_rows),
                "max_severity_score": round(max_severity, 4),
                "contradiction_flags": bool(final_rows),
                "no_contradictions_statement": (
                    "No contradictions detected in retrieved evidence" if not final_rows else ""
                ),
            },
            trace=[
                f"Detected {len(final_rows)} contradiction signal(s) from timeline, claims, and interpretation checks.",
            ],
        )


contradiction_detection_agent = ContradictionDetectionAgent()
