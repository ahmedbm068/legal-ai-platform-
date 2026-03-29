from __future__ import annotations

import json
from typing import Any

from backend.models.consultation_request import ConsultationRequest
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.llm_gateway import llm_gateway


class BookingAgent(BaseAgent):
    agent_name = "booking_agent"

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    def analyze_consultations(
        self,
        *,
        case_id: int,
        case_title: str,
        consultations: list[ConsultationRequest],
    ) -> AgentResult:
        if not consultations:
            return self.result(
                success=False,
                error="No consultation requests available for booking analysis.",
                trace=["Booking agent skipped because no consultation requests were supplied."],
            )

        heuristic_payload = self._build_heuristic_payload(
            case_id=case_id,
            case_title=case_title,
            consultations=consultations,
        )
        trace = [
            f"Starting booking analysis for case_id={case_id}.",
            f"Processed {len(consultations)} consultation request(s).",
            "Built heuristic booking payload.",
        ]

        if self.client:
            llm_payload = self._generate_llm_booking_brief(heuristic_payload=heuristic_payload)
            if llm_payload:
                heuristic_payload.update(llm_payload)
                heuristic_payload["used_llm"] = True
                trace.append("Enhanced booking payload with LLM synthesis.")
            else:
                heuristic_payload["used_llm"] = False
                trace.append("LLM synthesis unavailable; kept heuristic booking payload.")
        else:
            heuristic_payload["used_llm"] = False
            trace.append("No LLM client configured; kept heuristic booking payload.")

        warnings: list[str] = []
        if not heuristic_payload.get("preferred_schedule"):
            warnings.append("No preferred schedule was clearly captured yet.")
        if heuristic_payload.get("booking_intent") != "requested":
            warnings.append("No strong booking request signal was found.")

        return self.result(
            success=True,
            payload=heuristic_payload,
            warnings=warnings,
            trace=trace,
        )

    def _build_heuristic_payload(
        self,
        *,
        case_id: int,
        case_title: str,
        consultations: list[ConsultationRequest],
    ) -> dict[str, Any]:
        latest = consultations[0]
        preferred_schedule = self._first_non_empty(
            request.preferred_schedule for request in consultations
        )
        legal_area = self._first_non_empty(request.legal_area for request in consultations)
        client_name = self._first_non_empty(request.client_name for request in consultations)
        issue_summary = self._first_non_empty(request.issue_summary for request in consultations)

        urgency_rank = {"low": 0, "normal": 1, "medium": 2, "high": 3, "urgent": 4}
        urgency_level = max(
            (self._normalize_text(request.urgency_level).lower() for request in consultations),
            key=lambda value: urgency_rank.get(value, 1),
            default="normal",
        )

        booking_requested = any(
            self._normalize_text(request.booking_intent).lower() == "requested"
            for request in consultations
        )
        booking_intent = "requested" if booking_requested else self._normalize_text(latest.booking_intent) or "not_detected"

        next_action = (
            f"Offer available consultation slots for {preferred_schedule}."
            if preferred_schedule
            else "Contact the client to confirm their preferred consultation time."
        )

        narrative = (
            f"Booking overview for case {case_id} - {case_title}: "
            f"{client_name or 'The client'} has a consultation status of '{latest.status}'. "
            f"Booking intent is '{booking_intent}', urgency is '{urgency_level}', "
            f"and the preferred schedule is '{preferred_schedule or 'not yet provided'}'."
        )

        return {
            "client_name": client_name,
            "issue_summary": issue_summary,
            "legal_area": legal_area,
            "booking_intent": booking_intent,
            "urgency_level": urgency_level,
            "preferred_schedule": preferred_schedule,
            "status": latest.status,
            "recommended_action": next_action,
            "narrative_summary": narrative,
        }

    def _generate_llm_booking_brief(self, *, heuristic_payload: dict[str, Any]) -> dict[str, Any] | None:
        prompt = f"""
You are the Booking Agent inside a legal AI platform.

You receive structured consultation-booking context for a legal case.
Return valid JSON only with this schema:
{{
  "narrative_summary": "string",
  "recommended_action": "string"
}}

Rules:
- Do not invent scheduling details.
- Keep the language practical and operational.

Booking context:
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

            return {
                "narrative_summary": self._normalize_text(payload.get("narrative_summary"))
                or heuristic_payload.get("narrative_summary", ""),
                "recommended_action": self._normalize_text(payload.get("recommended_action"))
                or heuristic_payload.get("recommended_action", ""),
            }
        except Exception:
            return None

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

    def _first_non_empty(self, values) -> str | None:
        for value in values:
            cleaned = self._normalize_text(value)
            if cleaned:
                return cleaned
        return None


booking_agent = BookingAgent()
