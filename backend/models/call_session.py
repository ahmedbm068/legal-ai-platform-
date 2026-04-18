from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class CallSession(Base):
    __tablename__ = "call_sessions"

    id = Column(Integer, primary_key=True, index=True)

    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    started_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    provider_name = Column(String, nullable=True)
    provider_call_id = Column(String, nullable=True, index=True)
    caller_phone = Column(String, nullable=True)
    client_phone = Column(String, nullable=True)

    call_status = Column(String, nullable=False, default="planned")
    recording_status = Column(String, nullable=False, default="waiting_for_audio")
    summary_status = Column(String, nullable=False, default="pending")

    consent_accepted = Column(Boolean, nullable=False, default=False)
    consent_accepted_at = Column(DateTime(timezone=True), nullable=True)
    consent_request_status = Column(String, nullable=False, default="not_requested")
    consent_requested_at = Column(DateTime(timezone=True), nullable=True)
    consent_message = Column(Text, nullable=True)
    consent_response_text = Column(Text, nullable=True)
    consent_responded_at = Column(DateTime(timezone=True), nullable=True)

    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    summary_text = Column(Text, nullable=True)
    transcript_text = Column(Text, nullable=True)
    conversation_transcript_text = Column(Text, nullable=True)
    transcript_source = Column(String, nullable=True)
    transcription_error = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    case = relationship("Case", back_populates="call_sessions")
    tenant = relationship("Tenant")
    client = relationship("Client")
    started_by = relationship("User")
    voice_recording = relationship("VoiceRecording", back_populates="call_session", uselist=False)