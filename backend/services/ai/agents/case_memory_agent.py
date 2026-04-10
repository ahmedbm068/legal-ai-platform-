from __future__ import annotations

import json
from typing import Any

from backend.models.consultation_request import ConsultationRequest
from backend.models.document import Document
from backend.models.voice_recording import VoiceRecording
from backend.services.ai.agents.agent_output_formatter import AgentOutputFormatter
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.agents.evidence_trace_agent import evidence_trace_agent
from backend.services.ai.llm_gateway import llm_gateway


class CaseMemoryAgent(BaseAgent):
    agent_name = "case_memory_agent"

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    def build_case_memory(
        self,
        *,
        case_id: int,
        case_title: str,
        jurisdiction_country: str | None,
        documents: list[Document],
        consultations: list[ConsultationRequest] | None = None,
        voice_recordings: list[VoiceRecording] | None = None,
        reasoning_payload: dict[str, Any],
        objective: str | None = None,
    ) -> AgentResult:
        consultations = consultations or []
        voice_recordings = voice_recordings or []
        if not documents and not consultations and not voice_recordings:
            return self.result(
                success=False,
                error="No evidence was provided for the case memory snapshot.",
                trace=["Case memory agent skipped because no evidence sources were supplied."],
            )

        claim_trace_result = evidence_trace_agent.build_claim_trace(
            case_id=case_id,
            case_title=case_title,
            documents=documents,
            reasoning_payload=reasoning_payload,
            objective=objective,
        )

        heuristic_payload = self._build_heuristic_payload(
            case_id=case_id,
            case_title=case_title,
            jurisdiction_country=jurisdiction_country,
            documents=documents,
            consultations=consultations,
            voice_recordings=voice_recordings,
            reasoning_payload=reasoning_payload,
            claim_trace_payload=claim_trace_result.payload,
            objective=objective,
        )
        trace = [
            f"Starting case memory build for case_id={case_id}.",
            f"Indexed {len(heuristic_payload.get('document_inventory', []))} document(s) and {len(heuristic_payload.get('deadline_signals', []))} deadline signal(s).",
            "Built heuristic case-memory payload.",
        ]

        if self.client:
            llm_payload = self._generate_llm_memory(heuristic_payload=heuristic_payload)
            if llm_payload:
                heuristic_payload.update(llm_payload)
                heuristic_payload["used_llm"] = True
                trace.append("Enhanced case memory payload with LLM synthesis.")
            else:
                heuristic_payload["used_llm"] = False
                trace.append("LLM synthesis unavailable; kept heuristic case memory payload.")
        else:
            heuristic_payload["used_llm"] = False
            trace.append("No LLM client configured; kept heuristic case memory payload.")

        warnings: list[str] = []
        if not heuristic_payload.get("document_inventory"):
            warnings.append("No document inventory was extracted for the case memory snapshot.")
        if not heuristic_payload.get("claim_trace"):
            warnings.append("No claim-to-evidence trace was available for the case memory snapshot.")

        return self.result(success=True, payload=heuristic_payload, warnings=warnings, trace=trace)

    def _build_heuristic_payload(
        self,
        *,
        case_id: int,
        case_title: str,
        jurisdiction_country: str | None,
        documents: list[Document],
        consultations: list[ConsultationRequest],
        voice_recordings: list[VoiceRecording],
        reasoning_payload: dict[str, Any],
        claim_trace_payload: dict[str, Any],
        objective: str | None,
    ) -> dict[str, Any]:
        document_inventory = self._build_document_inventory(documents)
        claim_trace = self._normalize_claim_rows(claim_trace_payload.get("claim_trace"), limit=8)
        unsupported_claims = self._normalize_string_list(claim_trace_payload.get("unsupported_claims"), limit=8)
        deadline_signals = self._extract_deadline_signals(
            reasoning_payload=reasoning_payload,
            documents=documents,
            consultations=consultations,
        )
        contradictions = self._detect_contradictions(
            document_inventory=document_inventory,
            reasoning_payload=reasoning_payload,
            claim_trace=claim_trace,
        )
        open_proof_gaps = self._build_open_proof_gaps(
            reasoning_payload=reasoning_payload,
            unsupported_claims=unsupported_claims,
            document_inventory=document_inventory,
            contradictions=contradictions,
        )

        evidence_sources: list[str] = []
        for item in document_inventory:
            filename = str(item.get("filename") or "").strip()
            if filename and filename not in evidence_sources:
                evidence_sources.append(filename)

        supported_claims = sum(1 for item in claim_trace if item.get("status") == "supported")
        partial_claims = sum(1 for item in claim_trace if item.get("status") == "partial")

        memory_summary = (
            f"Case #{case_id} memory snapshot for {case_title}: {len(document_inventory)} document(s), "
            f"{len(deadline_signals)} deadline signal(s), and {supported_claims + partial_claims} mapped claim(s)."
        )
        if jurisdiction_country:
            memory_summary += f" Jurisdiction context: {self._normalize_text(jurisdiction_country)}."

        if objective:
            memory_summary += f" Focus: {self._normalize_text(objective)}."

        recommended_next_steps = self._build_recommended_next_steps(
            reasoning_payload=reasoning_payload,
            unsupported_claims=unsupported_claims,
            contradictions=contradictions,
        )

        confidence = "high" if supported_claims >= 2 and len(document_inventory) >= 3 else "medium" if document_inventory else "low"

        return {
            "case_id": case_id,
            "case_title": case_title,
            "jurisdiction_country": self._normalize_text(jurisdiction_country),
            "memory_summary": memory_summary,
            "document_inventory": document_inventory[:12],
            "claim_trace": claim_trace,
            "contradictions": contradictions[:6],
            "open_proof_gaps": open_proof_gaps[:6],
            "deadline_signals": deadline_signals[:8],
            "recommended_next_steps": recommended_next_steps[:8],
            "evidence_sources": evidence_sources[:10],
            "memory_score": self._estimate_memory_score(
                document_inventory=document_inventory,
                claim_trace=claim_trace,
                open_proof_gaps=open_proof_gaps,
            ),
            "confidence": confidence,
        }

    def _generate_llm_memory(self, *, heuristic_payload: dict[str, Any]) -> dict[str, Any] | None:
        prompt = f"""
You are the Case Memory Agent inside a legal AI platform.

Build a case memory snapshot that helps a lawyer see what is known, what is missing, and which evidence supports each claim.
{AgentOutputFormatter.build_quality_guidance(task="build a case memory snapshot with evidence trace and open gaps", structured_json=True)}

Return valid JSON only with this exact schema:
{{
  "memory_summary": "string",
  "document_inventory": [
    {{
      "filename": "string",
      "document_type": "string",
      "role": "string",
      "summary": "string"
    }}
  ],
  "claim_trace": [
    {{
      "claim": "string",
      "supporting_documents": ["string"],
            "status": "string",
      "note": "string"
    }}
  ],
  "contradictions": ["string"],
  "open_proof_gaps": ["string"],
  "deadline_signals": [
    {{
      "label": "string",
      "value": "string",
      "source": "string"
    }}
  ],
  "recommended_next_steps": ["string"],
  "confidence": "high"
}}

Rules:
- Use only the provided evidence.
- Do not invent dates, parties, or legal outcomes.
- Keep the answer practical, specific, and lawyer-friendly.
- If support is thin, say so plainly instead of guessing.

Context:
{json.dumps(heuristic_payload, ensure_ascii=False, indent=2)}
"""
        try:
            response = self.client.responses.create(model=self.model, input=prompt)
            raw_text = (response.output_text or "").strip()
            if not raw_text:
                return None

            payload = self._extract_json_payload(raw_text)
            if not payload:
                return None

            memory_summary = self._normalize_text(payload.get("memory_summary"))
            document_inventory = self._normalize_inventory_rows(payload.get("document_inventory"), limit=12)
            claim_trace = self._normalize_claim_rows(payload.get("claim_trace"), limit=8)
            contradictions = self._normalize_string_list(payload.get("contradictions"), limit=8)
            open_proof_gaps = self._normalize_string_list(payload.get("open_proof_gaps"), limit=8)
            deadline_signals = self._normalize_deadline_rows(payload.get("deadline_signals"), limit=8)
            recommended_next_steps = self._normalize_string_list(payload.get("recommended_next_steps"), limit=8)
            confidence = self._normalize_text(payload.get("confidence")) or "medium"

            if not memory_summary and not claim_trace and not document_inventory:
                return None

            return {
                "memory_summary": memory_summary or heuristic_payload.get("memory_summary") or "Case memory snapshot completed from available evidence.",
                "document_inventory": document_inventory or heuristic_payload.get("document_inventory") or [],
                "claim_trace": claim_trace or heuristic_payload.get("claim_trace") or [],
                "contradictions": contradictions or heuristic_payload.get("contradictions") or [],
                "open_proof_gaps": open_proof_gaps or heuristic_payload.get("open_proof_gaps") or [],
                "deadline_signals": deadline_signals or heuristic_payload.get("deadline_signals") or [],
                "recommended_next_steps": recommended_next_steps or heuristic_payload.get("recommended_next_steps") or [],
                "confidence": confidence,
            }
        except Exception:
            return None

    def _build_document_inventory(self, documents: list[Document]) -> list[dict[str, Any]]:
        inventory: list[dict[str, Any]] = []
        for document in documents[:15]:
            insights = self._safe_load_json(document.insights_json)
            filename = self._normalize_text(document.filename) or f"Document #{document.id}"
            document_type = self._normalize_text(insights.get("document_type") or document.document_type) or "Case Document"
            summary = self._normalize_text(
                document.summary_short
                or document.summary
                or insights.get("general_summary")
                or (document.redacted_text or document.extracted_text or "")[:240]
            )
            role = self._infer_document_role(filename=filename, document_type=document_type, summary=summary)
            inventory.append(
                {
                    "filename": filename,
                    "document_type": document_type,
                    "role": role,
                    "summary": summary,
                }
            )
        return inventory

    def _extract_deadline_signals(
        self,
        *,
        reasoning_payload: dict[str, Any],
        documents: list[Document],
        consultations: list[ConsultationRequest],
    ) -> list[dict[str, str]]:
        signals: list[dict[str, str]] = []

        for item in reasoning_payload.get("key_dates") or []:
            label = self._normalize_text(item.get("label"))
            value = self._normalize_text(item.get("value"))
            if label and value:
                row = {"label": label, "value": value, "source": "case reasoning"}
                if row not in signals:
                    signals.append(row)

        for document in documents:
            insights = self._safe_load_json(document.insights_json)
            for item in insights.get("important_dates") or []:
                label = self._normalize_text(item.get("label"))
                value = self._normalize_text(item.get("value"))
                if label and value:
                    row = {"label": label, "value": value, "source": self._normalize_text(document.filename) or f"Document #{document.id}"}
                    if row not in signals:
                        signals.append(row)

        for consultation in consultations:
            preferred_schedule = self._normalize_text(consultation.preferred_schedule)
            if preferred_schedule:
                row = {
                    "label": "Preferred consultation schedule",
                    "value": preferred_schedule,
                    "source": f"Consultation #{consultation.id}",
                }
                if row not in signals:
                    signals.append(row)

        return signals

    def _detect_contradictions(
        self,
        *,
        document_inventory: list[dict[str, Any]],
        reasoning_payload: dict[str, Any],
        claim_trace: list[dict[str, Any]],
    ) -> list[str]:
        contradictions: list[str] = []
        lowered_roles = " ".join(f"{item.get('role', '')} {item.get('document_type', '')} {item.get('summary', '')}".lower() for item in document_inventory)

        if any(marker in lowered_roles for marker in ["contract baseline", "performance evidence", "payment evidence"]):
            if any(marker in lowered_roles for marker in ["notice or escalation", "counterparty response"]):
                contradictions.append("The file contains both baseline performance evidence and dispute correspondence; reconcile the chronology before relying on the narrative.")

        if any(marker in lowered_roles for marker in ["settlement position"]) and any(marker in lowered_roles for marker in ["notice or escalation", "counterparty response"]):
            contradictions.append("Settlement material is present, but the dispute posture still needs to be aligned with the breach or response record.")

        if any(marker in lowered_roles for marker in ["performance evidence"]) and any(marker in lowered_roles for marker in ["payment evidence"]):
            contradictions.append("Performance and payment records should be reconciled before the lawyer treats them as one story.")

        unsupported_claims = [item.get("claim") for item in claim_trace if item.get("status") == "unsupported"]
        if unsupported_claims:
            contradictions.append(f"{len(unsupported_claims)} claim(s) still lack direct document support.")

        legal_risks = self._normalize_string_list(reasoning_payload.get("legal_risks"), limit=4)
        if legal_risks and not document_inventory:
            contradictions.append("Risk language exists, but there is no document inventory to anchor it yet.")

        return self._dedupe_ordered(contradictions)

    def _build_open_proof_gaps(
        self,
        *,
        reasoning_payload: dict[str, Any],
        unsupported_claims: list[str],
        document_inventory: list[dict[str, Any]],
        contradictions: list[str],
    ) -> list[str]:
        gaps: list[str] = []
        gaps.extend(self._normalize_string_list(reasoning_payload.get("evidence_gaps"), limit=6))

        for claim in unsupported_claims[:4]:
            gaps.append(f"Claim still needs support: {claim}")

        if not document_inventory:
            gaps.append("Document inventory is incomplete, so the lawyer cannot yet see the full evidence picture.")

        if contradictions:
            gaps.append("The file contains conflicting signals that should be reconciled before client communication.")

        if reasoning_payload.get("key_dates"):
            pass
        else:
            gaps.append("No clear deadline or date signal was captured from the current record.")

        return self._dedupe_ordered(gaps)

    def _build_recommended_next_steps(
        self,
        *,
        reasoning_payload: dict[str, Any],
        unsupported_claims: list[str],
        contradictions: list[str],
    ) -> list[str]:
        steps = self._normalize_string_list(reasoning_payload.get("recommended_next_steps"), limit=6)
        steps.insert(0, "Use the claim trace to prepare a lawyer-facing evidence map before drafting externally.")
        if unsupported_claims:
            steps.append("Request missing source documents for the unsupported claims before final advice goes out.")
        if contradictions:
            steps.append("Resolve the contradictory signals before the case is summarized for the client or partner.")
        return self._dedupe_ordered(steps)

    def _estimate_memory_score(
        self,
        *,
        document_inventory: list[dict[str, Any]],
        claim_trace: list[dict[str, Any]],
        open_proof_gaps: list[str],
    ) -> int:
        score = min(50, len(document_inventory) * 4)
        score += min(30, sum(1 for item in claim_trace if item.get("status") == "supported") * 6)
        score -= min(20, len(open_proof_gaps) * 3)
        return max(0, min(100, score))

    @staticmethod
    def _normalize_inventory_rows(values: Any, *, limit: int | None = None) -> list[dict[str, Any]]:
        if not isinstance(values, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            filename = AgentOutputFormatter.sanitize_text(item.get("filename"))
            document_type = AgentOutputFormatter.sanitize_text(item.get("document_type"))
            role = AgentOutputFormatter.sanitize_text(item.get("role"))
            summary = AgentOutputFormatter.sanitize_text(item.get("summary"))
            if not filename:
                continue
            row = {
                "filename": filename,
                "document_type": document_type,
                "role": role,
                "summary": summary,
            }
            if row not in normalized:
                normalized.append(row)
            if limit is not None and len(normalized) >= limit:
                break
        return normalized

    @staticmethod
    def _normalize_claim_rows(values: Any, *, limit: int | None = None) -> list[dict[str, Any]]:
        if not isinstance(values, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            claim = AgentOutputFormatter.sanitize_text(item.get("claim"))
            supporting_documents = AgentOutputFormatter.normalize_string_list(item.get("supporting_documents"), limit=4)
            status = AgentOutputFormatter.sanitize_text(item.get("status")).lower() or ("supported" if supporting_documents else "unsupported")
            note = AgentOutputFormatter.sanitize_text(item.get("note"))
            if not claim:
                continue
            row = {
                "claim": claim,
                "supporting_documents": supporting_documents,
                "status": status,
                "note": note,
            }
            if row not in normalized:
                normalized.append(row)
            if limit is not None and len(normalized) >= limit:
                break
        return normalized

    @staticmethod
    def _normalize_deadline_rows(values: Any, *, limit: int | None = None) -> list[dict[str, Any]]:
        if not isinstance(values, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            label = AgentOutputFormatter.sanitize_text(item.get("label"))
            value = AgentOutputFormatter.sanitize_text(item.get("value"))
            source = AgentOutputFormatter.sanitize_text(item.get("source"))
            if not (label and value):
                continue
            row = {"label": label, "value": value, "source": source}
            if row not in normalized:
                normalized.append(row)
            if limit is not None and len(normalized) >= limit:
                break
        return normalized

    @staticmethod
    def _normalize_string_list(values: Any, *, limit: int | None = None) -> list[str]:
        return AgentOutputFormatter.normalize_string_list(values, limit=limit)

    @staticmethod
    def _dedupe_ordered(items: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            cleaned = AgentOutputFormatter.sanitize_text(item)
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(cleaned)
        return deduped

    @staticmethod
    def _infer_document_role(*, filename: str, document_type: str, summary: str) -> str:
        lowered = f"{filename} {document_type} {summary}".lower()
        if any(marker in lowered for marker in ["master service agreement", "msa", "service agreement", "contract", "agreement"]):
            return "contract baseline"
        if any(marker in lowered for marker in ["notice of breach", "breach notice", "notice"]):
            return "notice or escalation"
        if any(marker in lowered for marker in ["response", "reply", "counterparty"]):
            return "counterparty response"
        if any(marker in lowered for marker in ["invoice", "reconciliation", "payment"]):
            return "payment evidence"
        if any(marker in lowered for marker in ["kpi", "dashboard", "performance", "sla"]):
            return "performance evidence"
        if any(marker in lowered for marker in ["settlement", "without prejudice", "offer", "proposal"]):
            return "settlement position"
        if any(marker in lowered for marker in ["memo", "note", "internal"]):
            return "internal analysis"
        if any(marker in lowered for marker in ["transcript", "call", "meeting"]):
            return "call or intake context"
        return "case evidence"

    @staticmethod
    def _safe_load_json(raw_value: str | None) -> dict[str, Any]:
        if not raw_value:
            return {}
        try:
            payload = json.loads(raw_value)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return AgentOutputFormatter.normalize_text(value)

    @staticmethod
    def _extract_json_payload(raw_text: str) -> dict[str, Any] | None:
        return AgentOutputFormatter.extract_json_payload(raw_text)


case_memory_agent = CaseMemoryAgent()