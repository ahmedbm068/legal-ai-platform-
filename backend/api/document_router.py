from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from backend.api.document_schema import (
    DocumentListItemOut,
    DocumentOut,
    DocumentUploadResponse,
    ImageBatchDetailResponse,
    ImageBatchUploadResponse,
    ImageDocumentBatchOut,
)
from backend.core.config import settings
from backend.core.deps import get_current_user, get_db
from backend.core.permissions import apply_tenant_scope
from backend.models.case import Case
from backend.models.case_image_asset import CaseImageAsset
from backend.models.document import Document
from backend.models.image_document_batch import ImageDocumentBatch
from backend.models.user import User
from backend.services.ai.image_document_service import image_document_service
from backend.services.storage_service import stream_file_response
from backend.services.use_cases.ingestion_use_case import ingestion_use_case


router = APIRouter(prefix="/documents", tags=["Documents"])


def get_tenant_case_or_404(db: Session, case_id: int, current_user: User) -> Case:
    case_query = db.query(Case).filter(Case.id == case_id, Case.deleted_at.is_(None))
    case = apply_tenant_scope(case_query, Case.tenant_id, current_user).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


def get_tenant_document_or_404(db: Session, document_id: int, current_user: User) -> Document:
    document_query = db.query(Document).filter(Document.id == document_id)
    document = apply_tenant_scope(document_query, Document.tenant_id, current_user).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def get_tenant_image_asset_or_404(db: Session, asset_id: int, current_user: User) -> CaseImageAsset:
    query = db.query(CaseImageAsset).filter(CaseImageAsset.id == asset_id)
    asset = apply_tenant_scope(query, CaseImageAsset.tenant_id, current_user).first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image asset not found.")
    return asset


def get_tenant_image_batch_or_404(db: Session, batch_id: int, current_user: User) -> ImageDocumentBatch:
    query = db.query(ImageDocumentBatch).filter(ImageDocumentBatch.id == batch_id)
    batch = apply_tenant_scope(query, ImageDocumentBatch.tenant_id, current_user).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image batch not found.")
    return batch


@router.get("/case/{case_id}", response_model=list[DocumentListItemOut])
def list_case_documents(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)
    query = db.query(Document).filter(Document.case_id == case_id, Document.archived_at.is_(None))
    return apply_tenant_scope(query, Document.tenant_id, current_user).order_by(
        Document.upload_timestamp.desc(), Document.id.desc()
    ).all()


@router.get("/case/{case_id}/archived", response_model=list[DocumentListItemOut])
def list_case_archived_documents(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)
    query = db.query(Document).filter(Document.case_id == case_id, Document.archived_at.isnot(None))
    return apply_tenant_scope(query, Document.tenant_id, current_user).order_by(
        Document.archived_at.desc(), Document.id.desc()
    ).all()

@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_tenant_document_or_404(db=db, document_id=document_id, current_user=current_user)


@router.get("/{document_id}/file")
def get_document_file(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_tenant_document_or_404(db=db, document_id=document_id, current_user=current_user)
    return stream_file_response(
        document.storage_path,
        media_type=document.file_type or "application/pdf",
        filename=document.filename,
    )


@router.post("/{document_id}/archive", status_code=status.HTTP_200_OK)
def archive_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_tenant_document_or_404(db=db, document_id=document_id, current_user=current_user)
    document.archived_at = func.now()
    db.commit()
    return {"message": "Document moved to archive", "document_id": document.id, "archived": True}


@router.post("/{document_id}/unarchive", status_code=status.HTTP_200_OK)
def unarchive_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_tenant_document_or_404(db=db, document_id=document_id, current_user=current_user)
    document.archived_at = None
    db.commit()
    return {"message": "Document restored from archive", "document_id": document.id, "archived": False}


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    background_tasks: BackgroundTasks,
    case_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    normalized_content_type = (file.content_type or "").split(";")[0].strip().lower()
    extension = Path(file.filename).suffix.lower()
    if normalized_content_type != "application/pdf" and extension != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported for this endpoint")

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    max_file_size = max(1, int(settings.DOCUMENT_UPLOAD_MAX_MB)) * 1024 * 1024
    if file_size > max_file_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum allowed size is {settings.DOCUMENT_UPLOAD_MAX_MB} MB.",
        )

    new_doc, job_payload = ingestion_use_case.create_document_upload(
        db=db,
        case=case,
        file=file,
        background_tasks=background_tasks,
    )
    ai_result = {
        "success": True,
        "message": "Document accepted for processing. Extraction and indexing will continue asynchronously.",
        "status": "queued",
        "chunks_count": None,
        "entities_extracted": None,
        "pii_items_count": None,
        "text_length": None,
        "error": None,
    }
    return {"document": new_doc, "ai_processing": ai_result, "job": job_payload}


