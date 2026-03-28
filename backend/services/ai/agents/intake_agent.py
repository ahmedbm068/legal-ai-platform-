from __future__ import annotations

from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.transcript_intake_service import transcript_intake_service


class IntakeAgent(BaseAgent):
    agent_name = "intake_agent"

    def process_transcript(
        self,
        *,
        transcript_text: str,
        preferred_schedule: str | None = None,
        fallback_client_name: str | None = None,
        fallback_client_email: str | None = None,
        fallback_client_phone: str | None = None,
        fallback_issue_summary: str | None = None,
        fallback_case_description: str | None = None,
    ) -> AgentResult:
        if not transcript_text or not transcript_text.strip():
            return self.result(
                success=False,
                error="Transcript text is empty.",
                trace=["Input validation failed: transcript text missing."],
            )

        trace = [
            "Received transcript text for intake processing.",
            "Running transcript intake extraction heuristics.",
        ]

        payload = transcript_intake_service.build_intake(transcript_text)

        if fallback_client_name and not payload.get("client_name"):
            payload["client_name"] = fallback_client_name
            trace.append("Applied fallback client name.")
        if fallback_client_email and not payload.get("client_email"):
            payload["client_email"] = fallback_client_email
            trace.append("Applied fallback client email.")
        if fallback_client_phone and not payload.get("client_phone"):
            payload["client_phone"] = fallback_client_phone
            trace.append("Applied fallback client phone.")
        if preferred_schedule and not payload.get("preferred_schedule"):
            payload["preferred_schedule"] = preferred_schedule
            payload["booking_intent"] = "requested"
            trace.append("Applied fallback preferred schedule and upgraded booking intent.")
        if fallback_issue_summary and not payload.get("issue_summary"):
            payload["issue_summary"] = fallback_issue_summary
            trace.append("Applied fallback issue summary.")
        if fallback_case_description and not payload.get("extracted_case_description"):
            payload["extracted_case_description"] = fallback_case_description
            trace.append("Applied fallback case description.")

        warnings: list[str] = []
        if not payload.get("client_name"):
            warnings.append("Client name could not be confidently extracted.")
        if payload.get("booking_intent") != "requested":
            warnings.append("No strong booking request signal detected in transcript.")
        if not payload.get("preferred_schedule"):
            warnings.append("Preferred schedule was not detected.")

        trace.append("Intake agent completed transcript processing.")

        return self.result(
            success=True,
            payload=payload,
            warnings=warnings,
            trace=trace,
        )


intake_agent = IntakeAgent()
