from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class DraftDocumentVersion(Base):
    __tablename__ = "draft_document_versions"

    id = Column(Integer, primary_key=True, index=True)
    draft_document_id = Column(Integer, ForeignKey("draft_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False, index=True)
    content_json = Column(Text, nullable=False, default="{}")
    content_html = Column(Text, nullable=False, default="")
    content_text = Column(Text, nullable=False, default="")
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    change_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    draft_document = relationship("DraftDocument", back_populates="versions")
    created_by_user = relationship("User")
