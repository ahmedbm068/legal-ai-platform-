from __future__ import annotations

import json
from typing import Any

from backend.models.document import Document
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.llm_gateway import llm_gateway


class DocumentComparisonAgent(BaseAgent):
    agent_name = "document_comparison_agent"

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    def compare_case_documents(
        self,
        *,
        case_id: int,
        documents: list[Document],
    ) -> AgentResult:
        if len(documents) < 2:
            return self.result(
                success=False,
                error="Need at least two documents for comparison.",
                trace=["Document comparison agent skipped because fewer than two documents were provided."],
            )

        heuristic_payload = self._build_heuristic_payload(case_id=case_id, documents=documents)
        trace = [
            f"Starting document comparison for case_id={case_id}.",
            f"Processed {len(documents)} documents.",
            "Built heuristic comparison payload.",
        ]

        if self.client:
            llm_payload = self._generate_llm_comparison(heuristic_payload=heuristic_payload)
            if llm_payload:
                heuristic_payload.update(llm_payload)
                heuristic_payload["used_llm"] = True
                trace.append("Enhanced comparison payload with LLM synthesis.")
            else:
                heuristic_payload["used_llm"] = False
                trace.append("LLM synthesis unavailable; kept heuristic comparison payload.")
        else:
            heuristic_payload["used_llm"] = False
            trace.append("No LLM client configured; kept heuristic comparison payload.")

        return self.result(success=True, payload=heuristic_payload, trace=trace)

    def _build_heuristic_payload(self, *, case_id: int, documents: list[Document]) -> dict[str, Any]:
        document_rows: list[dict[str, Any]] = []
        all_types: set[str] = set()
        all_dates: set[str] = set()
        all_risks: set[str] = set()

        for document in documents[:10]:
            insights = self._safe_load_json(document.insights_json)
            summary = self._normalize_text(
                document.summary_short or document.summary or (document.redacted_text or document.extracted_text or "")[:240]
            )
            document_type = self._normalize_text(insights.get("document_type") or document.document_type or "unknown")
            important_dates = [
                f"{self._normalize_text(item.get('label'))}: {self._normalize_text(item.get('value'))}"
                for item in insights.get("important_dates", [])
                if self._normalize_text(item.get("label")) and self._normalize_text(item.get("value"))
            ]
            legal_risks = [
                self._normalize_text(item)
                for item in insights.get("legal_risks", [])
                if self._normalize_text(item)
            ]

            all_types.add(document_type)
            all_dates.update(important_dates)
            all_risks.update(legal_risks)

            document_rows.append(
                {
                    "filename": document.filename,
                    "document_type": document_type,
                    "summary": summary,
                    "important_dates": important_dates[:8],
                    "legal_risks": legal_risks[:8],
                }
            )

        comparison_lines = [f"Comparison overview for case {case_id}:"]
        for row in document_rows:
            comparison_lines.append(
                f"- {row['filename']}: type={row['document_type']}, "
                f"dates={len(row['important_dates'])}, risks={len(row['legal_risks'])}, summary={row['summary']}"
            )

        if len(all_types) > 1:
            comparison_lines.append("")
            comparison_lines.append("Different document types are present across the case file.")
        if all_dates:
            comparison_lines.append("")
            comparison_lines.append("Date references found across documents:")
            comparison_lines.extend(f"- {item}" for item in sorted(all_dates)[:12])
        if all_risks:
            comparison_lines.append("")
            comparison_lines.append("Risk markers found across documents:")
            comparison_lines.extend(f"- {item}" for item in sorted(all_risks)[:12])

        comparison_lines.append("")
        comparison_lines.append("Manual follow-up: review contradictions, date mismatches, and coverage gaps across these documents.")

        return {
            "document_rows": document_rows,
            "comparison_text": "\n".join(comparison_lines).strip(),
        }

    def _generate_llm_comparison(self, *, heuristic_payload: dict[str, Any]) -> dict[str, Any] | None:
        prompt = f"""
You are the Document Comparison Agent inside a legal AI platform.

Compare the supplied documents and produce one practical comparison note.
Return valid JSON only with this schema:
{{
  "comparison_text": "string"
}}

Do not invent contradictions. If evidence is thin, keep the wording cautious.

Document comparison context:
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

            comparison_text = self._normalize_text(payload.get("comparison_text"))
            if not comparison_text:
                return None
            return {"comparison_text": comparison_text}
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


document_comparison_agent = DocumentComparisonAgent()
