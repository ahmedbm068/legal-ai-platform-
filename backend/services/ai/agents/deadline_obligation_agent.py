from __future__ import annotations

import json
import re
from typing import Any

from backend.models.consultation_request import ConsultationRequest
from backend.models.document import Document
from backend.services.ai.agents.agent_output_formatter import AgentOutputFormatter
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.llm_gateway import llm_gateway


class DeadlineObligationAgent(BaseAgent):
    agent_name = "deadline_obligation_agent"

    DEADLINE_KEYWORDS = (
        "deadline",
        "due",
        "due date",
        "no later than",
        "on or before",
        "within",
        "before",
        "after",
        "notice period",
        "cure period",
        "renewal",
        "expiration",
        "response",
    )
    OBLIGATION_KEYWORDS = (
        "shall",
        "must",
        "required to",
        "obliged to",
        "responsible for",
        "deliver",
        "provide",
        "pay",
        "notify",
        "submit",
        "respond",
        "cure",
        "maintain",
    )

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    def monitor_deadlines(
        self,
        *,
        case_id: int,
        case_title: str,
        documents: list[Document],
        consultations: list[ConsultationRequest] | None,
        reasoning_payload: dict[str, Any],
        objective: str | None = None,
    ) -> AgentResult:
        if not documents and not consultations:
            return self.result(
                success=False,
                error="No evidence was provided for deadline monitoring.",
                trace=["Deadline monitor skipped because no documents or consultations were supplied."],
            )

        consultations = consultations or []
        heuristic_payload = self._build_heuristic_payload(
            case_id=case_id,
            case_title=case_title,
            documents=documents,
            consultations=consultations,
            reasoning_payload=reasoning_payload,
            objective=objective,
        )
        trace = [
            f"Starting deadline monitoring for case_id={case_id}.",
            f"Collected {len(heuristic_payload.get('deadline_items', []))} deadline signal(s) and {len(heuristic_payload.get('obligation_items', []))} obligation signal(s).",
            "Built heuristic deadline-monitor payload.",
        ]

        if self.client:
            llm_payload = self._generate_llm_monitor(heuristic_payload=heuristic_payload)
            if llm_payload:
                heuristic_payload.update(llm_payload)
                heuristic_payload["used_llm"] = True
                trace.append("Enhanced deadline-monitor payload with LLM synthesis.")
            else:
                heuristic_payload["used_llm"] = False
                trace.append("LLM synthesis unavailable; kept heuristic deadline-monitor payload.")
        else:
            heuristic_payload["used_llm"] = False
            trace.append("No LLM client configured; kept heuristic deadline-monitor payload.")

        warnings: list[str] = []
        if not heuristic_payload.get("deadline_items"):
            warnings.append("No explicit deadline signals were extracted from the current record.")
        if not heuristic_payload.get("obligation_items"):
            warnings.append("No explicit obligation signals were extracted from the current record.")

        return self.result(success=True, payload=heuristic_payload, warnings=warnings, trace=trace)

    def _build_heuristic_payload(
        self,
        *,
        case_id: int,
        case_title: str,
        documents: list[Document],
        consultations: list[ConsultationRequest],
        reasoning_payload: dict[str, Any],
        objective: str | None,
    ) -> dict[str, Any]:
        deadline_items = self._collect_deadline_items(
            documents=documents,
            consultations=consultations,
            reasoning_payload=reasoning_payload,
        )
        obligation_items = self._collect_obligation_items(documents=documents, reasoning_payload=reasoning_payload)
        evidence_sources = self._collect_evidence_sources(documents=documents, consultations=consultations)

        deadline_summary = (
            f"Case #{case_id} deadline monitor for {case_title}: {len(deadline_items)} deadline signal(s) and {len(obligation_items)} obligation signal(s)."
        )
        if objective:
            deadline_summary += f" Focus: {self._normalize_text(objective)}."

        next_actions = self._build_next_actions(deadline_items=deadline_items, obligation_items=obligation_items)
        confidence = "high" if len(deadline_items) >= 2 or len(obligation_items) >= 2 else "medium" if deadline_items or obligation_items else "low"

        return {
            "case_id": case_id,
            "case_title": case_title,
            "objective": self._normalize_text(objective),
            "deadline_summary": deadline_summary,
            "deadline_items": deadline_items[:10],
            "obligation_items": obligation_items[:10],
            "next_actions": next_actions[:8],
            "evidence_sources": evidence_sources[:10],
            "confidence": confidence,
        }

    def _generate_llm_monitor(self, *, heuristic_payload: dict[str, Any]) -> dict[str, Any] | None:
        prompt = f"""
You are the Deadline Obligation Agent inside a legal AI platform.

Monitor the supplied case record for deadlines, notice windows, cure periods, and live obligations.
{AgentOutputFormatter.build_quality_guidance(task="monitor deadlines and obligations from case evidence", structured_json=True)}

Return valid JSON only with this exact schema:
{{
  "deadline_summary": "string",
  "deadline_items": [
    {{
      "label": "string",
      "value": "string",
      "source": "string",
      "kind": "string",
      "urgency": "string"
    }}
  ],
  "obligation_items": [
    {{
      "obligation": "string",
      "due_date": "string",
      "source": "string",
      "priority": "string",
      "note": "string"
    }}
  ],
  "next_actions": ["string"],
  "confidence": "high"
}}

Rules:
- Use only the provided evidence.
- Do not invent dates or obligations.
- Keep the output practical for a lawyer monitoring live deadlines.

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

            summary = self._normalize_text(payload.get("deadline_summary"))
            deadline_items = self._normalize_deadline_rows(payload.get("deadline_items"), limit=10)
            obligation_items = self._normalize_obligation_rows(payload.get("obligation_items"), limit=10)
            next_actions = self._normalize_string_list(payload.get("next_actions"), limit=8)
            confidence = self._normalize_text(payload.get("confidence")) or "medium"

            if not summary and not deadline_items and not obligation_items:
                return None

            return {
                "deadline_summary": summary or heuristic_payload.get("deadline_summary") or "Deadline monitoring completed from available case evidence.",
                "deadline_items": deadline_items or heuristic_payload.get("deadline_items") or [],
                "obligation_items": obligation_items or heuristic_payload.get("obligation_items") or [],
                "next_actions": next_actions or heuristic_payload.get("next_actions") or [],
                "confidence": confidence,
            }
        except Exception:
            return None

    def _collect_deadline_items(
        self,
        *,
        documents: list[Document],
        consultations: list[ConsultationRequest],
        reasoning_payload: dict[str, Any],
    ) -> list[dict[str, str]]:
        deadline_items: list[dict[str, str]] = []

        for item in reasoning_payload.get("key_dates") or []:
            label = self._normalize_text(item.get("label"))
            value = self._normalize_text(item.get("value"))
            if label and value:
                row = {
                    "label": label,
                    "value": value,
                    "source": "case reasoning",
                    "kind": "deadline",
                    "urgency": self._infer_urgency(label, value),
                }
                if row not in deadline_items:
                    deadline_items.append(row)

        for document in documents:
            insights = self._safe_load_json(document.insights_json)
            for item in insights.get("important_dates") or []:
                label = self._normalize_text(item.get("label"))
                value = self._normalize_text(item.get("value"))
                if label and value:
                    row = {
                        "label": label,
                        "value": value,
                        "source": self._normalize_text(document.filename) or f"Document #{document.id}",
                        "kind": "deadline",
                        "urgency": self._infer_urgency(label, value),
                    }
                    if row not in deadline_items:
                        deadline_items.append(row)

        for consultation in consultations:
            preferred_schedule = self._normalize_text(consultation.preferred_schedule)
            if preferred_schedule:
                row = {
                    "label": "Preferred consultation schedule",
                    "value": preferred_schedule,
                    "source": f"Consultation #{consultation.id}",
                    "kind": "deadline",
                    "urgency": "medium",
                }
                if row not in deadline_items:
                    deadline_items.append(row)

        return self._dedupe_deadline_rows(deadline_items)

    def _collect_obligation_items(
        self,
        *,
        documents: list[Document],
        reasoning_payload: dict[str, Any],
    ) -> list[dict[str, str]]:
        obligation_items: list[dict[str, str]] = []

        for document in documents:
            filename = self._normalize_text(document.filename) or f"Document #{document.id}"
            insights = self._safe_load_json(document.insights_json)
            pieces = [
                self._normalize_text(document.summary_short),
                self._normalize_text(document.summary),
                self._normalize_text(document.redacted_text),
                self._normalize_text(document.extracted_text),
                self._normalize_text(insights.get("general_summary")),
                " ".join(self._normalize_string_list(insights.get("key_points"), limit=6)),
            ]
            text = " ".join(piece for piece in pieces if piece).strip()
            if not text:
                continue

            for sentence in self._extract_obligation_sentences(text):
                obligation_items.append(
                    {
                        "obligation": sentence,
                        "due_date": self._extract_due_date_phrase(sentence),
                        "source": filename,
                        "priority": self._infer_priority(sentence),
                        "note": self._build_obligation_note(sentence),
                    }
                )

        for risk in self._normalize_string_list(reasoning_payload.get("legal_risks"), limit=6):
            obligation_items.append(
                {
                    "obligation": f"Track the risk tied to: {risk}",
                    "due_date": "",
                    "source": "case reasoning",
                    "priority": "medium",
                    "note": "Risk signal extracted from the case reasoning layer.",
                }
            )

        return self._dedupe_obligation_rows(obligation_items)

    def _collect_evidence_sources(self, *, documents: list[Document], consultations: list[ConsultationRequest]) -> list[str]:
        sources: list[str] = []
        for document in documents:
            filename = self._normalize_text(document.filename)
            if filename and filename not in sources:
                sources.append(filename)
        for consultation in consultations:
            source = f"Consultation #{consultation.id}"
            if source not in sources:
                sources.append(source)
        return sources

    def _build_next_actions(
        self,
        *,
        deadline_items: list[dict[str, str]],
        obligation_items: list[dict[str, str]],
    ) -> list[str]:
        actions: list[str] = []
        if deadline_items:
            actions.append("Create a live deadline register with owner, trigger, and response window.")
        if obligation_items:
            actions.append("Cross-check each obligation against the underlying contract or notice language.")
        if deadline_items and obligation_items:
            actions.append("Link each obligation to the deadline it creates so nothing is tracked twice.")
        if not actions:
            actions.append("Review the record manually to confirm whether any live deadlines still need extraction.")
        return actions

    @staticmethod
    def _extract_obligation_sentences(text: str) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        obligation_sentences: list[str] = []
        for sentence in sentences:
            cleaned = AgentOutputFormatter.sanitize_text(sentence)
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if any(keyword in lowered for keyword in DeadlineObligationAgent.OBLIGATION_KEYWORDS) or any(
                keyword in lowered for keyword in DeadlineObligationAgent.DEADLINE_KEYWORDS
            ):
                obligation_sentences.append(cleaned[:220])
        return obligation_sentences[:8]

    @staticmethod
    def _extract_due_date_phrase(sentence: str) -> str:
        match = re.search(
            r"\b(?:within|by|no later than|on or before|before|after)\b[^.;]{0,80}",
            sentence,
            flags=re.IGNORECASE,
        )
        if match:
            return AgentOutputFormatter.sanitize_text(match.group(0))[:120]
        return ""

    @staticmethod
    def _infer_priority(sentence: str) -> str:
        lowered = sentence.lower()
        if any(marker in lowered for marker in ["cure", "breach", "deadline", "final", "terminate", "notice period"]):
            return "high"
        if any(marker in lowered for marker in ["within", "by", "due", "submit", "provide", "respond"]):
            return "medium"
        return "low"

    @staticmethod
    def _infer_urgency(label: str, value: str) -> str:
        lowered = f"{label} {value}".lower()
        if any(marker in lowered for marker in ["cure", "breach", "deadline", "renewal", "expiration"]):
            return "high"
        if any(marker in lowered for marker in ["within", "by", "notice", "response"]):
            return "medium"
        return "low"

    @staticmethod
    def _build_obligation_note(sentence: str) -> str:
        lowered = sentence.lower()
        if any(marker in lowered for marker in ["cure", "notice"]):
            return "Monitor notice and cure timing carefully."
        if any(marker in lowered for marker in ["payment", "invoice"]):
            return "Likely tied to payment timing or invoice handling."
        if any(marker in lowered for marker in ["deliver", "provide", "submit"]):
            return "Likely a delivery or filing obligation."
        if any(marker in lowered for marker in ["renewal", "expiration"]):
            return "Track this for renewal or termination risk."
        return "Live obligation signal captured from the record."

    @staticmethod
    def _dedupe_deadline_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for row in rows:
            key = (row.get("label", "").lower(), row.get("value", "").lower(), row.get("source", "").lower())
            if key in seen:
                continue
            seen.add(key)
            normalized.append(row)
        return normalized

    @staticmethod
    def _dedupe_obligation_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in rows:
            key = f"{row.get('obligation', '')}|{row.get('source', '')}".lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(row)
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
            kind = AgentOutputFormatter.sanitize_text(item.get("kind")) or "deadline"
            urgency = AgentOutputFormatter.sanitize_text(item.get("urgency")) or "medium"
            if not (label and value):
                continue
            row = {"label": label, "value": value, "source": source, "kind": kind, "urgency": urgency}
            if row not in normalized:
                normalized.append(row)
            if limit is not None and len(normalized) >= limit:
                break
        return normalized

    @staticmethod
    def _normalize_obligation_rows(values: Any, *, limit: int | None = None) -> list[dict[str, Any]]:
        if not isinstance(values, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            obligation = AgentOutputFormatter.sanitize_text(item.get("obligation"))
            due_date = AgentOutputFormatter.sanitize_text(item.get("due_date"))
            source = AgentOutputFormatter.sanitize_text(item.get("source"))
            priority = AgentOutputFormatter.sanitize_text(item.get("priority")) or "medium"
            note = AgentOutputFormatter.sanitize_text(item.get("note"))
            if not obligation:
                continue
            row = {
                "obligation": obligation,
                "due_date": due_date,
                "source": source,
                "priority": priority,
                "note": note,
            }
            if row not in normalized:
                normalized.append(row)
            if limit is not None and len(normalized) >= limit:
                break
        return normalized

    @staticmethod
    def _normalize_string_list(values: Any, *, limit: int | None = None) -> list[str]:
        return AgentOutputFormatter.normalize_string_list(values, limit=limit)

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


deadline_obligation_agent = DeadlineObligationAgent()