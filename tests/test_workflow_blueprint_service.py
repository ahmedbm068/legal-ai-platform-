"""Tests for Phase A4 — workflow blueprint catalog."""

from __future__ import annotations

import unittest

from backend.services.ai.workflow_blueprint_service import (
    PREREQ_HAS_CASE_TITLE,
    PREREQ_HAS_DOCUMENTS,
    PREREQ_HAS_JURISDICTION,
    PREREQ_HAS_TRANSCRIPTS,
    STATUS_AVAILABLE,
    STATUS_BLOCKED,
    VALID_PREREQS,
    WorkflowBlueprintService,
    derive_case_flags,
    workflow_blueprint_service,
)


class CatalogTests(unittest.TestCase):
    def test_module_singleton_exposed(self) -> None:
        self.assertIsInstance(workflow_blueprint_service, WorkflowBlueprintService)

    def test_catalog_contains_expected_blueprints(self) -> None:
        ids = {bp.id for bp in workflow_blueprint_service.list_blueprints()}
        self.assertIn("case_brief_pack", ids)
        self.assertIn("irac_analysis", ids)
        self.assertIn("risk_triage", ids)
        self.assertIn("contract_redline_pack", ids)
        self.assertIn("client_call_recap", ids)

    def test_blueprint_steps_are_non_empty_and_have_agent(self) -> None:
        for bp in workflow_blueprint_service.list_blueprints():
            self.assertGreater(len(bp.steps), 0, msg=f"{bp.id} has no steps")
            for step in bp.steps:
                self.assertTrue(step.name)
                self.assertTrue(step.agent)

    def test_blueprint_prerequisites_are_known(self) -> None:
        for bp in workflow_blueprint_service.list_blueprints():
            for prereq in bp.prerequisites:
                self.assertIn(prereq, VALID_PREREQS, msg=f"{bp.id}: {prereq}")

    def test_to_dict_serializes_steps_as_dicts(self) -> None:
        bp = workflow_blueprint_service.get("case_brief_pack")
        self.assertIsNotNone(bp)
        payload = bp.to_dict()  # type: ignore[union-attr]
        self.assertEqual(payload["id"], "case_brief_pack")
        self.assertIsInstance(payload["steps"], list)
        self.assertIsInstance(payload["steps"][0], dict)
        self.assertIn("agent", payload["steps"][0])

    def test_get_unknown_blueprint_returns_none(self) -> None:
        self.assertIsNone(workflow_blueprint_service.get("does-not-exist"))


class PrerequisiteTests(unittest.TestCase):
    def test_blueprint_available_when_all_prereqs_met(self) -> None:
        availability = workflow_blueprint_service.check_prerequisites(
            blueprint_id="case_brief_pack",
            case_flags={
                PREREQ_HAS_DOCUMENTS: True,
                PREREQ_HAS_CASE_TITLE: True,
            },
        )
        self.assertEqual(availability.status, STATUS_AVAILABLE)
        self.assertEqual(availability.missing_prerequisites, ())

    def test_blueprint_blocked_when_documents_missing(self) -> None:
        availability = workflow_blueprint_service.check_prerequisites(
            blueprint_id="case_brief_pack",
            case_flags={PREREQ_HAS_CASE_TITLE: True},
        )
        self.assertEqual(availability.status, STATUS_BLOCKED)
        self.assertIn(PREREQ_HAS_DOCUMENTS, availability.missing_prerequisites)

    def test_unknown_blueprint_is_blocked(self) -> None:
        availability = workflow_blueprint_service.check_prerequisites(
            blueprint_id="ghost", case_flags={}
        )
        self.assertEqual(availability.status, STATUS_BLOCKED)
        self.assertIn("unknown_blueprint", availability.missing_prerequisites)

    def test_none_case_flags_blocks_anything_with_prereqs(self) -> None:
        availability = workflow_blueprint_service.check_prerequisites(
            blueprint_id="risk_triage", case_flags=None
        )
        self.assertEqual(availability.status, STATUS_BLOCKED)
        self.assertIn(PREREQ_HAS_DOCUMENTS, availability.missing_prerequisites)

    def test_availability_for_case_returns_one_record_per_blueprint(self) -> None:
        flags = {
            PREREQ_HAS_DOCUMENTS: True,
            PREREQ_HAS_CASE_TITLE: True,
            PREREQ_HAS_TRANSCRIPTS: False,
        }
        records = workflow_blueprint_service.availability_for_case(case_flags=flags)
        self.assertEqual(
            len(records), len(workflow_blueprint_service.list_blueprints())
        )
        by_id = {r.blueprint_id: r for r in records}
        self.assertEqual(by_id["case_brief_pack"].status, STATUS_AVAILABLE)
        self.assertEqual(by_id["client_call_recap"].status, STATUS_BLOCKED)
        self.assertIn(
            PREREQ_HAS_TRANSCRIPTS,
            by_id["client_call_recap"].missing_prerequisites,
        )


class DeriveCaseFlagsTests(unittest.TestCase):
    def test_empty_payload_yields_all_false(self) -> None:
        flags = derive_case_flags(None)
        self.assertEqual(set(flags.keys()), set(VALID_PREREQS))
        self.assertFalse(any(flags.values()))

    def test_document_count_drives_has_documents(self) -> None:
        flags = derive_case_flags({"document_count": 3, "title": "X"})
        self.assertTrue(flags[PREREQ_HAS_DOCUMENTS])
        self.assertTrue(flags[PREREQ_HAS_CASE_TITLE])
        self.assertFalse(flags[PREREQ_HAS_TRANSCRIPTS])

    def test_blank_title_is_falsey(self) -> None:
        flags = derive_case_flags({"title": "   "})
        self.assertFalse(flags[PREREQ_HAS_CASE_TITLE])

    def test_jurisdiction_string_drives_flag(self) -> None:
        flags = derive_case_flags({"jurisdiction_country": "FR"})
        self.assertTrue(flags[PREREQ_HAS_JURISDICTION])

    def test_transcripts_list_drives_flag(self) -> None:
        flags = derive_case_flags({"voice_recordings": [{"id": 1}]})
        self.assertTrue(flags[PREREQ_HAS_TRANSCRIPTS])


if __name__ == "__main__":
    unittest.main()
