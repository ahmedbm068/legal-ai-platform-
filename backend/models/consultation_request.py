from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class ConsultationRequest(Base):
    __tablename__ = "consultation_requests"

    id = Column(Integer, primary_key=True, index=True)

    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    voice_recording_id = Column(Integer, ForeignKey("voice_recordings.id", ondelete="SET NULL"), nullable=True, index=True)

    client_name = Column(String, nullable=True)
    client_email = Column(String, nullable=True)
    client_phone = Column(String, nullable=True)
    booking_intent = Column(String, nullable=False, default="not_detected")
    urgency_level = Column(String, nullable=False, default="normal")
    legal_area = Column(String, nullable=True)
    preferred_schedule = Column(String, nullable=True)
    issue_summary = Column(Text, nullable=False)
    extracted_case_description = Column(Text, nullable=True)
    intake_notes = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="new")
    extraction_source = Column(String, nullable=True)
    public_reference = Column(String, nullable=True, unique=True, index=True)
    source_channel = Column(String, nullable=False, default="internal")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    case = relationship("Case", back_populates="consultation_requests")
    tenant = relationship("Tenant")
    voice_recording = relationship("VoiceRecording")
