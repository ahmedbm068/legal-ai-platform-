from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    voice_recording_id = Column(Integer, ForeignKey("voice_recordings.id", ondelete="CASCADE"), nullable=True, index=True)
    consultation_request_id = Column(
        Integer,
        ForeignKey("consultation_requests.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    job_type = Column(String, nullable=False, index=True)
    queue_name = Column(String, nullable=False, default="default", server_default="default")
    status = Column(String, nullable=False, default="queued", server_default="queued", index=True)

    payload_json = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    max_attempts = Column(Integer, nullable=False, default=3, server_default="3")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    case = relationship("Case")
    document = relationship("Document")
    voice_recording = relationship("VoiceRecording")
    consultation_request = relationship("ConsultationRequest")
