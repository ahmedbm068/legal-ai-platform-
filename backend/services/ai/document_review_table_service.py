"""Phase A3 — Document review table service ("Vault-style").

Builds a side-by-side review matrix where rows are documents and columns
are lawyer-defined questions. Each cell is resolved deterministically
from the cached ``insights_json`` payload produced upstream by
``document_insight_service.build_insights``.

No LLM. No IO. The cells are pure projections of pre-computed insights,
which means the table renders instantly in the UI and is fully testable
in isolation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping


# ──────────────────────────────────────────────────────────────────────────
# Question taxonomy — keys mirror well-known fields in
# ``document_insight_service.build_insights`` output.
# ──────────────────────────────────────────────────────────────────────────

QUESTION_KIND_KEY_DATES = "key_dates"
QUESTION_KIND_PARTIES = "parties"
QUESTION_KIND_PAYMENT_TERMS = "payment_terms"
QUESTION_KIND_TERMINATION_TERMS = "termination_terms"
QUESTION_KIND_LEGAL_RISKS = "legal_risks"
QUESTION_KIND_MISSING_EVIDENCE = "missing_evidence"
QUESTION_KIND_KEY_POINTS = "key_points"
QUESTION_KIND_SUMMARY = "summary"
QUESTION_KIND_DOCUMENT_TYPE = "document_type"
QUESTION_KIND_RECOMMENDED_ACTIONS = "recommended_actions"

VALID_QUESTION_KINDS: frozenset[str] = frozenset(
    {
        QUESTION_KIND_KEY_DATES,
        QUESTION_KIND_PARTIES,
        QUESTION_KIND_PAYMENT_TERMS,
        QUESTION_KIND_TERMINATION_TERMS,
        QUESTION_KIND_LEGAL_RISKS,
        QUESTION_KIND_MISSING_EVIDENCE,
        QUESTION_KIND_KEY_POINTS,
        QUESTION_KIND_SUMMARY,
        QUESTION_KIND_DOCUMENT_TYPE,
        QUESTION_KIND_RECOMMENDED_ACTIONS,
    }
)


# Default column set when caller doesn't specify questions.
DEFAULT_QUESTION_KINDS: tuple[str, ...] = (
    QUESTION_KIND_DOCUMENT_TYPE,
    QUESTION_KIND_PARTIES,
    QUESTION_KIND_KEY_DATES,
    QUESTION_KIND_LEGAL_RISKS,
    QUESTION_KIND_MISSING_EVIDENCE,
)

# Human-readable column labels for default kinds.
_DEFAULT_LABELS: dict[str, str] = {
    QUESTION_KIND_KEY_DATES: "Key dates",
    QUESTION_KIND_PARTIES: "Parties",
    QUESTION_KIND_PAYMENT_TERMS: "Payment terms",
    QUESTION_KIND_TERMINATION_TERMS: "Termination terms",
    QUESTION_KIND_LEGAL_RISKS: "Legal risks",
    QUESTION_KIND_MISSING_EVIDENCE: "Missing evidence",
    QUESTION_KIND_KEY_POINTS: "Key points",
    QUESTION_KIND_SUMMARY: "Summary",
    QUESTION_KIND_DOCUMENT_TYPE: "Document type",
    QUESTION_KIND_RECOMMENDED_ACTIONS: "Recommended actions",
}

# Evidence strength for each kind given a non-empty value. Tracks how
# much we trust the underlying extractor.
_STRENGTH_BY_KIND: dict[str, str] = {
    QUESTION_KIND_DOCUMENT_TYPE: "strong",
    QUESTION_KIND_PARTIES: "strong",
    QUESTION_KIND_KEY_DATES: "strong",
    QUESTION_KIND_PAYMENT_TERMS: "medium",
    QUESTION_KIND_TERMINATION_TERMS: "medium",
    QUESTION_KIND_LEGAL_RISKS: "medium",
    QUESTION_KIND_MISSING_EVIDENCE: "medium",
    QUESTION_KIND_KEY_POINTS: "medium",
    QUESTION_KIND_SUMMARY: "medium",
    QUESTION_KIND_RECOMMENDED_ACTIONS: "weak",
}


@dataclass(frozen=True)
class ReviewQuestion:
    id: str
    label: str
    kind: str


@dataclass(frozen=True)
class ReviewCell:
    question_id: str
    kind: str
    values: tuple[str, ...]
    evidence_strength: str  # "strong" | "medium" | "weak" | "none"
    is_empty: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "kind": self.kind,
            "values": list(self.values),
            "evidence_strength": self.evidence_strength,
            "is_empty": self.is_empty,
        }


@dataclass(frozen=True)
class ReviewRow:
    document_id: int | None
    filename: str
    document_type: str | None
    cells: tuple[ReviewCell, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "filename": self.filename,
            "document_type": self.document_type,
            "cells": [cell.to_dict() for cell in self.cells],
        }


@dataclass(frozen=True)
class ReviewTable:
    case_id: int | None
    questions: tuple[ReviewQuestion, ...]
    rows: tuple[ReviewRow, ...]
    coverage: float = 0.0  # share of cells that resolved to non-empty values

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "questions": [asdict(q) for q in self.questions],
            "rows": [row.to_dict() for row in self.rows],
            "coverage": round(self.coverage, 4),
        }


class DocumentReviewTableService:
    """Stateless. See module docstring."""

    def build_questions(
        self,
        kinds: Iterable[str] | None = None,
        custom_labels: Mapping[str, str] | None = None,
    ) -> tuple[ReviewQuestion, ...]:
        """Resolve a list of question kinds (or default) into ``ReviewQuestion``s.

        Unknown kinds are skipped silently — the API layer should reject
        them earlier with a 400 if strict validation is desired.
        """

        chosen: list[str] = []
        seen: set[str] = set()
        for kind in (kinds or DEFAULT_QUESTION_KINDS):
            kind_norm = (kind or "").strip()
            if kind_norm not in VALID_QUESTION_KINDS or kind_norm in seen:
                continue
            seen.add(kind_norm)
            chosen.append(kind_norm)

        labels = dict(custom_labels or {})
        questions: list[ReviewQuestion] = []
        for kind in chosen:
            label = labels.get(kind) or _DEFAULT_LABELS.get(kind) or kind
            questions.append(ReviewQuestion(id=kind, label=label, kind=kind))
        return tuple(questions)

    def build_table(
        self,
        *,
        case_id: int | None,
        documents: Iterable[Mapping[str, Any]],
        questions: Iterable[ReviewQuestion] | None = None,
    ) -> ReviewTable:
        """Project the per-document insights onto the question matrix.

        Each ``documents`` entry must expose at least:
          * ``id`` (int | None)
          * ``filename`` (str)
          * ``insights`` (dict) OR ``insights_json`` (JSON string)

        Missing / unparseable insights yield empty cells with
        ``evidence_strength="none"`` — never raise.
        """

        question_tuple = tuple(questions) if questions is not None else self.build_questions()
        rows: list[ReviewRow] = []
        total_cells = 0
        non_empty_cells = 0

        for doc in documents:
            insights = self._read_insights(doc)
            cells: list[ReviewCell] = []
            for question in question_tuple:
                cell = self._resolve_cell(question=question, insights=insights)
                cells.append(cell)
                total_cells += 1
                if not cell.is_empty:
                    non_empty_cells += 1

            rows.append(
                ReviewRow(
                    document_id=self._read_int(doc, "id"),
                    filename=str(doc.get("filename") or "").strip() or "(unnamed document)",
                    document_type=self._read_str_or_none(insights.get("document_type")),
                    cells=tuple(cells),
                )
            )

        coverage = (non_empty_cells / total_cells) if total_cells else 0.0
        return ReviewTable(
            case_id=case_id,
            questions=question_tuple,
            rows=tuple(rows),
            coverage=coverage,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Cell resolution per kind
    # ──────────────────────────────────────────────────────────────────────

    def _resolve_cell(
        self,
        *,
        question: ReviewQuestion,
        insights: Mapping[str, Any],
    ) -> ReviewCell:
        kind = question.kind
        values = self._extract_values(kind=kind, insights=insights)
        if not values:
            return ReviewCell(
                question_id=question.id,
                kind=kind,
                values=(),
                evidence_strength="none",
                is_empty=True,
            )
        strength = _STRENGTH_BY_KIND.get(kind, "weak")
        return ReviewCell(
            question_id=question.id,
            kind=kind,
            values=tuple(values),
            evidence_strength=strength,
            is_empty=False,
        )

    def _extract_values(
        self,
        *,
        kind: str,
        insights: Mapping[str, Any],
    ) -> list[str]:
        if kind == QUESTION_KIND_DOCUMENT_TYPE:
            value = self._read_str_or_none(insights.get("document_type"))
            return [value] if value else []

        if kind == QUESTION_KIND_PARTIES:
            return self._string_list(insights.get("parties_detected"))

        if kind == QUESTION_KIND_KEY_DATES:
            return self._format_dates(insights.get("important_dates"))

        if kind == QUESTION_KIND_PAYMENT_TERMS:
            return self._string_list(insights.get("payment_terms"))

        if kind == QUESTION_KIND_TERMINATION_TERMS:
            return self._string_list(insights.get("termination_terms"))

        if kind == QUESTION_KIND_LEGAL_RISKS:
            return self._string_list(insights.get("legal_risks"))

        if kind == QUESTION_KIND_MISSING_EVIDENCE:
            return self._string_list(insights.get("missing_evidence"))

        if kind == QUESTION_KIND_KEY_POINTS:
            return self._string_list(insights.get("key_points"))

        if kind == QUESTION_KIND_RECOMMENDED_ACTIONS:
            return self._string_list(insights.get("recommended_actions"))

        if kind == QUESTION_KIND_SUMMARY:
            value = self._read_str_or_none(insights.get("general_summary"))
            return [value] if value else []

        return []

    # ──────────────────────────────────────────────────────────────────────
    # Defensive readers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _read_insights(doc: Mapping[str, Any]) -> dict[str, Any]:
        embedded = doc.get("insights")
        if isinstance(embedded, Mapping):
            return dict(embedded)
        raw = doc.get("insights_json")
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return parsed
        return {}

    @staticmethod
    def _read_int(doc: Mapping[str, Any], key: str) -> int | None:
        value = doc.get(key)
        return value if isinstance(value, int) else None

    @staticmethod
    def _read_str_or_none(value: Any) -> str | None:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return None

    @staticmethod
    def _string_list(value: Any, *, limit: int = 8) -> list[str]:
        if not isinstance(value, list):
            return []
        rows: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text and text not in rows:
                rows.append(text)
            if len(rows) >= limit:
                break
        return rows

    @staticmethod
    def _format_dates(value: Any, *, limit: int = 8) -> list[str]:
        """Dates payload is a list of dicts ``{label, date}`` per the
        insights extractor. Fall back gracefully to plain strings.
        """

        if not isinstance(value, list):
            return []
        rows: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                label = str(item.get("label") or "").strip()
                date = str(item.get("date") or "").strip()
                if label and date:
                    rows.append(f"{date} — {label}")
                elif date:
                    rows.append(date)
                elif label:
                    rows.append(label)
            else:
                text = str(item or "").strip()
                if text:
                    rows.append(text)
            if len(rows) >= limit:
                break
        return rows


document_review_table_service = DocumentReviewTableService()


__all__ = [
    "ReviewQuestion",
    "ReviewCell",
    "ReviewRow",
    "ReviewTable",
    "DocumentReviewTableService",
    "document_review_table_service",
    "VALID_QUESTION_KINDS",
    "DEFAULT_QUESTION_KINDS",
    "QUESTION_KIND_KEY_DATES",
    "QUESTION_KIND_PARTIES",
    "QUESTION_KIND_PAYMENT_TERMS",
    "QUESTION_KIND_TERMINATION_TERMS",
    "QUESTION_KIND_LEGAL_RISKS",
    "QUESTION_KIND_MISSING_EVIDENCE",
    "QUESTION_KIND_KEY_POINTS",
    "QUESTION_KIND_SUMMARY",
    "QUESTION_KIND_DOCUMENT_TYPE",
    "QUESTION_KIND_RECOMMENDED_ACTIONS",
]
