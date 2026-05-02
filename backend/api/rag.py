from datetime import datetime, timedelta, timezone
from typing import Literal
import re
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.deps import get_db, get_current_user
from backend.core.enums import UserRole
from backend.core.permissions import require_roles
from backend.models.case import Case
from backend.models.ai_response_audit_log import AIResponseAuditLog
from backend.models.copilot_feedback import CopilotFeedback
from backend.models.document import Document
from backend.models.generated_artifact_version import GeneratedArtifactVersion
from backend.models.user import User
from backend.services.jobs.job_queue_service import background_job_service
from backend.services.cache_service import _SKIP_CACHE
from backend.services.use_cases.ingestion_use_case import ingestion_use_case
from backend.services.ai.artifact_versioning_service import artifact_versioning_service
from backend.services.ai.agents.prompt_optimizer_agent import prompt_optimizer_agent
from backend.services.ai.llm_gateway import llm_gateway
from backend.services.ai.runtime_services import (
    agent_workflow_service,
    copilot_orchestration_service,
    rag_service,
    shared_document_pipeline,
)
from backend.services.draft_document_payload_service import build_draft_document_payload, is_drafting_request
from backend.api.rag_schema import (
    AskRequest,
    AskResponse,
    SearchRequest,
    SearchResponse,
    CopilotRequest,
    CopilotResponse,
    CopilotFeedbackCreateRequest,
    CopilotFeedbackOut,
    CopilotFeedbackWeeklySummaryResponse,
    AgentWorkflowRequest,
    AgentWorkflowResponse,
    ProviderStatusResponse,
    LLMTestRequest,
    LLMTestResponse,
    SemanticTranslateRequest,
    SemanticTranslateResponse,
    PromptOptimizationRequest,
    PromptOptimizationResponse,
    ArtifactVersionListResponse,
    ArtifactVersionManualEditRequest,
    ArtifactVersionAgentReviseRequest,
    ArtifactVersionMutationResponse,
    AIResponseAuditLogListResponse,
)


router = APIRouter(prefix="/ai", tags=["AI"])


