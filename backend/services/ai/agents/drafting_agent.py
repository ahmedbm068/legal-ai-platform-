from __future__ import annotations

import re

from backend.services.ai.agents.agent_output_formatter import AgentOutputFormatter
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.llm_gateway import llm_gateway


class DraftingAgent(BaseAgent):
    agent_name = "drafting_agent"

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip())

    @classmethod
    def _trim(cls, value: str, max_chars: int) -> str:
        cleaned = cls._clean_text(value)
        if len(cleaned) <= max_chars:
            return cleaned
        return f"{cleaned[:max_chars - 1].rstrip()}..."

    @classmethod
    def _extract_key_points(cls, case_summary: str, limit: int = 5) -> list[str]:
        points: list[str] = []
        seen: set[str] = set()

        for raw_line in (case_summary or "").splitlines():
            candidate = raw_line.strip()
            if not candidate:
                continue

            candidate = re.sub(r"^[\-•*\d\.)\s]+", "", candidate)
            candidate = cls._clean_text(candidate)

            if not candidate:
                continue

            lowered = candidate.lower()
            if lowered.startswith("document "):
                continue
            if lowered.startswith("case ") and "currently includes" in lowered:
                continue

            normalized_key = lowered[:180]
            if normalized_key in seen:
                continue

            seen.add(normalized_key)
            points.append(cls._trim(candidate, 180))
            if len(points) >= limit:
                return points

        compact = cls._clean_text(case_summary or "")
        if compact:
            for sentence in re.split(r"(?<=[.!?])\s+", compact):
                candidate = cls._trim(sentence, 180)
                if not candidate:
                    continue
                normalized_key = candidate.lower()
                if normalized_key in seen:
                    continue
                seen.add(normalized_key)
                points.append(candidate)
                if len(points) >= limit:
                    break

        return points

    @classmethod
    def _fallback_email(
        cls,
        *,
        case_id: int,
        case_title: str,
        case_summary: str,
        jurisdiction_country: str | None,
    ) -> str:
        key_points = cls._extract_key_points(case_summary, limit=4)
        summary_sentence = key_points[0] if key_points else cls._trim(case_summary, 320)
        jurisdiction_note = f" This matter is being handled under {jurisdiction_country} context." if jurisdiction_country else ""

        lines = [
            f"Subject: Case #{case_id} update - {case_title}",
            "",
            "Dear Client,",
            "",
            f"I wanted to share a clear update on case #{case_id} ({case_title}).{jurisdiction_note}",
            "",
            f"Current status: {summary_sentence or 'We are actively reviewing the latest material and progressing the matter.'}",
            "",
            "Key points:",
        ]

        if key_points:
            for point in key_points[:4]:
                lines.append(f"- {point}")
        else:
            lines.extend(
                [
                    "- We have reviewed the current case material on file.",
                    "- We are aligning facts, chronology, and obligations before the next filing step.",
                ]
            )

        lines.extend(
            [
                "",
                "Next steps:",
                "- Confirm any remaining factual or documentary gaps.",
                "- Share a focused action plan with deadlines and responsibilities.",
                "",
                "Please let me know if you would like a call this week to walk through this update line by line.",
                "",
                "Best regards,",
                "Your Legal Team",
            ]
        )

        return "\n".join(lines).strip()

    def draft_client_update_email(
        self,
        *,
        case_id: int,
        case_title: str,
        case_summary: str,
        jurisdiction_country: str | None = None,
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
        if jurisdiction_country:
            trace.append(f"Applying jurisdiction context for {jurisdiction_country}.")

        if self.client:
            jurisdiction_line = (
                f"The case jurisdiction is {jurisdiction_country}. Keep wording aligned with that legal context.\n"
                if jurisdiction_country
                else ""
            )
            distilled_points = self._extract_key_points(normalized_summary, limit=8)
            points_block = "\n".join(f"- {item}" for item in distilled_points) or "- No distilled points were available from the summary."
            prompt = f"""
You are the Drafting Agent inside a legal AI platform, writing to a non-lawyer client.

Draft a professional client update email using ONLY the grounded case summary and distilled points below.
Do not invent facts, dates, outcomes, names, or commitments.
If a detail is missing, explicitly state that the team is still confirming it.
Write in plain English that a client can read in under one minute.
Avoid legal jargon unless necessary; when needed, explain it briefly.
Do not mention AI, model behavior, prompts, "grounded summary", or internal tooling.

{AgentOutputFormatter.build_quality_guidance(task="draft a concise client-facing legal update email", structured_json=False)}

Output format requirements:
1) Subject line
2) Greeting: "Dear Client,"
3) One concise status paragraph
4) "Key points" section with 3-5 bullets (specific, client-facing)
5) "Next steps" section with exactly 2-3 bullets (concrete and practical)
6) Reassuring closing + invitation for questions

Length target: 160-240 words.
Tone: calm, professional, transparent, and action-oriented.

Return only the email body.

{jurisdiction_line}
Case id: {case_id}
Case title: {case_title}

Distilled points from case materials:
{points_block}

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

        fallback_email = self._fallback_email(
            case_id=case_id,
            case_title=case_title,
            case_summary=normalized_summary,
            jurisdiction_country=jurisdiction_country,
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
