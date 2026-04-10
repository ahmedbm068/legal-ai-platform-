from __future__ import annotations

import json
from typing import Any

from backend.models.document import Document
from backend.services.ai.agents.agent_output_formatter import AgentOutputFormatter
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.llm_gateway import llm_gateway


class InsightAgent(BaseAgent):
    agent_name = "insight_agent"

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    def generate_case_insights(
        self,
        *,
        case_id: int,
        case_title: str,
        jurisdiction_country: str | None,
        reasoning_payload: dict[str, Any],
        documents: list[Document],
        consultation_count: int = 0,
        voice_recording_count: int = 0,
    ) -> AgentResult:
        trace = [
            f"Starting case insights for case_id={case_id}.",
            f"Inputs: {len(documents)} documents, {consultation_count} consultations, {voice_recording_count} voice recordings.",
            "Built heuristic insight payload.",
        ]

        heuristic_payload = self._build_heuristic_payload(
            case_id=case_id,
            case_title=case_title,
            jurisdiction_country=jurisdiction_country,
            reasoning_payload=reasoning_payload,
            documents=documents,
            consultation_count=consultation_count,
            voice_recording_count=voice_recording_count,
        )

        if self.client:
            llm_payload = self._generate_llm_insights(heuristic_payload=heuristic_payload)
            if llm_payload:
                heuristic_payload.update(llm_payload)
                heuristic_payload["used_llm"] = True
                trace.append("Enhanced insight payload with LLM synthesis.")
            else:
                heuristic_payload["used_llm"] = False
                trace.append("LLM synthesis unavailable; kept heuristic insight payload.")
        else:
            heuristic_payload["used_llm"] = False
            trace.append("No LLM client configured; kept heuristic insight payload.")

        warnings: list[str] = []
        if not heuristic_payload.get("key_insights"):
            warnings.append("No strong insight signals were extracted from current case evidence.")

        return self.result(success=True, payload=heuristic_payload, warnings=warnings, trace=trace)

    def _build_heuristic_payload(
        self,
        *,
        case_id: int,
        case_title: str,
        jurisdiction_country: str | None,
        reasoning_payload: dict[str, Any],
        documents: list[Document],
        consultation_count: int,
        voice_recording_count: int,
    ) -> dict[str, Any]:
        main_issues = self._normalize_string_list(reasoning_payload.get("main_issues"), limit=8)
        legal_risks = self._normalize_string_list(reasoning_payload.get("legal_risks"), limit=8)
        next_steps = self._normalize_string_list(reasoning_payload.get("recommended_next_steps"), limit=8)

        key_dates: list[dict[str, str]] = []
        for item in reasoning_payload.get("key_dates") or []:
            label = self._normalize_text(item.get("label"))
            value = self._normalize_text(item.get("value"))
            if not label or not value:
                continue
            normalized_item = {"label": label, "value": value}
            if normalized_item not in key_dates:
                key_dates.append(normalized_item)

        evidence_sources: list[str] = []
        document_markers: set[str] = set()
        for source in reasoning_payload.get("sources") or []:
            filename = self._normalize_text(source.get("filename"))
            if filename and filename not in evidence_sources:
                evidence_sources.append(filename)

        for document in documents:
            filename = self._normalize_text(document.filename)
            if filename and filename not in evidence_sources:
                evidence_sources.append(filename)
            lowered_name = filename.lower()
            if any(token in lowered_name for token in ["kpi", "dashboard", "performance"]):
                document_markers.add("kpi")
            if any(token in lowered_name for token in ["invoice", "reconciliation", "payment"]):
                document_markers.add("invoice")
            if any(token in lowered_name for token in ["notice", "breach", "response", "cure"]):
                document_markers.add("notice")
            if any(token in lowered_name for token in ["settlement", "without_prejudice", "without prejudice"]):
                document_markers.add("settlement")
            if any(token in lowered_name for token in ["memo", "transcript", "call"]):
                document_markers.add("context")

        pending_documents = [
            document.filename
            for document in documents
            if not self._normalize_text(document.summary) and not self._normalize_text(document.summary_short)
        ]

        key_insights: list[str] = []
        if main_issues:
            key_insights.append(
                f"Core dispute drivers are concentrated around {', '.join(main_issues[:2])}."
            )
        if legal_risks:
            key_insights.append(f"Highest visible legal exposure is {legal_risks[0]}.")
        if key_dates:
            first_date = key_dates[0]
            key_insights.append(
                f"Most time-sensitive item is {first_date['label']} ({first_date['value']})."
            )
        if consultation_count > 0:
            key_insights.append(
                f"Client intake context is available from {consultation_count} consultation request(s)."
            )
        if voice_recording_count > 0:
            key_insights.append(
                f"Voice evidence exists ({voice_recording_count} recording(s)) and should be cross-checked with written records."
            )
        if evidence_sources:
            key_insights.append(
                f"The review set now spans {len(evidence_sources)} document(s), so the partner review should focus on clause-to-exhibit mapping rather than more intake."
            )
        if len(evidence_sources) >= len(documents) and documents:
            key_insights.append(
                "Document coverage appears complete, which makes this a good stage to test breach, notice, performance, and damages together."
            )

        if not key_insights:
            key_insights.append("Current case evidence does not yet provide strong, stable insight signals.")

        priority_actions = next_steps[:4]
        partner_review_actions = [
            "Prepare a partner review matrix: issue, clause, exhibit, strength, and owner.",
            "Separate strong evidence from weak or indirect material before external discussion.",
            "Confirm whether KPI, invoice, notice, and cure-period evidence tell one consistent story.",
        ]
        for action in reversed(partner_review_actions):
            priority_actions.insert(0, action)
        if pending_documents:
            priority_actions.append(
                f"Complete processing for {len(pending_documents)} pending document(s) to reduce blind spots."
            )
        if not priority_actions:
            priority_actions = [
                "Validate chronology, obligations, and evidence consistency before client communication.",
                "Prepare a partner review matrix that ties each issue to a clause and exhibit.",
            ]

        evidence_gaps: list[str] = []
        if pending_documents:
            evidence_gaps.append(
                "Some documents are pending summary/processing, limiting confidence in final conclusions."
            )
        if not key_dates:
            evidence_gaps.append("No explicit deadlines or due-date signals were extracted.")
        if not legal_risks:
            evidence_gaps.append("Risk extraction is currently weak and needs deeper evidence review.")
        if not evidence_sources:
            evidence_gaps.append("No stable evidence source mapping is available yet.")
        if "kpi" in document_markers:
            evidence_gaps.append("KPI methodology gap: confirm how the dashboard metrics were calculated and whether the source logs are intact.")
        if "invoice" in document_markers:
            evidence_gaps.append("Invoice support gap: reconcile the disputed line items to the underlying rate card, approvals, or payment trail.")
        if "notice" in document_markers:
            evidence_gaps.append("Notice and cure gap: verify the notice sequence, response dates, and any cure-period correspondence.")
        if "settlement" in document_markers:
            evidence_gaps.append("Settlement posture gap: confirm which concessions are exploratory and which terms are actually agreed.")
        if "context" in document_markers and consultation_count == 0 and voice_recording_count == 0:
            evidence_gaps.append("Context gap: the file has documentary evidence but no intake or call context to explain the negotiating position.")
        if legal_risks:
            evidence_gaps.append("Causation and damages gap: tie the alleged breach to measurable loss and the available contract remedy pathway.")

        if evidence_gaps:
            evidence_gaps = self._normalize_string_list(evidence_gaps, limit=6)

        summary_fragments = [
            f"Case #{case_id} ({case_title}) insight snapshot",
            f"{len(main_issues)} issue signal(s)",
            f"{len(legal_risks)} risk signal(s)",
            f"{len(key_dates)} date signal(s)",
        ]
        if jurisdiction_country:
            summary_fragments.append(f"jurisdiction context: {jurisdiction_country}")

        return {
            "case_id": case_id,
            "case_title": case_title,
            "jurisdiction_country": self._normalize_text(jurisdiction_country),
            "insight_summary": "; ".join(summary_fragments) + ".",
            "key_insights": key_insights[:6],
            "priority_actions": priority_actions[:6],
            "evidence_gaps": evidence_gaps[:6],
            "evidence_sources": evidence_sources[:10],
            "main_issue_count": len(main_issues),
            "risk_count": len(legal_risks),
            "date_count": len(key_dates),
        }

    def _generate_llm_insights(self, *, heuristic_payload: dict[str, Any]) -> dict[str, Any] | None:
        prompt = f"""
You are the Insight Agent inside a legal AI platform.

Generate a concise insight brief from the provided case reasoning payload.

{AgentOutputFormatter.build_quality_guidance(task="turn case reasoning into strategic partner-review insights", structured_json=True)}

Return valid JSON only with this schema:
{{
  "insight_summary": "string",
  "key_insights": ["string"],
  "priority_actions": ["string"],
  "evidence_gaps": ["string"]
}}

Rules:
- Use only provided evidence.
- Do not invent facts, dates, entities, or legal outcomes.
- Keep key_insights to 3-6 items.
- Keep priority_actions to 2-5 practical actions.
- Keep evidence_gaps to 0-4 items.

Input payload:
{json.dumps(heuristic_payload, ensure_ascii=False, indent=2)}
"""
        try:
            response = self.client.responses.create(model=self.model, input=prompt)
            output = llm_gateway.extract_output_text(response).strip()
            if not output:
                return None

            payload = self._extract_json_payload(output)
            if not payload:
                return None

            summary = self._normalize_text(payload.get("insight_summary"))
            key_insights = self._normalize_string_list(payload.get("key_insights"), limit=6)
            priority_actions = self._normalize_string_list(payload.get("priority_actions"), limit=6)
            evidence_gaps = self._normalize_string_list(payload.get("evidence_gaps"), limit=6)

            if not summary and not key_insights:
                return None

            return {
                "insight_summary": summary or "Case insights generated from available evidence.",
                "key_insights": key_insights,
                "priority_actions": priority_actions,
                "evidence_gaps": evidence_gaps,
            }
        except Exception:
            return None

    @staticmethod
    def _extract_json_payload(raw_text: str) -> dict[str, Any] | None:
        candidate = (raw_text or "").strip()
        if not candidate:
            return None

        if candidate.startswith("```"):
            candidate = candidate.strip("`")
            candidate = candidate.replace("json", "", 1).strip()

        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start < 0 or end <= start:
                return None
            try:
                parsed = json.loads(candidate[start : end + 1])
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _normalize_string_list(cls, value: Any, *, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []

        normalized: list[str] = []
        for item in value:
            cleaned = cls._normalize_text(item).rstrip(".")
            if not cleaned:
                continue
            if cleaned not in normalized:
                normalized.append(cleaned)
            if len(normalized) >= limit:
                break
        return normalized


insight_agent = InsightAgent()
