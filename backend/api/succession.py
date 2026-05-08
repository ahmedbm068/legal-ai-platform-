"""REST endpoint for the Tunisian succession entitlement calculator."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.api.succession_schema import (
    SuccessionCalculateRequest,
    SuccessionCalculateResponse,
)
from backend.core.deps import get_current_user, get_db
from backend.core.rate_limiter import limiter
from backend.models.user import User
from backend.services.legal.succession_calculator import compute


router = APIRouter(prefix="/ai/succession", tags=["AI"])


@router.post("/calculate", response_model=SuccessionCalculateResponse)
@limiter.limit("60/minute")
def calculate(
    request: Request,
    data: SuccessionCalculateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compute per-heir entitlement under Tunisian CSP arts 85–152.

    Pure deterministic rules engine — no LLM call, no DB write. Any
    deviation from canonical CSP outcomes is a calculator bug. The lawyer
    remains responsible for verifying the official article wording before
    relying on the result.
    """
    _ = (db, current_user)  # auth already enforced by Depends; kept for parity
    result = compute(data.to_input())
    return SuccessionCalculateResponse.from_result(result)
