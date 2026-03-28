from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.consultation_schema import ConsultationFromTranscriptResponse, ConsultationRequestOut
from backend.core.deps import get_current_user, get_db
from backend.models.case import Case
from backend.models.consultation_request import ConsultationRequest
from backend.models.user import User
from backend.models.voice_recording import VoiceRecording
from backend.services.ai.transcript_intake_service import transcript_intake_service


router = APIRouter(prefix="/consultations", tags=["Consultations"])


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


def get_tenant_recording_or_404(db: Session, recording_id: int, current_user: User) -> VoiceRecording:
    recording = (
        db.query(VoiceRecording)
        .filter(
            VoiceRecording.id == recording_id,
            VoiceRecording.tenant_id == current_user.tenant_id
        )
        .first()
    )

    if not recording:
        raise HTTPException(status_code=404, detail="Voice recording not found")

    return recording


@router.get("/case/{case_id}", response_model=list[ConsultationRequestOut])
def list_case_consultation_requests(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)

    return (
        db.query(ConsultationRequest)
        .filter(
            ConsultationRequest.case_id == case_id,
            ConsultationRequest.tenant_id == current_user.tenant_id
        )
        .order_by(ConsultationRequest.created_at.desc(), ConsultationRequest.id.desc())
        .all()
    )


@router.post("/from-recording/{recording_id}", response_model=ConsultationFromTranscriptResponse)
def build_consultation_request_from_recording(
    recording_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    recording = get_tenant_recording_or_404(db=db, recording_id=recording_id, current_user=current_user)

    if not recording.transcript_text or not recording.transcript_text.strip():
        raise HTTPException(status_code=400, detail="Recording has no transcript text available.")

    payload = transcript_intake_service.build_intake(recording.transcript_text)

    consultation = (
        db.query(ConsultationRequest)
        .filter(
            ConsultationRequest.voice_recording_id == recording.id,
            ConsultationRequest.tenant_id == current_user.tenant_id
        )
        .first()
    )

    if not consultation:
        consultation = ConsultationRequest(
            case_id=recording.case_id,
            tenant_id=current_user.tenant_id,
            voice_recording_id=recording.id,
            issue_summary=payload["issue_summary"],
        )
        db.add(consultation)

    consultation.client_name = payload["client_name"]
    consultation.client_email = payload["client_email"]
    consultation.client_phone = payload["client_phone"]
    consultation.booking_intent = payload["booking_intent"]
    consultation.urgency_level = payload["urgency_level"]
    consultation.legal_area = payload["legal_area"]
    consultation.preferred_schedule = payload["preferred_schedule"]
    consultation.issue_summary = payload["issue_summary"]
    consultation.extracted_case_description = payload["extracted_case_description"]
    consultation.intake_notes = payload["intake_notes"]
    consultation.extraction_source = payload["extraction_source"]
    consultation.status = "ready_for_review"

    db.commit()
    db.refresh(consultation)

    return {
        "message": "Consultation request extracted from transcript successfully.",
        "consultation_request": consultation,
    }
