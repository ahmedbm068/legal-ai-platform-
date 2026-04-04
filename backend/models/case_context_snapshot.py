from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class CaseContextSnapshot(Base):
    __tablename__ = "case_context_snapshots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "case_id", name="uq_case_context_snapshots_tenant_case"),
    )

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)

    version = Column(Integer, nullable=False, default=1, server_default="1")
    summary_text = Column(Text, nullable=True)
    snapshot_json = Column(Text, nullable=False)

    source_updated_at = Column(DateTime(timezone=True), nullable=True)
    refreshed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tenant = relationship("Tenant")
    case = relationship("Case")
