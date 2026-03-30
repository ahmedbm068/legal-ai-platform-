from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class GeneratedArtifactVersion(Base):
    __tablename__ = "generated_artifact_versions"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)

    artifact_type = Column(String, nullable=False, index=True)  # document_summary | case_email
    version_number = Column(Integer, nullable=False, default=1)
    content = Column(Text, nullable=False)
    source_kind = Column(String, nullable=False, default="agent_generation")
    edit_instruction = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)

    is_selected = Column(Boolean, nullable=False, default=False, index=True)

    parent_version_id = Column(
        Integer,
        ForeignKey("generated_artifact_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tenant = relationship("Tenant")
    case = relationship("Case")
    document = relationship("Document")
    parent_version = relationship("GeneratedArtifactVersion", remote_side=[id])
    created_by = relationship("User")

