from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.api.rag_schema import CopilotResponse
from backend.core.config import settings
from backend.core.deps import get_current_user, get_db
from backend.core.permissions import apply_tenant_scope
from backend.core.rate_limiter import limiter
from backend.models.case import Case
from backend.models.document import Document
from backend.models.document_chunk import DocumentChunk
from backend.models.user import User
from backend.services.ai.chunking_service import chunk_text
from backend.services.ai.extraction_service import extract_text_from_file
from backend.services.ai.llm_gateway import llm_gateway
from backend.services.ai.runtime_services import rag_service, shared_document_pipeline
from backend.services.ai.text_cleaning_service import normalize_text
from backend.services.draft_document_payload_service import build_draft_document_payload, is_drafting_request
from backend.services.storage_service import upload_file


router = APIRouter(prefix="/assistant", tags=["Assistant"])

MAX_ASSISTANT_UPLOAD_FILES = 10
TEMP_UPLOAD_TTL_MINUTES = 90
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}
SUPPORTED_CONTENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/x-markdown",
}


@dataclass
class TemporaryAssistantUpload:
    upload_id: str
    tenant_id: int
    user_id: int | None
    chat_session_id: str | None
    filename: str
    mime_type: str
    file_size: int
    extracted_text: str
    chunks: list[str]
    created_at: datetime


_TEMP_UPLOADS: dict[str, TemporaryAssistantUpload] = {}


class AssistantUploadedFileOut(BaseModel):
    id: str
    document_id: int | None = None
    filename: str
    file_size: int
    mime_type: str
    processing_status: str
    extracted_text_status: Literal["ready", "pending", "failed", "unsupported"]
    case_id: int | None = None
    temporary: bool = False
    error: str | None = None


class AssistantUploadResponse(BaseModel):
    uploaded_document_ids: list[str] = Field(default_factory=list)
    files: list[AssistantUploadedFileOut] = Field(default_factory=list)
    errors: list[AssistantUploadedFileOut] = Field(default_factory=list)


class AssistantAskWithFilesRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(..., min_length=1)
    case_id: int | None = Field(default=None, ge=1)
    chat_session_id: str | None = None
    uploaded_document_ids: list[str] = Field(default_factory=list, max_length=MAX_ASSISTANT_UPLOAD_FILES)
    top_k: int = Field(default=6, ge=1, le=10)
    use_external_research: bool = False
    mode: Literal["default", "legal_search"] = "default"
    legal_search_multilingual_output: bool = False
    reasoning_level: Literal["low", "medium", "high"] = "medium"
    agent_mode: bool = False
    conversation_history: list[dict[str, Any]] = Field(default_factory=list, max_length=30)


def _cleanup_temp_uploads() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=TEMP_UPLOAD_TTL_MINUTES)
    expired = [
        upload_id
        for upload_id, item in _TEMP_UPLOADS.items()
        if item.created_at < cutoff
    ]
    for upload_id in expired:
        _TEMP_UPLOADS.pop(upload_id, None)


def _get_tenant_case_or_404(db: Session, case_id: int, current_user: User) -> Case:
    query = db.query(Case).filter(Case.id == case_id, Case.deleted_at.is_(None))
    case = apply_tenant_scope(query, Case.tenant_id, current_user).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


def _normalize_content_type(file: UploadFile) -> str:
    return (file.content_type or "").split(";")[0].strip().lower()


def _file_size(file: UploadFile) -> int:
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    return size


def _validate_assistant_file(file: UploadFile) -> tuple[str, str]:
    filename = os.path.basename((file.filename or "").replace("\\", "/")).strip()
    if not filename:
        raise ValueError("Filename is required.")

    extension = Path(filename).suffix.lower()
    content_type = _normalize_content_type(file)
    if extension == ".docx":
        raise ValueError("DOCX extraction is not enabled on this server yet. Upload PDF, TXT, or MD.")
    if content_type.startswith("image/"):
        raise ValueError("Image OCR is not enabled for Assistant file attachments. Use the Documents image workflow.")
    if extension not in SUPPORTED_EXTENSIONS and content_type not in SUPPORTED_CONTENT_TYPES:
        raise ValueError("Unsupported file type. Upload PDF, TXT, or MD.")

    size = _file_size(file)
    max_file_size = max(1, int(settings.DOCUMENT_UPLOAD_MAX_MB)) * 1024 * 1024
    if size > max_file_size:
        raise ValueError(f"File too large. Maximum allowed size is {settings.DOCUMENT_UPLOAD_MAX_MB} MB.")

    if not content_type:
        content_type = {
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".md": "text/markdown",
        }.get(extension, "application/octet-stream")

    return filename, content_type


