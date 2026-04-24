from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvidenceStrength(str, Enum):
    STRONG = "STRONG"
    MEDIUM = "MEDIUM"
    WEAK = "WEAK"
    NONE = "NONE"


class ClaimSupportStatus(str, Enum):
    VERIFIED = "verified"
    PARTIALLY_SUPPORTED = "partially_supported"
    INFERRED = "inferred"
    UNSUPPORTED = "unsupported"


class SentenceSourceMapping(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    sentence: str
    source_label: str
    document_id: int | None = None
    chunk_id: int | None = None
    chunk_index: int | None = None
    exact_quote_span: str = ""
    quote: str = ""
    evidence_strength: EvidenceStrength = EvidenceStrength.NONE


class ClaimValidationItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    claim: str
    support_status: ClaimSupportStatus
    evidence_strength: EvidenceStrength = EvidenceStrength.NONE
    mappings: list[SentenceSourceMapping] = Field(default_factory=list)
    note: str = ""


class ContradictionSourceReference(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_label: str
    document_id: int | None = None
    chunk_id: int | None = None
    snippet: str = ""


class ContradictionRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    contradiction_type: str
    description: str
    conflicting_sources: list[ContradictionSourceReference] = Field(default_factory=list)
    severity_score: float = Field(default=0.0, ge=0.0, le=1.0)


class LegalReasoningSection(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str
    content: str
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    citation_coverage: float = Field(default=0.0, ge=0.0, le=1.0)


class TrustRiskSummary(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    client: str
    opposing_party: str


class TrustPanelResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    answer: str
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_strength: EvidenceStrength = EvidenceStrength.NONE
    verified_claims: list[ClaimValidationItem] = Field(default_factory=list)
    unsupported_claims: list[ClaimValidationItem] = Field(default_factory=list)
    sentence_to_source_mapping: list[SentenceSourceMapping] = Field(default_factory=list)
    contradictions: list[ContradictionRecord] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    risk_summary: TrustRiskSummary
    legal_reasoning_sections: list[LegalReasoningSection] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)


class OutputContractValidationResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    normalized_payload: dict[str, Any] = Field(default_factory=dict)
