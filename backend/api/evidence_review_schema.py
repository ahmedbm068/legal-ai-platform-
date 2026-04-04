from typing import Literal, List

from pydantic import BaseModel, ConfigDict, Field

from backend.api.document_schema import EvidenceAnalysisReviewOut


class EvidenceReviewDecisionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=2000)


class EvidenceReviewListResponse(BaseModel):
    reviews: List[EvidenceAnalysisReviewOut] = Field(default_factory=list)

