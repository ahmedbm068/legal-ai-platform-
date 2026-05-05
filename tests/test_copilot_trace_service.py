"""Tests for Phase B \u2014 copilot_trace_service.

Pure-Python tests with a fake SQLAlchemy ``Session`` so we can validate the
recording behaviour without standing up a real DB.
"""

from __future__ import annotations

import json
import unittest
from typing import Any

from backend.services.ai.copilot_trace_service import (
    VERDICT_ERROR,
    VERDICT_PARTIAL,
    VERDICT_REFUSED,
    VERDICT_UNVERIFIED,
    VERDICT_VERIFIED,
    copilot_trace_service,
    extract_mini_agents,
    extract_verdict,
)


class _FakeSession:
    """Captures ``add`` calls. Mimics the bits the service uses."""

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.committed = 0
        self.rolled_back = 0
        self.refresh_calls = 0

    def add(self, instance: Any) -> None:
        self.added.append(instance)

    def commit(self) -> None:
        self.committed += 1
        # Simulate an autoincrement id assignment on commit.
        if self.added:
            last = self.added[-1]
            if getattr(last, "id", None) is None:
                last.id = len(self.added)

    def refresh(self, instance: Any) -> None:
        self.refresh_calls += 1

    def rollback(self) -> None:
        self.rolled_back += 1


class ExtractMiniAgentsTests(unittest.TestCase):
    def test_pulls_from_selected_agents_first(self) -> None:
        state = {"selected_agents": ["intake_agent", "drafting_agent"]}
        self.assertEqual(
            extract_mini_agents(state, {}),
            ["intake_agent", "drafting_agent"],
        )

    def test_merges_with_agent_outputs_dedup(self) -> None:
        state = {
            "selected_agents": ["intake_agent"],
            "agent_outputs": {"intake_agent": {}, "verifier_agent": {}},
        }
        agents = extract_mini_agents(state, {})
        self.assertIn("intake_agent", agents)
        self.assertIn("verifier_agent", agents)
        # No duplicates for intake_agent.
        self.assertEqual(agents.count("intake_agent"), 1)

    def test_includes_legal_agent_pack_sequence(self) -> None:
        state = {"selected_agents": []}
        result = {
            "structured_result": {
                "legal_workflow_agents": {
                    "agent_sequence": ["fact_extraction", "rule_synthesis"],
                }
            }
        }
        agents = extract_mini_agents(state, result)
        self.assertIn("fact_extraction", agents)
        self.assertIn("rule_synthesis", agents)

    def test_returns_empty_when_nothing_known(self) -> None:
        self.assertEqual(extract_mini_agents({}, {}), [])


class ExtractVerdictTests(unittest.TestCase):
    def test_permission_denied_is_refused(self) -> None:
        self.assertEqual(extract_verdict({}, {"permission_denied": True}), VERDICT_REFUSED)

    def test_verified_status_is_verified(self) -> None:
        result = {
            "structured_result": {
                "global_output_contract": {"verification_status": "verified"}
            }
        }
        self.assertEqual(extract_verdict({}, result), VERDICT_VERIFIED)

    def test_partial_status_is_partial(self) -> None:
        result = {
            "structured_result": {
                "global_output_contract": {"verification_status": "partial"}
            }
        }
        self.assertEqual(extract_verdict({}, result), VERDICT_PARTIAL)

    def test_not_verified_aliases_to_unverified(self) -> None:
        result = {
            "structured_result": {
                "global_output_contract": {
                    "verification_status": "not_verified_no_direct_source"
                }
            }
        }
        self.assertEqual(extract_verdict({}, result), VERDICT_UNVERIFIED)

    def test_errors_in_state_yield_error_verdict_when_no_contract(self) -> None:
        state = {"errors": [{"node": "x", "error_type": "RuntimeError"}]}
        self.assertEqual(extract_verdict(state, {}), VERDICT_ERROR)


