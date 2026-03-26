from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.deps import get_db, get_current_user
from backend.models.case import Case
from backend.models.document import Document
from backend.models.user import User
from backend.api.document_schema import DocumentUploadResponse
from backend.services.storage_service import upload_file
from backend.services.ai.document_ai_pipeline import DocumentAIPipeline


router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)

pipeline = DocumentAIPipeline()


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    case_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
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

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    allowed_content_types = {
        "application/pdf",
    }

    if file.content_type not in allowed_content_types:
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported for this endpoint"
        )

    filename = file.filename.strip()

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    max_file_size = 20 * 1024 * 1024  # 20 MB

    if file_size > max_file_size:
        raise HTTPException(
            status_code=400,
            detail="File too large. Maximum allowed size is 20 MB for this prototype."
        )

    storage_path = upload_file(file.file, filename)

    new_doc = Document(
        filename=filename,
        storage_path=storage_path,
        file_size=file_size,
        file_type=file.content_type,
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