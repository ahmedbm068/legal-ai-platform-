"""Step 3C — Drafting execution extracted from CopilotService.

Handles draft_client_email_case, draft_internal_email_case,
draft_partner_strategy_note_case, draft_negotiation_strategy,
and draft_contract_redline_case.

CopilotService keeps compatibility shims that delegate here.
All helper methods (_get_case_or_404, _summarize_case, etc.) are
accessed through the runtime (CopilotService) reference — no
circular import needed since we type it as Any.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.models.client import Client
from backend.models.user import User
from backend.services.ai.agents.contract_redline_agent import contract_redline_agent
from backend.services.ai.agents.drafting_agent import drafting_agent
from backend.services.ai.agents.negotiation_strategy_agent import negotiation_strategy_agent
from backend.services.ai.artifact_versioning_service import artifact_versioning_service
from backend.services.ai.jurisdiction_context_service import jurisdiction_context_service

_logger = logging.getLogger("copilot.drafting")


class CopilotDraftingExecutionService:
    """Dedicated execution service for all drafting / communication /
    strategy-generation tasks.

    Instantiated once in CopilotService.__init__ and called via the
    compatibility shims.  Receives a `runtime` parameter (CopilotService
    instance) so helper methods stay in one place without duplication.
    """

    def __init__(self, *, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    # ──────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────────────────────────────────

    def execute(
        self,
        *,
        intent: str,
        runtime: Any,  # CopilotService — typed Any to avoid circular import
        db: Optional[Session] = None,
        tenant_id: Optional[int] = None,
        user_id: Optional[int] = None,
        case_id: Optional[int] = None,
        document_id: Optional[int] = None,
        objective: Optional[str] = None,
        horizon_days: Optional[int] = None,
        use_external_research: bool = True,
        case_context: Optional[Dict[str, Any]] = None,
        case_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        _logger.debug(
            "[DRAFTING] drafting_execution_start | intent=%s case_id=%s",
            intent,
            case_id,
        )

        result = self._dispatch(
            intent=intent,
            runtime=runtime,
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            case_id=case_id,
            document_id=document_id,
            objective=objective,
            horizon_days=horizon_days,
            use_external_research=use_external_research,
            case_context=case_context,
            case_snapshot=case_snapshot,
        )

        duration_ms = (time.perf_counter() - started) * 1000.0
        _logger.debug(
            "[DRAFTING] drafting_execution_end | intent=%s confidence=%s duration_ms=%.0f",
            intent,
            result.get("confidence"),
            duration_ms,
        )
        return result

    # ──────────────────────────────────────────────────────────────────────────
    # Dispatcher
    # ──────────────────────────────────────────────────────────────────────────

    def _dispatch(
        self,
        *,
        intent: str,
        runtime: Any,
        db: Optional[Session],
        tenant_id: Optional[int],
        user_id: Optional[int],
        case_id: Optional[int],
        document_id: Optional[int],
        objective: Optional[str],
        horizon_days: Optional[int],
        use_external_research: bool,
        case_context: Optional[Dict[str, Any]],
        case_snapshot: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if intent == "draft_client_email_case":
            return self._draft_client_email(
                runtime=runtime,
                db=db,
                tenant_id=tenant_id,
                case_id=case_id,
                user_id=user_id,
            )
        if intent == "draft_internal_email_case":
            return self._draft_internal_email(
                runtime=runtime,
                db=db,
                tenant_id=tenant_id,
                case_id=case_id,
            )
        if intent == "draft_partner_strategy_note_case":
            return self._draft_partner_strategy_note(
                runtime=runtime,
                db=db,
                tenant_id=tenant_id,
                case_id=case_id,
            )
        if intent == "draft_negotiation_strategy":
            return self._draft_negotiation_strategy(
                runtime=runtime,
                db=db,
                tenant_id=tenant_id,
                case_id=case_id,
                objective=objective or "",
                horizon_days=horizon_days,
                use_external_research=use_external_research,
                case_context=case_context,
                case_snapshot=case_snapshot,
            )
        if intent == "draft_contract_redline_case":
            return self._draft_contract_redline(
                runtime=runtime,
                db=db,
                tenant_id=tenant_id,
                case_id=case_id,
                document_id=document_id,
                objective=objective,
            )
        # Unknown drafting intent — should not happen in normal flow
        _logger.warning("[DRAFTING] unknown intent passed to dispatch: %s", intent)
        return {
            "answer": "I could not determine the correct drafting action.",
            "used_fallback": True,
            "fallback_reason": f"Unknown drafting intent: {intent}",
            "confidence": "low",
            "scope": "global",
            "sources": [],
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Draft client email
    # ──────────────────────────────────────────────────────────────────────────

    def _draft_client_email(
        self,
        *,
        runtime: Any,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        case = runtime._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = runtime._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)
        client = db.query(Client).filter(
            Client.id == case.client_id,
            Client.tenant_id == tenant_id,
            Client.deleted_at.is_(None),
        ).first()
        lawyer = None
        if user_id is not None:
            lawyer = db.query(User).filter(
                User.id == user_id,
                User.tenant_id == tenant_id,
                User.deleted_at.is_(None),
            ).first()
        if lawyer is None:
            lawyer = db.query(User).filter(
                User.id == case.lawyer_id,
                User.tenant_id == tenant_id,
                User.deleted_at.is_(None),
            ).first()
        client_name = runtime._normalize_text(getattr(client, "name", None)) or "Client"
        lawyer_name = runtime._normalize_text(getattr(lawyer, "name", None)) or "Your Legal Team"

        demo_email = runtime._build_medcare_rights_preserving_client_email(
            case=case,
            documents=documents,
            client_name=client_name,
            lawyer_name=lawyer_name,
        )
        if demo_email is not None:
            draft_text, sources = demo_email
            try:
                artifact_versioning_service.create_version(
                    db=db,
                    tenant_id=tenant_id,
                    artifact_type="case_email",
                    content=draft_text,
                    case_id=case.id,
                    source_kind="agent_generation",
                    metadata={
                        "case_title": case.title,
                        "client_name": client_name,
                        "lawyer_name": lawyer_name,
                        "used_llm": False,
                        "template": "medcare_rights_preserving_client_update",
                    },
                    auto_select=True,
                )
            except Exception:
                pass

            artifact_context = runtime._build_artifact_context(
                db=db,
                tenant_id=tenant_id,
                artifact_type="case_email",
                case_id=case.id,
            )

            return {
                "answer": draft_text,
                "used_fallback": False,
                "fallback_reason": None,
                "confidence": "high",
                "scope": "case",
                "sources": sources[:10],
                "artifact": artifact_context,
                "jurisdiction": jurisdiction_context,
            }

        case_summary = runtime._summarize_case(db=db, tenant_id=tenant_id, case_id=case_id)

        draft_result = drafting_agent.draft_client_update_email(
            case_id=case.id,
            case_title=case.title,
            case_summary=case_summary["answer"],
            jurisdiction_country=case.jurisdiction_country,
            client_name=client_name,
            lawyer_name=lawyer_name,
        )
        draft_text = (draft_result.payload.get("email_body") or "").strip()

        if draft_text:
            try:
                artifact_versioning_service.create_version(
                    db=db,
                    tenant_id=tenant_id,
                    artifact_type="case_email",
                    content=draft_text,
                    case_id=case.id,
                    source_kind="agent_generation",
                    metadata={
                        "case_title": case.title,
                        "used_llm": bool(draft_result.payload.get("used_llm")),
                    },
                    auto_select=True,
                )
            except Exception:
                pass

        artifact_context = runtime._build_artifact_context(
            db=db,
            tenant_id=tenant_id,
            artifact_type="case_email",
            case_id=case.id,
        )

        return {
            "answer": draft_text,
            "used_fallback": not bool(draft_result.payload.get("used_llm")),
            "fallback_reason": None if draft_result.payload.get("used_llm") else "Used drafting agent template fallback",
            "confidence": "high" if draft_result.payload.get("used_llm") else "medium",
            "scope": "case",
            "sources": case_summary["sources"],
            "artifact": artifact_context,
            "jurisdiction": jurisdiction_context,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Draft internal email
    # ──────────────────────────────────────────────────────────────────────────

    def _draft_internal_email(
        self,
        *,
        runtime: Any,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
    ) -> Dict[str, Any]:
        case_summary = runtime._summarize_case(db=db, tenant_id=tenant_id, case_id=case_id)
        case = runtime._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        sources = case_summary.get("sources") or []
        document_names: List[str] = []
        for source in sources:
            filename = runtime._normalize_text(source.get("filename") if isinstance(source, dict) else "")
            if filename and filename not in document_names:
                document_names.append(filename)
        documents_text = ", ".join(document_names[:8]) if document_names else "the current case record"

        summary_text = str(case_summary.get("answer") or "").strip()
        concise_overview = runtime._extract_internal_overview_sentence(summary_text, case.title)

        internal_email_lines = [
            f"Subject: Internal update - case #{case.id} ({case.title})",
            "",
            "Dear Supervising Lawyer,",
            "",
            (
                f"Case #{case.id} is currently centered on {concise_overview}. Reviewed documents: {documents_text}. "
                "Recommended next step: keep a short response window, preserve the factual record, and decide whether a narrower without-prejudice proposal should follow."
            ),
            "",
            "Best regards,",
            "Legal AI Platform",
        ]

        artifact_context = runtime._build_artifact_context(
            db=db,
            tenant_id=tenant_id,
            artifact_type="case_email",
            case_id=case.id,
        )

        return {
            "answer": "\n".join(internal_email_lines).strip(),
            "used_fallback": True,
            "fallback_reason": "Used deterministic internal update template",
            "confidence": "high",
            "scope": "case",
            "sources": case_summary["sources"],
            "artifact": artifact_context,
            "jurisdiction": jurisdiction_context,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Draft partner strategy note
    # ──────────────────────────────────────────────────────────────────────────

    def _draft_partner_strategy_note(
        self,
        *,
        runtime: Any,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
    ) -> Dict[str, Any]:
        case_summary = runtime._summarize_case(db=db, tenant_id=tenant_id, case_id=case_id)
        case = runtime._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        sources = case_summary.get("sources") or []

        document_names: List[str] = []
        for source in sources:
            filename = runtime._normalize_text(source.get("filename") if isinstance(source, dict) else "")
            if filename and filename not in document_names:
                document_names.append(filename)

        documents_text = ", ".join(document_names[:8]) if document_names else "the current case record"
        summary_text = str(case_summary.get("answer") or "").strip()
        concise_overview = runtime._extract_internal_overview_sentence(summary_text, case.title)

        note_lines = [
            f"Partner-ready strategy note - case #{case.id} ({case.title})",
            "",
            (
                f"Case #{case.id} is best framed as {concise_overview}. Reviewed documents: {documents_text}. "
                "The current leverage sits in the facts, dates, and any unresolved documentary gaps, so the clean next move is to keep the ask narrow, preserve concessions, and hold a short without-prejudice fallback in reserve if the other side does not move."
            ),
        ]

        artifact_context = runtime._build_artifact_context(
            db=db,
            tenant_id=tenant_id,
            artifact_type="case_email",
            case_id=case.id,
        )

        return {
            "answer": "\n".join(note_lines).strip(),
            "used_fallback": True,
            "fallback_reason": "Used deterministic partner strategy note template",
            "confidence": "high",
            "scope": "case",
            "sources": case_summary["sources"],
            "artifact": artifact_context,
            "jurisdiction": jurisdiction_context,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Draft negotiation strategy
    # ──────────────────────────────────────────────────────────────────────────

    def _draft_negotiation_strategy(
        self,
        *,
        runtime: Any,
        db: Optional[Session],
        tenant_id: Optional[int],
        case_id: Optional[int],
        objective: str,
        horizon_days: Optional[int],
        use_external_research: bool,
        case_context: Optional[Dict[str, Any]],
        case_snapshot: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if db is not None and tenant_id is not None and case_id is not None:
            case = runtime._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
            jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
            documents = runtime._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)
            medcare_strategy = runtime._build_medcare_without_prejudice_strategy(
                case=case,
                documents=documents,
                objective=objective,
            )
            if medcare_strategy is not None:
                answer, sources = medcare_strategy
                return {
                    "answer": answer,
                    "used_fallback": False,
                    "fallback_reason": None,
                    "confidence": "high",
                    "scope": "case",
                    "sources": sources[:10],
                    "jurisdiction": jurisdiction_context,
                }

        strategy_result = negotiation_strategy_agent.draft_strategy(
            objective=objective,
            horizon_days=horizon_days,
            case_context=case_context,
            case_snapshot=case_snapshot,
            use_external_research=use_external_research,
        )

        payload = strategy_result.payload
        lines = ["Negotiation strategy:"]

        summary = runtime._normalize_text(payload.get("strategy_summary"))
        if summary:
            lines.append(summary)

        case_basis = payload.get("case_basis") or []
        if case_basis:
            lines.extend(["", "Case basis:"])
            lines.extend(f"- {item}" for item in case_basis[:5])

        opening_position = runtime._normalize_text(payload.get("opening_position"))
        if opening_position:
            lines.extend(["", "Opening position:", f"- {opening_position}"])

        target_outcome = runtime._normalize_text(payload.get("target_outcome"))
        if target_outcome:
            lines.extend(["", "Target outcome:", f"- {target_outcome}"])

        red_lines = payload.get("red_lines") or []
        if red_lines:
            lines.extend(["", "Red lines:"])
            lines.extend(f"- {item}" for item in red_lines[:5])

        concessions = payload.get("concessions") or []
        if concessions:
            lines.extend(["", "Concession ladder:"])
            lines.extend(f"- {item}" for item in concessions[:5])

        day_by_day_plan = payload.get("day_by_day_plan") or []
        if day_by_day_plan:
            lines.extend(["", f"{min(max(int(horizon_days or 15), 1), 30)}-day plan:"])
            lines.extend(f"- {item}" for item in day_by_day_plan[:10])

        fallback_options = payload.get("fallback_options") or []
        if fallback_options:
            lines.extend(["", "Fallback options:"])
            lines.extend(f"- {item}" for item in fallback_options[:5])

        web_references = payload.get("web_references") or []
        if web_references:
            lines.extend(["", "Web references:"])
            lines.extend(f"- {item}" for item in web_references[:3])

        closing_position = runtime._normalize_text(payload.get("closing_position"))
        if closing_position:
            lines.extend(["", "Close:", f"- {closing_position}"])

        answer_text = "\n".join(lines).strip()

        return {
            "answer": answer_text,
            "used_fallback": not bool(payload.get("used_llm")),
            "fallback_reason": None if payload.get("used_llm") else "Used negotiation strategy agent template fallback",
            "confidence": "high" if payload.get("used_llm") else "medium",
            "scope": "global",
            "sources": [],
            "structured_result": payload,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Draft contract redline
    # ──────────────────────────────────────────────────────────────────────────

    def _draft_contract_redline(
        self,
        *,
        runtime: Any,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        document_id: Optional[int] = None,
        objective: Optional[str] = None,
    ) -> Dict[str, Any]:
        if case_id is None and document_id is not None:
            focused_document = runtime._get_document_or_404(db=db, tenant_id=tenant_id, document_id=document_id)
            case_id = focused_document.case_id

        if case_id is None:
            return {
                "answer": "Please open a case first so I can draft a contract redline.",
                "used_fallback": True,
                "fallback_reason": "No case context provided",
                "confidence": "low",
                "scope": "global",
                "sources": [],
            }

        case = runtime._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        case_documents = runtime._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        if document_id is not None:
            focused_document = runtime._get_document_or_404(db=db, tenant_id=tenant_id, document_id=document_id)
            focused_document_case_id = runtime._coerce_optional_int(focused_document.case_id)
            case_identity = runtime._coerce_optional_int(case.id)
            if focused_document_case_id != case_identity:
                from fastapi import HTTPException, status as http_status
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail="Document not found in the selected case.",
                )
            focused_document_id = runtime._coerce_optional_int(focused_document.id)
            documents = [focused_document] + [
                document
                for document in case_documents
                if runtime._coerce_optional_int(document.id) != focused_document_id
            ]
            focus_document_name = runtime._text_or_empty(focused_document.filename) or None
        else:
            documents = case_documents
            focus_document_name = None

        if not documents:
            return {
                "answer": f"Case {case.id} has no documents yet, so contract redlining cannot run.",
                "used_fallback": True,
                "fallback_reason": "No case documents found",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        for document in documents:
            runtime._ensure_document_summary(db=db, document=document)

        redline_result = contract_redline_agent.draft_redline(
            case_id=case.id,
            case_title=case.title,
            documents=documents,
            objective=runtime._normalize_contract_redline_objective(
                objective or "Draft a practical contract redline with clause-level suggestions, fallback positions, and source documents."
            ),
            focus_document_name=focus_document_name,
        )

        if not redline_result.success:
            return {
                "answer": "I could not draft a contract redline yet.",
                "used_fallback": True,
                "fallback_reason": redline_result.error or "Contract redline agent failed",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        payload = redline_result.payload
        summary_text = runtime._to_clean_summary_paragraph(
            str(payload.get("redline_summary") or ""),
            fallback=f"Case #{case.id} contract redline guidance is available but no concise summary was produced.",
            max_sentences=2,
            max_chars=420,
        )
        clause_rows = payload.get("clause_rows") or []
        priority_changes = runtime._normalize_next_steps(payload.get("priority_changes") or [])
        fallback_positions = runtime._normalize_next_steps(payload.get("fallback_positions") or [])
        risk_notes = runtime._normalize_next_steps(payload.get("risk_notes") or [])
        target_document = runtime._normalize_text(payload.get("target_document"))

        lines: List[str] = [f"Case #{case.id} contract redline:"]
        lines.append("")
        lines.append("Summary:")
        lines.append(summary_text)

        if target_document:
            lines.extend(["", "Target document:", f"- {target_document}"])

        if clause_rows:
            lines.append("")
            lines.append("Clause-level edits:")
            for item in clause_rows[:8]:
                clause = runtime._normalize_text(item.get("clause"))
                issue = runtime._normalize_text(item.get("issue"))
                suggestion = runtime._normalize_text(item.get("suggestion"))
                fallback_position_text = runtime._normalize_text(item.get("fallback_position"))
                source_documents = item.get("source_documents") or []
                source_text = ", ".join(
                    runtime._normalize_text(doc) for doc in source_documents
                    if runtime._normalize_text(doc)
                )
                if clause:
                    line = f"- {clause}: {issue or 'Review required.'}"
                    if suggestion:
                        line += f" Suggested change: {suggestion}."
                    if fallback_position_text:
                        line += f" Fallback: {fallback_position_text}."
                    if source_text:
                        line += f" Sources: {source_text}."
                    lines.append(line)

        if priority_changes:
            lines.append("")
            lines.append("Priority changes:")
            lines.extend(f"- {item}" for item in priority_changes[:6])

        if risk_notes:
            lines.append("")
            lines.append("Risk notes:")
            lines.extend(f"- {item}" for item in risk_notes[:6])

        if fallback_positions:
            lines.append("")
            lines.append("Fallback positions:")
            lines.extend(f"- {item}" for item in fallback_positions[:5])

        fallback_sources: List[Dict[str, Any]] = []
        for document in documents:
            source_text = runtime._text_or_empty(document.summary_short) or runtime._text_or_empty(document.summary)
            if source_text:
                fallback_sources.append(runtime._build_source(document=document, snippet=source_text))

        used_llm = bool(payload.get("used_llm"))
        return {
            "answer": "\n".join(lines).strip(),
            "used_fallback": not used_llm,
            "fallback_reason": None if used_llm else "Used contract redline heuristic synthesis",
            "confidence": str(payload.get("confidence") or ("high" if clause_rows else "medium")),
            "scope": "case",
            "sources": fallback_sources[:10],
            "jurisdiction": jurisdiction_context,
            "structured_result": payload,
        }


__all__ = ["CopilotDraftingExecutionService"]