class RecordTests(unittest.TestCase):
    def _base_state(self, **overrides: Any) -> dict[str, Any]:
        state = {
            "request_id": "00000000-0000-0000-0000-000000000001",
            "tenant_id": 7,
            "user_id": 11,
            "intent_name": "draft_client_email_case",
            "intent": "draft_client_email_case",
            "route": "agent_execution",
            "mode": "default",
            "effective_mode": "default",
            "trust_enabled": True,
            "use_trust_engine": True,
            "matter_type": "contract",
            "task_type": "drafting",
            "warnings": [],
            "errors": [],
            "selected_agents": ["intake_agent", "drafting_agent"],
            "agent_outputs": {"copilot_service": {}},
            "stage_records": [],
            "workspace_case_id": 42,
        }
        state.update(overrides)
        return state

    def _base_result(self, **overrides: Any) -> dict[str, Any]:
        result = {
            "answer": "ok",
            "confidence": "high",
            "used_fallback": False,
            "structured_result": {
                "global_output_contract": {"verification_status": "verified"}
            },
        }
        result.update(overrides)
        return result

    def test_record_persists_a_row_with_expected_fields(self) -> None:
        db = _FakeSession()
        new_id = copilot_trace_service.record(
            db=db, state=self._base_state(), result=self._base_result(), duration_ms=125.7
        )

        self.assertIsNotNone(new_id)
        self.assertEqual(len(db.added), 1)
        row = db.added[0]
        self.assertEqual(row.call_id, "00000000-0000-0000-0000-000000000001")
        self.assertEqual(row.tenant_id, 7)
        self.assertEqual(row.user_id, 11)
        self.assertEqual(row.case_id, 42)
        self.assertEqual(row.intent, "draft_client_email_case")
        self.assertEqual(row.big_agent, "drafting_agent")  # routed by intent
        self.assertEqual(row.route, "agent_execution")
        self.assertEqual(row.verdict, VERDICT_VERIFIED)
        self.assertEqual(row.confidence, "high")
        self.assertEqual(row.used_fallback, 0)
        self.assertEqual(row.error_count, 0)
        self.assertEqual(row.duration_ms, 125)

        mini = json.loads(row.mini_agents_used_json)
        self.assertIn("intake_agent", mini)
        self.assertIn("drafting_agent", mini)

    def test_record_returns_none_when_call_id_missing(self) -> None:
        db = _FakeSession()
        new_id = copilot_trace_service.record(
            db=db,
            state={"tenant_id": 1, "intent_name": "ask_global"},
            result={},
        )
        self.assertIsNone(new_id)
        self.assertEqual(len(db.added), 0)

    def test_record_handles_unknown_verification_status_as_unverified(self) -> None:
        db = _FakeSession()
        copilot_trace_service.record(
            db=db,
            state=self._base_state(),
            result=self._base_result(
                structured_result={
                    "global_output_contract": {"verification_status": "garbage_value"}
                }
            ),
        )
        self.assertEqual(db.added[0].verdict, VERDICT_UNVERIFIED)

    def test_record_records_error_count_when_state_has_errors(self) -> None:
        db = _FakeSession()
        state = self._base_state(errors=[{"node": "verifier", "error_type": "TimeoutError"}])
        copilot_trace_service.record(db=db, state=state, result=self._base_result())
        self.assertEqual(db.added[0].error_count, 1)

    def test_record_unknown_intent_leaves_big_agent_null(self) -> None:
        db = _FakeSession()
        state = self._base_state(intent_name="totally_unknown_intent", intent="totally_unknown_intent")
        copilot_trace_service.record(db=db, state=state, result=self._base_result())
        self.assertIsNone(db.added[0].big_agent)


class SerializeTests(unittest.TestCase):
    def test_serialize_round_trips_json_columns(self) -> None:
        from backend.models.copilot_trace import CopilotTrace

        row = CopilotTrace(
            id=1,
            call_id="abc",
            tenant_id=1,
            intent="ask_global",
            big_agent="research_agent",
            verdict="verified",
            error_count=0,
            mini_agents_used_json=json.dumps(["a", "b"]),
            stages_json=json.dumps([{"name": "intent_detection", "status": "success"}]),
            metadata_json=json.dumps({"matter_type": "contract"}),
        )
        payload = copilot_trace_service.serialize(row)
        self.assertEqual(payload["call_id"], "abc")
        self.assertEqual(payload["mini_agents_used"], ["a", "b"])
        self.assertEqual(payload["stages"][0]["name"], "intent_detection")
        self.assertEqual(payload["metadata"]["matter_type"], "contract")

    def test_serialize_handles_missing_json_columns(self) -> None:
        from backend.models.copilot_trace import CopilotTrace

        row = CopilotTrace(
            id=2,
            call_id="zzz",
            verdict="not_run",
            error_count=0,
        )
        payload = copilot_trace_service.serialize(row)
        self.assertEqual(payload["mini_agents_used"], [])
        self.assertEqual(payload["stages"], [])
        self.assertEqual(payload["metadata"], {})


if __name__ == "__main__":
    unittest.main()
