from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)

    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    lawyer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    consultation_request_id = Column(
        Integer,
        ForeignKey("consultation_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    appointment_type = Column(String, nullable=False, default="meeting")
    visibility_scope = Column(String, nullable=False, default="shared")
    status = Column(String, nullable=False, default="scheduled")
    scheduled_at = Column(DateTime(timezone=True), nullable=False, index=True)
    duration_minutes = Column(Integer, nullable=False, default=30)
    location = Column(String, nullable=True)
    timezone_name = Column(String, nullable=False, default="UTC")
    ai_summary = Column(Text, nullable=True)
    ai_recommendation = Column(Text, nullable=True)
    ai_confidence = Column(String, nullable=True)
    ai_source = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    case = relationship("Case", back_populates="appointments")
    tenant = relationship("Tenant")
    lawyer = relationship("User", foreign_keys=[lawyer_id])
    client = relationship("Client")
    consultation_request = relationship("ConsultationRequest")
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
