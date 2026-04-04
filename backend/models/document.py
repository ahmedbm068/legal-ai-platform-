from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from backend.database.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)

    filename = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)

    processing_status = Column(String, nullable=False, default="pending")
    processing_error = Column(Text, nullable=True)

    file_size = Column(Integer, nullable=False)
    file_type = Column(String, nullable=False)
    upload_timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    source_image_batch_id = Column(Integer, nullable=True, index=True)

    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    extracted_text = Column(Text, nullable=True)
    redacted_text = Column(Text, nullable=True)

    summary = Column(Text, nullable=True)
    summary_short = Column(Text, nullable=True)
    summary_status = Column(String, nullable=False, default="not_started")
    summary_error = Column(Text, nullable=True)
    summary_generated_at = Column(DateTime(timezone=True), nullable=True)

    document_type = Column(String, nullable=True)
    summary_version = Column(String, nullable=True)
    summary_source = Column(String, nullable=True)
    insights_json = Column(Text, nullable=True)
    last_intelligence_run_at = Column(DateTime(timezone=True), nullable=True)

    case = relationship("Case", back_populates="documents")
    tenant = relationship("Tenant")

    chunks = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan"
    )

    entities = relationship(
        "DocumentEntity",
        back_populates="document",
        cascade="all, delete-orphan"
    )
