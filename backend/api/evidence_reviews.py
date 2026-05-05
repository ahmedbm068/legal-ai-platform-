from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.document_schema import EvidenceAnalysisReviewOut
from backend.api.evidence_review_schema import EvidenceReviewDecisionRequest, EvidenceReviewListResponse
from backend.core.deps import get_current_user, get_db
from backend.core.permissions import apply_tenant_scope, require_lawyer
from backend.models.case import Case
from backend.models.evidence_analysis_review import EvidenceAnalysisReview
from backend.models.user import User
from backend.services.ai.image_document_service import image_document_service

router = APIRouter(prefix="/evidence-reviews", tags=["Evidence Reviews"])


def _get_tenant_case_or_404(db: Session, case_id: int, current_user: User) -> Case:
    query = db.query(Case).filter(Case.id == case_id, Case.deleted_at.is_(None))
    case = apply_tenant_scope(query, Case.tenant_id, current_user).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    return case


def _get_tenant_review_or_404(db: Session, review_id: int, current_user: User) -> EvidenceAnalysisReview:
    query = db.query(EvidenceAnalysisReview).filter(EvidenceAnalysisReview.id == review_id)
    review = apply_tenant_scope(query, EvidenceAnalysisReview.tenant_id, current_user).first()
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence review not found.")
    return review


@router.get("/case/{case_id}", response_model=EvidenceReviewListResponse)
def list_case_evidence_reviews(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)
    query = db.query(EvidenceAnalysisReview).filter(EvidenceAnalysisReview.case_id == case_id)
    rows = apply_tenant_scope(query, EvidenceAnalysisReview.tenant_id, current_user).order_by(
        EvidenceAnalysisReview.created_at.desc(),
        EvidenceAnalysisReview.id.desc(),
    ).all()
    return {
        "reviews": [
            image_document_service.to_review_public_payload(row)
            for row in rows
            if image_document_service.to_review_public_payload(row) is not None
        ]
    }


@router.post("/{review_id}/decision", response_model=EvidenceAnalysisReviewOut)
def decide_evidence_review(
    review_id: int,
    data: EvidenceReviewDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
):
    review = _get_tenant_review_or_404(db=db, review_id=review_id, current_user=current_user)
    updated = image_document_service.apply_review_decision(
        db=db,
        review=review,
        decision=data.decision,
        reviewed_by_user_id=current_user.id,
        note=data.note,
    )
    payload = image_document_service.to_review_public_payload(updated)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Review serialization failed.")
    return payload
