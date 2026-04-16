from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.services.ai.agents.prompt_correction_agent import prompt_correction_agent
from backend.services.ai.agents.prompt_optimizer_agent import prompt_optimizer_agent
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


class RuntimeCopilotOrchestrator:
    OPTIMIZABLE_INTENTS = {
        "ask_document",
        "ask_case",
        "ask_global",
        "summarize_global",
    }

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
            },
        )

        optimized_message: str | None = None
        clean_query = str(parsed.get("clean_query") or corrected_message).strip()
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

        result = self.copilot_service.handle_message(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role=user_role,
            message=pipeline_request.message,
            top_k=pipeline_request.top_k,
            use_external_research=pipeline_request.use_external_research,
            mode=pipeline_request.mode,
            legal_search_multilingual_output=pipeline_request.legal_search_multilingual_output,
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
                "agent_mode": request.agent_mode,
                "workspace_case_id": request.workspace_case_id,
                "workspace_document_id": request.workspace_document_id,
                "attachments_count": request.attachments_count,
            },
            "execution_context": execution_context.model_dump(mode="json"),
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
