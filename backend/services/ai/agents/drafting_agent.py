from __future__ import annotations

from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.llm_gateway import llm_gateway


class DraftingAgent(BaseAgent):
    agent_name = "drafting_agent"

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    def draft_client_update_email(
        self,
        *,
        case_id: int,
        case_title: str,
        case_summary: str,
    ) -> AgentResult:
        normalized_summary = (case_summary or "").strip()
        if not normalized_summary:
            return self.result(
                success=False,
                error="Case summary is empty.",
                trace=["Input validation failed: case summary missing for drafting."],
            )

        trace = [
            f"Starting drafting for case_id={case_id}.",
            "Using grounded case summary as drafting context.",
        ]

        if self.client:
            prompt = f"""
You are the Drafting Agent inside a legal AI platform.

Draft a professional client update email using only the provided grounded case summary.
Do not invent facts.
Keep the tone clear, calm, and professional.
Keep the email concise and practical.

Structure:
1) Subject line
2) One short status paragraph
3) "Key points" bullet list (3-6 bullets)
4) "Next steps" bullet list (2-4 bullets)
5) Closing with invitation for questions

Return only the email body.

Case id: {case_id}
Case title: {case_title}

Grounded case summary:
{normalized_summary}
"""
            try:
                response = self.client.responses.create(
                    model=self.model,
                    input=prompt,
                )
                email_body = (response.output_text or "").strip()
                if email_body:
                    trace.append("Drafting agent generated the email with LLM assistance.")
                    return self.result(
                        success=True,
                        payload={
                            "email_body": email_body,
                            "used_llm": True,
                        },
                        trace=trace,
                    )
            except Exception:
                trace.append("LLM drafting failed; falling back to template-based drafting.")

        fallback_email = (
            f"Subject: Update on Case {case_id} - {case_title}\n\n"
            "Dear Client,\n\n"
            "I am writing to provide a concise update on your case status.\n\n"
            f"{normalized_summary}\n\n"
            "Next steps:\n"
            "- We will continue monitoring deadlines and evidence consistency.\n"
            "- We will share any material updates promptly.\n\n"
            "Please let me know if you would like a deeper breakdown by issue or document.\n\n"
            "Best regards,\n"
            "Your Legal Team"
        )
        trace.append("Drafting agent produced a template-based fallback email.")

        return self.result(
            success=True,
            payload={
                "email_body": fallback_email,
                "used_llm": False,
            },
            trace=trace,
        )


drafting_agent = DraftingAgent()
