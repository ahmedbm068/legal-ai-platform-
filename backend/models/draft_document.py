from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class DraftDocument(Base):
    __tablename__ = "draft_documents"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    title = Column(String, nullable=False)
    document_type = Column(String, nullable=False, default="general")
    content_json = Column(Text, nullable=False, default="{}")
    content_html = Column(Text, nullable=False, default="")
    content_text = Column(Text, nullable=False, default="")
    status = Column(String, nullable=False, default="draft", index=True)
    source_context_json = Column(Text, nullable=True)
    citations_json = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    tenant = relationship("Tenant")
    case = relationship("Case")
    created_by_user = relationship("User")
    versions = relationship("DraftDocumentVersion", back_populates="draft_document", cascade="all, delete-orphan")
