from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session

from backend.core.deps import get_db, get_current_user
from backend.models.document import Document
from backend.models.user import User
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

    filename = file.filename

    upload_file(file.file, filename)

    new_doc = Document(
        filename=filename,
        storage_path=filename,
        case_id=case_id,
        tenant_id=current_user.tenant_id
    )

    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    return {
        "message": "Document uploaded",
        "document_id": new_doc.id
    }