from __future__ import annotations

import json
from typing import Any, Optional

from backend.services.ai.agents.agent_output_formatter import AgentOutputFormatter
from backend.services.ai.llm_gateway import llm_gateway


class SummarizationAgent:
    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.summary_model

    @property
    def available(self) -> bool:
        return self.client is not None

    def summarize_document(
        self,
        *,
        filename: str,
        document_text: str,
        heuristic_insights: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        if not self.client:
            return None

        prompt = self._build_document_prompt(
            filename=filename,
            document_text=document_text,
            heuristic_insights=heuristic_insights,
        )

        try:
            response = self.client.responses.create(
                model=self.model,
                input=prompt,
            )

            raw_text = (response.output_text or "").strip()
            if not raw_text:
                return None

            payload = self._extract_json_payload(raw_text)
            if not payload:
                return None

            return self._normalize_payload(payload, heuristic_insights)
        except Exception:
            return None

    def _build_document_prompt(
        self,
        *,
        filename: str,
        document_text: str,
        heuristic_insights: dict[str, Any],
    ) -> str:
        return f"""
You are the Summarization Agent inside a legal AI system.

Your task is to improve a legal document summary while staying grounded in the provided document text and heuristic extraction.
Do not invent facts, laws, dates, obligations, or parties.
If some detail is uncertain, keep the wording cautious and omit unsupported claims.

    {AgentOutputFormatter.build_quality_guidance(task="summarize a legal document", structured_json=True)}

Return valid JSON only with this exact schema:
{{
  "summary": "string",
  "summary_short": "string",
  "document_type": "string",
  "key_points": ["string"],
  "important_dates": [{{"label": "string", "value": "string"}}],
  "parties_detected": ["string"],
  "legal_risks": ["string"],
  "recommended_actions": ["string"],
  "summary_source": "llm_summary_agent",
  "summary_version": "v1"
}}

Requirements for "summary":
- Use this structure exactly:
Overview:
<narrative>

Main Issues:
- ...

Key Obligations / Clauses:
- ...

Key Dates:
- ...

Legal Risks:
- ...

Recommended Next Steps:
- ...

Requirements for "summary_short":
- 2 to 4 sentences
- crisp and professional

Filename:
{filename}

Heuristic insights:
{json.dumps(heuristic_insights, ensure_ascii=False, indent=2)}

Document text:
{document_text}
"""

    @staticmethod
    def _extract_json_payload(raw_text: str) -> Optional[dict[str, Any]]:
        return AgentOutputFormatter.extract_json_payload(raw_text)

    @staticmethod
    def _normalize_payload(payload: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary": AgentOutputFormatter.sanitize_text(payload.get("summary")),
            "summary_short": AgentOutputFormatter.sanitize_text(payload.get("summary_short")),
            "document_type": AgentOutputFormatter.sanitize_text(payload.get("document_type") or fallback.get("document_type") or "unknown"),
            "key_points": AgentOutputFormatter.normalize_string_list(payload.get("key_points") or fallback.get("key_points") or [], limit=8),
            "important_dates": AgentOutputFormatter.normalize_date_items(payload.get("important_dates") or fallback.get("important_dates") or []),
            "parties_detected": AgentOutputFormatter.normalize_string_list(payload.get("parties_detected") or fallback.get("parties_detected") or [], limit=8),
            "legal_risks": AgentOutputFormatter.normalize_string_list(payload.get("legal_risks") or fallback.get("legal_risks") or [], limit=8),
            "recommended_actions": AgentOutputFormatter.normalize_string_list(payload.get("recommended_actions") or fallback.get("recommended_actions") or [], limit=8),
            "summary_source": AgentOutputFormatter.sanitize_text(payload.get("summary_source") or "llm_summary_agent"),
            "summary_version": AgentOutputFormatter.sanitize_text(payload.get("summary_version") or "v1"),
        }


summarization_agent = SummarizationAgent()
