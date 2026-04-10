from __future__ import annotations

import json
import re
from typing import Any

from backend.models.document import Document
from backend.services.ai.agents.agent_output_formatter import AgentOutputFormatter
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.llm_gateway import llm_gateway


class EvidenceStrengthAgent(BaseAgent):
    agent_name = "evidence_strength_agent"

    NON_LEGAL_FILENAME_MARKERS = (
        "runbook",
        "smoke",
        "test",
        "prompt",
        "readme",
        ".md",
    )
    STRONG_EVIDENCE_KEYWORDS = (
        "master service agreement",
        "service agreement",
        "msa",
        "contract",
        "agreement",
        "sla",
        "service level",
        "notice of breach",
        "breach notice",
        "cure period",
        "termination",
        "payment terms",
        "invoice",
        "reconciliation",
        "kpi",
        "dashboard",
        "performance",
        "material breach",
        "default",
    )
    WEAK_EVIDENCE_KEYWORDS = (
        "internal memo",
        "memo",
        "summary",
        "draft",
        "template",
        "runbook",
        "test",
        "smoke",
        "prompt",
        "readme",
    )

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    def evaluate_evidence_strength(
        self,
        *,
        case_id: int,
        case_title: str,
        objective: str,
        documents: list[Document],
        reasoning_payload: dict[str, Any],
    ) -> AgentResult:
        if not documents:
            return self.result(
                success=False,
                error="No documents were provided for evidence assessment.",
                trace=["Evidence strength agent skipped because no documents were supplied."],
            )

        heuristic_payload = self._build_heuristic_payload(
            case_id=case_id,
            case_title=case_title,
            objective=objective,
            documents=documents,
            reasoning_payload=reasoning_payload,
        )
        trace = [
            f"Starting evidence-strength review for case_id={case_id}.",
            f"Processed {len(documents)} document(s) for material-breach evidence ranking.",
            "Built heuristic evidence-strength payload.",
        ]

        if self.client:
            llm_payload = self._generate_llm_assessment(heuristic_payload=heuristic_payload)
            if llm_payload:
                heuristic_payload.update(llm_payload)
                heuristic_payload["used_llm"] = True
                trace.append("Enhanced evidence-strength payload with LLM synthesis.")
            else:
                heuristic_payload["used_llm"] = False
                trace.append("LLM synthesis unavailable; kept heuristic evidence-strength payload.")
        else:
            heuristic_payload["used_llm"] = False
            trace.append("No LLM client configured; kept heuristic evidence-strength payload.")

        warnings: list[str] = []
        if not heuristic_payload.get("strongest_evidence"):
            warnings.append("No strong material-breach evidence signals were extracted from the current record.")

        return self.result(success=True, payload=heuristic_payload, warnings=warnings, trace=trace)

    def _build_heuristic_payload(
        self,
        *,
        case_id: int,
        case_title: str,
        objective: str,
        documents: list[Document],
        reasoning_payload: dict[str, Any],
    ) -> dict[str, Any]:
        evaluated_rows: list[dict[str, Any]] = []
        evidence_sources: list[str] = []

        reasoning_terms = self._collect_reasoning_terms(reasoning_payload)

        for document in documents[:15]:
            insights = self._safe_load_json(document.insights_json)
            filename = self._normalize_text(document.filename) or f"Document #{document.id}"
            evidence_text = " ".join(
                [
                    filename,
                    self._normalize_text(document.document_type),
                    self._normalize_text(document.summary_short),
                    self._normalize_text(document.summary),
                    self._normalize_text(document.redacted_text),
                    self._normalize_text(document.extracted_text),
                    self._normalize_text(insights.get("general_summary")),
                    self._normalize_text(insights.get("document_type")),
                    " ".join(self._normalize_string_list(insights.get("legal_risks"), limit=6)),
                    " ".join(self._normalize_string_list(insights.get("key_points"), limit=6)),
                ]
            )
            score, reasons = self._score_document(
                filename=filename,
                evidence_text=evidence_text,
                insights=insights,
                reasoning_terms=reasoning_terms,
            )
            evaluated_rows.append(
                {
                    "filename": filename,
                    "score": score,
                    "reasons": reasons,
                }
            )
            evidence_sources.append(filename)

        ranked_rows = sorted(evaluated_rows, key=lambda row: (row["score"], row["filename"].lower()), reverse=True)
        strongest = [
            {
                "filename": row["filename"],
                "why_it_is_strong": self._build_strong_reason(row["filename"], row["reasons"], objective),
                "material_breach_link": self._build_material_breach_link(row["filename"], row["reasons"]),
            }
            for row in ranked_rows[:4]
            if row["score"] >= 3
        ]

        weakest_rows = sorted(evaluated_rows, key=lambda row: (row["score"], row["filename"].lower()))
        weakest = [
            {
                "filename": row["filename"],
                "why_it_is_weak": self._build_weak_reason(row["filename"], row["reasons"], objective),
            }
            for row in weakest_rows[:4]
            if row["score"] <= 1
        ]

        if strongest:
            strongest_names = ", ".join(item["filename"] for item in strongest[:3])
            strongest_summary = f"The strongest evidence is concentrated in {strongest_names}."
        else:
            strongest_summary = "The record does not yet contain a clearly dominant material-breach exhibit."

        if weakest:
            weakest_names = ", ".join(item["filename"] for item in weakest[:3])
            weakest_summary = f"The weakest evidence is concentrated in {weakest_names}."
        else:
            weakest_summary = "There is no clearly weak exhibit, but some records remain indirect or incomplete."

        return {
            "case_id": case_id,
            "case_title": case_title,
            "objective": self._normalize_text(objective),
            "evidence_summary": f"{strongest_summary} {weakest_summary}".strip(),
            "strongest_evidence": strongest[:4],
            "weakest_evidence": weakest[:4],
            "recommended_follow_up": self._build_follow_up_actions(strongest=strongest, weakest=weakest),
            "evidence_sources": evidence_sources[:10],
            "confidence": "high" if len(strongest) >= 2 else "medium" if strongest else "low",
        }

    def _generate_llm_assessment(self, *, heuristic_payload: dict[str, Any]) -> dict[str, Any] | None:
        prompt = f"""
You are the Evidence Strength Agent inside a legal AI platform.

Rank the supplied case documents by how strongly they support or weaken a material breach theory.
{AgentOutputFormatter.build_quality_guidance(task="rank evidence strength for a material-breach theory", structured_json=True)}

Return valid JSON only with this exact schema:
{{
  "evidence_summary": "string",
  "strongest_evidence": [
    {{
      "filename": "string",
      "why_it_is_strong": "string",
      "material_breach_link": "string"
    }}
  ],
  "weakest_evidence": [
    {{
      "filename": "string",
      "why_it_is_weak": "string"
    }}
  ],
  "recommended_follow_up": ["string"],
  "confidence": "high"
}}

Rules:
- Use only the provided evidence.
- Do not invent facts, dates, contract terms, or breach findings.
- Prefer documents that directly prove contractual duties, breach notices, KPI failure, invoice disputes, payment defaults, or cure-period triggers.
- Treat generic notes, templates, or non-substantive artifacts as weak evidence.
- Keep the answer strict and concise.

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

            strongest = self._normalize_evidence_rows(payload.get("strongest_evidence"), strong=True)
            weakest = self._normalize_evidence_rows(payload.get("weakest_evidence"), strong=False)
            summary = self._normalize_text(payload.get("evidence_summary"))
            actions = self._normalize_string_list(payload.get("recommended_follow_up"), limit=6)
            confidence = self._normalize_text(payload.get("confidence")) or "medium"

            if not summary and not strongest and not weakest:
                return None

            return {
                "evidence_summary": summary or heuristic_payload.get("evidence_summary") or "Evidence ranking completed from available case records.",
                "strongest_evidence": strongest or heuristic_payload.get("strongest_evidence") or [],
                "weakest_evidence": weakest or heuristic_payload.get("weakest_evidence") or [],
                "recommended_follow_up": actions or heuristic_payload.get("recommended_follow_up") or [],
                "confidence": confidence,
            }
        except Exception:
            return None

    def _score_document(
        self,
        *,
        filename: str,
        evidence_text: str,
        insights: dict[str, Any],
        reasoning_terms: set[str],
    ) -> tuple[int, list[str]]:
        lowered = evidence_text.lower()
        score = 0
        reasons: list[str] = []

        if self._looks_like_non_legal_document(filename=filename, text=lowered):
            score -= 4
            reasons.append("looks like a non-legal or test artifact")

        if any(token in lowered for token in self.STRONG_EVIDENCE_KEYWORDS):
            score += 3
            reasons.append("contains direct contract, breach, payment, or performance language")

        if any(token in lowered for token in ["notice", "cure", "termination", "default"]):
            score += 2
            reasons.append("contains notice, cure, termination, or default signals")

        if any(token in lowered for token in ["invoice", "reconciliation", "amount due", "payment due", "late payment"]):
            score += 2
            reasons.append("shows payment or invoice mechanics tied to breach exposure")

        if any(token in lowered for token in ["kpi", "dashboard", "sla", "service level", "performance"]):
            score += 2
            reasons.append("contains operational performance evidence relevant to an SLA breach theory")

        if any(term in lowered for term in reasoning_terms):
            score += 1
            reasons.append("matches the main issues and risk language extracted from the case record")

        if self._has_concrete_metrics(lowered):
            score += 1
            reasons.append("contains concrete metrics, dates, or amounts instead of generic narrative")

        if not self._normalize_text(evidence_text):
            score -= 2
            reasons.append("has little or no extractable text")

        if any(token in lowered for token in self.WEAK_EVIDENCE_KEYWORDS):
            score -= 1
            reasons.append("reads like a generic note rather than primary evidence")

        if len(reasons) > 3:
            reasons = reasons[:3]

        return score, reasons

    @staticmethod
    def _collect_reasoning_terms(reasoning_payload: dict[str, Any]) -> set[str]:
        terms: set[str] = set()
        for key in ("main_issues", "legal_risks", "recommended_next_steps"):
            for value in reasoning_payload.get(key) or []:
                text = str(value or "").lower()
                for token in re.findall(r"[a-z0-9]+", text):
                    if len(token) > 3:
                        terms.add(token)
        return terms

    @staticmethod
    def _build_strong_reason(filename: str, reasons: list[str], objective: str) -> str:
        if reasons:
            return f"{reasons[0].capitalize()}."
        if objective:
            return f"Directly addresses the objective: {objective.strip()}."
        return f"Directly supports the case theory in {filename}."

    @staticmethod
    def _build_material_breach_link(filename: str, reasons: list[str]) -> str:
        if any("contract" in reason for reason in reasons):
            return "It helps prove the contractual baseline that must be breached before material-breach analysis can succeed."
        if any("performance" in reason for reason in reasons):
            return "It helps show performance failure against the agreed service levels or obligations."
        if any("payment" in reason for reason in reasons):
            return "It helps quantify non-payment or disputed charges that may support breach and damages analysis."
        if any("notice" in reason or "cure" in reason for reason in reasons):
            return "It helps show that the breach was formally raised and that cure or escalation rights were triggered."
        return "It is relevant to whether the alleged breach is direct, repeated, and tied to a contractual obligation."

    @staticmethod
    def _build_weak_reason(filename: str, reasons: list[str], objective: str) -> str:
        if reasons:
            return f"{reasons[0].capitalize()}."
        if objective:
            return f"It does not directly answer the objective: {objective.strip()}."
        return f"It is more indirect than the primary evidence in {filename}."

    @staticmethod
    def _build_follow_up_actions(*, strongest: list[dict[str, Any]], weakest: list[dict[str, Any]]) -> list[str]:
        actions: list[str] = []
        if strongest:
            actions.append("Anchor the breach theory on the strongest contractual and performance exhibits.")
        if weakest:
            actions.append("Avoid overclaiming from generic or indirect records until they are tied to a clause or metric.")
        actions.append("Cross-check each strong document against the contract clause, notice trail, and damages amount.")
        return actions[:4]

    @staticmethod
    def _normalize_evidence_rows(values: Any, *, strong: bool) -> list[dict[str, Any]]:
        if not isinstance(values, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            filename = str(item.get("filename") or "").strip()
            if not filename:
                continue
            if strong:
                normalized.append(
                    {
                        "filename": filename,
                        "why_it_is_strong": str(item.get("why_it_is_strong") or "").strip(),
                        "material_breach_link": str(item.get("material_breach_link") or "").strip(),
                    }
                )
            else:
                normalized.append(
                    {
                        "filename": filename,
                        "why_it_is_weak": str(item.get("why_it_is_weak") or "").strip(),
                    }
                )
        return normalized

    @staticmethod
    def _has_concrete_metrics(text: str) -> bool:
        return bool(
            re.search(r"\b\d{1,3}(?:[,. ]\d{3})*(?:\.\d+)?\b", text)
            or re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
            or re.search(r"\b\d{1,3}(?:\.\d+)?%\b", text)
        )

    def _looks_like_non_legal_document(self, *, filename: str, text: str) -> bool:
        lowered = f"{filename} {text}".lower()
        return any(marker in lowered for marker in self.NON_LEGAL_FILENAME_MARKERS)

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

    @classmethod
    def _normalize_string_list(cls, values: Any, *, limit: int) -> list[str]:
        if not isinstance(values, list):
            return []

        normalized: list[str] = []
        for item in values:
            cleaned = cls._normalize_text(item).rstrip(".")
            if not cleaned:
                continue
            if cleaned not in normalized:
                normalized.append(cleaned)
            if len(normalized) >= limit:
                break
        return normalized


evidence_strength_agent = EvidenceStrengthAgent()