def _parse_json_payload(raw_text: str) -> dict | None:
    payload_text = raw_text.strip()
    if not payload_text:
        return None
    try:
        parsed = json.loads(payload_text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    fenced_match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", payload_text, flags=re.IGNORECASE)
    if fenced_match:
        try:
            parsed = json.loads(fenced_match.group(1))
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            pass

    start = payload_text.find("{")
    end = payload_text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(payload_text[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            pass

    return None


def _to_version_rows_payload(rows: list[GeneratedArtifactVersion]) -> tuple[list[dict], int | None]:
    versions = [artifact_versioning_service.to_public_payload(row) for row in rows]
    selected_version_id = next((item["id"] for item in versions if item.get("is_selected")), None)
    return versions, selected_version_id


def _resolve_case_country(db: Session, tenant_id: int, case_id: int | None) -> str | None:
    if case_id is None:
        return None
    case = (
        db.query(Case)
        .filter(
            Case.id == case_id,
            Case.tenant_id == tenant_id,
            Case.deleted_at.is_(None),
        )
        .first()
    )
    if not case:
        return None
    return (case.jurisdiction_country or "tunisia").strip().lower()


def _loads_json_object(raw_value: str | None) -> dict:
    if not raw_value:
        return {}
    try:
        payload = json.loads(raw_value)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _loads_json_list(raw_value: str | None) -> list:
    if not raw_value:
        return []
    try:
        payload = json.loads(raw_value)
        return payload if isinstance(payload, list) else []
    except Exception:
        return []


def _audit_log_to_public(row: AIResponseAuditLog) -> dict:
    answer = str(row.answer_text or "")
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "user_id": row.user_id,
        "case_id": row.case_id,
        "document_id": row.document_id,
        "endpoint": row.endpoint,
        "parsed_intent": row.parsed_intent,
        "response_version": row.response_version,
        "model_name": row.model_name,
        "prompt_version": row.prompt_version,
        "question_text": row.question_text,
        "answer_preview": answer[:800],
        "sources": _loads_json_list(row.sources_json),
        "trust_panel": _loads_json_object(row.trust_panel_json),
        "validation": _loads_json_object(row.validation_json),
        "metadata": _loads_json_object(row.metadata_json),
        "created_at": row.created_at,
    }


@router.post("/process-document/{document_id}")
def process_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.tenant_id == current_user.tenant_id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    job = background_job_service.enqueue(
        db=db,
        job_type="document_process",
        payload={"document_id": document.id},
        tenant_id=current_user.tenant_id,
        case_id=document.case_id,
        document_id=document.id,
        queue_name="documents",
    )
    return {
        "message": "Document processing has been queued.",
        "job": background_job_service.to_public_payload(job),
    }


@router.get("/jobs/{job_id}")
def get_background_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = background_job_service.get_job(db=db, job_id=job_id)
    if not job or job.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return background_job_service.to_public_payload(job)


@router.post("/cases/{case_id}/snapshot/refresh")
def refresh_case_snapshot(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = (
        db.query(Case)
        .filter(
            Case.id == case_id,
            Case.tenant_id == current_user.tenant_id,
            Case.deleted_at.is_(None),
        )
        .first()
    )
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    return {
        "message": "Case snapshot refresh queued.",
        "job": ingestion_use_case.enqueue_case_snapshot_refresh(
            db=db,
            tenant_id=current_user.tenant_id,
            case_id=case.id,
        ),
    }


@router.post("/search", response_model=SearchResponse)
def search_chunks(
    data: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return rag_service.search_chunks(
        db=db,
        tenant_id=current_user.tenant_id,
        query=data.query,
        top_k=data.top_k,
        case_id=data.case_id,
        document_id=data.document_id
    )


@router.post("/ask", response_model=AskResponse)
def ask_question(
    data: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return rag_service.answer_question(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        question=data.question,
        top_k=data.top_k,
        case_id=data.case_id,
        document_id=data.document_id
    )


@router.post("/copilot", response_model=CopilotResponse)
def copilot(
    data: CopilotRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    _token = _SKIP_CACHE.set(data.skip_cache)
    try:
        response = copilot_orchestration_service.run(
            db=db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            user_role=current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
            message=data.message,
            top_k=data.top_k,
            use_external_research=data.use_external_research,
            mode=data.mode,
            legal_search_multilingual_output=data.legal_search_multilingual_output,
            legal_search_code_scope=data.legal_search_code_scope,
            reasoning_level=data.reasoning_level,
            agent_mode=data.agent_mode,
            workspace_case_id=data.workspace_case_id,
            workspace_document_id=data.workspace_document_id,
            conversation_history=[item.model_dump() for item in data.conversation_history],
            attachments=[item.model_dump() for item in data.attachments],
            save_attachments_to_case=data.save_attachments_to_case,
            attachment_case_id=data.attachment_case_id,
        )
    finally:
        _SKIP_CACHE.reset(_token)
    if is_drafting_request(data.message, response.get("parsed_intent"), response.get("action_category")):
        answer = str(response.get("answer") or response.get("message") or "")
        sources = response.get("sources") if isinstance(response.get("sources"), list) else []
        citations = response.get("citations") if isinstance(response.get("citations"), list) else []
        response["open_editor"] = True
        response["draft_document"] = build_draft_document_payload(
            prompt=data.message,
            answer=answer,
            parsed_intent=response.get("parsed_intent"),
            case_id=data.workspace_case_id,
            sources=sources,
            citations=citations,
        )
        response["message"] = "I drafted it and opened it in the editor."
    else:
        response["open_editor"] = False
        response["draft_document"] = None
    return response


@router.post("/optimize-prompt", response_model=PromptOptimizationResponse)
def optimize_prompt(
    data: PromptOptimizationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_type: str | None = None
    target_id: int | None = None

    if data.workspace_document_id is not None:
        document = (
            db.query(Document)
            .filter(
                Document.id == data.workspace_document_id,
                Document.tenant_id == current_user.tenant_id,
            )
            .first()
        )
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
        target_type = "document"
        target_id = document.id
    elif data.workspace_case_id is not None:
        case = (
            db.query(Case)
            .filter(
                Case.id == data.workspace_case_id,
                Case.tenant_id == current_user.tenant_id,
                Case.deleted_at.is_(None),
            )
            .first()
        )
        if not case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
        target_type = "case"
        target_id = case.id

    optimized = prompt_optimizer_agent.optimize_query(
        raw_query=data.prompt,
        intent="optimize_prompt",
        target_type=target_type,
        target_id=target_id,
        allow_llm=True,
    )

    original_prompt = data.prompt.strip()
    optimized_prompt = (
        str(optimized.payload.get("optimized_query") or "").strip()
        if optimized.success
        else ""
    )
    if not optimized_prompt:
        optimized_prompt = original_prompt

    unchanged = optimized_prompt == original_prompt
    applied_improvements = (
        [str(item).strip() for item in (optimized.payload.get("applied_improvements") or []) if str(item).strip()]
        if optimized.success
        else []
    )

    return {
        "optimized_prompt": optimized_prompt,
        "notes": optimized.payload.get("notes") if optimized.success else (optimized.error or "Prompt optimization failed."),
        "strategy": str(optimized.payload.get("strategy") or "heuristic") if optimized.success else "fallback",
        "used_llm": bool(optimized.payload.get("used_llm")) if optimized.success else False,
        "applied_improvements": applied_improvements,
        "unchanged": unchanged,
        "target_type": target_type,
        "target_id": target_id,
    }


@router.post("/feedback", response_model=CopilotFeedbackOut, status_code=status.HTTP_201_CREATED)
def create_copilot_feedback(
    data: CopilotFeedbackCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inferred_jurisdiction = data.jurisdiction
    if not inferred_jurisdiction:
        inferred_jurisdiction = _resolve_case_country(db, current_user.tenant_id, data.case_id)

    metadata_payload = dict(data.metadata or {})
    if data.lawyer_correction and "lawyer_correction" not in metadata_payload:
        metadata_payload["lawyer_correction"] = data.lawyer_correction
    if data.preferred_reasoning_path and "preferred_reasoning_path" not in metadata_payload:
        metadata_payload["preferred_reasoning_path"] = data.preferred_reasoning_path
    if data.root_cause and not metadata_payload.get("root_cause"):
        metadata_payload["root_cause"] = data.root_cause
    if data.legal_domain is not None and "legal_domain" not in metadata_payload:
        metadata_payload["legal_domain"] = data.legal_domain
    if inferred_jurisdiction and not metadata_payload.get("jurisdiction"):
        metadata_payload["jurisdiction"] = inferred_jurisdiction

    feedback = CopilotFeedback(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        case_id=data.case_id,
        document_id=data.document_id,
        message_id=data.message_id,
        parsed_intent=data.parsed_intent,
        confidence=data.confidence,
        feedback_value=data.feedback_value,
        prompt_text=data.prompt_text,
        response_text=data.response_text,
        comment=data.comment,
        root_cause=data.root_cause,
        legal_domain=data.legal_domain,
        jurisdiction=inferred_jurisdiction,
        source_count=int(data.source_count),
        metadata_json=json.dumps(metadata_payload, ensure_ascii=False),
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return {
        "id": feedback.id,
        "tenant_id": feedback.tenant_id,
        "user_id": feedback.user_id,
        "case_id": feedback.case_id,
        "document_id": feedback.document_id,
        "message_id": feedback.message_id,
        "parsed_intent": feedback.parsed_intent,
        "confidence": feedback.confidence,
        "feedback_value": feedback.feedback_value,
        "prompt_text": feedback.prompt_text,
        "response_text": feedback.response_text,
        "comment": feedback.comment,
        "lawyer_correction": metadata_payload.get("lawyer_correction"),
        "preferred_reasoning_path": metadata_payload.get("preferred_reasoning_path"),
        "root_cause": feedback.root_cause,
        "legal_domain": feedback.legal_domain,
        "jurisdiction": feedback.jurisdiction,
        "source_count": feedback.source_count,
        "metadata": json.loads(feedback.metadata_json) if feedback.metadata_json else {},
        "created_at": feedback.created_at,
    }


@router.get("/feedback/weekly-summary", response_model=CopilotFeedbackWeeklySummaryResponse)
def copilot_feedback_weekly_summary(
    weeks: int = Query(default=8, ge=1, le=52),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    horizon = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    rows = (
        db.query(CopilotFeedback)
        .filter(
            CopilotFeedback.tenant_id == current_user.tenant_id,
            CopilotFeedback.created_at >= horizon,
        )
        .order_by(CopilotFeedback.created_at.desc())
        .all()
    )

    grouped: dict[tuple[str, str], dict[str, int | float | str]] = {}
    for row in rows:
        created_at = row.created_at
        if created_at is None:
            continue

        localized = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
        week_start_date = (localized - timedelta(days=localized.weekday())).date().isoformat()
        intent = (row.parsed_intent or "unknown").strip() or "unknown"
        key = (week_start_date, intent)

        bucket = grouped.setdefault(
            key,
            {
                "week_start": week_start_date,
                "intent": intent,
                "up": 0,
                "down": 0,
                "total": 0,
                "up_rate": 0.0,
            },
        )

        if row.feedback_value == "up":
            bucket["up"] = int(bucket["up"]) + 1
        else:
            bucket["down"] = int(bucket["down"]) + 1
        bucket["total"] = int(bucket["total"]) + 1

    summary_rows = sorted(
        grouped.values(),
        key=lambda item: (str(item["week_start"]), int(item["total"])),
        reverse=True,
    )

    for item in summary_rows:
        total = int(item["total"])
        item["up_rate"] = round((int(item["up"]) / total), 4) if total else 0.0

    return {
        "weeks": weeks,
        "rows": summary_rows,
    }


@router.get("/audit-logs", response_model=AIResponseAuditLogListResponse)
def list_ai_response_audit_logs(
    case_id: int | None = Query(default=None, ge=1),
    document_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, [UserRole.lawyer])
    query = db.query(AIResponseAuditLog).filter(AIResponseAuditLog.tenant_id == current_user.tenant_id)
    if case_id is not None:
        query = query.filter(AIResponseAuditLog.case_id == case_id)
    if document_id is not None:
        query = query.filter(AIResponseAuditLog.document_id == document_id)

    total = query.count()
    rows = (
        query.order_by(AIResponseAuditLog.created_at.desc(), AIResponseAuditLog.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "total": total,
        "rows": [_audit_log_to_public(row) for row in rows],
    }


@router.get("/artifacts/versions", response_model=ArtifactVersionListResponse)
def list_artifact_versions(
    artifact_type: Literal["document_summary", "case_email"] = Query(...),
    case_id: int | None = Query(default=None, ge=1),
    document_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = artifact_versioning_service.list_versions(
        db=db,
        tenant_id=current_user.tenant_id,
        artifact_type=artifact_type,
        case_id=case_id,
        document_id=document_id,
    )
    versions, selected_version_id = _to_version_rows_payload(rows)
    return {
        "artifact_type": artifact_type,
        "case_id": rows[0].case_id if rows else case_id,
        "document_id": rows[0].document_id if rows else document_id,
        "selected_version_id": selected_version_id,
        "versions": versions,
    }


@router.post("/artifacts/versions/edit", response_model=ArtifactVersionMutationResponse)
def create_artifact_version_edit(
    data: ArtifactVersionManualEditRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    created = artifact_versioning_service.create_version(
        db=db,
        tenant_id=current_user.tenant_id,
        artifact_type=data.artifact_type,
        content=data.content,
        case_id=data.case_id,
        document_id=data.document_id,
        source_kind="manual_edit",
        edit_instruction=data.edit_instruction,
        parent_version_id=data.parent_version_id,
        created_by_user_id=current_user.id,
        auto_select=True,
    )
    rows = artifact_versioning_service.list_versions(
        db=db,
        tenant_id=current_user.tenant_id,
        artifact_type=created.artifact_type,  # type: ignore[arg-type]
        case_id=created.case_id,
        document_id=created.document_id,
    )
    versions, selected_version_id = _to_version_rows_payload(rows)

    return {
        "artifact_type": created.artifact_type,
        "case_id": created.case_id,
        "document_id": created.document_id,
        "selected_version_id": selected_version_id,
        "version": artifact_versioning_service.to_public_payload(created),
        "versions": versions,
    }


@router.post("/artifacts/versions/agent-revise", response_model=ArtifactVersionMutationResponse)
def revise_artifact_version_with_agent(
    data: ArtifactVersionAgentReviseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base_version: GeneratedArtifactVersion | None = None
    if data.base_version_id is not None:
        base_version = (
            db.query(GeneratedArtifactVersion)
            .filter(
                GeneratedArtifactVersion.id == data.base_version_id,
                GeneratedArtifactVersion.tenant_id == current_user.tenant_id,
            )
            .first()
        )
        if not base_version:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Base version not found.")
        if base_version.artifact_type != data.artifact_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="base_version_id does not match artifact_type.",
            )
        if data.case_id is not None and data.case_id != base_version.case_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="base_version_id does not match case_id.",
            )
        if data.document_id is not None and data.document_id != base_version.document_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="base_version_id does not match document_id.",
            )
    else:
        rows = artifact_versioning_service.list_versions(
            db=db,
            tenant_id=current_user.tenant_id,
            artifact_type=data.artifact_type,
            case_id=data.case_id,
            document_id=data.document_id,
        )
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No version found for this artifact scope.",
            )
        base_version = next((row for row in rows if row.is_selected), rows[-1])

    case_country = _resolve_case_country(
        db=db,
        tenant_id=current_user.tenant_id,
        case_id=base_version.case_id,
    )

    revised_content = artifact_versioning_service.revise_with_agent(
        artifact_type=data.artifact_type,
        current_content=base_version.content,
        instruction=data.instruction,
        jurisdiction_country=case_country,
    )
    created = artifact_versioning_service.create_version(
        db=db,
        tenant_id=current_user.tenant_id,
        artifact_type=data.artifact_type,
        content=revised_content,
        case_id=base_version.case_id,
        document_id=base_version.document_id,
        source_kind="agent_revision",
        edit_instruction=data.instruction,
        parent_version_id=base_version.id,
        created_by_user_id=current_user.id,
        metadata={
            "base_version_id": base_version.id,
            "jurisdiction_country": case_country,
        },
        auto_select=True,
    )

    rows = artifact_versioning_service.list_versions(
        db=db,
        tenant_id=current_user.tenant_id,
        artifact_type=created.artifact_type,  # type: ignore[arg-type]
        case_id=created.case_id,
        document_id=created.document_id,
    )
    versions, selected_version_id = _to_version_rows_payload(rows)

    return {
        "artifact_type": created.artifact_type,
        "case_id": created.case_id,
        "document_id": created.document_id,
        "selected_version_id": selected_version_id,
        "version": artifact_versioning_service.to_public_payload(created),
        "versions": versions,
    }


@router.post("/artifacts/versions/{version_id}/select", response_model=ArtifactVersionMutationResponse)
def select_artifact_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    selected = artifact_versioning_service.select_version(
        db=db,
        tenant_id=current_user.tenant_id,
        version_id=version_id,
    )
    rows = artifact_versioning_service.list_versions(
        db=db,
        tenant_id=current_user.tenant_id,
        artifact_type=selected.artifact_type,  # type: ignore[arg-type]
        case_id=selected.case_id,
        document_id=selected.document_id,
    )
    versions, selected_version_id = _to_version_rows_payload(rows)

    return {
        "artifact_type": selected.artifact_type,
        "case_id": selected.case_id,
        "document_id": selected.document_id,
        "selected_version_id": selected_version_id,
        "version": artifact_versioning_service.to_public_payload(selected),
        "versions": versions,
    }


@router.post("/agent-workflow", response_model=AgentWorkflowResponse)
def run_agent_workflow(
    data: AgentWorkflowRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_roles(current_user, [UserRole.admin, UserRole.lawyer])
    return agent_workflow_service.run_case_workflow(
        db=db,
        tenant_id=current_user.tenant_id,
        case_id=data.case_id,
        objective=data.objective,
        top_k=data.top_k,
    )


@router.get("/provider-status", response_model=ProviderStatusResponse)
def provider_status(
    current_user: User = Depends(get_current_user)
):
    _ = current_user
    return {
        "provider_available": llm_gateway.available,
        "base_url": llm_gateway.base_url,
        "model": llm_gateway.default_model,
        "summary_model": llm_gateway.summary_model,
        "key_present": bool(llm_gateway.api_key),
        "provider_name": llm_gateway.provider_name,
        "vision_available": llm_gateway.vision_available,
        "vision_provider_name": llm_gateway.vision_provider_name,
        "vision_model": llm_gateway.resolve_model("vision") if llm_gateway.vision_available else None,
        "vision_reason_unavailable": llm_gateway.vision_reason_unavailable,
    }


@router.post("/test-llm", response_model=LLMTestResponse)
def test_llm(
    data: LLMTestRequest,
    current_user: User = Depends(get_current_user)
):
    _ = current_user
    client = llm_gateway.create_client()
    provider_name = llm_gateway.provider_name

    if not client:
        return {
            "ok": False,
            "provider_name": provider_name,
            "model": llm_gateway.default_model,
            "output": "",
            "error": "No API key/provider configured.",
        }

    try:
        response = client.responses.create(
            model=llm_gateway.default_model,
            input=data.prompt,
        )
        return {
            "ok": True,
            "provider_name": provider_name,
            "model": llm_gateway.default_model,
            "output": llm_gateway.extract_output_text(response),
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider_name": provider_name,
            "model": llm_gateway.default_model,
            "output": "",
            "error": str(exc),
        }


@router.post("/translate", response_model=SemanticTranslateResponse)
def semantic_translate(
    data: SemanticTranslateRequest,
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    normalized_texts = [str(text or "").strip() for text in data.texts]
    normalized_texts = [text for text in normalized_texts if text]
    if not normalized_texts:
        return {
            "target_language": data.target_language,
            "translations": [],
            "used_fallback": True,
        }

    if data.source_language != "auto" and data.target_language == data.source_language:
        return {
            "target_language": data.target_language,
            "translations": normalized_texts,
            "used_fallback": False,
        }

    client = llm_gateway.create_client()
    if not client:
        return {
            "target_language": data.target_language,
            "translations": normalized_texts,
            "used_fallback": True,
        }

    prompt = f"""
You are a legal semantic translation engine.

Task:
- Translate each item in the provided JSON list to target language '{data.target_language}'.
- Source language hint: '{data.source_language}'.
- Domain: '{data.domain}'.

Rules:
- Preserve legal meaning and technical precision.
- Keep legal terms, product names, law/article references, and entity names accurate.
- Preserve formatting, bullets, numbering, and line breaks.
- Do not add commentary.
- Return valid JSON only in this schema:
{{
  "translations": ["..."]
}}

Input JSON:
{json.dumps(normalized_texts, ensure_ascii=False)}
"""
    try:
        response = client.responses.create(
            model=llm_gateway.default_model,
            input=prompt,
        )
        raw_text = llm_gateway.extract_output_text(response).strip()
        payload = _parse_json_payload(raw_text) if raw_text else {}
        translations = payload.get("translations") if isinstance(payload, dict) else None
        if isinstance(translations, list):
            cleaned = [str(item or "").strip() for item in translations]
            if len(cleaned) == len(normalized_texts) and all(cleaned):
                return {
                    "target_language": data.target_language,
                    "translations": cleaned,
                    "used_fallback": False,
                }
    except Exception:
        pass

    return {
        "target_language": data.target_language,
        "translations": normalized_texts,
        "used_fallback": True,
    }
