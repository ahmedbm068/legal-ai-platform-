from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from backend.models.consultation_request import ConsultationRequest
from backend.models.document import Document
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.llm_gateway import llm_gateway


class TimelineAgent(BaseAgent):
    agent_name = "timeline_agent"

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    def build_case_timeline(
        self,
        *,
        case_id: int,
        case_title: str,
        documents: list[Document],
        consultations: list[ConsultationRequest] | None = None,
    ) -> AgentResult:
        if not documents and not consultations:
            return self.result(
                success=False,
                error="No evidence was provided for timeline generation.",
                trace=["Timeline agent skipped because no documents or consultations were supplied."],
            )

        heuristic_payload = self._build_heuristic_payload(
            case_id=case_id,
            case_title=case_title,
            documents=documents,
            consultations=consultations or [],
        )
        trace = [
            f"Starting timeline generation for case_id={case_id}.",
            f"Collected {len(heuristic_payload.get('events', []))} timeline event(s).",
            "Built heuristic timeline payload.",
        ]

        if self.client and heuristic_payload.get("events"):
            llm_payload = self._generate_llm_timeline(heuristic_payload=heuristic_payload)
            if llm_payload:
                heuristic_payload.update(llm_payload)
                heuristic_payload["used_llm"] = True
                trace.append("Enhanced timeline payload with LLM synthesis.")
            else:
                heuristic_payload["used_llm"] = False
                trace.append("LLM synthesis unavailable; kept heuristic timeline payload.")
        else:
            heuristic_payload["used_llm"] = False
            trace.append("No LLM client configured or no events found; kept heuristic timeline payload.")

        warnings: list[str] = []
        if not heuristic_payload.get("events"):
            warnings.append("No explicit timeline events were extracted from the current case evidence.")

        return self.result(success=True, payload=heuristic_payload, warnings=warnings, trace=trace)

    def _build_heuristic_payload(
        self,
        *,
        case_id: int,
        case_title: str,
        documents: list[Document],
        consultations: list[ConsultationRequest],
    ) -> dict[str, Any]:
        events: list[dict[str, str]] = []

        for document in documents:
            insights = self._safe_load_json(document.insights_json)
            for item in insights.get("important_dates", []):
                label = self._normalize_text(item.get("label"))
                value = self._normalize_text(item.get("value"))
                if not label or not value:
                    continue
                event = {
                    "date": value,
                    "label": label,
                    "source": document.filename,
                }
                if event not in events:
                    events.append(event)

        for consultation in consultations:
            preferred_schedule = self._normalize_text(consultation.preferred_schedule)
            if preferred_schedule:
                event = {
                    "date": preferred_schedule,
                    "label": "Preferred consultation schedule",
                    "source": f"Consultation #{consultation.id}",
                }
                if event not in events:
                    events.append(event)

        events = sorted(events, key=self._event_sort_key)

        timeline_text = [f"Case timeline for case {case_id} - {case_title}:"]
        if events:
            for event in events[:20]:
                timeline_text.append(f"- {event['date']} | {event['label']} | source: {event['source']}")
        else:
            timeline_text.append("- No explicit timeline events were extracted yet.")

        return {
            "events": events[:20],
            "timeline_text": "\n".join(timeline_text),
        }

    def _generate_llm_timeline(self, *, heuristic_payload: dict[str, Any]) -> dict[str, Any] | None:
        prompt = f"""
You are the Timeline Agent inside a legal AI platform.

You receive extracted timeline events from a legal case.
Return valid JSON only with this schema:
{{
  "timeline_text": "string"
}}

Rules:
- Use only the provided events.
- Keep the timeline practical and concise.
- Do not invent dates.

Timeline context:
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
            timeline_text = self._normalize_text(payload.get("timeline_text"))
            if not timeline_text:
                return None
            return {"timeline_text": timeline_text}
        except Exception:
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
    def _normalize_text(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _event_sort_key(event: dict[str, str]) -> tuple[int, datetime]:
        value = (event.get("date") or "").strip()
        parsed = TimelineAgent._try_parse_date(value)
        if parsed is None:
            return (1, datetime.max)
        return (0, parsed)

    @staticmethod
    def _try_parse_date(value: str) -> datetime | None:
        normalized = value.strip()
        if not normalized:
            return None

        patterns = [
            "%Y-%m-%d",
            "%B %d, %Y",
            "%b %d, %Y",
        ]
        for fmt in patterns:
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue

        inline = re.search(r"\d{4}-\d{2}-\d{2}", normalized)
        if inline:
            try:
                return datetime.strptime(inline.group(0), "%Y-%m-%d")
            except ValueError:
                return None
        return None


timeline_agent = TimelineAgent()
