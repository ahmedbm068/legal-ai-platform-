from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.deps import get_db, get_current_user
from backend.models.document import Document
from backend.models.user import User
from backend.services.ai.document_ai_pipeline import DocumentAIPipeline
from backend.services.ai.rag_service import RagService
from backend.services.ai.copilot_service import CopilotService
from backend.api.rag_schema import (
    AskRequest,
    AskResponse,
    SearchRequest,
    SearchResponse,
    CopilotRequest,
    CopilotResponse
)


router = APIRouter(prefix="/ai", tags=["AI"])

pipeline = DocumentAIPipeline()
rag_service = RagService(
    vector_store=pipeline.vector_store,
    embedding_service=pipeline.embedding_service
)
copilot_service = CopilotService(rag_service=rag_service)


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
        top_k=data.top_k
    )