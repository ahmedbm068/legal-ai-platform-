from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session

from backend.core.deps import get_db, get_current_user
from backend.models.document import Document
from backend.models.user import User
from backend.services.storage_service import upload_file
from backend.services.ai.document_ai_pipeline import DocumentAIPipeline


router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)

pipeline = DocumentAIPipeline()


@router.post("/upload")
def upload_document(
    case_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    filename = file.filename

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    storage_path = upload_file(file.file, filename)

    new_doc = Document(
        filename=filename,
        storage_path=storage_path,
        file_size=file_size,
        file_type=file.content_type,
        case_id=case_id,
        tenant_id=current_user.tenant_id
    )

    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    ai_result = pipeline.process_document(new_doc, db)

    return {
        "document": {
            "id": new_doc.id,
            "filename": new_doc.filename,
            "storage_path": new_doc.storage_path,
            "file_size": new_doc.file_size,
            "file_type": new_doc.file_type,
            "upload_timestamp": new_doc.upload_timestamp,
            "case_id": new_doc.case_id,
            "tenant_id": new_doc.tenant_id
        },
        "ai_processing": ai_result
    }