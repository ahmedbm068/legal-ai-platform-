from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func

from backend.database.database import Base


class LLMCallLog(Base):
    __tablename__ = "llm_call_log"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=True, index=True)
    call_id = Column(String(64), nullable=True, index=True)
    model = Column(String(120), nullable=False)
    api = Column(String(32), nullable=False, default="responses")
    duration_ms = Column(Float, nullable=False, default=0.0)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    extra_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now(), default=datetime.utcnow)
