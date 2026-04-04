from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class ImageDocumentBatch(Base):
    __tablename__ = "image_document_batches"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    generated_document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)

    title = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued", server_default="queued", index=True)
    processing_error = Column(Text, nullable=True)
    asset_count = Column(Integer, nullable=False, default=0, server_default="0")
    generate_document = Column(Boolean, nullable=False, default=True, server_default="true")
    run_authenticity_check = Column(Boolean, nullable=False, default=False, server_default="false")
    ocr_provider = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    case = relationship("Case")
    created_by = relationship("User")
    generated_document = relationship("Document", foreign_keys=[generated_document_id])
