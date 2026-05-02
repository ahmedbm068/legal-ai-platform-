from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class VoiceRecording(Base):
    __tablename__ = "voice_recordings"

    id = Column(Integer, primary_key=True, index=True)

    filename = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)

    transcription_status = Column(String, nullable=False, default="pending")
    transcription_error = Column(Text, nullable=True)
    transcript_text = Column(Text, nullable=True)
    conversation_transcript_text = Column(Text, nullable=True)
    transcript_source = Column(String, nullable=True)
    transcript_language = Column(String, nullable=True)
    recording_kind = Column(String, nullable=False, default="voice_note")
    call_session_id = Column(Integer, ForeignKey("call_sessions.id", ondelete="SET NULL"), nullable=True, unique=True, index=True)

    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    case = relationship("Case", back_populates="voice_recordings")
    tenant = relationship("Tenant")
    uploaded_by = relationship("User")
    call_session = relationship("CallSession", back_populates="voice_recording")
