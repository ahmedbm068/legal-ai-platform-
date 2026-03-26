from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.deps import get_db
from backend.models.document import Document
from backend.services.ai.document_ai_pipeline import DocumentAIPipeline
from backend.services.ai.rag_service import RagService


router = APIRouter(prefix="/ai", tags=["AI"])

pipeline = DocumentAIPipeline()
rag_service = RagService(
    vector_store=pipeline.vector_store,
    embedding_service=pipeline.embedding_service
)


class AskRequest(BaseModel):
    question: str
    top_k: int = 5
    case_id: Optional[int] = None
    document_id: Optional[int] = None


@router.post("/process-document/{document_id}")
def process_document(document_id: int, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return pipeline.process_document(document, db)


@router.post("/ask")
def ask_question(data: AskRequest):
    return rag_service.answer_question(
        question=data.question,
        top_k=data.top_k,
        case_id=data.case_id,
        document_id=data.document_id
    )