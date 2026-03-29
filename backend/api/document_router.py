from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.deps import get_db, get_current_user
from backend.models.case import Case
from backend.models.document import Document
from backend.models.user import User
from backend.api.document_schema import DocumentListItemOut, DocumentOut, DocumentUploadResponse
from backend.services.storage_service import upload_file
from backend.services.ai.document_ai_pipeline import DocumentAIPipeline


router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)

pipeline = DocumentAIPipeline()


def get_tenant_case_or_404(db: Session, case_id: int, current_user: User) -> Case:
    case = (
        db.query(Case)
        .filter(
            Case.id == case_id,
            Case.tenant_id == current_user.tenant_id,
            Case.deleted_at.is_(None)
        )
        .first()
    )

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    return case


def get_tenant_document_or_404(db: Session, document_id: int, current_user: User) -> Document:
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.tenant_id == current_user.tenant_id
        )
        .first()
    )

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return document


@router.get("/case/{case_id}", response_model=list[DocumentListItemOut])
def list_case_documents(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)

    return (
        db.query(Document)
        .filter(
            Document.case_id == case_id,
            Document.tenant_id == current_user.tenant_id
        )
        .order_by(Document.upload_timestamp.desc(), Document.id.desc())
        .all()
    )


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return get_tenant_document_or_404(db=db, document_id=document_id, current_user=current_user)


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    case_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    normalized_content_type = (file.content_type or "").split(";")[0].strip().lower()
    extension = Path(file.filename).suffix.lower()

    if normalized_content_type != "application/pdf" and extension != ".pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported for this endpoint"
        )

    filename = file.filename.strip()

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    max_file_size = max(1, int(settings.DOCUMENT_UPLOAD_MAX_MB)) * 1024 * 1024

    if file_size > max_file_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum allowed size is {settings.DOCUMENT_UPLOAD_MAX_MB} MB."
        )

    storage_path = upload_file(file.file, filename)

    new_doc = Document(
        filename=filename,
        storage_path=storage_path,
        file_size=file_size,
        file_type=normalized_content_type or "application/pdf",
        case_id=case_id,
        tenant_id=current_user.tenant_id,
        processing_status="pending"
    )

    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    ai_result = pipeline.process_document(new_doc, db)
    db.refresh(new_doc)

    return {
        "document": new_doc,
        "ai_processing": ai_result
    }