def _extract_upload_to_text(file: UploadFile, filename: str) -> str:
    suffix = Path(filename).suffix.lower() or ".bin"
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_path = temp_file.name
    try:
        with temp_file:
            shutil.copyfileobj(file.file, temp_file)
        file.file.seek(0)
        text = extract_text_from_file(temp_path, filename=filename, use_ocr_fallback=True)
        return normalize_text(text)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def _create_case_document(
    *,
    db: Session,
    case: Case,
    file: UploadFile,
    filename: str,
    content_type: str,
    file_size: int,
) -> tuple[Document, dict[str, Any]]:
    storage_path = upload_file(file.file, filename, prefix="documents")
    file.file.seek(0)
    document = Document(
        filename=filename,
        storage_path=storage_path,
        file_size=file_size,
        file_type=content_type,
        case_id=case.id,
        tenant_id=case.tenant_id,
        processing_status="queued",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    ai_result = shared_document_pipeline.process_document(document, db)
    db.refresh(document)
    return document, ai_result


def _source_from_chunk(
    *,
    document_id: int | None,
    case_id: int | None,
    filename: str,
    chunk_index: int,
    content: str,
    score: float,
) -> dict[str, Any]:
    return {
        "chunk_id": None,
        "document_id": document_id,
        "case_id": case_id,
        "filename": filename,
        "chunk_index": chunk_index,
        "score": round(float(score), 4),
        "snippet": content[:300],
        "chunk_text": content,
    }


def _tokenize(value: str) -> set[str]:
    return {token for token in re.findall(r"[A-Za-z0-9_]+", (value or "").lower()) if len(token) > 2}


def _rank_sources(question: str, sources: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    terms = _tokenize(question)
    wants_whole_document = any(
        word in (question or "").lower()
        for word in ("summarize", "summary", "compare", "all", "risks", "extract", "overview")
    )

    ranked: list[dict[str, Any]] = []
    for position, source in enumerate(sources):
        text = str(source.get("chunk_text") or source.get("snippet") or "")
        overlap = len(terms.intersection(_tokenize(text)))
        base_score = overlap / max(1, len(terms)) if terms else 0.0
        if wants_whole_document and position < max(10, top_k * 2):
            base_score = max(base_score, 0.45)
        ranked.append({**source, "score": max(float(source.get("score") or 0.0), base_score)})

    ranked.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    return ranked[: max(1, top_k)]


def _format_citations(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for source in sources:
        label = str(source.get("filename") or "Uploaded file")
        chunk_index = source.get("chunk_index")
        if chunk_index is not None:
            label = f"{label} - chunk {chunk_index}"
        key = (label, source.get("document_id"), source.get("case_id"))
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            {
                "label": label,
                "document_id": source.get("document_id"),
                "case_id": source.get("case_id"),
                "snippet": str(source.get("chunk_text") or source.get("snippet") or "")[:280],
            }
        )
    return citations


def _build_extract_fallback_answer(question: str, sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "I could not find extractable text in the uploaded documents."
    intro = "I found the following grounded excerpts in the uploaded documents:"
    bullets = [
        f"- {source.get('filename')}: {str(source.get('chunk_text') or source.get('snippet') or '').strip()[:420]}"
        for source in sources[:5]
    ]
    return "\n".join([intro, *bullets, "", "Lawyer review required before legal reliance."]).strip()


def _generate_answer(question: str, sources: list[dict[str, Any]], reasoning_level: str) -> tuple[str, bool, str | None]:
    if not sources:
        return "I could not find enough evidence in the uploaded documents.", True, "No usable uploaded document text"

    context = "\n\n---\n\n".join(
        f"[{source.get('filename')} - chunk {source.get('chunk_index')}]\n{source.get('chunk_text') or source.get('snippet') or ''}"
        for source in sources
    )[:18000]
    prompt = f"""
You are a legal AI assistant for lawyers.
Answer only from the uploaded document context below. If the uploaded files do not support the answer, say so clearly.
Use concise legal drafting. Mention source filenames where useful. Do not invent facts.
End with: Lawyer review required before legal reliance.

Question:
{question}

Uploaded document context:
{context}
""".strip()

    client = llm_gateway.create_client()
    if not client:
        return _build_extract_fallback_answer(question, sources), True, "No LLM provider API key is configured"

    try:
        tier = "heavy" if reasoning_level == "high" else "standard"
        response = client.responses.create(model=llm_gateway.resolve_model(tier), input=prompt)
        answer = llm_gateway.extract_output_text(response).strip()
        if answer:
            return answer, False, None
    except Exception as exc:
        return _build_extract_fallback_answer(question, sources), True, str(exc)

    return _build_extract_fallback_answer(question, sources), True, "LLM returned an empty answer"


@router.post("/upload", response_model=AssistantUploadResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
def upload_assistant_files(
    request: Request,
    response: Response,
    files: list[UploadFile] = File(...),
    case_id: int | None = Form(default=None),
    chat_session_id: str | None = Form(default=None),
    message: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _cleanup_temp_uploads()
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one file is required.")
    if len(files) > MAX_ASSISTANT_UPLOAD_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many files. Maximum allowed is {MAX_ASSISTANT_UPLOAD_FILES}.",
        )

    case = _get_tenant_case_or_404(db, case_id, current_user) if case_id is not None else None
    uploaded: list[AssistantUploadedFileOut] = []
    errors: list[AssistantUploadedFileOut] = []

    for file in files:
        raw_name = (file.filename or "file").strip() or "file"
        try:
            filename, content_type = _validate_assistant_file(file)
            size = _file_size(file)
            if case:
                document, ai_result = _create_case_document(
                    db=db,
                    case=case,
                    file=file,
                    filename=filename,
                    content_type=content_type,
                    file_size=size,
                )
                uploaded.append(
                    AssistantUploadedFileOut(
                        id=str(document.id),
                        document_id=document.id,
                        filename=document.filename,
                        file_size=document.file_size,
                        mime_type=document.file_type,
                        processing_status=document.processing_status,
                        extracted_text_status="ready" if document.extracted_text else "failed",
                        case_id=document.case_id,
                        temporary=False,
                        error=ai_result.get("error") or (None if document.extracted_text else ai_result.get("message")),
                    )
                )
            else:
                extracted_text = _extract_upload_to_text(file, filename)
                if not extracted_text.strip():
                    raise ValueError("No text could be extracted from the file.")
                chunks = chunk_text(
                    extracted_text,
                    chunk_size=max(300, int(settings.CHUNK_SIZE)),
                    overlap=max(0, int(settings.CHUNK_OVERLAP)),
                )
                upload_id = f"temp_{uuid.uuid4().hex}"
                _TEMP_UPLOADS[upload_id] = TemporaryAssistantUpload(
                    upload_id=upload_id,
                    tenant_id=current_user.tenant_id,
                    user_id=current_user.id,
                    chat_session_id=chat_session_id,
                    filename=filename,
                    mime_type=content_type,
                    file_size=size,
                    extracted_text=extracted_text,
                    chunks=chunks,
                    created_at=datetime.now(timezone.utc),
                )
                uploaded.append(
                    AssistantUploadedFileOut(
                        id=upload_id,
                        document_id=None,
                        filename=filename,
                        file_size=size,
                        mime_type=content_type,
                        processing_status="processed",
                        extracted_text_status="ready",
                        case_id=None,
                        temporary=True,
                    )
                )
        except Exception as exc:
            errors.append(
                AssistantUploadedFileOut(
                    id="",
                    document_id=None,
                    filename=raw_name,
                    file_size=0,
                    mime_type=_normalize_content_type(file) or "application/octet-stream",
                    processing_status="failed",
                    extracted_text_status="unsupported",
                    case_id=case_id,
                    temporary=case is None,
                    error=str(exc),
                )
            )

    return {
        "uploaded_document_ids": [item.id for item in uploaded],
        "files": uploaded,
        "errors": errors,
    }


@router.post("/ask-with-files", response_model=CopilotResponse)
@limiter.limit("30/minute")
def ask_with_files(
    request: Request,
    response: Response,
    data: AssistantAskWithFilesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _cleanup_temp_uploads()
    if not data.uploaded_document_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No uploaded document ids were provided.")
    if len(data.uploaded_document_ids) > MAX_ASSISTANT_UPLOAD_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many files. Maximum allowed is {MAX_ASSISTANT_UPLOAD_FILES}.",
        )

    case = _get_tenant_case_or_404(db, data.case_id, current_user) if data.case_id is not None else None
    source_candidates: list[dict[str, Any]] = []
    pending_files: list[str] = []

    for raw_id in data.uploaded_document_ids:
        upload_id = str(raw_id)
        if upload_id.isdigit():
            document = (
                db.query(Document)
                .filter(Document.id == int(upload_id), Document.tenant_id == current_user.tenant_id)
                .first()
            )
            if not document:
                continue
            if case is not None and document.case_id != case.id:
                continue
            if document.processing_status != "processed" or not document.extracted_text:
                shared_document_pipeline.process_document(document, db)
                db.refresh(document)
            if document.processing_status != "processed" or not document.extracted_text:
                pending_files.append(document.filename)
                continue
            chunks = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == document.id, DocumentChunk.tenant_id == current_user.tenant_id)
                .order_by(DocumentChunk.chunk_index.asc())
                .all()
            )
            if chunks:
                for chunk in chunks:
                    source_candidates.append(
                        _source_from_chunk(
                            document_id=document.id,
                            case_id=document.case_id,
                            filename=document.filename,
                            chunk_index=chunk.chunk_index,
                            content=chunk.content,
                            score=0.0,
                        )
                    )
            else:
                for index, chunk_body in enumerate(chunk_text(document.extracted_text)):
                    source_candidates.append(
                        _source_from_chunk(
                            document_id=document.id,
                            case_id=document.case_id,
                            filename=document.filename,
                            chunk_index=index,
                            content=chunk_body,
                            score=0.0,
                        )
                    )
            continue

        temp_upload = _TEMP_UPLOADS.get(upload_id)
        if not temp_upload:
            continue
        if temp_upload.tenant_id != current_user.tenant_id or temp_upload.user_id != current_user.id:
            continue
        if data.chat_session_id and temp_upload.chat_session_id and temp_upload.chat_session_id != data.chat_session_id:
            continue
        for index, chunk in enumerate(temp_upload.chunks):
            source_candidates.append(
                _source_from_chunk(
                    document_id=None,
                    case_id=None,
                    filename=temp_upload.filename,
                    chunk_index=index,
                    content=chunk,
                    score=0.0,
                )
            )

    if case is not None:
        case_results = rag_service.retrieve_context(
            db=db,
            tenant_id=current_user.tenant_id,
            question=data.message,
            top_k=max(2, min(data.top_k, 6)),
            case_id=case.id,
            document_id=None,
        )
        for item in case_results:
            source_candidates.append(
                _source_from_chunk(
                    document_id=item.get("document_id"),
                    case_id=item.get("case_id") or case.id,
                    filename=str(item.get("filename") or "Case document"),
                    chunk_index=int(item.get("chunk_index") or 0),
                    content=str(item.get("chunk_text") or item.get("snippet") or ""),
                    score=float(item.get("score") or 0.2),
                )
            )

    sources = _rank_sources(data.message, source_candidates, data.top_k)
    citations = _format_citations(sources)
    if pending_files and not sources:
        answer = "The uploaded documents are still processing: " + ", ".join(pending_files[:5])
        used_fallback = True
        fallback_reason = "Uploaded documents are still processing"
    else:
        answer, used_fallback, fallback_reason = _generate_answer(data.message, sources, data.reasoning_level)

    response = {
        "message": answer,
        "parsed_intent": "ask_uploaded_documents",
        "target_type": "case" if case else "assistant_upload",
        "target_id": case.id if case else None,
        "mode": data.mode,
        "agent_mode": data.agent_mode,
        "action_category": "analysis",
        "action_status": None,
        "permission_denied": False,
        "steps": [],
        "structured_result": {"uploaded_document_ids": data.uploaded_document_ids},
        "answer": answer,
        "used_fallback": used_fallback,
        "fallback_reason": fallback_reason,
        "confidence": "medium" if sources else "low",
        "scope": "case_uploads" if case else "temporary_uploads",
        "sources": [{key: value for key, value in source.items() if key != "chunk_text"} for source in sources],
        "citations": citations,
        "trust_panel": {
            "grounding": "uploaded_documents" if sources else "not_grounded",
            "human_review": "required",
            "pending_files": pending_files,
        },
        "execution_trace": [],
        "cache": {"key": None, "hit": False, "backend": "none"},
        "job_id": None,
        "case_snapshot_version": None,
        "artifact": None,
        "jurisdiction": None,
        "vision_result": None,
        "reasoning_result": None,
        "saved_asset_ids": [],
        "review_record_id": None,
    }
    if is_drafting_request(data.message, response["parsed_intent"], response["action_category"]):
        visible_sources = [{key: value for key, value in source.items() if key != "chunk_text"} for source in sources]
        response["open_editor"] = True
        response["draft_document"] = build_draft_document_payload(
            prompt=data.message,
            answer=answer,
            parsed_intent=response["parsed_intent"],
            case_id=case.id if case else None,
            sources=visible_sources,
            citations=citations,
        )
        response["message"] = "I drafted it and opened it in the editor."
    else:
        response["open_editor"] = False
        response["draft_document"] = None
    return response
