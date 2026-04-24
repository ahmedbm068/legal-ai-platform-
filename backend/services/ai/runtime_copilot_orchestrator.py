from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.services.ai.agents.legal_workflow_agent_pack import legal_workflow_agent_pack
from backend.services.ai.agents.matter_classification_agent import matter_classification_agent
from backend.services.ai.agents.prompt_correction_agent import prompt_correction_agent
from backend.services.ai.agents.prompt_optimizer_agent import prompt_optimizer_agent
from backend.services.ai.ai_response_audit_service import ai_response_audit_service
from backend.services.ai.case_context_service import case_context_service
from backend.services.ai.case_snapshot_service import case_snapshot_service
from backend.services.ai.command_parsing_service import command_parsing_service
from backend.services.ai.copilot_memory_service import CopilotMemoryService, copilot_memory_service
from backend.services.ai.copilot_pipeline_contracts import (
    CopilotExecutionContext,
    CopilotPipelineRequest,
    PipelineStageRecord,
    PipelineStageStatus,
)
from backend.services.ai.copilot_service import CopilotService
from backend.services.ai.legal_trust_service import legal_trust_service


class RuntimeCopilotOrchestrator:
    OPTIMIZABLE_INTENTS = {
        "ask_document",
        "ask_case",
        "ask_global",
        "summarize_global",
    }
    LEGAL_ANALYSIS_INTENTS = {
        "ask_document",
        "ask_case",
        "ask_global",
        "summarize_case",
        "summarize_document",
        "summarize_global",
        "summarize_and_analyze_risks_case",
        "analyze_risks_case",
        "build_timeline_case",
        "compare_case_documents",
        "trace_case_evidence",
        "monitor_deadlines_case",
    }
    DRAFTING_INTENTS = {
        "draft_client_email_case",
        "draft_internal_email_case",
        "draft_partner_strategy_note_case",
        "draft_negotiation_strategy",
        "draft_contract_redline_case",
    }
    DOCUMENT_REVIEW_INTENTS = {
        "summarize_document",
        "compare_case_documents",
        "trace_case_evidence",
        "review_booking_case",
    }
    CLIENT_EXPLANATION_INTENTS = {
        "draft_client_email_case",
    }
    CIVIL_OBLIGATION_MARKERS = {
        "civil obligation",
        "obligation",
        "contract",
        "breach",
        "liability",
        "payment terms",
        "notice clause",
    }
    SUCCESSION_MARKERS = {
        "succession",
        "inheritance",
        "heritage",
        "heir",
        "testament",
        "estate",
    }
    INTERNATIONAL_PRIVATE_MARKERS = {
        "international private law",
        "droit international prive",
        "international prive",
        "conflit de lois",
        "conflict of laws",
        "exequatur",
        "foreign judgment",
    }
    LITIGATION_MEMO_MARKERS = {
        "litigation position",
        "position memo",
        "contentious",
        "argument map",
        "pleading",
    }
    ARTICLE_APPLICABILITY_MARKERS = {
        "article applicability",
        "which article applies",
        "applicable article",
        "article review",
    }
    DRAFTING_MARKERS = {
        "draft",
        "prepare memo",
        "write memo",
        "write email",
        "prepare email",
        "redline",
    }
    CLIENT_EXPLANATION_MARKERS = {
        "explain to client",
        "client explanation",
        "client-ready",
        "plain language",
    }
    DOCUMENT_REVIEW_MARKERS = {
        "review document",
        "document review",
        "compare documents",
        "extract clause",
        "scan clauses",
    }
    UNCERTAINTY_MARKERS = {
        "not sure",
        "unclear",
        "uncertain",
        "missing",
        "unknown",
        "insufficient",
        "ambiguous",
        "conflict",
    }
    GLOBAL_CONTRACT_SECTION_TITLES = (
        "Matter Understood",
        "Confirmed Facts",
        "Legal Issue",
        "Relevant Legal Basis",
        "Rule Summary",
        "Application to Known Facts",
        "Preliminary Application",
        "Missing Facts / Uncertainty",
        "Counter-Analysis / Alternative Interpretation",
        "Counter-Analysis",
        "Practical Next Steps",
        "Lawyer Review Note",
    )
    DEFAULT_LAWYER_REVIEW_NOTE = (
        "This output is legal-assistance material for professional review. "
        "Final legal judgment remains with the responsible lawyer."
    )

    def __init__(
        self,
        *,
        copilot_service: CopilotService,
        memory_service: CopilotMemoryService | None = None,
    ) -> None:
        self.copilot_service = copilot_service
        self.memory_service = memory_service or copilot_memory_service

    def run(
        self,
        *,
        db: Session,
        tenant_id: int,
        user_id: int | None,
        user_role: str,
        message: str,
        top_k: int = 5,
        use_external_research: bool = True,
        mode: str | None = None,
        legal_search_multilingual_output: bool = False,
        legal_search_code_scope: list[str] | None = None,
        reasoning_level: str | None = None,
        agent_mode: bool = False,
        workspace_case_id: int | None = None,
        workspace_document_id: int | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        save_attachments_to_case: bool = False,
        attachment_case_id: int | None = None,
        allowed_case_ids: list[int] | None = None,
        allowed_document_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        pipeline_request = CopilotPipelineRequest(
            message=message,
            top_k=top_k,
            use_external_research=use_external_research,
            mode=str(mode or "default"),
            legal_search_multilingual_output=legal_search_multilingual_output,
            legal_search_code_scope=list(legal_search_code_scope or []),
            reasoning_level=str(reasoning_level or "medium").strip().lower() or "medium",
            agent_mode=agent_mode,
            workspace_case_id=workspace_case_id,
            workspace_document_id=workspace_document_id,
            attachments_count=len(attachments or []),
            save_attachments_to_case=save_attachments_to_case,
            attachment_case_id=attachment_case_id,
        )
        stage_records: list[PipelineStageRecord] = []

        merged_history = self.memory_service.load_recent_history(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            case_id=workspace_case_id,
            document_id=workspace_document_id,
            conversation_history=conversation_history or [],
        )
        self._append_stage(
            stage_records,
            name="context_resolution",
            status=PipelineStageStatus.success,
            detail="Loaded and merged recent copilot history.",
            metadata={
                "history_items": len(merged_history),
                "workspace_case_id": workspace_case_id,
                "workspace_document_id": workspace_document_id,
            },
        )

        if attachments:
            self._append_stage(
                stage_records,
                name="attachment_resolution",
                status=PipelineStageStatus.skipped,
                detail="Chat image analysis is disabled. Use scanned-photo upload from the case workspace instead.",
                metadata={"attachment_count": len(attachments)},
            )
            return {
                "message": "Chat image analysis is disabled. Upload scanned photos from the case workspace to process document images.",
                "parsed_intent": "scan_document_images",
                "target_type": "case" if workspace_case_id else None,
                "target_id": workspace_case_id,
                "mode": str(mode or "default"),
                "agent_mode": False,
                "action_category": "analysis",
                "action_status": "unavailable",
                "permission_denied": False,
                "steps": [],
                "structured_result": {},
                "answer": "Chat image analysis is disabled. Upload scanned photos from the case workspace to process document images.",
                "used_fallback": True,
                "fallback_reason": "chat_image_analysis_disabled",
                "confidence": "low",
                "scope": "case" if workspace_case_id else "workspace",
                "sources": [],
                "citations": [],
                "cache": {"hit": False, "backend": "none"},
                "execution_trace": [record.model_dump(mode="json") for record in stage_records],
            }

        raw_parse = command_parsing_service.parse(pipeline_request.message)
        correction_result = prompt_correction_agent.correct_query(
            raw_query=pipeline_request.message,
            conversation_history=merged_history,
            allow_llm=False,
        )
        corrected_message = (
            str(correction_result.payload.get("corrected_query") or "").strip()
            if correction_result.success
            else ""
        ) or pipeline_request.message
        self._append_stage(
            stage_records,
            name="prompt_correction",
            status=PipelineStageStatus.success if correction_result.success else PipelineStageStatus.failed,
            detail=(
                "Applied prompt correction agent."
                if correction_result.success
                else "Prompt correction failed, fallback to original prompt."
            ),
            metadata={
                "changed": corrected_message != pipeline_request.message,
                "strategy": "heuristic_only",
                "warnings": correction_result.warnings,
            },
        )

        parsed = command_parsing_service.parse(corrected_message)
        intent = str(parsed.get("intent") or "ask_global").strip() or "ask_global"
        self._append_stage(
            stage_records,
            name="intent_detection",
            status=PipelineStageStatus.success,
            detail="Parsed command intent and target scope.",
            metadata={
                "intent": intent,
                "target_type": parsed.get("target_type"),
                "target_id": parsed.get("target_id"),
                "confidence": parsed.get("confidence"),
                "confidence_score": parsed.get("confidence_score"),
            },
        )

        parsed, arbitration_metadata = self._arbitrate_low_confidence_intent(
            raw_parse=raw_parse,
            parsed=parsed,
            workspace_case_id=workspace_case_id,
            workspace_document_id=workspace_document_id,
        )
        intent = str(parsed.get("intent") or "ask_global").strip() or "ask_global"
        self._append_stage(
            stage_records,
            name="low_confidence_intent_arbitration",
            status=PipelineStageStatus.success if arbitration_metadata.get("activated") else PipelineStageStatus.skipped,
            detail=(
                "Applied low-confidence arbitration to stabilize intent routing."
                if arbitration_metadata.get("activated")
                else "Low-confidence arbitration not required."
            ),
            metadata=arbitration_metadata,
        )

        optimized_message: str | None = None
        clean_query = str(parsed.get("clean_query") or corrected_message).strip()
        requested_mode = str(pipeline_request.mode or "default").strip().lower() or "default"
        if (
            requested_mode == "default"
            and not pipeline_request.agent_mode
            and not self.copilot_service._chat_mode_needs_rag(
                question=clean_query or corrected_message,
                intent=intent,
                case_id=parsed.get("case_id") if isinstance(parsed.get("case_id"), int) else workspace_case_id,
                document_id=(
                    parsed.get("document_id") if isinstance(parsed.get("document_id"), int) else workspace_document_id
                ),
            )
        ):
            chat_result = self.copilot_service._respond_in_chat_mode(
                question=clean_query or corrected_message,
                user_role=user_role,
                conversation_history=merged_history,
            )
            chat_result = self.copilot_service._strip_heavy_trust_diagnostics(chat_result)
            self._append_stage(
                stage_records,
                name="casual_chat_bypass",
                status=PipelineStageStatus.success,
                detail="Handled default Chat Mode directly without legal workflow, RAG, or trust enforcement.",
                metadata={"intent": intent, "mode": requested_mode},
            )
            structured_result = chat_result.pop("structured_result", {})
            action_status = str(chat_result.pop("action_status", "")).strip() or (
                "fallback" if chat_result.get("used_fallback") else "completed"
            )
            response_payload = {
                "message": pipeline_request.message,
                "parsed_intent": intent,
                "target_type": parsed.get("target_type"),
                "target_id": parsed.get("target_id"),
                "mode": "default",
                "reasoning_level": pipeline_request.reasoning_level,
                "agent_mode": False,
                "action_category": self.copilot_service.ACTION_CATEGORY_BY_INTENT.get(intent, "query"),
                "action_status": action_status,
                "permission_denied": bool(chat_result.pop("permission_denied", False)),
                "steps": [],
                "structured_result": structured_result if isinstance(structured_result, dict) else {},
                **chat_result,
            }
            response_payload["execution_trace"] = [record.model_dump(mode="json") for record in stage_records]
            self.memory_service.append_exchange(
                db=db,
                tenant_id=tenant_id,
                user_id=user_id,
                mode="default",
                parsed_intent=intent,
                user_message=pipeline_request.message,
                assistant_message=str(response_payload.get("answer") or ""),
                case_id=None,
                document_id=None,
                metadata=self._build_memory_metadata(response_payload),
            )
            return response_payload

        if intent in self.OPTIMIZABLE_INTENTS and clean_query:
            optimize_result = prompt_optimizer_agent.optimize_query(
                raw_query=clean_query,
                intent=intent,
                target_type=parsed.get("target_type"),
                target_id=parsed.get("target_id"),
                allow_llm=False,
            )
            optimized_candidate = (
                str(optimize_result.payload.get("optimized_query") or "").strip()
                if optimize_result.success
                else ""
            )
            optimized_message = optimized_candidate or clean_query
            self._append_stage(
                stage_records,
                name="prompt_optimization",
                status=PipelineStageStatus.success if optimize_result.success else PipelineStageStatus.failed,
                detail=(
                    "Optimized query for retrieval/generation."
                    if optimize_result.success
                    else "Prompt optimization failed, fallback to corrected query."
                ),
                metadata={
                    "optimized": bool(optimized_candidate),
                    "strategy": optimize_result.payload.get("strategy") if optimize_result.success else None,
                    "warnings": optimize_result.warnings,
                },
            )
        else:
            self._append_stage(
                stage_records,
                name="prompt_optimization",
                status=PipelineStageStatus.skipped,
                detail="Optimization skipped for non-retrieval intent.",
                metadata={"intent": intent},
            )

        selected_reasoning_level = pipeline_request.reasoning_level
        rollout_eligible, rollout_reason, rollout_bucket = self.copilot_service._is_high_reasoning_rollout_eligible(
            tenant_id=tenant_id,
        )
        high_reasoning_eligible = (
            selected_reasoning_level == "high"
            and bool(settings.ENABLE_HIGH_REASONING_MULTI_ANSWER)
            and pipeline_request.mode == "default"
            and intent in self.OPTIMIZABLE_INTENTS
            and rollout_eligible
        )
        self._append_stage(
            stage_records,
            name="high_reasoning_selector",
            status=PipelineStageStatus.success,
            detail=(
                "High reasoning multi-answer path is enabled for this request."
                if high_reasoning_eligible
                else "High reasoning multi-answer path not activated for this request."
            ),
            metadata={
                "reasoning_level": selected_reasoning_level,
                "feature_enabled": bool(settings.ENABLE_HIGH_REASONING_MULTI_ANSWER),
                "eligible": high_reasoning_eligible,
                "mode": pipeline_request.mode,
                "intent": intent,
                "rollout_eligible": rollout_eligible,
                "rollout_reason": rollout_reason,
                "rollout_bucket": rollout_bucket,
            },
        )

        execution_context = CopilotExecutionContext(
            corrected_message=corrected_message,
            optimized_message=optimized_message,
            parsed_intent=intent,
            target_type=parsed.get("target_type"),
            target_id=parsed.get("target_id"),
        )

        effective_case_id = parsed.get("case_id") if isinstance(parsed.get("case_id"), int) else workspace_case_id
        effective_document_id = (
            parsed.get("document_id") if isinstance(parsed.get("document_id"), int) else workspace_document_id
        )
        case_context = case_context_service.build_context(
            db=db,
            tenant_id=tenant_id,
            case_id=effective_case_id,
            document_id=effective_document_id,
        )
        context_case = case_context.get("case") if isinstance(case_context.get("case"), dict) else {}
        snapshot = case_snapshot_service.get_snapshot(
            db=db,
            tenant_id=tenant_id,
            case_id=context_case.get("id") if isinstance(context_case.get("id"), int) else effective_case_id,
        )
        snapshot_payload = case_snapshot_service.to_public_payload(snapshot)
        self._append_stage(
            stage_records,
            name="case_context_enrichment",
            status=PipelineStageStatus.success,
            detail="Built case-aware context for reasoning and memory continuity.",
            metadata={
                "scope": case_context.get("scope"),
                "case_id": context_case.get("id"),
                "document_count": context_case.get("document_count", 0),
                "risk_signal_count": len(case_context.get("risk_signals") or []),
                "timeline_events": len(case_context.get("timeline") or []),
            },
        )
        self._append_stage(
            stage_records,
            name="snapshot_load",
            status=PipelineStageStatus.success if snapshot_payload else PipelineStageStatus.skipped,
            detail="Loaded persisted case snapshot." if snapshot_payload else "No persisted case snapshot was available.",
            metadata={
                "case_snapshot_version": snapshot_payload.get("version") if isinstance(snapshot_payload, dict) else None,
            },
        )

        available_document_summaries = self._extract_available_document_summaries(
            case_context=case_context,
            snapshot_payload=snapshot_payload,
        )
        classification_result = matter_classification_agent.classify_matter(
            user_prompt=clean_query or corrected_message,
            case_context=case_context,
            available_document_summaries=available_document_summaries,
        )
        matter_classification = classification_result.payload if classification_result.success else {}
        self._append_stage(
            stage_records,
            name="matter_classification",
            status=PipelineStageStatus.success if classification_result.success else PipelineStageStatus.failed,
            detail=(
                "Classified legal matter before legal reasoning begins."
                if classification_result.success
                else "Matter classification failed; fallback to heuristic workflow planning."
            ),
            metadata={
                "matter_type": matter_classification.get("matter_type"),
                "subtopic": matter_classification.get("subtopic"),
                "likely_code_family": matter_classification.get("likely_code_family"),
                "task_type": matter_classification.get("task_type"),
                "legal_dimension": matter_classification.get("legal_dimension"),
                "classification_confidence": matter_classification.get("confidence"),
            },
        )

        workflow_plan = self._build_legal_workflow_plan(
            message=clean_query or corrected_message,
            parsed=parsed,
            case_context=case_context,
            requested_mode=pipeline_request.mode,
            legal_search_code_scope=pipeline_request.legal_search_code_scope,
            matter_classification=matter_classification,
        )
        self._append_stage(
            stage_records,
            name="workflow_planning",
            status=PipelineStageStatus.success,
            detail="Planned legal-assistance workflow before answer generation.",
            metadata={
                "workflow_template": workflow_plan.get("workflow_template"),
                "agent_sequence": workflow_plan.get("agent_sequence") or [],
                "workflow_kind": workflow_plan.get("workflow_kind"),
                "matter_type": workflow_plan.get("matter_type"),
                "trust_level": workflow_plan.get("trust_level"),
                "recommended_output_format": workflow_plan.get("recommended_output_format"),
                "source_needs": workflow_plan.get("source_needs") or [],
            },
        )

        parsed, routing_metadata = self._apply_workflow_routing(
            parsed=parsed,
            workflow_plan=workflow_plan,
            workspace_case_id=workspace_case_id,
            workspace_document_id=workspace_document_id,
        )
        intent = str(parsed.get("intent") or intent).strip() or intent
        effective_mode = self._resolve_effective_mode(
            requested_mode=pipeline_request.mode,
            workflow_plan=workflow_plan,
        )
        use_trust_engine = self.copilot_service._should_use_trust_engine(
            normalized_mode=effective_mode,
            intent=intent,
            agent_mode=pipeline_request.agent_mode,
        )
        self._append_stage(
            stage_records,
            name="workflow_routing",
            status=PipelineStageStatus.success,
            detail="Applied workflow-aware routing before copilot execution.",
            metadata={
                "requested_mode": pipeline_request.mode,
                "effective_mode": effective_mode,
                "use_trust_engine": use_trust_engine,
                **routing_metadata,
            },
        )

        execution_context = CopilotExecutionContext(
            corrected_message=corrected_message,
            optimized_message=optimized_message,
            parsed_intent=intent,
            target_type=parsed.get("target_type"),
            target_id=parsed.get("target_id"),
            planned_matter_type=str(workflow_plan.get("matter_type") or "").strip() or None,
            planned_workflow=str(workflow_plan.get("workflow_kind") or "").strip() or None,
            planned_output_format=str(workflow_plan.get("recommended_output_format") or "").strip() or None,
            requested_user_goal=str(workflow_plan.get("user_goal") or "").strip() or None,
        )

        result = self.copilot_service.handle_message(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role=user_role,
            message=pipeline_request.message,
            top_k=pipeline_request.top_k,
            use_external_research=pipeline_request.use_external_research,
            mode=effective_mode,
            legal_search_multilingual_output=pipeline_request.legal_search_multilingual_output,
            legal_search_code_scope=pipeline_request.legal_search_code_scope,
            reasoning_level=pipeline_request.reasoning_level,
            agent_mode=pipeline_request.agent_mode,
            workspace_case_id=workspace_case_id,
            workspace_document_id=workspace_document_id,
            conversation_history=merged_history,
            preparsed_command=parsed,
            skip_autocorrect=True,
            preoptimized_query=optimized_message,
            allowed_case_ids=allowed_case_ids,
            allowed_document_ids=allowed_document_ids,
            case_context=case_context,
            case_snapshot=snapshot_payload,
        )

        global_output_contract = self._build_global_output_contract(
            result=result,
            workflow_plan=workflow_plan,
            case_context=case_context,
            parsed_intent=intent,
            user_query=pipeline_request.message,
        )
        if use_trust_engine:
            self._apply_global_output_contract(
                result=result,
                output_contract=global_output_contract,
            )

        if not use_trust_engine:
            legal_agent_pack_payload = {
                "workflow_template": workflow_plan.get("workflow_kind"),
                "agent_sequence": [],
                "disabled": True,
                "reason": "Trust/legal workflow diagnostics skipped for this mode.",
                "verification": {"verification_status": "not_run_mode_not_trust_eligible"},
            }
        elif settings.LEGAL_AGENT_KILL_SWITCH:
            legal_agent_pack_payload = {
                "workflow_template": workflow_plan.get("workflow_kind"),
                "agent_sequence": [],
                "disabled": True,
                "reason": "LEGAL_AGENT_KILL_SWITCH is enabled.",
                "verification": {"verification_status": "unverified"},
            }
        else:
            legal_agent_pack_payload = legal_workflow_agent_pack.run(
                workflow_plan=workflow_plan,
                output_contract=global_output_contract,
                case_context=case_context,
                result=result,
            )
        if use_trust_engine:
            global_output_contract = self._enrich_global_output_contract_with_agent_pack(
                output_contract=global_output_contract,
                agent_pack_payload=legal_agent_pack_payload,
            )
            self._apply_global_output_contract(
                result=result,
                output_contract=global_output_contract,
            )
            self._apply_legal_workflow_agent_pack(
                result=result,
                agent_pack_payload=legal_agent_pack_payload,
            )
            self._apply_composed_legal_answer_if_needed(
                result=result,
                workflow_plan=workflow_plan,
                effective_mode=effective_mode,
                agent_pack_payload=legal_agent_pack_payload,
            )

        if settings.LEGAL_TRUST_ENGINE_ENABLED and use_trust_engine:
            trust_result = legal_trust_service.enforce_response(
                result=result,
                output_contract=global_output_contract,
                case_context=case_context,
                force_structured_answer=(
                    settings.LEGAL_TRUST_STRICT_OUTPUTS
                    and self._should_force_legal_trust_answer(
                        parsed_intent=intent,
                        workflow_plan=workflow_plan,
                        effective_mode=effective_mode,
                    )
                ),
            )
            result["answer"] = trust_result.answer
            result["trust_panel"] = trust_result.trust_panel
            self._apply_trust_panel(
                result=result,
                trust_panel=trust_result.trust_panel,
                validation=trust_result.validation,
                claim_validation=trust_result.claim_validation,
                contradiction_detection=trust_result.contradiction_detection,
            )
            result = self.copilot_service._normalize_trust_state(result)
            self._append_stage(
                stage_records,
                name="legal_trust_engine",
                status=PipelineStageStatus.success,
                detail="Enforced legal trust panel, claim validation, contradiction checks, and output contract validation.",
                metadata={
                    "is_valid": trust_result.validation.get("is_valid"),
                    "citation_coverage": (trust_result.trust_panel.get("metrics") or {}).get("citation_coverage"),
                    "hallucination_rate": (trust_result.trust_panel.get("metrics") or {}).get("hallucination_rate"),
                    "contradiction_count": (trust_result.trust_panel.get("metrics") or {}).get("contradiction_count"),
                },
            )
        elif settings.LEGAL_TRUST_ENGINE_ENABLED:
            result = self.copilot_service._strip_trust_artifacts(result)
            self._append_stage(
                stage_records,
                name="legal_trust_engine",
                status=PipelineStageStatus.skipped,
                detail="Trust engine skipped because the selected mode is not trust-eligible.",
                metadata={"mode": effective_mode, "intent": intent},
            )

        self._append_stage(
            stage_records,
            name="copilot_execution",
            status=PipelineStageStatus.success,
            detail="Executed copilot service with orchestration context.",
            metadata={
                "result_intent": result.get("parsed_intent"),
                "mode": result.get("mode"),
                "used_fallback": bool(result.get("used_fallback")),
            },
        )
        self._append_stage(
            stage_records,
            name="legal_workflow_agents",
            status=PipelineStageStatus.success,
            detail="Executed structured legal workflow agents and final composer.",
            metadata={
                "workflow_template": legal_agent_pack_payload.get("workflow_template"),
                "agent_sequence": legal_agent_pack_payload.get("agent_sequence") or [],
                "verification_status": (
                    (legal_agent_pack_payload.get("verification") or {}).get("verification_status")
                    if isinstance(legal_agent_pack_payload.get("verification"), dict)
                    else None
                ),
            },
        )
        self._append_stage(
            stage_records,
            name="global_output_contract",
            status=PipelineStageStatus.success,
            detail="Normalized response to the shared legal output contract.",
            metadata={
                "matter_type": global_output_contract.get("matter_type"),
                "verification_status": global_output_contract.get("verification_status"),
                "confidence": global_output_contract.get("confidence"),
                "relevant_source_count": len(global_output_contract.get("relevant_sources") or []),
                "missing_fact_count": len(global_output_contract.get("missing_facts") or []),
            },
        )

        resolved_case_id, resolved_document_id = self._resolve_memory_scope(
            response_payload=result,
            fallback_case_id=workspace_case_id,
            fallback_document_id=workspace_document_id,
        )
        self.memory_service.append_exchange(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            mode=str(result.get("mode") or mode or "default"),
            parsed_intent=(str(execution_context.parsed_intent or result.get("parsed_intent") or "").strip() or None),
            user_message=pipeline_request.message,
            assistant_message=str(result.get("answer") or ""),
            case_id=resolved_case_id,
            document_id=resolved_document_id,
            metadata=self._build_memory_metadata(result),
        )
        structured_result = result.get("structured_result") if isinstance(result.get("structured_result"), dict) else {}
        ai_response_audit_service.record(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            endpoint="/ai/copilot",
            question=pipeline_request.message,
            answer=str(result.get("answer") or ""),
            parsed_intent=(str(execution_context.parsed_intent or result.get("parsed_intent") or "").strip() or None),
            case_id=resolved_case_id,
            document_id=resolved_document_id,
            sources=result.get("sources") if isinstance(result.get("sources"), list) else [],
            trust_panel=result.get("trust_panel") if isinstance(result.get("trust_panel"), dict) else structured_result.get("trust_panel"),
            validation=structured_result.get("trust_validation") if isinstance(structured_result.get("trust_validation"), dict) else {},
            metadata={
                "mode": result.get("mode"),
                "confidence": result.get("confidence"),
                "workflow_kind": workflow_plan.get("workflow_kind"),
                "case_snapshot_version": result.get("case_snapshot_version"),
            },
        )
        self._append_stage(
            stage_records,
            name="memory_persistence",
            status=PipelineStageStatus.success,
            detail="Persisted user/assistant exchange into case memory.",
            metadata={"case_id": resolved_case_id, "document_id": resolved_document_id},
        )

        self._inject_pipeline_metadata(
            result=result,
            request=pipeline_request,
            stages=stage_records,
            execution_context=execution_context,
            case_context=case_context,
            resolved_case_id=resolved_case_id,
            resolved_document_id=resolved_document_id,
            snapshot_payload=snapshot_payload,
            workflow_plan=workflow_plan,
            effective_mode=effective_mode,
        )
        return result

    @staticmethod
    def _resolve_memory_scope(
        *,
        response_payload: dict[str, Any],
        fallback_case_id: int | None,
        fallback_document_id: int | None,
    ) -> tuple[int | None, int | None]:
        target_type = str(response_payload.get("target_type") or "").strip().lower()
        target_id = response_payload.get("target_id")
        case_id = fallback_case_id
        document_id = fallback_document_id
        if target_type == "case" and isinstance(target_id, int):
            case_id = target_id
            document_id = None
        elif target_type == "document" and isinstance(target_id, int):
            document_id = target_id
        return case_id, document_id

    @staticmethod
    def _build_memory_metadata(result: dict[str, Any]) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        for key in (
            "confidence",
            "scope",
            "action_category",
            "action_status",
            "fallback_reason",
            "permission_denied",
            "review_record_id",
            "saved_asset_ids",
        ):
            value = result.get(key)
            if value is not None:
                metadata[key] = value

        structured_result = result.get("structured_result")
        if isinstance(structured_result, dict):
            contract = structured_result.get("global_output_contract")
            if isinstance(contract, dict):
                verification_status = str(contract.get("verification_status") or "").strip()
                matter_type = str(contract.get("matter_type") or "").strip()
                if verification_status:
                    metadata["verification_status"] = verification_status
                if matter_type:
                    metadata["matter_type"] = matter_type
        return metadata

    @staticmethod
    def _append_stage(
        stages: list[PipelineStageRecord],
        *,
        name: str,
        status: PipelineStageStatus,
        detail: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        stages.append(
            PipelineStageRecord(
                name=name,
                status=status,
                detail=detail,
                metadata=metadata or {},
            )
        )

    @staticmethod
    def _inject_pipeline_metadata(
        *,
        result: dict[str, Any],
        request: CopilotPipelineRequest,
        stages: list[PipelineStageRecord],
        execution_context: CopilotExecutionContext,
        case_context: dict[str, Any],
        resolved_case_id: int | None,
        resolved_document_id: int | None,
        snapshot_payload: dict[str, Any] | None,
        workflow_plan: dict[str, Any],
        effective_mode: str,
    ) -> None:
        structured_result = result.get("structured_result")
        if not isinstance(structured_result, dict):
            structured_result = {}

        structured_result["pipeline"] = {
            "entrypoint": "runtime_copilot_orchestrator",
            "version": "v2",
            "request": {
                "top_k": request.top_k,
                "mode": request.mode,
                "effective_mode": effective_mode,
                "reasoning_level": request.reasoning_level,
                "agent_mode": request.agent_mode,
                "workspace_case_id": request.workspace_case_id,
                "workspace_document_id": request.workspace_document_id,
                "attachments_count": request.attachments_count,
            },
            "execution_context": execution_context.model_dump(mode="json"),
            "workflow_plan": workflow_plan,
            "case_context": case_context,
            "resolved_case_id": resolved_case_id,
            "resolved_document_id": resolved_document_id,
        }
        if snapshot_payload:
            structured_result["pipeline"]["snapshot"] = snapshot_payload

        result["structured_result"] = structured_result
        result["execution_trace"] = [record.model_dump(mode="json") for record in stages]
        if snapshot_payload and result.get("case_snapshot_version") is None:
            result["case_snapshot_version"] = snapshot_payload.get("version")

    @classmethod
    def _should_force_legal_trust_answer(
        cls,
        *,
        parsed_intent: str,
        workflow_plan: dict[str, Any],
        effective_mode: str,
    ) -> bool:
        workflow_kind = str(workflow_plan.get("workflow_kind") or "").strip()
        if effective_mode == "legal_search":
            return True
        if parsed_intent in cls.LEGAL_ANALYSIS_INTENTS:
            return True
        return workflow_kind in {"legal_analysis", "document_review", "client_explanation"}

    @staticmethod
    def _apply_trust_panel(
        *,
        result: dict[str, Any],
        trust_panel: dict[str, Any],
        validation: dict[str, Any],
        claim_validation: dict[str, Any],
        contradiction_detection: dict[str, Any],
    ) -> None:
        structured_result = result.get("structured_result")
        if not isinstance(structured_result, dict):
            structured_result = {}
        structured_result["trust_panel"] = trust_panel
        structured_result["trust_validation"] = validation
        structured_result["claim_validation"] = claim_validation
        structured_result["contradiction_detection"] = contradiction_detection
        result["structured_result"] = structured_result

    @staticmethod
    def _extract_available_document_summaries(
        *,
        case_context: dict[str, Any],
        snapshot_payload: dict[str, Any] | None,
    ) -> list[str]:
        summaries: list[str] = []

        timeline_rows = case_context.get("timeline") or []
        if isinstance(timeline_rows, list):
            for item in timeline_rows:
                if not isinstance(item, dict):
                    continue
                if str(item.get("event_type") or "").strip().lower() != "document_uploaded":
                    continue
                label = str(item.get("label") or "").strip()
                if label and label not in summaries:
                    summaries.append(label)

        risk_signals = case_context.get("risk_signals") or []
        if isinstance(risk_signals, list):
            for signal in risk_signals:
                text = str(signal or "").strip()
                if text and text not in summaries:
                    summaries.append(text)

        if isinstance(snapshot_payload, dict):
            summary_text = str(snapshot_payload.get("summary_text") or "").strip()
            if summary_text and summary_text not in summaries:
                summaries.append(summary_text)

            reasoning = snapshot_payload.get("reasoning")
            if isinstance(reasoning, dict):
                for key in ("overview", "narrative_summary", "main_issues"):
                    value = reasoning.get(key)
                    if isinstance(value, str):
                        text = value.strip()
                        if text and text not in summaries:
                            summaries.append(text)
                    elif isinstance(value, list):
                        for item in value:
                            text = str(item or "").strip()
                            if text and text not in summaries:
                                summaries.append(text)

            citations = snapshot_payload.get("citations")
            if isinstance(citations, list):
                for item in citations:
                    if not isinstance(item, dict):
                        continue
                    label = str(item.get("label") or "").strip()
                    snippet = str(item.get("snippet") or "").strip()
                    text = f"{label}: {snippet}".strip(": ")
                    if text and text not in summaries:
                        summaries.append(text)

        return summaries[:24]

    @staticmethod
    def _apply_global_output_contract(*, result: dict[str, Any], output_contract: dict[str, Any]) -> None:
        structured_result = result.get("structured_result")
        if not isinstance(structured_result, dict):
            structured_result = {}
        structured_result["global_output_contract"] = output_contract
        result["structured_result"] = structured_result

    @staticmethod
    def _enrich_global_output_contract_with_agent_pack(
        *,
        output_contract: dict[str, Any],
        agent_pack_payload: dict[str, Any],
    ) -> dict[str, Any]:
        enriched = dict(output_contract)
        verification_payload = agent_pack_payload.get("verification")
        if isinstance(verification_payload, dict):
            evidence_strength = verification_payload.get("evidence_strength")
            if isinstance(evidence_strength, dict):
                enriched["evidence_strength"] = evidence_strength
            verification_status = verification_payload.get("verification_status")
            if verification_status:
                enriched["verification_status"] = str(verification_status).strip()

        position_strength = agent_pack_payload.get("position_strength")
        if isinstance(position_strength, dict):
            enriched["position_strength"] = position_strength

        recommended_strategy = agent_pack_payload.get("recommended_strategy") or agent_pack_payload.get("strategy")
        if isinstance(recommended_strategy, dict):
            enriched["recommended_strategy"] = recommended_strategy

        contradiction_analysis = agent_pack_payload.get("contradictions")
        if isinstance(contradiction_analysis, list):
            normalized_contradictions = RuntimeCopilotOrchestrator._ensure_contradiction_rows(
                contradiction_analysis,
                max_items=12,
            )
            enriched["contradiction_analysis"] = normalized_contradictions
            enriched["contradictions"] = normalized_contradictions

        timeline_legal_impact = agent_pack_payload.get("timeline_legal_impact")
        if isinstance(timeline_legal_impact, list):
            enriched["timeline_legal_impact"] = timeline_legal_impact

        client_risk_summary = agent_pack_payload.get("client_risk_summary")
        if isinstance(client_risk_summary, dict):
            enriched["client_risk_summary"] = client_risk_summary

        feedback_loop = agent_pack_payload.get("feedback_loop")
        if isinstance(feedback_loop, dict):
            enriched["feedback_loop"] = feedback_loop

        return enriched

    @staticmethod
    def _apply_legal_workflow_agent_pack(*, result: dict[str, Any], agent_pack_payload: dict[str, Any]) -> None:
        structured_result = result.get("structured_result")
        if not isinstance(structured_result, dict):
            structured_result = {}
        structured_result["legal_workflow_agents"] = agent_pack_payload
        result["structured_result"] = structured_result

    @staticmethod
    def _apply_composed_legal_answer_if_needed(
        *,
        result: dict[str, Any],
        workflow_plan: dict[str, Any],
        effective_mode: str,
        agent_pack_payload: dict[str, Any],
    ) -> None:
        workflow_kind = str(workflow_plan.get("workflow_kind") or "").strip()
        if workflow_kind != "legal_analysis" and effective_mode != "legal_search":
            return
        composer_payload = agent_pack_payload.get("final_output_composer")
        if not isinstance(composer_payload, dict):
            return
        composed_answer = str(composer_payload.get("answer") or "").strip()
        if not composed_answer:
            return
        original_answer = str(result.get("answer") or "").strip()
        structured_result = result.get("structured_result")
        if not isinstance(structured_result, dict):
            structured_result = {}
        if original_answer:
            structured_result["original_answer_before_final_composer"] = original_answer
        structured_result["final_answer_source"] = "final_legal_output_composer"
        result["structured_result"] = structured_result
        result["answer"] = composed_answer

    @staticmethod
    def _normalize_confidence_label(value: Any) -> str:
        token = str(value or "").strip().lower()
        if token == "high":
            return "high"
        if token == "medium":
            return "medium"
        return "low"

    @staticmethod
    def _normalize_verification_status(value: Any) -> str:
        token = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if token in {
            "verified",
            "source_grounded_article_references_present",
            "source_grounded_verified",
        }:
            return "verified"
        if token in {
            "partial",
            "partially_verified",
            "source_grounded_reference_partial",
            "source_grounded_partial",
        }:
            return "partial"
        if token in {
            "unverified",
            "not_verified_no_direct_source",
            "not_verified_access_denied",
            "not_verified_document_scope_failure",
            "not_verified_case_scope_failure",
        }:
            return "unverified"
        return "unverified"

    @staticmethod
    def _ensure_string_list(values: Any, *, max_items: int = 12) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized: list[str] = []
        for item in values:
            cleaned = str(item or "").strip()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
            if len(normalized) >= max_items:
                break
        return normalized

    @classmethod
    def _ensure_contradiction_rows(cls, values: Any, *, max_items: int = 12) -> list[dict[str, Any]]:
        if not isinstance(values, list):
            return []
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in values:
            if isinstance(item, str):
                description = item.strip()
                impact = "medium"
                sources: list[str] = []
            elif isinstance(item, dict):
                description = str(item.get("description") or "").strip()
                impact_token = str(item.get("impact") or "medium").strip().lower()
                impact = impact_token if impact_token in {"low", "medium", "high"} else "medium"
                sources = cls._ensure_string_list(item.get("sources"), max_items=5)
            else:
                continue
            if not description:
                continue
            key = f"{description}|{impact}|{','.join(sources)}".lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append({"description": description, "impact": impact, "sources": sources})
            if len(rows) >= max_items:
                break
        return rows

    @classmethod
    def _extract_section_text(cls, *, answer: str, section_titles: tuple[str, ...]) -> str:
        text = str(answer or "")
        if not text.strip():
            return ""

        section_match = None
        for title in section_titles:
            pattern = re.compile(
                rf"(?im)^\s*(?:\d+\.\s*)?(?:\*+\s*)?{re.escape(title)}(?:\s*\*+)?\s*$"
            )
            candidate = pattern.search(text)
            if candidate and (section_match is None or candidate.start() < section_match.start()):
                section_match = candidate

        if section_match is None:
            return ""

        start = section_match.end()
        end = len(text)
        for title in cls.GLOBAL_CONTRACT_SECTION_TITLES:
            pattern = re.compile(
                rf"(?im)^\s*(?:\d+\.\s*)?(?:\*+\s*)?{re.escape(title)}(?:\s*\*+)?\s*$"
            )
            candidate = pattern.search(text, pos=start)
            if candidate and candidate.start() < end:
                end = candidate.start()

        return text[start:end].strip()

    @staticmethod
    def _extract_list_from_block(*, block: str, max_items: int = 8) -> list[str]:
        rows = [line.strip() for line in str(block or "").splitlines() if line.strip()]
        if len(rows) <= 1 and ";" in str(block or ""):
            rows = [item.strip() for item in str(block).split(";") if item.strip()]

        extracted: list[str] = []
        for row in rows:
            cleaned = re.sub(r"^(?:[-*\u2022]|\d+[\).])\s*", "", row).strip()
            if not cleaned:
                continue
            if cleaned not in extracted:
                extracted.append(cleaned)
            if len(extracted) >= max_items:
                break
        return extracted

    @classmethod
    def _extract_answer_derived_fields(cls, *, answer: str) -> dict[str, Any]:
        legal_issue = cls._extract_section_text(answer=answer, section_titles=("Legal Issue",))
        rule_summary = cls._extract_section_text(answer=answer, section_titles=("Rule Summary",))
        application = cls._extract_section_text(
            answer=answer,
            section_titles=("Application to Known Facts", "Preliminary Application"),
        )
        counter_analysis = cls._extract_section_text(
            answer=answer,
            section_titles=("Counter-Analysis / Alternative Interpretation", "Counter-Analysis"),
        )
        confirmed_block = cls._extract_section_text(answer=answer, section_titles=("Confirmed Facts",))
        missing_block = cls._extract_section_text(
            answer=answer,
            section_titles=("Missing Facts / Uncertainty",),
        )
        next_steps_block = cls._extract_section_text(
            answer=answer,
            section_titles=("Practical Next Steps",),
        )

        inferred_facts: list[str] = []
        for line in confirmed_block.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            if "inferred facts:" in candidate.lower():
                inferred = candidate.split(":", 1)[1].strip() if ":" in candidate else ""
                if inferred:
                    inferred_facts.append(inferred)

        missing_from_confirmed: list[str] = []
        for line in confirmed_block.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            if "missing facts:" in candidate.lower():
                missing = candidate.split(":", 1)[1].strip() if ":" in candidate else ""
                if missing:
                    missing_from_confirmed.append(missing)

        return {
            "legal_issue": legal_issue,
            "governing_rule": rule_summary,
            "application": application,
            "counter_analysis": counter_analysis,
            "inferred_facts": inferred_facts,
            "missing_facts": cls._extract_list_from_block(block=missing_block) + missing_from_confirmed,
            "next_steps": cls._extract_list_from_block(block=next_steps_block),
        }

    @staticmethod
    def _extract_relevant_sources(result: dict[str, Any]) -> list[dict[str, Any]]:
        extracted: list[dict[str, Any]] = []

        citations = result.get("citations")
        if isinstance(citations, list):
            for item in citations:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label") or "").strip()
                snippet = str(item.get("snippet") or "").strip()
                url = str(item.get("url") or "").strip()
                if not (label or snippet or url):
                    continue
                extracted.append(
                    {
                        "label": label or "Legal citation",
                        "snippet": snippet,
                        "url": url or None,
                    }
                )

        if not extracted:
            sources = result.get("sources")
            if isinstance(sources, list):
                for item in sources:
                    if not isinstance(item, dict):
                        continue
                    label = str(item.get("filename") or "").strip()
                    snippet = str(item.get("snippet") or "").strip()
                    if not (label or snippet):
                        continue
                    extracted.append(
                        {
                            "label": label or "Legal source",
                            "snippet": snippet,
                            "url": None,
                        }
                    )

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in extracted:
            key = f"{item.get('label')}|{item.get('url')}|{item.get('snippet')}".strip().lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
            if len(deduped) >= 12:
                break
        return deduped

    @staticmethod
    def _extract_jurisdiction_text(*, result: dict[str, Any], case_context: dict[str, Any]) -> str:
        jurisdiction_payload = result.get("jurisdiction")
        if isinstance(jurisdiction_payload, dict):
            country_code = str(jurisdiction_payload.get("country_code") or "").strip()
            country_display = str(jurisdiction_payload.get("country_display_name") or "").strip()
            if country_code:
                return country_code
            if country_display:
                return country_display

        case_payload = case_context.get("case") if isinstance(case_context.get("case"), dict) else {}
        return str(case_payload.get("jurisdiction_country") or "").strip()

    @staticmethod
    def _derive_verification_status(
        *,
        explicit_status: Any,
        used_fallback: bool,
        confidence: str,
        relevant_sources: list[dict[str, Any]],
        governing_rule: str,
        application: str,
    ) -> str:
        normalized_explicit = RuntimeCopilotOrchestrator._normalize_verification_status(explicit_status)
        if str(explicit_status or "").strip():
            return normalized_explicit
        if used_fallback:
            return "unverified"
        if confidence == "high" and relevant_sources and governing_rule and application:
            return "verified"
        if relevant_sources:
            return "partial"
        return "unverified"

    def _build_global_output_contract(
        self,
        *,
        result: dict[str, Any],
        workflow_plan: dict[str, Any],
        case_context: dict[str, Any],
        parsed_intent: str,
        user_query: str,
    ) -> dict[str, Any]:
        structured_result = result.get("structured_result")
        if not isinstance(structured_result, dict):
            structured_result = {}

        answer = str(result.get("answer") or "").strip()
        answer_derived = self._extract_answer_derived_fields(answer=answer)
        contract_confidence = self._normalize_confidence_label(result.get("confidence"))

        confirmed_facts = self._ensure_string_list(workflow_plan.get("confirmed_facts"))
        inferred_facts = self._ensure_string_list(structured_result.get("inferred_facts"))
        for item in self._ensure_string_list(answer_derived.get("inferred_facts")):
            if item not in inferred_facts:
                inferred_facts.append(item)

        missing_facts = self._ensure_string_list(workflow_plan.get("missing_facts"))
        for item in self._ensure_string_list(answer_derived.get("missing_facts")):
            if item not in missing_facts:
                missing_facts.append(item)

        legal_issue = str(answer_derived.get("legal_issue") or structured_result.get("legal_issue") or "").strip()
        if not legal_issue:
            legal_issue = str(workflow_plan.get("user_goal") or user_query or "").strip()

        relevant_sources = self._extract_relevant_sources(result)

        governing_rule = str(answer_derived.get("governing_rule") or structured_result.get("governing_rule") or "").strip()
        application = str(answer_derived.get("application") or structured_result.get("application") or "").strip()
        counter_analysis = str(
            answer_derived.get("counter_analysis")
            or structured_result.get("counter_analysis")
            or ""
        ).strip()

        contradictions = self._ensure_contradiction_rows(structured_result.get("contradictions"))
        for signal in case_context.get("risk_signals") or []:
            text = str(signal or "").strip()
            if text and "contradict" in text.lower():
                contradictions.append(
                    {
                        "description": text,
                        "impact": "medium",
                        "sources": ["risk_signals"],
                    }
                )
        contradictions = self._ensure_contradiction_rows(contradictions, max_items=12)

        next_steps = self._ensure_string_list(structured_result.get("next_steps"))
        for item in self._ensure_string_list(structured_result.get("recommended_next_steps")):
            if item not in next_steps:
                next_steps.append(item)
        for item in self._ensure_string_list(answer_derived.get("next_steps")):
            if item not in next_steps:
                next_steps.append(item)
        if not next_steps:
            next_steps = self._ensure_string_list(workflow_plan.get("source_needs"), max_items=3)

        verification_status = self._derive_verification_status(
            explicit_status=structured_result.get("verification_status"),
            used_fallback=bool(result.get("used_fallback")),
            confidence=contract_confidence,
            relevant_sources=relevant_sources,
            governing_rule=governing_rule,
            application=application,
        )

        lawyer_review_note = str(
            structured_result.get("lawyer_review_note")
            or workflow_plan.get("non_replacement_rule")
            or self.DEFAULT_LAWYER_REVIEW_NOTE
        ).strip()

        evidence_strength = structured_result.get("evidence_strength")
        if not isinstance(evidence_strength, dict):
            evidence_strength = {"strong": [], "medium": [], "weak": []}
        else:
            evidence_strength = {
                "strong": self._ensure_string_list(evidence_strength.get("strong"), max_items=10),
                "medium": self._ensure_string_list(evidence_strength.get("medium"), max_items=10),
                "weak": self._ensure_string_list(evidence_strength.get("weak"), max_items=10),
            }
        position_strength = structured_result.get("position_strength")
        if not isinstance(position_strength, dict):
            position_strength = {
                "score": 0,
                "label": "weak",
                "reason": "Position strength is provisional because structured verification is incomplete.",
            }
        else:
            score = int(position_strength.get("score") or 0)
            label = str(position_strength.get("label") or "weak").strip().lower()
            if score >= 70:
                label = "strong"
            elif score >= 40:
                label = "arguable"
            else:
                label = "weak"
            position_strength = {
                "score": max(0, min(100, score)),
                "label": label,
                "reason": str(position_strength.get("reason") or "").strip()
                or "Position strength remains preliminary and review-dependent.",
            }
        recommended_strategy = structured_result.get("recommended_strategy")
        if not isinstance(recommended_strategy, dict):
            recommended_strategy = {
                "type": "gather_evidence",
                "reason": "Missing facts and source verification should be addressed before strategic action.",
                "risk_level": "medium",
            }
        else:
            strategy_type = str(recommended_strategy.get("type") or "gather_evidence").strip().lower().replace(" ", "_")
            if strategy_type not in {"negotiate", "litigate", "gather_evidence", "wait", "escalate"}:
                strategy_type = "gather_evidence"
            risk_level = str(recommended_strategy.get("risk_level") or "medium").strip().lower()
            if risk_level not in {"low", "medium", "high"}:
                risk_level = "medium"
            recommended_strategy = {
                "type": strategy_type,
                "reason": str(recommended_strategy.get("reason") or "").strip()
                or "Recommended strategy remains preliminary and subject to lawyer review.",
                "risk_level": risk_level,
            }
        client_risk_summary = structured_result.get("client_risk_summary")
        if not isinstance(client_risk_summary, dict):
            client_risk_summary = {
                "financial_risk": "Financial exposure remains preliminary until supporting facts are complete.",
                "legal_risk": "Legal exposure remains preliminary and may change after further verification.",
                "urgency": "medium",
                "summary": "Client risk view is preliminary and should be reviewed by counsel.",
            }
        else:
            urgency = str(client_risk_summary.get("urgency") or "medium").strip().lower()
            if urgency not in {"low", "medium", "high"}:
                urgency = "medium"
            client_risk_summary = {
                "financial_risk": str(client_risk_summary.get("financial_risk") or "").strip()
                or "Financial exposure remains preliminary until supporting facts are complete.",
                "legal_risk": str(client_risk_summary.get("legal_risk") or "").strip()
                or "Legal exposure remains preliminary and may change after further verification.",
                "urgency": urgency,
                "summary": str(client_risk_summary.get("summary") or "").strip()
                or "Client risk view is preliminary and should be reviewed by counsel.",
            }

        return {
            "matter_type": str(workflow_plan.get("matter_type") or "mixed private law matter").strip(),
            "user_intent": str(parsed_intent or workflow_plan.get("parsed_intent") or "ask_global").strip(),
            "jurisdiction": self._extract_jurisdiction_text(result=result, case_context=case_context),
            "confirmed_facts": confirmed_facts,
            "inferred_facts": inferred_facts,
            "missing_facts": missing_facts,
            "legal_issue": legal_issue,
            "relevant_sources": relevant_sources,
            "governing_rule": governing_rule,
            "application": application,
            "counter_analysis": counter_analysis,
            "contradictions": contradictions,
            "position_strength": position_strength,
            "recommended_strategy": recommended_strategy,
            "evidence_strength": evidence_strength,
            "client_risk_summary": client_risk_summary,
            "confidence": contract_confidence,
            "verification_status": verification_status,
            "next_steps": next_steps,
            "lawyer_review_note": lawyer_review_note,
        }

    @staticmethod
    def _query_contains_markers(*, query: str, markers: set[str]) -> bool:
        lowered = str(query or "").lower()
        return any(marker in lowered for marker in markers)

    def _classify_matter_type(
        self,
        *,
        query: str,
        parsed_intent: str,
        legal_search_code_scope: list[str],
    ) -> str:
        lowered = str(query or "").lower()
        normalized_scope = {str(item or "").strip().lower() for item in (legal_search_code_scope or [])}

        if parsed_intent in self.CLIENT_EXPLANATION_INTENTS or self._query_contains_markers(
            query=lowered,
            markers=self.CLIENT_EXPLANATION_MARKERS,
        ):
            return "client explanation"
        if parsed_intent in self.DRAFTING_INTENTS or self._query_contains_markers(
            query=lowered,
            markers=self.DRAFTING_MARKERS,
        ):
            return "drafting"
        if parsed_intent in self.DOCUMENT_REVIEW_INTENTS or self._query_contains_markers(
            query=lowered,
            markers=self.DOCUMENT_REVIEW_MARKERS,
        ):
            return "document review"
        if self._query_contains_markers(query=lowered, markers=self.LITIGATION_MEMO_MARKERS):
            return "litigation position memo"
        if self._query_contains_markers(query=lowered, markers=self.ARTICLE_APPLICABILITY_MARKERS):
            return "article applicability review"

        succession_hit = self._query_contains_markers(query=lowered, markers=self.SUCCESSION_MARKERS) or (
            "code_succession" in normalized_scope
        )
        intl_hit = self._query_contains_markers(query=lowered, markers=self.INTERNATIONAL_PRIVATE_MARKERS) or (
            "code_international_prive" in normalized_scope
        )
        civil_hit = self._query_contains_markers(query=lowered, markers=self.CIVIL_OBLIGATION_MARKERS) or (
            "code_civil" in normalized_scope
        )

        hits = sum(1 for value in (civil_hit, succession_hit, intl_hit) if value)
        if hits >= 2:
            return "mixed private law matter"
        if succession_hit:
            return "succession"
        if intl_hit:
            return "international private law"
        if civil_hit or parsed_intent in self.LEGAL_ANALYSIS_INTENTS:
            return "civil obligation"
        return "mixed private law matter"

    def _select_workflow_kind(self, *, parsed_intent: str, matter_type: str, task_type: str | None = None) -> str:
        normalized_task_type = str(task_type or "").strip().lower()
        if normalized_task_type == "explanation":
            return "client_explanation"
        if normalized_task_type == "drafting":
            return "drafting"
        if normalized_task_type == "research":
            return "legal_analysis"

        if parsed_intent in self.CLIENT_EXPLANATION_INTENTS or matter_type == "client explanation":
            return "client_explanation"
        if parsed_intent in self.DRAFTING_INTENTS or matter_type == "drafting":
            return "drafting"
        if parsed_intent in self.DOCUMENT_REVIEW_INTENTS or matter_type == "document review":
            return "document_review"
        if matter_type in {"litigation position memo", "article applicability review"}:
            return "legal_analysis"
        if parsed_intent in self.LEGAL_ANALYSIS_INTENTS:
            return "legal_analysis"
        return "general_assistance"

    @staticmethod
    def _extract_confirmed_facts_from_context(case_context: dict[str, Any]) -> list[str]:
        case_payload = case_context.get("case") if isinstance(case_context.get("case"), dict) else {}
        facts: list[str] = []

        if isinstance(case_payload.get("id"), int):
            facts.append(f"Active case context is available (case_id={case_payload.get('id')}).")
        title = str(case_payload.get("title") or "").strip()
        if title:
            facts.append(f"Case title: {title}.")
        jurisdiction = str(case_payload.get("jurisdiction_country") or "").strip()
        if jurisdiction:
            facts.append(f"Jurisdiction context: {jurisdiction}.")

        document_count = int(case_payload.get("document_count") or 0)
        if document_count > 0:
            facts.append(f"Documents available in workspace: {document_count}.")

        timeline_count = len(case_context.get("timeline") or [])
        if timeline_count > 0:
            facts.append(f"Timeline events available: {timeline_count}.")

        risk_count = len(case_context.get("risk_signals") or [])
        if risk_count > 0:
            facts.append(f"Risk signals detected in case context: {risk_count}.")

        return facts[:8]

    def _infer_missing_facts(
        self,
        *,
        matter_type: str,
        workflow_kind: str,
        case_context: dict[str, Any],
        query: str,
    ) -> list[str]:
        missing: list[str] = []
        case_payload = case_context.get("case") if isinstance(case_context.get("case"), dict) else {}
        has_case = isinstance(case_payload.get("id"), int)
        document_count = int(case_payload.get("document_count") or 0)

        if not has_case:
            missing.append("No active case context is selected in the workspace.")
        if document_count <= 0:
            missing.append("No supporting case documents are currently available for grounded analysis.")
        if not str(case_payload.get("jurisdiction_country") or "").strip():
            missing.append("Jurisdiction country is not explicitly confirmed.")

        if matter_type == "succession":
            missing.extend(
                [
                    "Family relationship map and heir status are not fully confirmed.",
                    "Testament validity details and inheritance documents may be missing.",
                ]
            )
        elif matter_type == "international private law":
            missing.extend(
                [
                    "Cross-border connecting factors (domicile, nationality, place of performance) may be incomplete.",
                    "Foreign judgment or governing-law clause evidence may require verification.",
                ]
            )
        elif matter_type == "civil obligation":
            missing.extend(
                [
                    "Key contractual clauses and breach chronology may be incomplete.",
                    "Notice, cure period, and damages evidence may require confirmation.",
                ]
            )

        if workflow_kind in {"drafting", "client_explanation"} and document_count < 2:
            missing.append("Drafting confidence is limited without a fuller factual record.")

        if self._query_contains_markers(query=query, markers=self.UNCERTAINTY_MARKERS):
            missing.append("The request itself signals uncertainty; assumptions should be explicitly validated.")

        deduped: list[str] = []
        for item in missing:
            if item not in deduped:
                deduped.append(item)
        return deduped[:10]

    def _determine_source_needs(
        self,
        *,
        matter_type: str,
        workflow_kind: str,
        has_case_scope: bool,
        has_document_scope: bool,
    ) -> list[str]:
        source_needs: list[str] = []

        if workflow_kind == "legal_analysis":
            if matter_type == "succession":
                source_needs.extend(
                    [
                        "Code de succession / statut personnel provisions relevant to heirs and testament.",
                        "Civil-status and inheritance documents from the case file.",
                    ]
                )
            elif matter_type == "international private law":
                source_needs.extend(
                    [
                        "Code international prive provisions on conflict rules and recognition/exequatur.",
                        "Governing-law and jurisdiction clauses, plus foreign decision documents if any.",
                    ]
                )
            elif matter_type == "mixed private law matter":
                source_needs.extend(
                    [
                        "Cross-family retrieval from Code civil, succession, and international private law where applicable.",
                        "Case documents showing factual links between the legal families.",
                    ]
                )
            else:
                source_needs.extend(
                    [
                        "Code civil provisions and procedural contract/breach evidence.",
                        "Case chronology, notices, and supporting exhibits.",
                    ]
                )
        elif workflow_kind == "document_review":
            source_needs.extend(
                [
                    "Target document text and clause-level snippets.",
                    "Related supporting documents for contradiction/consistency checks.",
                ]
            )
        elif workflow_kind in {"drafting", "client_explanation"}:
            source_needs.extend(
                [
                    "Verified case summary and key legal basis from prior analysis.",
                    "Latest timeline and risk highlights to avoid unsupported drafting claims.",
                ]
            )

        if not has_case_scope:
            source_needs.append("Case scope selection is required for stronger grounding and traceability.")
        if has_document_scope:
            source_needs.append("Document-scoped retrieval should be prioritized before broader case/global retrieval.")

        deduped: list[str] = []
        for item in source_needs:
            if item not in deduped:
                deduped.append(item)
        return deduped[:10]

    @staticmethod
    def _recommend_output_format(*, workflow_kind: str, matter_type: str) -> str:
        if workflow_kind == "drafting":
            return "editable_draft"
        if workflow_kind == "client_explanation":
            return "client_explanation_draft"
        if workflow_kind == "document_review":
            return "document_review_matrix"
        if matter_type == "litigation position memo":
            return "litigation_position_memo"
        if matter_type == "article applicability review":
            return "article_applicability_review"
        return "structured_legal_analysis"

    @staticmethod
    def _workflow_template_for_matter(*, workflow_kind: str, matter_type: str) -> str:
        if workflow_kind == "client_explanation":
            return "client_explanation"
        if workflow_kind == "drafting":
            return "editable_drafting"
        if matter_type == "civil obligation":
            return "civil_dispute_analysis"
        if matter_type == "succession":
            return "succession_analysis"
        if matter_type == "international private law":
            return "international_private_law_screening"
        if matter_type == "article applicability review":
            return "article_applicability_review"
        if matter_type == "litigation position memo":
            return "internal_legal_memo"
        return "structured_legal_analysis"

    @staticmethod
    def _workflow_agent_sequence(*, workflow_template: str, workflow_kind: str) -> list[str]:
        if workflow_template == "civil_dispute_analysis":
            return [
                "matter_classification_agent",
                "fact_extraction_agent",
                "retrieval_agent",
                "rule_synthesis_agent",
                "application_agent",
                "missing_facts_agent",
                "counter_analysis_agent",
                "verifier_agent",
                "memo_drafting_agent",
            ]
        if workflow_template == "succession_analysis":
            return [
                "matter_classification_agent",
                "fact_extraction_agent",
                "retrieval_agent",
                "rule_synthesis_agent",
                "application_agent",
                "missing_facts_agent",
                "verifier_agent",
                "memo_drafting_agent",
            ]
        if workflow_template == "international_private_law_screening":
            return [
                "matter_classification_agent",
                "fact_extraction_agent",
                "retrieval_agent",
                "rule_synthesis_agent",
                "application_agent",
                "missing_facts_agent",
                "counter_analysis_agent",
                "verifier_agent",
                "memo_drafting_agent",
            ]
        if workflow_template == "article_applicability_review":
            return [
                "retrieval_agent",
                "rule_synthesis_agent",
                "application_agent",
                "counter_analysis_agent",
                "verifier_agent",
                "memo_drafting_agent",
            ]
        if workflow_template == "internal_legal_memo":
            return [
                "fact_extraction_agent",
                "retrieval_agent",
                "rule_synthesis_agent",
                "application_agent",
                "missing_facts_agent",
                "counter_analysis_agent",
                "verifier_agent",
                "memo_drafting_agent",
                "next_steps_agent",
            ]
        if workflow_kind == "client_explanation":
            return [
                "fact_extraction_agent",
                "retrieval_agent",
                "rule_synthesis_agent",
                "application_agent",
                "missing_facts_agent",
                "verifier_agent",
                "client_explanation_agent",
                "next_steps_agent",
            ]
        if workflow_kind == "drafting":
            return [
                "fact_extraction_agent",
                "retrieval_agent",
                "rule_synthesis_agent",
                "application_agent",
                "missing_facts_agent",
                "verifier_agent",
                "drafting_agent",
                "next_steps_agent",
            ]
        return [
            "matter_classification_agent",
            "fact_extraction_agent",
            "retrieval_agent",
            "rule_synthesis_agent",
            "application_agent",
            "missing_facts_agent",
            "counter_analysis_agent",
            "verifier_agent",
            "memo_drafting_agent",
            "next_steps_agent",
        ]

    @staticmethod
    def _default_code_family_for_matter(matter_type: str) -> str:
        mapping = {
            "civil obligation": "code_civil",
            "succession": "code_succession",
            "international private law": "code_international_prive",
            "mixed private law matter": "mixed_or_ambiguous",
            "article applicability review": "context_dependent",
            "document review": "context_dependent",
            "drafting": "context_dependent",
            "client explanation": "context_dependent",
            "litigation position memo": "context_dependent",
        }
        return mapping.get(str(matter_type or "").strip().lower(), "mixed_or_ambiguous")

    def _estimate_trust_level(
        self,
        *,
        parsed: dict[str, Any],
        workflow_kind: str,
        case_context: dict[str, Any],
        query: str,
    ) -> str:
        confidence = str(parsed.get("confidence") or "low").strip().lower()
        case_payload = case_context.get("case") if isinstance(case_context.get("case"), dict) else {}
        has_case = isinstance(case_payload.get("id"), int)
        document_count = int(case_payload.get("document_count") or 0)

        if workflow_kind == "legal_analysis" and (
            confidence == "low"
            or not has_case
            or document_count <= 0
            or self._query_contains_markers(query=query, markers=self.UNCERTAINTY_MARKERS)
        ):
            return "low"
        if workflow_kind == "legal_analysis" and confidence == "high" and document_count >= 3:
            return "high"
        return "medium"

    def _build_legal_workflow_plan(
        self,
        *,
        message: str,
        parsed: dict[str, Any],
        case_context: dict[str, Any],
        requested_mode: str,
        legal_search_code_scope: list[str],
        matter_classification: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = str(parsed.get("clean_query") or message or "").strip()
        parsed_intent = str(parsed.get("intent") or "ask_global").strip() or "ask_global"

        classification_payload = matter_classification if isinstance(matter_classification, dict) else {}
        classified_matter_type = str(classification_payload.get("matter_type") or "").strip()
        classified_task_type = str(classification_payload.get("task_type") or "").strip().lower()
        classified_subtopic = str(classification_payload.get("subtopic") or "").strip()
        classified_code_family = str(classification_payload.get("likely_code_family") or "").strip()
        classified_dimension = str(classification_payload.get("legal_dimension") or "").strip().lower()
        classified_urgency_sensitivity = classification_payload.get("urgency_sensitivity")
        if not isinstance(classified_urgency_sensitivity, dict):
            classified_urgency_sensitivity = {}
        classification_confidence = str(classification_payload.get("confidence") or "").strip().lower()

        heuristic_matter_type = self._classify_matter_type(
            query=query,
            parsed_intent=parsed_intent,
            legal_search_code_scope=legal_search_code_scope,
        )
        matter_type = classified_matter_type or heuristic_matter_type

        workflow_kind = self._select_workflow_kind(
            parsed_intent=parsed_intent,
            matter_type=matter_type,
            task_type=classified_task_type or None,
        )
        confirmed_facts = self._extract_confirmed_facts_from_context(case_context)
        missing_facts = self._infer_missing_facts(
            matter_type=matter_type,
            workflow_kind=workflow_kind,
            case_context=case_context,
            query=query,
        )

        has_case_scope = isinstance(parsed.get("case_id"), int) or isinstance(
            (case_context.get("case") or {}).get("id") if isinstance(case_context.get("case"), dict) else None,
            int,
        )
        has_document_scope = isinstance(parsed.get("document_id"), int)
        source_needs = self._determine_source_needs(
            matter_type=matter_type,
            workflow_kind=workflow_kind,
            has_case_scope=has_case_scope,
            has_document_scope=has_document_scope,
        )
        output_format = self._recommend_output_format(workflow_kind=workflow_kind, matter_type=matter_type)
        workflow_template = self._workflow_template_for_matter(
            workflow_kind=workflow_kind,
            matter_type=matter_type,
        )
        agent_sequence = self._workflow_agent_sequence(
            workflow_template=workflow_template,
            workflow_kind=workflow_kind,
        )
        trust_level = self._estimate_trust_level(
            parsed=parsed,
            workflow_kind=workflow_kind,
            case_context=case_context,
            query=query,
        )

        likely_code_family = classified_code_family or self._default_code_family_for_matter(matter_type)
        legal_dimension = classified_dimension or (
            "procedural"
            if matter_type in {"document review", "article applicability review"}
            else "substantive"
        )
        task_type = classified_task_type or (
            "analysis" if workflow_kind == "legal_analysis" else "drafting" if workflow_kind == "drafting" else "analysis"
        )

        ambiguity_note = str(classification_payload.get("ambiguity_note") or "").strip()
        if ambiguity_note:
            missing_facts = [*missing_facts, ambiguity_note]

        return {
            "user_goal": query or "Clarify and progress legal work request.",
            "parsed_intent": parsed_intent,
            "matter_type": matter_type,
            "subtopic": classified_subtopic or "General legal classification pending lawyer review.",
            "likely_code_family": likely_code_family,
            "task_type": task_type,
            "legal_dimension": legal_dimension,
            "urgency_sensitivity": {
                "urgency": str(classified_urgency_sensitivity.get("urgency") or "normal").strip().lower() or "normal",
                "sensitivity": str(classified_urgency_sensitivity.get("sensitivity") or "standard").strip().lower() or "standard",
            },
            "matter_classification_confidence": (
                classification_confidence
                if classification_confidence in {"low", "medium", "high"}
                else "medium"
            ),
            "workflow_kind": workflow_kind,
            "confirmed_facts": confirmed_facts,
            "missing_facts": missing_facts,
            "source_needs": source_needs,
            "recommended_output_format": output_format,
            "workflow_template": workflow_template,
            "agent_sequence": agent_sequence,
            "trust_level": trust_level,
            "requested_mode": requested_mode,
            "prefer_structured_analysis": workflow_kind == "legal_analysis",
            "prefer_verification_first": trust_level == "low" or self._query_contains_markers(
                query=query,
                markers=self.UNCERTAINTY_MARKERS,
            ),
            "non_replacement_rule": (
                "Final legal judgment remains with the human lawyer; output is reviewable legal-assistance material."
            ),
        }

    def _apply_workflow_routing(
        self,
        *,
        parsed: dict[str, Any],
        workflow_plan: dict[str, Any],
        workspace_case_id: int | None,
        workspace_document_id: int | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        candidate = dict(parsed)
        original_intent = str(candidate.get("intent") or "ask_global").strip() or "ask_global"
        resolved_intent = original_intent
        workflow_kind = str(workflow_plan.get("workflow_kind") or "").strip()
        matter_type = str(workflow_plan.get("matter_type") or "").strip()
        reason = "no_override"

        has_case_scope = isinstance(candidate.get("case_id"), int) or isinstance(workspace_case_id, int)
        has_document_scope = isinstance(candidate.get("document_id"), int) or isinstance(workspace_document_id, int)

        if workflow_kind == "client_explanation" and has_case_scope and original_intent in self.LEGAL_ANALYSIS_INTENTS:
            resolved_intent = "draft_client_email_case"
            reason = "client_explanation_route"
        elif workflow_kind == "drafting" and has_case_scope and original_intent in self.LEGAL_ANALYSIS_INTENTS:
            resolved_intent = "draft_partner_strategy_note_case" if matter_type == "litigation position memo" else "draft_internal_email_case"
            reason = "drafting_route"
        elif workflow_kind == "document_review" and has_document_scope and original_intent in {
            "ask_global",
            "ask_case",
            "ask_document",
            "summarize_global",
        }:
            resolved_intent = "summarize_document"
            reason = "document_review_route"
        elif workflow_kind == "legal_analysis" and original_intent in {"ask_global", "summarize_global"}:
            if has_document_scope:
                resolved_intent = "ask_document"
                reason = "structured_document_scope_route"
            elif has_case_scope:
                resolved_intent = "ask_case"
                reason = "structured_case_scope_route"

        if resolved_intent != original_intent:
            candidate["intent"] = resolved_intent
            if resolved_intent in {"ask_case", "summarize_case", "draft_client_email_case", "draft_internal_email_case", "draft_partner_strategy_note_case"} and not isinstance(candidate.get("case_id"), int):
                if isinstance(workspace_case_id, int):
                    candidate["case_id"] = workspace_case_id
            if resolved_intent in {"ask_document", "summarize_document"} and not isinstance(candidate.get("document_id"), int):
                if isinstance(workspace_document_id, int):
                    candidate["document_id"] = workspace_document_id

        candidate["workflow_plan"] = workflow_plan
        return candidate, {
            "intent_overridden": resolved_intent != original_intent,
            "original_intent": original_intent,
            "resolved_intent": resolved_intent,
            "reason": reason,
        }

    @staticmethod
    def _resolve_effective_mode(*, requested_mode: str, workflow_plan: dict[str, Any]) -> str:
        normalized_mode = str(requested_mode or "default").strip().lower() or "default"
        return normalized_mode

    @staticmethod
    def _scope_adjusted_intent(
        *,
        intent: str,
        prefer_case: bool,
        prefer_document: bool,
    ) -> str:
        normalized_intent = str(intent or "").strip() or "ask_global"
        if prefer_document and normalized_intent == "ask_global":
            return "ask_document"
        if prefer_case and normalized_intent == "ask_global":
            return "ask_case"
        if prefer_document and normalized_intent == "summarize_global":
            return "summarize_document"
        if prefer_case and normalized_intent == "summarize_global":
            return "summarize_case"
        if prefer_case and normalized_intent == "ask_document":
            return "ask_case"
        if prefer_document and normalized_intent == "ask_case":
            return "ask_document"
        if prefer_case and normalized_intent == "summarize_document":
            return "summarize_case"
        if prefer_document and normalized_intent == "summarize_case":
            return "summarize_document"
        return normalized_intent

    def _arbitrate_low_confidence_intent(
        self,
        *,
        raw_parse: dict[str, Any],
        parsed: dict[str, Any],
        workspace_case_id: int | None,
        workspace_document_id: int | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        parsed_candidate = dict(parsed)
        raw_intent = str(raw_parse.get("intent") or "").strip()
        parsed_intent = str(parsed_candidate.get("intent") or "ask_global").strip() or "ask_global"
        parsed_confidence = str(parsed_candidate.get("confidence") or "low").strip().lower() or "low"
        raw_confidence = str(raw_parse.get("confidence") or "low").strip().lower() or "low"
        parsed_score = float(parsed_candidate.get("confidence_score") or 0.0)
        raw_score = float(raw_parse.get("confidence_score") or 0.0)

        low_confidence = bool(parsed_candidate.get("low_confidence")) or parsed_confidence == "low"
        conflicting = bool(raw_intent) and raw_intent != parsed_intent

        metadata: dict[str, Any] = {
            "activated": False,
            "reason": "not_required",
            "original_intent": parsed_intent,
            "resolved_intent": parsed_intent,
            "low_confidence": low_confidence,
            "conflicting": conflicting,
            "raw_intent": raw_intent or None,
            "parsed_confidence": parsed_confidence,
            "parsed_confidence_score": parsed_score,
            "raw_confidence": raw_confidence,
            "raw_confidence_score": raw_score,
        }
        if not low_confidence and not conflicting:
            return parsed_candidate, metadata

        explicit_case_scope = isinstance(parsed_candidate.get("case_id"), int) or bool(workspace_case_id)
        explicit_document_scope = isinstance(parsed_candidate.get("document_id"), int) or bool(workspace_document_id)

        candidates = parsed_candidate.get("arbitration_candidates")
        if isinstance(candidates, list):
            ordered_candidates = [str(candidate).strip() for candidate in candidates if str(candidate).strip()]
        else:
            ordered_candidates = [parsed_intent]

        scope_adjusted = self._scope_adjusted_intent(
            intent=parsed_intent,
            prefer_case=explicit_case_scope,
            prefer_document=explicit_document_scope,
        )
        if scope_adjusted not in ordered_candidates:
            ordered_candidates.insert(0, scope_adjusted)

        if raw_intent and raw_intent not in ordered_candidates:
            ordered_candidates.append(raw_intent)

        if explicit_document_scope:
            for candidate in ("ask_document", "summarize_document"):
                if candidate not in ordered_candidates:
                    ordered_candidates.append(candidate)
        elif explicit_case_scope:
            for candidate in ("ask_case", "summarize_case"):
                if candidate not in ordered_candidates:
                    ordered_candidates.append(candidate)

        resolved_intent = ordered_candidates[0] if ordered_candidates else parsed_intent
        reason = "scope_aligned"

        confidence_rank = {"low": 0, "medium": 1, "high": 2}
        if raw_intent and (
            raw_score >= max(parsed_score + 0.15, 0.72)
            or confidence_rank.get(raw_confidence, 0) > confidence_rank.get(parsed_confidence, 0)
        ):
            resolved_intent = raw_intent
            reason = "raw_parse_confidence_dominant"
        elif resolved_intent != parsed_intent:
            reason = "scope_adjusted"

        metadata.update(
            {
                "activated": True,
                "reason": reason,
                "resolved_intent": resolved_intent,
                "candidates": ordered_candidates,
            }
        )

        if resolved_intent != parsed_intent:
            parsed_candidate["intent"] = resolved_intent
            if parsed_score < 0.6:
                parsed_candidate["confidence"] = "medium"
                parsed_candidate["confidence_score"] = 0.6
                parsed_candidate["low_confidence"] = False
        parsed_candidate["intent_arbitration"] = metadata
        return parsed_candidate, metadata
