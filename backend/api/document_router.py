from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pathlib import Path
import uuid

from backend.core.deps import get_db, get_current_user
from backend.models.document import Document
from backend.models.user import User
from backend.models.case import Case
from backend.services.storage_service import upload_file


router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)


@router.post("/upload")
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
            Case.tenant_id == current_user.tenant_id
        )
        .first()
    )

    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found"
        )

    original_filename = file.filename or "document.pdf"
    file_extension = Path(original_filename).suffix.lower()
    unique_id = uuid.uuid4().hex

    stored_filename = f"{unique_id}{file_extension}"
    storage_path = (
        f"tenant_{current_user.tenant_id}/"
        f"cases/{case_id}/"
        f"documents/{stored_filename}"
    )

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    file_type = file.content_type or "application/octet-stream"

    upload_file(file.file, storage_path)

    new_doc = Document(
        filename=original_filename,
        storage_path=storage_path,
        case_id=case_id,
        tenant_id=current_user.tenant_id,
        file_size=file_size,
        file_type=file_type
    )

    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    return {
        "message": "Document uploaded",
        "document_id": new_doc.id,
        "filename": new_doc.filename,
        "storage_path": new_doc.storage_path,
        "file_size": new_doc.file_size,
        "file_type": new_doc.file_type
    }