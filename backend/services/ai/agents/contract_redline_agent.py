from __future__ import annotations

import json
from typing import Any

from backend.models.document import Document
from backend.services.ai.agents.agent_output_formatter import AgentOutputFormatter
from backend.services.ai.agents.base_agent import BaseAgent, AgentResult
from backend.services.ai.llm_gateway import llm_gateway


class ContractRedlineAgent(BaseAgent):
    agent_name = "contract_redline_agent"

    CLAUSE_TOPICS: dict[str, dict[str, Any]] = {
        "payment": {
            "keywords": ("payment", "invoice", "fees", "billing", "amount", "consideration"),
            "issue": "Payment terms need a lawyer pass for timing, proof, and any late-payment exposure.",
            "suggestion": "Tighten payment milestones, invoice support, and any late-fee mechanics.",
            "fallback": "If they resist, keep the payment structure but narrow the dispute window and evidence burden.",
        },
        "liability": {
            "keywords": ("liability", "indemnity", "damages", "losses", "cap", "limitation of liability"),
            "issue": "Liability allocation should be checked for caps, carve-outs, and mutuality.",
            "suggestion": "Align the cap, carve-outs, and indemnity language with the risk appetite.",
            "fallback": "If they resist, preserve a cap but carve out fraud, wilful misconduct, and payment obligations.",
        },
        "termination": {
            "keywords": ("termination", "terminate", "cure period", "notice period", "renewal", "expiration"),
            "issue": "Termination and cure timing can change leverage and should be made explicit.",
            "suggestion": "Clarify termination triggers, cure windows, and any auto-renewal language.",
            "fallback": "If they resist, keep the trigger but extend cure rights and written notice obligations.",
        },
        "sla": {
            "keywords": ("sla", "service level", "kpi", "uptime", "service credit", "performance"),
            "issue": "Service-level language should be tied to measurable outcomes and remedies.",
            "suggestion": "Define the KPI or service-level test and link it to service credits or remedies.",
            "fallback": "If they resist, keep the metric but narrow the remedy and measurement ambiguity.",
        },
        "confidentiality": {
            "keywords": ("confidential", "confidentiality", "nondisclosure", "non-disclosure", "nda"),
            "issue": "Confidentiality scope should be checked for exceptions, duration, and disclosure rights.",
            "suggestion": "Clarify permitted disclosures, duration, and confidentiality survival language.",
            "fallback": "If they resist, preserve the clause but narrow the exceptions and add a disclosure protocol.",
        },
        "governing law": {
            "keywords": ("governing law", "jurisdiction", "venue", "forum"),
            "issue": "Governing law and forum choices affect enforcement and litigation leverage.",
            "suggestion": "Confirm the governing law, venue, and forum selection against the matter strategy.",
            "fallback": "If they resist, keep the chosen law but narrow the forum fight and preserve rights.",
        },
        "assignment": {
            "keywords": ("assignment", "transfer", "novate", "subcontract"),
            "issue": "Assignment and transfer terms should be checked for hidden consent rights.",
            "suggestion": "Add consent controls for assignment, transfer, or subcontracting.",
            "fallback": "If they resist, keep the clause but require notice and reasonableness for consent.",
        },
        "warranty": {
            "keywords": ("warranty", "representation", "represent", "warrants"),
            "issue": "Warranty and representation wording may overreach if not bounded.",
            "suggestion": "Narrow the warranty scope and align any representations with actual knowledge.",
            "fallback": "If they resist, preserve the statement but qualify it by knowledge and materiality.",
        },
    }

    def __init__(self) -> None:
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model

    def draft_redline(
        self,
        *,
        case_id: int,
        case_title: str,
        documents: list[Document],
        objective: str | None = None,
        focus_document_name: str | None = None,
    ) -> AgentResult:
        if not documents:
            return self.result(
                success=False,
                error="No documents were provided for contract redlining.",
                trace=["Contract redline agent skipped because no documents were supplied."],
            )

        heuristic_payload = self._build_heuristic_payload(
            case_id=case_id,
            case_title=case_title,
            documents=documents,
            objective=objective,
            focus_document_name=focus_document_name,
        )
        trace = [
            f"Starting contract redline drafting for case_id={case_id}.",
            f"Reviewed {len(heuristic_payload.get('clause_rows', []))} clause signal(s).",
            "Built heuristic contract-redline payload.",
        ]

        if self.client:
            llm_payload = self._generate_llm_redline(heuristic_payload=heuristic_payload)
            if llm_payload:
                heuristic_payload.update(llm_payload)
                heuristic_payload["used_llm"] = True
                trace.append("Enhanced contract redline payload with LLM synthesis.")
            else:
                heuristic_payload["used_llm"] = False
                trace.append("LLM synthesis unavailable; kept heuristic contract redline payload.")
        else:
            heuristic_payload["used_llm"] = False
            trace.append("No LLM client configured; kept heuristic contract redline payload.")

        warnings: list[str] = []
        if not heuristic_payload.get("clause_rows"):
            warnings.append("No clause-level signals were extracted from the current contract pack.")

        return self.result(success=True, payload=heuristic_payload, warnings=warnings, trace=trace)

    def _build_heuristic_payload(
        self,
        *,
        case_id: int,
        case_title: str,
        documents: list[Document],
        objective: str | None,
        focus_document_name: str | None,
    ) -> dict[str, Any]:
        document_rows = self._build_document_rows(documents)
        clause_rows = self._build_clause_rows(document_rows=document_rows, focus_document_name=focus_document_name)
        target_document = self._choose_target_document(document_rows=document_rows, focus_document_name=focus_document_name)
        evidence_sources = [row["filename"] for row in document_rows if row.get("filename")]

        redline_summary = (
            f"Case #{case_id} redline brief for {case_title}: {len(clause_rows)} clause signal(s) identified across {len(document_rows)} document(s)."
        )
        if objective:
            redline_summary += f" Focus: {self._normalize_text(objective)}."

        priority_changes = [row["suggestion"] for row in clause_rows[:5]]
        risk_notes = [row["issue"] for row in clause_rows[:5]]
        confidence = "high" if len(clause_rows) >= 4 else "medium" if clause_rows else "low"

        return {
            "case_id": case_id,
            "case_title": case_title,
            "objective": self._normalize_text(objective),
            "focus_document_name": self._normalize_text(focus_document_name),
            "target_document": target_document,
            "redline_summary": redline_summary,
            "clause_rows": clause_rows[:10],
            "priority_changes": priority_changes[:8],
            "risk_notes": risk_notes[:8],
            "fallback_positions": [row["fallback_position"] for row in clause_rows[:5]],
            "evidence_sources": evidence_sources[:10],
            "confidence": confidence,
        }

    def _generate_llm_redline(self, *, heuristic_payload: dict[str, Any]) -> dict[str, Any] | None:
        prompt = f"""
You are the Contract Redline Agent inside a legal AI platform.

Draft clause-level redline guidance for the supplied contract record.
{AgentOutputFormatter.build_quality_guidance(task="draft a practical contract redline plan", structured_json=True)}

Return valid JSON only with this exact schema:
{{
  "redline_summary": "string",
  "target_document": "string",
  "clause_rows": [
    {{
      "clause": "string",
      "issue": "string",
      "suggestion": "string",
      "fallback_position": "string",
      "source_documents": ["string"]
    }}
  ],
  "priority_changes": ["string"],
  "risk_notes": ["string"],
  "confidence": "high"
}}

Rules:
- Use only the provided evidence.
- Do not invent clause language or hidden terms.
- Keep the guidance practical for a lawyer preparing a markup or negotiation pass.

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

            summary = self._normalize_text(payload.get("redline_summary"))
            target_document = self._normalize_text(payload.get("target_document"))
            clause_rows = self._normalize_clause_rows(payload.get("clause_rows"), limit=10)
            priority_changes = self._normalize_string_list(payload.get("priority_changes"), limit=8)
            risk_notes = self._normalize_string_list(payload.get("risk_notes"), limit=8)
            confidence = self._normalize_text(payload.get("confidence")) or "medium"

            if not summary and not clause_rows:
                return None

            return {
                "redline_summary": summary or heuristic_payload.get("redline_summary") or "Contract redline guidance completed from available case records.",
                "target_document": target_document or heuristic_payload.get("target_document") or "",
                "clause_rows": clause_rows or heuristic_payload.get("clause_rows") or [],
                "priority_changes": priority_changes or heuristic_payload.get("priority_changes") or [],
                "risk_notes": risk_notes or heuristic_payload.get("risk_notes") or [],
                "confidence": confidence,
            }
        except Exception:
            return None

    def _build_document_rows(self, documents: list[Document]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for document in documents[:12]:
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
            rows.append(
                {
                    "filename": filename,
                    "document_type": document_type or "Case Document",
                    "summary": summary,
                    "text": text,
                }
            )
        return rows

    def _build_clause_rows(
        self,
        *,
        document_rows: list[dict[str, Any]],
        focus_document_name: str | None,
    ) -> list[dict[str, Any]]:
        clause_rows: list[dict[str, Any]] = []
        focus_lower = self._normalize_text(focus_document_name).lower()

        for clause_name, definition in self.CLAUSE_TOPICS.items():
            matched_documents: list[str] = []
            matched_texts: list[str] = []
            for row in document_rows:
                text = str(row.get("text") or "").lower()
                if any(keyword in text for keyword in definition["keywords"]):
                    filename = str(row.get("filename") or "").strip()
                    if filename and filename not in matched_documents:
                        matched_documents.append(filename)
                    matched_texts.append(text)

            if not matched_documents:
                continue

            issue = str(definition["issue"])
            suggestion = str(definition["suggestion"])
            fallback_position = str(definition["fallback"])
            if focus_lower and not any(focus_lower in doc.lower() for doc in matched_documents):
                issue = f"{issue} The selected document does not appear to be the main source, so confirm the target file first."

            clause_rows.append(
                {
                    "clause": clause_name.replace("_", " ").title(),
                    "issue": issue,
                    "suggestion": suggestion,
                    "fallback_position": fallback_position,
                    "source_documents": matched_documents[:4],
                }
            )

        clause_rows.sort(key=lambda row: self._clause_priority(row["clause"]))
        return clause_rows

    def _choose_target_document(
        self,
        *,
        document_rows: list[dict[str, Any]],
        focus_document_name: str | None,
    ) -> str:
        if focus_document_name:
            return self._normalize_text(focus_document_name)

        for row in document_rows:
            filename = self._normalize_text(row.get("filename"))
            lowered = filename.lower()
            if any(marker in lowered for marker in ["master service agreement", "msa", "agreement", "contract", "terms", "redline"]):
                return filename

        return self._normalize_text(document_rows[0].get("filename") if document_rows else "")

    @staticmethod
    def _clause_priority(clause_name: str) -> int:
        priority_order = [
            "Liability",
            "Payment",
            "Termination",
            "Sla",
            "Governing Law",
            "Confidentiality",
            "Warranty",
            "Assignment",
        ]
        try:
            return priority_order.index(clause_name)
        except ValueError:
            return len(priority_order)

    @staticmethod
    def _normalize_clause_rows(values: Any, *, limit: int | None = None) -> list[dict[str, Any]]:
        if not isinstance(values, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            clause = AgentOutputFormatter.sanitize_text(item.get("clause"))
            issue = AgentOutputFormatter.sanitize_text(item.get("issue"))
            suggestion = AgentOutputFormatter.sanitize_text(item.get("suggestion"))
            fallback_position = AgentOutputFormatter.sanitize_text(item.get("fallback_position"))
            source_documents = AgentOutputFormatter.normalize_string_list(item.get("source_documents"), limit=4)
            if not clause:
                continue
            row = {
                "clause": clause,
                "issue": issue,
                "suggestion": suggestion,
                "fallback_position": fallback_position,
                "source_documents": source_documents,
            }
            if row not in normalized:
                normalized.append(row)
            if limit is not None and len(normalized) >= limit:
                break
        return normalized

    @staticmethod
    def _normalize_string_list(values: Any, *, limit: int | None = None) -> list[str]:
        return AgentOutputFormatter.normalize_string_list(values, limit=limit)

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
    def _normalize_text(value: Any) -> str:
        return AgentOutputFormatter.normalize_text(value)

    @staticmethod
    def _extract_json_payload(raw_text: str) -> dict[str, Any] | None:
        return AgentOutputFormatter.extract_json_payload(raw_text)


contract_redline_agent = ContractRedlineAgent()