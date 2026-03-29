from __future__ import annotations

import json
from typing import Any

from backend.models.case import Case
from backend.models.consultation_request import ConsultationRequest
from backend.models.document import Document
from backend.models.voice_recording import VoiceRecording
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.llm_gateway import llm_gateway


class CaseReasoningAgent(BaseAgent):
    agent_name = "case_reasoning_agent"

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    def analyze_case(
        self,
        *,
        case: Case,
        documents: list[Document],
        consultation_requests: list[ConsultationRequest] | None = None,
        voice_recordings: list[VoiceRecording] | None = None,
    ) -> AgentResult:
        if not documents:
            return self.result(
                success=False,
                error="Case has no documents to reason over.",
                trace=["Input validation failed: no documents supplied to case reasoning agent."],
            )

        consultation_requests = consultation_requests or []
        voice_recordings = voice_recordings or []

        trace = [
            f"Starting case reasoning for case_id={case.id}.",
            f"Received {len(documents)} documents, {len(consultation_requests)} consultation requests, "
            f"and {len(voice_recordings)} voice recordings.",
        ]

        heuristic_payload = self._build_heuristic_payload(
            case=case,
            documents=documents,
            consultation_requests=consultation_requests,
            voice_recordings=voice_recordings,
        )
        trace.append("Built heuristic case intelligence payload.")

        if self.client:
            llm_payload = self._generate_llm_case_brief(case=case, heuristic_payload=heuristic_payload)
            if llm_payload:
                heuristic_payload.update(llm_payload)
                heuristic_payload["used_llm"] = True
                trace.append("Enhanced case reasoning payload with LLM synthesis.")
            else:
                heuristic_payload["used_llm"] = False
                trace.append("LLM synthesis unavailable; kept heuristic case reasoning payload.")
        else:
            heuristic_payload["used_llm"] = False
            trace.append("No LLM client configured; kept heuristic case reasoning payload.")

        has_governing_law_signal = bool(heuristic_payload.get("_has_governing_law_signal"))
        has_payment_terms_signal = bool(heuristic_payload.get("_has_payment_terms_signal"))
        heuristic_payload["legal_risks"] = self._reconcile_risks_with_contract_signals(
            risks=self._normalize_string_list(heuristic_payload.get("legal_risks")),
            has_governing_law_signal=has_governing_law_signal,
            has_payment_terms_signal=has_payment_terms_signal,
        )
        heuristic_payload["main_issues"] = self._clean_main_issues(
            issues=self._normalize_string_list(heuristic_payload.get("main_issues")),
            has_governing_law_signal=has_governing_law_signal,
            has_payment_terms_signal=has_payment_terms_signal,
        )

        heuristic_payload.pop("_has_governing_law_signal", None)
        heuristic_payload.pop("_has_payment_terms_signal", None)

        heuristic_payload["case_id"] = case.id
        heuristic_payload["case_title"] = case.title
        heuristic_payload["document_count"] = len(documents)

        return self.result(
            success=True,
            payload=heuristic_payload,
            warnings=self._build_warnings(heuristic_payload),
            trace=trace,
        )

    def _build_heuristic_payload(
        self,
        *,
        case: Case,
        documents: list[Document],
        consultation_requests: list[ConsultationRequest],
        voice_recordings: list[VoiceRecording],
    ) -> dict[str, Any]:
        document_summaries: list[str] = []
        parties: list[str] = []
        dates: list[dict[str, str]] = []
        risks: list[str] = []
        actions: list[str] = []
        document_types: list[str] = []
        sources: list[dict[str, Any]] = []
        main_issues: list[str] = []
        has_governing_law_signal = False
        has_payment_terms_signal = False

        for document in documents:
            insights = self._safe_load_json(document.insights_json)
            summary_text = self._normalize_text(
                document.summary_short
                or document.summary
                or (document.redacted_text or document.extracted_text or "")[:500]
            )

            if summary_text:
                document_summaries.append(f"{document.filename}: {summary_text}")
                sources.append(
                    {
                        "chunk_id": None,
                        "document_id": document.id,
                        "case_id": document.case_id,
                        "filename": document.filename,
                        "chunk_index": None,
                        "score": 1.0,
                        "snippet": summary_text[:300],
                    }
                )

            document_type = self._normalize_text(insights.get("document_type") or document.document_type)
            if document_type and document_type not in document_types:
                document_types.append(document_type)

            for party in insights.get("parties_detected", []):
                cleaned = self._normalize_text(party)
                if cleaned and cleaned not in parties and self._is_reasonable_party(cleaned):
                    parties.append(cleaned)

            for date_item in insights.get("important_dates", []):
                label = self._normalize_text(date_item.get("label"))
                value = self._normalize_text(date_item.get("value"))
                normalized_item = {"label": label, "value": value}
                if label and value and normalized_item not in dates:
                    dates.append(normalized_item)

            for risk in insights.get("legal_risks", []):
                cleaned = self._normalize_text(risk)
                if cleaned and cleaned not in risks:
                    risks.append(cleaned)

            for action in (insights.get("recommended_next_actions", []) or insights.get("recommended_actions", [])):
                cleaned = self._normalize_text(action)
                if cleaned and cleaned not in actions:
                    actions.append(cleaned)

            for point in insights.get("key_points", []):
                cleaned = self._normalize_text(point)
                if cleaned and cleaned not in main_issues:
                    main_issues.append(cleaned)

            signal_text = " ".join(
                [
                    self._normalize_text(document.extracted_text),
                    self._normalize_text(document.redacted_text),
                    self._normalize_text(document.summary),
                    self._normalize_text(document.summary_short),
                ]
            ).lower()

            if (
                "governing law" in signal_text
                or "applicable law" in signal_text
                or "laws of tunisia" in signal_text
            ):
                has_governing_law_signal = True

            if any(
                token in signal_text
                for token in [
                    "payment terms",
                    "net 30",
                    "late payment",
                    "invoice due",
                    "payment due",
                    "amount due",
                    "invoice",
                ]
            ):
                has_payment_terms_signal = True

        risks = self._reconcile_risks_with_contract_signals(
            risks=risks,
            has_governing_law_signal=has_governing_law_signal,
            has_payment_terms_signal=has_payment_terms_signal,
        )
        main_issues = self._clean_main_issues(
            issues=main_issues,
            has_governing_law_signal=has_governing_law_signal,
            has_payment_terms_signal=has_payment_terms_signal,
        )

        intake_items = self._build_intake_items(consultation_requests)
        transcript_highlights = self._build_transcript_highlights(voice_recordings)

        if not main_issues:
            main_issues = [summary.split(": ", 1)[-1] for summary in document_summaries[:4]]

        if intake_items:
            for intake in intake_items[:3]:
                issue_summary = self._normalize_text(intake.get("issue_summary"))
                if issue_summary and issue_summary not in main_issues:
                    main_issues.append(issue_summary)

        overview_lines = [
            f"Case {case.id} - {case.title}",
            f"The case currently contains {len(documents)} document(s).",
        ]
        if document_types:
            overview_lines.append("Detected document types: " + ", ".join(document_types[:6]) + ".")
        if parties:
            overview_lines.append("Main parties detected: " + ", ".join(parties[:6]) + ".")
        if intake_items:
            overview_lines.append("Client intake context is available from consultation workflows.")

        return {
            "overview": " ".join(overview_lines).strip(),
            "main_issues": main_issues[:8],
            "key_dates": dates[:12],
            "legal_risks": risks[:10],
            "recommended_next_steps": actions[:10] or self._default_next_steps(),
            "document_types": document_types[:10],
            "document_summaries": document_summaries[:12],
            "parties": parties[:12],
            "intake_items": intake_items[:6],
            "transcript_highlights": transcript_highlights[:6],
            "sources": sources[:10],
            "_has_governing_law_signal": has_governing_law_signal,
            "_has_payment_terms_signal": has_payment_terms_signal,
            "narrative_summary": self._build_fallback_narrative(
                overview_lines=overview_lines,
                main_issues=main_issues,
                key_dates=dates,
                legal_risks=risks,
                next_steps=actions,
            ),
        }

    @staticmethod
    def _reconcile_risks_with_contract_signals(
        *,
        risks: list[str],
        has_governing_law_signal: bool,
        has_payment_terms_signal: bool,
    ) -> list[str]:
        normalized: list[str] = []
        for risk in risks:
            lowered = risk.lower()
            if has_governing_law_signal and "no governing law clause" in lowered:
                continue
            if has_payment_terms_signal and (
                "no clear payment obligation" in lowered
                or "payment obligation was confidently extracted" in lowered
            ):
                continue
            if risk not in normalized:
                normalized.append(risk)
        return normalized

    @staticmethod
    def _clean_main_issues(
        *,
        issues: list[str],
        has_governing_law_signal: bool,
        has_payment_terms_signal: bool,
    ) -> list[str]:
        cleaned: list[str] = []
        for issue in issues:
            item = issue.strip()
            if not item:
                continue

            lowered = item.lower()
            if lowered.startswith("risk:"):
                continue
            if "no clear payment obligation" in lowered and has_payment_terms_signal:
                continue
            if "no governing law clause" in lowered and has_governing_law_signal:
                continue

            if item not in cleaned:
                cleaned.append(item)

        return cleaned

    def _generate_llm_case_brief(
        self,
        *,
        case: Case,
        heuristic_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        prompt = f"""
You are the Case Reasoning Agent inside a legal AI platform.

You receive grounded case intelligence that came from documents, intake records, and voice transcripts.
Your job is to synthesize that information into a clean case brief without inventing facts.

Return valid JSON only with this exact schema:
{{
  "overview": "string",
  "narrative_summary": "string",
  "main_issues": ["string"],
  "key_dates": [{{"label": "string", "value": "string"}}],
  "legal_risks": ["string"],
  "recommended_next_steps": ["string"]
}}

Rules:
- Use only the provided case intelligence.
- If evidence is thin, keep the wording cautious.
- Do not invent legal conclusions, statutes, or deadlines.
- Keep the output practical and concise.

Case id: {case.id}
Case title: {case.title}

Case intelligence:
{json.dumps(heuristic_payload, ensure_ascii=False, indent=2)}
"""

        try:
            response = self.client.responses.create(
                model=self.model,
                input=prompt,
            )
            raw_text = (response.output_text or "").strip()
            if not raw_text:
                return None

            parsed = self._extract_json_payload(raw_text)
            if not parsed:
                return None

            return {
                "overview": self._normalize_text(parsed.get("overview")) or heuristic_payload.get("overview", ""),
                "narrative_summary": self._normalize_text(parsed.get("narrative_summary"))
                or heuristic_payload.get("narrative_summary", ""),
                "main_issues": self._normalize_string_list(parsed.get("main_issues")) or heuristic_payload.get("main_issues", []),
                "key_dates": self._normalize_date_items(parsed.get("key_dates")) or heuristic_payload.get("key_dates", []),
                "legal_risks": self._normalize_string_list(parsed.get("legal_risks")) or heuristic_payload.get("legal_risks", []),
                "recommended_next_steps": self._normalize_string_list(parsed.get("recommended_next_steps"))
                or heuristic_payload.get("recommended_next_steps", []),
            }
        except Exception:
            return None

    def _build_intake_items(
        self,
        consultation_requests: list[ConsultationRequest],
    ) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []

        for request in consultation_requests:
            item = {
                "client_name": self._normalize_text(request.client_name),
                "booking_intent": self._normalize_text(request.booking_intent),
                "urgency_level": self._normalize_text(request.urgency_level),
                "legal_area": self._normalize_text(request.legal_area),
                "preferred_schedule": self._normalize_text(request.preferred_schedule),
                "issue_summary": self._normalize_text(request.issue_summary),
            }

            if any(item.values()) and item not in items:
                items.append(item)

        return items

    def _build_transcript_highlights(
        self,
        voice_recordings: list[VoiceRecording],
    ) -> list[str]:
        highlights: list[str] = []

        for recording in voice_recordings:
            transcript = self._normalize_text(recording.transcript_text)
            if not transcript:
                continue

            highlight = transcript[:240].strip()
            if len(transcript) > 240:
                highlight += "..."

            if highlight and highlight not in highlights:
                highlights.append(highlight)

        return highlights

    def _build_fallback_narrative(
        self,
        *,
        overview_lines: list[str],
        main_issues: list[str],
        key_dates: list[dict[str, str]],
        legal_risks: list[str],
        next_steps: list[str],
    ) -> str:
        sections = [" ".join(overview_lines).strip(), "", "Main Issues:"]

        if main_issues:
            sections.extend(f"- {item}" for item in main_issues[:5])
        else:
            sections.append("- No major issues were clearly extracted yet.")

        sections.append("")
        sections.append("Key Dates:")
        if key_dates:
            sections.extend(f"- {item['label']}: {item['value']}" for item in key_dates[:8])
        else:
            sections.append("- No major dates were clearly detected.")

        sections.append("")
        sections.append("Legal Risks:")
        if legal_risks:
            sections.extend(f"- {item}" for item in legal_risks[:8])
        else:
            sections.append("- No major legal risks were clearly detected.")

        sections.append("")
        sections.append("Recommended Next Steps:")
        if next_steps:
            sections.extend(f"- {item}" for item in next_steps[:8])
        else:
            sections.extend(f"- {item}" for item in self._default_next_steps())

        return "\n".join(sections).strip()

    @staticmethod
    def _build_warnings(payload: dict[str, Any]) -> list[str]:
        warnings: list[str] = []

        if not payload.get("legal_risks"):
            warnings.append("No explicit legal risks were extracted from the current case evidence.")
        if not payload.get("key_dates"):
            warnings.append("No explicit key dates were extracted from the current case evidence.")
        if not payload.get("intake_items"):
            warnings.append("No consultation intake records were available for this case reasoning pass.")

        return warnings

    @staticmethod
    def _default_next_steps() -> list[str]:
        return [
            "Review the document set for consistency across parties, obligations, and dates.",
            "Verify deadlines, hearing dates, and notice periods against the source documents.",
            "Check whether more supporting evidence or client clarification is needed.",
        ]

    @staticmethod
    def _extract_json_payload(raw_text: str) -> dict[str, Any] | None:
        candidate = raw_text.strip()

        if candidate.startswith("```"):
            candidate = candidate.strip("`")
            candidate = candidate.replace("json", "", 1).strip()

        try:
            payload = json.loads(candidate)
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None

            try:
                payload = json.loads(candidate[start : end + 1])
                return payload if isinstance(payload, dict) else None
            except json.JSONDecodeError:
                return None

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
        return str(value or "").strip()

    @classmethod
    def _normalize_string_list(cls, values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        return [cls._normalize_text(value) for value in values if cls._normalize_text(value)]

    @classmethod
    def _normalize_date_items(cls, values: Any) -> list[dict[str, str]]:
        if not isinstance(values, list):
            return []

        items: list[dict[str, str]] = []
        for item in values:
            if not isinstance(item, dict):
                continue

            label = cls._normalize_text(item.get("label"))
            value = cls._normalize_text(item.get("value"))
            if label and value:
                items.append({"label": label, "value": value})

        return items

    @staticmethod
    def _is_reasonable_party(value: str) -> bool:
        lowered = value.lower().strip()
        if not lowered:
            return False

        blocked_fragments = [
            "invoice records",
            "warehouse logs",
            "document overview",
            "this document",
            "question answering",
            "sample document",
            "used to test",
            "key dates",
        ]

        if any(fragment in lowered for fragment in blocked_fragments):
            return False

        return len(value) <= 60


case_reasoning_agent = CaseReasoningAgent()
