from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.sql import func

from backend.database.database import Base


class RequestAuditLog(Base):
    """Captures every mutating HTTP request (POST/PUT/PATCH/DELETE)."""

    __tablename__ = "request_audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, nullable=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)

    method = Column(String(10), nullable=False, index=True)
    path = Column(String(512), nullable=False, index=True)
    status_code = Column(Integer, nullable=False, index=True)
    duration_ms = Column(Float, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
