"""Phase A3 — Document review table service tests."""

from __future__ import annotations

import json
import unittest

from backend.services.ai.document_review_table_service import (
    DEFAULT_QUESTION_KINDS,
    QUESTION_KIND_KEY_DATES,
    QUESTION_KIND_LEGAL_RISKS,
    QUESTION_KIND_PARTIES,
    QUESTION_KIND_PAYMENT_TERMS,
    VALID_QUESTION_KINDS,
    document_review_table_service,
)


SAMPLE_INSIGHTS_FULL = {
    "document_type": "master_service_agreement",
    "general_summary": "MSA between Acme and Doe Corp dated 2024-04-01.",
    "key_points": ["MSA signed", "2-year term", "Renews annually"],
    "important_dates": [
        {"label": "Effective date", "date": "2024-04-01"},
        {"label": "Renewal", "date": "2026-04-01"},
    ],
    "parties_detected": ["Acme Corp", "Doe Corp"],
    "payment_terms": ["Net 30 from invoice date"],
    "termination_terms": ["90-day notice required"],
    "missing_evidence": ["Signed amendment v2"],
    "legal_risks": ["Auto-renew without notice", "Limited liability cap"],
    "recommended_actions": ["Verify renewal calendar"],
}

SAMPLE_INSIGHTS_EMPTY: dict[str, object] = {}


def _doc(doc_id: int, filename: str, insights: dict | None, *, use_json: bool = False) -> dict:
    base: dict[str, object] = {"id": doc_id, "filename": filename}
    if insights is None:
        return base
    if use_json:
        base["insights_json"] = json.dumps(insights)
    else:
        base["insights"] = insights
    return base


class BuildQuestionsTests(unittest.TestCase):
    def test_default_questions_match_default_kinds(self) -> None:
        questions = document_review_table_service.build_questions()
        kinds = tuple(q.kind for q in questions)
        self.assertEqual(kinds, DEFAULT_QUESTION_KINDS)
        for q in questions:
            self.assertEqual(q.id, q.kind)
            self.assertTrue(q.label)

    def test_unknown_kinds_are_silently_dropped(self) -> None:
        questions = document_review_table_service.build_questions(
            kinds=["parties", "bogus", "legal_risks"],
        )
        self.assertEqual(
            tuple(q.kind for q in questions),
            ("parties", "legal_risks"),
        )

    def test_duplicate_kinds_are_deduplicated(self) -> None:
        questions = document_review_table_service.build_questions(
            kinds=["parties", "parties", "legal_risks"],
        )
        self.assertEqual(
            tuple(q.kind for q in questions),
            ("parties", "legal_risks"),
        )

    def test_custom_label_overrides_default(self) -> None:
        questions = document_review_table_service.build_questions(
            kinds=["parties"],
            custom_labels={"parties": "Who"},
        )
        self.assertEqual(questions[0].label, "Who")

    def test_valid_question_kinds_is_complete(self) -> None:
        # Sanity check: every default kind is in VALID_QUESTION_KINDS.
        for kind in DEFAULT_QUESTION_KINDS:
            self.assertIn(kind, VALID_QUESTION_KINDS)


