from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class AIResponseAuditLog(Base):
    __tablename__ = "ai_response_audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)

    endpoint = Column(String, nullable=False, index=True)
    parsed_intent = Column(String, nullable=True, index=True)
    response_version = Column(String, nullable=False, default="legal_trust_response_v1")
    model_name = Column(String, nullable=True)
    prompt_version = Column(String, nullable=True)

    question_text = Column(Text, nullable=False)
    answer_text = Column(Text, nullable=False)
    sources_json = Column(Text, nullable=True)
    trust_panel_json = Column(Text, nullable=True)
    validation_json = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    tenant = relationship("Tenant")
    user = relationship("User")
    case = relationship("Case")
    document = relationship("Document")
