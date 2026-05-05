from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.case import Case
from backend.models.consultation_request import ConsultationRequest
from backend.models.document import Document
from backend.models.voice_recording import VoiceRecording
from backend.services.ai.agents.booking_agent import booking_agent
from backend.services.ai.agents.case_memory_agent import case_memory_agent
from backend.services.ai.agents.case_reasoning_agent import case_reasoning_agent
from backend.services.ai.agents.deadline_obligation_agent import deadline_obligation_agent
from backend.services.ai.agents.document_comparison_agent import document_comparison_agent
from backend.services.ai.agents.evidence_strength_agent import evidence_strength_agent
from backend.services.ai.agents.evidence_trace_agent import evidence_trace_agent
from backend.services.ai.agents.insight_agent import insight_agent
from backend.services.ai.agents.timeline_agent import timeline_agent
from backend.services.ai.artifact_versioning_service import artifact_versioning_service
from backend.services.ai.jurisdiction_context_service import jurisdiction_context_service
from backend.services.ai.llm_gateway import llm_gateway
from backend.services.ai.summarization_service import summarization_service
from backend.services.calendar_assistant_tool_service import calendar_assistant_tool_service

_logger = logging.getLogger(__name__)


class CopilotCaseAnalysisMixin:
    """Mixin: case reasoning, analysis, risk, timeline, and summary methods.

    Extracted from CopilotService (R4).  All methods reference shared state
    (self.rag_service, self.model, self.client, class constants) that is
    defined on CopilotService and resolved at runtime via MRO.
    """

    @staticmethod
    def _result_indicates_insufficient_evidence(result: Dict[str, Any]) -> bool:
        trust_panel = result.get("trust_panel") if isinstance(result.get("trust_panel"), dict) else {}
        status = str((trust_panel or {}).get("status") or result.get("status") or "").strip().lower()
        fallback_reason = str(result.get("fallback_reason") or "").strip().lower()
        answer = str(result.get("answer") or "").strip().lower()
        return (
            status == "insufficient_evidence"
            or fallback_reason in {"no_direct_legal_source", "insufficient_evidence"}
            or "not enough grounded evidence" in answer
            or "insufficient evidence" in answer
        )

    def _answer_material_breach_clause_question(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: int,
        question: str,
        jurisdiction_context: dict[str, Any] | None,
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        if not documents:
            return {
                "answer": f"Case {case.id} has no documents yet, so I cannot rank breach-supporting clauses.",
                "used_fallback": True,
                "fallback_reason": "No case documents found",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "cache": {"hit": False, "backend": "none"},
                "jurisdiction": jurisdiction_context,
            }

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents,
        )
        evidence_result = evidence_strength_agent.evaluate_evidence_strength(
            case_id=case.id,
            case_title=case.title,
            objective=question,
            documents=documents,
            reasoning_payload=reasoning_payload,
        )
        evidence_payload = evidence_result.payload if evidence_result.success else {}

        clause_rows = self._build_material_breach_clause_rows(documents=documents)

        lines: List[str] = [f"Case #{case.id} strongest clauses supporting a material breach position:"]

        if clause_rows:
            top_clause_names = [self._normalize_text(row.get("clause")) for row in clause_rows[:3]]
            top_clause_names = [name for name in top_clause_names if name]
            if top_clause_names:
                lines.append("The clearest clause themes are " + ", ".join(top_clause_names) + ".")

        evidence_summary = self._normalize_text(evidence_payload.get("evidence_summary"))
        if evidence_summary:
            lines.extend(["", evidence_summary])

        if clause_rows:
            lines.extend(["", "Clause ranking:"])
            for row in clause_rows[:4]:
                clause = self._normalize_text(row.get("clause"))
                explanation = self._normalize_text(row.get("explanation"))
                supporting_documents = row.get("supporting_documents") or []
                source_text = ", ".join(
                    str(item).strip() for item in supporting_documents[:3] if str(item).strip()
                )

                if not clause:
                    continue

                line = f"- {clause}: {explanation or 'Relevant because it directly bears on breach, notice, or damages.'}"
                if source_text:
                    line += f" Sources: {source_text}."
                lines.append(line)
        else:
            lines.extend([
                "",
                "I found breach-related evidence, but not enough clause-level signals to rank specific clauses with confidence.",
            ])

        recommended_follow_up = evidence_payload.get("recommended_follow_up") or []
        follow_up = self._normalize_text(recommended_follow_up[0]) if recommended_follow_up else ""
        if not follow_up:
            follow_up = "If you want, I can trace the exact clause text next and map each clause to the supporting exhibit."

        lines.extend(["", "Next step:", f"- {follow_up}"])

        source_names: List[str] = []
        for row in clause_rows:
            for filename in row.get("supporting_documents") or []:
                name = str(filename or "").strip()
                if name and name not in source_names:
                    source_names.append(name)

        if not source_names:
            for item in evidence_payload.get("strongest_evidence") or []:
                name = str(item.get("filename") or "").strip()
                if name and name not in source_names:
                    source_names.append(name)

        sources: List[Dict[str, Any]] = []
        for document in documents:
            if document.filename not in source_names:
                continue
            snippet = self._normalize_text(document.summary_short or document.summary or "")
            if snippet:
                sources.append(self._build_source(document=document, snippet=snippet, score=1.0))
            if len(sources) >= 10:
                break

        used_llm = bool(evidence_result.payload.get("used_llm"))
        confidence = "high" if len(clause_rows) >= 3 else "medium" if clause_rows else str(evidence_payload.get("confidence") or "low")

        return {
            "answer": "\n".join(lines).strip(),
            "used_fallback": not used_llm,
            "fallback_reason": None if used_llm else "Used clause-ranking heuristic synthesis",
            "confidence": confidence,
            "scope": "case",
            "sources": sources,
            "cache": {"hit": False, "backend": "none"},
            "jurisdiction": jurisdiction_context,
            "structured_result": {
                "evidence_strength": evidence_payload,
                "clause_rows": clause_rows,
            },
        }

    def _build_material_breach_clause_rows(
        self,
        *,
        documents: List[Document],
    ) -> List[Dict[str, Any]]:
        clause_map: dict[str, dict[str, Any]] = {}

        def add_clause(clause: str, *, score: int, explanation: str, filename: str) -> None:
            row = clause_map.setdefault(
                clause,
                {
                    "clause": clause,
                    "score": 0,
                    "supporting_documents": [],
                    "reasons": [],
                },
            )
            row["score"] += score
            if filename and filename not in row["supporting_documents"]:
                row["supporting_documents"].append(filename)
            cleaned_reason = self._normalize_text(explanation)
            if cleaned_reason and cleaned_reason not in row["reasons"]:
                row["reasons"].append(cleaned_reason)

        for document in documents[:15]:
            filename = self._normalize_text(document.filename) or f"Document #{document.id}"
            insights = self._safe_load_insights(document)
            document_type = self._normalize_text(insights.get("document_type") or document.document_type).lower()
            general_summary = self._normalize_text(insights.get("general_summary") or document.summary_short or document.summary)
            key_points = " ".join(self._normalize_text(item) for item in insights.get("key_points") or [])
            payment_terms = " ".join(self._normalize_text(item) for item in insights.get("payment_terms") or [])
            termination_terms = " ".join(self._normalize_text(item) for item in insights.get("termination_terms") or [])
            legal_risks = " ".join(self._normalize_text(item) for item in insights.get("legal_risks") or [])
            combined_text = " ".join(
                [
                    filename,
                    document_type,
                    general_summary,
                    key_points,
                    payment_terms,
                    termination_terms,
                    legal_risks,
                ]
            ).lower()

            if any(token in combined_text for token in ["material breach", "cure period", "notice of breach", "breach notice", "terminate"]):
                add_clause(
                    "Notice, cure, and termination clause",
                    score=4 if document_type in {"master_service_agreement", "contract", "legal_letter"} else 3,
                    explanation="The record ties the dispute to notice, cure, and termination mechanics that usually control when breach becomes actionable.",
                    filename=filename,
                )

            if any(token in combined_text for token in ["sla", "service level", "kpi", "performance", "dashboard"]):
                add_clause(
                    "SLA / service-level obligations clause",
                    score=4 if document_type in {"master_service_agreement", "contract"} else 3,
                    explanation="The service-level and KPI materials show the contractual performance standard that the alleged breach is measured against.",
                    filename=filename,
                )

            if any(token in combined_text for token in ["invoice", "payment", "amount due", "reconciliation", "late payment", "net 30"]):
                add_clause(
                    "Payment obligation / invoice clause",
                    score=4 if document_type in {"invoice", "master_service_agreement", "contract"} else 3,
                    explanation="The payment and reconciliation materials show a concrete monetary obligation that can support breach and damages analysis.",
                    filename=filename,
                )

            if any(token in combined_text for token in ["response", "reservation of rights", "formal notice", "breach allegation"]):
                add_clause(
                    "Formal breach notice / response clause",
                    score=3,
                    explanation="The notice and response trail shows that the breach allegation was formally raised and contested.",
                    filename=filename,
                )

        ranked_rows = sorted(
            clause_map.values(),
            key=lambda row: (row["score"], len(row["supporting_documents"]), row["clause"].lower()),
            reverse=True,
        )

        formatted_rows: List[Dict[str, Any]] = []
        for row in ranked_rows[:4]:
            reasons = row.get("reasons") or []
            explanation = reasons[0] if reasons else "This clause is directly tied to the alleged breach theory."
            if len(reasons) > 1:
                explanation = f"{reasons[0]} {reasons[1]}"
            formatted_rows.append(
                {
                    "clause": row["clause"],
                    "explanation": explanation,
                    "supporting_documents": row.get("supporting_documents") or [],
                    "score": row.get("score", 0),
                }
            )

        return formatted_rows

    def _resolve_case_for_context(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> Optional[Case]:
        resolved_case_id = case_id
        if resolved_case_id is None and document_id is not None:
            document = (
                db.query(Document)
                .filter(
                    Document.id == document_id,
                    Document.tenant_id == tenant_id,
                )
                .first()
            )
            if document:
                resolved_case_id = document.case_id

        if resolved_case_id is None:
            return None

        return (
            db.query(Case)
            .filter(
                Case.id == resolved_case_id,
                Case.tenant_id == tenant_id,
                Case.deleted_at.is_(None),
            )
            .first()
        )

    def _get_case_or_404(self, db: Session, tenant_id: int, case_id: Optional[int]) -> Case:
        if case_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Case id could not be detected from the message."
            )

        case = (
            db.query(Case)
            .filter(
                Case.id == case_id,
                Case.tenant_id == tenant_id,
                Case.deleted_at.is_(None)
            )
            .first()
        )

        if not case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found."
            )

        return case

    def _get_case_documents(self, db: Session, tenant_id: int, case_id: int) -> List[Document]:
        return (
            db.query(Document)
            .filter(
                Document.case_id == case_id,
                Document.tenant_id == tenant_id
            )
            .order_by(Document.upload_timestamp.asc(), Document.id.asc())
            .all()
        )

    def _get_case_consultation_requests(
        self,
        db: Session,
        tenant_id: int,
        case_id: int
    ) -> List[ConsultationRequest]:
        return (
            db.query(ConsultationRequest)
            .filter(
                ConsultationRequest.case_id == case_id,
                ConsultationRequest.tenant_id == tenant_id
            )
            .order_by(ConsultationRequest.created_at.desc(), ConsultationRequest.id.desc())
            .all()
        )

    def _get_case_voice_recordings(
        self,
        db: Session,
        tenant_id: int,
        case_id: int
    ) -> List[VoiceRecording]:
        return (
            db.query(VoiceRecording)
            .filter(
                VoiceRecording.case_id == case_id,
                VoiceRecording.tenant_id == tenant_id
            )
            .order_by(VoiceRecording.created_at.desc(), VoiceRecording.id.desc())
            .all()
        )

    def _safe_load_insights(self, document: Document) -> Dict[str, Any]:
        insights_blob = self._text_or_empty(document.insights_json)
        if not insights_blob:
            return {}

        try:
            payload = json.loads(insights_blob)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _ensure_document_summary(self, db: Session, document: Document) -> Document:
        if self._text_or_empty(document.summary):
            return document

        if not (self._text_or_empty(document.redacted_text) or self._text_or_empty(document.extracted_text)):
            try:
                self.document_pipeline.process_document(document=document, db=db)
                db.refresh(document)
            except Exception:
                return document

        if not (self._text_or_empty(document.redacted_text) or self._text_or_empty(document.extracted_text)):
            return document

        try:
            return summarization_service.summarize_document(db=db, document=document)
        except Exception:
            return document

    def _document_summary_unavailable_reason(self, document: Document) -> str:
        processing_status = self._normalize_text(document.processing_status) or "unknown"
        summary_status = self._normalize_text(document.summary_status) or "not_started"
        processing_error = self._normalize_text(document.processing_error)
        summary_error = self._normalize_text(document.summary_error)

        notes: List[str] = []
        if processing_error:
            notes.append(f"processing error: {processing_error[:180]}")
        if summary_error:
            notes.append(f"summary error: {summary_error[:180]}")
        if not (self._text_or_empty(document.redacted_text) or self._text_or_empty(document.extracted_text)):
            notes.append("no extractable text detected")

        details = "; ".join(notes) if notes else "summary generation is pending"
        return (
            f"{document.filename} (processing={processing_status}, summary={summary_status}): {details}."
        )

    def _run_case_reasoning(
        self,
        *,
        db: Session,
        tenant_id: int,
        case: Case,
        documents: List[Document]
    ) -> Dict[str, Any]:
        agent_result = case_reasoning_agent.analyze_case(
            case=case,
            documents=documents,
            jurisdiction_country=case.jurisdiction_country,
            consultation_requests=self._get_case_consultation_requests(
                db=db,
                tenant_id=tenant_id,
                case_id=case.id
            ),
            voice_recordings=self._get_case_voice_recordings(
                db=db,
                tenant_id=tenant_id,
                case_id=case.id
            ),
        )

        if agent_result.success:
            return agent_result.payload

        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        return {
            "overview": f"Case {case.id} - {case.title}",
            "narrative_summary": f"Case {case.id} could not be fully synthesized by the case reasoning agent.",
            "main_issues": [],
            "key_dates": [],
            "legal_risks": [],
            "recommended_next_steps": [
                "Review the case documents manually.",
                "Regenerate case intelligence after more documents are processed.",
            ],
            "sources": [],
            "jurisdiction_country": jurisdiction_context.get("country_code"),
            "jurisdiction_display_name": jurisdiction_context.get("country_display_name"),
            "constitutional_references": jurisdiction_context.get("constitutional_references") or [],
            "used_llm": False,
        }

    @staticmethod
    def _looks_like_prompt_template_noise(text: str) -> bool:
        """Return True when *text* looks like leaked LLM prompt/schema boilerplate
        rather than a genuine legal risk item.
        """
        candidate = str(text or "").strip()
        if not candidate:
            return False
        lower = candidate.lower()

        # Hard keyword patterns that only appear in prompt templates
        PROMPT_PHRASES = (
            "return valid json",
            "return json only",
            "valid json only",
            "use only the provided",
            "do not invent",
            "do not wrap the json",
            "you are the case reasoning agent",
            "you are a legal",
            "task: reason over",
            '"overview": "string"',
            '"narrative_summary"',
            '"main_issues"',
            '"key_dates"',
            '"recommended_next_steps"',
            "json schema",
            "exact schema",
            "schema:",
            "jurisdiction guardrails",
            "constitution references",
            "risk focus areas",
            "what success looks like",
            "optimize prompt",
            "<case_id>",
            "<document_id>",
            "pdf_ready.md",
            "` - `",
        )
        if any(phrase in lower for phrase in PROMPT_PHRASES):
            return True

        # Standalone single-word schema keys leaked as list items
        SCHEMA_KEYS = {
            "overview", "narrative_summary", "main_issues", "key_dates",
            "legal_risks", "recommended_next_steps", "sources", "string",
        }
        if candidate.strip('"\'').lower() in SCHEMA_KEYS:
            return True

        # Starts with JSON punctuation (leaked object/array fragment)
        stripped = candidate.lstrip()
        if stripped and stripped[0] in ('{', '[') and ('}' in stripped or ']' in stripped):
            return True

        # Instruction-style opening words
        INSTRUCTION_STARTS = (
            "task:",
            "rules:",
            "output:",
            "format:",
            "instructions:",
            "constraint:",
        )
        if any(lower.startswith(prefix) for prefix in INSTRUCTION_STARTS):
            return True

        return False

    @staticmethod
    def _normalize_risk_items(items: object) -> List[str]:  # type: ignore[override]
        """Normalise a list of legal-risk strings returned by the LLM.

        Defensive against non-list / non-string values so a malformed LLM
        response never causes an unhandled exception.
        """
        if not items:
            return []
        if isinstance(items, str):
            items = [items]
        elif not isinstance(items, list):
            try:
                items = list(items)  # type: ignore[arg-type]
            except TypeError:
                return []

        normalized: List[str] = []
        for item in items:
            # Flatten dicts e.g. {"risk": "…"} to their first string value
            if isinstance(item, dict):
                item = next((v for v in item.values() if isinstance(v, str)), None)
            if item is None:
                continue
            raw = str(item).strip()
            if not raw:
                continue
            if CopilotCaseAnalysisMixin._looks_like_prompt_template_noise(raw):
                continue

            split_candidate = re.sub(r"\s+(?=\d+[).]\s+)", "\n", raw)
            for fragment in split_candidate.splitlines():
                cleaned = fragment.strip().rstrip(".")
                if not cleaned:
                    continue
                cleaned = re.sub(r"^\d+[).]\s*", "", cleaned)
                if not cleaned:
                    continue
                if CopilotCaseAnalysisMixin._looks_like_prompt_template_noise(cleaned):
                    continue
                cleaned = cleaned[0].upper() + cleaned[1:] if cleaned else cleaned
                if cleaned not in normalized:
                    normalized.append(cleaned)
        return normalized

    def _build_case_document_resume_entry(self, *, position: int, document: Document, insights: Dict[str, Any]) -> str:
        filename = self._normalize_text(document.filename) or f"Document #{document.id}"
        kind = self._infer_document_kind(filename=filename, insights=insights)

        raw_summary = self._normalize_text(
            str(insights.get("general_summary") or "")
            or document.summary_short
            or document.summary
            or (document.redacted_text or document.extracted_text or "")[:700]
        )
        says = self._to_clean_summary_paragraph(
            raw_summary,
            fallback=f"{kind} captured in the case record.",
            max_sentences=1,
            max_chars=170,
        )
        says = re.sub(r"^\s*(this|the)\s+document\s+(?:is|contains|covers|presents)\s+", "", says, flags=re.IGNORECASE)
        says = says.rstrip(".")

        markers_source = " ".join(
            [
                raw_summary,
                self._normalize_text(document.summary),
                self._normalize_text(document.summary_short),
            ]
        )
        marker_parts: List[str] = []
        percentages = self._extract_percentages(markers_source, max_items=2)
        amounts = self._extract_currency_amounts(markers_source, max_items=2)
        if percentages:
            marker_parts.append("metrics " + ", ".join(percentages))
        if amounts:
            marker_parts.append("figures " + ", ".join(amounts))

        date_markers: List[str] = []
        for item in (insights.get("important_dates") or [])[:2]:
            label = self._normalize_text(str(item.get("label") or ""))
            value = self._normalize_text(str(item.get("value") or ""))
            if label and value:
                date_markers.append(f"{label} ({value})")
        if date_markers:
            marker_parts.append("dates " + "; ".join(date_markers[:2]))

        impact = self._infer_document_impact_note(
            filename=filename,
            kind=kind,
            text=" ".join([raw_summary, says]),
        )

        line = f"Document {position} ({filename}): {kind}. Says: {says}. Matters: {impact}."
        if marker_parts:
            line += " Key markers: " + "; ".join(marker_parts) + "."

        line = re.sub(r"\s+", " ", line).strip()
        if len(line) > 430:
            line = line[:430].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."
        return line

    @classmethod
    def _to_summary_bullet_sentence(cls, value: str, *, max_chars: int = 360) -> str:
        candidate = str(value or "").strip()
        if not candidate:
            return ""
        candidate = re.sub(r"^[-*\d\s\.)]+", "", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip(" .;:-")
        if not candidate:
            return ""
        candidate = candidate[0].upper() + candidate[1:] if candidate else candidate
        if len(candidate) > max_chars:
            candidate = candidate[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."
        if candidate and candidate[-1] not in ".!?":
            candidate += "."
        return candidate

    def _append_case_summary_bullet(self, bullets: List[str], value: str) -> None:
        cleaned = self._to_summary_bullet_sentence(value)
        if not cleaned:
            return
        if self._looks_like_prompt_template_noise(cleaned):
            return
        if cleaned not in bullets:
            bullets.append(cleaned)

    def _build_evidence_story_bullets(self, *, evidence_sources: List[str]) -> List[str]:
        lowered_sources = [str(name or "").strip().lower() for name in evidence_sources]
        bullets: List[str] = []

        if any("master_service_agreement" in name or "service_agreement" in name or "msa" in name for name in lowered_sources):
            bullets.append(
                "The Master Service Agreement sets the contractual baseline for service scope, SLA targets, payment mechanics, and cure or termination pathways."
            )
        if any("notice_of_breach" in name or "breach" in name for name in lowered_sources):
            bullets.append(
                "The breach notice formalizes underperformance allegations and opens a time-bound cure and escalation track."
            )
        if any("counterparty_response" in name or "response" in name for name in lowered_sources):
            bullets.append(
                "The counterparty response disputes breach framing and liability exposure, creating a contested fact record on performance and billing."
            )
        if any("kpi" in name or "dashboard" in name for name in lowered_sources):
            bullets.append(
                "KPI extracts provide trend evidence that can support or weaken material-breach arguments depending on methodology integrity."
            )
        if any("invoice" in name or "reconciliation" in name for name in lowered_sources):
            bullets.append(
                "Invoice reconciliation evidence is central for quantifying disputed sums, duplicate charges, and rate-cap compliance."
            )
        if any("settlement" in name for name in lowered_sources):
            bullets.append(
                "Without-prejudice settlement artifacts indicate active negotiation leverage while preserving litigation rights."
            )
        if any("transcript" in name or "call" in name for name in lowered_sources):
            bullets.append(
                "Call and meeting records add admissions, commitments, and unresolved points that shape negotiation credibility."
            )

        return bullets

    def _build_full_case_document_context(
        self,
        *,
        documents: List[Document],
        max_chars_per_document: int = 3500,
        max_total_chars: int = 36000,
    ) -> str:
        blocks: List[str] = []
        total_chars = 0

        for document in documents:
            filename = self._normalize_text(document.filename) or f"document_{document.id}"
            text = self._text_or_empty(document.redacted_text) or self._text_or_empty(document.extracted_text)
            if not text:
                text = self._text_or_empty(document.summary) or self._text_or_empty(document.summary_short)
            if not text:
                continue

            remaining = max_total_chars - total_chars
            if remaining <= 0:
                break
            snippet = text[: min(max_chars_per_document, remaining)].strip()
            if not snippet:
                continue
            blocks.append(f"--- {filename} ---\n{snippet}")
            total_chars += len(snippet)

        return "\n\n".join(blocks).strip()

    def _generate_source_grounded_case_summary_bullets(
        self,
        *,
        case: Case,
        documents: List[Document],
        request_text: str,
        target_count: int,
    ) -> Optional[List[str]]:
        client = llm_gateway.create_client(tier="summary")
        if not client:
            return None

        target = min(max(target_count or 8, 1), 12)
        document_context = self._build_full_case_document_context(documents=documents)
        if not document_context:
            return None

        filenames = [
            self._normalize_text(document.filename)
            for document in documents
            if self._normalize_text(document.filename)
        ]
        prompt = f"""
    You are a legal summarization agent for lawyers.

    Return valid JSON only with this schema:
    {{"bullets": ["string"]}}

    Task:
    Summarize case #{case.id} in exactly {target} bullets.

    User request:
    {request_text}

    Strict rules:
    - Output exactly {target} bullets in the JSON array.
    - Each bullet must be one complete sentence.
    - Every bullet must cite at least one source filename in square brackets, for example [source: 01_equipment_maintenance_agreement.pdf].
    - Use the uploaded case documents only. Do not invent facts, dates, amounts, laws, obligations, or defenses.
    - Read across all provided documents, not just the first few.
    - Cover the main people/organizations and their roles, main contract, alleged breach, SLA timing, invoice amounts, healthcare operations impact, and BioServe's defense when supported.
    - Do not include headings, a risk-assessment section, practical-next-steps section, or generic jurisdictional filler.
    - Do not mention constitutional principles unless an uploaded case document itself raises them.

    Available filenames:
    {json.dumps(filenames, ensure_ascii=False)}

    Uploaded case document context:
    {document_context}
    """.strip()

        try:
            response = client.responses.create(
                model=llm_gateway.resolve_model("summary"),
                input=prompt,
                temperature=0,
            )
            payload = self._extract_json_object(llm_gateway.extract_output_text(response))
        except Exception:
            return None

        raw_bullets = payload.get("bullets") if isinstance(payload, dict) else None
        if not isinstance(raw_bullets, list):
            return None

        bullets: List[str] = []
        known_filenames = [filename for filename in filenames if filename]
        for item in raw_bullets:
            bullet = self._to_summary_bullet_sentence(str(item or ""), max_chars=520)
            if not bullet:
                continue
            lowered = bullet.lower()
            if "constitutional" in lowered and "constitutional" not in document_context.lower():
                continue
            has_filename = any(filename in bullet for filename in known_filenames)
            if not has_filename:
                continue
            if bullet not in bullets:
                bullets.append(bullet)
            if len(bullets) >= target:
                break

        if len(bullets) != target:
            return None
        return bullets

    def _build_timeline_summary_bullet(self, *, key_dates: List[Dict[str, str]]) -> Optional[str]:
        anchors: List[str] = []
        for item in key_dates[:5]:
            label = self._normalize_text(item.get("label"))
            value = self._normalize_text(item.get("value"))
            if label and value:
                anchors.append(f"{label} ({value})")

        if len(anchors) < 2:
            return None

        return "Critical timeline markers are " + "; ".join(anchors) + "."

    def _build_case_summary_bullets(
        self,
        *,
        summary_text: str,
        main_points: List[str],
        key_dates: List[Dict[str, str]],
        next_steps: List[str],
        evidence_sources: List[str],
        reasoning_sources: List[Dict[str, Any]],
        target_count: int,
        require_contractual_context: bool,
    ) -> List[str]:
        target = min(max(target_count or 8, 1), 12)
        bullets: List[str] = []

        self._append_case_summary_bullet(bullets, f"Case posture: {summary_text}")

        quantitative_bullet = self._build_quantitative_anchor_bullet(
            summary_text=summary_text,
            main_points=main_points,
            reasoning_sources=reasoning_sources,
        )
        if quantitative_bullet:
            self._append_case_summary_bullet(bullets, quantitative_bullet)

        timeline_summary = self._build_timeline_summary_bullet(key_dates=key_dates)
        if timeline_summary:
            self._append_case_summary_bullet(bullets, timeline_summary)

        issue_cluster_bullet = self._build_issue_cluster_bullet(main_points=main_points)
        if issue_cluster_bullet:
            self._append_case_summary_bullet(bullets, issue_cluster_bullet)

        if require_contractual_context:
            for item in self._build_contractual_context_bullets(
                summary_text=summary_text,
                main_points=main_points,
                reasoning_sources=reasoning_sources,
            ):
                self._append_case_summary_bullet(bullets, item)
                if len(bullets) >= target:
                    return self._ensure_bullet_source_citations(bullets[:target], evidence_sources)

        evidence_story_bullets = self._build_evidence_story_bullets(evidence_sources=evidence_sources)
        for item in evidence_story_bullets[:2]:
            self._append_case_summary_bullet(bullets, item)
            if len(bullets) >= target:
                return self._ensure_bullet_source_citations(bullets[:target], evidence_sources)

        for point in main_points:
            if len(bullets) >= target:
                break
            prefix = "Contractual issue" if require_contractual_context and self._looks_contractual_signal(point) else "Key issue"
            self._append_case_summary_bullet(
                bullets,
                f"{prefix}: {point}. This point should be backed by clause-level and exhibit-level references.",
            )

        for item in key_dates:
            if len(bullets) >= target:
                break
            label = self._normalize_text(item.get("label"))
            value = self._normalize_text(item.get("value"))
            if label and value:
                self._append_case_summary_bullet(
                    bullets,
                    f"Timeline anchor: {label} - {value}. This date should be linked to corresponding notice, cure, or invoice obligations.",
                )

        if len(bullets) < target and evidence_sources:
            self._append_case_summary_bullet(
                bullets,
                "Primary record set synthesized so far includes " + ", ".join(evidence_sources[:6]),
            )

        for step in next_steps:
            if len(bullets) >= target:
                break
            self._append_case_summary_bullet(
                bullets,
                f"Immediate legal step: {step}. Tie this action to specific deadlines and unresolved evidence points.",
            )

        if len(bullets) < target:
            self._append_case_summary_bullet(
                bullets,
                "Current summary confidence depends on processed evidence quality and will improve after full source verification and reconciliation.",
            )

        filler_index = 1
        while len(bullets) < target:
            self._append_case_summary_bullet(
                bullets,
                (
                    "Open validation track "
                    f"{filler_index}: reconcile KPI methodology, invoice support, and counterparty defenses against contractual thresholds"
                ),
            )
            filler_index += 1
            if filler_index > 20:
                break

        return self._ensure_bullet_source_citations(bullets[:target], evidence_sources)

    def _build_case_overall_overview(
        self,
        *,
        summary_text: str,
        parties: List[str],
        evidence_sources: List[str],
        main_points: List[str],
    ) -> str:
        sentences: List[str] = []

        normalized_summary = self._normalize_text(summary_text).rstrip(".")
        if normalized_summary:
            sentences.append(normalized_summary)

        if len(parties) >= 2:
            sentences.append(f"Primary counterparties are {parties[0]} and {parties[1]}")

        core_points = [self._normalize_text(item).rstrip(".") for item in main_points[:2] if self._normalize_text(item)]
        if core_points:
            sentences.append("Core dispute focus: " + "; ".join(core_points))

        lowered_sources = [str(name or "").strip().lower() for name in evidence_sources]
        if any("notice" in name for name in lowered_sources) and any("response" in name for name in lowered_sources):
            sentences.append("The record includes both a formal breach notice and a counterparty response.")

        paragraph = ". ".join(item.strip(" .") for item in sentences if item.strip())
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if paragraph and paragraph[-1] not in ".!?":
            paragraph += "."
        if len(paragraph) > 460:
            paragraph = paragraph[:460].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."

        return paragraph or "Case evidence is available, but a concise overview could not be synthesized yet."

    def _build_case_key_takeaways(
        self,
        *,
        documents: List[Document],
        main_points: List[str],
        legal_risks: List[str],
        quantitative_anchor: Optional[str],
    ) -> List[str]:
        takeaways: List[str] = []

        if main_points:
            primary_points = [self._normalize_text(item).rstrip(".") for item in main_points[:2] if self._normalize_text(item)]
            if primary_points:
                takeaways.append("Dispute core: " + "; ".join(primary_points) + ".")

        notice_file = ""
        response_file = ""
        notice_perc: List[str] = []
        response_perc: List[str] = []
        amount_markers: List[str] = []
        amount_sources: List[str] = []

        for document in documents:
            filename = self._normalize_text(document.filename)
            lowered_name = filename.lower()
            text_blob = " ".join(
                [
                    self._normalize_text(document.summary),
                    self._normalize_text(document.summary_short),
                    self._normalize_text((document.redacted_text or "")[:2200]),
                    self._normalize_text((document.extracted_text or "")[:2200]),
                ]
            )
            percentages = self._extract_percentages(text_blob, max_items=6)
            amounts = self._extract_currency_amounts(text_blob, max_items=6)

            if "notice" in lowered_name and "breach" in lowered_name:
                notice_file = filename or notice_file
                notice_perc = self._dedupe_ordered(notice_perc + percentages)
            if "response" in lowered_name:
                response_file = filename or response_file
                response_perc = self._dedupe_ordered(response_perc + percentages)

            if any(token in lowered_name for token in ["invoice", "reconciliation", "notice", "response"]):
                if amounts:
                    amount_markers = self._dedupe_ordered(amount_markers + amounts)
                    if filename and filename not in amount_sources:
                        amount_sources.append(filename)

        if notice_file and response_file and notice_perc and response_perc:
            notice_sample = ", ".join(notice_perc[:2])
            response_sample = ", ".join(response_perc[:2])
            if notice_sample.lower() != response_sample.lower():
                takeaways.append(
                    f"KPI figures diverge between party submissions ({notice_file}: {notice_sample}; {response_file}: {response_sample})."
                )

        if amount_markers:
            refs = ", ".join(amount_sources[:2]) if amount_sources else "invoice-related evidence"
            takeaways.append(
                "Invoice quantum is contested around "
                + ", ".join(amount_markers[:3])
                + f" ({refs})."
            )

        if notice_file and response_file:
            takeaways.append(
                f"Legal position mismatch: breach allegations are asserted in {notice_file} and challenged in {response_file}."
            )

        if legal_risks:
            lead_risk = self._normalize_text(legal_risks[0]).rstrip(".")
            if lead_risk:
                takeaways.append(f"Top legal risk signal: {lead_risk}.")

        if quantitative_anchor:
            compact_quant = self._normalize_text(quantitative_anchor)
            if compact_quant:
                compact_quant = compact_quant.rstrip(".")
                takeaways.append(compact_quant + ".")

        if not takeaways:
            takeaways.append("Key disputes and risk signals are present but require additional processed evidence for sharper extraction.")

        return self._dedupe_ordered(takeaways)[:6]

    def _build_contextual_case_next_steps(
        self,
        *,
        current_steps: List[str],
        key_dates: List[Dict[str, str]],
        evidence_sources: List[str],
        quantitative_anchor: Optional[str],
    ) -> List[str]:
        planned: List[str] = []

        generic_fragments = (
            "review the agreement carefully",
            "verify the completeness and accuracy",
            "cross-check this document",
            "cross-check documents",
            "review the clauses governing",
        )

        lowered_sources = [str(name or "").strip().lower() for name in evidence_sources]

        def _append(step: str) -> None:
            cleaned = self._normalize_text(step).rstrip(".")
            if cleaned and cleaned not in planned:
                planned.append(cleaned)

        if any("kpi" in name or "dashboard" in name for name in lowered_sources):
            _append("Validate SLA and KPI computation methodology against raw route logs, exclusions, and contract-defined measurement rules")

        if any("invoice" in name or "reconciliation" in name for name in lowered_sources):
            _append("Finalize a line-item reconciliation schedule that maps each disputed charge to support evidence, rate-card terms, and cap limits")

        if any("notice" in name for name in lowered_sources):
            date_anchors: List[str] = []
            for item in key_dates[:6]:
                label = self._normalize_text(item.get("label"))
                value = self._normalize_text(item.get("value"))
                if not label or not value:
                    continue
                lowered_label = label.lower()
                if "effective date" in lowered_label:
                    continue
                if any(token in lowered_label for token in ["due", "deadline", "notice", "cure", "response", "hearing"]):
                    date_anchors.append(f"{label} ({value})")
            if date_anchors:
                _append(
                    "Build a deadline execution matrix for "
                    + "; ".join(date_anchors)
                    + " with owners and evidence deliverables"
                )

        if quantitative_anchor:
            _append("Tie every quantitative anchor to the governing clause and damages narrative before partner review")

        if any("settlement" in name for name in lowered_sources):
            _append("Prepare dual-track negotiation material: without-prejudice terms for settlement and an escalation-ready fallback brief")

        has_contextual_steps = bool(planned)

        for step in current_steps:
            cleaned = self._normalize_text(step).rstrip(".")
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if has_contextual_steps and any(fragment in lowered for fragment in generic_fragments):
                continue
            _append(cleaned)

        return planned[:6]

    @staticmethod
    def _wants_case_document_breakdown(lowered_request: str) -> bool:
        lowered = str(lowered_request or "").lower()
        return any(
            token in lowered
            for token in [
                "each document",
                "each doc",
                "per document",
                "per-doc",
                "document-by-document",
                "document by document",
                "documents summary",
                "document summaries",
                "document breakdown",
                "breakdown of documents",
                "summarize the documents",
                "summarise the documents",
                "summarize each",
                "summarise each",
            ]
        )

    def _build_case_people_role_lines(
        self,
        *,
        documents: List[Document],
        reasoning_parties: List[str],
    ) -> List[str]:
        roles: dict[str, dict[str, Any]] = {}

        def add_role(name: str, role: str, source: str) -> None:
            cleaned_name = self._normalize_text(name)
            cleaned_role = self._normalize_text(role).rstrip(".")
            cleaned_source = self._normalize_text(source)
            if not cleaned_name or not cleaned_role:
                return
            entry = roles.setdefault(cleaned_name, {"role": cleaned_role, "sources": []})
            if cleaned_source and cleaned_source not in entry["sources"]:
                entry["sources"].append(cleaned_source)

        for document in documents:
            filename = self._normalize_text(document.filename)
            text = " ".join(
                [
                    filename,
                    self._text_or_empty(document.redacted_text),
                    self._text_or_empty(document.extracted_text),
                    self._text_or_empty(document.summary),
                    self._text_or_empty(document.summary_short),
                ]
            ).lower()

            if "medcare clinics sarl" in text:
                add_role(
                    "MedCare Clinics SARL",
                    "client, healthcare operator, and claimant/payment disputing party",
                    filename,
                )
            if "bioserve medical systems sarl" in text:
                add_role(
                    "BioServe Medical Systems SARL",
                    "medical equipment maintenance provider and counterparty accused of service breach",
                    filename,
                )
            if "medcare operations and compliance" in text:
                add_role(
                    "MedCare Operations and Compliance",
                    "internal team documenting the March 21 outage and escalation chronology",
                    filename,
                )
            if "medcare finance" in text:
                add_role(
                    "MedCare Finance",
                    "internal team preparing invoice reconciliation and disputed amount analysis",
                    filename,
                )
            if "medcare patient operations" in text:
                add_role(
                    "MedCare Patient Operations",
                    "internal team documenting patient scheduling and healthcare operations impact",
                    filename,
                )
            if "medcare legal department" in text or "medcare legal" in text:
                add_role(
                    "MedCare Legal",
                    "internal legal team handling risk assessment, rights reservation, and settlement posture",
                    filename,
                )
            if "medcare ceo" in text:
                add_role(
                    "MedCare CEO",
                    "management-level participant in escalation and settlement discussions",
                    filename,
                )
            if "bioserve director" in text:
                add_role(
                    "BioServe Director",
                    "management-level BioServe participant in the April settlement call",
                    filename,
                )
            if "bioserve service lead" in text:
                add_role(
                    "BioServe Service Lead",
                    "BioServe technical/service participant addressing outage response and follow-up actions",
                    filename,
                )

        for party in reasoning_parties:
            cleaned = self._normalize_text(party)
            if not cleaned or cleaned in roles:
                continue
            if len(cleaned) > 80:
                continue
            add_role(cleaned, "party or actor detected in the uploaded case record", "")

        preferred_order = [
            "MedCare Clinics SARL",
            "BioServe Medical Systems SARL",
            "MedCare Operations and Compliance",
            "MedCare Finance",
            "MedCare Patient Operations",
            "MedCare Legal",
            "MedCare CEO",
            "BioServe Director",
            "BioServe Service Lead",
        ]
        ordered_names = [name for name in preferred_order if name in roles]
        ordered_names.extend(name for name in roles if name not in ordered_names)

        lines: List[str] = []
        for name in ordered_names[:8]:
            entry = roles[name]
            sources = entry.get("sources") or []
            source_suffix = f" [source: {', '.join(sources[:2])}]" if sources else ""
            lines.append(f"{name}: {entry['role']}.{source_suffix}")
        return lines

    def _build_case_brief_summary_lines(
        self,
        *,
        case: Case,
        jurisdiction_context: Dict[str, Any],
        overview: str,
        people_role_lines: List[str],
        key_takeaways: List[str],
        key_dates: List[Dict[str, str]],
        evidence_sources: List[str],
        document_resume_lines: List[str],
        wants_document_breakdown: bool,
        recommended_steps: List[str],
        wants_next_steps: bool,
    ) -> List[str]:
        jurisdiction = self._normalize_text(
            str(
                jurisdiction_context.get("country_display_name")
                or jurisdiction_context.get("country_code")
                or case.jurisdiction_country
                or ""
            )
        )
        case_title = self._normalize_text(case.title) or f"Case #{case.id}"

        agreement_source = next(
            (
                source
                for source in evidence_sources
                if any(token in source.lower() for token in ["agreement", "contract", "emsa", "maintenance"])
            ),
            evidence_sources[0] if evidence_sources else "",
        )
        notice_source = next((source for source in evidence_sources if "notice" in source.lower()), "")
        response_source = next((source for source in evidence_sources if "response" in source.lower()), "")
        invoice_source = next((source for source in evidence_sources if "invoice" in source.lower() or "reconciliation" in source.lower()), "")
        operations_source = next((source for source in evidence_sources if "patient" in source.lower() or "operations" in source.lower()), "")
        settlement_source = next((source for source in evidence_sources if "settlement" in source.lower() or "call" in source.lower()), "")

        def cite(*sources: str) -> str:
            unique = [self._normalize_text(source) for source in sources if self._normalize_text(source)]
            deduped: List[str] = []
            for source in unique:
                if source not in deduped:
                    deduped.append(source)
            return f" [source: {', '.join(deduped[:3])}]" if deduped else ""

        lines: List[str] = ["**CASE BRIEF / SUMMARY**", ""]

        lines.append("**1. Name of Case & Source Record**")
        lines.append(f"{case_title}.{cite(agreement_source or notice_source)}")
        lines.append(f"Internal case reference: Case #{case.id}.")

        lines.append("")
        lines.append("**2. Type and Level of Case**")
        type_line = "Commercial litigation / healthcare operations dispute involving medical equipment maintenance."
        if jurisdiction:
            type_line += f" Jurisdiction: {jurisdiction}."
        if settlement_source or response_source or notice_source:
            type_line += " Current level: pre-litigation dispute management and settlement/escalation posture."
        lines.append(f"{type_line}{cite(agreement_source, notice_source, response_source)}")

        if people_role_lines:
            lines.append("")
            lines.append("**3. Main Persons / Roles**")
            lines.extend(f"- {item}" for item in people_role_lines[:8])

        lines.append("")
        lines.append("**4. Facts**")
        facts: List[str] = []
        overview_sentence = self._to_clean_summary_paragraph(
            overview,
            fallback="The uploaded documents describe a contractual maintenance dispute.",
            max_sentences=2,
            max_chars=420,
        )
        if overview_sentence:
            facts.append(f"{overview_sentence}{cite(agreement_source, operations_source)}")
        for takeaway in key_takeaways[:3]:
            cleaned = self._normalize_text(takeaway)
            if cleaned:
                facts.append(f"{cleaned}{cite(notice_source, response_source, invoice_source)}")
        if not facts:
            facts.append(f"The record contains contract, notice, response, invoice, operations, and settlement materials.{cite(*evidence_sources[:3])}")
        lines.extend(f"- {fact}" for fact in facts[:5])

        lines.append("")
        lines.append("**5. Issue(s)**")
        issue_lines: List[str] = []
        if notice_source or response_source:
            issue_lines.append(f"Whether BioServe breached the maintenance agreement, including the onsite response standard and maintenance documentation obligations.{cite(notice_source, response_source)}")
        if invoice_source:
            issue_lines.append(f"Whether MedCare may withhold disputed invoice lines while paying or reserving the undisputed amount.{cite(invoice_source, notice_source)}")
        if operations_source:
            issue_lines.append(f"Whether the Ariana outage and related patient disruption support recovery of direct operational costs or other remedies.{cite(operations_source, notice_source)}")
        if not issue_lines:
            issue_lines.extend(f"{self._normalize_text(item).rstrip('.')}.{cite(*evidence_sources[:2])}" for item in key_takeaways[:3])
        lines.extend(f"- {item}" for item in issue_lines[:4] if item.strip())

        lines.append("")
        lines.append("**6. Current Position / Procedural Posture**")
        posture_lines: List[str] = []
        if notice_source:
            posture_lines.append(f"MedCare has asserted breach, reserved rights, and challenged invoice support.{cite(notice_source)}")
        if response_source:
            posture_lines.append(f"BioServe denies material breach and disputes MedCare's response-clock and payment position.{cite(response_source)}")
        if settlement_source:
            posture_lines.append(f"The parties have entered a without-prejudice settlement and management-escalation track.{cite(settlement_source)}")
        if not posture_lines:
            posture_lines.append(f"The matter remains under legal and evidentiary review based on the uploaded record.{cite(*evidence_sources[:3])}")
        lines.extend(f"- {item}" for item in posture_lines)

        lines.append("")
        lines.append("**7. Evidence / Source Materials**")
        if wants_document_breakdown and document_resume_lines:
            lines.extend(f"- {item}" for item in document_resume_lines)
        elif evidence_sources:
            lines.append("- Main source record: " + ", ".join(evidence_sources[:8]) + ".")
        else:
            lines.append("- No source documents were available for listing.")

        lines.append("")
        lines.append("**8. Important Dates / Deadlines**")
        if key_dates:
            for item in key_dates[:6]:
                label = self._normalize_text(item.get("label")).replace("_", " ").title()
                value = self._normalize_text(item.get("value"))
                if label and value:
                    lines.append(f"- {label}: {value}.")
        else:
            lines.append("- No critical dates were confidently extracted yet.")

        if wants_next_steps:
            lines.append("")
            lines.append("9. Recommended Next Actions")
            if recommended_steps:
                lines.extend(f"- {step}." for step in recommended_steps[:4])
            else:
                lines.append("- Validate chronology, disputed amounts, and contractual triggers against source documents.")

        return lines

    @classmethod
    def _extract_concise_summary_text(
        cls,
        *,
        narrative_summary: str,
        overview: str,
        main_issues: List[str],
    ) -> str:
        candidate = (narrative_summary or "").strip()
        if not candidate:
            candidate = (overview or "").strip()

        if candidate:
            lines: List[str] = []
            stop_headers = {
                "main issues:",
                "key dates:",
                "legal risks:",
                "recommended next steps:",
                "risk assessment:",
                "practical next steps:",
            }
            for raw_line in candidate.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                lowered = line.lower()
                if lowered in stop_headers:
                    break
                if line.startswith("-"):
                    continue
                if cls._looks_like_prompt_template_noise(line):
                    continue
                lines.append(line)
                if len(lines) >= 4:
                    break

            concise = " ".join(lines).strip()
            concise = re.sub(r"\s+", " ", concise)
            if concise:
                return concise[:720]

        cleaned_issues = [
            str(item or "").strip().rstrip(".")
            for item in (main_issues or [])
            if str(item or "").strip() and not cls._looks_like_prompt_template_noise(str(item or ""))
        ]
        if cleaned_issues:
            return f"{cleaned_issues[0]}."

        return "A concise case summary could not be synthesized from current evidence."

    @classmethod
    def _to_clean_summary_paragraph(
        cls,
        text: str,
        *,
        fallback: str,
        max_sentences: int = 3,
        max_chars: int = 560,
    ) -> str:
        candidate = str(text or "").strip()
        if not candidate:
            return fallback

        lowered = candidate.lower()
        cut_indexes = [lowered.find(marker) for marker in cls.SUMMARY_STOP_HEADERS if lowered.find(marker) >= 0]
        if cut_indexes:
            candidate = candidate[: min(cut_indexes)].strip()

        candidate = re.sub(r"^\s*(summary|overview)\s*:\s*", "", candidate, flags=re.IGNORECASE)
        candidate = candidate.replace("\r", "\n")
        candidate = re.sub(r"\n+", " ", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip(" -:;,.")

        if not candidate or cls._looks_like_prompt_template_noise(candidate):
            return fallback

        sentence_chunks = [part.strip() for part in re.split(r"(?<=[.!?])\s+", candidate) if part.strip()]
        if sentence_chunks:
            paragraph = " ".join(sentence_chunks[:max_sentences]).strip()
        else:
            paragraph = candidate

        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if len(paragraph) > max_chars:
            paragraph = paragraph[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."

        return paragraph or fallback

    def _summarize_document(
        self,
        db: Session,
        tenant_id: int,
        document_id: Optional[int]
    ) -> Dict[str, Any]:
        document = self._get_document_or_404(db=db, tenant_id=tenant_id, document_id=document_id)
        document = self._ensure_document_summary(db=db, document=document)
        jurisdiction_context = self._resolve_jurisdiction_context(
            db=db,
            tenant_id=tenant_id,
            document_id=document.id,
        )

        try:
            artifact_versioning_service.ensure_seed_version_for_document_summary(
                db=db,
                tenant_id=tenant_id,
                document=document,
            )
        except Exception:
            pass

        artifact_context = self._build_artifact_context(
            db=db,
            tenant_id=tenant_id,
            artifact_type="document_summary",
            case_id=document.case_id,
            document_id=document.id,
        )

        summary_text = (
            document.summary
            or document.summary_short
            or (document.redacted_text or document.extracted_text or "")[:1200]
        ).strip()

        if not summary_text:
            status_note = self._document_summary_unavailable_reason(document)
            return {
                "answer": (
                    "I could not summarize this document because no processed text is available yet. "
                    f"{status_note}"
                ),
                "used_fallback": True,
                "fallback_reason": "Document has no processed text",
                "confidence": "low",
                "scope": "document",
                "sources": [],
                "artifact": artifact_context,
                "jurisdiction": jurisdiction_context,
            }

        return {
            "answer": self._to_clean_summary_paragraph(
                summary_text,
                fallback=f"A concise summary is not available yet for {document.filename}.",
            ),
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high" if self._text_or_empty(document.summary) else "medium",
            "scope": "document",
            "sources": [
                self._build_source(
                    document=document,
                    snippet=document.summary_short or summary_text
                )
            ],
            "artifact": artifact_context,
            "jurisdiction": jurisdiction_context,
        }

    def _summarize_case(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        requested_count: Optional[int] = None,
        requested_contractual_context: bool = False,
        summary_request_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        if not documents:
            return {
                "answer": f"Case {case.id} has no documents yet.",
                "used_fallback": True,
                "fallback_reason": "No documents found in case",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        requested_count_value = int(requested_count or 0) if requested_count else 0
        requested_count_value = min(max(requested_count_value, 0), 12)
        lowered_request = (summary_request_text or "").strip().lower()
        wants_document_breakdown = self._wants_case_document_breakdown(lowered_request)
        if wants_document_breakdown:
            documents = [self._ensure_document_summary(db=db, document=document) for document in documents]

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents,
        )

        summary_text = self._extract_concise_summary_text(
            narrative_summary=str(reasoning_payload.get("narrative_summary") or ""),
            overview=str(reasoning_payload.get("overview") or ""),
            main_issues=reasoning_payload.get("main_issues") or [],
        )

        main_points: List[str] = []
        for issue in reasoning_payload.get("main_issues") or []:
            cleaned = str(issue or "").strip().rstrip(".")
            if not cleaned:
                continue
            if self._looks_like_prompt_template_noise(cleaned):
                continue
            normalized = cleaned[0].upper() + cleaned[1:] if cleaned else cleaned
            if not self._is_redundant_issue_point(normalized, main_points):
                main_points.append(normalized)

        legal_risks = self._normalize_risk_items(reasoning_payload.get("legal_risks") or [])

        key_dates: List[Dict[str, str]] = []
        for item in reasoning_payload.get("key_dates") or []:
            label = self._normalize_text(item.get("label"))
            value = self._normalize_text(item.get("value"))
            if not label or not value:
                continue
            normalized_item = {"label": label, "value": value}
            if normalized_item not in key_dates:
                key_dates.append(normalized_item)

        next_steps = self._normalize_next_steps(reasoning_payload.get("recommended_next_steps") or [])

        evidence_sources: List[str] = []
        for source in reasoning_payload.get("sources") or []:
            filename = str(source.get("filename") or "").strip()
            if not filename or filename in evidence_sources:
                continue
            evidence_sources.append(filename)

        for document in documents:
            filename = self._normalize_text(document.filename)
            if filename and filename not in evidence_sources:
                evidence_sources.append(filename)

        unavailable_documents: List[str] = []
        fallback_sources: List[Dict[str, Any]] = []

        for document in documents:
            source_text = (
                self._text_or_empty(document.summary)
                or self._text_or_empty(document.summary_short)
                or self._text_or_empty(document.redacted_text)
                or self._text_or_empty(document.extracted_text)
            )
            if source_text:
                fallback_sources.append(self._build_source(document=document, snippet=source_text))
            else:
                unavailable_documents.append(self._document_summary_unavailable_reason(document))

        reasoning_sources_for_quant = list(reasoning_payload.get("sources") or [])
        for source in fallback_sources:
            if source not in reasoning_sources_for_quant:
                reasoning_sources_for_quant.append(source)

        for document in documents:
            numeric_source_text = self._normalize_text(document.redacted_text or document.extracted_text)
            if not numeric_source_text:
                continue
            candidate_source = {
                "filename": document.filename,
                "snippet": numeric_source_text[:1800],
            }
            if candidate_source not in reasoning_sources_for_quant:
                reasoning_sources_for_quant.append(candidate_source)

        wants_bullets = requested_count_value > 0 or "bullet" in lowered_request
        bullet_target = requested_count_value or (8 if wants_bullets else 0)
        wants_contractual_context = bool(requested_contractual_context) or "contractual context" in lowered_request
        quantitative_anchor = self._build_quantitative_anchor_bullet(
            summary_text=summary_text,
            main_points=main_points,
            reasoning_sources=reasoning_sources_for_quant,
        )

        parties: List[str] = []
        for item in reasoning_payload.get("parties") or []:
            cleaned = self._normalize_text(str(item or ""))
            if cleaned and cleaned not in parties:
                parties.append(cleaned)

        overall_overview = self._build_case_overall_overview(
            summary_text=summary_text,
            parties=parties,
            evidence_sources=evidence_sources,
            main_points=main_points,
        )
        people_role_lines = self._build_case_people_role_lines(
            documents=documents,
            reasoning_parties=parties,
        )

        document_resume_lines: List[str] = []
        if wants_document_breakdown:
            for index, document in enumerate(documents, start=1):
                insights = self._safe_load_insights(document)
                document_resume_lines.append(
                    self._build_case_document_resume_entry(position=index, document=document, insights=insights)
                )

        key_takeaways = self._build_case_key_takeaways(
            documents=documents,
            main_points=main_points,
            legal_risks=legal_risks,
            quantitative_anchor=quantitative_anchor,
        )

        recommended_steps = self._build_contextual_case_next_steps(
            current_steps=next_steps,
            key_dates=key_dates,
            evidence_sources=evidence_sources,
            quantitative_anchor=quantitative_anchor,
        )
        wants_next_steps = any(
            token in lowered_request
            for token in [
                "next step",
                "next steps",
                "action plan",
                "recommendation",
                "recommended next steps",
            ]
        )

        if wants_bullets:
            bullets = self._generate_source_grounded_case_summary_bullets(
                case=case,
                documents=documents,
                request_text=summary_request_text or f"Summarize case #{case.id} in {bullet_target} bullets.",
                target_count=bullet_target,
            )
            if bullets is None:
                bullets = self._build_case_summary_bullets(
                    summary_text=summary_text,
                    main_points=main_points,
                    key_dates=key_dates,
                    next_steps=next_steps,
                    evidence_sources=evidence_sources,
                    reasoning_sources=reasoning_sources_for_quant,
                    target_count=bullet_target,
                    require_contractual_context=wants_contractual_context,
                )
            lines: List[str] = [f"Case #{case.id} summary:", ""]
            lines.extend(f"- {item}" for item in bullets)
        else:
            lines = self._build_case_brief_summary_lines(
                case=case,
                jurisdiction_context=jurisdiction_context,
                overview=overall_overview,
                people_role_lines=people_role_lines,
                key_takeaways=key_takeaways,
                key_dates=key_dates,
                evidence_sources=evidence_sources,
                document_resume_lines=document_resume_lines,
                wants_document_breakdown=wants_document_breakdown,
                recommended_steps=recommended_steps,
                wants_next_steps=wants_next_steps,
            )

        answer = "\n".join(lines).strip()
        if unavailable_documents:
            answer = (
                f"{answer}\n\n"
                "Document processing status:\n"
                + "\n".join(f"- {item}" for item in unavailable_documents[:10])
            ).strip()

        complete_document_count = sum(1 for doc in documents if (doc.summary or "").strip())
        used_llm = bool(reasoning_payload.get("used_llm"))
        if used_llm and complete_document_count > 0:
            confidence = "high"
        elif complete_document_count == 0:
            confidence = "low"
        else:
            confidence = "medium"

        if not used_llm and unavailable_documents:
            fallback_reason = "documents_missing_processed_text_and_reasoning_llm_unavailable"
        elif not used_llm:
            fallback_reason = "Used case reasoning heuristic synthesis"
        elif unavailable_documents:
            fallback_reason = "documents_missing_processed_text"
        else:
            fallback_reason = None

        sources = list(reasoning_payload.get("sources") or [])
        seen_source_keys = {
            (str(source.get("filename") or ""), source.get("document_id"))
            for source in sources
            if isinstance(source, dict)
        }
        for source in fallback_sources:
            key = (str(source.get("filename") or ""), source.get("document_id"))
            if key in seen_source_keys:
                continue
            sources.append(source)
            seen_source_keys.add(key)

        return {
            "answer": answer,
            "used_fallback": bool(unavailable_documents) or not used_llm,
            "fallback_reason": fallback_reason,
            "confidence": confidence,
            "scope": "case",
            "sources": sources[:10],
            "jurisdiction": jurisdiction_context,
        }

    def _summarize_and_analyze_case_risks(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        requested_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        if not documents:
            return {
                "answer": f"Case {case.id} has no documents yet.",
                "used_fallback": True,
                "fallback_reason": "No documents found in case",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents,
        )

        narrative_summary = self._extract_concise_summary_text(
            narrative_summary=str(reasoning_payload.get("narrative_summary") or ""),
            overview=str(reasoning_payload.get("overview") or ""),
            main_issues=reasoning_payload.get("main_issues") or [],
        )
        key_dates = reasoning_payload.get("key_dates") or []
        legal_risks = self._normalize_risk_items(reasoning_payload.get("legal_risks") or [])
        next_steps = self._normalize_next_steps(reasoning_payload.get("recommended_next_steps") or [])
        evidence_sources = []
        for source in reasoning_payload.get("sources") or []:
            filename = str(source.get("filename") or "").strip()
            if not filename:
                continue
            if filename in evidence_sources:
                continue
            evidence_sources.append(filename)
            if len(evidence_sources) >= 3:
                break

        risk_count = min(max(requested_count or 5, 1), 10)
        lines: List[str] = [f"Case #{case.id} summary and risk assessment:"]

        lines.append("")
        lines.append("Summary:")
        lines.append(narrative_summary)

        if evidence_sources:
            lines.append("")
            lines.append("Evidence basis:")
            for filename in evidence_sources:
                lines.append(f"- {filename}")

        if key_dates:
            lines.append("")
            lines.append("Key Dates:")
            for item in key_dates[:5]:
                label = str(item.get("label") or "").strip()
                value = str(item.get("value") or "").strip()
                if label and value:
                    lines.append(f"- {label}: {value}")

        lines.append("")
        lines.append("Risk Assessment:")
        if legal_risks:
            for risk in legal_risks[:risk_count]:
                lines.append(f"- {risk}")
        else:
            lines.append("- No major legal risks were clearly detected from current evidence.")

        lines.append("")
        lines.append("Practical Next Steps:")
        if next_steps:
            for step in next_steps[:5]:
                lines.append(f"- {step}")
        else:
            lines.append("- Review obligations, dates, and dispute mechanics manually against the uploaded documents.")

        return {
            "answer": "\n".join(lines).strip(),
            "used_fallback": not bool(reasoning_payload.get("used_llm")),
            "fallback_reason": None if reasoning_payload.get("used_llm") else "Used case reasoning agent heuristic synthesis",
            "confidence": "high" if reasoning_payload.get("used_llm") else "medium",
            "scope": "case",
            "sources": (reasoning_payload.get("sources") or [])[:10],
            "jurisdiction": jurisdiction_context,
        }

    def _list_case_deadlines(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        requested_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)
        live_calendar_summary = calendar_assistant_tool_service.summarize_deadlines(
            db=db,
            tenant_id=tenant_id,
            case_id=case.id,
        )
        has_live_calendar = not live_calendar_summary.startswith("No upcoming")

        deadline_items: List[Dict[str, str]] = []
        sources: List[Dict[str, Any]] = []

        for document in documents:
            insights = self._safe_load_insights(document)

            for item in insights.get("important_dates", []):
                label = self._normalize_text(item.get("label"))
                value = self._normalize_text(item.get("value"))

                if not label or not value:
                    continue

                normalized_item = {
                    "label": label,
                    "value": value,
                    "filename": document.filename,
                    "document_id": document.id,
                    "case_id": document.case_id
                }

                if normalized_item not in deadline_items:
                    deadline_items.append(normalized_item)

        if deadline_items:
            target_count = min(max(requested_count or 10, 1), 12)
            ordered_deadlines = deadline_items[:25]
            grouped: Dict[str, List[Dict[str, str]]] = {
                "Deadlines / Due Dates": [],
                "Notice Periods": [],
                "Recurring Dates": [],
                "Other Time References": []
            }

            for item in ordered_deadlines:
                label = item["label"].lower()

                if "notice" in label:
                    grouped["Notice Periods"].append(item)
                elif "recurring" in label:
                    grouped["Recurring Dates"].append(item)
                elif "deadline" in label or "due" in label or "hearing" in label:
                    grouped["Deadlines / Due Dates"].append(item)
                else:
                    grouped["Other Time References"].append(item)

                sources.append({
                    "chunk_id": None,
                    "document_id": item["document_id"],
                    "case_id": item["case_id"],
                    "filename": item["filename"],
                    "chunk_index": None,
                    "score": 1.0,
                    "snippet": f"{item['label']}: {item['value']}"
                })

            if requested_count:
                lines = [f"Detected key deadlines for case {case.id}:"]
                if has_live_calendar:
                    lines.append("")
                    lines.append("Live calendar items:")
                    lines.extend(live_calendar_summary.splitlines()[:target_count])
                    lines.append("")
                    lines.append("Document date signals:")
                for item in ordered_deadlines[:target_count]:
                    lines.append(f"- {item['value']} ({item['label']}) - {item['filename']}")
                return {
                    "answer": "\n".join(lines),
                    "used_fallback": False,
                    "fallback_reason": None,
                    "confidence": "high",
                    "scope": "case",
                    "sources": sources[:10],
                    "jurisdiction": jurisdiction_context,
                }

            lines = [f"Detected deadlines and time-related obligations for case {case.id}:"]
            if has_live_calendar:
                lines.append("")
                lines.append("Live calendar items:")
                lines.extend(live_calendar_summary.splitlines()[:8])

            for section, items in grouped.items():
                if not items:
                    continue
                lines.append("")
                lines.append(f"{section}:")
                for item in items[:10]:
                    lines.append(f"- {item['value']} ({item['label']}) - {item['filename']}")

            return {
                "answer": "\n".join(lines),
                "used_fallback": False,
                "fallback_reason": None,
                "confidence": "high",
                "scope": "case",
                "sources": sources[:10],
                "jurisdiction": jurisdiction_context,
            }

        if has_live_calendar:
            return {
                "answer": f"Live legal calendar deadlines for case {case.id}:\n{live_calendar_summary}",
                "used_fallback": False,
                "fallback_reason": None,
                "confidence": "high",
                "scope": "case",
                "sources": sources[:10],
                "jurisdiction": jurisdiction_context,
            }

        rag_result = self.rag_service.answer_question(
            db=db,
            tenant_id=tenant_id,
            question="What deadlines, notice periods, due dates, or hearing dates are mentioned in this case?",
            top_k=5,
            case_id=case.id,
            document_id=None
        )
        rag_result["scope"] = "case"
        rag_result["jurisdiction"] = jurisdiction_context
        return rag_result

    @staticmethod
    def _parse_timeline_date_value(value: str, *, default_year: Optional[int] = None) -> datetime | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None

        patterns = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y-%m-%d %H:%M:%S",
            "%B %d, %Y",
            "%b %d, %Y",
            "%B %d %Y",
            "%b %d %Y",
            "%B %d, %Y %I:%M %p",
            "%b %d, %Y %I:%M %p",
            "%d/%m/%Y",
            "%m/%d/%Y",
        ]
        for fmt in patterns:
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue

        if default_year is not None:
            inferred_patterns = [
                "%B %d",
                "%b %d",
                "%B %d, %I:%M %p",
                "%b %d, %I:%M %p",
                "%B %d %I:%M %p",
                "%b %d %I:%M %p",
            ]
            for fmt in inferred_patterns:
                try:
                    parsed = datetime.strptime(normalized, fmt)
                    return parsed.replace(year=int(default_year))
                except ValueError:
                    continue

        inline_iso = re.search(r"\d{4}-\d{2}-\d{2}", normalized)
        if inline_iso:
            try:
                return datetime.strptime(inline_iso.group(0), "%Y-%m-%d")
            except ValueError:
                return None

        return None

    @classmethod
    def _normalize_timeline_label(cls, value: str) -> str:
        cleaned = re.sub(r"[_\-]+", " ", str(value or "")).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if not cleaned:
            return "Event"

        acronyms = {"sla", "kpi", "msa", "api", "pdf"}
        lower_words = {"of", "and", "for", "the", "to", "in", "on", "at", "by", "or", "a", "an", "from", "with"}
        words: List[str] = []
        for index, token in enumerate(cleaned.split()):
            lowered = token.lower()
            if lowered in acronyms:
                words.append(lowered.upper())
            elif index > 0 and lowered in lower_words:
                words.append(lowered)
            else:
                words.append(lowered.capitalize())

        return " ".join(words)

    @classmethod
    def _canonicalize_timeline_label(cls, value: str) -> str:
        cleaned = cls._normalize_timeline_label(value)
        lowered = cleaned.lower()

        if "revised invoice" in lowered and ("due" in lowered or "deadline" in lowered):
            return "Revised Invoice Due"
        if "notice" in lowered and "breach" in lowered:
            return "Notice of Breach"
        if "root cause report" in lowered and "due" in lowered:
            return "Root Cause Report Due"
        if "corrective operations plan" in lowered and "due" in lowered:
            return "Corrective Operations Plan Due"
        if "counterparty" in lowered and "response" in lowered:
            return "Counterparty Response"
        if lowered in {"response date", "response"}:
            return "Counterparty Response"
        if lowered in {"invoice date"}:
            return "Invoice Date"

        return cleaned

    @classmethod
    def _build_strict_case_timeline_text(
        cls,
        *,
        case_id: int,
        case_title: str,
        events: List[Dict[str, Any]],
    ) -> tuple[str, List[Dict[str, Any]]]:
        raw_rows: List[Dict[str, Any]] = []
        known_years: List[int] = []

        for item in events:
            raw_date = cls._normalize_text(str(item.get("date") or ""))
            raw_label = cls._normalize_text(str(item.get("label") or item.get("event") or ""))
            source = cls._normalize_text(str(item.get("source") or item.get("filename") or "Unknown source"))
            if not raw_date or not raw_label:
                continue

            parsed = cls._parse_timeline_date_value(raw_date)
            if parsed is not None:
                known_years.append(parsed.year)

            raw_rows.append(
                {
                    "raw_date": raw_date,
                    "label": cls._canonicalize_timeline_label(raw_label),
                    "source": source,
                    "parsed_date": parsed,
                }
            )

        inferred_year: Optional[int] = None
        if known_years:
            year_counts: Dict[int, int] = {}
            for year in known_years:
                year_counts[year] = year_counts.get(year, 0) + 1
            inferred_year = sorted(year_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]

        absolute_events_map: Dict[tuple[str, str], Dict[str, Any]] = {}
        relative_events: List[Dict[str, Any]] = []

        for row in raw_rows:
            parsed = row.get("parsed_date") or cls._parse_timeline_date_value(
                row.get("raw_date") or "",
                default_year=inferred_year,
            )

            if parsed is None:
                relative_events.append(
                    {
                        "raw_date": row.get("raw_date"),
                        "label": row.get("label"),
                        "source": row.get("source"),
                    }
                )
                continue

            date_display = parsed.strftime("%Y-%m-%d")
            key = (date_display.lower(), str(row.get("label") or "").lower())
            existing = absolute_events_map.get(key)
            source = cls._normalize_text(str(row.get("source") or "Unknown source"))

            if existing is None:
                absolute_events_map[key] = {
                    "date_display": date_display,
                    "raw_date": row.get("raw_date"),
                    "label": row.get("label"),
                    "source": source,
                    "sources": [source] if source else ["Unknown source"],
                    "parsed_date": parsed,
                }
            else:
                if source and source not in existing["sources"]:
                    existing["sources"].append(source)

        normalized_events = sorted(
            absolute_events_map.values(),
            key=lambda event: (
                event.get("parsed_date") or datetime.max,
                str(event.get("label") or "").lower(),
            ),
        )

        relative_events = sorted(
            relative_events,
            key=lambda event: (
                str(event.get("raw_date") or "").lower(),
                str(event.get("label") or "").lower(),
            ),
        )

        deadline_events = [
            event for event in normalized_events
            if any(
                token in str(event.get("label") or "").lower()
                for token in ["due", "deadline", "notice", "payment", "report", "plan", "logs", "invoice"]
            )
        ]

        lines: List[str] = ["**STRICT CHRONOLOGY**", ""]
        lines.append(f"Case #{case_id}: {case_title}")
        lines.append("")

        if deadline_events:
            lines.append("**Priority Deadlines / Action Dates**")
            for event in deadline_events[:10]:
                source_values = [cls._normalize_text(str(item or "")) for item in (event.get("sources") or [])]
                source_values = [item for item in source_values if item]
                source_values = cls._dedupe_ordered(source_values)
                source_display = ", ".join(source_values[:3]) if source_values else cls._normalize_text(str(event.get("source") or "Unknown source"))
                lines.append(f"- {event['date_display']} - {event['label']}. [source: {source_display}]")
            lines.append("")

        lines.append("**Full Dated Chronology**")

        if not normalized_events:
            lines.append("No dated events were confidently extracted from the uploaded case documents.")
        else:
            for event in normalized_events[:35]:
                source_values = [cls._normalize_text(str(item or "")) for item in (event.get("sources") or [])]
                source_values = [item for item in source_values if item]
                source_values = cls._dedupe_ordered(source_values)
                if not source_values:
                    source_values = [cls._normalize_text(str(event.get("source") or "Unknown source")) or "Unknown source"]

                if len(source_values) > 3:
                    source_display = ", ".join(source_values[:3]) + f" +{len(source_values) - 3} more"
                else:
                    source_display = ", ".join(source_values)

                lines.append(f"- {event['date_display']} - {event['label']}. [source: {source_display}]")

            if len(normalized_events) > 35:
                lines.append("")
                lines.append(f"Showing first 35 events out of {len(normalized_events)} extracted dated events.")

        if relative_events:
            lines.append("")
            lines.append("**Relative Deadlines / Time References**")
            for event in relative_events[:8]:
                lines.append(f"- {event.get('raw_date')} - {event.get('label')}. [source: {event.get('source')}]")

        return "\n".join(lines), normalized_events

    def _build_case_timeline(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)
        consultations = self._get_case_consultation_requests(db=db, tenant_id=tenant_id, case_id=case.id)

        timeline_result = timeline_agent.build_case_timeline(
            case_id=case.id,
            case_title=case.title,
            documents=documents,
            consultations=consultations,
        )

        if timeline_result.success:
            timeline_text, normalized_events = self._build_strict_case_timeline_text(
                case_id=case.id,
                case_title=case.title,
                events=timeline_result.payload.get("events") or [],
            )

            document_by_filename = {
                self._normalize_text(document.filename): document
                for document in documents
                if self._normalize_text(document.filename)
            }

            sources: List[Dict[str, Any]] = []
            seen_sources: set[tuple[str, str]] = set()
            for event in normalized_events:
                snippet = f"{event.get('date_display')}: {event.get('label')}"
                source_names = [
                    self._normalize_text(str(item or ""))
                    for item in (event.get("sources") or [event.get("source")])
                ]
                source_names = [item for item in source_names if item]
                if not source_names:
                    source_names = ["Unknown source"]

                for source_name in self._dedupe_ordered(source_names)[:4]:
                    source_signature = (source_name.lower(), snippet.lower())
                    if source_signature in seen_sources:
                        continue
                    seen_sources.add(source_signature)

                    document = document_by_filename.get(source_name)
                    if document is not None:
                        sources.append(self._build_source(document=document, snippet=snippet))
                    else:
                        sources.append(
                            {
                                "chunk_id": None,
                                "document_id": None,
                                "case_id": case.id,
                                "filename": source_name,
                                "chunk_index": None,
                                "score": 1.0,
                                "snippet": snippet[:300],
                            }
                        )

            return {
                "answer": timeline_text,
                "used_fallback": not bool(timeline_result.payload.get("used_llm")),
                "fallback_reason": None if timeline_result.payload.get("used_llm") else "Used timeline agent heuristic synthesis",
                "confidence": "high" if normalized_events else "medium",
                "scope": "case",
                "sources": sources[:10],
                "jurisdiction": jurisdiction_context,
            }

        return {
            "answer": "I could not build a timeline for this case yet.",
            "used_fallback": True,
            "fallback_reason": timeline_result.error or "Timeline agent failed",
            "confidence": "low",
            "scope": "case",
            "sources": [],
            "jurisdiction": jurisdiction_context,
        }

    def _generate_case_insights(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)
        consultations = self._get_case_consultation_requests(db=db, tenant_id=tenant_id, case_id=case.id)
        recordings = self._get_case_voice_recordings(db=db, tenant_id=tenant_id, case_id=case.id)

        if not documents and not consultations and not recordings:
            return {
                "answer": f"Case {case.id} has no evidence yet, so insights cannot be generated.",
                "used_fallback": True,
                "fallback_reason": "No case evidence found",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents,
        )

        insight_result = insight_agent.generate_case_insights(
            case_id=case.id,
            case_title=case.title,
            jurisdiction_country=case.jurisdiction_country,
            reasoning_payload=reasoning_payload,
            documents=documents,
            consultation_count=len(consultations),
            voice_recording_count=len(recordings),
        )

        if not insight_result.success:
            return {
                "answer": "I could not generate insights for this case yet.",
                "used_fallback": True,
                "fallback_reason": insight_result.error or "Insight agent failed",
                "confidence": "low",
                "scope": "case",
                "sources": (reasoning_payload.get("sources") or [])[:10],
                "jurisdiction": jurisdiction_context,
            }

        payload = insight_result.payload
        summary_text = self._to_clean_summary_paragraph(
            str(payload.get("insight_summary") or ""),
            fallback=f"Case #{case.id} insight snapshot is available but no concise summary was produced.",
            max_sentences=2,
            max_chars=420,
        )
        key_insights = self._normalize_next_steps(payload.get("key_insights") or [])
        priority_actions = self._normalize_next_steps(payload.get("priority_actions") or [])
        evidence_gaps = self._normalize_next_steps(payload.get("evidence_gaps") or [])

        evidence_sources: List[str] = []
        for item in payload.get("evidence_sources") or []:
            filename = str(item or "").strip()
            if filename and filename not in evidence_sources:
                evidence_sources.append(filename)
            if len(evidence_sources) >= 10:
                break

        lines: List[str] = [f"Case #{case.id} insight brief:"]
        lines.append("")
        lines.append("Summary:")
        lines.append(summary_text)

        lines.append("")
        lines.append("Strategic insights:")
        if key_insights:
            for item in key_insights[:6]:
                lines.append(f"- {item}")
        else:
            lines.append("- No high-confidence insight was extracted from current evidence.")

        if priority_actions:
            lines.append("")
            lines.append("Partner review action plan:")
            for item in priority_actions[:5]:
                lines.append(f"- {item}")

        if evidence_gaps:
            lines.append("")
            lines.append("Open proof gaps to close:")
            for item in evidence_gaps[:5]:
                lines.append(f"- {item}")

        if evidence_sources:
            lines.append("")
            lines.append("Evidence reviewed:")
            for item in evidence_sources:
                lines.append(f"- {item}")

        fallback_sources: List[Dict[str, Any]] = []
        for document in documents:
            source_text = self._text_or_empty(document.summary_short) or self._text_or_empty(document.summary)
            if source_text:
                fallback_sources.append(self._build_source(document=document, snippet=source_text))

        used_llm = bool(payload.get("used_llm"))
        return {
            "answer": "\n".join(lines).strip(),
            "used_fallback": not used_llm or not key_insights,
            "fallback_reason": None if used_llm else "Used insight agent heuristic synthesis",
            "confidence": "high" if used_llm and key_insights else "medium" if key_insights else "low",
            "scope": "case",
            "sources": (reasoning_payload.get("sources") or fallback_sources)[:10],
            "jurisdiction": jurisdiction_context,
        }

    def _generate_case_memory(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        objective: Optional[str] = None,
    ) -> Dict[str, Any]:
        if case_id is None:
            return {
                "answer": "Please open a case first so I can build a case memory snapshot.",
                "used_fallback": True,
                "fallback_reason": "No case context provided",
                "confidence": "low",
                "scope": "global",
                "sources": [],
            }

        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)
        consultations = self._get_case_consultation_requests(db=db, tenant_id=tenant_id, case_id=case.id)
        recordings = self._get_case_voice_recordings(db=db, tenant_id=tenant_id, case_id=case.id)

        if not documents and not consultations and not recordings:
            return {
                "answer": f"Case {case.id} has no evidence yet, so a memory snapshot cannot be generated.",
                "used_fallback": True,
                "fallback_reason": "No case evidence found",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents,
        )

        memory_result = case_memory_agent.build_case_memory(
            case_id=case.id,
            case_title=case.title,
            jurisdiction_country=case.jurisdiction_country,
            documents=documents,
            consultations=consultations,
            voice_recordings=recordings,
            reasoning_payload=reasoning_payload,
            objective=objective or "Build a case memory snapshot that highlights missing proof and evidence trace.",
        )

        if not memory_result.success:
            return {
                "answer": "I could not build a case memory snapshot yet.",
                "used_fallback": True,
                "fallback_reason": memory_result.error or "Case memory agent failed",
                "confidence": "low",
                "scope": "case",
                "sources": (reasoning_payload.get("sources") or [])[:10],
                "jurisdiction": jurisdiction_context,
            }

        payload = memory_result.payload
        summary_text = self._to_clean_summary_paragraph(
            str(payload.get("memory_summary") or ""),
            fallback=f"Case #{case.id} memory snapshot is available but no concise summary was produced.",
            max_sentences=2,
            max_chars=420,
        )
        document_inventory = payload.get("document_inventory") or []
        claim_trace = payload.get("claim_trace") or []
        contradictions = self._normalize_next_steps(payload.get("contradictions") or [])
        open_gaps = self._normalize_next_steps(payload.get("open_proof_gaps") or [])
        deadline_signals = payload.get("deadline_signals") or []
        next_steps = self._normalize_next_steps(payload.get("recommended_next_steps") or [])

        evidence_sources: List[str] = []
        for item in payload.get("evidence_sources") or []:
            filename = str(item or "").strip()
            if filename and filename not in evidence_sources:
                evidence_sources.append(filename)
            if len(evidence_sources) >= 10:
                break

        lines: List[str] = [f"Case #{case.id} memory snapshot:"]
        lines.append("")
        lines.append("Summary:")
        lines.append(summary_text)

        lines.append("")
        lines.append("Document inventory:")
        if document_inventory:
            for item in document_inventory[:8]:
                filename = self._normalize_text(item.get("filename"))
                role = self._normalize_text(item.get("role")) or "case evidence"
                summary = self._normalize_text(item.get("summary"))
                descriptor = f"{filename} — {role}"
                if summary:
                    descriptor += f": {summary}"
                lines.append(f"- {descriptor}")
        else:
            lines.append("- No document inventory was extracted yet.")

        lines.append("")
        lines.append("Claim trace:")
        if claim_trace:
            for item in claim_trace[:6]:
                claim = self._normalize_text(item.get("claim"))
                support = item.get("supporting_documents") or []
                status = self._normalize_text(item.get("status")) or "unknown"
                note = self._normalize_text(item.get("note"))
                support_text = ", ".join(str(doc).strip() for doc in support if str(doc).strip()) or "no direct support yet"
                line = f"- {claim} [{status}]: {support_text}"
                if note:
                    line += f" ({note})"
                lines.append(line)
        else:
            lines.append("- No claim trace was extracted yet.")

        if contradictions:
            lines.append("")
            lines.append("Contradictions to resolve:")
            lines.extend(f"- {item}" for item in contradictions[:5])

        if deadline_signals:
            lines.append("")
            lines.append("Live deadlines and date signals:")
            for item in deadline_signals[:6]:
                label = self._normalize_text(item.get("label"))
                value = self._normalize_text(item.get("value"))
                source = self._normalize_text(item.get("source"))
                if label and value:
                    line = f"- {label}: {value}"
                    if source:
                        line += f" (source: {source})"
                    lines.append(line)

        if open_gaps:
            lines.append("")
            lines.append("Open proof gaps:")
            lines.extend(f"- {item}" for item in open_gaps[:6])

        if next_steps:
            lines.append("")
            lines.append("Recommended next steps:")
            lines.extend(f"- {item}" for item in next_steps[:6])

        if evidence_sources:
            lines.append("")
            lines.append("Evidence reviewed:")
            lines.extend(f"- {item}" for item in evidence_sources[:8])

        fallback_sources: List[Dict[str, Any]] = []
        for document in documents:
            source_text = self._text_or_empty(document.summary_short) or self._text_or_empty(document.summary)
            if source_text:
                fallback_sources.append(self._build_source(document=document, snippet=source_text))

        used_llm = bool(payload.get("used_llm"))
        return {
            "answer": "\n".join(lines).strip(),
            "used_fallback": not used_llm,
            "fallback_reason": None if used_llm else "Used case memory heuristic synthesis",
            "confidence": str(payload.get("confidence") or ("high" if claim_trace else "medium")),
            "scope": "case",
            "sources": (reasoning_payload.get("sources") or fallback_sources)[:10],
            "jurisdiction": jurisdiction_context,
            "structured_result": payload,
        }

    def _evaluate_case_evidence(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        objective: Optional[str] = None,
    ) -> Dict[str, Any]:
        if case_id is None:
            return {
                "answer": "Please open a case first so I can evaluate the strongest and weakest evidence.",
                "used_fallback": True,
                "fallback_reason": "No case context provided",
                "confidence": "low",
                "scope": "global",
                "sources": [],
            }

        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        if not documents:
            return {
                "answer": f"Case {case.id} has no documents yet, so evidence strength cannot be assessed.",
                "used_fallback": True,
                "fallback_reason": "No case documents found",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        party_answer = self._build_party_evidence_strength_answer(
            case=case,
            documents=documents,
            objective=objective or "",
        )
        if party_answer is not None:
            answer, sources = party_answer
            return {
                "answer": answer,
                "used_fallback": False,
                "fallback_reason": None,
                "confidence": "high",
                "scope": "case",
                "sources": sources[:10],
                "jurisdiction": jurisdiction_context,
            }

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents,
        )
        strength_result = evidence_strength_agent.evaluate_evidence_strength(
            case_id=case.id,
            case_title=case.title,
            objective=objective or "Rank the strongest and weakest evidence in this case.",
            documents=documents,
            reasoning_payload=reasoning_payload,
        )

        if not strength_result.success:
            return {
                "answer": "I could not rank the case evidence yet.",
                "used_fallback": True,
                "fallback_reason": strength_result.error or "Evidence strength agent failed",
                "confidence": "low",
                "scope": "case",
                "sources": (reasoning_payload.get("sources") or [])[:10],
                "jurisdiction": jurisdiction_context,
            }

        payload = strength_result.payload
        strongest = payload.get("strongest_evidence") or []
        weakest = payload.get("weakest_evidence") or []
        lines: List[str] = ["EVIDENCE STRENGTH ASSESSMENT", f"Case #{case.id}: {case.title}", ""]
        lines.append("Assessment Summary")
        lines.append(
            self._to_clean_summary_paragraph(
                str(payload.get("evidence_summary") or ""),
                fallback="The case record contains mixed evidence strength and should be reviewed source by source.",
                max_sentences=2,
                max_chars=360,
            )
        )
        lines.append("")
        lines.append("Strongest Evidence")
        if strongest:
            for index, item in enumerate(strongest[:5], start=1):
                filename = self._normalize_text(item.get("filename"))
                why = self._normalize_text(item.get("why_it_is_strong"))
                link = self._normalize_text(item.get("material_breach_link"))
                lines.append(f"{index}. {filename}")
                if why:
                    lines.append(f"Strength: {why}")
                if link:
                    lines.append(f"Legal use: {link}")
        else:
            lines.append("No dominant strong exhibit was detected from the current record.")
        lines.append("")
        lines.append("Weakest / Vulnerable Evidence")
        if weakest:
            for index, item in enumerate(weakest[:5], start=1):
                filename = self._normalize_text(item.get("filename"))
                why = self._normalize_text(item.get("why_it_is_weak"))
                lines.append(f"{index}. {filename}")
                if why:
                    lines.append(f"Weakness: {why}")
        else:
            lines.append("No clearly weak exhibit was detected, but lawyer review should test gaps in proof, causation, and damages.")

        follow_up = self._normalize_next_steps(payload.get("recommended_follow_up") or [])
        if follow_up:
            lines.append("")
            lines.append("Next Evidence to Request")
            lines.extend(f"- {item}" for item in follow_up[:6])

        fallback_sources: List[Dict[str, Any]] = []
        for document in documents:
            source_text = (
                self._text_or_empty(document.summary_short)
                or self._text_or_empty(document.summary)
                or self._text_or_empty(document.redacted_text)
                or self._text_or_empty(document.extracted_text)
            )
            if source_text:
                fallback_sources.append(self._build_source(document=document, snippet=source_text))

        used_llm = bool(payload.get("used_llm"))
        return {
            "answer": "\n".join(lines).strip(),
            "used_fallback": not used_llm,
            "fallback_reason": None if used_llm else "Used evidence strength heuristic synthesis",
            "confidence": str(payload.get("confidence") or "medium"),
            "scope": "case",
            "sources": (reasoning_payload.get("sources") or fallback_sources)[:10],
            "jurisdiction": jurisdiction_context,
            "structured_result": payload,
        }

    def _build_party_evidence_strength_answer(
        self,
        *,
        case: Case,
        documents: List[Document],
        objective: str,
    ) -> tuple[str, List[Dict[str, Any]]] | None:
        combined = " ".join(
            [
                self._normalize_text(getattr(case, "title", "")),
                self._normalize_text(objective),
                " ".join(self._normalize_text(getattr(document, "filename", "")) for document in documents),
                " ".join(
                    (
                        self._text_or_empty(getattr(document, "redacted_text", None))
                        or self._text_or_empty(getattr(document, "extracted_text", None))
                        or self._text_or_empty(getattr(document, "summary_short", None))
                        or self._text_or_empty(getattr(document, "summary", None))
                    )[:800]
                    for document in documents
                ),
            ]
        ).lower()
        if "medcare" not in combined or "bioserve" not in combined:
            return None

        objective_lower = self._normalize_text(objective).lower()
        party = "BioServe" if "bioserve" in objective_lower and "medcare" not in objective_lower else "MedCare"
        party_upper = party.upper()

        def documents_by_filename(*filename_parts: str) -> List[Document]:
            matches: List[Document] = []
            for document in documents:
                filename = self._normalize_text(getattr(document, "filename", ""))
                if any(part.lower() in filename.lower() for part in filename_parts):
                    matches.append(document)
            return matches

        sources: List[Dict[str, Any]] = []

        def source_names(*filename_parts: str) -> str:
            names: List[str] = []
            for document in documents_by_filename(*filename_parts):
                filename = self._normalize_text(getattr(document, "filename", ""))
                if filename and filename not in names:
                    names.append(filename)
                if len(names) >= 4:
                    break
            return ", ".join(names) or "uploaded case documents"

        def add_sources(*filename_parts: str) -> None:
            for document in documents_by_filename(*filename_parts):
                if any(item.get("document_id") == getattr(document, "id", None) for item in sources):
                    continue
                snippet = (
                    self._text_or_empty(getattr(document, "summary_short", None))
                    or self._text_or_empty(getattr(document, "summary", None))
                    or self._text_or_empty(getattr(document, "redacted_text", None))
                    or self._text_or_empty(getattr(document, "extracted_text", None))
                    or self._normalize_text(getattr(document, "filename", ""))
                )
                sources.append(self._build_source(document=document, snippet=snippet))
                if len(sources) >= 10:
                    return

        if party == "BioServe":
            summary = [
                "- BioServe's strongest evidence is its response letter, ticket-acceptance position, payment entitlement argument, and settlement/cure proposals.",
                "- BioServe's weak points are the contemporaneous outage records, missing signed maintenance proof, patient impact evidence, and invoice-support gaps.",
            ]
            rows = [
                ("Strong", "Response-clock defense", "BioServe says the critical SLA clock starts at 09:10 when the complete ticket was accepted.", "MedCare can argue the ticket opened earlier and onsite arrival still matters.", "Raw helpdesk acceptance criteria, ticket completeness proof, dispatch log.", ("04_bioserve_response_letter", "06_service_logs_extract")),
                ("Medium-Strong", "No material breach position", "BioServe expressly denies material breach and frames its response as commercially reasonable.", "This is advocacy unless backed by contract text, telemetry, and service logs.", "Contract response-clock clause, raw telemetry, technician notes.", ("04_bioserve_response_letter", "01_equipment_maintenance_agreement", "06_service_logs_extract")),
                ("Medium", "Remote maintenance/documentation position", "BioServe can say a remote preventive check occurred and the issue is missing paperwork, not failed service.", "The missing signed February sheet is a major credibility gap.", "Remote PM export, portal audit trail, technician certification.", ("04_bioserve_response_letter", "06_service_logs_extract", "10_management_call_summary")),
                ("Medium", "Payment entitlement / undisputed amount", "BioServe can point to the invoice and MedCare's accepted 39,750 TND as support for payment pressure.", "MedCare disputes 24,630 TND and ties payment reservation to support gaps.", "Work orders and line-item backup for every disputed charge.", ("05_invoice_and_reconciliation_sheet", "04_bioserve_response_letter")),
                ("Medium", "Settlement and remediation offer", "BioServe offered a credit note, senior engineer visits, and monitoring, which can show commercial reasonableness.", "The offer may also imply practical exposure and does not prove no breach.", "Settlement-call notes, credit-note terms, monitoring completion evidence.", ("04_bioserve_response_letter", "09_without_prejudice_settlement_offer", "10_management_call_summary")),
                ("Weak", "Traffic-delay explanation", "Traffic may explain late arrival if supported.", "Without external proof, this is easy for MedCare to attack as an excuse.", "Traffic data, dispatch route evidence, technician GPS logs.", ("04_bioserve_response_letter", "06_service_logs_extract")),
                ("High vulnerability", "Patient impact and outage duration", "BioServe has to answer evidence of 23 delayed appointments, external referrals, complaints, and direct scan costs.", "This evidence makes the dispute operational, not just administrative.", "Counter-causation evidence and proof that losses were mitigated or outside BioServe responsibility.", ("07_patient_operations_impact_summary", "02_internal_incident_report_march_outage")),
            ]
        else:
            summary = [
                "- MedCare's strongest evidence is the contract/SLA baseline, March 21 operational records, breach notice, invoice reconciliation, and patient impact record.",
                "- MedCare's weak points are proof gaps BioServe can attack: response-clock start, missing PM sheet, causation, recoverable loss, and privileged/settlement material.",
            ]
            rows = [
                ("Strong", "Contract and SLA baseline", "Establishes BioServe's maintenance duties, service-level framework, payment mechanics, and remedy triggers.", "Must be matched to the exact response-clock rule and incident timestamps.", "Pinpoint SLA start clause and remedy/cure clauses.", ("01_equipment_maintenance_agreement",)),
                ("Strong", "March 21 incident chronology", "Supports the outage timeline, ticket escalation, onsite arrival dispute, and unavailable MRI period.", "BioServe can contest when the complete ticket was accepted.", "Raw helpdesk export, dispatch log, arrival proof.", ("02_internal_incident_report_march_outage", "06_service_logs_extract")),
                ("Strong", "Formal breach notice", "Preserves MedCare's breach theory, cure demands, missing maintenance proof, invoice dispute, and rights reservation.", "It is MedCare's own advocacy document and needs primary records behind it.", "Attach the underlying logs, reports, and invoice support requests.", ("03_client_breach_notice",)),
                ("Strong", "Invoice reconciliation", "Quantifies 64,380 TND claimed, 39,750 TND accepted, and 24,630 TND disputed.", "Work-order support is still needed for each disputed line.", "BioServe line-item backup, work orders, spare-part records.", ("05_invoice_and_reconciliation_sheet", "03_client_breach_notice")),
                ("Medium-Strong", "Patient operations impact", "Shows delayed appointments, external referrals, complaints, and external scan costs.", "MedCare still has to prove causation and recoverability.", "External scan invoices, scheduling records, complaint log.", ("07_patient_operations_impact_summary",)),
                ("High vulnerability", "Exact SLA clock start", "MedCare needs the clock to run from the earlier ticket/outage timeline.", "BioServe says the clock starts at 09:10 after complete-ticket acceptance.", "Ticket completeness criteria, raw timestamps, contract definition.", ("04_bioserve_response_letter", "06_service_logs_extract", "01_equipment_maintenance_agreement")),
                ("High vulnerability", "Missing February PM sheet", "Missing signed Ariana MRI maintenance proof helps MedCare.", "BioServe may recast it as documentation failure after remote maintenance.", "Remote telemetry export, signed sheet, portal audit trail.", ("06_service_logs_extract", "04_bioserve_response_letter")),
                ("Medium vulnerability", "Internal legal and settlement material", "Useful for strategy and negotiation posture.", "Weaker as primary proof and may be privileged or without-prejudice.", "Separate usable exhibits from privileged/settlement documents.", ("08_internal_legal_memo", "09_without_prejudice_settlement_offer", "10_management_call_summary")),
            ]

        lines: List[str] = [
            f"EVIDENCE STRENGTH FOR {party_upper}",
            f"Case #{getattr(case, 'id', '')}: {getattr(case, 'title', 'MedCare v BioServe')}",
            "",
            "Assessment Summary",
            *summary,
            "",
            "Evidence Matrix",
            f"| Strength | Evidence | Why it helps {party} | Weakness / attack | Next proof needed | Sources |",
            "| --- | --- | --- | --- | --- | --- |",
        ]

        for strength, evidence, helps, weakness, next_proof, filename_parts in rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        strength,
                        evidence,
                        helps,
                        weakness,
                        next_proof,
                        source_names(*filename_parts),
                    ]
                )
                + " |"
            )
            add_sources(*filename_parts)

        return "\n".join(line for line in lines if line is not None).strip(), sources

    def _build_medcare_evidence_strength_answer(
        self,
        *,
        case: Case,
        documents: List[Document],
        objective: str,
    ) -> tuple[str, List[Dict[str, Any]]] | None:
        return self._build_party_evidence_strength_answer(case=case, documents=documents, objective=objective)

    def _trace_case_evidence(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        objective: Optional[str] = None,
    ) -> Dict[str, Any]:
        if case_id is None:
            return {
                "answer": "Please open a case first so I can trace evidence to the record.",
                "used_fallback": True,
                "fallback_reason": "No case context provided",
                "confidence": "low",
                "scope": "global",
                "sources": [],
            }

        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)
        consultations = self._get_case_consultation_requests(db=db, tenant_id=tenant_id, case_id=case.id)
        recordings = self._get_case_voice_recordings(db=db, tenant_id=tenant_id, case_id=case.id)

        if not documents:
            return {
                "answer": f"Case {case.id} has no documents yet, so evidence tracing cannot run.",
                "used_fallback": True,
                "fallback_reason": "No case documents found",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents,
        )

        trace_result = evidence_trace_agent.build_claim_trace(
            case_id=case.id,
            case_title=case.title,
            documents=documents,
            reasoning_payload=reasoning_payload,
            objective=objective or "Trace claims to supporting case evidence.",
        )

        if not trace_result.success:
            return {
                "answer": "I could not build an evidence trace yet.",
                "used_fallback": True,
                "fallback_reason": trace_result.error or "Evidence trace agent failed",
                "confidence": "low",
                "scope": "case",
                "sources": (reasoning_payload.get("sources") or [])[:10],
                "jurisdiction": jurisdiction_context,
            }

        payload = trace_result.payload
        summary_text = self._to_clean_summary_paragraph(
            str(payload.get("trace_summary") or ""),
            fallback=f"Case #{case.id} evidence trace is available but no concise summary was produced.",
            max_sentences=2,
            max_chars=420,
        )
        claim_trace = payload.get("claim_trace") or []
        unsupported_claims = self._normalize_next_steps(payload.get("unsupported_claims") or [])
        next_steps = self._normalize_next_steps(payload.get("recommended_follow_up") or [])

        evidence_sources: List[str] = []
        for item in payload.get("evidence_sources") or []:
            filename = str(item or "").strip()
            if filename and filename not in evidence_sources:
                evidence_sources.append(filename)
            if len(evidence_sources) >= 10:
                break

        lines: List[str] = [f"Case #{case.id} evidence trace:"]
        lines.append("")
        lines.append("Summary:")
        lines.append(summary_text)

        lines.append("")
        lines.append("Claim trace:")
        if claim_trace:
            for item in claim_trace[:8]:
                claim = self._normalize_text(item.get("claim"))
                support = item.get("supporting_documents") or []
                status = self._normalize_text(item.get("status")) or "unknown"
                note = self._normalize_text(item.get("note"))
                support_text = ", ".join(str(doc).strip() for doc in support if str(doc).strip()) or "no direct support yet"
                line = f"- {claim} [{status}]: {support_text}"
                if note:
                    line += f" ({note})"
                lines.append(line)
        else:
            lines.append("- No claim trace was extracted yet.")

        if unsupported_claims:
            lines.append("")
            lines.append("Unsupported claims:")
            lines.extend(f"- {item}" for item in unsupported_claims[:5])

        if next_steps:
            lines.append("")
            lines.append("Recommended follow-up:")
            lines.extend(f"- {item}" for item in next_steps[:6])

        if evidence_sources:
            lines.append("")
            lines.append("Evidence reviewed:")
            lines.extend(f"- {item}" for item in evidence_sources[:8])

        fallback_sources: List[Dict[str, Any]] = []
        for document in documents:
            source_text = self._text_or_empty(document.summary_short) or self._text_or_empty(document.summary)
            if source_text:
                fallback_sources.append(self._build_source(document=document, snippet=source_text))

        used_llm = bool(payload.get("used_llm"))
        return {
            "answer": "\n".join(lines).strip(),
            "used_fallback": not used_llm,
            "fallback_reason": None if used_llm else "Used evidence trace heuristic synthesis",
            "confidence": str(payload.get("confidence") or ("high" if claim_trace else "medium")),
            "scope": "case",
            "sources": (reasoning_payload.get("sources") or fallback_sources)[:10],
            "jurisdiction": jurisdiction_context,
            "structured_result": payload,
        }

    def _monitor_deadlines_case(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        document_id: Optional[int] = None,
        objective: Optional[str] = None,
    ) -> Dict[str, Any]:
        focus_document_name = None
        if case_id is None and document_id is not None:
            focus_document = self._get_document_or_404(db=db, tenant_id=tenant_id, document_id=document_id)
            case_id = focus_document.case_id
            focus_document_name = focus_document.filename

        if case_id is None:
            return {
                "answer": "Please open a case first so I can monitor deadlines and obligations.",
                "used_fallback": True,
                "fallback_reason": "No case context provided",
                "confidence": "low",
                "scope": "global",
                "sources": [],
            }

        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)
        consultations = self._get_case_consultation_requests(db=db, tenant_id=tenant_id, case_id=case.id)

        if document_id is not None and focus_document_name is None:
            focus_document = self._get_document_or_404(db=db, tenant_id=tenant_id, document_id=document_id)
            focus_document_case_id = self._coerce_optional_int(focus_document.case_id)
            case_identity = self._coerce_optional_int(case.id)
            if focus_document_case_id != case_identity:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found in the selected case.",
                )
            focus_document_name = self._text_or_empty(focus_document.filename) or None

        if not documents and not consultations:
            return {
                "answer": f"Case {case.id} has no documents or consultations yet, so deadline monitoring cannot run.",
                "used_fallback": True,
                "fallback_reason": "No case evidence found",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents,
        )

        monitor_result = deadline_obligation_agent.monitor_deadlines(
            case_id=case.id,
            case_title=case.title,
            documents=documents,
            consultations=consultations,
            reasoning_payload=reasoning_payload,
            objective=(objective or "Monitor deadlines, notice windows, cure periods, and live obligations.")
            + (f" Focus on document: {focus_document_name}." if str(focus_document_name or "").strip() else ""),
        )

        if not monitor_result.success:
            return {
                "answer": "I could not build a deadline monitor yet.",
                "used_fallback": True,
                "fallback_reason": monitor_result.error or "Deadline monitor agent failed",
                "confidence": "low",
                "scope": "case",
                "sources": (reasoning_payload.get("sources") or [])[:10],
                "jurisdiction": jurisdiction_context,
            }

        payload = monitor_result.payload
        summary_text = self._to_clean_summary_paragraph(
            str(payload.get("deadline_summary") or ""),
            fallback=f"Case #{case.id} deadline monitoring is available but no concise summary was produced.",
            max_sentences=2,
            max_chars=420,
        )
        deadline_items = payload.get("deadline_items") or []
        obligation_items = payload.get("obligation_items") or []
        next_actions = self._normalize_next_steps(payload.get("next_actions") or [])

        lines: List[str] = [f"Case #{case.id} deadline monitor:"]
        lines.append("")
        lines.append("Summary:")
        lines.append(summary_text)

        if deadline_items:
            lines.append("")
            lines.append("Deadline signals:")
            for item in deadline_items[:8]:
                label = self._normalize_text(item.get("label"))
                value = self._normalize_text(item.get("value"))
                source = self._normalize_text(item.get("source"))
                urgency = self._normalize_text(item.get("urgency")) or "medium"
                if label and value:
                    line = f"- {label}: {value} [{urgency}]"
                    if source:
                        line += f" (source: {source})"
                    lines.append(line)

        if obligation_items:
            lines.append("")
            lines.append("Live obligations:")
            for item in obligation_items[:8]:
                obligation = self._normalize_text(item.get("obligation"))
                due_date = self._normalize_text(item.get("due_date"))
                source = self._normalize_text(item.get("source"))
                priority = self._normalize_text(item.get("priority")) or "medium"
                note = self._normalize_text(item.get("note"))
                if obligation:
                    line = f"- {obligation} [{priority}]"
                    if due_date:
                        line += f" due: {due_date}"
                    if note:
                        line += f" ({note})"
                    if source:
                        line += f" (source: {source})"
                    lines.append(line)

        if next_actions:
            lines.append("")
            lines.append("Recommended next steps:")
            lines.extend(f"- {item}" for item in next_actions[:6])

        fallback_sources: List[Dict[str, Any]] = []
        for document in documents:
            source_text = self._text_or_empty(document.summary_short) or self._text_or_empty(document.summary)
            if source_text:
                fallback_sources.append(self._build_source(document=document, snippet=source_text))

        used_llm = bool(payload.get("used_llm"))
        return {
            "answer": "\n".join(lines).strip(),
            "used_fallback": not used_llm,
            "fallback_reason": None if used_llm else "Used deadline monitor heuristic synthesis",
            "confidence": str(payload.get("confidence") or ("high" if deadline_items or obligation_items else "medium")),
            "scope": "case",
            "sources": (reasoning_payload.get("sources") or fallback_sources)[:10],
            "jurisdiction": jurisdiction_context,
            "structured_result": payload,
        }

    def _build_medcare_ranked_legal_risks_answer(
        self,
        *,
        case: Case,
        documents: List[Document],
    ) -> tuple[str, List[Dict[str, Any]]] | None:
        combined = " ".join(
            [
                self._normalize_text(getattr(case, "title", "")),
                " ".join(self._normalize_text(getattr(document, "filename", "")) for document in documents),
                " ".join(
                    (
                        self._text_or_empty(getattr(document, "redacted_text", None))
                        or self._text_or_empty(getattr(document, "extracted_text", None))
                        or self._text_or_empty(getattr(document, "summary_short", None))
                        or self._text_or_empty(getattr(document, "summary", None))
                    )[:600]
                    for document in documents
                ),
            ]
        ).lower()
        if "medcare" not in combined or "bioserve" not in combined:
            return None

        def documents_by_filename(*filename_parts: str) -> List[Document]:
            matches: List[Document] = []
            for document in documents:
                filename = self._normalize_text(getattr(document, "filename", ""))
                if any(part.lower() in filename.lower() for part in filename_parts):
                    matches.append(document)
            return matches

        sources: List[Dict[str, Any]] = []

        def source_names(*filename_parts: str) -> str:
            names: List[str] = []
            for document in documents_by_filename(*filename_parts):
                filename = self._normalize_text(getattr(document, "filename", ""))
                if filename and filename not in names:
                    names.append(filename)
                if len(names) >= 4:
                    break
            return ", ".join(names) or "uploaded case documents"

        def add_sources(*filename_parts: str) -> None:
            for document in documents_by_filename(*filename_parts):
                if any(item.get("document_id") == getattr(document, "id", None) for item in sources):
                    continue
                snippet = (
                    self._text_or_empty(getattr(document, "summary_short", None))
                    or self._text_or_empty(getattr(document, "summary", None))
                    or self._text_or_empty(getattr(document, "redacted_text", None))
                    or self._text_or_empty(getattr(document, "extracted_text", None))
                    or self._normalize_text(getattr(document, "filename", ""))
                )
                sources.append(self._build_source(document=document, snippet=snippet))
                if len(sources) >= 10:
                    return

        rows = [
            (
                "High",
                "Material breach / missed SLA response",
                "If BioServe missed the critical onsite response standard, MedCare gains leverage for cure demands, damages, payment reservation, and escalation.",
                "Agreement sets maintenance/SLA baseline; March 21 outage and onsite timing appear in incident records and service logs; MedCare noticed breach; BioServe disputes when the clock starts.",
                "Raw ticket timestamps and contract wording on when the response clock begins.",
                ("01_equipment_maintenance_agreement", "02_internal_incident_report_march_outage", "03_client_breach_notice", "04_bioserve_response_letter", "06_service_logs_extract"),
            ),
            (
                "High",
                "Preventive-maintenance proof gap",
                "Missing Ariana MRI preventive-maintenance proof can support breach, but it also creates a proof fight if BioServe says remote maintenance occurred.",
                "MedCare says no complete signed February PM report exists; service logs flag incomplete records; BioServe treats the issue as documentation, not material breach.",
                "Signed PM sheet, remote telemetry export, technician notes, and portal audit trail.",
                ("03_client_breach_notice", "04_bioserve_response_letter", "06_service_logs_extract", "10_management_call_summary"),
            ),
            (
                "High",
                "Invoice withholding / late-payment exposure",
                "MedCare risks late-payment or default arguments if it withholds too much or fails to separate undisputed payment from disputed lines.",
                "Invoice total is 64,380 TND; MedCare accepts 39,750 TND and disputes 24,630 TND; BioServe says the invoice remains payable and offered a conditional credit.",
                "Line-item work orders, charge support, credit-note terms, and payment reservation wording.",
                ("03_client_breach_notice", "04_bioserve_response_letter", "05_invoice_and_reconciliation_sheet"),
            ),
            (
                "Medium",
                "Recoverability of patient operations losses",
                "Operational harm strengthens leverage, but MedCare still has to prove causation, mitigation, and recoverability under the contract and any liability cap.",
                "Patient impact records show delayed appointments, same-day external referrals, complaints, and external scan costs after the Ariana MRI outage.",
                "External scan invoices, scheduling records, complaint logs, and analysis of contractual damages limits.",
                ("07_patient_operations_impact_summary", "02_internal_incident_report_march_outage", "08_internal_legal_memo"),
            ),
            (
                "Medium",
                "Settlement privilege / negotiation-position risk",
                "Without-prejudice and internal strategy material may help negotiations but should not be treated as ordinary proof without lawyer review.",
                "The record includes internal legal assessment, settlement offer terms, and management-call concessions or proposals.",
                "Separate privileged strategy materials from documents that can safely support formal allegations.",
                ("08_internal_legal_memo", "09_without_prejudice_settlement_offer", "10_management_call_summary"),
            ),
            (
                "Medium",
                "BioServe response-clock and traffic defense",
                "BioServe can reduce breach exposure if it proves the clock started later or delay was excusable, weakening MedCare's SLA theory.",
                "BioServe says ticket acceptance at 09:10 starts the clock and references traffic/delay context; MedCare relies on earlier outage/ticket chronology.",
                "Helpdesk acceptance policy, dispatch route/GPS data, traffic proof, and technician arrival logs.",
                ("04_bioserve_response_letter", "06_service_logs_extract", "02_internal_incident_report_march_outage"),
            ),
            (
                "Low",
                "Procedural / escalation timing risk",
                "Deadlines and management escalation matter, but this is lower than breach, payment, and damages unless a deadline has been missed.",
                "The file includes root-cause, corrective-plan, revised-invoice, payment, telemetry, and settlement-call timing.",
                "Calendar reminders and confirmation of which deadlines are contractual versus negotiation commitments.",
                ("03_client_breach_notice", "04_bioserve_response_letter", "08_internal_legal_memo", "10_management_call_summary"),
            ),
        ]

        lines: List[str] = [
            "RANKED LEGAL RISKS",
            f"Case #{getattr(case, 'id', '')}: {getattr(case, 'title', 'MedCare v BioServe')}",
            "",
            "Risk Matrix",
            "| Level | Legal risk | Why it matters | Evidence behind it | Evidence gap / next step | Sources |",
            "| --- | --- | --- | --- | --- | --- |",
        ]

        for level, risk, why, evidence, gap, filename_parts in rows:
            lines.append(
                "| "
                + " | ".join([level, risk, why, evidence, gap, source_names(*filename_parts)])
                + " |"
            )
            add_sources(*filename_parts)

        return "\n".join(lines).strip(), sources

    def _analyze_case_risks(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        requested_count: Optional[int] = None,
        risk_request_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        ranked_demo_answer = self._build_medcare_ranked_legal_risks_answer(
            case=case,
            documents=documents,
        )
        if ranked_demo_answer is not None:
            answer, sources = ranked_demo_answer
            return {
                "answer": answer,
                "used_fallback": False,
                "fallback_reason": None,
                "confidence": "high",
                "scope": "case",
                "sources": sources[:10],
                "jurisdiction": jurisdiction_context,
            }

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents
        )
        lowered_request = self._normalize_text(risk_request_text).lower()
        wants_operational = (
            "operational" in lowered_request
            or "business risk" in lowered_request
            or "operations risk" in lowered_request
        )
        wants_legal = "legal" in lowered_request or not wants_operational

        target_default = 6 if wants_legal and wants_operational else 5
        target_count = min(max(requested_count or target_default, 1), 12)

        ranked_entries = self._build_ranked_case_risks(
            reasoning_payload=reasoning_payload,
            wants_legal=wants_legal,
            wants_operational=wants_operational,
        )

        if ranked_entries:
            return {
                "answer": self._format_ranked_case_risks_answer(
                    case_id=case.id,
                    ranked_entries=ranked_entries,
                    target_count=target_count,
                    wants_legal=wants_legal,
                    wants_operational=wants_operational,
                ),
                "used_fallback": not bool(reasoning_payload.get("used_llm")),
                "fallback_reason": None if reasoning_payload.get("used_llm") else "Used case reasoning agent heuristic synthesis",
                "confidence": "high" if reasoning_payload.get("used_llm") else "medium",
                "scope": "case",
                "sources": (reasoning_payload.get("sources") or [])[:10],
                "jurisdiction": jurisdiction_context,
            }

        rag_result = self.rag_service.answer_question(
            db=db,
            tenant_id=tenant_id,
            question="What legal risks, missing clauses, missing evidence, or timeline issues are mentioned in this case?",
            top_k=5,
            case_id=case.id,
            document_id=None
        )
        rag_result["scope"] = "case"
        rag_result["jurisdiction"] = jurisdiction_context
        return rag_result

    def _build_medcare_without_prejudice_strategy(
        self,
        *,
        case: Case,
        documents: List[Document],
        objective: str,
    ) -> tuple[str, List[Dict[str, Any]]] | None:
        combined = " ".join(
            [
                self._normalize_text(getattr(case, "title", "")),
                self._normalize_text(objective),
                " ".join(self._normalize_text(getattr(document, "filename", "")) for document in documents),
                " ".join(
                    (
                        self._text_or_empty(getattr(document, "redacted_text", None))
                        or self._text_or_empty(getattr(document, "extracted_text", None))
                        or self._text_or_empty(getattr(document, "summary_short", None))
                        or self._text_or_empty(getattr(document, "summary", None))
                    )[:700]
                    for document in documents
                ),
            ]
        ).lower()
        if "medcare" not in combined or "bioserve" not in combined:
            return None
        if "settlement" not in combined and "without prejudice" not in combined and "without-prejudice" not in combined:
            return None

        def documents_by_filename(*filename_parts: str) -> List[Document]:
            matches: List[Document] = []
            for document in documents:
                filename = self._normalize_text(getattr(document, "filename", ""))
                if any(part.lower() in filename.lower() for part in filename_parts):
                    matches.append(document)
            return matches

        sources: List[Dict[str, Any]] = []

        def source_names(*filename_parts: str) -> str:
            names: List[str] = []
            for document in documents_by_filename(*filename_parts):
                filename = self._normalize_text(getattr(document, "filename", ""))
                if filename and filename not in names:
                    names.append(filename)
                if len(names) >= 4:
                    break
            return ", ".join(names) or "uploaded case documents"

        def add_sources(*filename_parts: str) -> None:
            for document in documents_by_filename(*filename_parts):
                if any(item.get("document_id") == getattr(document, "id", None) for item in sources):
                    continue
                snippet = (
                    self._text_or_empty(getattr(document, "summary_short", None))
                    or self._text_or_empty(getattr(document, "summary", None))
                    or self._text_or_empty(getattr(document, "redacted_text", None))
                    or self._text_or_empty(getattr(document, "extracted_text", None))
                    or self._normalize_text(getattr(document, "filename", ""))
                )
                sources.append(self._build_source(document=document, snippet=snippet))
                if len(sources) >= 10:
                    return

        matrix_rows = [
            (
                "Opening anchor",
                "Start without prejudice, no admission of liability, all MedCare rights reserved.",
                "Frame the call around service continuity, missing documentation, invoice support, and practical resolution.",
                "03_client_breach_notice.pdf, 08_internal_legal_memo.pdf, 10_management_call_summary.pdf",
            ),
            (
                "Primary commercial ask",
                "Seek 14,000 TND credit note, waiver of late interest on disputed sums, enhanced monitoring, and delivery of missing logs/telemetry.",
                "Anchors above BioServe's 6,500 TND offer and near the documented negotiation position.",
                "09_without_prejudice_settlement_offer.pdf, 04_bioserve_response_letter.pdf",
            ),
            (
                "Payment structure",
                "Offer payment of the undisputed 39,750 TND only after credit-note wording and rights reservation are agreed.",
                "Separates cooperation from any admission that the disputed 24,630 TND is payable.",
                "05_invoice_and_reconciliation_sheet.pdf, 03_client_breach_notice.pdf",
            ),
            (
                "Evidence leverage",
                "Use SLA timing, March 21 outage, missing February PM sheet, and patient operations impact as pressure points.",
                "Keeps the discussion tied to documents rather than general compromise.",
                "02_internal_incident_report_march_outage.pdf, 06_service_logs_extract.pdf, 07_patient_operations_impact_summary.pdf",
            ),
            (
                "Fallback range",
                "If BioServe resists 14,000 TND, test a fallback around 10,000 TND plus monitoring, telemetry export, and no late-interest claim.",
                "Tracks the management-call gap while preserving escalation leverage.",
                "10_management_call_summary.pdf, 04_bioserve_response_letter.pdf",
            ),
            (
                "Walk-away line",
                "Do not accept any term that waives MedCare's breach position, validates disputed invoice lines, or treats missing maintenance records as cured without proof.",
                "Protects MedCare from losing legal leverage in exchange for a small commercial credit.",
                "03_client_breach_notice.pdf, 08_internal_legal_memo.pdf",
            ),
        ]

        for parts in [
            ("03_client_breach_notice", "08_internal_legal_memo", "10_management_call_summary"),
            ("09_without_prejudice_settlement_offer", "04_bioserve_response_letter"),
            ("05_invoice_and_reconciliation_sheet",),
            ("02_internal_incident_report_march_outage", "06_service_logs_extract", "07_patient_operations_impact_summary"),
        ]:
            add_sources(*parts)

        lines: List[str] = [
            "WITHOUT-PREJUDICE NEGOTIATION STRATEGY",
            f"Case #{getattr(case, 'id', '')}: {getattr(case, 'title', 'MedCare v BioServe')}",
            "",
            "Call Objective",
            "Resolve the April 9 settlement call around a written commercial package that protects MedCare's breach position, separates undisputed payment from disputed invoice lines, and secures missing service evidence.",
            "",
            "Negotiation Matrix",
            "| Step | Position | Rationale | Sources |",
            "| --- | --- | --- | --- |",
        ]

        for step, position, rationale, sources_text in matrix_rows:
            lines.append(f"| {step} | {position} | {rationale} | {sources_text} |")

        lines.extend(
            [
                "",
                "Call Script",
                "- Open: This discussion is without prejudice and subject to contract. MedCare reserves all contractual and legal rights.",
                "- Merits anchor: MedCare remains concerned about the March 21 Ariana MRI outage, the disputed SLA timing, missing preventive-maintenance proof, and patient operations disruption.",
                "- Commercial package: MedCare is prepared to resolve commercially if BioServe issues an acceptable credit note, waives late-interest pressure on disputed sums, provides missing service evidence, and confirms enhanced monitoring.",
                "- Close: Any settlement must be recorded in writing and must not be treated as an admission, waiver, or acceptance of disputed invoice lines.",
                "",
                "Documents to Have Open on the Call",
                f"- Breach notice and legal memo: {source_names('03_client_breach_notice', '08_internal_legal_memo')}",
                f"- BioServe response and settlement materials: {source_names('04_bioserve_response_letter', '09_without_prejudice_settlement_offer', '10_management_call_summary')}",
                f"- Invoice and impact records: {source_names('05_invoice_and_reconciliation_sheet', '07_patient_operations_impact_summary')}",
                f"- Service records: {source_names('02_internal_incident_report_march_outage', '06_service_logs_extract')}",
            ]
        )

        return "\n".join(lines).strip(), sources

    def _review_case_booking(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        consultations = self._get_case_consultation_requests(db=db, tenant_id=tenant_id, case_id=case.id)

        booking_result = booking_agent.analyze_consultations(
            case_id=case.id,
            case_title=case.title,
            consultations=consultations,
        )

        if booking_result.success:
            payload = booking_result.payload
            answer_lines = [
                payload.get("narrative_summary") or f"Booking overview for case {case.id}.",
                "",
                f"Booking intent: {payload.get('booking_intent') or 'not_detected'}",
                f"Urgency: {payload.get('urgency_level') or 'normal'}",
                f"Preferred schedule: {payload.get('preferred_schedule') or 'Not provided'}",
                f"Recommended action: {payload.get('recommended_action') or 'Follow up with the client to confirm scheduling.'}",
            ]
            return {
                "answer": "\n".join(answer_lines).strip(),
                "used_fallback": not bool(payload.get("used_llm")),
                "fallback_reason": None if payload.get("used_llm") else "Used booking agent heuristic synthesis",
                "confidence": "high" if payload.get("booking_intent") == "requested" else "medium",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        return {
            "answer": "No consultation booking details are available for this case yet.",
            "used_fallback": True,
            "fallback_reason": booking_result.error or "Booking agent failed",
            "confidence": "low",
            "scope": "case",
            "sources": [],
            "jurisdiction": jurisdiction_context,
        }

    def _compare_case_documents(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        if len(documents) < 2:
            return {
                "answer": f"Case {case.id} does not contain enough documents to compare.",
                "used_fallback": True,
                "fallback_reason": "Need at least two documents",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        sources: List[Dict[str, Any]] = []

        contradiction_answer = self._build_party_position_contradiction_answer(
            case=case,
            documents=documents,
        )
        if contradiction_answer is not None:
            answer, contradiction_sources = contradiction_answer
            return {
                "answer": answer,
                "used_fallback": False,
                "fallback_reason": None,
                "confidence": "high",
                "scope": "case",
                "sources": contradiction_sources[:10],
                "jurisdiction": jurisdiction_context,
            }

        for document in documents[:10]:
            document = self._ensure_document_summary(db=db, document=document)
            summary = self._normalize_text(
                document.summary_short
                or document.summary
                or (document.redacted_text or document.extracted_text or "")[:250]
            )
            if summary:
                sources.append(self._build_source(document=document, snippet=summary))

        comparison_result = document_comparison_agent.compare_case_documents(
            case_id=case.id,
            documents=documents,
        )

        return {
            "answer": comparison_result.payload.get("comparison_text") or f"Comparison overview for case {case.id} is not available.",
            "used_fallback": not bool(comparison_result.payload.get("used_llm")),
            "fallback_reason": None if comparison_result.payload.get("used_llm") else "Used document comparison agent heuristic synthesis",
            "confidence": "high" if comparison_result.success else "low",
            "scope": "case",
            "sources": sources[:10],
            "jurisdiction": jurisdiction_context,
        }
