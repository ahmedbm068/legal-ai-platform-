from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class CaseImageAsset(Base):
    __tablename__ = "case_image_assets"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("image_document_batches.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    filename = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    page_order = Column(Integer, nullable=True)
    source_scope = Column(String, nullable=False, default="case_batch", server_default="case_batch")
    processing_status = Column(String, nullable=False, default="queued", server_default="queued", index=True)
    processing_error = Column(Text, nullable=True)

    extracted_text = Column(Text, nullable=True)
    detected_language = Column(String, nullable=True)
    ocr_confidence = Column(Float, nullable=True)
    metadata_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tenant = relationship("Tenant")
    case = relationship("Case")
    batch = relationship("ImageDocumentBatch")
    created_by = relationship("User")

