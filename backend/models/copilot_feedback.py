from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class CopilotFeedback(Base):
    __tablename__ = "copilot_feedback"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)

    message_id = Column(String, nullable=True, index=True)
    parsed_intent = Column(String, nullable=True, index=True)
    confidence = Column(String, nullable=True)
    feedback_value = Column(String, nullable=False, index=True)  # up | down

    prompt_text = Column(Text, nullable=False)
    response_text = Column(Text, nullable=False)
    comment = Column(Text, nullable=True)
    root_cause = Column(String, nullable=True, index=True)
    legal_domain = Column(Boolean, nullable=True, index=True)
    jurisdiction = Column(String, nullable=True, index=True)
    source_count = Column(Integer, nullable=False, default=0)
    metadata_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    tenant = relationship("Tenant")
    user = relationship("User")
    case = relationship("Case")
    document = relationship("Document")