@router.post("/upload-images", response_model=ImageBatchUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_image_batch(
    background_tasks: BackgroundTasks,
    case_id: int,
    files: list[UploadFile] = File(...),
    title: str | None = Form(default=None),
    generate_document: bool = Form(default=True),
    run_authenticity_check: bool = Form(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one image or PDF is required.")
    if len(files) > max(1, int(settings.IMAGE_BATCH_MAX_FILES)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many files. Maximum allowed is {settings.IMAGE_BATCH_MAX_FILES}.",
        )

    for file in files:
        if not file.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Every file must have a filename.")
        image_document_service._validate_upload(filename=file.filename, content_type=file.content_type)
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        normalized_content_type = (file.content_type or "").split(";")[0].strip().lower()
        extension = Path(file.filename).suffix.lower()
        max_file_size_mb = settings.DOCUMENT_UPLOAD_MAX_MB if normalized_content_type == "application/pdf" or extension == ".pdf" else settings.IMAGE_UPLOAD_MAX_MB
        max_file_size = max(1, int(max_file_size_mb)) * 1024 * 1024
        if file_size > max_file_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{file.filename}' exceeds the {max_file_size_mb} MB limit.",
            )

    batch, job = ingestion_use_case.create_image_batch_upload(
        db=db,
        case=case,
        files=files,
        title=title,
        generate_document=generate_document,
        run_authenticity_check=run_authenticity_check,
        created_by_user_id=current_user.id,
        background_tasks=background_tasks,
    )
    return {"batch": batch, "job": job}


@router.get("/case/{case_id}/image-batches", response_model=list[ImageDocumentBatchOut])
def list_case_image_batches(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)
    query = db.query(ImageDocumentBatch).filter(
        ImageDocumentBatch.case_id == case_id,
        ImageDocumentBatch.archived_at.is_(None),
    )
    return apply_tenant_scope(query, ImageDocumentBatch.tenant_id, current_user).order_by(
        ImageDocumentBatch.created_at.desc(), ImageDocumentBatch.id.desc()
    ).all()


@router.get("/case/{case_id}/image-batches/archived", response_model=list[ImageDocumentBatchOut])
def list_case_archived_image_batches(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)
    query = db.query(ImageDocumentBatch).filter(
        ImageDocumentBatch.case_id == case_id,
        ImageDocumentBatch.archived_at.isnot(None),
    )
    return apply_tenant_scope(query, ImageDocumentBatch.tenant_id, current_user).order_by(
        ImageDocumentBatch.archived_at.desc(), ImageDocumentBatch.id.desc()
    ).all()

@router.get("/image-batches/{batch_id}", response_model=ImageBatchDetailResponse)
def get_image_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    batch = get_tenant_image_batch_or_404(db=db, batch_id=batch_id, current_user=current_user)
    return image_document_service.to_batch_detail_payload(db=db, batch=batch)


@router.post("/image-batches/{batch_id}/archive", status_code=status.HTTP_200_OK)
def archive_image_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    batch = get_tenant_image_batch_or_404(db=db, batch_id=batch_id, current_user=current_user)
    batch.archived_at = func.now()
    db.commit()
    return {"message": "Image batch moved to archive", "batch_id": batch.id, "archived": True}


@router.post("/image-batches/{batch_id}/unarchive", status_code=status.HTTP_200_OK)
def unarchive_image_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    batch = get_tenant_image_batch_or_404(db=db, batch_id=batch_id, current_user=current_user)
    batch.archived_at = None
    db.commit()
    return {"message": "Image batch restored from archive", "batch_id": batch.id, "archived": False}


@router.get("/image-assets/{asset_id}/file")
def get_image_asset_file(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = get_tenant_image_asset_or_404(db=db, asset_id=asset_id, current_user=current_user)
    return stream_file_response(
        asset.storage_path,
        media_type=asset.mime_type or "application/octet-stream",
        filename=asset.filename,
    )
