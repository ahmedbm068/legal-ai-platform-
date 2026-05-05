"""Phase A2 — Drafting outline + citation insertion service tests."""

from __future__ import annotations

import unittest

from backend.services.ai.citation_insertion_service import (
    citation_insertion_service,
)
from backend.services.ai.drafting_outline_service import (
    SUPPORTED_INTENTS,
    drafting_outline_service,
)


class DraftingOutlineSupportTests(unittest.TestCase):
    def test_all_five_drafting_intents_are_supported(self) -> None:
        expected = {
            "draft_client_email_case",
            "draft_internal_email_case",
            "draft_partner_strategy_note_case",
            "draft_negotiation_strategy",
            "draft_contract_redline_case",
        }
        self.assertEqual(SUPPORTED_INTENTS, frozenset(expected))
        for intent in expected:
            self.assertTrue(
                drafting_outline_service.is_supported(intent),
                f"intent {intent} should be supported",
            )

    def test_unsupported_intent_raises(self) -> None:
        self.assertFalse(drafting_outline_service.is_supported("ask_global"))
        with self.assertRaises(ValueError):
            drafting_outline_service.build_outline(intent="ask_global")


class DraftingOutlineShapeTests(unittest.TestCase):
    def test_client_email_outline_has_required_anchor_sections(self) -> None:
        outline = drafting_outline_service.build_outline(
            intent="draft_client_email_case",
        )
        headings = [s.heading for s in outline.sections]
        for expected in ("Subject line", "Status summary", "What we recommend", "Sign-off"):
            self.assertIn(expected, headings, f"missing section: {expected}")
        self.assertEqual(outline.audience, "Client (non-lawyer)")
        self.assertGreaterEqual(len(outline.sections), 5)

    def test_outline_to_dict_round_trip(self) -> None:
        outline = drafting_outline_service.build_outline(
            intent="draft_partner_strategy_note_case",
            objective="Decide whether to settle by Friday.",
        )
        payload = outline.to_dict()
        self.assertEqual(payload["intent"], "draft_partner_strategy_note_case")
        self.assertIsInstance(payload["sections"], list)
        self.assertGreater(len(payload["sections"]), 0)
        first = payload["sections"][0]
        for field in ("heading", "purpose", "suggested_citations", "required"):
            self.assertIn(field, first)

    def test_case_hints_include_objective_and_case_metadata(self) -> None:
        outline = drafting_outline_service.build_outline(
            intent="draft_client_email_case",
            objective="Update on hearing scheduled next week",
            case_context={
                "case": {
                    "title": "Acme v. Doe",
                    "jurisdiction_country": "tunisia",
                    "document_count": 4,
                },
                "risk_signals": ["Statute of limitations risk"],
            },
            jurisdiction="Tunisia",
        )
        joined = " | ".join(outline.case_hints)
        self.assertIn("Objective:", joined)
        self.assertIn("Acme v. Doe", joined)
        self.assertIn("4 case document", joined)
        self.assertIn("Risk:", joined)
        self.assertEqual(outline.jurisdiction, "tunisia")

    def test_case_hints_deduplicate_and_cap(self) -> None:
        outline = drafting_outline_service.build_outline(
            intent="draft_client_email_case",
            case_context={
                "case": {"title": "X", "jurisdiction_country": "tunisia"},
                "risk_signals": ["a", "a", "b", "c", "d", "e"],
            },
        )
        # cap at 6
        self.assertLessEqual(len(outline.case_hints), 6)


class CitationInsertionTests(unittest.TestCase):
    def test_insert_doc_citation_replaces_marker(self) -> None:
        sources = [{"document_id": 7, "filename": "complaint.pdf"}]
        result = citation_insertion_service.insert_citation(
            body="The contract was breached [cite:doc:7] last March.",
            marker_kind="doc",
            ref_id=7,
            sources=sources,
        )
        self.assertTrue(result.inserted)
        self.assertIn("Doc: complaint.pdf", result.body)
        self.assertNotIn("[cite:doc:7]", result.body)

    def test_insert_source_citation_uses_1_based_index(self) -> None:
        citations = [
            {"source_label": "Code Civil art. 99"},
            {"source_label": "Cass. 2024 no. 12"},
        ]
        result = citation_insertion_service.insert_citation(
            body="The article applies [cite:source:2].",
            marker_kind="source",
            ref_id=2,
            citations=citations,
        )
        self.assertTrue(result.inserted)
        self.assertIn("Cass. 2024 no. 12", result.body)

    def test_insert_at_position_when_no_marker(self) -> None:
        sources = [{"document_id": 1, "filename": "doc.pdf"}]
        result = citation_insertion_service.insert_citation(
            body="Hello world",
            marker_kind="doc",
            ref_id=1,
            sources=sources,
            position=5,
        )
        self.assertTrue(result.inserted)
        # space + bracket label inserted at offset 5
        self.assertTrue(result.body.startswith("Hello [Doc: doc.pdf]"))

    def test_unknown_kind_returns_failure_without_modifying_body(self) -> None:
        result = citation_insertion_service.insert_citation(
            body="hello",
            marker_kind="bogus",
            ref_id=1,
        )
        self.assertFalse(result.inserted)
        self.assertEqual(result.body, "hello")
        self.assertIsNone(result.label)

    def test_unknown_doc_id_returns_failure(self) -> None:
        result = citation_insertion_service.insert_citation(
            body="Some text [cite:doc:99]",
            marker_kind="doc",
            ref_id=99,
            sources=[{"document_id": 1, "filename": "x.pdf"}],
        )
        self.assertFalse(result.inserted)
        self.assertEqual(result.body, "Some text [cite:doc:99]")

    def test_position_out_of_bounds_returns_failure(self) -> None:
        result = citation_insertion_service.insert_citation(
            body="short",
            marker_kind="doc",
            ref_id=1,
            sources=[{"document_id": 1, "filename": "x.pdf"}],
            position=999,
        )
        self.assertFalse(result.inserted)
        self.assertEqual(result.body, "short")

    def test_parse_inline_markers_resolves_all_at_once(self) -> None:
        body = (
            "Para A [cite:doc:1]. "
            "Para B [cite:source:1]. "
            "Para C [cite:source:99] (unresolvable)."
        )
        result = citation_insertion_service.parse_inline_markers(
            body=body,
            sources=[{"document_id": 1, "filename": "ex.pdf"}],
            citations=[{"source_label": "Statute X"}],
        )
        self.assertTrue(result.inserted)
        self.assertIn("Doc: ex.pdf", result.body)
        self.assertIn("Statute X", result.body)
        # unresolvable marker stays untouched
        self.assertIn("[cite:source:99]", result.body)
        self.assertIn("substituted=2", result.reason)
        self.assertIn("unresolved=1", result.reason)

    def test_legacy_short_marker_falls_back_to_source(self) -> None:
        result = citation_insertion_service.insert_citation(
            body="Cite this [cite:1] please.",
            marker_kind="source",
            ref_id=1,
            citations=[{"source_label": "Legacy Short"}],
        )
        self.assertTrue(result.inserted)
        self.assertIn("Legacy Short", result.body)
        self.assertNotIn("[cite:1]", result.body)


if __name__ == "__main__":
    unittest.main()
