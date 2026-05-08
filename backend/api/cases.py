from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from backend.core.permissions import apply_tenant_scope, is_admin, require_lawyer
from backend.core.deps import get_db, get_current_user
from backend.models.case import Case
from backend.models.user import User
from backend.models.client import Client
from backend.api.case_schema import CaseCreate, CaseUpdate, CaseOut
from backend.api.voice_schema import VoiceUploadResponse
from backend.services.ai.agents.summarization_agent import summarization_agent
from backend.services.ai.agents.chronology_agent import chronology_agent
from backend.services.ai.case_context_service import case_context_service
from backend.services.ai.big_agents import big_agent_registry
from backend.services.ai.document_review_table_service import (
    DEFAULT_QUESTION_KINDS,
    VALID_QUESTION_KINDS,
    document_review_table_service,
)
from backend.services.ai.workflow_blueprint_service import (
    derive_case_flags,
    workflow_blueprint_service,
)
from backend.models.document import Document
from backend.services.use_cases.ingestion_use_case import ingestion_use_case

_ALLOWED_AUDIO_CONTENT_TYPES = {
    "audio/webm", "audio/wav", "audio/x-wav", "audio/mpeg",
    "audio/mp4", "audio/mp3", "audio/ogg", "audio/x-m4a", "audio/m4a",
}
_ALLOWED_AUDIO_EXTENSIONS = {".webm", ".wav", ".mp3", ".mp4", ".ogg", ".m4a"}

router = APIRouter(prefix="/cases", tags=["Cases"])


@router.post("/", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
def create_case(
    case_data: CaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer)
):

    client_query = db.query(Client).filter(
        Client.id == case_data.client_id,
        Client.deleted_at.is_(None)
    )
    client = apply_tenant_scope(client_query, Client.tenant_id, current_user).first()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    resolved_tenant_id = client.tenant_id if is_admin(current_user) else current_user.tenant_id

    new_case = Case(
        title=case_data.title,
        description=case_data.description,
        status=case_data.status,
        jurisdiction_country=case_data.jurisdiction_country.value
        if hasattr(case_data.jurisdiction_country, "value")
        else str(case_data.jurisdiction_country),
        tenant_id=resolved_tenant_id,
        lawyer_id=current_user.id,
        client_id=case_data.client_id
    )

    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    return new_case


@router.get("/", response_model=list[CaseOut])
def list_cases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Case).filter(Case.deleted_at.is_(None))
    return apply_tenant_scope(query, Case.tenant_id, current_user).all()


@router.get("/{case_id}", response_model=CaseOut)
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Case).filter(
        Case.id == case_id,
        Case.deleted_at.is_(None)
    )
    case = apply_tenant_scope(query, Case.tenant_id, current_user).first()

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    return case


@router.put("/{case_id}", response_model=CaseOut)
def update_case(
    case_id: int,
    case_data: CaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer)
):

    case_query = db.query(Case).filter(
        Case.id == case_id,
        Case.deleted_at.is_(None)
    )
    case = apply_tenant_scope(case_query, Case.tenant_id, current_user).first()

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if current_user.role != UserRole.admin and case.lawyer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your assigned cases"
        )

    if case_data.client_id is not None:
        client_query = db.query(Client).filter(
            Client.id == case_data.client_id,
            Client.deleted_at.is_(None)
        )
        client = apply_tenant_scope(client_query, Client.tenant_id, current_user).first()

        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        case.client_id = case_data.client_id
        if is_admin(current_user):
            case.tenant_id = client.tenant_id

    if case_data.title is not None:
        case.title = case_data.title

    if case_data.description is not None:
        case.description = case_data.description

    if case_data.status is not None:
        case.status = case_data.status

    if case_data.jurisdiction_country is not None:
        case.jurisdiction_country = (
            case_data.jurisdiction_country.value
            if hasattr(case_data.jurisdiction_country, "value")
            else str(case_data.jurisdiction_country)
        )

    db.commit()
    db.refresh(case)

    return case


@router.delete("/{case_id}", status_code=status.HTTP_200_OK)
def delete_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer)
):

    query = db.query(Case).filter(
        Case.id == case_id,
        Case.deleted_at.is_(None)
    )
    case = apply_tenant_scope(query, Case.tenant_id, current_user).first()

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if current_user.role != UserRole.admin and case.lawyer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your assigned cases"
        )

    case.deleted_at = func.now()
    db.commit()

    return {"message": "Case archived successfully"}


@router.post("/{case_id}/summarize", response_model=dict)
def summarize_case(
    case_id: int,
    num_bullets: int = 8,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Case).filter(
        Case.id == case_id,
        Case.deleted_at.is_(None)
    )
    case = apply_tenant_scope(query, Case.tenant_id, current_user).first()

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    documents = []
    for doc in case.documents:
        if doc.extracted_text:
            documents.append({"filename": doc.filename, "content": doc.extracted_text})

    if not documents:
        raise HTTPException(status_code=400, detail="No documents with extracted text found for this case.")

    summary = summarization_agent.summarize_case(
        case_id=case_id, documents=documents, num_bullets=num_bullets
    )

    if not summary:
        raise HTTPException(status_code=500, detail="Failed to generate summary.")

    return summary