class BuildTableTests(unittest.TestCase):
    def test_full_insights_yield_strong_evidence_cells(self) -> None:
        table = document_review_table_service.build_table(
            case_id=42,
            documents=[_doc(1, "msa.pdf", SAMPLE_INSIGHTS_FULL)],
        )
        self.assertEqual(table.case_id, 42)
        self.assertEqual(len(table.rows), 1)
        row = table.rows[0]
        self.assertEqual(row.document_id, 1)
        self.assertEqual(row.filename, "msa.pdf")
        self.assertEqual(row.document_type, "master_service_agreement")
        self.assertEqual(len(row.cells), len(DEFAULT_QUESTION_KINDS))
        # All default cells should be non-empty for the full sample.
        for cell in row.cells:
            self.assertFalse(cell.is_empty, f"{cell.kind} should not be empty")
            self.assertIn(cell.evidence_strength, {"strong", "medium"})

    def test_empty_insights_yield_empty_cells_with_none_strength(self) -> None:
        table = document_review_table_service.build_table(
            case_id=None,
            documents=[_doc(2, "blank.pdf", SAMPLE_INSIGHTS_EMPTY)],
        )
        row = table.rows[0]
        self.assertIsNone(row.document_type)
        for cell in row.cells:
            self.assertTrue(cell.is_empty)
            self.assertEqual(cell.evidence_strength, "none")
            self.assertEqual(cell.values, ())

    def test_key_dates_are_formatted_as_date_em_dash_label(self) -> None:
        table = document_review_table_service.build_table(
            case_id=1,
            documents=[_doc(1, "msa.pdf", SAMPLE_INSIGHTS_FULL)],
            questions=document_review_table_service.build_questions(
                kinds=[QUESTION_KIND_KEY_DATES],
            ),
        )
        cell = table.rows[0].cells[0]
        self.assertEqual(cell.values[0], "2024-04-01 — Effective date")
        self.assertEqual(cell.values[1], "2026-04-01 — Renewal")

    def test_insights_json_string_is_parsed(self) -> None:
        table = document_review_table_service.build_table(
            case_id=1,
            documents=[_doc(1, "msa.pdf", SAMPLE_INSIGHTS_FULL, use_json=True)],
            questions=document_review_table_service.build_questions(
                kinds=[QUESTION_KIND_PARTIES],
            ),
        )
        cell = table.rows[0].cells[0]
        self.assertEqual(cell.values, ("Acme Corp", "Doe Corp"))
        self.assertEqual(cell.evidence_strength, "strong")

    def test_malformed_insights_json_yields_empty_cells_not_an_exception(self) -> None:
        doc = {"id": 1, "filename": "x.pdf", "insights_json": "{not json"}
        table = document_review_table_service.build_table(
            case_id=None,
            documents=[doc],
        )
        for cell in table.rows[0].cells:
            self.assertTrue(cell.is_empty)

    def test_coverage_is_mean_of_non_empty_cells(self) -> None:
        # 2 docs × 2 questions = 4 cells; only first doc has values → coverage = 0.5
        questions = document_review_table_service.build_questions(
            kinds=[QUESTION_KIND_PARTIES, QUESTION_KIND_LEGAL_RISKS],
        )
        table = document_review_table_service.build_table(
            case_id=1,
            documents=[
                _doc(1, "full.pdf", SAMPLE_INSIGHTS_FULL),
                _doc(2, "empty.pdf", SAMPLE_INSIGHTS_EMPTY),
            ],
            questions=questions,
        )
        self.assertEqual(table.coverage, 0.5)

    def test_unnamed_document_falls_back_to_placeholder(self) -> None:
        table = document_review_table_service.build_table(
            case_id=None,
            documents=[{"id": 5, "filename": "", "insights": SAMPLE_INSIGHTS_FULL}],
        )
        self.assertEqual(table.rows[0].filename, "(unnamed document)")


class TableSerializationTests(unittest.TestCase):
    def test_to_dict_round_trips_full_table_shape(self) -> None:
        table = document_review_table_service.build_table(
            case_id=7,
            documents=[_doc(1, "msa.pdf", SAMPLE_INSIGHTS_FULL)],
            questions=document_review_table_service.build_questions(
                kinds=[QUESTION_KIND_PAYMENT_TERMS],
            ),
        )
        payload = table.to_dict()
        self.assertEqual(payload["case_id"], 7)
        self.assertEqual(len(payload["questions"]), 1)
        self.assertEqual(payload["questions"][0]["kind"], "payment_terms")
        self.assertEqual(len(payload["rows"]), 1)
        cell = payload["rows"][0]["cells"][0]
        self.assertEqual(cell["kind"], "payment_terms")
        self.assertEqual(cell["values"], ["Net 30 from invoice date"])
        self.assertEqual(cell["evidence_strength"], "medium")
        self.assertFalse(cell["is_empty"])
        self.assertEqual(payload["coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
