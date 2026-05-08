"""Pydantic schemas for the Tunisian succession calculator endpoint."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.services.legal.succession_calculator import (
    SuccessionInput,
    SuccessionResult,
)


class SuccessionCalculateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    spouse_kind: Literal["husband", "wife", "none"] = "none"
    sons: int = Field(default=0, ge=0, le=20)
    daughters: int = Field(default=0, ge=0, le=20)
    father_alive: bool = False
    mother_alive: bool = False
    full_brothers: int = Field(default=0, ge=0, le=20)
    full_sisters: int = Field(default=0, ge=0, le=20)
    paternal_brothers: int = Field(default=0, ge=0, le=20)
    paternal_sisters: int = Field(default=0, ge=0, le=20)
    maternal_siblings: int = Field(default=0, ge=0, le=20)
    estate_value_tnd: Optional[float] = Field(default=None, ge=0.0)

    def to_input(self) -> SuccessionInput:
        return SuccessionInput(
            spouse_kind=self.spouse_kind,
            sons=self.sons,
            daughters=self.daughters,
            father_alive=self.father_alive,
            mother_alive=self.mother_alive,
            full_brothers=self.full_brothers,
            full_sisters=self.full_sisters,
            paternal_brothers=self.paternal_brothers,
            paternal_sisters=self.paternal_sisters,
            maternal_siblings=self.maternal_siblings,
            estate_value_tnd=self.estate_value_tnd,
        )


class SuccessionHeirOut(BaseModel):
    heir: str
    share_fraction: str        # e.g. "1/8" — keeps the exact rational value
    share_percent: float
    share_amount_tnd: Optional[float] = None
    article_refs: list[str]
    reasoning: str


class SuccessionCitationOut(BaseModel):
    article: str
    code_name: str
    summary: str
    snippet: str = ""
    url: Optional[str] = None


class SuccessionCalculateResponse(BaseModel):
    heirs: list[SuccessionHeirOut]
    total_distributed: str     # Fraction serialised as "n/d"
    total_percent: float
    radd_applied: bool
    awl_applied: bool
    notes: list[str]
    citations: list[SuccessionCitationOut]

    @classmethod
    def from_result(cls, result: SuccessionResult) -> "SuccessionCalculateResponse":
        return cls(
            heirs=[
                SuccessionHeirOut(
                    heir=h.heir,
                    share_fraction=str(h.share_fraction),
                    share_percent=h.share_percent,
                    share_amount_tnd=h.share_amount_tnd,
                    article_refs=list(h.article_refs),
                    reasoning=h.reasoning,
                )
                for h in result.heirs
            ],
            total_distributed=str(result.total_distributed),
            total_percent=round(float(result.total_distributed) * 100.0, 6),
            radd_applied=result.radd_applied,
            awl_applied=result.awl_applied,
            notes=list(result.notes),
            citations=[
                SuccessionCitationOut(
                    article=c.article,
                    code_name=c.code_name,
                    summary=c.summary,
                    snippet=c.snippet,
                    url=c.url,
                )
                for c in result.citations
            ],
        )