@router.post("/{case_id}/chronology", response_model=dict)
def get_case_chronology(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Case).filter(
        Case.id == case_id,
        Case.deleted_at.is_(None)
    )
    case = apply_tenant_scope(query, Case.tenant_id, current_user).first()

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    documents = []
    for doc in case.documents:
        if doc.extracted_text:
            documents.append({"filename": doc.filename, "content": doc.extracted_text})

    if not documents:
        raise HTTPException(status_code=400, detail="No documents with extracted text found for this case.")

    chronology = chronology_agent.extract_chronology_from_case(
        case_id=case_id, documents=documents
    )

    if not chronology:
        raise HTTPException(status_code=500, detail="Failed to generate chronology.")

    return chronology


@router.get("/{case_id}/workspace", response_model=dict)
def get_case_workspace(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Phase A1 — Lawyer Workspace v2 aggregation endpoint.

    Returns a single payload combining:
      * core case metadata (id, title, status, jurisdiction, counts)
      * timeline events (documents / consultations / recordings)
      * computed risk signals (from document insights + urgent consultations)
      * memory snapshot (recent intent counts)
      * the catalog of Big Agents available for this workspace
        (so the UI can render a "what can I do here?" rail)

    Tenant scope is enforced through ``apply_tenant_scope`` and the
    ``case_context_service`` itself filters by ``tenant_id``.
    """

    query = db.query(Case).filter(
        Case.id == case_id,
        Case.deleted_at.is_(None),
    )
    case = apply_tenant_scope(query, Case.tenant_id, current_user).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    context = case_context_service.build_context(
        db=db,
        tenant_id=current_user.tenant_id,
        case_id=case_id,
    )

    big_agents_payload = [agent.to_dict() for agent in big_agent_registry.list_all()]

    return {
        "case_id": case_id,
        "scope": context.get("scope", "case"),
        "case": context.get("case"),
        "timeline": context.get("timeline", []),
        "risk_signals": context.get("risk_signals", []),
        "memory": context.get("memory", {}),
        "big_agents": big_agents_payload,
    }


@router.get("/{case_id}/review-table", response_model=dict)
def get_case_review_table(
    case_id: int,
    questions: str | None = Query(
        default=None,
        description=(
            "Comma-separated list of question kinds. "
            "Defaults to: document_type,parties,key_dates,legal_risks,missing_evidence."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Phase A3 — Vault-style document review table.

    Returns a matrix where each row is a document in the case and each
    column is a lawyer-defined question. Cells are resolved deterministically
    from each document's cached ``insights_json``. No LLM call.
    """

    case_query = db.query(Case).filter(
        Case.id == case_id,
        Case.deleted_at.is_(None),
    )
    case = apply_tenant_scope(case_query, Case.tenant_id, current_user).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if questions is None or not questions.strip():
        kinds: tuple[str, ...] = DEFAULT_QUESTION_KINDS
    else:
        requested = [item.strip() for item in questions.split(",") if item.strip()]
        unknown = [k for k in requested if k not in VALID_QUESTION_KINDS]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown question kinds: {', '.join(unknown)}",
            )
        kinds = tuple(requested)

    question_tuple = document_review_table_service.build_questions(kinds=kinds)

    documents = (
        db.query(Document)
        .filter(
            Document.case_id == case.id,
            Document.tenant_id == current_user.tenant_id,
        )
        .order_by(Document.upload_timestamp.desc(), Document.id.desc())
        .all()
    )

    doc_payload = [
        {
            "id": doc.id,
            "filename": doc.filename,
            "insights_json": doc.insights_json,
        }
        for doc in documents
    ]

    table = document_review_table_service.build_table(
        case_id=case.id,
        documents=doc_payload,
        questions=question_tuple,
    )
    return table.to_dict()


