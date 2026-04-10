from __future__ import annotations

import json
import re
from typing import Any

from backend.models.document import Document
from backend.services.ai.agents.agent_output_formatter import AgentOutputFormatter
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.llm_gateway import llm_gateway


class EvidenceTraceAgent(BaseAgent):
    agent_name = "evidence_trace_agent"

    STOPWORDS = {
        "the",
        "and",
        "or",
        "for",
        "with",
        "from",
        "that",
        "this",
        "these",
        "those",
        "case",
        "document",
        "claim",
        "claims",
        "evidence",
        "support",
        "supported",
        "show",
        "shows",
        "trace",
        "map",
        "proof",
        "issue",
        "issues",
        "risk",
        "risks",
        "legal",
        "current",
        "posture",
        "what",
        "are",
        "we",
        "missing",
        "need",
        "needed",
        "missing",
        "strong",
        "weak",
        "best",
        "worst",
    }

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    def build_claim_trace(
        self,
        *,
        case_id: int,
        case_title: str,
        documents: list[Document],
        reasoning_payload: dict[str, Any],
        objective: str | None = None,
    ) -> AgentResult:
        if not documents:
            return self.result(
                success=False,
                error="No documents were provided for evidence tracing.",
                trace=["Evidence trace agent skipped because no documents were supplied."],
            )

        heuristic_payload = self._build_heuristic_payload(
            case_id=case_id,
            case_title=case_title,
            documents=documents,
            reasoning_payload=reasoning_payload,
            objective=objective,
        )
        trace = [
            f"Starting evidence trace for case_id={case_id}.",
            f"Mapped {len(heuristic_payload.get('claim_trace', []))} claim(s) against {len(heuristic_payload.get('evidence_sources', []))} source(s).",
            "Built heuristic claim-to-evidence payload.",
        ]

        if self.client:
            llm_payload = self._generate_llm_trace(heuristic_payload=heuristic_payload)
            if llm_payload:
                heuristic_payload.update(llm_payload)
                heuristic_payload["used_llm"] = True
                trace.append("Enhanced evidence trace payload with LLM synthesis.")
            else:
                heuristic_payload["used_llm"] = False
                trace.append("LLM synthesis unavailable; kept heuristic evidence trace payload.")
        else:
            heuristic_payload["used_llm"] = False
            trace.append("No LLM client configured; kept heuristic evidence trace payload.")

        warnings: list[str] = []
        if not heuristic_payload.get("claim_trace"):
            warnings.append("No claim-to-evidence mapping could be extracted from the current case record.")

        return self.result(success=True, payload=heuristic_payload, warnings=warnings, trace=trace)

    def _build_heuristic_payload(
        self,
        *,
        case_id: int,
        case_title: str,
        documents: list[Document],
        reasoning_payload: dict[str, Any],
        objective: str | None,
    ) -> dict[str, Any]:
        document_rows = self._build_document_rows(documents)
        claims = self._collect_claims(reasoning_payload=reasoning_payload, objective=objective)

        claim_trace: list[dict[str, Any]] = []
        unsupported_claims: list[str] = []
        evidence_sources: list[str] = []

        for document_row in document_rows:
            filename = document_row.get("filename") or ""
            if filename and filename not in evidence_sources:
                evidence_sources.append(filename)

        for claim in claims[:8]:
            ranked_documents = self._rank_supporting_documents(claim=claim, document_rows=document_rows)
            if ranked_documents:
                supporting_documents = [row["filename"] for row in ranked_documents[:3]]
                top_score = ranked_documents[0]["score"]
                status = "supported" if top_score >= 3 else "partial"
                note = self._build_support_note(claim=claim, ranked_documents=ranked_documents)
                claim_trace.append(
                    {
                        "claim": claim,
                        "supporting_documents": supporting_documents,
                        "status": status,
                        "note": note,
                    }
                )
            else:
                claim_trace.append(
                    {
                        "claim": claim,
                        "supporting_documents": [],
                        "status": "unsupported",
                        "note": "No direct document support was found yet.",
                    }
                )
                unsupported_claims.append(claim)

        supported_count = sum(1 for item in claim_trace if item.get("status") == "supported")
        partial_count = sum(1 for item in claim_trace if item.get("status") == "partial")
        unsupported_count = sum(1 for item in claim_trace if item.get("status") == "unsupported")

        trace_summary = (
            f"Mapped {supported_count} supported claim(s), {partial_count} partial claim(s), and {unsupported_count} unsupported claim(s) for case {case_id}."
        )
        if objective:
            trace_summary = f"{trace_summary} Objective: {self._normalize_text(objective)}."

        recommended_follow_up = self._build_follow_up_actions(
            claim_trace=claim_trace,
            unsupported_claims=unsupported_claims,
            objective=objective,
        )

        confidence = "high" if supported_count >= 2 else "medium" if supported_count >= 1 else "low"

        return {
            "case_id": case_id,
            "case_title": case_title,
            "objective": self._normalize_text(objective),
            "trace_summary": trace_summary,
            "claim_trace": claim_trace,
            "unsupported_claims": unsupported_claims,
            "recommended_follow_up": recommended_follow_up,
            "evidence_sources": evidence_sources[:10],
            "confidence": confidence,
        }

    def _generate_llm_trace(self, *, heuristic_payload: dict[str, Any]) -> dict[str, Any] | None:
        prompt = f"""
You are the Evidence Trace Agent inside a legal AI platform.

Map each supplied claim to the documents that support it.
{AgentOutputFormatter.build_quality_guidance(task="map legal claims to supporting evidence", structured_json=True)}

Return valid JSON only with this exact schema:
{{
  "trace_summary": "string",
  "claim_trace": [
    {{
      "claim": "string",
      "supporting_documents": ["string"],
            "status": "string",
      "note": "string"
    }}
  ],
  "unsupported_claims": ["string"],
  "recommended_follow_up": ["string"],
  "confidence": "high"
}}

Rules:
- Use only the provided evidence.
- Do not invent support that is not in the record.
- Keep the trace strict, concise, and lawyer-friendly.
- If support is thin, mark the claim as partial or unsupported.

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

            summary = self._normalize_text(payload.get("trace_summary"))
            claim_trace = self._normalize_claim_rows(payload.get("claim_trace"), limit=8)
            unsupported_claims = self._normalize_string_list(payload.get("unsupported_claims"), limit=8)
            recommended_follow_up = self._normalize_string_list(payload.get("recommended_follow_up"), limit=8)
            confidence = self._normalize_text(payload.get("confidence")) or "medium"

            if not summary and not claim_trace:
                return None

            return {
                "trace_summary": summary or heuristic_payload.get("trace_summary") or "Claim trace completed from available case records.",
                "claim_trace": claim_trace or heuristic_payload.get("claim_trace") or [],
                "unsupported_claims": unsupported_claims or heuristic_payload.get("unsupported_claims") or [],
                "recommended_follow_up": recommended_follow_up or heuristic_payload.get("recommended_follow_up") or [],
                "confidence": confidence,
            }
        except Exception:
            return None

    def _build_document_rows(self, documents: list[Document]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for document in documents[:15]:
            insights = self._safe_load_json(document.insights_json)
            filename = self._normalize_text(document.filename) or f"Document #{document.id}"
            document_type = self._normalize_text(insights.get("document_type") or document.document_type)
            summary = self._normalize_text(
                document.summary_short
                or document.summary
                or insights.get("general_summary")
                or (document.redacted_text or document.extracted_text or "")[:260]
            )
            text = " ".join(
                [
                    filename,
                    document_type,
                    summary,
                    self._normalize_text(document.redacted_text),
                    self._normalize_text(document.extracted_text),
                    " ".join(self._normalize_string_list(insights.get("legal_risks"), limit=6)),
                    " ".join(self._normalize_string_list(insights.get("key_points"), limit=6)),
                ]
            )
            role = self._infer_document_role(filename=filename, document_type=document_type, text=text)
            rows.append(
                {
                    "filename": filename,
                    "document_type": document_type or "Case Document",
                    "role": role,
                    "summary": summary,
                    "text": text,
                }
            )
        return rows

    def _collect_claims(self, *, reasoning_payload: dict[str, Any], objective: str | None) -> list[str]:
        claims: list[str] = []
        claims.extend(self._normalize_string_list(reasoning_payload.get("main_issues"), limit=6))
        claims.extend(self._normalize_string_list(reasoning_payload.get("legal_risks"), limit=6))
        if objective:
            claims.insert(0, self._normalize_text(objective))
        if not claims:
            claims.append("What does the current record support and what remains unproven?")
        return self._dedupe_ordered(claims)

    def _rank_supporting_documents(
        self,
        *,
        claim: str,
        document_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        claim_lower = self._normalize_text(claim).lower()
        claim_tokens = {
            token
            for token in re.findall(r"[a-z0-9]+", claim_lower)
            if token not in self.STOPWORDS and len(token) > 2
        }

        ranked: list[dict[str, Any]] = []
        for row in document_rows:
            text = str(row.get("text") or "").lower()
            score = 0
            matched_terms: list[str] = []
            for token in claim_tokens:
                if token in text:
                    score += 1
                    matched_terms.append(token)

            role = str(row.get("role") or "").lower()
            document_type = str(row.get("document_type") or "").lower()
            if any(marker in claim_lower for marker in ["invoice", "payment", "amount", "fees"]) and any(
                marker in (role + " " + document_type + " " + text)
                for marker in ["invoice", "payment", "reconciliation", "amount"]
            ):
                score += 2
            if any(marker in claim_lower for marker in ["kpi", "performance", "service level", "sla"]) and any(
                marker in (role + " " + document_type + " " + text)
                for marker in ["kpi", "performance", "sla", "service level"]
            ):
                score += 2
            if any(marker in claim_lower for marker in ["notice", "cure", "breach", "default"]) and any(
                marker in (role + " " + document_type + " " + text)
                for marker in ["notice", "breach", "cure", "default", "response"]
            ):
                score += 2
            if any(marker in claim_lower for marker in ["settlement", "offer", "proposal", "counteroffer"]) and any(
                marker in (role + " " + document_type + " " + text)
                for marker in ["settlement", "offer", "proposal", "counteroffer"]
            ):
                score += 2

            if score <= 0:
                continue

            ranked.append(
                {
                    "filename": row["filename"],
                    "score": score,
                    "matched_terms": matched_terms[:6],
                    "role": row.get("role") or "case document",
                    "summary": row.get("summary") or "",
                }
            )

        ranked.sort(key=lambda item: (item["score"], item["filename"].lower()), reverse=True)
        return ranked

    @staticmethod
    def _build_support_note(*, claim: str, ranked_documents: list[dict[str, Any]]) -> str:
        top_documents = ", ".join(item["filename"] for item in ranked_documents[:3])
        top_terms: list[str] = []
        for item in ranked_documents[:3]:
            top_terms.extend(item.get("matched_terms") or [])
        top_terms = list(dict.fromkeys(top_terms))[:4]
        if top_terms:
            return f"Matched on {', '.join(top_terms)} across {top_documents}."
        return f"Matched against {top_documents}."

    @staticmethod
    def _build_follow_up_actions(
        *,
        claim_trace: list[dict[str, Any]],
        unsupported_claims: list[str],
        objective: str | None,
    ) -> list[str]:
        actions: list[str] = []
        if unsupported_claims:
            for claim in unsupported_claims[:3]:
                actions.append(f"Request direct proof for: {claim}")
        else:
            actions.append("Use the mapped claims to draft a cited client update or partner brief.")

        supported_docs = []
        for item in claim_trace:
            supported_docs.extend(item.get("supporting_documents") or [])
        if supported_docs:
            unique_docs = list(dict.fromkeys(supported_docs))[:5]
            actions.append(f"Re-read the source documents most tied to the claims: {', '.join(unique_docs)}.")

        if objective:
            actions.append(f"Keep the trace aligned to the user objective: {self._normalize_text(objective)}.")

        return AgentOutputFormatter.normalize_string_list(actions, limit=6)

    @staticmethod
    def _infer_document_role(*, filename: str, document_type: str, text: str) -> str:
        lowered = f"{filename} {document_type} {text}".lower()
        if any(marker in lowered for marker in ["master service agreement", "msa", "service agreement", "contract", "agreement"]):
            return "contract baseline"
        if any(marker in lowered for marker in ["notice of breach", "breach notice", "notice"]):
            return "notice or escalation"
        if any(marker in lowered for marker in ["response", "reply", "counterparty"]):
            return "counterparty response"
        if any(marker in lowered for marker in ["invoice", "reconciliation", "payment"]):
            return "payment evidence"
        if any(marker in lowered for marker in ["kpi", "dashboard", "performance", "sla"]):
            return "performance evidence"
        if any(marker in lowered for marker in ["settlement", "without prejudice", "offer", "proposal"]):
            return "settlement position"
        if any(marker in lowered for marker in ["memo", "note", "internal"]):
            return "internal analysis"
        if any(marker in lowered for marker in ["transcript", "call", "meeting"]):
            return "call or intake context"
        return "case evidence"

    def _normalize_claim_rows(self, values: Any, *, limit: int | None = None) -> list[dict[str, Any]]:
        if not isinstance(values, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            claim = self._normalize_text(item.get("claim"))
            supporting_documents = self._normalize_string_list(item.get("supporting_documents"), limit=4)
            status = self._normalize_text(item.get("status")).lower() or ("supported" if supporting_documents else "unsupported")
            note = self._normalize_text(item.get("note"))
            if not claim:
                continue
            row = {
                "claim": claim,
                "supporting_documents": supporting_documents,
                "status": status,
                "note": note,
            }
            if row not in normalized:
                normalized.append(row)
            if limit is not None and len(normalized) >= limit:
                break
        return normalized

    @staticmethod
    def _normalize_string_list(values: Any, *, limit: int | None = None) -> list[str]:
        if not isinstance(values, list):
            return []

        normalized: list[str] = []
        for item in values:
            cleaned = AgentOutputFormatter.sanitize_text(item).rstrip(".")
            if not cleaned:
                continue
            if cleaned not in normalized:
                normalized.append(cleaned)
            if limit is not None and len(normalized) >= limit:
                break
        return normalized

    @staticmethod
    def _dedupe_ordered(items: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            cleaned = AgentOutputFormatter.sanitize_text(item)
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(cleaned)
        return deduped

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
        return AgentOutputFormatter.extract_json_payload(raw_text)


evidence_trace_agent = EvidenceTraceAgent()