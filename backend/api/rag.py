from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.deps import get_db, get_current_user
from backend.models.document import Document
from backend.models.user import User
from backend.services.ai.document_ai_pipeline import DocumentAIPipeline
from backend.services.ai.agent_workflow_service import AgentWorkflowService
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
)


router = APIRouter(prefix="/ai", tags=["AI"])

pipeline = DocumentAIPipeline()
rag_service = RagService(
    vector_store=pipeline.vector_store,
    embedding_service=pipeline.embedding_service
)
copilot_service = CopilotService(rag_service=rag_service)
agent_workflow_service = AgentWorkflowService(rag_service=rag_service)


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
    )


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
