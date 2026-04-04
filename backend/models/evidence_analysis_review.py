from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class EvidenceAnalysisReview(Base):
    __tablename__ = "evidence_analysis_reviews"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    image_asset_id = Column(Integer, ForeignKey("case_image_assets.id", ondelete="SET NULL"), nullable=True, index=True)
    image_batch_id = Column(Integer, ForeignKey("image_document_batches.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewed_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    status = Column(String, nullable=False, default="ready_for_review", server_default="ready_for_review", index=True)
    review_decision = Column(String, nullable=True, index=True)
    risk_score = Column(Integer, nullable=False, default=0, server_default="0")
    confidence = Column(String, nullable=False, default="low", server_default="low")
    analysis_text = Column(Text, nullable=False)
    signals_json = Column(Text, nullable=True)
    limitations_json = Column(Text, nullable=True)
    evidence_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    case = relationship("Case")
    image_asset = relationship("CaseImageAsset")
    image_batch = relationship("ImageDocumentBatch")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_user_id])
