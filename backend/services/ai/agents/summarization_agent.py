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
  "legal_case_analysis": {{
    "case_name": "string",
    "court_level": "string",
    "citation": "string",
    "judges": ["string"],
    "catchwords": ["string"],
    "headnote_warning": "string",
    "fact_flowchart": ["chronological legally material fact"],
    "legal_issues": ["string"],
    "holding": ["string"],
    "ratio": ["string"],
    "obiter": ["string"],
    "summary_bullets": ["string"]
  }},
  "summary_source": "llm_summary_agent",
  "summary_version": "v2_case_reading"
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

Legal Case Reading Brief:
Case Anatomy:
- Case: ...
- Court: ...
- Citation: ...
- Catchwords: ...

Headnote Caution:
- Treat headnotes as orientation only; verify the facts, holding, ratio, and obiter against the judgment text.

Fact Flowchart:
- ...

Legal Issue(s):
- ...

Holding:
- ...

Ratio Decidendi:
- ...

Obiter Dicta:
- ...

Half-Page Case Summary:
- ...

Legal Risks:
- ...

Recommended Next Steps:
- ...

Legal case reading method:
- If the document is a judgment, reported case, law report, or case note, analyze it like a lawyer reading a case.
- Start from case anatomy: parties, court, citation, catchwords/legal area, and judges when available.
- Treat any headnote as helpful but non-authoritative; verify against the judgment.
- Build a chronological fact flowchart of legally material facts only. Ask whether omitting the fact would change the outcome.
- Separate legal issue, holding, ratio decidendi, and obiter dicta.
- Ratio must be the necessary legal reasoning for the outcome, not every interesting statement.
- Obiter is useful commentary, dissent, hypotheticals, or statements not necessary to the result.
- Compress the final case note into revision-ready bullets.
- If the document is not a legal case, return an empty legal_case_analysis object and omit the Legal Case Reading Brief section from the summary.

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
            "legal_case_analysis": SummarizationAgent._normalize_case_analysis(
                payload.get("legal_case_analysis") or fallback.get("legal_case_analysis") or {}
            ),
            "summary_source": AgentOutputFormatter.sanitize_text(payload.get("summary_source") or "llm_summary_agent"),
            "summary_version": AgentOutputFormatter.sanitize_text(payload.get("summary_version") or "v2_case_reading"),
        }

    @staticmethod
    def _normalize_case_analysis(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}

        return {
            "case_name": AgentOutputFormatter.sanitize_text(value.get("case_name")),
            "court_level": AgentOutputFormatter.sanitize_text(value.get("court_level")),
            "citation": AgentOutputFormatter.sanitize_text(value.get("citation")),
            "judges": AgentOutputFormatter.normalize_string_list(value.get("judges"), limit=8),
            "catchwords": AgentOutputFormatter.normalize_string_list(value.get("catchwords"), limit=10),
            "headnote_warning": AgentOutputFormatter.sanitize_text(value.get("headnote_warning")),
            "fact_flowchart": AgentOutputFormatter.normalize_string_list(value.get("fact_flowchart"), limit=8),
            "legal_issues": AgentOutputFormatter.normalize_string_list(value.get("legal_issues"), limit=6),
            "holding": AgentOutputFormatter.normalize_string_list(value.get("holding"), limit=6),
            "ratio": AgentOutputFormatter.normalize_string_list(value.get("ratio"), limit=6),
            "obiter": AgentOutputFormatter.normalize_string_list(value.get("obiter"), limit=6),
            "summary_bullets": AgentOutputFormatter.normalize_string_list(value.get("summary_bullets"), limit=10),
        }


summarization_agent = SummarizationAgent()
