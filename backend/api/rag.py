from typing import Literal
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
import json

from backend.core.deps import get_db, get_current_user
from backend.models.case import Case
from backend.models.document import Document
from backend.models.generated_artifact_version import GeneratedArtifactVersion
from backend.models.user import User
from backend.services.ai.document_ai_pipeline import DocumentAIPipeline
from backend.services.ai.agent_workflow_service import AgentWorkflowService
from backend.services.ai.artifact_versioning_service import artifact_versioning_service
from backend.services.ai.rag_service import RagService
from backend.services.ai.copilot_service import CopilotService
from backend.services.ai.llm_gateway import llm_gateway
from backend.api.rag_schema import (
    AskRequest,
    AskResponse,
    SearchRequest,
    SearchResponse,
    CopilotRequest,
    CopilotResponse,
    AgentWorkflowRequest,
    AgentWorkflowResponse,
    ProviderStatusResponse,
    LLMTestRequest,
    LLMTestResponse,
    SemanticTranslateRequest,
    SemanticTranslateResponse,
    ArtifactVersionListResponse,
    ArtifactVersionManualEditRequest,
    ArtifactVersionAgentReviseRequest,
    ArtifactVersionMutationResponse,
)


router = APIRouter(prefix="/ai", tags=["AI"])

pipeline = DocumentAIPipeline()
rag_service = RagService(
    vector_store=pipeline.vector_store,
    embedding_service=pipeline.embedding_service
)
copilot_service = CopilotService(rag_service=rag_service)
agent_workflow_service = AgentWorkflowService(rag_service=rag_service)


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

    return pipeline.process_document(document, db)


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
    return copilot_service.handle_message(
        db=db,
        tenant_id=current_user.tenant_id,
        message=data.message,
        top_k=data.top_k,
        use_external_research=data.use_external_research,
        conversation_history=[item.model_dump() for item in data.conversation_history],
    )


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