@router.get("/{case_id}/workflows", response_model=dict)
def list_case_workflows(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Phase A4 — Workflow blueprint catalog for a case.

    Returns the full blueprint catalog plus per-blueprint availability
    (``available`` or ``blocked`` with the missing prerequisites). Pure
    metadata — no execution.
    """

    case_query = db.query(Case).filter(
        Case.id == case_id,
        Case.deleted_at.is_(None),
    )
    case = apply_tenant_scope(case_query, Case.tenant_id, current_user).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    document_count = (
        db.query(Document)
        .filter(
            Document.case_id == case.id,
            Document.tenant_id == current_user.tenant_id,
        )
        .count()
    )

    case_payload = {
        "title": case.title,
        "jurisdiction_country": case.jurisdiction_country,
        "document_count": document_count,
    }
    flags = derive_case_flags(case_payload)
    blueprints = workflow_blueprint_service.list_blueprints()
    availability = workflow_blueprint_service.availability_for_case(case_flags=flags)

    return {
        "case_id": case.id,
        "case_flags": flags,
        "blueprints": [bp.to_dict() for bp in blueprints],
        "availability": [a.to_dict() for a in availability],
    }


@router.get("/{case_id}/workflows/{blueprint_id}", response_model=dict)
def preview_case_workflow(
    case_id: int,
    blueprint_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return a single workflow blueprint preview with case-aware availability."""

    case_query = db.query(Case).filter(
        Case.id == case_id,
        Case.deleted_at.is_(None),
    )
    case = apply_tenant_scope(case_query, Case.tenant_id, current_user).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    blueprint = workflow_blueprint_service.get(blueprint_id)
    if blueprint is None:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow blueprint not found: {blueprint_id}",
        )

    document_count = (
        db.query(Document)
        .filter(
            Document.case_id == case.id,
            Document.tenant_id == current_user.tenant_id,
        )
        .count()
    )
    case_payload = {
        "title": case.title,
        "jurisdiction_country": case.jurisdiction_country,
        "document_count": document_count,
    }
    flags = derive_case_flags(case_payload)
    availability = workflow_blueprint_service.check_prerequisites(
        blueprint_id=blueprint_id,
        case_flags=flags,
    )
    return {
        "case_id": case.id,
        "case_flags": flags,
        "blueprint": blueprint.to_dict(),
        "availability": availability.to_dict(),
    }


@router.post("/{case_id}/voice/upload", response_model=VoiceUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_voice_for_case(
    case_id: int,
    background_tasks: BackgroundTasks,
    recording_kind: str = Form(default="voice_note"),
    call_session_id: int | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Phase A2 — case-scoped voice upload alias.

    Mirrors POST /voice/upload but with case_id in the path so the URL
    matches the spec: /cases/{case_id}/voice/upload.
    """
    case_query = db.query(Case).filter(Case.id == case_id, Case.deleted_at.is_(None))
    case = apply_tenant_scope(case_query, Case.tenant_id, current_user).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    normalized_ct = (file.content_type or "").split(";")[0].strip().lower()
    ext = Path(file.filename).suffix.lower()
    if normalized_ct not in _ALLOWED_AUDIO_CONTENT_TYPES and ext not in _ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported audio format. Use webm, wav, mp3, mp4, or ogg.")

    recording, job_payload = ingestion_use_case.create_voice_upload(
        db=db,
        case=case,
        file=file,
        uploaded_by_user_id=current_user.id,
        call_session_id=call_session_id,
        recording_kind=recording_kind,
        background_tasks=background_tasks,
    )
    message = (
        "Call recording uploaded. Transcription is queued."
        if recording.recording_kind == "call_recording"
        else "Voice recording uploaded. Transcription is queued."
    )
    return {"recording": recording, "message": message, "job": job_payload}


@router.get("/{case_id}/parties", response_model=dict)
def get_case_parties(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Phase A3 — party-role mapping from document insights.

    Aggregates parties_detected from each document's cached insights_json.
    No LLM call — pure read from already-extracted data.
    """
    case_query = db.query(Case).filter(Case.id == case_id, Case.deleted_at.is_(None))
    case = apply_tenant_scope(case_query, Case.tenant_id, current_user).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    documents = (
        db.query(Document)
        .filter(Document.case_id == case.id, Document.tenant_id == current_user.tenant_id)
        .order_by(Document.upload_timestamp.desc(), Document.id.desc())
        .all()
    )

    seen: set[str] = set()
    parties: list[dict] = []
    for doc in documents:
        insights = doc.insights_json or {}
        for party in insights.get("parties_detected") or []:
            name = str(party or "").strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                parties.append({"name": name, "source_document": doc.filename, "role": None})

    return {
        "case_id": case_id,
        "party_count": len(parties),
        "parties": parties,
        "documents_scanned": len(documents),
    }


@router.get("/{case_id}/obligations", response_model=dict)
def get_case_obligations(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Phase A3 — obligation extraction from document insights.

    Aggregates important_dates and legal_risks from each document's
    cached insights_json. No LLM call.
    """
    case_query = db.query(Case).filter(Case.id == case_id, Case.deleted_at.is_(None))
    case = apply_tenant_scope(case_query, Case.tenant_id, current_user).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    documents = (
        db.query(Document)
        .filter(Document.case_id == case.id, Document.tenant_id == current_user.tenant_id)
        .order_by(Document.upload_timestamp.desc(), Document.id.desc())
        .all()
    )

    deadlines: list[dict] = []
    obligations: list[dict] = []

    for doc in documents:
        insights = doc.insights_json or {}
        for date_item in insights.get("important_dates") or []:
            label = str(date_item.get("label") or "").strip()
            value = str(date_item.get("value") or "").strip()
            if label or value:
                deadlines.append({"label": label, "value": value, "source_document": doc.filename})
        for risk in insights.get("legal_risks") or []:
            text = str(risk or "").strip()
            if text:
                obligations.append({"description": text, "source_document": doc.filename, "type": "legal_risk"})

    return {
        "case_id": case_id,
        "deadline_count": len(deadlines),
        "obligation_count": len(obligations),
        "deadlines": deadlines,
        "obligations": obligations,
        "documents_scanned": len(documents),
    }
